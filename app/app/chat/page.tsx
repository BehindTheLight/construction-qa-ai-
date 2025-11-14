"use client";
import { useState, useRef, useEffect } from "react";
import Sidebar from "@/components/Sidebar";
import Chat from "@/components/Chat";
import LoadingWrapper from "@/components/LoadingWrapper";
import NotificationBell from "@/components/NotificationBell";
import { Convo } from "@/lib/types";
import { listProjects } from "@/lib/api";
import { useRouter } from "next/navigation";
import { LayoutDashboard } from "lucide-react";

export default function ChatPage() {
  const router = useRouter();
  const [projectId, setProjectId] = useState("windsor_1032_california");
  const [convo, setConvo] = useState<Convo | null>(null);
  const [projects, setProjects] = useState<any[]>([]);
  const [loadingProjects, setLoadingProjects] = useState(true);
  const refreshConvosRef = useRef<() => void>();

  // Load projects dynamically
  useEffect(() => {
    const loadProjects = async () => {
      try {
        const data = await listProjects();
        setProjects(data.projects || []);
        
        // If current projectId doesn't exist, use the first available project
        if (data.projects.length > 0) {
          const projectExists = data.projects.some((p: any) => p.project_id === projectId);
          if (!projectExists) {
            setProjectId(data.projects[0].project_id);
          }
        }
      } catch (error) {
        console.error("Failed to load projects:", error);
      } finally {
        setLoadingProjects(false);
      }
    };

    loadProjects();
  }, []);

  const getProjectDisplayName = (project: any) => {
    // Convert project_id to readable name
    if (project.project_id === "demo_project") return "Demo Project";
    
    // Extract readable name from project_id (e.g., windsor_1032_california -> 1032 CALIFORNIA)
    const parts = project.project_id.split("_");
    if (parts[0] === "windsor" && parts.length > 1) {
      return parts.slice(1).map((p: string) => p.toUpperCase()).join(" ");
    }
    
    return project.project_id;
  };

  return (
    <LoadingWrapper>
      <div className="flex h-screen overflow-hidden">
      {/* Sidebar */}
      <Sidebar
        projectId={projectId}
        currentConvoId={convo?.convo_id}
        onSelect={setConvo}
        refreshConvosRef={refreshConvosRef}
      />

      {/* Main Chat Area */}
      <div className="flex-1 flex flex-col min-h-0">
        {/* Project Selector Header */}
        <div className="border-b bg-white px-6 py-3 flex items-center gap-3">
          <label className="text-sm font-medium text-gray-700">Project:</label>
          <select
            className="border border-gray-300 rounded-lg px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
            value={projectId}
            onChange={(e) => setProjectId(e.target.value)}
            disabled={loadingProjects}
          >
            {loadingProjects ? (
              <option>Loading projects...</option>
            ) : projects.length === 0 ? (
              <option>No projects available</option>
            ) : (
              projects.map((project) => (
                <option key={project.project_id} value={project.project_id}>
                  {getProjectDisplayName(project)} ({project.doc_count})
                </option>
              ))
            )}
          </select>
          <button
            onClick={() => router.push("/dashboard")}
            className="ml-4 flex items-center gap-2 px-3 py-1.5 text-sm bg-gray-100 hover:bg-gray-200 rounded-lg transition"
            title="Go to Dashboard"
          >
            <LayoutDashboard className="w-4 h-4" />
            Dashboard
          </button>
          <div className="ml-auto flex items-center gap-4">
            <NotificationBell />
            <div className="text-xs text-gray-400">
              {convo ? `Conversation: ${convo.title || "Untitled"}` : "No conversation selected"}
            </div>
          </div>
        </div>

        {/* Chat or Empty State */}
        {convo ? (
          <Chat projectId={projectId} convoId={convo.convo_id} onMessageSent={() => refreshConvosRef.current?.()} />
        ) : (
          <div className="flex-1 flex items-center justify-center bg-gray-50">
            <div className="text-center text-gray-400">
              <svg
                className="w-16 h-16 mx-auto mb-4 text-gray-300"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={1.5}
                  d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"
                />
              </svg>
              <h3 className="text-lg font-medium mb-1">Select or create a chat</h3>
              <p className="text-sm">Choose a conversation from the sidebar to get started</p>
            </div>
          </div>
        )}
      </div>
    </div>
    </LoadingWrapper>
  );
}

