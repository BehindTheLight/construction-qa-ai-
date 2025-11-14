-- Add visual_content table for Vision LLM extracted content (drawings, diagrams, complex tables)
CREATE TABLE IF NOT EXISTS visual_content (
  content_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number INT NOT NULL,
  content_type TEXT NOT NULL,  -- 'table', 'drawing', 'form', 'mixed', etc.
  data JSONB NOT NULL,          -- Flexible JSON structure from Vision LLM
  extracted_text TEXT,          -- Flattened text for BM25 search
  vector REAL[],                -- Embeddings for k-NN search (will be set separately)
  source TEXT DEFAULT 'vision_llm',
  confidence REAL,
  error TEXT,                   -- Store errors for debugging
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_visual_doc_page ON visual_content(doc_id, page_number);
CREATE INDEX IF NOT EXISTS idx_visual_type ON visual_content(content_type);
CREATE INDEX IF NOT EXISTS idx_visual_text ON visual_content USING gin(to_tsvector('english', extracted_text));


