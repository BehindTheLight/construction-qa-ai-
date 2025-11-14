import os
import uuid
import psycopg
import json
from typing import Optional, List, Dict, Any
from datetime import datetime
from fastapi import FastAPI, Query, HTTPException, Request, BackgroundTasks, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.settings import settings
from db.init_db import init_db
from db.run_migrations import run as run_migrations
from search.create_index import create_index
from ingest.pdf_extractor import extract_pdf, file_checksum, try_extract_toc
from ingest.chunker import chunk_pages
from ingest.indexer import upsert_doc_and_pages, embed_chunks, bulk_index_chunks, delete_document_chunks
from ingest.unstructured_processor import process_document_with_unstructured
from ingest.table_indexer import delete_table_rows_for_doc
from ingest.vision_processor import process_document_with_vision
from ingest.vision_parser import delete_visual_content_for_doc
from ingest.visual_content_indexer import process_visual_content_for_search
from search.opensearch_client import get_os_client
from llm.query_embed import embed_query
from search.hybrid import run_hybrid_search
from search.reranker import rerank
from search.router import guess_toc_ranges, build_toc_boost_clauses
from qa.qa_service import answer_question, answer_question_stream

app = FastAPI(title="Insani API", version="0.1.0")

# Configure CORS to allow frontend access
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",  # Next.js dev server
        "http://127.0.0.1:3000",  # Alternative localhost
    ],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers
)

class IngestRequest(BaseModel):
    file_path: str
    project_id: str = "demo_project"
    doc_id: str | None = None
    title: str | None = None
    doc_type: str = "permit"
    discipline: str = "GENERAL"

class SearchResponseChunk(BaseModel):
    chunk_id: str
    doc_id: str
    project_id: str
    page_number: int
    section: str | None = None
    text: str
    bbox: list[float] | None = None
    source: str | None = None
    confidence: float | None = None
    score: float

class QARequest(BaseModel):
    question: str
    project_id: str
    doc_type: Optional[str] = None
    discipline: Optional[str] = None
    size: int = 64

class QACitation(BaseModel):
    doc_id: str
    page_number: int
    snippet: Optional[str] = None
    bbox: Optional[List[float]] = None

class QuerySuggestion(BaseModel):
    query: str
    preview: str
    citation_count: int
    cached_answer: Optional[str] = None
    cached_citations: Optional[List[QACitation]] = None

class QAResponse(BaseModel):
    answer: str
    citations: List[QACitation]
    suggestions: Optional[List[QuerySuggestion]] = None

class ConvoCreate(BaseModel):
    project_id: str
    title: Optional[str] = None

class MessageCreate(BaseModel):
    role: str  # 'user' | 'assistant'
    content: str
    citations: Optional[List[Dict[str, Any]]] = None

@app.get("/health")
def health():
    return {"ok": True}

@app.post("/admin/init-db")
def admin_init_db():
    init_db()
    return {"ok": True, "msg": "db initialized"}

@app.post("/admin/migrate")
def admin_migrate():
    run_migrations()
    return {"ok": True, "msg": "migrations applied"}

@app.post("/admin/init-index")
def admin_init_index():
    create_index()
    return {"ok": True, "msg": "index ensured"}

