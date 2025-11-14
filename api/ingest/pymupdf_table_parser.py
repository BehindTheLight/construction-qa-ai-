"""
PyMuPDF-based table parser for complex tables with merged cells.

This parser uses text bounding boxes to spatially parse tables that 
Unstructured's automatic HTML parser struggles with.

Specifically designed for tables like "Fire and Sound Resistance of Walls"
which have nested headers and merged cells.
"""

import fitz  # PyMuPDF
import logging
from typing import List, Dict, Any, Optional, Tuple
import re

logger = logging.getLogger(__name__)


def extract_text_blocks_with_bbox(page: fitz.Page) -> List[Dict[str, Any]]:
    """
    Extract all text blocks from a PyMuPDF page with bounding boxes.
    
    Args:
        page: PyMuPDF page object
        
    Returns:
        List of dicts with 'text', 'bbox' (x0, y0, x1, y1), 'y_mid' (vertical center)
    """
    blocks = []
    text_dict = page.get_text("dict")
    
    for block in text_dict["blocks"]:
        if block["type"] == 0:  # Text block
            for line in block["lines"]:
                for span in line["spans"]:
                    text = span["text"].strip()
                    if text:
                        bbox = span["bbox"]  # (x0, y0, x1, y1)
                        blocks.append({
                            "text": text,
                            "bbox": bbox,
                            "x0": bbox[0],
                            "y0": bbox[1],
                            "x1": bbox[2],
                            "y1": bbox[3],
                            "y_mid": (bbox[1] + bbox[3]) / 2,  # Vertical center
                            "x_mid": (bbox[0] + bbox[2]) / 2,  # Horizontal center
                        })
    
    return blocks


def group_blocks_by_row(blocks: List[Dict], y_tolerance: float = 5.0) -> List[List[Dict]]:
    """
    Group text blocks into rows based on vertical position.
    
    Args:
        blocks: List of text blocks with bbox info
        y_tolerance: Maximum Y difference to consider blocks on same row
        
    Returns:
        List of rows, where each row is a list of blocks sorted by X position
    """
    if not blocks:
        return []
    
    # Sort by vertical position
    sorted_blocks = sorted(blocks, key=lambda b: b["y_mid"])
    
    rows = []
    current_row = [sorted_blocks[0]]
    current_y = sorted_blocks[0]["y_mid"]
    
    for block in sorted_blocks[1:]:
        if abs(block["y_mid"] - current_y) <= y_tolerance:
            # Same row
            current_row.append(block)
        else:
            # New row
            rows.append(sorted(current_row, key=lambda b: b["x0"]))  # Sort by X
            current_row = [block]
            current_y = block["y_mid"]
    
    # Add last row
    if current_row:
        rows.append(sorted(current_row, key=lambda b: b["x0"]))
    
    return rows


def detect_fire_resistance_table(blocks: List[Dict]) -> Optional[Tuple[float, float]]:
    """
    Detect if the page contains "Fire and Sound Resistance of Walls" table.
    
    Args:
        blocks: Text blocks from the page
        
    Returns:
        (start_y, end_y) tuple if table found, None otherwise
    """
    # Look for table header
    for i, block in enumerate(blocks):
        if "Fire" in block["text"] and "Sound" in block["text"] and "Resistance" in block["text"]:
            logger.info(f"Found Fire & Sound Resistance table header at y={block['y_mid']:.1f}")
            start_y = block["y0"]
            
            # Find end of table (look for next major section or end of content)
            # Typically extends 400-500 pts down from header
            end_y = start_y + 500
            
            return (start_y, end_y)
    
    return None


