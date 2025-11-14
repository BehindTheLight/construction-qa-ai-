"use client";
import { useEffect, useState } from "react";
import { listConvos, createConvo, deleteConvo } from "@/lib/api";
import { Convo } from "@/lib/types";

interface SidebarProps {
  projectId: string;
  currentConvoId?: string;
  onSelect: (convo: Convo) => void;
  refreshConvosRef?: React.MutableRefObject<(() => void) | undefined>;
}

export default function Sidebar({ projectId, currentConvoId, onSelect, refreshConvosRef }: SidebarProps) {
  const [convos, setConvos] = useState<Convo[]>([]);
  const [loading, setLoading] = useState(false);

  async function refresh() {
    setLoading(true);
    try {
      const data = await listConvos(projectId);
      setConvos(data);
    } catch (error) {
      console.error("Failed to load conversations:", error);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    if (projectId) {
      refresh();
    }
  }, [projectId]);

  // Expose refresh function to parent via ref
  useEffect(() => {
    if (refreshConvosRef) {
      refreshConvosRef.current = refresh;
    }
  }, [refreshConvosRef, projectId]);

  async function handleNewChat() {
    try {
      const id = await createConvo(projectId, "New chat");
      await refresh();
      const newConvo = convos.find((c) => c.convo_id === id);
      if (newConvo) {
        onSelect(newConvo);
      } else {
        // If not in list yet, create a temp one
        onSelect({ convo_id: id, project_id: projectId, title: "New chat", created_at: new Date().toISOString() });
      }
    } catch (error) {
      console.error("Failed to create conversation:", error);
    }
  }

  async function handleDelete(convoId: string, e: React.MouseEvent) {
    e.stopPropagation(); // Prevent selecting the conversation
    if (!confirm("Delete this conversation?")) return;
    
    try {
      await deleteConvo(convoId);
      await refresh();
      // If the deleted convo was selected, clear selection
      if (currentConvoId === convoId) {
        // Select the first available conversation, or none
        if (convos.length > 1) {
          const remaining = convos.filter(c => c.convo_id !== convoId);
          if (remaining.length > 0) {
            onSelect(remaining[0]);
          }
        }
      }
    } catch (error) {
      console.error("Failed to delete conversation:", error);
    }
  }

  return (
    <div className="w-64 bg-gray-900 text-white h-screen flex flex-col">
      {/* Header */}
      <div className="p-3 border-b border-gray-700">
        <button
          className="w-full py-3 px-4 rounded-lg border border-gray-600 hover:bg-gray-800 transition-colors font-medium text-sm"
          onClick={handleNewChat}
          disabled={loading}
        >
          + New chat
        </button>
      </div>

      {/* Conversations List */}
      <div className="flex-1 overflow-y-auto py-3">
        {loading && convos.length === 0 ? (
          <div className="px-3 py-2 text-gray-400 text-sm">Loading...</div>
        ) : convos.length === 0 ? (
          <div className="px-3 py-2 text-gray-400 text-sm">No conversations yet</div>
        ) : (
          <div className="space-y-1">
            {convos.map((c) => (
              <div
                key={c.convo_id}
                className="relative group mx-2"
              >
                <button
                  className={`w-full text-left px-3 py-3 rounded-lg transition-colors ${
                    currentConvoId === c.convo_id
                      ? "bg-gray-800"
                      : "hover:bg-gray-800"
                  }`}
                  onClick={() => onSelect(c)}
                >
                  <div className="text-sm font-medium truncate pr-8">
                    {c.title || "Untitled"}
                  </div>
                  <div className="text-xs text-gray-400 mt-1">
                    {new Date(c.created_at).toLocaleDateString()}
                  </div>
                </button>
                
                {/* Delete Button - appears on hover */}
                <button
                  className="absolute right-2 top-1/2 -translate-y-1/2 opacity-0 group-hover:opacity-100 transition-opacity p-2 hover:bg-red-600 rounded"
                  onClick={(e) => handleDelete(c.convo_id, e)}
                  title="Delete conversation"
                >
                  <svg 
                    className="w-4 h-4" 
                    fill="none" 
                    viewBox="0 0 24 24" 
                    stroke="currentColor"
                  >
                    <path 
                      strokeLinecap="round" 
                      strokeLinejoin="round" 
                      strokeWidth={2} 
                      d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16" 
                    />
                  </svg>
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Footer */}
      <div className="p-3 border-t border-gray-700">
        <div className="text-xs text-gray-400">
          <div className="font-medium mb-1">Demo — Ask & Cite</div>
          <div>Construction document Q&A</div>
        </div>
      </div>
    </div>
  );
}