@app.get("/search", response_model=List[SearchResponseChunk])
def search(
    q: str = Query(..., min_length=2, description="Search query"),
    project_id: str = Query(..., description="Project ID to search within"),
    doc_type: Optional[str] = Query(None, description="Filter by document type"),
    discipline: Optional[str] = Query(None, description="Filter by discipline"),
    size: int = Query(10, ge=1, le=100, description="Number of results to return")
):
    """
    Hybrid search endpoint combining BM25 text search and k-NN vector search.
    Results are reranked using Cohere (or fallback to original order).
    
    Returns chunks with citations (page_number, bbox) for PDF highlighting.
    """
    # Build filters
    filters: Dict[str, Any] = {"project_id": project_id}
    if doc_type:
        filters["doc_type"] = doc_type
    if discipline:
        filters["discipline"] = discipline

    # Embed query using Naga AI (3072-d)
    qvec = embed_query(q)
    
    # TOC-aware routing: boost page ranges from table of contents if available
    toc_ranges = guess_toc_ranges(project_id, q)
    toc_boost_clauses = build_toc_boost_clauses(toc_ranges) if toc_ranges else None
    if toc_boost_clauses:
        print(f"  [TOC] Boosting {len(toc_ranges)} page range(s)")
    
    # Hybrid search: fetch top-K (64) candidates for reranking
    fetch_size = max(size * 6, 64)  # Over-fetch for better reranking
    hits = run_hybrid_search(
        q, 
        qvec, 
        size=fetch_size, 
        num_candidates=200, 
        filters=filters,
        toc_boost_clauses=toc_boost_clauses
    )

    # Rerank with Cohere
    order = rerank(q, hits)
    hits = [hits[i] for i in order[:size]]

    # Format response
    out: List[SearchResponseChunk] = []
    for h in hits:
        s = h["_source"]
        out.append(SearchResponseChunk(
            chunk_id=s["chunk_id"],
            doc_id=s["doc_id"],
            project_id=s["project_id"],
            page_number=s["page_number"],
            section=s.get("section"),
            text=s["text"],
            bbox=s.get("bbox"),
            source=s.get("source"),
            confidence=s.get("confidence"),
            score=h.get("_score", 0.0)
        ))
    return out

@app.post("/ingest/local")
def ingest_local(req: IngestRequest):
    # Verify file
    path = req.file_path
    if not os.path.exists(path):
        return {"ok": False, "error": f"file not found: {path}"}

    # IDs and meta
    doc_id = req.doc_id or f"doc_{uuid.uuid4().hex[:8]}"
    title = req.title or os.path.basename(path)
    checksum = file_checksum(path)

    # Extract pages & blocks (OCR for scanned pages will be added in Step 4)
    extracted = extract_pdf(path)
    pages = extracted["pages"]

    # Extract TOC (table of contents) from early pages
    toc_count = try_extract_toc(doc_id, pages)

    # Upsert doc + pages
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        upsert_doc_and_pages(conn, doc_id, req.project_id, title, req.doc_type, req.discipline, path, checksum, pages)

        # Chunk
        chunks = chunk_pages(doc_id, req.project_id, req.doc_type, req.discipline, pages)
        if not chunks:
            return {"ok": False, "error": "no chunks produced (likely all pages are scanned) — OCR arrives in Step 4"}

        # Embed
        vectors = embed_chunks(chunks)

        # Index
        os_client = get_os_client()
        bulk_index_chunks(conn, os_client, chunks, vectors)

    return {
        "ok": True,
        "doc_id": doc_id,
        "pages": len(pages),
        "chunks_indexed": len(chunks),
        "toc_entries": toc_count
    }

@app.delete("/documents/{doc_id}")
def delete_document(doc_id: str):
    """
    Delete a document and all its associated data:
    - Document metadata
    - All pages (CASCADE)
    - All chunks from PostgreSQL (CASCADE) and OpenSearch
    - All table rows from PostgreSQL (CASCADE) and OpenSearch
    - All visual content from PostgreSQL (CASCADE)
    - All TOC entries (CASCADE)
    - All conversations/messages referencing this doc
    """
    # Delete chunks from OpenSearch
    delete_document_chunks(doc_id)
    
    # Delete table rows and visual content from OpenSearch and PostgreSQL
    os_client = get_os_client()
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        delete_table_rows_for_doc(conn, os_client, doc_id)
        delete_visual_content_for_doc(conn, doc_id)
    
    # Then delete from PostgreSQL (CASCADE handles pages, chunks, toc_entries)
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM documents WHERE doc_id = %s", (doc_id,))
            rows_deleted = cur.rowcount
        conn.commit()
    
    if rows_deleted == 0:
        raise HTTPException(status_code=404, detail=f"Document {doc_id} not found")
    
    return {
        "ok": True,
        "doc_id": doc_id,
        "message": "Document and all associated data deleted"
    }

