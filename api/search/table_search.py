"""
Hybrid search for table rows extracted by Unstructured.

Implements BM25 + k-NN search specifically for structured table data,
with label boosting for exact construction code matches.
"""

from typing import List, Dict, Any, Optional
from opensearchpy import OpenSearch
from concurrent.futures import ThreadPoolExecutor

from search.opensearch_client import get_os_client
from core.settings import settings
from ingest.table_indexer import extract_labels_from_text


def run_table_hybrid_search(
    query: str,
    query_vector: List[float],
    project_id: str,
    doc_id: Optional[str] = None,
    doc_type: Optional[str] = None,
    discipline: Optional[str] = None,
    size: int = 10
) -> List[Dict[str, Any]]:
    """
    Run hybrid search (BM25 + k-NN) on table rows index.
    
    Args:
        query: Search query text
        query_vector: Embedding vector for semantic search
        project_id: Project ID filter
        doc_id: Optional document ID filter
        doc_type: Optional document type filter
        discipline: Optional discipline filter
        size: Number of results to return
        
    Returns:
        List of table row dicts with scores
    """
    client = get_os_client()
    
    # Extract labels for exact matching boost
    labels = extract_labels_from_text(query)
    
    # Build filters
    filter_clauses = [{"term": {"project_id": project_id}}]
    if doc_id:
        filter_clauses.append({"term": {"doc_id": doc_id}})
    if doc_type:
        filter_clauses.append({"term": {"doc_type": doc_type}})
    if discipline:
        filter_clauses.append({"term": {"discipline": discipline}})
    
    # Run BM25 and k-NN in parallel
    with ThreadPoolExecutor(max_workers=2) as executor:
        bm25_future = executor.submit(_run_table_bm25, client, query, labels, filter_clauses, size)
        knn_future = executor.submit(_run_table_knn, client, query_vector, filter_clauses, size)
        
        bm25_hits = bm25_future.result()
        knn_hits = knn_future.result()
    
    # Merge results (simple union by row_id with max score)
    merged = _merge_table_results(bm25_hits, knn_hits, size)
    
    return merged


def _run_table_bm25(
    client: OpenSearch,
    query: str,
    labels: List[str],
    filter_clauses: List[Dict],
    size: int
) -> List[Dict[str, Any]]:
    """Run BM25 search on table rows"""
    
    # Build query with label boosting
    should_clauses = [
        {
            "multi_match": {
                "query": query,
                "fields": ["table_text^3", "table_label^2", "columns_text"],
                "type": "best_fields"
            }
        }
    ]
    
    # Add label exact match boost (high boost for W2a, R-10, etc.)
    if labels:
        should_clauses.append({
            "constant_score": {
                "filter": {"terms": {"labels": labels}},
                "boost": 10.0  # Very high boost for exact label match
            }
        })
    
    body = {
        "size": size,
        "query": {
            "bool": {
                "must": should_clauses,
                "filter": filter_clauses
            }
        }
    }
    
    try:
        resp = client.search(index=settings.OPENSEARCH_TABLE_INDEX, body=body)
        hits = []
        for hit in resp["hits"]["hits"]:
            row = hit["_source"]
            row["score"] = hit["_score"]
            row["match_type"] = "bm25"
            hits.append(row)
        return hits
    except Exception as e:
        print(f"Warning: Table BM25 search failed: {e}")
        return []


def _run_table_knn(
    client: OpenSearch,
    query_vector: List[float],
    filter_clauses: List[Dict],
    size: int
) -> List[Dict[str, Any]]:
    """Run k-NN search on table rows"""
    
    body = {
        "size": size,
        "query": {
            "bool": {
                "must": [
                    {
                        "knn": {
                            "vector": {
                                "vector": query_vector,
                                "k": size
                            }
                        }
                    }
                ],
                "filter": filter_clauses
            }
        }
    }
    
    try:
        resp = client.search(index=settings.OPENSEARCH_TABLE_INDEX, body=body)
        hits = []
        for hit in resp["hits"]["hits"]:
            row = hit["_source"]
            row["score"] = hit["_score"]
            row["match_type"] = "knn"
            hits.append(row)
        return hits
    except Exception as e:
        print(f"Warning: Table k-NN search failed: {e}")
        return []


def _merge_table_results(
    bm25_hits: List[Dict],
    knn_hits: List[Dict],
    size: int
) -> List[Dict[str, Any]]:
    """
    Merge BM25 and k-NN results, taking best score for each row.
    
    Args:
        bm25_hits: Results from BM25 search
        knn_hits: Results from k-NN search
        size: Max results to return
        
    Returns:
        Merged and sorted results
    """
    # Build dict by row_id with max score
    merged_dict = {}
    
    for hit in bm25_hits:
        row_id = hit["row_id"]
        if row_id not in merged_dict or hit["score"] > merged_dict[row_id]["score"]:
            merged_dict[row_id] = hit
    
    for hit in knn_hits:
        row_id = hit["row_id"]
        if row_id not in merged_dict or hit["score"] > merged_dict[row_id]["score"]:
            merged_dict[row_id] = hit
        elif row_id in merged_dict:
            # If both matched, note it
            merged_dict[row_id]["match_type"] = "hybrid"
    
    # Sort by score and take top N
    results = sorted(merged_dict.values(), key=lambda x: x["score"], reverse=True)[:size]
    
    return results


def convert_table_rows_to_chunks(table_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Convert table rows to chunk format for unified handling.
    
    Args:
        table_rows: List of table row dicts from search
        
    Returns:
        List of chunks with table data
    """
    chunks = []
    for row in table_rows:
        chunk = {
            "chunk_id": row["row_id"],
            "doc_id": row["doc_id"],
            "project_id": row["project_id"],
            "page_number": row["page_number"],
            "section": row.get("table_label"),
            "text": row["table_text"],
            "bbox": row.get("bbox"),
            "source": "table",
            "confidence": 1.0,  # Tables are high confidence
            "score": row["score"]
        }
        chunks.append(chunk)
    
    return chunks


