import axios from "axios";
import { API_BASE } from "./env";
import { QAResponse, SearchChunk, Convo, Message } from "./types";

export async function createConvo(project_id: string, title?: string): Promise<string> {
  const { data } = await axios.post(`${API_BASE}/conversations`, { project_id, title });
  return data.convo_id as string;
}

export async function listConvos(project_id: string): Promise<Convo[]> {
  const { data } = await axios.get<Convo[]>(`${API_BASE}/conversations`, {
    params: { project_id },
  });
  return data;
}

export async function getMessages(convo_id: string): Promise<Message[]> {
  const { data} = await axios.get<Message[]>(
    `${API_BASE}/conversations/${convo_id}/messages`
  );
  return data;
}

export async function addMessage(convo_id: string, msg: Message): Promise<void> {
  await axios.post(`${API_BASE}/conversations/${convo_id}/messages`, msg);
}

export async function deleteConvo(convo_id: string): Promise<void> {
  await axios.delete(`${API_BASE}/conversations/${convo_id}`);
}

export async function qa(
  question: string,
  project_id: string,
  doc_type?: string,
  discipline?: string
): Promise<QAResponse> {
  const { data } = await axios.post<QAResponse>(`${API_BASE}/qa`, {
    question,
    project_id,
    doc_type,
    discipline,
    size: 64,
  });
  return data;
}

/**
 * Streaming version of QA that uses Server-Sent Events.
 * Provides real-time updates as the answer is being generated.
 * 
 * @param question User's question
 * @param project_id Project ID to search
 * @param callbacks Object with callbacks for different events
 * @param doc_type Optional document type filter
 * @param discipline Optional discipline filter
 * @returns Promise that resolves when stream completes
 */
export async function qaStream(
  question: string,
  project_id: string,
  callbacks: {
    onStatus?: (message: string) => void;
    onChunk?: (content: string) => void;
    onDone?: (answer: string, citations: any[], suggestions?: any[]) => void;
    onError?: (error: string) => void;
  },
  doc_type?: string,
  discipline?: string
): Promise<void> {
  const response = await fetch(`${API_BASE}/qa/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      question,
      project_id,
      doc_type,
      discipline,
      size: 64,
    }),
  });

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`);
  }

  const reader = response.body?.getReader();
  const decoder = new TextDecoder();

  if (!reader) {
    throw new Error("Response body is not readable");
  }

  try {
    while (true) {
      const { done, value } = await reader.read();
      
      if (done) break;

      // Decode the chunk
      const chunk = decoder.decode(value, { stream: true });
      
      // Split by newlines to handle multiple SSE messages
      const lines = chunk.split("\n");
      
      for (const line of lines) {
        if (line.startsWith("data: ")) {
          const dataStr = line.slice(6); // Remove "data: " prefix
          
          try {
            const data = JSON.parse(dataStr);
            
            // Handle different event types
            switch (data.type) {
              case "status":
                callbacks.onStatus?.(data.message);
                break;
              
              case "chunk":
                callbacks.onChunk?.(data.content);
                break;
              
              case "done":
                callbacks.onDone?.(data.answer, data.citations || [], data.suggestions || []);
                break;
              
              case "error":
                callbacks.onError?.(data.message);
                break;
            }
          } catch (e) {
            // Skip malformed JSON
            console.warn("Failed to parse SSE data:", dataStr, e);
          }
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

export async function search(
  q: string,
  project_id: string,
  doc_type?: string,
  discipline?: string,
  size = 10
): Promise<SearchChunk[]> {
  const { data } = await axios.get<SearchChunk[]>(`${API_BASE}/search`, {
    params: { q, project_id, doc_type, discipline, size },
  });
  return data;
}

export function pdfViewerUrl(doc_id: string, page: number, bbox?: number[]): string {
  // For now, placeholder URL - will be replaced with actual PDF.js viewer
  let base = `${API_BASE}/documents/${doc_id}?page=${page}`;
  if (bbox && bbox.length === 4) {
    base += `&bbox=${bbox.join(",")}`;
  }
  return base;
}

// Dashboard & Admin API Functions
export async function checkHealthStatus(): Promise<any> {
  const { data } = await axios.get(`${API_BASE}/health/status`);
  return data;
}

export async function listProjects(): Promise<any> {
  const { data } = await axios.get(`${API_BASE}/projects/list`);
  return data;
}

export async function uploadPDF(formData: FormData): Promise<any> {
  const { data } = await axios.post(`${API_BASE}/admin/upload-pdf`, formData, {
    headers: {
      "Content-Type": "multipart/form-data",
    },
  });
  return data;
}

export async function getIngestionStatus(jobId: string): Promise<any> {
  const { data } = await axios.get(`${API_BASE}/admin/ingestion-status/${jobId}`);
  return data;
}

export async function listAllDocuments(): Promise<any> {
  const { data } = await axios.get(`${API_BASE}/admin/documents`);
  return data;
}

export async function deleteDocument(docId: string): Promise<any> {
  const { data } = await axios.delete(`${API_BASE}/documents/${docId}`);
  return data;
}

