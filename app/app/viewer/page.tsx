"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";
import dynamic from "next/dynamic";

// Dynamically import the PDF viewer with no SSR
const PDFViewer = dynamic(() => import("@/components/PDFViewer"), {
  ssr: false,
  loading: () => (
    <div className="flex items-center justify-center h-screen bg-gray-100">
      <div className="text-center">
        <div className="inline-block w-8 h-8 border-4 border-blue-600 border-t-transparent rounded-full animate-spin mb-4"></div>
        <div className="text-gray-600">Loading viewer...</div>
      </div>
    </div>
  ),
});

type Rect = [number, number, number, number]; // [x1,y1,x2,y2] in PDF points (72dpi)

function parseRects(s: string | null): Rect[] {
  if (!s) return [];
  // supports "x1,y1,x2,y2" or multiple rects joined by ';'
  return s.split(";").map(seg => seg.split(",").map(Number) as Rect);
}

export default function ViewerPage() {
  const sp = useSearchParams();
  const docId = sp.get("doc_id");
  const pageNum = Number(sp.get("page") || "1");
  const bboxParam = sp.get("bbox"); // single bbox: "x1,y1,x2,y2"
  const bboxesParam = sp.get("bboxes"); // multiple: "x1,y1,x2,y2;...;..."
  
  const rects = useMemo(() => {
    const multi = parseRects(bboxesParam);
    if (multi.length) return multi;
    const single = parseRects(bboxParam);
    return single.length ? single : [];
  }, [bboxParam, bboxesParam]);

  if (!docId) {
    return (
      <div className="flex items-center justify-center h-screen bg-gray-100">
        <div className="text-center">
          <h2 className="text-xl font-semibold text-red-600 mb-2">No Document</h2>
          <p className="text-gray-600">No document ID provided in URL</p>
          <p className="text-sm text-gray-500 mt-2">
            URL should include: ?doc_id=...&page=1
          </p>
        </div>
      </div>
    );
  }

  return <PDFViewer docId={docId} pageNum={pageNum} rects={rects} />;
}

