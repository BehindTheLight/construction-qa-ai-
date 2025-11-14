"""
Visual Content Indexer

Embeds and indexes Vision LLM extracted content into OpenSearch
for hybrid search (BM25 + k-NN).
"""

import logging
from typing import List, Dict, Any
import psycopg

from core.settings import settings
from llm.embeddings import EmbedderNaga
from search.opensearch_client import INDEX_NAME

logger = logging.getLogger(__name__)


def embed_visual_content(conn, doc_id: str) -> Dict[str, int]:
    """
    Embed all visual content for a document.
    
    Args:
        conn: PostgreSQL connection
        doc_id: Document ID
        
    Returns:
        Dict with stats (entries_embedded, entries_skipped)
    """
    embedder = EmbedderNaga()
    
    # Get all visual content without embeddings
    with conn.cursor() as cur:
        cur.execute("""
            SELECT content_id, extracted_text
            FROM visual_content
            WHERE doc_id = %s
              AND (vector IS NULL OR array_length(vector, 1) IS NULL)
              AND extracted_text IS NOT NULL
              AND extracted_text != ''
        """, (doc_id,))
        
        rows = cur.fetchall()
    
    if not rows:
        logger.info(f"[Visual Indexer] No visual content to embed for {doc_id}")
        return {"entries_embedded": 0, "entries_skipped": 0}
    
    logger.info(f"[Visual Indexer] Embedding {len(rows)} visual content entries...")
    
    # Prepare texts for batch embedding
    content_ids = []
    texts = []
    
    for content_id, extracted_text in rows:
        content_ids.append(content_id)
        # Limit text length for embedding (max ~8k tokens = ~32k chars)
        texts.append(extracted_text[:30000])
    
    # Batch embed
    try:
        vectors = embedder.embed_batch(texts)
        logger.info(f"[Visual Indexer] Generated {len(vectors)} embeddings")
    except Exception as e:
        logger.error(f"[Visual Indexer] Embedding failed: {e}")
        return {"entries_embedded": 0, "entries_skipped": len(rows)}
    
    # Update database with vectors
    embedded_count = 0
    with conn.cursor() as cur:
        for content_id, vector in zip(content_ids, vectors):
            try:
                cur.execute("""
                    UPDATE visual_content
                    SET vector = %s
                    WHERE content_id = %s
                """, (vector, content_id))
                embedded_count += 1
            except Exception as e:
                logger.error(f"[Visual Indexer] Failed to update {content_id}: {e}")
    
    conn.commit()
    
    logger.info(f"[Visual Indexer] ✓ Embedded {embedded_count}/{len(rows)} entries")
    
    return {
        "entries_embedded": embedded_count,
        "entries_skipped": len(rows) - embedded_count
    }


def index_visual_content_to_opensearch(conn, os_client, doc_id: str, project_id: str) -> Dict[str, int]:
    """
    Index visual content to OpenSearch for hybrid search.
    
    Args:
        conn: PostgreSQL connection
        os_client: OpenSearch client
        doc_id: Document ID
        project_id: Project ID for filtering
        
    Returns:
        Dict with stats (entries_indexed, entries_failed)
    """
    # Get all visual content with embeddings
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 
                vc.content_id,
                vc.doc_id,
                vc.page_number,
                vc.content_type,
                vc.extracted_text,
                vc.vector,
                vc.source,
                vc.confidence,
                d.doc_type,
                d.discipline
            FROM visual_content vc
            JOIN documents d ON vc.doc_id = d.doc_id
            WHERE vc.doc_id = %s
              AND vc.vector IS NOT NULL
              AND array_length(vc.vector, 1) IS NOT NULL
        """, (doc_id,))
        
        rows = cur.fetchall()
    
    if not rows:
        logger.info(f"[Visual Indexer] No visual content with embeddings to index for {doc_id}")
        return {"entries_indexed": 0, "entries_failed": 0}
    
    logger.info(f"[Visual Indexer] Indexing {len(rows)} visual content entries to OpenSearch...")
    
    # Prepare bulk index operations
    actions = []
    indexed_count = 0
    failed_count = 0
    
    for row in rows:
        (content_id, doc_id, page_number, content_type, extracted_text, 
         vector, source, confidence, doc_type, discipline) = row
        
        # Create OpenSearch document
        doc = {
            "chunk_id": content_id,  # Use content_id as chunk_id
            "doc_id": doc_id,
            "project_id": project_id,
            "page_number": page_number,
            "section": content_type,  # Use content_type as section
            "text": extracted_text,
            "vector": vector,
            "source": source or "vision_llm",
            "confidence": confidence or 0.95,
            "doc_type": doc_type,
            "discipline": discipline,
            "bbox": [0, 0, 0, 0]  # Visual content covers whole page (no specific bbox)
        }
        
        actions.append({"index": {"_index": INDEX_NAME, "_id": content_id}})
        actions.append(doc)
    
    # Bulk index to OpenSearch
    if actions:
        try:
            from opensearchpy import helpers
            
            # Convert to proper bulk format
            bulk_actions = []
            for i in range(0, len(actions), 2):
                action = actions[i]
                doc = actions[i + 1]
                bulk_actions.append({
                    "_index": INDEX_NAME,
                    "_id": action["index"]["_id"],
                    "_source": doc
                })
            
            success, failed = helpers.bulk(
                os_client,
                bulk_actions,
                refresh=True,
                raise_on_error=False
            )
            
            indexed_count = success
            failed_count = len(bulk_actions) - success
            
            logger.info(f"[Visual Indexer] ✓ Indexed {indexed_count}/{len(bulk_actions)} entries to OpenSearch")
            
            if failed_count > 0:
                logger.warning(f"[Visual Indexer] Failed to index {failed_count} entries")
        
        except Exception as e:
            logger.error(f"[Visual Indexer] Bulk indexing failed: {e}")
            failed_count = len(actions) // 2
    
    return {
        "entries_indexed": indexed_count,
        "entries_failed": failed_count
    }


def process_visual_content_for_search(conn, os_client, doc_id: str, project_id: str) -> Dict[str, Any]:
    """
    Complete pipeline: Embed + Index visual content for search.
    
    Args:
        conn: PostgreSQL connection
        os_client: OpenSearch client
        doc_id: Document ID
        project_id: Project ID
        
    Returns:
        Dict with combined stats
    """
    logger.info(f"[Visual Indexer] Processing visual content for search: {doc_id}")
    
    # Step 1: Embed
    embed_stats = embed_visual_content(conn, doc_id)
    
    # Step 2: Index to OpenSearch
    index_stats = index_visual_content_to_opensearch(conn, os_client, doc_id, project_id)
    
    total_stats = {
        **embed_stats,
        **index_stats,
        "success": embed_stats["entries_embedded"] > 0 or index_stats["entries_indexed"] > 0
    }
    
    logger.info(f"[Visual Indexer] ✓ Complete. Embedded: {embed_stats['entries_embedded']}, Indexed: {index_stats['entries_indexed']}")
    
    return total_stats

