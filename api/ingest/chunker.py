from typing import List, Dict, Any
import uuid

def chunk_pages(doc_id: str, project_id: str, doc_type: str, discipline: str, pages: List[Dict[str, Any]], max_chars: int = 1200) -> List[Dict[str, Any]]:
    """
    Greedy chunk by page blocks; keep bbox per block (first block bbox if merged).
    Now tracks source (text|ocr) and confidence for OCR pages.
    """
    chunks = []
    for p in pages:
        page_no = p["page_number"]
        is_ocr = p["is_scanned"]
        
        if is_ocr and not p["blocks"]:
            # No OCR results; skip
            continue

        cur_text, cur_bbox, confs = "", None, []
        for b in p["blocks"]:
            t = (b.get("text") or "").strip()
            if not t:
                continue
            if not cur_bbox:
                cur_bbox = b["bbox"]

            if len(cur_text) + len(t) + 1 <= max_chars:
                cur_text = (cur_text + "\n" + t) if cur_text else t
                # expand bbox to include this block
                x0,y0,x1,y1 = cur_bbox
                bx0,by0,bx1,by1 = b["bbox"]
                cur_bbox = [min(x0,bx0), min(y0,by0), max(x1,bx1), max(y1,by1)]
                # collect confidence if available
                if "confidence" in b and b["confidence"] is not None:
                    confs.append(b["confidence"])
            else:
                # Save current chunk
                chunks.append({
                    "chunk_id": str(uuid.uuid4()),
                    "doc_id": doc_id,
                    "project_id": project_id,
                    "doc_type": doc_type,
                    "discipline": discipline,
                    "page_number": page_no,
                    "section": None,
                    "text": cur_text,
                    "bbox": cur_bbox,
                    "source": "ocr" if is_ocr else "text",
                    "confidence": (sum(confs)/len(confs)) if confs else None
                })
                # reset
                cur_text, cur_bbox, confs = t, b["bbox"], ([b["confidence"]] if b.get("confidence") else [])

        if cur_text:
            chunks.append({
                "chunk_id": str(uuid.uuid4()),
                "doc_id": doc_id,
                "project_id": project_id,
                "doc_type": doc_type,
                "discipline": discipline,
                "page_number": page_no,
                "section": None,
                "text": cur_text,
                "bbox": cur_bbox,
                "source": "ocr" if is_ocr else "text",
                "confidence": (sum(confs)/len(confs)) if confs else None
            })
    return chunks

