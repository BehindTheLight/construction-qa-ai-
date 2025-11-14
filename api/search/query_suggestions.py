"""
Smart Query Suggestions Module

When a query returns "Not found", automatically:
1. Generate alternative phrasings using LLM
2. Test each alternative
3. Return suggestions that have results
"""

import logging
from typing import List, Dict, Any, Optional
from llm.chat import NagaChat

logger = logging.getLogger(__name__)

QUERY_REPHRASE_PROMPT = """You are a construction document search assistant.
A user's query returned no results. Generate 2-3 alternative ways to ask the same question that might find results.

Focus on:
- Using synonyms (e.g., "drawings" instead of "diagrams", "plans" instead of "blueprints")
- Simplifying complex queries
- Using common construction terminology
- Being more specific or more general as appropriate

Return ONLY a JSON object with "suggestions" array. Each suggestion should be a complete, natural question.

Examples:

User Query: "Show me the architectural diagrams"
Output:
{{"suggestions": ["Show me the architectural drawings", "Where are the architectural plans?", "What pages have the building drawings?"]}}

User Query: "What is the window to wall ratio?"
Output:
{{"suggestions": ["What is the ratio of windows to wall area?", "What percentage is windows and glass?", "What is the W, S & G percentage?"]}}

User Query: "Tell me about the foundation specifications"
Output:
{{"suggestions": ["What are the foundation requirements?", "What is specified for the foundation?", "Show me foundation details"]}}

Now generate suggestions for this query:
User Query: "{query}"
Output:"""


def generate_query_suggestions(original_query: str, max_suggestions: int = 3) -> List[str]:
    """
    Generate alternative phrasings of a query using LLM.
    
    Args:
        original_query: The original user query that returned no results
        max_suggestions: Maximum number of suggestions to generate (default 3)
        
    Returns:
        List of suggested alternative queries
    """
    try:
        prompt = QUERY_REPHRASE_PROMPT.format(query=original_query)
        
        chat = NagaChat(model="gpt-4o-mini")
        response = chat.chat(
            messages=[{"role": "user", "content": prompt}],
            temperature=0.5,  # Slightly higher for creative alternatives
            max_tokens=200
        )
        
        # Parse JSON response
        import json
        data = json.loads(response)
        suggestions = data.get("suggestions", [])
        
        print(f"[Smart Suggestions] Generated {len(suggestions)} alternatives for: '{original_query}'")
        for i, suggestion in enumerate(suggestions[:max_suggestions], 1):
            print(f"[Smart Suggestions]   {i}. {suggestion}")
        
        return suggestions[:max_suggestions]
        
    except Exception as e:
        logger.warning(f"[Smart Suggestions] Failed to generate suggestions: {e}")
        return []


def test_query_suggestion(
    suggestion: str,
    qa_function,
    filters: Dict[str, Any]
) -> Optional[Dict[str, Any]]:
    """
    Test if a suggested query returns results.
    
    Args:
        suggestion: The suggested query to test
        qa_function: The QA function to call (answer_question)
        filters: Filters to pass to the QA function
        
    Returns:
        QA result if successful (has citations), None if no results
    """
    try:
        result = qa_function(suggestion, filters, size=64)
        
        # Check if result has citations (meaning it found something)
        if result.get("citations") and len(result["citations"]) > 0:
            print(f"[Smart Suggestions] ✓ '{suggestion}' found {len(result['citations'])} results")
            return result
        else:
            print(f"[Smart Suggestions] ✗ '{suggestion}' found no results (answer: {result.get('answer', '')[:50]}...)")
            return None
            
    except Exception as e:
        logger.warning(f"[Smart Suggestions] Error testing '{suggestion}': {e}")
        return None


def find_working_suggestions(
    original_query: str,
    qa_function,
    filters: Dict[str, Any],
    max_to_test: int = 3
) -> List[Dict[str, Any]]:
    """
    Generate and test query suggestions SEQUENTIALLY, returning only those that work.
    
    Args:
        original_query: The original query that returned no results
        qa_function: The QA function to call for testing
        filters: Filters to pass to the QA function
        max_to_test: Maximum number of suggestions to test
        
    Returns:
        List of working suggestions with their queries and preview results
        Format: [{"query": "...", "preview": "..."}, ...]
    """
    # Generate suggestions
    suggestions = generate_query_suggestions(original_query, max_suggestions=max_to_test)
    
    if not suggestions:
        return []
    
    # Test each suggestion SEQUENTIALLY (parallel testing caused issues with settings changes)
    working_suggestions = []
    for suggestion in suggestions:
        result = test_query_suggestion(suggestion, qa_function, filters)
        
        if result:
            # Extract a preview of the answer
            answer_preview = result.get("answer", "")[:150]
            if len(result.get("answer", "")) > 150:
                answer_preview += "..."
            
            working_suggestions.append({
                "query": suggestion,
                "preview": answer_preview,
                "citation_count": len(result.get("citations", [])),
                "cached_answer": result.get("answer"),
                "cached_citations": result.get("citations", [])
            })
    
    print(f"[Smart Suggestions] Found {len(working_suggestions)} working alternatives out of {len(suggestions)} tested (SEQUENTIAL)")
    
    return working_suggestions