@app.post("/ingest/replace")
def ingest_replace(req: IngestRequest):
    """
    Replace a document: delete existing data and re-ingest.
    
    If doc_id is provided, deletes that document first.
    If doc_id is not provided, generates a new one (same as /ingest/local).
    """
    # If doc_id provided, delete existing document
    if req.doc_id:
        try:
            delete_document(req.doc_id)
            print(f"  Deleted existing document: {req.doc_id}")
        except HTTPException:
            # Document doesn't exist, that's fine
            print(f"  Document {req.doc_id} not found, proceeding with fresh ingest")
    
    # Now ingest (same logic as /ingest/local)
    path = req.file_path
    if not os.path.exists(path):
        return {"ok": False, "error": f"file not found: {path}"}

    doc_id = req.doc_id or f"doc_{uuid.uuid4().hex[:8]}"
    title = req.title or os.path.basename(path)
    checksum = file_checksum(path)

    # Extract pages & blocks
    extracted = extract_pdf(path)
    pages = extracted["pages"]

    # Extract TOC
    toc_count = try_extract_toc(doc_id, pages)

    # Upsert doc + pages
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        upsert_doc_and_pages(conn, doc_id, req.project_id, title, req.doc_type, req.discipline, path, checksum, pages)

        # Process with Vision LLM (drawings, scanned tables, diagrams)
        vision_stats = process_document_with_vision(conn, path, doc_id, pages)

        # Process with Unstructured (tables, scanned pages - if Vision didn't process them)
        unstructured_stats = process_document_with_unstructured(
            conn, path, doc_id, req.project_id, req.doc_type, req.discipline, pages
        )

        # Chunk
        chunks = chunk_pages(doc_id, req.project_id, req.doc_type, req.discipline, pages)
        if not chunks:
            return {"ok": False, "error": "no chunks produced"}

        # Embed
        vectors = embed_chunks(chunks)

        # Index chunks
        os_client = get_os_client()
        bulk_index_chunks(conn, os_client, chunks, vectors)
        
        # Embed + Index visual content (if any was extracted by Vision LLM)
        visual_index_stats = process_visual_content_for_search(conn, os_client, doc_id, req.project_id)

    return {
        "ok": True,
        "doc_id": doc_id,
        "pages": len(pages),
        "chunks_indexed": len(chunks),
        "toc_entries": toc_count,
        "visual_pages_processed": vision_stats.get("visual_pages_processed", 0),
        "visual_content_extracted": vision_stats.get("visual_content_extracted", 0),
        "visual_content_indexed": visual_index_stats.get("entries_indexed", 0),
        "replaced": req.doc_id is not None,
        "tables_extracted": unstructured_stats.get("tables_extracted", 0),
        "pages_with_tables": unstructured_stats.get("pages_processed", 0)
    }

@app.post("/qa", response_model=QAResponse)
def qa(req: QARequest):
    """
    Question-answering endpoint using RAG (Retrieval-Augmented Generation).
    
    Flow:
    1. TOC-aware routing (optional boost if TOC available)
    2. Hybrid search (BM25 + k-NN) to retrieve relevant chunks
    3. Cohere rerank to prioritize most relevant
    4. LLM (Naga AI) to generate answer with strict citations
    
    Returns answer with citations including doc_id, page_number, snippet, and bbox.
    If no relevant information found, returns "Not found in the project documents."
    """
    try:
        filters: Dict[str, Any] = {"project_id": req.project_id}
        if req.doc_type:
            filters["doc_type"] = req.doc_type
        if req.discipline:
            filters["discipline"] = req.discipline
        
        # TOC-aware routing: boost page ranges from table of contents if available
        toc_ranges = guess_toc_ranges(req.project_id, req.question)
        toc_boost_clauses = build_toc_boost_clauses(toc_ranges) if toc_ranges else None
        if toc_boost_clauses:
            print(f"  [TOC-QA] Boosting {len(toc_ranges)} page range(s)")
        
        result = answer_question(req.question, filters, size=req.size, toc_boost_clauses=toc_boost_clauses)
        return result
    
    except RuntimeError as e:
        # Handle API connectivity issues gracefully
        error_msg = str(e)
        if "Embedding failed" in error_msg or "timed out" in error_msg.lower():
            print(f"[QA Error] API connectivity issue: {error_msg}")
            return {
                "answer": "Service temporarily unavailable. The AI service is experiencing connectivity issues. Please try again in a moment.",
                "citations": []
            }
        elif "LLM call failed" in error_msg:
            print(f"[QA Error] LLM issue: {error_msg}")
            return {
                "answer": "Unable to generate answer at this time. Please try again in a moment.",
                "citations": []
            }
        else:
            print(f"[QA Error] Unexpected error: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Internal error: {error_msg}")
    
    except Exception as e:
        print(f"[QA Error] Unexpected exception: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected error occurred")


