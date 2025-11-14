-- Conversation history tables for chat interface

CREATE TABLE IF NOT EXISTS conversations (
  convo_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  title TEXT,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS messages (
  msg_id TEXT PRIMARY KEY,
  convo_id TEXT NOT NULL REFERENCES conversations(convo_id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user','assistant')),
  content TEXT NOT NULL,
  citations JSONB,
  created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_msgs_convo ON messages(convo_id, created_at);
CREATE INDEX IF NOT EXISTS idx_convos_project ON conversations(project_id, created_at DESC);