def parse_fire_resistance_table(page: fitz.Page) -> List[Dict[str, Any]]:
    """
    Parse the "Fire and Sound Resistance of Walls" table using spatial analysis.
    
    Table structure:
    - Column 1: Wall Number (W1a, W2b, etc.) - leftmost, narrow
    - Column 2: Description (wide text block)
    - Column 3-4: Fire-Resistance Ratings (split into Loadbearing/Non-Loadbearing)
    - Column 5: STC values
    
    Args:
        page: PyMuPDF page object
        
    Returns:
        List of parsed table rows with structured data
    """
    blocks = extract_text_blocks_with_bbox(page)
    
    # Detect table boundaries
    table_bounds = detect_fire_resistance_table(blocks)
    if not table_bounds:
        return []
    
    start_y, end_y = table_bounds
    
    # Filter blocks within table
    table_blocks = [b for b in blocks if start_y <= b["y_mid"] <= end_y]
    
    if not table_blocks:
        return []
    
    logger.info(f"Found {len(table_blocks)} text blocks in Fire & Sound Resistance table")
    
    # Group into rows
    rows = group_blocks_by_row(table_blocks, y_tolerance=8.0)
    
    # Define column boundaries based on typical layout
    # These are approximate X positions for the table columns
    col_boundaries = {
        "wall_number": (0, 80),      # Left edge
        "description": (80, 350),     # Wide middle section
        "fire_lb": (350, 430),        # Fire-Resistance Loadbearing
        "fire_nlb": (430, 510),       # Fire-Resistance Non-Loadbearing
        "stc": (510, 1000),           # STC (rightmost)
    }
    
    parsed_rows = []
    wall_pattern = re.compile(r'W\d+[a-z]?', re.IGNORECASE)
    
    for row_idx, row in enumerate(rows):
        # Skip header rows (first few rows)
        if row_idx < 3:
            continue
        
        # Check if this row contains a wall identifier
        row_text = " ".join([b["text"] for b in row])
        wall_match = wall_pattern.search(row_text)
        
        if not wall_match:
            continue
        
        wall_number = wall_match.group(0).upper()
        
        # Extract values by column position
        description_parts = []
        fire_lb = ""
        fire_nlb = ""
        stc = ""
        
        for block in row:
            x_mid = block["x_mid"]
            text = block["text"]
            
            # Assign to column based on X position
            if col_boundaries["wall_number"][0] <= x_mid < col_boundaries["wall_number"][1]:
                pass  # Wall number already extracted
            elif col_boundaries["description"][0] <= x_mid < col_boundaries["description"][1]:
                description_parts.append(text)
            elif col_boundaries["fire_lb"][0] <= x_mid < col_boundaries["fire_lb"][1]:
                fire_lb = text
            elif col_boundaries["fire_nlb"][0] <= x_mid < col_boundaries["fire_nlb"][1]:
                fire_nlb = text
            elif col_boundaries["stc"][0] <= x_mid:
                stc = text
        
        description = " ".join(description_parts)
        
        # Only add if we have substantive data
        if wall_number and (description or fire_lb or fire_nlb or stc):
            parsed_row = {
                "columns": {
                    "Wall Number": wall_number,
                    "Description": description,
                    "Fire-Resistance Rating (Loadbearing)": fire_lb,
                    "Fire-Resistance Rating (Non-Loadbearing)": fire_nlb,
                    "Typical Sound Transmission Class (STC)": stc
                }
            }
            parsed_rows.append(parsed_row)
            logger.info(f"  Parsed {wall_number}: LB={fire_lb}, NLB={fire_nlb}, STC={stc}")
    
    logger.info(f"PyMuPDF parser extracted {len(parsed_rows)} rows from Fire & Sound Resistance table")
    return parsed_rows


def try_pymupdf_table_parsing(pdf_path: str, page_number: int) -> Optional[List[Dict[str, Any]]]:
    """
    Attempt to parse tables using PyMuPDF bbox-based method.
    
    Args:
        pdf_path: Path to PDF file
        page_number: Page number (1-indexed)
        
    Returns:
        List of parsed table rows if successful, None otherwise
    """
    try:
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_number - 1)  # 0-indexed
        
        # Try to parse Fire & Sound Resistance table
        rows = parse_fire_resistance_table(page)
        
        doc.close()
        
        if rows:
            return rows
        
        return None
        
    except Exception as e:
        logger.error(f"PyMuPDF table parsing failed for page {page_number}: {e}")
        return None


