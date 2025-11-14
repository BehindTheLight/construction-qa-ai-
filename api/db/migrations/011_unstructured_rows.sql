-- Add table rows extracted by Unstructured for structured table data

CREATE TABLE IF NOT EXISTS table_rows (
  row_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number INT NOT NULL,
  table_label TEXT,              -- Optional label/caption for the table
  columns JSONB NOT NULL,         -- Column name -> value mapping
  bbox JSONB,                     -- Bounding box in PDF points [x1, y1, x2, y2]
  source TEXT DEFAULT 'unstructured',
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rows_doc_page ON table_rows(doc_id, page_number);
CREATE INDEX IF NOT EXISTS idx_rows_doc ON table_rows(doc_id);

-- Add source field to chunks to track origin (text, ocr, unstructured)
ALTER TABLE chunks ADD COLUMN IF NOT EXISTS source TEXT DEFAULT 'text';

-- Add index on source for filtering
CREATE INDEX IF NOT EXISTS idx_chunks_source ON chunks(source);


