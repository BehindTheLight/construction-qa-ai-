"use client";

import { useEffect, useRef, useState } from "react";

type Rect = [number, number, number, number]; // [x1,y1,x2,y2] in PDF points (72dpi)

interface PDFViewerProps {
  docId: string;
  pageNum: number;
  rects: Rect[];
}

export default function PDFViewer({ docId, pageNum, rects }: PDFViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(0.5);
  const [viewportH, setViewportH] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [totalPages, setTotalPages] = useState(0);
  const [showHighlights, setShowHighlights] = useState(true);

  useEffect(() => {
    // Extra safety: only run in browser
    if (typeof window === "undefined") {
      return;
    }

    let mounted = true;

    const loadPDF = async () => {
      try {
        setLoading(true);
        setError(null);

        console.log("[PDFViewer] Starting PDF load for doc:", docId);

        // Dynamically import PDF.js only on client side (v3.11.174 - stable with Next.js)
        const pdfjsLib = await import("pdfjs-dist");
        console.log("[PDFViewer] PDF.js library loaded");
        
        // Set worker source - use local worker file from public directory
        (pdfjsLib as any).GlobalWorkerOptions.workerSrc = "/pdf.worker.js";
        console.log("[PDFViewer] Worker source set to /pdf.worker.js");

        const url = `${process.env.NEXT_PUBLIC_API_BASE}/documents/${docId}/file`;
        console.log("[PDFViewer] Loading PDF from:", url);
        
        const loadingTask = (pdfjsLib as any).getDocument({
          url: url,
          withCredentials: false,
        });
        
        console.log("[PDFViewer] Waiting for PDF document...");
        
        // Add timeout to prevent hanging forever
        const timeoutPromise = new Promise((_, reject) => 
          setTimeout(() => reject(new Error("PDF loading timeout (30s)")), 30000)
        );
        
        const pdf = await Promise.race([loadingTask.promise, timeoutPromise]);
        console.log("[PDFViewer] PDF loaded successfully, pages:", (pdf as any).numPages);
        
        if (!mounted) {
          console.log("[PDFViewer] Component unmounted, aborting");
          return;
        }
        
        setTotalPages((pdf as any).numPages);
        console.log("[PDFViewer] Total pages set, loading page", pageNum);
        
        const page = await (pdf as any).getPage(pageNum);
        console.log("[PDFViewer] Page loaded:", pageNum);
        
        if (!mounted) {
          console.log("[PDFViewer] Component unmounted after page load, aborting");
          return;
        }

        const viewport = page.getViewport({ scale });
        setViewportH(viewport.height);
        console.log("[PDFViewer] Viewport configured:", viewport.width, "x", viewport.height);

        const canvas = canvasRef.current;
        if (!canvas) {
          console.error("[PDFViewer] Canvas ref is null!");
          throw new Error("Canvas element not found");
        }
        
        const ctx = canvas.getContext("2d");
        if (!ctx) {
          console.error("[PDFViewer] Cannot get 2D context!");
          throw new Error("Cannot get canvas 2D context");
        }
        
        canvas.width = viewport.width;
        canvas.height = viewport.height;
        console.log("[PDFViewer] Canvas sized, starting render...");

        // Render page
        const renderContext = { canvasContext: ctx, viewport };
        await page.render(renderContext).promise;
        console.log("[PDFViewer] Page rendered successfully!");

        if (!mounted) {
          console.log("[PDFViewer] Component unmounted after render, aborting");
          return;
        }

        // Draw highlights
        const overlay = containerRef.current;
        if (!overlay) {
          console.log("[PDFViewer] ⚠️ Overlay ref is null!");
          return;
        }
        
        // Clear previous highlights
        overlay.querySelectorAll(".hl").forEach(el => el.remove());

        // Only draw highlights if showHighlights is true
        if (showHighlights && rects.length > 0) {
          console.log("[PDFViewer] Drawing", rects.length, "highlights");
          console.log("[PDFViewer] Viewport height:", viewport.height, "Scale:", scale);

          rects.forEach((r, idx) => {
            const [x1, y1, x2, y2] = r;
            console.log(`[PDFViewer] Rect ${idx}: PDF coords [${x1}, ${y1}, ${x2}, ${y2}]`);
            
            const rx = x1 * scale;
            // Use y1 directly without flipping (bbox is already in correct orientation)
            const ry_canvas_top = y1 * scale;
            const rw = (x2 - x1) * scale;
            const rh = (y2 - y1) * scale;
            
            console.log(`[PDFViewer] Rect ${idx}: Canvas position (${rx.toFixed(1)}, ${ry_canvas_top.toFixed(1)}) size (${rw.toFixed(1)} x ${rh.toFixed(1)})`);
            
            const div = document.createElement("div");
            div.className = "hl";
            div.style.position = "absolute";
            div.style.left = `${rx}px`;
            div.style.top = `${ry_canvas_top}px`;
            div.style.width = `${rw}px`;
            div.style.height = `${rh}px`;
            div.style.border = "2px solid #22c55e";
            div.style.background = "rgba(34,197,94,0.18)";
            div.style.borderRadius = "4px";
            div.style.pointerEvents = "none";
            div.style.zIndex = "10"; // Ensure it's above the canvas
            overlay.appendChild(div);
          });
        } else {
          console.log("[PDFViewer] Highlights disabled or no rects, skipping drawing");
        }
        
        console.log("[PDFViewer] Highlights appended to overlay, checking overlay dimensions...");
        console.log("[PDFViewer] Overlay computed style:", {
          width: overlay.style.width,
          height: overlay.style.height,
          position: window.getComputedStyle(overlay).position
        });
        
        console.log("[PDFViewer] Setting loading to false");
        setLoading(false);
        console.log("[PDFViewer] ✅ All done!");
      } catch (err: any) {
        console.error("[PDFViewer] ❌ Error during PDF loading:", err);
        console.error("[PDFViewer] Error stack:", err.stack);
        if (mounted) {
          setError(err.message || "Failed to load PDF");
          setLoading(false);
        }
      }
    };

    console.log("[PDFViewer] useEffect triggered, calling loadPDF()");
    loadPDF();

    return () => {
      mounted = false;
    };
  }, [docId, pageNum, rects, scale, showHighlights]);

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <div className="bg-white border-b px-4 py-3 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <div className="text-sm font-medium">
            Document: <span className="font-mono text-blue-600">{docId}</span>
          </div>
          <div className="text-sm text-gray-600">
            Page {pageNum} {totalPages > 0 && `of ${totalPages}`}
          </div>
        </div>
        
        {/* Zoom Controls */}
        <div className="flex items-center gap-2">
          <button
            className="px-3 py-1 border rounded hover:bg-gray-50 text-sm font-medium disabled:opacity-50"
            onClick={() => setScale(s => Math.max(s - 0.25, 0.5))}
            disabled={loading}
          >
            −
          </button>
          <span className="text-sm text-gray-600 min-w-16 text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            className="px-3 py-1 border rounded hover:bg-gray-50 text-sm font-medium disabled:opacity-50"
            onClick={() => setScale(s => Math.min(s + 0.25, 3))}
            disabled={loading}
          >
            +
          </button>
          <button
            className="ml-2 px-3 py-1 border rounded hover:bg-gray-50 text-sm font-medium disabled:opacity-50"
            onClick={() => setScale(0.5)}
            disabled={loading}
          >
            Reset
          </button>
          
          {/* Highlight Toggle */}
          {rects.length > 0 && (
            <button
              className={`ml-4 px-3 py-1 border rounded text-sm font-medium disabled:opacity-50 transition-colors ${
                showHighlights 
                  ? 'bg-green-600 text-white hover:bg-green-700 border-green-600' 
                  : 'bg-gray-100 text-gray-700 hover:bg-gray-200'
              }`}
              onClick={() => setShowHighlights(!showHighlights)}
              disabled={loading}
            >
              {showHighlights ? '✓ Highlights' : 'Highlights'}
            </button>
          )}
        </div>
      </div>

      {/* PDF Viewer */}
      <div className="p-8 flex justify-center">
        {/* Loading Overlay */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mb-4"></div>
            <div className="text-gray-600">Loading PDF...</div>
          </div>
        )}

        {/* Error Display */}
        {error && !loading && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-6 max-w-md">
            <h3 className="text-red-800 font-semibold mb-2">Error Loading PDF</h3>
            <p className="text-red-600 text-sm">{error}</p>
          </div>
        )}

        {/* Canvas - Always rendered but hidden while loading */}
        <div 
          className="bg-white shadow-lg rounded-lg overflow-hidden"
          style={{ display: loading || error ? 'none' : 'block' }}
        >
          <div className="relative inline-block" style={{ lineHeight: 0 }}>
            {/* overlay for highlights */}
            <div 
              ref={containerRef} 
              className="absolute left-0 top-0 pointer-events-none" 
              style={{ width: "100%", height: viewportH }} 
            />
            <canvas ref={canvasRef} />
          </div>
        </div>
      </div>

      {/* Footer */}
      {rects.length > 0 && !loading && !error && (
        <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 bg-green-600 text-white px-4 py-2 rounded-full shadow-lg text-sm">
          {rects.length} highlight{rects.length > 1 ? "s" : ""} shown
        </div>
      )}
    </div>
  );
}

