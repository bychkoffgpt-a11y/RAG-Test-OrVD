CREATE TABLE IF NOT EXISTS documents (
  id BIGSERIAL PRIMARY KEY,
  doc_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  file_name TEXT NOT NULL,
  file_hash TEXT NOT NULL,
  version INTEGER NOT NULL DEFAULT 1,
  status TEXT NOT NULL DEFAULT 'indexed',
  pages INTEGER,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(doc_id, source_type, version)
);

CREATE TABLE IF NOT EXISTS chunks (
  id BIGSERIAL PRIMARY KEY,
  doc_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  chunk_id TEXT NOT NULL,
  page_number INTEGER,
  text_preview TEXT,
  image_paths JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE(chunk_id, source_type)
);

CREATE TABLE IF NOT EXISTS qa_audit (
  id BIGSERIAL PRIMARY KEY,
  request_id TEXT NOT NULL,
  user_question TEXT NOT NULL,
  answer_text TEXT NOT NULL,
  sources JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
