import json
import re
from typing import Dict, Any, List, Optional, Iterator
from search.hybrid import run_hybrid_search
from search.table_search import run_table_hybrid_search, convert_table_rows_to_chunks
from search.reranker import rerank
from llm.query_embed import embed_query
from llm.chat import get_chat_client, NagaChat
from qa.synth import build_context, build_messages, to_citations
from core.settings import settings

def answer_question(
    question: str, 
    filters: Dict[str, Any], 
    size: int = 64,
    toc_boost_clauses: Optional[List[Dict]] = None,
    enable_smart_suggestions: bool = True
) -> Dict[str, Any]:
    """
    Answer a question using RAG: retrieve, rerank, generate answer with citations.
    If no results found and smart suggestions enabled, suggest alternative queries.
    
    Args:
        question: User's natural language question
        filters: Dict with project_id, doc_type, discipline filters
        size: Number of candidates to retrieve (before reranking)
        toc_boost_clauses: Optional TOC-based boost clauses for hybrid search
        enable_smart_suggestions: If True, generate query suggestions when no results found
    
    Returns:
        Dict with 'answer' (str), 'citations' (list), and optionally 'suggestions' (list)
    """
    # 1) Retrieve with hybrid search (with optional TOC boosting)
    qvec = embed_query(question)
    hits = run_hybrid_search(
        query=question, 
        query_vector=qvec, 
        size=size, 
        num_candidates=200, 
        filters=filters,
        toc_boost_clauses=toc_boost_clauses
    )
    
    # 1b) Also search table rows if Unstructured is enabled
    table_chunks = []
    if settings.USE_UNSTRUCTURED:
        try:
            table_rows = run_table_hybrid_search(
                query=question,
                query_vector=qvec,
                project_id=filters.get("project_id"),
                doc_id=filters.get("doc_id"),
                doc_type=filters.get("doc_type"),
                discipline=filters.get("discipline"),
                size=20  # Get some table results
            )
            if table_rows:
                table_chunks = convert_table_rows_to_chunks(table_rows)
                print(f"[Table-Search] Found {len(table_chunks)} table rows")
        except Exception as e:
            print(f"[Table-Search] Warning: Table search failed: {e}")
    
    if not hits and not table_chunks:
        return {
            "answer": "Not found in the project documents.",
            "citations": []
        }
    
    # 2) Rerank with Cohere (combine chunks and tables)
    all_items = hits + table_chunks
    if all_items:
        order = rerank(question, all_items)
        all_items = [all_items[i] for i in order[:15]]  # Top 15 after reranking (increased from 10 for better coverage)
    
    # 3) Build context from reranked results
    chunks = []
    for item in all_items:
        # Handle both regular hits and table chunks
        if "_source" in item:  # Regular chunk from OpenSearch
            s = item["_source"]
            chunks.append({
                "chunk_id": s["chunk_id"],
                "doc_id": s["doc_id"],
                "project_id": s["project_id"],
                "page_number": s["page_number"],
                "section": s.get("section"),
                "text": s["text"],
                "bbox": s.get("bbox"),
                "source": s.get("source"),
                "confidence": s.get("confidence"),
            })
        else:  # Table chunk (already in chunk format)
            chunks.append(item)
    
    context_text, selected = build_context(chunks)
    
    # Debug: Log token usage and bbox presence
    try:
        import tiktoken
        tokenizer = tiktoken.get_encoding("cl100k_base")
        context_tokens = len(tokenizer.encode(context_text))
        print(f"[Token-Aware] Context: {len(context_text)} chars, {context_tokens} tokens, {len(selected)} chunks")
    except Exception:
        print(f"[Char-Based] Context: {len(context_text)} chars, {len(selected)} chunks")
    
    # Debug: Check if selected chunks have bbox
    for i, c in enumerate(selected[:3]):
        bbox_info = c.get("bbox", "MISSING")
        print(f"[Debug] Selected chunk {i}: doc={c['doc_id']} page={c['page_number']} bbox={bbox_info}")
    
    # Debug: Show first 500 chars of context
    print(f"[Debug] Context preview:\n{context_text[:500]}\n...")
    
    # 7) Call LLM with strict citation prompt (use original question)
    chat = get_chat_client()
    messages = build_messages(question, context_text)  # Use original question
    raw = chat.chat(messages=messages, temperature=0.0, max_tokens=600)
    
    print(f"[Debug] LLM raw response:\n{raw}\n")
    
    # 8) Parse strict JSON; fallback with repair attempt if needed
    try:
        data = json.loads(raw)
        
        # Sanity: require citations array
        if "citations" not in data or not isinstance(data.get("citations"), list):
            raise ValueError("Missing or invalid citations field")
        
        # If answer says "Not found", clear citations and try smart suggestions
        if data.get("answer", "").lower().startswith("not found"):
            data["citations"] = []
            
            # Generate smart suggestions if enabled
            if enable_smart_suggestions:
                from search.query_suggestions import find_working_suggestions
                print(f"[Smart Suggestions] LLM returned 'Not found' - generating suggestions...")
                suggestions = find_working_suggestions(question, answer_question_no_suggestions, filters, max_to_test=3)
                print(f"[Smart Suggestions] Found {len(suggestions)} working suggestions")
                
                if suggestions:
                    data["suggestions"] = suggestions
        # If model forgot citations but has an answer, add fallback
        elif len(data["citations"]) == 0 and data.get("answer"):
            data["citations"] = to_citations(selected)
        else:
            # Fix bbox: LLM often returns [0,0,0,0], so merge with actual chunk bbox
            print(f"[Debug] Fixing bboxes for {len(data['citations'])} citations")
            for cite in data["citations"]:
                print(f"[Debug] Citation: doc={cite.get('doc_id')} page={cite.get('page_number')} bbox_before={cite.get('bbox')}")
                # Find matching chunk by doc_id and page_number
                matched = False
                for chunk in selected:
                    if (cite.get("doc_id") == chunk["doc_id"] and 
                        cite.get("page_number") == chunk["page_number"]):
                        matched = True
                        chunk_bbox = chunk.get("bbox")
                        print(f"[Debug] Matched chunk bbox={chunk_bbox}")
                        # Replace bbox if it's missing or all zeros
                        if not cite.get("bbox") or cite["bbox"] == [0, 0, 0, 0]:
                            cite["bbox"] = chunk_bbox
                            print(f"[Debug] Fixed bbox to {cite['bbox']}")
                        break
                if not matched:
                    print(f"[Debug] No matching chunk found for doc={cite.get('doc_id')} page={cite.get('page_number')}")
        
        # Trim snippet sizes for frontend
        for c in data["citations"]:
            if "snippet" in c and c["snippet"] and len(c["snippet"]) > 240:
                c["snippet"] = c["snippet"][:240] + "…"
        
        return data
    
    except Exception as e:
        # JSON repair attempt: extract first {...} block
        # Handles cases where LLM adds prose or markdown code fences
        match = re.search(r'\{.*\}', raw, flags=re.DOTALL)
        if match:
            try:
                data = json.loads(match.group(0))
                
                # Same validation as above
                if "citations" in data and isinstance(data.get("citations"), list):
                    if data.get("answer", "").lower().startswith("not found"):
                        data["citations"] = []
                        
                        # Generate smart suggestions if enabled (same as main path)
                        if enable_smart_suggestions:
                            from search.query_suggestions import find_working_suggestions
                            print(f"[Smart Suggestions] LLM returned 'Not found' - generating suggestions...")
                            suggestions = find_working_suggestions(question, answer_question_no_suggestions, filters, max_to_test=3)
                            print(f"[Smart Suggestions] Found {len(suggestions)} working suggestions")
                            
                            if suggestions:
                                data["suggestions"] = suggestions
                    elif len(data["citations"]) == 0 and data.get("answer"):
                        data["citations"] = to_citations(selected)
                    else:
                        # Fix bbox: merge with actual chunk bbox
                        for cite in data["citations"]:
                            for chunk in selected:
                                if (cite.get("doc_id") == chunk["doc_id"] and 
                                    cite.get("page_number") == chunk["page_number"]):
                                    if not cite.get("bbox") or cite["bbox"] == [0, 0, 0, 0]:
                                        cite["bbox"] = chunk.get("bbox")
                                    break
                    
                    # Trim snippets
                    for c in data["citations"]:
                        if "snippet" in c and c["snippet"] and len(c["snippet"]) > 240:
                            c["snippet"] = c["snippet"][:240] + "…"
                    
                    return data
            except Exception:
                pass  # Fall through to conservative fallback
        
        # Conservative fallback: always return useful citations
        return {
            "answer": "Not found in the project documents." if not selected else "See cited excerpts.",
            "citations": to_citations(selected)
        }


