"""
TOC-based Query Router - Boost search results using table of contents

Given a query, determines if it matches TOC entries and returns page ranges to boost.
"""

import psycopg
import os
from typing import List, Tuple, Optional
from core.settings import settings


def guess_toc_ranges(
    project_id: str,
    query: str,
    doc_id: Optional[str] = None
) -> List[Tuple[str, int, int]]:
    """
    Find TOC page ranges that match the query intent.
    
    Args:
        project_id: Project to search within
        query: User's search query
        doc_id: Optional specific document ID to limit search
        
    Returns:
        List of tuples: [(doc_id, page_start, page_end), ...]
    """
    # Check if query contains keywords that suggest section-specific search
    ql = query.lower()
    
    # Define trigger keywords for different document sections
    triggers = [
        ("architectural", ["architectural", "drawing", "floor plan", "plan", "architecture"]),
        ("site", ["site plan", "site", "lot plan"]),
        ("civil", ["civil", "grading", "lot grading"]),
        ("mechanical", ["mechanical", "hvac", "ventilation", "heating", "cooling"]),
        ("electrical", ["electrical", "electric", "power", "wiring"]),
        ("plumbing", ["plumbing", "plumb", "piping", "water"]),
        ("spec", ["spec", "specification", "sb-12", "support doc", "supporting"]),
        ("permit", ["permit", "application"]),
        ("inspection", ["inspection", "inspect"]),
        ("structural", ["structural", "structure", "framing", "foundation"]),
    ]
    
    # Check if any trigger words match the query
    hit = any(any(w in ql for w in words) for _, words in triggers)
    if not hit:
        print(f"[TOC-Router] No trigger words matched for query: '{query}'")
        return []
    
    print(f"[TOC-Router] Query: '{query}' matched triggers, searching TOC...")
    
    # Query database for matching TOC entries
    where = "WHERE d.project_id=%s"
    params = [project_id]
    
    if doc_id:
        where += " AND te.doc_id=%s"
        params.append(doc_id)
    
    sql = f"""
        SELECT te.doc_id, te.page_start, te.page_end, te.title
        FROM toc_entries te
        JOIN documents d ON d.doc_id = te.doc_id
        {where}
    """
    
    out = []
    try:
        with psycopg.connect(settings.POSTGRES_DSN) as conn:
            with conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()
                
                # Filter TOC entries by relevance to query
                for row in rows:
                    doc_id_result, page_start, page_end, title = row
                    title_lower = title.lower()
                    
                    # Check if any trigger words appear in the TOC title
                    matches = False
                    for _, words in triggers:
                        if any(w in ql and w in title_lower for w in words):
                            matches = True
                            break
                    
                    if matches:
                        out.append((doc_id_result, page_start, page_end))
    except Exception as e:
        print(f"Warning: TOC routing failed: {e}")
        return []
    
    if out:
        print(f"[TOC-Router] Found {len(out)} TOC page range(s) to boost")
    else:
        print(f"[TOC-Router] No TOC matches found in database")
    
    return out


def build_toc_boost_clauses(toc_ranges: List[Tuple[str, int, int]]) -> List[dict]:
    """
    Build OpenSearch boost clauses for TOC page ranges.
    
    Args:
        toc_ranges: List of (doc_id, page_start, page_end) tuples
        
    Returns:
        List of OpenSearch query clauses for boosting
    """
    if not toc_ranges:
        return []
    
    boost_clauses = []
    for doc_id, page_start, page_end in toc_ranges:
        boost_clauses.append({
            "constant_score": {
                "filter": {
                    "bool": {
                        "must": [
                            {"term": {"doc_id": doc_id}},
                            {"range": {"page_number": {"gte": page_start, "lte": page_end}}}
                        ]
                    }
                },
                "boost": 3.5
            }
        })
    
    return boost_clauses

