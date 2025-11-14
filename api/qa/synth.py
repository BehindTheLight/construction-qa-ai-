from typing import List, Dict, Any, Tuple
import tiktoken

# Token-aware limits (more precise than character-based)
MAX_CONTEXT_TOKENS = 8000  # Safe budget for most models (leaves room for output)
RESERVED_TOKENS = 500      # For system prompt + user message wrapper
MAX_TOKENS_PER_CHUNK = 300  # ~1200 chars, but exact

def _dedupe_and_limit(chunks: List[Dict[str, Any]], max_items: int = 10) -> List[Dict[str, Any]]:
    """
    Deduplicate by chunk_id and prefer diverse pages/doc_ids.
    
    Ensures we don't flood the context with multiple chunks from the same page.
    """
    seen_chunks = set()
    seen_pages = {}
    out = []
    
    for c in chunks:
        chunk_id = c["chunk_id"]
        if chunk_id in seen_chunks:
            continue
        
        seen_chunks.add(chunk_id)
        
        # Prefer diversity: keep first per (doc_id, page_number)
        key = (c["doc_id"], c["page_number"])
        if key in seen_pages:
            continue
        
        seen_pages[key] = True
        out.append(c)
        
        if len(out) >= max_items:
            break
    
    return out

def _trim_to_sentence_boundary(text: str, max_chars: int) -> str:
    """Trim text at sentence boundary to avoid cutting mid-sentence."""
    if len(text) <= max_chars:
        return text
    
    # Find last period, exclamation, or question mark before limit
    truncated = text[:max_chars]
    last_period = max(
        truncated.rfind('. '),
        truncated.rfind('! '),
        truncated.rfind('? ')
    )
    
    if last_period > max_chars * 0.7:  # Keep if we don't lose >30%
        return text[:last_period + 1]
    else:
        return truncated + "…"