def answer_question_no_suggestions(
    question: str, 
    filters: Dict[str, Any], 
    size: int = 64,
    toc_boost_clauses: Optional[List[Dict]] = None
) -> Dict[str, Any]:
    """
    Wrapper for answer_question with smart suggestions disabled.
    Used when testing query suggestions to avoid infinite recursion.
    """
    return answer_question(question, filters, size, toc_boost_clauses, enable_smart_suggestions=False)


def answer_question_stream(
    question: str,
    filters: Dict[str, Any],
    size: int = 64,
    toc_boost_clauses: Optional[List[Dict]] = None
) -> Iterator[str]:
    """
    Stream answer generation using Server-Sent Events.
    
    Yields JSON chunks in SSE format:
    - data: {"type": "status", "message": "Searching..."} 
    - data: {"type": "chunk", "content": "partial answer..."}
    - data: {"type": "done", "answer": "full answer", "citations": [...]}
    
    Args:
        question: User's natural language question
        filters: Dict with project_id, doc_type, discipline filters
        size: Number of candidates to retrieve (before reranking)
        toc_boost_clauses: Optional TOC-based boost clauses
    
    Yields:
        SSE-formatted strings with JSON data
    """
    import time
    
    try:
        # Step 1: Search (fast) - send status update
        yield f"data: {json.dumps({'type': 'status', 'message': 'Searching documents...'})}\n\n"
        
        qvec = embed_query(question)
        hits = run_hybrid_search(
            query=question,
            query_vector=qvec,
            size=size,
            num_candidates=200,
            filters=filters,
            toc_boost_clauses=toc_boost_clauses
        )
        
        # Also search tables
        table_chunks = []
        if settings.USE_UNSTRUCTURED:
            try:
                table_rows = run_table_hybrid_search(
                    query=question,
                    query_vector=qvec,
                    project_id=filters.get("project_id"),
                    doc_id=filters.get("doc_id"),
                    doc_type=filters.get("doc_type"),
                    discipline=filters.get("discipline"),
                    size=20
                )
                if table_rows:
                    table_chunks = convert_table_rows_to_chunks(table_rows)
            except Exception as e:
                print(f"[Table-Search] Warning: {e}")
        
        if not hits and not table_chunks:
            yield f"data: {json.dumps({'type': 'done', 'answer': 'Not found in the project documents.', 'citations': []})}\n\n"
            return
        
        # Step 2: Rerank (fast) - send status update
        yield f"data: {json.dumps({'type': 'status', 'message': 'Ranking results...'})}\n\n"
        
        all_items = hits + table_chunks
        if all_items:
            order = rerank(question, all_items)
            all_items = [all_items[i] for i in order[:15]]
        
        # Build context
        chunks = []
        for item in all_items:
            if "_source" in item:
                s = item["_source"]
                chunks.append({
                    "chunk_id": s["chunk_id"],
                    "doc_id": s["doc_id"],
                    "project_id": s["project_id"],
                    "page_number": s["page_number"],
                    "section": s.get("section"),
                    "text": s["text"],
                    "bbox": s.get("bbox"),
                    "source": s.get("source"),
                    "confidence": s.get("confidence"),
                })
            else:
                chunks.append(item)
        
        context_text, selected = build_context(chunks)
        
        # Step 3: LLM Generation (slow) - stream this part
        yield f"data: {json.dumps({'type': 'status', 'message': 'Generating answer...'})}\n\n"
        
        messages = build_messages(question, context_text)
        
        # Only NagaChat supports streaming for now
        chat_client = get_chat_client()
        extracted_answer = ""  # Keep track of extracted answer for fallback
        
        if not isinstance(chat_client, NagaChat):
            # Fallback to non-streaming for Cohere
            response_text = chat_client.chat(messages, temperature=0.0, max_tokens=500)
            # Try to extract answer from JSON for display
            try:
                parsed = json.loads(response_text)
                display_text = parsed.get('answer', response_text)
                extracted_answer = display_text
            except:
                display_text = response_text
                extracted_answer = response_text
            yield f"data: {json.dumps({'type': 'chunk', 'content': display_text})}\n\n"
        else:
            # Stream the response - extract answer from JSON as it comes
            accumulated_text = ""
            last_answer_length = 0
            
            for chunk in chat_client.stream(messages, temperature=0.0, max_tokens=500):
                accumulated_text += chunk
                
                # Use regex to extract content from "answer" field (works even with incomplete JSON)
                # More robust pattern that handles escaped quotes, newlines, and special chars
                import re
                # Try to match: "answer": "content..." where content can include escaped quotes
                # Pattern explanation: match everything after "answer":" until we hit an unescaped quote followed by comma or closing brace
                match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)(?:"|$)', accumulated_text, re.DOTALL)
                
                if match:
                    # Extract the answer text (handle escaped characters)
                    raw_answer = match.group(1)
                    # Unescape common escape sequences
                    answer_text = raw_answer.replace('\\"', '"').replace('\\n', '\n').replace('\\/', '/').replace('\\\\', '\\')
                    extracted_answer = answer_text  # Save for fallback
                    
                    # Only yield new content
                    if len(answer_text) > last_answer_length:
                        new_content = answer_text[last_answer_length:]
                        if new_content:  # Only send if there's actual new content
                            yield f"data: {json.dumps({'type': 'chunk', 'content': new_content})}\n\n"
                        last_answer_length = len(answer_text)
            
            response_text = accumulated_text
        
        # Step 4: Parse and send final result
        try:
            # Try to parse as JSON
            data = json.loads(response_text)
            
            # Fix bboxes
            if "citations" in data and selected:
                for c in data["citations"]:
                    if "bbox" in c and c.get("doc_id") and c.get("page_number") is not None:
                        # Find matching chunk
                        for chunk in selected:
                            if chunk["doc_id"] == c["doc_id"] and chunk["page_number"] == c["page_number"]:
                                if chunk.get("bbox"):
                                    c["bbox"] = chunk["bbox"]
                                break
            
            # Check if answer is "Not found" and generate suggestions
            if data.get("answer", "").lower().startswith("not found"):
                data["citations"] = []
                
                # Generate smart suggestions
                yield f"data: {json.dumps({'type': 'status', 'message': 'Finding alternative queries...'})}\n\n"
                
                from search.query_suggestions import find_working_suggestions
                print(f"[Smart Suggestions] LLM returned 'Not found' - generating suggestions...")
                suggestions = find_working_suggestions(question, answer_question_no_suggestions, filters, max_to_test=3)
                print(f"[Smart Suggestions] Found {len(suggestions)} working suggestions")
                
                if suggestions:
                    data["suggestions"] = suggestions
            
            yield f"data: {json.dumps({'type': 'done', 'answer': data.get('answer', ''), 'citations': data.get('citations', []), 'suggestions': data.get('suggestions', [])})}\n\n"
        
        except json.JSONDecodeError as e:
            # Fallback if LLM didn't return valid JSON - use the extracted answer from streaming
            fallback_answer = extracted_answer if extracted_answer else "See cited excerpts."
            print(f"[QA Stream] JSON parse failed: {str(e)}")
            print(f"[QA Stream] Raw response (first 500 chars): {response_text[:500]}")
            print(f"[QA Stream] Extracted answer length: {len(fallback_answer)}")
            print(f"[QA Stream] Using extracted answer: {fallback_answer[:200]}...")
            
            # Check if answer is "Not found" and generate suggestions
            fallback_suggestions = []
            fallback_citations = []
            
            if fallback_answer.lower().startswith("not found"):
                # No citations for "Not found" responses
                fallback_citations = []
                
                # Generate suggestions
                yield f"data: {json.dumps({'type': 'status', 'message': 'Finding alternative queries...'})}\n\n"
                
                from search.query_suggestions import find_working_suggestions
                print(f"[Smart Suggestions Stream] Generating suggestions for fallback answer...")
                fallback_suggestions = find_working_suggestions(question, answer_question_no_suggestions, filters, max_to_test=3)
                print(f"[Smart Suggestions Stream] Found {len(fallback_suggestions)} working suggestions")
                if fallback_suggestions:
                    for i, sug in enumerate(fallback_suggestions, 1):
                        print(f"[Smart Suggestions Stream]   {i}. {sug.get('query', 'N/A')}")
            else:
                # Use selected chunks as citations for regular answers
                fallback_citations = to_citations(selected)
            
            # Log what we're sending to frontend
            print(f"[QA Stream] Sending to frontend:")
            print(f"  Answer: {fallback_answer[:50]}...")
            print(f"  Citations: {len(fallback_citations)}")
            print(f"  Suggestions: {len(fallback_suggestions)}")
            
            yield f"data: {json.dumps({'type': 'done', 'answer': fallback_answer, 'citations': fallback_citations, 'suggestions': fallback_suggestions})}\n\n"
    
    except Exception as e:
        # Error handling
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)})}\n\n"
