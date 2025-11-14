"""
Process pages with Vision LLM when enabled.

Orchestrates Vision LLM processing for visual content in PDFs.
"""

import fitz
import logging
from typing import List, Dict, Any

from core.settings import settings
from ingest.pdf_extractor import calculate_page_stats
from ingest.vision_parser import should_use_vision_llm, try_vision_parsing, delete_visual_content_for_doc

logger = logging.getLogger(__name__)


def process_document_with_vision(
    conn,
    pdf_path: str,
    doc_id: str,
    pages_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Orchestrates Vision LLM processing for a document.
    
    Identifies pages with visual content (drawings, scanned tables, diagrams)
    and processes them with Vision LLM.
    
    Args:
        conn: PostgreSQL connection
        pdf_path: Path to PDF file
        doc_id: Document ID
        pages_data: List of page data dicts from PDF extraction
        
    Returns:
        Dict with processing stats
    """
    if not settings.USE_VISION_LLM:
        logger.info("[Vision] USE_VISION_LLM is false, skipping processing.")
        return {"visual_pages_processed": 0, "visual_content_extracted": 0}
    
    logger.info(f"[Vision] Processing document {doc_id} with Vision LLM")
    
    # Open PDF for stats calculation
    doc = fitz.open(pdf_path)
    
    # Determine which pages need Vision LLM
    pages_to_process = []
    for page_data in pages_data:
        page_num = page_data["page_number"]
        page_index = page_num - 1  # 0-based for PyMuPDF
        
        # Calculate stats
        stats = calculate_page_stats(page_data, doc, page_index)
        
        # Check if Vision LLM should process this page
        if should_use_vision_llm(stats):
            pages_to_process.append((page_num, stats))
            logger.info(
                f"[Vision] Page {page_num} needs processing "
                f"(image_coverage={stats['image_coverage']:.2%}, chars={stats['char_len']})"
            )
    
    doc.close()
    
    if not pages_to_process:
        logger.info("[Vision] No pages need Vision LLM processing")
        return {"visual_pages_processed": 0, "visual_content_extracted": 0}
    
    # Apply max pages limit
    if len(pages_to_process) > settings.VISION_MAX_PAGES_PER_DOC:
        logger.warning(
            f"[Vision] Document has {len(pages_to_process)} visual pages, "
            f"limiting to {settings.VISION_MAX_PAGES_PER_DOC} (cost control)"
        )
        pages_to_process = pages_to_process[:settings.VISION_MAX_PAGES_PER_DOC]
    
    # Process each page with Vision LLM
    successful_pages = 0
    total_tokens = 0
    
    for page_num, stats in pages_to_process:
        logger.info(f"[Vision] Processing page {page_num}/{len(pages_to_process)}")
        
        result = try_vision_parsing(pdf_path, page_num, doc_id, conn)
        
        if result:
            successful_pages += 1
            tokens = result.get("tokens_used", {})
            total_tokens += tokens.get("total_tokens", 0)
            logger.info(
                f"[Vision] ✓ Page {page_num} processed successfully "
                f"(type={result['content_type']}, tokens={tokens.get('total_tokens', 0)})"
            )
        else:
            logger.warning(f"[Vision] ✗ Page {page_num} processing failed")
    
    logger.info(
        f"[Vision] Finished processing. "
        f"Successful: {successful_pages}/{len(pages_to_process)} pages, "
        f"Total tokens: {total_tokens}"
    )
    
    return {
        "visual_pages_processed": successful_pages,
        "visual_content_extracted": successful_pages,
        "total_vision_tokens": total_tokens
    }