def build_context(chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Build LLM context from retrieved chunks with token-aware truncation.
    
    Uses tiktoken to count actual tokens and trim intelligently at sentence boundaries.
    Ensures we never exceed the model's context limit.
    
    Returns:
        (context_text, selected_chunks)
    """
    try:
        # Initialize tokenizer (cl100k_base is used by gpt-4, gpt-3.5-turbo)
        tokenizer = tiktoken.get_encoding("cl100k_base")
    except Exception:
        # Fallback to character-based if tiktoken fails
        return _build_context_char_based(chunks)
    
    # Deduplicate and limit to reasonable number
    candidates = _dedupe_and_limit(chunks, max_items=15)  # Over-fetch, trim by tokens
    
    available_tokens = MAX_CONTEXT_TOKENS - RESERVED_TOKENS
    selected = []
    sections = []
    current_tokens = 0
    
    for i, c in enumerate(candidates, 1):
        # Build header (always included)
        bbox_str = ""
        if c.get("bbox") and len(c.get("bbox", [])) == 4:
            bbox = c["bbox"]
            bbox_str = f" bbox=[{bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}]"
        
        header = (
            f"[{i}] doc_id={c['doc_id']} "
            f"page={c['page_number']} "
            f"source={c.get('source', 'text')} "
            f"conf={c.get('confidence')}"
            f"{bbox_str}\n"
        )
        header_tokens = len(tokenizer.encode(header))
        
        # Count tokens in chunk text
        text = c["text"]
        text_tokens = len(tokenizer.encode(text))
        total_tokens = header_tokens + text_tokens + 2  # +2 for "\n\n" separator
        
        if current_tokens + total_tokens <= available_tokens:
            # Chunk fits completely
            sections.append(header + text)
            selected.append(c)
            current_tokens += total_tokens
        elif current_tokens + header_tokens + 100 <= available_tokens:
            # Partial fit: trim text at sentence boundary
            remaining = available_tokens - current_tokens - header_tokens - 2
            
            # Binary search for max text that fits
            chars_per_token = len(text) / text_tokens if text_tokens > 0 else 4
            estimated_chars = int(remaining * chars_per_token)
            
            # Trim at sentence boundary
            trimmed = _trim_to_sentence_boundary(text, estimated_chars)
            trimmed_tokens = len(tokenizer.encode(trimmed))
            
            # Adjust if estimate was off
            while trimmed_tokens > remaining and len(trimmed) > 100:
                trimmed = _trim_to_sentence_boundary(trimmed, len(trimmed) - 100)
                trimmed_tokens = len(tokenizer.encode(trimmed))
            
            if trimmed_tokens >= 50:  # Only include if meaningful
                sections.append(header + trimmed)
                selected.append(c)
                current_tokens += header_tokens + trimmed_tokens + 2
            
            break  # Stop after partial chunk
        else:
            # No more room
            break
    
    ctx = "\n\n".join(sections)
    return ctx, selected

def _build_context_char_based(chunks: List[Dict[str, Any]]) -> Tuple[str, List[Dict[str, Any]]]:
    """
    Fallback character-based context builder (used if tiktoken unavailable).
    """
    selected = _dedupe_and_limit(chunks, max_items=10)
    
    sections = []
    for i, c in enumerate(selected, 1):
        text = c["text"]
        if len(text) > 1000:
            text = _trim_to_sentence_boundary(text, 1000)
        
        bbox_str = ""
        if c.get("bbox") and len(c.get("bbox", [])) == 4:
            bbox = c["bbox"]
            bbox_str = f" bbox=[{bbox[0]:.1f},{bbox[1]:.1f},{bbox[2]:.1f},{bbox[3]:.1f}]"
        
        header = (
            f"[{i}] doc_id={c['doc_id']} "
            f"page={c['page_number']} "
            f"source={c.get('source', 'text')} "
            f"conf={c.get('confidence')}"
            f"{bbox_str}"
        )
        sections.append(header + "\n" + text)
    
    ctx = "\n\n".join(sections)
    
    if len(ctx) > 10000:
        ctx = ctx[:10000] + "…"
    
    return ctx, selected

# ============================================================================
# PROMPT VERSIONS 
# ============================================================================
# CURRENT: V1 (Original) - Comprehensive and well-tested
# TESTED: V2 (Optimized) - Did not improve speed, actually made it worse
# ============================================================================
SYSTEM_PROMPT = """You are an assistant for construction projects.
Use ONLY the CONTEXT provided. If not found, answer exactly "Not found in the project documents."

CRITICAL: Return ONLY valid JSON. No markdown. No prose before or after the JSON. No code fences.

JSON schema:
{
  "answer": "string",
  "citations": [
    {
      "doc_id": "string",
      "page_number": 123,
      "snippet": "string",
      "bbox": [x1, y1, x2, y2]
    }
  ]
}

Rules:
- Quote numeric values with units exactly as written in context.
- Do not invent information.
- Always include 1-3 citations when answer is found.
- If no evidence in context, return: {"answer":"Not found in the project documents.","citations":[]}
- Extract bbox from the context headers. Format: [1] doc_id=xxx page=N source=xxx conf=0.9 bbox=[x1,y1,x2,y2]
- Copy the bbox array exactly as shown (4 numbers). If bbox is not present, use null.
"""

# ============================================================================
# ALTERNATIVE PROMPT (V2) - Streamlined version (TESTED: DID NOT IMPROVE SPEED)
# ============================================================================
# SYSTEM_PROMPT = """You are a construction document assistant. Answer using ONLY the provided CONTEXT.
# 
# Return valid JSON in this format:
# {
#   "answer": "your answer here",
#   "citations": [{"doc_id": "string", "page_number": 123, "snippet": "quote", "bbox": [x1,y1,x2,y3]}]
# }
# 
# Quick rules:
# - Found answer? Include 1-3 citations with bbox from context headers [N] doc_id=X page=Y bbox=[...]
# - No answer? Return: {"answer":"Not found in the project documents.","citations":[]}
# - Quote exact numbers and units from context
# - Return only JSON, no markdown or explanations
# """

def build_messages(question: str, context_text: str) -> List[Dict[str, str]]:
    """
    Build chat messages for LLM call.
    """
    user_message = f"""QUESTION: {question}

CONTEXT:
{context_text}
"""
    
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
    ]

def to_citations(selected: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Fallback citations if model output can't be parsed; take top 1-3.
    """
    cites = []
    for c in selected[:3]:
        snippet = c["text"][:200]
        if len(c["text"]) > 200:
            snippet += "…"
        
        cites.append({
            "doc_id": c["doc_id"],
            "page_number": c["page_number"],
            "snippet": snippet,
            "bbox": c.get("bbox")
        })
    
    return cites

