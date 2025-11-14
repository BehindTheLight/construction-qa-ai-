import fitz  # PyMuPDF
from typing import List, Dict, Any, Tuple
import hashlib
import os
import uuid
import psycopg
from core.settings import settings
from .ocr import render_page_image, tesseract_ocr_blocks
from .toc_parser import parse_toc_lines, canonical_label, looks_like_toc_page

def file_checksum(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()

def extract_pdf(path: str) -> Dict[str, Any]:
    """Return {pages: [ {page_number, width, height, is_scanned, blocks: [ {text, bbox} ] } ] }"""
    assert os.path.exists(path), f"file not found: {path}"
    doc = fitz.open(path)
    pages = []
    for i in range(doc.page_count):
        page = doc.load_page(i)
        width, height = page.rect.width, page.rect.height

        # Try text blocks (machine-readable); fall back to OCR if no text
        blocks_raw = page.get_text("blocks", flags=fitz.TEXT_PRESERVE_LIGATURES | fitz.TEXT_PRESERVE_WHITESPACE)
        blocks = []
        for b in blocks_raw:
            # b = (x0,y0,x1,y1, "text", block_no, block_type, ...)
            if len(b) >= 5:
                x0, y0, x1, y1, text = b[0], b[1], b[2], b[3], b[4]
                text = (text or "").strip()
                if text:
                    blocks.append({"text": text, "bbox": [x0, y0, x1, y1]})

        is_scanned = (len(blocks) == 0)
        
        # OCR scanned pages
        if is_scanned:
            print(f"  OCR page {i+1}...")
            pil_img = render_page_image(doc, i, dpi=300)
            ocr_blocks = tesseract_ocr_blocks(pil_img)
            blocks = [{"text": b["text"], "bbox": b["bbox"], "confidence": b.get("confidence")} for b in ocr_blocks]
            avg_conf = float(sum(b.get("confidence",0) for b in ocr_blocks)/len(ocr_blocks)) if ocr_blocks else None
        else:
            avg_conf = None
        pages.append({
            "page_number": i + 1,
            "width": int(width),
            "height": int(height),
            "is_scanned": is_scanned,
            "ocr_conf": avg_conf,
            "blocks": blocks
        })
    doc.close()
    return {"pages": pages}


def try_extract_toc(doc_id: str, pages_data: List[Dict[str, Any]]) -> int:
    """
    Extract table of contents from early pages and store in database.
    
    Args:
        doc_id: Document ID
        pages_data: List of page dicts from extract_pdf (with blocks)
        
    Returns:
        Number of TOC entries found and stored
    """
    # Build page_number -> full_text mapping for first 3 pages
    page_text_blocks = {}
    for page_data in pages_data[:3]:  # Only check first 3 pages
        page_num = page_data["page_number"]
        blocks = page_data.get("blocks", [])
        full_text = "\n".join([b["text"] for b in blocks if b.get("text")])
        page_text_blocks[page_num] = full_text
    
    candidates = []
    for page_num, txt in page_text_blocks.items():
        if not txt:
            continue
            
        # Check if this looks like a TOC page
        if not looks_like_toc_page(txt):
            continue
        
        print(f"  Found TOC on page {page_num}")
        lines = [l for l in txt.splitlines() if l.strip()]
        entries = parse_toc_lines(lines)
        
        for e in entries:
            e["page"] = page_num
            e["label"] = canonical_label(e["title"])  # May be None
        
        candidates.extend(entries)
    
    if not candidates:
        print("  No TOC found in document")
        return 0
    
    # Store in database
    stored_count = 0
    
    with psycopg.connect(settings.POSTGRES_DSN) as conn:
        with conn.cursor() as cur:
            for e in candidates:
                toc_id = "tc_" + uuid.uuid4().hex[:12]
                try:
                    cur.execute("""
                        INSERT INTO toc_entries (toc_id, doc_id, title, page_start, page_end, confidence, raw_line)
                        VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (doc_id, title, page_start, page_end) DO NOTHING
                    """, (
                        toc_id,
                        doc_id,
                        e["title"],
                        e["page_start"],
                        e["page_end"],
                        e.get("confidence", 0.8),
                        e.get("raw_line", "")
                    ))
                    stored_count += 1
                except Exception as ex:
                    print(f"  Warning: Failed to store TOC entry '{e['title']}': {ex}")
        conn.commit()
    
    print(f"  Stored {stored_count} TOC entries")
    return stored_count


def calculate_page_stats(page_data: Dict[str, Any], doc: fitz.Document, page_index: int) -> Dict[str, Any]:
    """
    Calculate statistics for a page to determine if Unstructured should be used.
    
    Args:
        page_data: Page data from extract_pdf
        doc: PyMuPDF document object
        page_index: 0-based page index
        
    Returns:
        Dict with char_len, image_coverage, vector_paths
    """
    # Character count from blocks
    char_len = sum(len(b.get("text", "")) for b in page_data.get("blocks", []))
    
    # Try to estimate image coverage and vector paths
    page = doc.load_page(page_index)
    
    # Count images
    images = page.get_images()
    image_coverage = 0.0
    if images:
        # Rough estimate: assume images cover significant area if present
        image_coverage = min(len(images) * 0.2, 0.9)  # Cap at 90%
    
    # Count vector paths (drawings have many paths)
    try:
        drawings = page.get_drawings()
        vector_paths = len(drawings)
    except:
        vector_paths = 0
    
    return {
        "char_len": char_len,
        "image_coverage": image_coverage,
        "vector_paths": vector_paths
    }


def should_use_unstructured(stats: Dict[str, Any]) -> bool:
    """
    Determine if Unstructured should be used for this page.
    
    Criteria:
    - Very low text (< 50 chars) - likely scanned or form
    - High image coverage (> 35%) - likely scanned document
    - Many vector paths (> 5000) - complex drawing with embedded tables
    
    Args:
        stats: Page statistics from calculate_page_stats
        
    Returns:
        True if Unstructured should be used
    """
    # Check threshold from settings
    min_text = settings.UNSTRUCTURED_MIN_TEXT_THRESHOLD
    
    if stats.get("char_len", 0) < min_text:
        return True
    
    if stats.get("image_coverage", 0.0) > 0.35:
        return True
    
    # Very complex drawings might have tables
    if stats.get("vector_paths", 0) > 5000:
        return True
    
    return False


def choose_unstructured_strategy(stats: Dict[str, Any]) -> str:
    """
    Choose the appropriate Unstructured strategy based on page characteristics.
    
    Args:
        stats: Page statistics
        
    Returns:
        "fast" or "hi_res"
    """
    # Use hi_res for very low text (likely scanned) or very complex drawings
    if stats.get("char_len", 0) < 20:
        return "hi_res"
    
    if stats.get("vector_paths", 0) > 8000:
        return "hi_res"
    
    # Default to fast for most cases
    return settings.UNSTRUCTURED_STRATEGY

