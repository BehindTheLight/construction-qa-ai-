"use client";

import { useEffect, useState, useRef } from "react";

export default function LoadingWrapper({ children }: { children: React.ReactNode }) {
  const [loading, setLoading] = useState(true);
  const [fadeOut, setFadeOut] = useState(false);
  const [apiChecked, setApiChecked] = useState(false);
  const [showWink, setShowWink] = useState(false);
  const hasRunRef = useRef(false);

  useEffect(() => {
    // Check if user has already seen the loading screen in this session
    const hasSeenLoading = sessionStorage.getItem("hasSeenLoading");
    
    console.log("[LoadingWrapper] Has seen loading:", hasSeenLoading);
    
    if (hasSeenLoading === "true") {
      // Skip loading screen if already seen
      console.log("[LoadingWrapper] Skipping loading screen - already seen this session");
      setLoading(false);
      return;
    }

    // Prevent double execution in React StrictMode
    if (hasRunRef.current) {
      console.log("[LoadingWrapper] Already started animation, skipping duplicate");
      return;
    }
    hasRunRef.current = true;

    console.log("[LoadingWrapper] Showing loading screen...");
    // Mark as seen for this session
    sessionStorage.setItem("hasSeenLoading", "true");

    // Step 1: Check API after 1 second
    const apiTimer = setTimeout(() => {
      console.log("[LoadingWrapper] Step 1: API checked ✓");
      setApiChecked(true);
    }, 1000);

    // Step 2: Show wink after 1.5 seconds
    const winkTimer = setTimeout(() => {
      console.log("[LoadingWrapper] Step 2: Showing wink ;)");
      setShowWink(true);
    }, 1500);

    // Step 3: Start fade out after 2.2 seconds
    const fadeTimer = setTimeout(() => {
      console.log("[LoadingWrapper] Step 3: Starting fade out...");
      setFadeOut(true);
    }, 2200);

    // Step 4: Actually hide after fade animation (2.2s + 0.6s fade = 2.8s total)
    const hideTimer = setTimeout(() => {
      console.log("[LoadingWrapper] Step 4: Loading complete, hiding screen");
      setLoading(false);
    }, 2800);

    return () => {
      clearTimeout(apiTimer);
      clearTimeout(winkTimer);
      clearTimeout(fadeTimer);
      clearTimeout(hideTimer);
    };
    // Empty deps array - only run once on mount
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) {
    return (
      <div className={`fixed inset-0 bg-gradient-to-br from-blue-50 to-indigo-100 flex items-center justify-center z-50 transition-opacity duration-600 ${fadeOut ? 'opacity-0' : 'opacity-100'}`}>
        <div className="text-center">
          {/* Logo/Icon with wink animation */}
          <div className="mb-6">
            <div className="w-20 h-20 mx-auto bg-blue-600 rounded-2xl flex items-center justify-center shadow-xl transition-all duration-300">
              {!showWink ? (
                <svg
                  className="w-12 h-12 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
                  />
                </svg>
              ) : (
                /* Wink face ;) */
                <div className="text-white text-3xl font-bold animate-pulse">
                  ;)
                </div>
              )}
            </div>
          </div>

          {/* Title */}
          <h1 className="text-3xl font-bold text-gray-800 mb-2">Demo</h1>
          <p className="text-gray-600 mb-8">Construction Ask & Cite</p>

          {/* API Status Check */}
          <div className="flex items-center justify-center gap-3 mb-4">
            <span className="text-sm text-gray-600">Checking NAGA API status</span>
            {apiChecked ? (
              <svg
                className="w-5 h-5 text-green-600 animate-bounce"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M5 13l4 4L19 7"
                />
              </svg>
            ) : (
              <div className="w-4 h-4 border-2 border-blue-600 border-t-transparent rounded-full animate-spin"></div>
            )}
          </div>

          {/* Status message */}
          {apiChecked && (
            <div className="text-sm text-green-600 font-medium animate-fade-in">
              Model is UP ✓
            </div>
          )}
        </div>
      </div>
    );
  }

  return <>{children}</>;
}

