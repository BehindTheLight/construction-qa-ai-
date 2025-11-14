from typing import Any, Dict, List
from .opensearch_client import get_os_client, INDEX_NAME

def build_filters(filters: Dict[str, Any] | None) -> List[Dict[str, Any]]:
    """
    Build OpenSearch filter clauses from a dictionary of filters.
    Supports single values (term) and lists (terms).
    
    For text fields with keyword subfields (project_id, doc_type, discipline),
    uses the .keyword subfield for exact matching.
    """
    # Fields that are text with keyword subfields (need .keyword for exact match)
    KEYWORD_FIELDS = {"project_id", "doc_type", "discipline", "section", "source"}
    
    filter_clauses = []
    if not filters:
        return filter_clauses
    for k, v in filters.items():
        if v is None:
            continue
        
        # Use .keyword subfield for text fields to ensure exact matching
        field_name = f"{k}.keyword" if k in KEYWORD_FIELDS else k
        
        if isinstance(v, list):
            filter_clauses.append({"terms": {field_name: v}})
        else:
            filter_clauses.append({"term": {field_name: v}})
    return filter_clauses

def run_bm25_search(query: str, size: int, filters: Dict[str, Any] | None = None, toc_boost_clauses: List[Dict] | None = None):
    """Run BM25 text search with optional TOC-based boosting."""
    client = get_os_client()
    filter_clauses = build_filters(filters)
    
    bool_query = {
        "filter": filter_clauses,
        "must": {
            "multi_match": {
                "query": query,
                "fields": ["text^3", "section"],
                "type": "best_fields",
                "operator": "or"
            }
        }
    }
    
    # Add TOC-based boosting if available
    if toc_boost_clauses:
        bool_query["should"] = toc_boost_clauses
        # Note: We don't set minimum_should_match, so these are pure boosts
    
    body = {
        "size": size,
        "query": {"bool": bool_query}
    }
    res = client.search(index=INDEX_NAME, body=body)
    return res["hits"]["hits"]

def run_vector_search(query_vector: List[float], size: int, num_candidates: int, filters: Dict[str, Any] | None = None):
    """
    Run k-NN vector search using OpenSearch's knn query with pre-filtering.
    
    For OpenSearch 2.12.0, we use the knn query directly with a filter parameter.
    This keeps vector computation on the server (uses HNSW index).
    """
    client = get_os_client()
    filter_clauses = build_filters(filters)
    
    # Build the k-NN query body
    # In OpenSearch 2.x with k-NN plugin, use the knn query type
    # Note: num_candidates is NOT supported in 2.12.0 (causes JSON parse error)
    body = {
        "size": size,
        "query": {
            "knn": {
                "vector": {
                    "vector": query_vector,
                    "k": size
                    # num_candidates not supported in OpenSearch 2.12.0
                }
            }
        }
    }
    
    # Add filters if present (applied as post-filter to avoid breaking k-NN)
    if filter_clauses:
        body["post_filter"] = {
            "bool": {"must": filter_clauses}
        }
    
    try:
        res = client.search(index=INDEX_NAME, body=body)
        return res["hits"]["hits"]
    except Exception as e:
        # Fallback: if k-NN query fails, fetch filtered docs and compute in Python
        # This ensures reliability even if k-NN plugin isn't configured
        print(f"Warning: k-NN query failed ({e}), falling back to Python cosine")
        import numpy as np
        
        # Fetch filtered documents
        fetch_body = {
            "size": min(size * 5, 500),  # Over-fetch but cap at 500
            "query": {
                "bool": {
                    "filter": filter_clauses,
                    "must": {"match_all": {}}
                }
            },
            "_source": ["chunk_id", "doc_id", "project_id", "page_number", "section", 
                       "text", "bbox", "source", "confidence", "doc_type", "discipline", "vector"]
        }
        res = client.search(index=INDEX_NAME, body=fetch_body)
        hits = res["hits"]["hits"]
        
        # Score by cosine similarity
        qvec = np.array(query_vector)
        for hit in hits:
            vec = hit["_source"].get("vector")
            if vec:
                vec = np.array(vec)
                similarity = np.dot(qvec, vec) / (np.linalg.norm(qvec) * np.linalg.norm(vec))
                hit["_score"] = float(similarity)
            else:
                hit["_score"] = 0.0
        
        # Sort and return top-k
        hits.sort(key=lambda x: x["_score"], reverse=True)
        return hits[:size]

def run_hybrid_search(
    query: str, 
    query_vector: List[float], 
    size: int = 64, 
    num_candidates: int = 200, 
    filters: Dict[str, Any] | None = None,
    toc_boost_clauses: List[Dict] | None = None
):
    """
    Execute hybrid search by running BM25 and k-NN searches in parallel, then merging.
    
    Uses:
    - BM25 via standard _search endpoint (with optional TOC boosting)
    - k-NN via _knn_search endpoint (server-side HNSW, fast and scalable)
    - Parallel execution with asyncio for lower latency
    - Merge and deduplicate results
    
    Args:
        query: Natural language query string
        query_vector: Embedding vector for the query (3072-d)
        size: Number of results to return (per search, before merge)
        num_candidates: Number of candidates for k-NN HNSW (2-4x size recommended)
        filters: Dictionary of filters (project_id, doc_type, etc.)
        toc_boost_clauses: Optional TOC-based boost clauses for BM25
    
    Returns:
        List of OpenSearch hits (merged from BM25 and k-NN, ready for reranking)
    """
    import asyncio
    import concurrent.futures
    
    # Run both searches in parallel using ThreadPoolExecutor
    # (opensearch-py is sync, so we use threads not async)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        bm25_future = executor.submit(run_bm25_search, query, size, filters, toc_boost_clauses)
        knn_future = executor.submit(run_vector_search, query_vector, size, num_candidates, filters)
        
        bm25_hits = bm25_future.result()
        knn_hits = knn_future.result()
    
    # Merge and deduplicate by chunk_id (union of both result sets)
    seen = {}
    for hit in bm25_hits + knn_hits:
        chunk_id = hit["_source"]["chunk_id"]
        if chunk_id not in seen:
            seen[chunk_id] = hit
        else:
            # Keep the higher score (though scores aren't directly comparable)
            # Doesn't matter much since Cohere reranks anyway
            if hit.get("_score", 0) > seen[chunk_id].get("_score", 0):
                seen[chunk_id] = hit
    
    # Return merged results (Cohere will rerank and truncate to final size)
    merged = list(seen.values())
    merged.sort(key=lambda x: x.get("_score", 0), reverse=True)
    return merged

