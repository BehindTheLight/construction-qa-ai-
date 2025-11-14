ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source TEXT;         -- "text" | "ocr" | "drawing_ocr"
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS confidence REAL;      -- average OCR confidence if applicable
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);


