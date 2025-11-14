"use client";
import { useState } from "react";
import { search } from "@/lib/api";
import { SearchChunk } from "@/lib/types";
import Link from "next/link";

export default function SearchPage() {
  const [projectId, setProjectId] = useState("demo_project");
  const [query, setQuery] = useState("backfill inspection");
  const [results, setResults] = useState<SearchChunk[]>([]);
  const [loading, setLoading] = useState(false);

  async function handleSearch() {
    if (!query.trim()) return;
    setLoading(true);
    try {
      const data = await search(query, projectId);
      setResults(data);
    } catch (error) {
      console.error("Search failed:", error);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Header */}
      <div className="bg-white border-b px-6 py-4">
        <div className="max-w-4xl mx-auto">
          <div className="flex items-center justify-between mb-4">
            <h1 className="text-xl font-bold">Document Search</h1>
            <Link href="/chat" className="text-blue-600 hover:underline text-sm">
              ← Back to Chat
            </Link>
          </div>

          {/* Search Input */}
          <div className="flex gap-3">
            <select
              className="border border-gray-300 rounded-lg px-3 py-2 text-sm"
              value={projectId}
              onChange={(e) => setProjectId(e.target.value)}
            >
              <option value="demo_project">Demo Project</option>
              <option value="windsor_normalized_bbox">Windsor Sample</option>
            </select>
            <input
              className="flex-1 border border-gray-300 rounded-lg px-4 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
              placeholder="Search documents..."
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            />
            <button
              className="px-6 py-2 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50"
              onClick={handleSearch}
              disabled={loading || !query.trim()}
            >
              {loading ? "Searching..." : "Search"}
            </button>
          </div>
        </div>
      </div>

      {/* Results */}
      <div className="max-w-4xl mx-auto px-6 py-6">
        {loading ? (
          <div className="text-center py-12 text-gray-400">Searching...</div>
        ) : results.length === 0 ? (
          <div className="text-center py-12 text-gray-400">
            No results yet. Try searching for something.
          </div>
        ) : (
          <div className="space-y-4">
            <div className="text-sm text-gray-600 mb-4">
              Found {results.length} results
            </div>
            {results.map((r, i) => (
              <div key={i} className="bg-white rounded-lg shadow-sm border border-gray-200 p-4">
                <div className="flex items-center gap-2 text-xs text-gray-500 mb-2">
                  <span className="font-medium">Page {r.page_number}</span>
                  <span>•</span>
                  <span>{r.doc_id}</span>
                  {r.source && (
                    <>
                      <span>•</span>
                      <span className="px-2 py-0.5 bg-gray-100 rounded">
                        {r.source === "ocr" ? "OCR" : "Native Text"}
                      </span>
                    </>
                  )}
                  {r.confidence && (
                    <>
                      <span>•</span>
                      <span>Confidence: {Math.round(r.confidence)}%</span>
                    </>
                  )}
                  <span className="ml-auto font-semibold">
                    Score: {r.score.toFixed(2)}
                  </span>
                </div>
                <div className="text-sm text-gray-700 whitespace-pre-wrap">
                  {r.text.length > 400 ? r.text.slice(0, 400) + "..." : r.text}
                </div>
                {r.section && (
                  <div className="mt-2 text-xs text-gray-500">
                    Section: {r.section}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}


