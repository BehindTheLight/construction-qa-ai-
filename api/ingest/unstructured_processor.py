"""
Process pages with Unstructured when needed.

Integrates Unstructured PDF processing into the main ingestion pipeline.
"""

import fitz
from typing import List, Dict, Any
import logging

from core.settings import settings
from ingest.unstructured_pdf import (
    is_unstructured_available,
    partition_pdf_with_unstructured,
    filter_elements_by_page,
    element_bbox_pts,
    parse_html_table,
    extract_table_text_fallback
)
from ingest.pdf_extractor import (
    calculate_page_stats,
    should_use_unstructured,
    choose_unstructured_strategy
)
from ingest.table_indexer import index_table_rows, delete_table_rows_for_doc
from ingest.pymupdf_table_parser import try_pymupdf_table_parsing
from search.opensearch_client import get_os_client

logger = logging.getLogger(__name__)


def process_document_with_unstructured(
    conn,
    pdf_path: str,
    doc_id: str,
    project_id: str,
    doc_type: str,
    discipline: str,
    pages_data: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """
    Process a PDF document with Unstructured for pages that need it.
    
    Args:
        conn: PostgreSQL connection
        pdf_path: Path to PDF file
        doc_id: Document ID
        project_id: Project ID
        doc_type: Document type
        discipline: Discipline
        pages_data: Page data from extract_pdf
        
    Returns:
        Dict with stats (tables_extracted, pages_processed)
    """
    if not settings.USE_UNSTRUCTURED:
        logger.info("[Unstructured] Disabled in settings")
        return {"tables_extracted": 0, "pages_processed": 0}
    
    if not is_unstructured_available():
        logger.warning("[Unstructured] Library not available, skipping")
        return {"tables_extracted": 0, "pages_processed": 0}
    
    logger.info(f"[Unstructured] Processing document {doc_id}")
    
    # Open PDF for stats calculation
    doc = fitz.open(pdf_path)
    
    # Determine which pages need Unstructured
    pages_to_process = []
    for page_data in pages_data:
        page_num = page_data["page_number"]
        page_index = page_num - 1  # 0-based for PyMuPDF
        
        # Check if page was scanned (OCR'd) or meets heuristics
        is_scanned = page_data.get("is_scanned", False)
        
        stats = calculate_page_stats(page_data, doc, page_index)
        needs_unstructured = is_scanned or should_use_unstructured(stats)
        
        if needs_unstructured:
            strategy = choose_unstructured_strategy(stats)
            pages_to_process.append((page_num, strategy, stats))
            reason = "scanned" if is_scanned else f"heuristics (chars={stats['char_len']})"
            logger.info(
                f"[Unstructured] Page {page_num} needs processing ({reason}, strategy={strategy})"
            )
    
    doc.close()
    
    if not pages_to_process:
        logger.info("[Unstructured] No pages need processing")
        return {"tables_extracted": 0, "pages_processed": 0}
    
    # Process with Unstructured (do it once for the whole document)
    # Use the most conservative strategy if multiple pages
    strategies = [s for _, s, _ in pages_to_process]
    strategy = "hi_res" if "hi_res" in strategies else settings.UNSTRUCTURED_STRATEGY
    
    logger.info(f"[Unstructured] Partitioning PDF with strategy={strategy}")
    try:
        elements = partition_pdf_with_unstructured(
            pdf_path,
            strategy=strategy,
            infer_tables=settings.UNSTRUCTURED_INFER_TABLES
        )
    except Exception as e:
        logger.error(f"[Unstructured] Partitioning failed: {e}")
        return {"tables_extracted": 0, "pages_processed": 0}
    
    # Process each page
    os_client = get_os_client()
    total_tables = 0
    
    for page_num, _, _ in pages_to_process:
        # Try PyMuPDF parser first (if enabled)
        table_rows = []
        pymupdf_success = False
        
        if settings.USE_PYMUPDF_TABLE_PARSER:
            logger.info(f"[PyMuPDF] Trying bbox-based table parsing for page {page_num}")
            pymupdf_rows = try_pymupdf_table_parsing(pdf_path, page_num)
            if pymupdf_rows:
                table_rows.extend(pymupdf_rows)
                pymupdf_success = True
                logger.info(f"[PyMuPDF] Successfully parsed {len(pymupdf_rows)} rows on page {page_num}")
        
        # If PyMuPDF didn't find tables, try Unstructured
        if not pymupdf_success:
            # Filter elements for this page
            page_elements = filter_elements_by_page(elements, page_num)
            
            # Extract tables from Unstructured elements
            for el in page_elements:
                if el.category == "Table":
                    # Try to parse HTML if available
                    html = getattr(el.metadata, "text_as_html", None)
                    if html:
                        rows = parse_html_table(html)
                        logger.info(f"    Parsed table on page {page_num}: {len(rows)} rows extracted")
                        # Debug: Show first 2 rows
                        for i, row in enumerate(rows[:2]):
                            logger.debug(f"      Row {i}: {row.get('columns', {})}")
                    else:
                        rows = extract_table_text_fallback(el)
                        logger.info(f"    No HTML for table on page {page_num}, using fallback: {len(rows)} rows")
                    
                    # Add bbox to each row
                    bbox = element_bbox_pts(el)
                    for row in rows:
                        row["bbox"] = bbox
                    
                    table_rows.extend(rows)
        
        if table_rows:
            # Index table rows
            try:
                index_table_rows(
                    conn,
                    os_client,
                    doc_id,
                    project_id,
                    doc_type,
                    discipline,
                    page_num,
                    table_rows,
                    table_label=None  # Could extract from nearby text
                )
                total_tables += len(table_rows)
                logger.info(f"[Unstructured] Page {page_num}: indexed {len(table_rows)} table rows")
            except Exception as e:
                logger.error(f"[Unstructured] Failed to index tables for page {page_num}: {e}")
    
    return {
        "tables_extracted": total_tables,
        "pages_processed": len(pages_to_process)
    }

