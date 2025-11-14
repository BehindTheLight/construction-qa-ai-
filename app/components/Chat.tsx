"use client";
import { useEffect, useRef, useState } from "react";
import { qa, qaStream, addMessage, getMessages } from "@/lib/api";
import MessageView from "./Message";
import { Message } from "@/lib/types";

interface ChatProps {
  projectId: string;
  convoId: string;
  onMessageSent?: () => void;
}

export default function Chat({ projectId, convoId, onMessageSent }: ChatProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [streamingStatus, setStreamingStatus] = useState<string>("");
  const [streamingContent, setStreamingContent] = useState<string>("");
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const listRef = useRef<HTMLDivElement>(null);

  async function loadHistory() {
    try {
      const hist = await getMessages(convoId);
      setMessages(hist);
    } catch (error) {
      console.error("Failed to load messages:", error);
    }
  }

  useEffect(() => {
    if (convoId) {
      setMessages([]);
      loadHistory();
    }
  }, [convoId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    // Auto-scroll during streaming
    if (streamingContent) {
      messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
    }
  }, [streamingContent]);

  async function sendQuery(question: string) {
    if (loading) return;

    setLoading(true);
    setStreamingStatus("");
    setStreamingContent("");

    // Add user message
    const userMsg: Message = { role: "user", content: question };
    setMessages((prev) => [...prev, userMsg]);

    try {
      // Save user message
      await addMessage(convoId, userMsg);
      
      // Notify parent to refresh conversation list (for auto-naming)
      onMessageSent?.();

      // Use streaming API for real-time updates
      await qaStream(
        question,
        projectId,
        {
          onStatus: (status) => {
            setStreamingStatus(status);
          },
          onChunk: (chunk) => {
            setStreamingContent((prev) => prev + chunk);
          },
          onDone: async (answer, citations, suggestions) => {
            // Clear streaming state
            setStreamingStatus("");
            setStreamingContent("");
            
            // Add final assistant message
            const assistantMsg: Message = {
              role: "assistant",
              content: answer,
              citations: citations,
              suggestions: suggestions,
            };
            setMessages((prev) => [...prev, assistantMsg]);

            // Save assistant message
            await addMessage(convoId, assistantMsg);
          },
          onError: (error) => {
            console.error("Streaming error:", error);
            setStreamingStatus("");
            setStreamingContent("");
            setMessages((prev) => [
              ...prev,
              {
                role: "assistant",
                content: `Sorry, an error occurred: ${error}`,
                citations: [],
              },
            ]);
          },
        }
      );
    } catch (error) {
      console.error("Failed to send message:", error);
      setStreamingStatus("");
      setStreamingContent("");
      // Add error message
      setMessages((prev) => [
        ...prev,
        {
          role: "assistant",
          content: "Sorry, something went wrong. Please try again.",
          citations: [],
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  async function send() {
    if (!input.trim() || loading) return;

    const question = input.trim();
    setInput("");
    await sendQuery(question);
  }

  function handleSuggestionClick(query: string, cachedAnswer?: string, cachedCitations?: any[]) {
    if (loading) return;

    // If we have cached results, use them instantly!
    if (cachedAnswer && cachedCitations) {
      // Add user message
      const userMsg: Message = { role: "user", content: query };
      setMessages((prev) => [...prev, userMsg]);

      // Add cached assistant response immediately (no API call!)
      const assistantMsg: Message = {
        role: "assistant",
        content: cachedAnswer,
        citations: cachedCitations,
      };
      setMessages((prev) => [...prev, assistantMsg]);

      // Save both messages to history
      (async () => {
        try {
          await addMessage(convoId, userMsg);
          await addMessage(convoId, assistantMsg);
          onMessageSent?.();
        } catch (error) {
          console.error("Failed to save cached suggestion:", error);
        }
      })();
    } else {
      // Fallback: send query normally if no cache
      sendQuery(query);
    }
  }

  return (
    <div className="flex flex-col flex-1 min-h-0 bg-gray-50">
      {/* Messages Container */}
      <div ref={listRef} className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto">
          {messages.length === 0 ? (
            <div className="text-center text-gray-400 mt-20">
              <h2 className="text-2xl font-semibold mb-2">
                Ask anything about your construction documents
              </h2>
              <p className="text-sm">
                Get instant answers with citations to specific pages and sections
              </p>
            </div>
          ) : (
            <>
              {messages.map((msg, i) => (
                <MessageView key={i} message={msg} onSuggestionClick={handleSuggestionClick} />
              ))}
              {loading && (
                <div className="flex justify-start w-full mb-4">
                  <div className="bg-white shadow-sm border border-gray-200 rounded-2xl px-5 py-3 max-w-2xl">
                    {streamingStatus && !streamingContent && (
                      <div className="flex items-center gap-2 text-sm text-gray-500 mb-2">
                        <div className="w-2 h-2 bg-blue-400 rounded-full animate-pulse"></div>
                        {streamingStatus}
                      </div>
                    )}
                    {streamingContent ? (
                      <div className="text-gray-800">
                        {streamingContent}
                        <span className="inline-block w-1.5 h-4 bg-blue-500 ml-1 animate-pulse"></span>
                      </div>
                    ) : (
                      <div className="flex items-center gap-2 text-gray-500">
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "0ms" }}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "150ms" }}></div>
                        <div className="w-2 h-2 bg-gray-400 rounded-full animate-bounce" style={{ animationDelay: "300ms" }}></div>
                      </div>
                    )}
                  </div>
                </div>
              )}
              <div ref={messagesEndRef} />
            </>
          )}
        </div>
      </div>

      {/* Input Area - stays at bottom */}
      <div className="border-t bg-white p-4 flex-shrink-0">
        <div className="max-w-3xl mx-auto flex gap-3">
          <input
            className="flex-1 border border-gray-300 rounded-xl px-4 py-3 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            placeholder="Ask about permits, inspections, specs, requirements..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && input.trim()) {
                e.preventDefault();
                send();
              }
            }}
            disabled={loading}
          />
          <button
            className="px-6 py-3 rounded-xl bg-blue-600 text-white font-medium hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            disabled={!input.trim() || loading}
            onClick={send}
          >
            {loading ? "Sending..." : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}