@app.post("/qa/stream")
def qa_stream(req: QARequest):
    """
    Streaming version of QA endpoint using Server-Sent Events (SSE).
    
    This endpoint streams the answer as it's being generated, providing:
    - Immediate feedback (status updates)
    - Partial answers as they're generated
    - Same quality as regular /qa endpoint
    
    The response is streamed in SSE format with these event types:
    - status: Progress updates ("Searching...", "Ranking...", "Generating...")
    - chunk: Partial answer text chunks
    - done: Final answer with citations
    - error: Error message if something goes wrong
    
    Frontend should use EventSource or fetch with stream handling to consume this.
    """
    try:
        filters: Dict[str, Any] = {"project_id": req.project_id}
        if req.doc_type:
            filters["doc_type"] = req.doc_type
        if req.discipline:
            filters["discipline"] = req.discipline
        
        # TOC-aware routing
        toc_ranges = guess_toc_ranges(req.project_id, req.question)
        toc_boost_clauses = build_toc_boost_clauses(toc_ranges) if toc_ranges else None
        if toc_boost_clauses:
            print(f"  [TOC-QA Stream] Boosting {len(toc_ranges)} page range(s)")
        
        # Return streaming response
        return StreamingResponse(
            answer_question_stream(req.question, filters, size=req.size, toc_boost_clauses=toc_boost_clauses),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",  # Disable nginx buffering
            }
        )
    
    except Exception as e:
        print(f"[QA Stream Error] {e}")
        import traceback
        traceback.print_exc()
        
        # Return error as SSE
        def error_stream():
            yield f"data: {{\"type\": \"error\", \"message\": \"{str(e)}\"}}\n\n"
        
        return StreamingResponse(
            error_stream(),
            media_type="text/event-stream"
        )

# ============================================================================
# DEBUG ENDPOINTS
# ============================================================================

