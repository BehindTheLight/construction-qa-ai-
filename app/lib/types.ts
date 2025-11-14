export type Citation = {
  doc_id: string;
  page_number: number;
  snippet?: string;
  bbox?: number[];
};

export type QuerySuggestion = {
  query: string;
  preview: string;
  citation_count: number;
  cached_answer?: string;  // Full answer from testing
  cached_citations?: Citation[];  // Full citations from testing
};

export type QAResponse = {
  answer: string;
  citations: Citation[];
  suggestions?: QuerySuggestion[] | null;
};

export type SearchChunk = {
  chunk_id: string;
  doc_id: string;
  project_id: string;
  page_number: number;
  section?: string | null;
  text: string;
  bbox?: number[] | null;
  source?: string | null;
  confidence?: number | null;
  score: number;
};

export type Message = {
  role: "user" | "assistant";
  content: string;
  citations?: Citation[];
  suggestions?: QuerySuggestion[] | null;
  created_at?: string;
};

export type Convo = {
  convo_id: string;
  project_id: string;
  title?: string;
  created_at: string;
};


