"""
Unstructured PDF parser for scanned pages and table extraction.

Uses unstructured library to:
1. Extract text from scanned/image-heavy pages via OCR
2. Detect and parse table structures
3. Maintain coordinates for PDF highlighting
"""

from typing import List, Dict, Any, Optional
import logging

# Import will fail gracefully if unstructured not installed
try:
    from unstructured.partition.pdf import partition_pdf
    UNSTRUCTURED_AVAILABLE = True
except ImportError:
    UNSTRUCTURED_AVAILABLE = False
    partition_pdf = None

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


def is_unstructured_available() -> bool:
    """Check if unstructured library is installed"""
    return UNSTRUCTURED_AVAILABLE


def partition_pdf_with_unstructured(
    path: str,
    strategy: str = "hi_res",
    infer_tables: bool = True
) -> List[Any]:
    """
    Partition PDF using unstructured library with best practices for scanned/mixed PDFs.
    
    Args:
        path: Path to PDF file
        strategy: "fast" or "hi_res" (hi_res recommended for scanned PDFs with tables)
        infer_tables: Whether to detect and parse table structures
        
    Returns:
        List of unstructured elements
        
    Raises:
        ImportError: If unstructured is not installed
        Exception: If partitioning fails
    """
    if not UNSTRUCTURED_AVAILABLE:
        raise ImportError(
            "unstructured library not installed. "
            "Install with: pip install 'unstructured[pdf]'"
        )
    
    logger.info(f"Partitioning PDF with unstructured (strategy={strategy}, infer_tables={infer_tables})")
    
    try:
        elements = partition_pdf(
            filename=path,
            strategy=strategy,
            extract_image_block_types=["Table"],  # Extract tables from images
            infer_table_structure=infer_tables,
            ocr_mode="entire_page",               # Process entire page with OCR (best for mixed PDFs)
            languages=["eng"],                    # Use new parameter instead of deprecated ocr_languages
            include_page_breaks=True,             # Better page boundary detection
            extract_tables=True,                  # Explicitly extract tables
            table_as_cells=False,                 # Get table as rows (not cells) - better for merged cells
        )
        logger.info(f"Extracted {len(elements)} elements from PDF")
        
        # Debug: Log table elements found
        tables = [e for e in elements if e.category == "Table"]
        if tables:
            logger.info(f"  Found {len(tables)} table elements")
            for i, t in enumerate(tables[:3]):  # Log first 3 tables
                html = getattr(t.metadata, "text_as_html", None)
                logger.info(f"    Table {i+1}: page={t.metadata.page_number}, "
                           f"has_html={bool(html)}, text_len={len(t.text) if t.text else 0}")
        
        return elements
    except Exception as e:
        logger.error(f"Unstructured partitioning failed: {e}")
        raise


def element_bbox_pts(element: Any) -> Optional[List[float]]:
    """
    Extract bounding box from unstructured element in PDF points (72 DPI).
    
    Args:
        element: Unstructured element
        
    Returns:
        [x1, y1, x2, y2] in PDF points, or None if not available
    """
    try:
        metadata = getattr(element, "metadata", None)
        if not metadata:
            return None
            
        coords = getattr(metadata, "coordinates", None)
        if not coords or not hasattr(coords, "points"):
            return None
        
        points = coords.points
        if len(points) < 4:
            return None
        
        # Points are typically [(x1,y1), (x2,y1), (x2,y2), (x1,y2)]
        # Extract bbox as [x1, y1, x2, y2]
        x_coords = [p[0] for p in points]
        y_coords = [p[1] for p in points]
        
        return [
            min(x_coords),
            min(y_coords),
            max(x_coords),
            max(y_coords)
        ]
    except Exception as e:
        logger.debug(f"Failed to extract bbox from element: {e}")
        return None


def parse_html_table(html_str: str) -> List[Dict[str, Any]]:
    """
    Parse HTML table into structured rows.
    
    Handles:
    - Column headers (th tags)
    - Merged cells (colspan/rowspan attributes)
    - Complex table structures
    
    Args:
        html_str: HTML table string
        
    Returns:
        List of dicts with 'columns' key containing column_name -> value mapping
    """
    if not html_str or not html_str.strip():
        return []
    
    try:
        soup = BeautifulSoup(html_str, 'html.parser')
        table = soup.find('table')
        if not table:
            return []
        
        rows_data = []
        
        # Extract headers if present
        headers = []
        header_row = table.find('thead')
        if header_row:
            headers = [th.get_text(strip=True) for th in header_row.find_all(['th', 'td'])]
        elif table.find('tr'):
            # Try first row as headers if all cells are <th>
            first_row = table.find('tr')
            ths = first_row.find_all(['th', 'td'])
            if ths and all(cell.name == 'th' for cell in ths):
                headers = [th.get_text(strip=True) for th in ths]
        
        # Debug: Log header extraction
        logger.debug(f"Extracted {len(headers)} headers: {headers}")
        
        # Extract data rows
        tbody = table.find('tbody') or table
        for row_idx, tr in enumerate(tbody.find_all('tr')):
            # Get all cells (both td and th)
            cells = tr.find_all(['td', 'th'])
            
            # Extract text and handle colspan
            cell_values = []
            for cell in cells:
                text = cell.get_text(strip=True)
                colspan = int(cell.get('colspan', 1))
                # Repeat value for colspan (simple handling of merged cells)
                for _ in range(colspan):
                    cell_values.append(text)
            
            if not cell_values or all(not v for v in cell_values):
                continue
            
            # Create column mapping
            if headers and len(cell_values) <= len(headers):
                # Use headers as keys (pad cell_values if needed)
                padded_values = cell_values + [''] * (len(headers) - len(cell_values))
                row_dict = dict(zip(headers, padded_values))
            elif headers and len(cell_values) > len(headers):
                # More values than headers - use headers for first N, then generic names
                row_dict = dict(zip(headers, cell_values[:len(headers)]))
                for i, val in enumerate(cell_values[len(headers):]):
                    row_dict[f"extra_col_{i}"] = val
            else:
                # Use generic column names
                row_dict = {f"col_{i}": val for i, val in enumerate(cell_values)}
            
            rows_data.append({"columns": row_dict})
        
        logger.debug(f"Parsed HTML table: {len(rows_data)} rows, {len(headers)} columns")
        return rows_data
        
    except Exception as e:
        logger.warning(f"Failed to parse HTML table: {e}")
        return []


def extract_table_text_fallback(element: Any) -> List[Dict[str, Any]]:
    """
    Fallback table extraction when HTML is not available.
    
    Attempts to parse table from plain text by splitting on newlines.
    
    Args:
        element: Unstructured table element
        
    Returns:
        List with single row containing raw text
    """
    text = getattr(element, "text", "").strip()
    if not text:
        return []
    
    # Simple fallback: treat entire table as one "row" with raw text
    # More sophisticated parsing could detect column separators
    return [{"columns": {"raw_text": text}}]


def filter_elements_by_page(elements: List[Any], page_number: int) -> List[Any]:
    """
    Filter unstructured elements to only those on a specific page.
    
    Args:
        elements: List of unstructured elements
        page_number: Page number (1-indexed)
        
    Returns:
        Filtered list of elements for that page
    """
    page_elements = []
    for el in elements:
        metadata = getattr(el, "metadata", None)
        if metadata and getattr(metadata, "page_number", None) == page_number:
            page_elements.append(el)
    
    return page_elements

