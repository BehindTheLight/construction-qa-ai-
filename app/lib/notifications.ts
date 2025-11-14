/**
 * Shared notification system using localStorage as event bus
 * This allows different components to add notifications
 */

export interface Notification {
  id: string;
  type: "ingestion" | "api_status" | "general";
  message: string;
  status: "info" | "success" | "error" | "warning";
  timestamp: Date;
  read: boolean;
}

/**
 * Add a notification that will appear in the NotificationBell
 * Uses localStorage as a simple event bus between components
 */
export function addNotification(params: {
  type: "ingestion" | "api_status" | "general";
  message: string;
  status: "info" | "success" | "error" | "warning";
}) {
  const newNotification: Notification = {
    id: `notif_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
    ...params,
    timestamp: new Date(),
    read: false,
  };

  // Load existing notifications
  const stored = localStorage.getItem("notifications");
  let notifications: Notification[] = [];
  
  if (stored) {
    try {
      notifications = JSON.parse(stored);
    } catch (e) {
      console.error("Failed to parse notifications:", e);
    }
  }

  // Avoid duplicate notifications (within 5 seconds)
  const isDuplicate = notifications.some(
    (n) => 
      n.message === newNotification.message && 
      Date.now() - new Date(n.timestamp).getTime() < 5000
  );

  if (isDuplicate) {
    return;
  }

  // Add new notification and keep last 10
  notifications = [newNotification, ...notifications].slice(0, 10);

  // Save back to localStorage
  localStorage.setItem("notifications", JSON.stringify(notifications));

  // Dispatch custom event to notify NotificationBell to refresh
  window.dispatchEvent(new Event("notifications-updated"));
}

/**
 * Clear all notifications
 */
export function clearAllNotifications() {
  localStorage.removeItem("notifications");
  window.dispatchEvent(new Event("notifications-updated"));
}

/**
 * Get all notifications
 */
export function getNotifications(): Notification[] {
  const stored = localStorage.getItem("notifications");
  if (!stored) return [];

  try {
    const parsed = JSON.parse(stored);
    return parsed.map((n: any) => ({
      ...n,
      timestamp: new Date(n.timestamp),
    }));
  } catch (e) {
    console.error("Failed to load notifications:", e);
    return [];
  }
}

