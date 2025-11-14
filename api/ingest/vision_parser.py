"""
Vision LLM parser for visual content in construction PDFs.

Handles:
- Rendering PDF pages to high-quality images
- Calling Vision LLM for analysis
- Storing results in visual_content table
"""

import fitz  # PyMuPDF
import io
import json
import logging
import uuid
from typing import Dict, Any, Optional, List
from PIL import Image

from core.settings import settings
from llm.vision_client import call_vision_llm, encode_image_to_base64, flatten_vision_data_to_text

logger = logging.getLogger(__name__)


def render_page_to_image(page: fitz.Page, dpi: int = 300, max_size: int = 2048) -> bytes:
    """
    Render a PDF page to PNG image bytes.
    
    Args:
        page: PyMuPDF page object
        dpi: Dots per inch for rendering (higher = better quality)
        max_size: Maximum width/height in pixels (for cost control)
        
    Returns:
        PNG image as bytes
    """
    # Calculate zoom factor from DPI (72 DPI is default)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    
    # Render page to pixmap
    pix = page.get_pixmap(matrix=mat, alpha=False)
    
    # Convert to PIL Image for resizing if needed
    img_data = pix.tobytes("png")
    img = Image.open(io.BytesIO(img_data))
    
    # Resize if image is too large (to control API costs)
    if img.width > max_size or img.height > max_size:
        # Calculate new size maintaining aspect ratio
        ratio = min(max_size / img.width, max_size / img.height)
        new_width = int(img.width * ratio)
        new_height = int(img.height * ratio)
        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
        logger.info(f"Resized image from {pix.width}x{pix.height} to {new_width}x{new_height}")
    
    # Convert back to PNG bytes
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()


def should_use_vision_llm(page_stats: Dict[str, Any]) -> bool:
    """
    Determine if a page should be processed with Vision LLM.
    
    Triggers when image coverage > threshold (always, regardless of text).
    
    Args:
        page_stats: Dictionary with 'char_len', 'image_coverage', 'vector_paths'
        
    Returns:
        True if Vision LLM should process this page
    """
    image_coverage = page_stats.get("image_coverage", 0.0)
    
    # Always trigger if image coverage exceeds threshold
    if image_coverage >= settings.VISION_MIN_IMAGE_COVERAGE:
        logger.info(f"Vision LLM triggered: image_coverage={image_coverage:.2%}")
        return True
    
    return False


def try_vision_parsing(
    pdf_path: str,
    page_number: int,
    doc_id: str,
    conn
) -> Optional[Dict[str, Any]]:
    """
    Process a PDF page with Vision LLM.
    
    Steps:
    1. Render page to high-quality PNG
    2. Encode to base64
    3. Call Vision LLM API
    4. Parse response
    5. Store in visual_content table
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        doc_id: Document ID
        conn: PostgreSQL connection
        
    Returns:
        Dict with processing results or None if failed
    """
    if not settings.USE_VISION_LLM:
        return None
    
    try:
        # Open PDF and get page
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_number - 1)  # 0-indexed
        
        logger.info(f"[Vision] Processing page {page_number}: rendering to image...")
        
        # Render page to image
        image_bytes = render_page_to_image(
            page,
            dpi=settings.VISION_IMAGE_DPI,
            max_size=settings.VISION_IMAGE_MAX_SIZE
        )
        
        doc.close()
        
        # Encode to base64
        image_base64 = encode_image_to_base64(image_bytes)
        
        # Call Vision LLM
        logger.info(f"[Vision] Calling Vision LLM for page {page_number}...")
        vision_result = call_vision_llm(image_base64, page_number)
        
        if not vision_result.get("success"):
            # Store error for debugging
            error_msg = vision_result.get("error", "Unknown error")
            logger.error(f"[Vision] Failed for page {page_number}: {error_msg}")
            
            content_id = "vc_" + uuid.uuid4().hex[:12]
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO visual_content 
                    (content_id, doc_id, page_number, content_type, data, extracted_text, error)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    content_id,
                    doc_id,
                    page_number,
                    "error",
                    "{}",  # Empty JSON
                    "",
                    error_msg
                ))
            conn.commit()
            
            return None
        
        # Extract data
        vision_data = vision_result["data"]
        content_type = vision_data.get("content_type", "unknown")
        
        # Flatten to searchable text
        extracted_text = flatten_vision_data_to_text(vision_data)
        
        # Generate content ID
        content_id = "vc_" + uuid.uuid4().hex[:12]
        
        # Store in database
        logger.info(f"[Vision] Storing {content_type} content for page {page_number}")
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO visual_content 
                (content_id, doc_id, page_number, content_type, data, extracted_text, confidence)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (
                content_id,
                doc_id,
                page_number,
                content_type,
                json.dumps(vision_data),
                extracted_text,
                0.95  # High confidence for Vision LLM
            ))
        conn.commit()
        
        logger.info(f"[Vision] ✓ Successfully processed page {page_number} ({content_type})")
        
        return {
            "content_id": content_id,
            "content_type": content_type,
            "page_number": page_number,
            "extracted_text": extracted_text,
            "tokens_used": vision_result.get("tokens_used", {})
        }
    
    except Exception as e:
        logger.error(f"[Vision] Unexpected error processing page {page_number}: {e}")
        
        # Store error
        try:
            content_id = "vc_" + uuid.uuid4().hex[:12]
            with conn.cursor() as cur:
                cur.execute("""
                    INSERT INTO visual_content 
                    (content_id, doc_id, page_number, content_type, data, extracted_text, error)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                """, (
                    content_id,
                    doc_id,
                    page_number,
                    "error",
                    "{}",
                    "",
                    str(e)
                ))
            conn.commit()
        except Exception as e2:
            logger.error(f"[Vision] Failed to store error: {e2}")
        
        return None


def delete_visual_content_for_doc(conn, doc_id: str):
    """Delete all visual content for a document."""
    logger.info(f"Deleting visual content for doc_id={doc_id}")
    with conn.cursor() as cur:
        cur.execute("DELETE FROM visual_content WHERE doc_id = %s", (doc_id,))
        rows_deleted = cur.rowcount
    conn.commit()
    logger.info(f"  Deleted {rows_deleted} visual content entries from PostgreSQL for doc_id={doc_id}")

