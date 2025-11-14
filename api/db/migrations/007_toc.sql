-- Add table of contents entries for TOC-aware retrieval

CREATE TABLE IF NOT EXISTS toc_entries (
  toc_id TEXT PRIMARY KEY,
  doc_id TEXT NOT NULL,
  title TEXT NOT NULL,
  page_start INT NOT NULL,
  page_end INT NOT NULL,
  confidence REAL,
  raw_line TEXT,
  UNIQUE(doc_id, title, page_start, page_end)
);

CREATE INDEX IF NOT EXISTS idx_toc_doc ON toc_entries(doc_id, page_start, page_end);