@app.get("/debug/toc/{doc_id}")
def debug_toc_entries(doc_id: str):
    """Debug endpoint to view TOC entries for a document."""
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT toc_id, title, page_start, page_end, confidence, raw_line
                FROM toc_entries
                WHERE doc_id = %s
                ORDER BY page_start
            """, (doc_id,))
            rows = cur.fetchall()
    
    return {
        "ok": True,
        "doc_id": doc_id,
        "toc_count": len(rows),
        "entries": [
            {
                "toc_id": r[0],
                "title": r[1],
                "page_start": r[2],
                "page_end": r[3],
                "confidence": float(r[4]) if r[4] else None,
                "raw_line": r[5]
            }
            for r in rows
        ]
    }

# ============================================================================
# CONVERSATION ENDPOINTS (for chat history)
# ============================================================================

@app.post("/conversations")
def create_conversation(body: ConvoCreate):
    """
    Create a new conversation for a project.
    Returns the conversation ID.
    """
    convo_id = "cv_" + uuid.uuid4().hex[:12]
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO conversations (convo_id, project_id, title) VALUES (%s, %s, %s)",
                (convo_id, body.project_id, body.title)
            )
        conn.commit()
    return {"ok": True, "convo_id": convo_id}

@app.get("/conversations")
def list_conversations(project_id: str = Query(..., description="Project ID to list conversations for")):
    """
    List all conversations for a project, ordered by most recent first.
    """
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT convo_id, project_id, title, created_at FROM conversations WHERE project_id = %s ORDER BY created_at DESC",
                (project_id,)
            )
            rows = cur.fetchall()
    
    return [
        {
            "convo_id": r[0],
            "project_id": r[1],
            "title": r[2],
            "created_at": r[3].isoformat()
        }
        for r in rows
    ]

@app.get("/conversations/{convo_id}/messages")
def get_conversation_messages(convo_id: str):
    """
    Get all messages in a conversation, ordered chronologically.
    """
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT role, content, citations, created_at FROM messages WHERE convo_id = %s ORDER BY created_at ASC",
                (convo_id,)
            )
            rows = cur.fetchall()
    
    return [
        {
            "role": r[0],
            "content": r[1],
            "citations": r[2],  # Already JSONB, psycopg returns as dict/list
            "created_at": r[3].isoformat()
        }
        for r in rows
    ]

@app.post("/conversations/{convo_id}/messages")
def add_conversation_message(convo_id: str, body: MessageCreate):
    """
    Add a message to a conversation (user or assistant).
    Auto-names conversation with first user message.
    """
    if body.role not in ("user", "assistant"):
        raise HTTPException(status_code=400, detail="role must be 'user' or 'assistant'")
    
    msg_id = "ms_" + uuid.uuid4().hex[:12]
    
    # Convert citations to JSON string for JSONB column
    citations_json = json.dumps(body.citations) if body.citations is not None else None
    
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO messages (msg_id, convo_id, role, content, citations) VALUES (%s, %s, %s, %s, %s)",
                (msg_id, convo_id, body.role, body.content, citations_json)
            )
            
            # Auto-name conversation with first user message (first 50 chars)
            if body.role == "user":
                cur.execute("SELECT COUNT(*) FROM messages WHERE convo_id=%s AND role='user'", (convo_id,))
                user_msg_count = cur.fetchone()[0]
                if user_msg_count == 1:  # This is the first user message
                    title = body.content[:50].strip()
                    if len(body.content) > 50:
                        title += "..."
                    cur.execute("UPDATE conversations SET title=%s WHERE convo_id=%s", (title, convo_id))
        
        conn.commit()
    
    return {"ok": True, "msg_id": msg_id}

@app.delete("/conversations/{convo_id}")
def delete_conversation(convo_id: str):
    """
    Delete a conversation and all its messages (CASCADE).
    """
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM conversations WHERE convo_id=%s", (convo_id,))
        conn.commit()
    
    return {"ok": True}

# ============================================================================
# PDF FILE STREAMING (for PDF.js viewer)
# ============================================================================

def _get_pdf_path(doc_id: str) -> str:
    """Get PDF file path from database."""
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT source_path FROM documents WHERE doc_id = %s", (doc_id,))
            row = cur.fetchone()
    
    if not row:
        raise HTTPException(status_code=404, detail="document not found")
    
    path = row[0]
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="file not found on disk")
    
    return path

@app.get("/documents/{doc_id}/file")
def stream_pdf(doc_id: str, request: Request):
    """
    Stream PDF with Range support for PDF.js.
    
    Supports partial content requests (HTTP 206) for efficient PDF loading
    and seeking within the document.
    """
    path = _get_pdf_path(doc_id)
    file_size = os.path.getsize(path)
    range_header = request.headers.get("range")

    def iter_file(start=0, end=None, chunk_size=1024*256):
        """Iterator that yields file chunks."""
        with open(path, "rb") as f:
            f.seek(start)
            remaining = (end - start + 1) if end is not None else None
            while True:
                read_size = chunk_size if remaining is None else min(chunk_size, remaining)
                data = f.read(read_size)
                if not data:
                    break
                if remaining is not None:
                    remaining -= len(data)
                yield data

    headers = {"Accept-Ranges": "bytes"}

    if range_header:
        # Parse range header (e.g., "bytes=0-1023")
        units, _, rng = range_header.partition("=")
        if units != "bytes":
            raise HTTPException(status_code=416, detail="Unsupported range unit")
        
        start_s, _, end_s = rng.partition("-")
        try:
            start = int(start_s) if start_s else 0
            end = int(end_s) if end_s else file_size - 1
        except ValueError:
            raise HTTPException(status_code=416, detail="Bad range")
        
        end = min(end, file_size - 1)
        
        if start > end or start >= file_size:
            raise HTTPException(status_code=416, detail="Bad range")
        
        content_length = end - start + 1
        headers.update({
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(content_length),
        })
        
        return StreamingResponse(
            iter_file(start, end),
            status_code=206,
            headers=headers,
            media_type="application/pdf"
        )

    # Full file request
    headers["Content-Length"] = str(file_size)
    return StreamingResponse(
        iter_file(),
        headers=headers,
        media_type="application/pdf"
    )

# ============================================================================
# Dashboard & Admin Endpoints
# ============================================================================

class IngestionProgress:
    """Track progress of background ingestion jobs."""
    def __init__(self, job_id: str, filename: str):
        self.job_id = job_id
        self.filename = filename
        self.status = "pending"  # pending, processing, completed, failed
        self.progress = 0.0  # 0.0 to 1.0
        self.message = ""
        self.doc_id = None
        self.project_id = None
        self.error = None
        self.created_at = datetime.now()

# In-memory storage for ingestion progress (simple, single-user)
ingestion_jobs: Dict[str, IngestionProgress] = {}

@app.get("/health/status")
async def health_status():
    """
    Check status of all external services.
    Returns: {service_name: "online" | "offline" | "degraded"}
    """
    status = {}
    
    # Check Naga AI
    try:
        from llm.embeddings import EmbedderNaga
        embedder = EmbedderNaga()
        test_vec = embedder.embed_batch(["test"])
        status["naga_ai"] = "online" if test_vec and len(test_vec) > 0 else "degraded"
    except Exception as e:
        status["naga_ai"] = "offline"
        status["naga_error"] = str(e)[:100]
    
    # Check Cohere
    try:
        import requests
        r = requests.get("https://api.cohere.ai/", timeout=5)
        status["cohere"] = "online" if r.status_code < 500 else "degraded"
    except Exception as e:
        status["cohere"] = "offline"
        status["cohere_error"] = str(e)[:100]
    
    # Check PostgreSQL
    try:
        conn = psycopg.connect(settings.POSTGRES_DSN)
        cur = conn.cursor()
        cur.execute("SELECT 1")
        cur.fetchone()
        conn.close()
        status["postgresql"] = "online"
    except Exception as e:
        status["postgresql"] = "offline"
        status["postgresql_error"] = str(e)[:100]
    
    # Check OpenSearch
    try:
        client = get_os_client()
        info = client.info()
        status["opensearch"] = "online" if info else "degraded"
    except Exception as e:
        status["opensearch"] = "offline"
        status["opensearch_error"] = str(e)[:100]
    
    return status

@app.get("/projects/list")
def list_projects():
    """
    Get all available projects for dropdown.
    Returns: [{project_id, doc_count, last_updated, titles}]
    """
    conn = psycopg.connect(settings.POSTGRES_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            project_id,
            COUNT(doc_id) as doc_count,
            MAX(created_at) as last_updated,
            array_agg(title ORDER BY created_at DESC) as titles
        FROM documents
        GROUP BY project_id
        ORDER BY last_updated DESC
    """)
    
    projects = []
    for row in cur.fetchall():
        projects.append({
            "project_id": row[0],
            "doc_count": row[1],
            "last_updated": row[2].isoformat() if row[2] else None,
            "titles": row[3] if row[3] else []
        })
    
    conn.close()
    return {"projects": projects}

