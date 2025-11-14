from typing import List, Dict, Any
from core.settings import settings

def cohere_rerank(query: str, docs: List[Dict[str, Any]]) -> List[int]:
    """
    Rerank search results using Cohere's rerank-english-v3.0 model.
    
    Args:
        query: The search query
        docs: List of OpenSearch hits (with _source.text) or pre-converted chunks (with text)
    
    Returns:
        List of indices in descending order of relevance
    """
    import requests
    
    if not settings.COHERE_API_KEY:
        # Fallback: return original order
        return list(range(len(docs)))
    
    # Extract text from docs (handle both formats)
    texts = []
    for d in docs:
        if "_source" in d:  # Regular OpenSearch hit
            texts.append(d["_source"]["text"])
        elif "text" in d:  # Pre-converted chunk (e.g., from tables)
            texts.append(d["text"])
        else:
            texts.append("")  # Fallback for unexpected format
    
    payload = {
        "model": "rerank-english-v3.0",
        "query": query,
        "documents": texts,
        "top_n": len(docs)  # Return all, sorted by relevance
    }
    headers = {
        "Authorization": f"Bearer {settings.COHERE_API_KEY}", 
        "Content-Type": "application/json"
    }
    
    r = requests.post(
        "https://api.cohere.ai/v1/rerank", 
        json=payload, 
        headers=headers, 
        timeout=60
    )
    r.raise_for_status()
    data = r.json()
    
    # Cohere returns results sorted by relevance_score (descending)
    # Extract the original indices
    order = [item["index"] for item in data["results"]]
    
    # Ensure we return a complete permutation (safety check)
    seen = set(order)
    order.extend([i for i in range(len(docs)) if i not in seen])
    
    return order

def rerank(query: str, docs: List[Dict[str, Any]]) -> List[int]:
    """
    Rerank search results based on configured provider.
    
    Currently supports:
    - cohere: Cohere rerank-english-v3.0
    - (future: local BGE reranker)
    
    Returns indices in descending order of relevance.
    Falls back to original order on error.
    """
    if settings.RERANK_PROVIDER == "cohere":
        try:
            return cohere_rerank(query, docs)
        except Exception as e:
            print(f"Reranking failed: {e}, using original order")
            return list(range(len(docs)))
    
    # Future: add local BGE here
    # elif settings.RERANK_PROVIDER == "local":
    #     return local_bge_rerank(query, docs)
    
    # Default: no reranking
    return list(range(len(docs)))

