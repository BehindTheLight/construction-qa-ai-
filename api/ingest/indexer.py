import uuid
from typing import List, Dict, Any
from opensearchpy import helpers
from opensearchpy import OpenSearch
import psycopg
from psycopg.types.json import Json
from llm.embeddings import EmbedderNaga, EMBED_DIM
from search.opensearch_client import get_os_client, INDEX_NAME

def upsert_doc_and_pages(conn, doc_id: str, project_id: str, title: str, doc_type: str, discipline: str, source_path: str, checksum: str, pages_meta: List[Dict[str, Any]]):
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO documents (doc_id, project_id, title, doc_type, discipline, source_path, checksum)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (doc_id) DO UPDATE
            SET project_id=EXCLUDED.project_id, title=EXCLUDED.title, doc_type=EXCLUDED.doc_type,
                discipline=EXCLUDED.discipline, source_path=EXCLUDED.source_path, checksum=EXCLUDED.checksum
        """, (doc_id, project_id, title, doc_type, discipline, source_path, checksum))
        for p in pages_meta:
            page_id = f"{doc_id}:{p['page_number']}"
            cur.execute("""
                INSERT INTO pages (page_id, doc_id, page_number, width, height, is_scanned, ocr_conf)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (page_id) DO UPDATE
                SET width=EXCLUDED.width, height=EXCLUDED.height, is_scanned=EXCLUDED.is_scanned, ocr_conf=EXCLUDED.ocr_conf
            """, (page_id, doc_id, p["page_number"], p["width"], p["height"], p["is_scanned"], p["ocr_conf"]))
    conn.commit()

def embed_chunks(chunks: List[Dict[str, Any]], batch_size: int = 32):
    from core.settings import settings
    from llm.embeddings import EmbedderGemini
    
    # Use appropriate embedder based on settings
    if settings.EMBEDDINGS_PROVIDER == "gemini":
        emb = EmbedderGemini()
    else:
        emb = EmbedderNaga()
    
    vectors = []
    texts = [c["text"] for c in chunks]
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i+batch_size]
        vectors.extend(emb.embed_batch(batch))
    assert all(len(v) == EMBED_DIM for v in vectors), "Embedding dimension mismatch"
    return vectors

def bulk_index_chunks(conn, os_client: OpenSearch, chunks: List[Dict[str, Any]], vectors: List[List[float]]):
    actions = []
    for c, v in zip(chunks, vectors):
        # upsert chunk row
        with conn.cursor() as cur:
            # Use psycopg Json adapter for JSONB column
            bbox_json = Json(c["bbox"]) if c["bbox"] else None
            cur.execute("""
                INSERT INTO chunks (chunk_id, doc_id, project_id, page_number, section, text, bbox, token_count, doc_type, discipline, source, confidence)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT (chunk_id) DO NOTHING
            """, (c["chunk_id"], c["doc_id"], c["project_id"], c["page_number"], c["section"],
                  c["text"], bbox_json, None, c["doc_type"], c["discipline"], c.get("source"), c.get("confidence")))
        # os action
        body = {
            **{k: c[k] for k in ["chunk_id","doc_id","project_id","doc_type","discipline","page_number","section","text"]},
            "vector": v,
            "bbox": c["bbox"],
            "source": c.get("source"),
            "confidence": c.get("confidence"),
        }
        actions.append({"_index": INDEX_NAME, "_id": c["chunk_id"], "_source": body})
    conn.commit()
    helpers.bulk(os_client, actions, refresh=True)


def delete_document_chunks(doc_id: str):
    """
    Delete all chunks for a document from both PostgreSQL and OpenSearch.
    
    Args:
        doc_id: Document ID to delete chunks for
    """
    os_client = get_os_client()
    
    # Delete from OpenSearch using delete_by_query
    query = {
        "query": {
            "term": {"doc_id": doc_id}
        }
    }
    
    try:
        result = os_client.delete_by_query(index=INDEX_NAME, body=query, refresh=True)
        deleted_count = result.get("deleted", 0)
        print(f"  Deleted {deleted_count} chunks from OpenSearch for doc_id={doc_id}")
    except Exception as e:
        print(f"  Warning: Failed to delete from OpenSearch: {e}")
    
    # PostgreSQL deletion happens via CASCADE when document is deleted
    # So we don't need to explicitly delete chunks here

