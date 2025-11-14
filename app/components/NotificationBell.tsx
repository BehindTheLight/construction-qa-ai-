"use client";
import { useState, useEffect } from "react";
import { Bell, CheckCircle, XCircle, RefreshCw, X } from "lucide-react";
import { checkHealthStatus } from "@/lib/api";

interface Notification {
  id: string;
  type: "ingestion" | "api_status";
  message: string;
  status: "info" | "success" | "error" | "warning";
  timestamp: Date;
  read: boolean;
}

export default function NotificationBell() {
  const [isOpen, setIsOpen] = useState(false);
  const [notifications, setNotifications] = useState<Notification[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);

  // Load notifications from localStorage on mount
  useEffect(() => {
    const loadNotifications = () => {
      const stored = localStorage.getItem("notifications");
      if (stored) {
        try {
          const parsed = JSON.parse(stored);
          // Convert timestamp strings back to Date objects
          const withDates = parsed.map((n: any) => ({
            ...n,
            timestamp: new Date(n.timestamp),
          }));
          setNotifications(withDates);
        } catch (e) {
          console.error("Failed to load notifications:", e);
        }
      }
    };

    // Load on mount
    loadNotifications();

    // Listen for notifications added by other components
    window.addEventListener("notifications-updated", loadNotifications);

    return () => {
      window.removeEventListener("notifications-updated", loadNotifications);
    };
  }, []);

  // Save notifications to localStorage whenever they change
  useEffect(() => {
    if (notifications.length > 0) {
      localStorage.setItem("notifications", JSON.stringify(notifications));
    }
  }, [notifications]);

  // Poll for system status periodically
  useEffect(() => {
    checkSystemHealth();
    const interval = setInterval(checkSystemHealth, 30000); // Every 30 seconds
    return () => clearInterval(interval);
  }, []);

  // Update unread count
  useEffect(() => {
    setUnreadCount(notifications.filter((n) => !n.read).length);
  }, [notifications]);

  async function checkSystemHealth() {
    try {
      const health = await checkHealthStatus();
      
      // Check for offline services with details
      const offlineServices: string[] = [];
      const errorDetails: string[] = [];
      
      Object.entries(health).forEach(([key, value]) => {
        if (key.endsWith("_error") && value) {
          // Extract service name from key (e.g., "opensearch_error" -> "OpenSearch")
          const serviceName = key.replace("_error", "")
            .split("_")
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ");
          errorDetails.push(`${serviceName}: ${value}`);
        } else if (!key.endsWith("_error") && value === "offline") {
          const serviceName = key
            .split("_")
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(" ");
          offlineServices.push(serviceName);
        }
      });

      if (offlineServices.length > 0 || errorDetails.length > 0) {
        let message = "";
        
        if (offlineServices.length > 0) {
          message = `Service offline: ${offlineServices.join(", ")}`;
        }
        
        if (errorDetails.length > 0) {
          if (message) message += " | ";
          message += errorDetails.join("; ");
        }
        
        addNotification({
          type: "api_status",
          message: message,
          status: "error",
        });
      }
    } catch (error) {
      // Main API server is completely unreachable
      addNotification({
        type: "api_status",
        message: "Main API Server unreachable (http://localhost:8000)",
        status: "error",
      });
    }
  }

  function addNotification(params: {
    type: "ingestion" | "api_status";
    message: string;
    status: "info" | "success" | "error" | "warning";
  }) {
    const newNotification: Notification = {
      id: `notif_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      ...params,
      timestamp: new Date(),
      read: false,
    };

    setNotifications((prev) => {
      // Avoid duplicate notifications
      const isDuplicate = prev.some(
        (n) => n.message === newNotification.message && Date.now() - n.timestamp.getTime() < 5000
      );
      if (isDuplicate) return prev;

      // Keep only last 10 notifications
      return [newNotification, ...prev].slice(0, 10);
    });
  }

  function markAsRead(id: string) {
    setNotifications((prev) =>
      prev.map((n) => (n.id === id ? { ...n, read: true } : n))
    );
  }

  function markAllAsRead() {
    setNotifications((prev) => prev.map((n) => ({ ...n, read: true })));
  }

  function removeNotification(id: string) {
    setNotifications((prev) => prev.filter((n) => n.id !== id));
  }

  function getStatusIcon(status: string) {
    switch (status) {
      case "success":
        return <CheckCircle className="w-5 h-5 text-green-500" />;
      case "error":
        return <XCircle className="w-5 h-5 text-red-500" />;
      case "warning":
        return <RefreshCw className="w-5 h-5 text-yellow-500" />;
      default:
        return <Bell className="w-5 h-5 text-blue-500" />;
    }
  }

  function formatTimestamp(date: Date) {
    const now = new Date();
    const diffMs = now.getTime() - date.getTime();
    const diffMins = Math.floor(diffMs / 60000);

    if (diffMins < 1) return "Just now";
    if (diffMins < 60) return `${diffMins}m ago`;
    const diffHours = Math.floor(diffMins / 60);
    if (diffHours < 24) return `${diffHours}h ago`;
    return date.toLocaleDateString();
  }

  return (
    <div className="relative">
      {/* Bell Icon Button */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="relative p-2 rounded-lg hover:bg-gray-100 transition"
        title="Notifications"
      >
        <Bell className="w-5 h-5 text-gray-600" />
        {unreadCount > 0 && (
          <span className="absolute top-0 right-0 w-5 h-5 bg-red-500 text-white text-xs font-bold rounded-full flex items-center justify-center">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}
      </button>

      {/* Dropdown Panel */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 z-10"
            onClick={() => setIsOpen(false)}
          />

          {/* Notification Panel */}
          <div className="absolute right-0 mt-2 w-96 bg-white rounded-lg shadow-lg border border-gray-200 z-20">
            {/* Header */}
            <div className="flex items-center justify-between px-4 py-3 border-b">
              <h3 className="font-semibold text-gray-900">Notifications</h3>
              {unreadCount > 0 && (
                <button
                  onClick={markAllAsRead}
                  className="text-xs text-blue-500 hover:text-blue-600"
                >
                  Mark all as read
                </button>
              )}
            </div>

            {/* Notification List */}
            <div className="max-h-96 overflow-y-auto">
              {notifications.length === 0 ? (
                <div className="px-4 py-8 text-center text-gray-400">
                  <Bell className="w-12 h-12 mx-auto mb-2 text-gray-300" />
                  <p className="text-sm">No notifications</p>
                </div>
              ) : (
                notifications.map((notif) => (
                  <div
                    key={notif.id}
                    onClick={() => markAsRead(notif.id)}
                    className={`px-4 py-3 border-b hover:bg-gray-50 cursor-pointer transition ${
                      !notif.read ? "bg-blue-50" : ""
                    }`}
                  >
                    <div className="flex items-start gap-3">
                      {getStatusIcon(notif.status)}
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-gray-900 break-words">
                          {notif.message}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {formatTimestamp(notif.timestamp)}
                        </p>
                      </div>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          removeNotification(notif.id);
                        }}
                        className="flex-shrink-0 p-1 hover:bg-gray-200 rounded"
                      >
                        <X className="w-4 h-4 text-gray-400" />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>

            {/* Footer */}
            {notifications.length > 0 && (
              <div className="px-4 py-2 bg-gray-50 text-center border-t">
                <button
                  onClick={() => {
                    setNotifications([]);
                    localStorage.removeItem("notifications");
                  }}
                  className="text-xs text-gray-500 hover:text-gray-700"
                >
                  Clear all notifications
                </button>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
