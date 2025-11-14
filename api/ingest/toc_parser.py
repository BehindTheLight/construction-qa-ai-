"""
TOC Parser - Extract table of contents entries from PDF pages

Handles various formats:
- "Architectural drawing ..... 10-12"
- "Site plan .... 9"
- "Info .... 13–15" (en dash)
- "Title 10-12" (no dots)
"""

import re
from typing import List, Dict, Optional

# Patterns that handle: "Architectural drawing .... 10-12", "Site plan .... 9", "Info .... 13–15"
PAGE_NUM_END = r"(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?$"  # For matching at end of line
PAGE_NUM_STANDALONE = r"(\d{1,3})(?:\s*[-–]\s*(\d{1,3}))?"  # For standalone matching
DOT_LEADER = r"\.{2,}"  # "....." (optional)

def parse_toc_lines(lines: List[str]) -> List[Dict]:
    """
    Parse TOC lines to extract title and page ranges.
    
    Handles two formats:
    1. Same line: "Title ..... 10-12"
    2. Separate lines: "Title\n10-12"
    
    Args:
        lines: List of text lines from a page
        
    Returns:
        List of dicts with keys: title, page_start, page_end, raw_line, confidence
    """
    out = []
    i = 0
    
    while i < len(lines):
        ln = lines[i]
        s = ln.strip()
        
        if not s:
            i += 1
            continue
            
        # Format 1: Try "Title ..... 10-12" (with dot leaders) on same line
        m = re.search(rf"{DOT_LEADER}?\s*{PAGE_NUM_END}", s)
        if not m:
            # Try "Title 10-12" (no dots, just space) on same line
            m = re.search(rf"\s+{PAGE_NUM_END}", s)
        
        if m:
            # Found page number on same line
            p1 = int(m.group(1))
            p2 = int(m.group(2) or m.group(1))
            title = s[:m.start()].strip(" .\t")
            
            if title and p1 >= 1 and p2 >= p1:
                out.append({
                    "title": title,
                    "page_start": p1,
                    "page_end": p2,
                    "raw_line": ln,
                    "confidence": 0.9
                })
            i += 1
            continue
        
        # Format 2: Check if next line is just page number(s)
        if i + 1 < len(lines):
            next_line = lines[i + 1].strip()
            # Check if next line is ONLY page numbers (e.g., "10-12" or "5")
            page_match = re.match(rf"^{PAGE_NUM_STANDALONE}$", next_line)
            if page_match and s and len(s) > 2:  # Title must be meaningful
                p1 = int(page_match.group(1))
                p2 = int(page_match.group(2) or page_match.group(1))
                title = s.strip()
                
                if p1 >= 1 and p2 >= p1:
                    out.append({
                        "title": title,
                        "page_start": p1,
                        "page_end": p2,
                        "raw_line": f"{ln}\n{lines[i+1]}",
                        "confidence": 0.85
                    })
                    i += 2  # Skip both title and page number lines
                    continue
        
        i += 1
            
    return out


# Optional normalization for routing keywords
# Maps canonical labels to variants that might appear in TOC or queries
CANON = {
    "architectural drawing": [
        "architectural drawing", "architectural drawings", "architectural plans",
        "floor plan", "plans", "architecture"
    ],
    "site plan": ["site plan", "site", "lot plan"],
    "civil drawing": [
        "civil", "civil drawing", "lot grading", "grading", "civil engineering"
    ],
    "mechanical": [
        "mechanical", "hvac", "mechanical ventilation", "heating", "cooling"
    ],
    "electrical": ["electrical", "electric", "power"],
    "plumbing": ["plumbing", "plumb", "piping"],
    "specifications": [
        "specifications", "specs", "support doc", "supporting documents",
        "technical specs"
    ],
    "structural": ["structural", "structure", "framing"],
}


def canonical_label(title: str) -> Optional[str]:
    """
    Map a TOC title to a canonical label for routing.
    
    Args:
        title: TOC entry title
        
    Returns:
        Canonical label or None if no match
    """
    t = title.lower()
    for canon, variants in CANON.items():
        if any(v in t for v in variants):
            return canon
    return None


def looks_like_toc_page(text: str) -> bool:
    """
    Heuristic to detect if a page contains a table of contents.
    
    Args:
        text: Full text of the page
        
    Returns:
        True if page likely contains TOC
    """
    text_lower = text.lower()
    
    # Direct mention
    if "table of contents" in text_lower:
        return True
    
    # Check for TOC-like patterns (multiple lines with page numbers at end or standalone)
    lines = text.splitlines()
    page_num_lines = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        # Check if line ends with page numbers
        if re.search(rf"{PAGE_NUM_END}", stripped):
            page_num_lines += 1
        # Check if line is ONLY page numbers (separate line format)
        elif re.match(rf"^{PAGE_NUM_STANDALONE}$", stripped):
            page_num_lines += 1
    
    # If >5 lines have page numbers, likely a TOC
    if page_num_lines > 5:
        return True
    
    return False