@app.get("/admin/documents")
def list_all_documents():
    """
    Get all documents with detailed information for dashboard management.
    Returns: [{doc_id, title, project_id, doc_type, pages, visual_items, tables, created_at}]
    """
    conn = psycopg.connect(settings.POSTGRES_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT 
            d.doc_id,
            d.title,
            d.project_id,
            d.doc_type,
            d.created_at,
            (SELECT COUNT(*) FROM pages WHERE pages.doc_id = d.doc_id) as page_count,
            (SELECT COUNT(*) FROM visual_content WHERE visual_content.doc_id = d.doc_id) as visual_count,
            (SELECT COUNT(*) FROM table_rows WHERE table_rows.doc_id = d.doc_id) as table_count,
            (SELECT COUNT(*) FROM chunks WHERE chunks.doc_id = d.doc_id) as chunk_count
        FROM documents d
        ORDER BY d.created_at DESC
    """)
    
    documents = []
    for row in cur.fetchall():
        documents.append({
            "doc_id": row[0],
            "title": row[1],
            "project_id": row[2],
            "doc_type": row[3],
            "created_at": row[4].isoformat() if row[4] else None,
            "page_count": row[5],
            "visual_count": row[6],
            "table_count": row[7],
            "chunk_count": row[8]
        })
    
    conn.close()
    return {"documents": documents}

@app.post("/admin/upload-pdf")
async def upload_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    project_id: str = Form(...),
    doc_type: str = Form("permit"),
    discipline: Optional[str] = Form(None)
):
    """
    Upload PDF and start background ingestion.
    Returns job_id to track progress.
    """
    # Validate file type
    if not file.filename.endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are allowed")
    
    # Generate job ID
    job_id = str(uuid.uuid4())
    
    # Save uploaded file permanently (not temp file)
    import shutil
    uploads_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "data", "uploads")
    os.makedirs(uploads_dir, exist_ok=True)
    
    # Generate unique filename to avoid conflicts
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_filename = file.filename.replace(" ", "_")
    permanent_path = os.path.join(uploads_dir, f"{timestamp}_{safe_filename}")
    
    with open(permanent_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    
    # Initialize progress tracker
    progress = IngestionProgress(job_id, file.filename)
    ingestion_jobs[job_id] = progress
    
    # Start background task
    background_tasks.add_task(
        ingest_pdf_with_progress,
        job_id=job_id,
        file_path=permanent_path,
        filename=file.filename,
        project_id=project_id,
        doc_type=doc_type,
        discipline=discipline
    )
    
    return {
        "job_id": job_id,
        "message": "Ingestion started",
        "filename": file.filename,
        "project_id": project_id
    }

@app.get("/admin/ingestion-status/{job_id}")
def get_ingestion_status(job_id: str):
    """
    Get current progress of an ingestion job.
    Includes database fallback for jobs that completed before API restart.
    """
    # Check in-memory storage first
    if job_id in ingestion_jobs:
        progress = ingestion_jobs[job_id]
        return {
            "job_id": job_id,
            "filename": progress.filename,
            "status": progress.status,
            "progress": progress.progress,
            "message": progress.message,
            "doc_id": progress.doc_id,
            "project_id": progress.project_id,
            "error": progress.error
        }
    
    # Fallback: Check if document exists in database
    # (Job might have completed before API restart)
    conn = psycopg.connect(settings.POSTGRES_DSN)
    cur = conn.cursor()
    cur.execute("""
        SELECT doc_id, title, project_id, created_at 
        FROM documents 
        WHERE doc_id = %s
        ORDER BY created_at DESC 
        LIMIT 1
    """, (job_id,))
    
    row = cur.fetchone()
    conn.close()
    
    if row:
        # Found document with matching doc_id (ingestion completed)
        return {
            "job_id": job_id,
            "filename": row[1],
            "status": "completed",
            "progress": 1.0,
            "message": f"Ingestion completed: {row[1]}",
            "doc_id": row[0],
            "project_id": row[2]
        }
    
    # Job not found anywhere
    return {
        "job_id": job_id,
        "status": "unknown",
        "progress": 0.0,
        "message": "Job not found. It may have been completed before API restart. Check the projects list.",
        "error": None
    }

async def ingest_pdf_with_progress(
    job_id: str,
    file_path: str,
    filename: str,
    project_id: str,
    doc_type: str,
    discipline: Optional[str]
):
    """
    Background task to ingest PDF with progress updates.
    Follows the same flow as /ingest/replace endpoint.
    """
    progress = ingestion_jobs[job_id]
    
    try:
        progress.status = "processing"
        progress.project_id = project_id
        progress.message = "Starting PDF processing..."
        progress.progress = 0.05
        
        # Generate doc_id
        doc_id = f"doc_{uuid.uuid4().hex[:8]}"
        progress.doc_id = doc_id
        
        # Step 1: Extract pages & blocks
        progress.message = "Extracting text and metadata from PDF..."
        progress.progress = 0.1
        
        extracted = extract_pdf(file_path)
        pages = extracted["pages"]
        progress.progress = 0.15
        progress.message = f"Extracted {len(pages)} pages"
        
        # Step 2: Extract TOC
        progress.message = "Extracting table of contents..."
        progress.progress = 0.2
        toc_count = try_extract_toc(doc_id, pages)
        
        # Step 3: Upsert doc + pages to database
        progress.message = "Saving document to database..."
        progress.progress = 0.25
        checksum = file_checksum(file_path)
        
        conn = psycopg.connect(settings.POSTGRES_DSN)
        try:
            upsert_doc_and_pages(conn, doc_id, project_id, filename, doc_type, discipline or "", file_path, checksum, pages)
            progress.progress = 0.3
            
            # Step 4: Process with Vision LLM if enabled
            if settings.USE_VISION_LLM:
                progress.message = "Processing visual content with Vision LLM..."
                progress.progress = 0.35
                
                vision_stats = process_document_with_vision(conn, file_path, doc_id, pages)
                progress.progress = 0.5
                progress.message = f"Vision LLM processed {vision_stats.get('visual_pages_processed', 0)} pages"
            
            # Step 5: Process with Unstructured if enabled
            if settings.USE_UNSTRUCTURED:
                progress.message = "Extracting tables with Unstructured.io..."
                progress.progress = 0.55
                
                from ingest.unstructured_processor import process_document_with_unstructured
                unstructured_stats = process_document_with_unstructured(
                    conn, file_path, doc_id, project_id, doc_type, discipline or "", pages
                )
                progress.progress = 0.65
                progress.message = f"Extracted {unstructured_stats.get('tables_extracted', 0)} tables"
            
            # Step 6: Chunk pages
            progress.message = "Creating text chunks..."
            progress.progress = 0.7
            chunks = chunk_pages(doc_id, project_id, doc_type, discipline or "", pages)
            
            if not chunks:
                progress.status = "failed"
                progress.error = "No chunks produced"
                progress.message = "Failed: No text chunks could be created"
                return
            
            # Step 7: Embed chunks
            progress.message = "Generating embeddings..."
            progress.progress = 0.75
            vectors = embed_chunks(chunks)
            
            # Step 8: Index chunks to OpenSearch
            progress.message = "Indexing chunks to search engine..."
            progress.progress = 0.8
            os_client = get_os_client()
            bulk_index_chunks(conn, os_client, chunks, vectors)
            
            # Step 9: Embed + Index visual content if Vision LLM was used
            if settings.USE_VISION_LLM:
                progress.message = "Indexing visual content..."
                progress.progress = 0.9
                visual_index_stats = process_visual_content_for_search(conn, os_client, doc_id, project_id)
                progress.message = f"Indexed {visual_index_stats.get('entries_indexed', 0)} visual content items"
            
            progress.progress = 0.95
            
        finally:
            conn.close()
        
        # Complete
        progress.status = "completed"
        progress.message = f"Successfully ingested {filename}"
        progress.progress = 1.0
        
        print(f"[Ingestion Complete] {filename} → doc_id={doc_id}, project={project_id}, pages={len(pages)}, chunks={len(chunks)}, toc={toc_count}")
        
    except Exception as e:
        progress.status = "failed"
        progress.error = str(e)
        progress.message = f"Ingestion failed: {str(e)}"
        print(f"[Ingestion Error] {filename}: {e}")
        import traceback
        traceback.print_exc()
        
        # If ingestion failed, clean up the uploaded file
        if os.path.exists(file_path):
            os.remove(file_path)
            print(f"[Cleanup] Removed failed upload: {file_path}")

