"""
Table row indexing for Unstructured-extracted tables.

Handles:
1. Storing table rows in PostgreSQL
2. Indexing table rows in OpenSearch with embeddings
3. Label extraction from table cells
"""

import uuid
import json
import re
from typing import List, Dict, Any
from opensearchpy import OpenSearch, helpers
from psycopg.types.json import Json

from core.settings import settings
from llm.embeddings import EmbedderNaga


def extract_labels_from_text(text: str) -> List[str]:
    """
    Extract construction labels from text.
    
    Patterns:
    - Wall types: W2a, W1, W-3
    - Assembly codes: A-2, A1
    - R-values: R-10, R20
    - STC ratings: STC 36, STC50
    - Fire ratings: 1h, 2h, 45min
    
    Args:
        text: Text to extract labels from
        
    Returns:
        List of unique labels (uppercase)
    """
    if not text:
        return []
    
    labels = set()
    text_upper = text.upper()
    
    # Pattern 1: Wall/Assembly codes (W2a, A-2, etc.)
    pattern1 = r'\b[A-Z]\d+[A-Z]?\b'
    labels.update(re.findall(pattern1, text_upper))
    
    # Pattern 2: Hyphenated codes (R-10, A-3, etc.)
    pattern2 = r'\b[A-Z]-\d+\b'
    labels.update(re.findall(pattern2, text_upper))
    
    # Pattern 3: STC ratings
    pattern3 = r'\bSTC\s*\d+\b'
    labels.update(re.findall(pattern3, text_upper))
    
    # Pattern 4: Fire ratings (1H, 2H, 45MIN, etc.)
    pattern4 = r'\b\d+H\b|\b\d+MIN\b'
    labels.update(re.findall(pattern4, text_upper))
    
    return sorted(list(labels))


def flatten_columns_to_text(columns: Dict[str, str]) -> str:
    """
    Convert columns dict to searchable text.
    
    Args:
        columns: Dictionary of column_name -> value
        
    Returns:
        Concatenated text suitable for search
    """
    parts = []
    for key, value in columns.items():
        # Include both key and value for better search
        if key and key != "raw_text":
            parts.append(f"{key}: {value}")
        else:
            parts.append(str(value))
    
    return " | ".join(parts)


def index_table_rows(
    conn,
    os_client: OpenSearch,
    doc_id: str,
    project_id: str,
    doc_type: str,
    discipline: str,
    page_number: int,
    table_rows: List[Dict[str, Any]],
    table_label: str = None
):
    """
    Index table rows into both PostgreSQL and OpenSearch.
    
    Args:
        conn: PostgreSQL connection
        os_client: OpenSearch client
        doc_id: Document ID
        project_id: Project ID
        doc_type: Document type
        discipline: Discipline
        page_number: Page number
        table_rows: List of dicts with 'columns' and optional 'bbox'
        table_label: Optional table caption/title
    """
    if not table_rows:
        return
    
    # Initialize embedder
    emb = EmbedderNaga()
    
    # Prepare rows for indexing
    pg_rows = []
    os_actions = []
    texts_to_embed = []
    
    for row in table_rows:
        row_id = "ur_" + uuid.uuid4().hex[:12]
        columns = row.get("columns", {})
        bbox = row.get("bbox")
        
        # Flatten columns to searchable text
        table_text = flatten_columns_to_text(columns)
        
        # Extract labels from all column values
        all_text = " ".join(str(v) for v in columns.values())
        labels = extract_labels_from_text(all_text)
        
        # Prepare for PostgreSQL
        pg_rows.append((
            row_id,
            doc_id,
            page_number,
            table_label,
            columns,
            bbox
        ))
        
        # Prepare for OpenSearch (will add vector after embedding)
        os_actions.append({
            "row_id": row_id,
            "doc_id": doc_id,
            "page_number": page_number,
            "project_id": project_id,
            "doc_type": doc_type,
            "discipline": discipline,
            "table_label": table_label,
            "table_text": table_text,
            "columns_text": json.dumps(columns),  # For exact matching
            "labels": labels,
            "bbox": bbox,
            "source": "unstructured"
        })
        
        texts_to_embed.append(table_text)
    
    # 1. Store in PostgreSQL
    with conn.cursor() as cur:
        for row_id, doc_id_val, page_num, tbl_label, cols, bbox_val in pg_rows:
            cur.execute("""
                INSERT INTO table_rows (row_id, doc_id, page_number, table_label, columns, bbox, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (row_id) DO NOTHING
            """, (
                row_id,
                doc_id_val,
                page_num,
                tbl_label,
                Json(cols),
                Json(bbox) if bbox else None,
                "unstructured"
            ))
    conn.commit()
    
    # 2. Generate embeddings
    vectors = emb.embed_batch(texts_to_embed)
    
    # 3. Index in OpenSearch
    bulk_actions = []
    for action, vector in zip(os_actions, vectors):
        action["vector"] = vector
        bulk_actions.append({
            "_index": settings.OPENSEARCH_TABLE_INDEX,
            "_id": action["row_id"],
            "_source": action
        })
    
    if bulk_actions:
        helpers.bulk(os_client, bulk_actions, refresh=True)
        print(f"  Indexed {len(bulk_actions)} table rows for page {page_number}")


def delete_table_rows_for_doc(conn, os_client: OpenSearch, doc_id: str):
    """
    Delete all table rows for a document from both PostgreSQL and OpenSearch.
    
    Args:
        conn: PostgreSQL connection
        os_client: OpenSearch client
        doc_id: Document ID
    """
    # Delete from OpenSearch
    query = {
        "query": {
            "term": {"doc_id": doc_id}
        }
    }
    
    try:
        result = os_client.delete_by_query(
            index=settings.OPENSEARCH_TABLE_INDEX,
            body=query,
            refresh=True
        )
        deleted_count = result.get("deleted", 0)
        print(f"  Deleted {deleted_count} table rows from OpenSearch for doc_id={doc_id}")
    except Exception as e:
        print(f"  Warning: Failed to delete table rows from OpenSearch: {e}")
    
    # Delete from PostgreSQL (CASCADE will handle this, but explicit is fine)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM table_rows WHERE doc_id = %s", (doc_id,))
        deleted_count = cur.rowcount
        print(f"  Deleted {deleted_count} table rows from PostgreSQL for doc_id={doc_id}")
    conn.commit()


