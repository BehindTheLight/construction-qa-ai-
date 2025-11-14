import { Message, Citation, QuerySuggestion } from "@/lib/types";
import { useState } from "react";

interface CitationsProps {
  citations: Citation[];
}

function buildViewerUrl(doc_id: string, page: number, bbox?: number[]): string {
  const base = `/viewer?doc_id=${encodeURIComponent(doc_id)}&page=${page}`;
  if (bbox && bbox.length === 4) {
    return `${base}&bbox=${bbox.join(",")}`;
  }
  return base;
}

// Extract page numbers mentioned in text (e.g., "pages 10-12", "page 5", "p.3")
function extractPageNumbers(text: string): number[] {
  const pages = new Set<number>();
  
  // Pattern 1: "pages 10-12" or "page 10-12"
  const rangePattern = /pages?\s+(\d+)\s*[-–]\s*(\d+)/gi;
  let match;
  while ((match = rangePattern.exec(text)) !== null) {
    const start = parseInt(match[1]);
    const end = parseInt(match[2]);
    for (let i = start; i <= Math.min(end, start + 10); i++) { // Limit to 10 pages max
      pages.add(i);
    }
  }
  
  // Pattern 2: "page 5", "p.5", "pg 3"
  const singlePattern = /(?:page|pages|p\.|pg)\s*(\d+)/gi;
  while ((match = singlePattern.exec(text)) !== null) {
    const pageNum = parseInt(match[1]);
    if (pageNum >= 1 && pageNum <= 9999) { // Reasonable page range
      pages.add(pageNum);
    }
  }
  
  return Array.from(pages).sort((a, b) => a - b);
}

function Citations({ citations }: CitationsProps) {
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  if (!citations?.length) return null;

  return (
    <div className="mt-3 flex flex-wrap gap-2">
      {citations.map((c, i) => (
        <div key={i} className="relative">
          <a
            className="inline-flex items-center gap-1 text-xs px-3 py-1.5 bg-gray-100 text-gray-700 rounded-full hover:bg-gray-200 transition-colors"
            href={buildViewerUrl(c.doc_id, c.page_number, c.bbox)}
            target="_blank"
            rel="noopener noreferrer"
            onMouseEnter={() => setHoveredIndex(i)}
            onMouseLeave={() => setHoveredIndex(null)}
          >
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
            <span>
              p.{c.page_number} · {c.doc_id.slice(4, 12)}
            </span>
          </a>
          
          {/* Tooltip on hover */}
          {hoveredIndex === i && c.snippet && (
            <div className="absolute bottom-full left-1/2 transform -translate-x-1/2 mb-2 px-3 py-2 bg-gray-900 text-white text-xs rounded-lg shadow-lg max-w-xs z-50 pointer-events-none">
              <div className="whitespace-normal">{c.snippet}</div>
              {/* Arrow */}
              <div className="absolute top-full left-1/2 transform -translate-x-1/2 -mt-1">
                <div className="border-4 border-transparent border-t-gray-900"></div>
              </div>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}

interface SuggestedPagesProps {
  answerText: string;
  docId?: string;
}

function SuggestedPages({ answerText, docId }: SuggestedPagesProps) {
  const pageNumbers = extractPageNumbers(answerText);
  
  // Only show if we have pages and a doc_id to link to
  if (!pageNumbers.length || !docId) return null;
  
  return (
    <div className="mt-3 pt-3 border-t border-gray-200">
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-gray-500 font-medium">Mentioned Pages:</span>
        {pageNumbers.map((pageNum) => (
          <a
            key={pageNum}
            href={buildViewerUrl(docId, pageNum)}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 text-xs px-2.5 py-1 bg-blue-50 text-blue-700 rounded-md hover:bg-blue-100 transition-colors border border-blue-200"
          >
            <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M13 7l5 5m0 0l-5 5m5-5H6"
              />
            </svg>
            <span>Go to p.{pageNum}</span>
          </a>
        ))}
      </div>
    </div>
  );
}

interface QuerySuggestionsProps {
  suggestions: QuerySuggestion[];
  onSuggestionClick: (query: string, cachedAnswer?: string, cachedCitations?: Citation[]) => void;
}

function QuerySuggestions({ suggestions, onSuggestionClick }: QuerySuggestionsProps) {
  if (!suggestions?.length) return null;

  return (
    <div className="mt-4 pt-4 border-t border-gray-200">
      <div className="flex items-start gap-2 mb-2">
        <svg className="w-4 h-4 text-blue-500 mt-0.5 flex-shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
        <div className="flex-1">
          <p className="text-xs text-gray-600 font-medium mb-2">
            Try rephrasing your question:
          </p>
          <div className="flex flex-col gap-2">
            {suggestions.map((suggestion, i) => (
              <button
                key={i}
                onClick={() => onSuggestionClick(
                  suggestion.query, 
                  suggestion.cached_answer, 
                  suggestion.cached_citations
                )}
                className="text-left p-3 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-colors group"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="flex-1">
                    <p className="text-sm text-blue-900 font-medium mb-1 group-hover:text-blue-700">
                      {suggestion.query}
                    </p>
                    <p className="text-xs text-gray-600 line-clamp-2">
                      {suggestion.preview}
                    </p>
                  </div>
                  <svg className="w-4 h-4 text-blue-500 flex-shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 7l5 5m0 0l-5 5m5-5H6" />
                  </svg>
                </div>
              </button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

interface MessageViewProps {
  message: Message;
  onSuggestionClick?: (query: string, cachedAnswer?: string, cachedCitations?: Citation[]) => void;
}

export default function MessageView({ message, onSuggestionClick }: MessageViewProps) {
  const isUser = message.role === "user";
  
  // Get doc_id from first citation (if available) for suggested pages
  const docId = message.citations?.[0]?.doc_id;

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"} w-full mb-4`}>
      <div
        className={`max-w-[80%] rounded-2xl px-5 py-3 ${
          isUser
            ? "bg-blue-600 text-white ml-auto"
            : "bg-white shadow-sm border border-gray-200"
        }`}
      >
        <div className="whitespace-pre-wrap break-words">{message.content}</div>
        {!isUser && message.citations && (
          <Citations citations={message.citations} />
        )}
        {!isUser && (
          <SuggestedPages answerText={message.content} docId={docId} />
        )}
        {!isUser && message.suggestions && onSuggestionClick && (
          <QuerySuggestions suggestions={message.suggestions} onSuggestionClick={onSuggestionClick} />
        )}
      </div>
    </div>
  );
}

