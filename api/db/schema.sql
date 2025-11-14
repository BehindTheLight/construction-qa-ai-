CREATE TABLE IF NOT EXISTS documents (
  doc_id         TEXT PRIMARY KEY,
  project_id     TEXT NOT NULL,
  title          TEXT NOT NULL,
  doc_type       TEXT NOT NULL,     -- permit | spec | drawing | rfi | submittal
  discipline     TEXT,              -- ARC | STR | MEP | PLUMB | HVAC | GENERAL
  source_path    TEXT NOT NULL,     -- local file path
  checksum       TEXT NOT NULL,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS pages (
  page_id        TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  page_number    INT NOT NULL,
  width          INT,
  height         INT,
  is_scanned     BOOLEAN DEFAULT FALSE,
  ocr_conf       REAL,              -- avg OCR confidence if scanned
  UNIQUE (doc_id, page_number)
);

CREATE TABLE IF NOT EXISTS chunks (
  chunk_id       TEXT PRIMARY KEY,
  doc_id         TEXT NOT NULL REFERENCES documents(doc_id) ON DELETE CASCADE,
  project_id     TEXT NOT NULL,
  page_number    INT NOT NULL,
  section        TEXT,              -- inferred section header / block
  text           TEXT NOT NULL,
  bbox           JSONB,             -- [x1,y1,x2,y2] in page coords; null if not available
  token_count    INT,
  doc_type       TEXT,              -- duplicated for filtering
  discipline     TEXT,
  created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_chunks_doc ON chunks(doc_id, page_number);
CREATE INDEX IF NOT EXISTS idx_chunks_project ON chunks(project_id);
CREATE INDEX IF NOT EXISTS idx_chunks_filters ON chunks(doc_type, discipline);


