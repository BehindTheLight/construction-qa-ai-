from typing import List, Dict, Any, Tuple
import fitz
import numpy as np
import cv2
import pytesseract
from PIL import Image

# Coordinate normalization: OCR renders at 300 DPI, but we store in PDF points (72 DPI)
OCR_RENDER_DPI = 300
PDF_DPI = 72.0
BBOX_SCALE = PDF_DPI / OCR_RENDER_DPI  # 0.24

def render_page_image(doc: fitz.Document, page_index: int, dpi: int = OCR_RENDER_DPI) -> Image.Image:
    """Render a PDF page as an image at the specified DPI."""
    page = doc.load_page(page_index)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
    return img

def preprocess_for_ocr(pil_img: Image.Image) -> np.ndarray:
    """Preprocess image for better OCR results."""
    img = np.array(pil_img)
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    # denoise + adaptive threshold
    gray = cv2.bilateralFilter(gray, 7, 75, 75)
    th = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                               cv2.THRESH_BINARY, 35, 11)
    return th

def tesseract_ocr_blocks(pil_img: Image.Image) -> List[Dict[str, Any]]:
    """
    Run Tesseract OCR on an image and return text blocks with bounding boxes.
    Groups word-level results by line.
    
    Bounding boxes are normalized to PDF coordinate space (72 DPI) for consistency
    with native PDF text blocks.
    """
    th = preprocess_for_ocr(pil_img)
    # Tesseract returns a TSV with word-level boxes; we group by line
    data = pytesseract.image_to_data(th, output_type=pytesseract.Output.DICT, lang="eng")
    n = len(data["text"])
    lines: Dict[int, List[int]] = {}
    
    for i in range(n):
        if int(data["conf"][i]) < 0:
            continue
        # Create a unique line identifier
        ln = data["line_num"][i] + 1000 * data["block_num"][i] + 100000 * data["page_num"][i]
        lines.setdefault(ln, []).append(i)

    blocks = []
    for ln, idxs in lines.items():
        texts = [data["text"][i] for i in idxs if data["text"][i].strip()]
        if not texts:
            continue
        
        # Calculate bounding box for the line (in pixel coordinates)
        x0 = min(data["left"][i] for i in idxs)
        y0 = min(data["top"][i] for i in idxs)
        x1 = max(data["left"][i] + data["width"][i] for i in idxs)
        y1 = max(data["top"][i] + data["height"][i] for i in idxs)
        
        # Normalize to PDF coordinate space (72 DPI)
        # OCR was done at 300 DPI, so scale down by 72/300 = 0.24
        bbox_normalized = [
            float(x0 * BBOX_SCALE),
            float(y0 * BBOX_SCALE),
            float(x1 * BBOX_SCALE),
            float(y1 * BBOX_SCALE)
        ]
        
        # Calculate average confidence for the line
        confs = [int(data["conf"][i]) for i in idxs if int(data["conf"][i]) >= 0]
        avg_conf = float(sum(confs)/len(confs)) if confs else None
        
        blocks.append({
            "text": " ".join(texts),
            "bbox": bbox_normalized,  # now in PDF points (72 DPI)
            "confidence": avg_conf
        })
    
    return blocks

