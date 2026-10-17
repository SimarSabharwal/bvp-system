/**
 * Student System — Notifications & Announcements Component
 * In-app glassmorphic toasts, notification center with unread badges, and announcements reader.
 */

import { api } from "../api.js";
import { realtime } from "../realtime.js";

export class NotificationManager {
  constructor() {
    this.unreadCount = 0;
    this.notifications = [];
    this.announcements = [];
    this.container = document.getElementById("toast-container");
    this.initRealtimeListener();
  }

  showToast(message, type = "info", duration = 5000) {
    if (!this.container) {
      this.container = document.getElementById("toast-container");
      if (!this.container) return;
    }

    const toast = document.createElement("div");
    toast.className = `toast toast-${type} glass-card`;
    toast.setAttribute("role", "alert");
    toast.setAttribute("aria-live", "polite");

    const icon = type === "success" ? "✓" : type === "error" ? "⚠" : "ℹ";
    const tone = type === "error" ? "danger" : ["success", "warning", "info"].includes(type) ? type : "info";
    toast.innerHTML = `
      <span style="font-weight: bold; color: var(--color-${tone});">${icon}</span>
      <div style="flex: 1; line-height: 1.4;">${this.escapeHtml(message)}</div>
      <button class="modal-close" style="font-size: 1rem; cursor: pointer;" aria-label="Dismiss">&times;</button>
    `;

    const closeBtn = toast.querySelector("button");
    const dismiss = () => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.25s ease";
      setTimeout(() => toast.remove(), 250);
    };

    closeBtn.addEventListener("click", dismiss);
    if (duration > 0) {
      setTimeout(dismiss, duration);
    }

    this.container.appendChild(toast);
  }

  initRealtimeListener() {
    realtime.on("notification", (notif) => {
      this.unreadCount++;
      this.updateBadge();
      this.showToast(notif.title || notif.message, notif.severity || "info");
      this.notifications.unshift(notif);
      this.renderNotificationList();
    });
  }

  updateBadge() {
    const badge = document.getElementById("notif-unread-badge");
    if (badge) {
      if (this.unreadCount > 0) {
        badge.textContent = this.unreadCount > 99 ? "99+" : this.unreadCount;
        badge.style.display = "inline-flex";
      } else {
        badge.style.display = "none";
      }
    }
  }

  async loadNotifications() {
    try {
      const res = await api.getNotifications({ limit: 25 });
      if (res && res.items) {
        this.notifications = res.items;
        this.unreadCount = res.unread_count ?? this.notifications.filter(n => !n.read_at).length;
        this.updateBadge();
        this.renderNotificationList();
      }
    } catch (err) {
      console.warn("Failed to load notifications:", err);
    }
  }

  async loadAnnouncements() {
    try {
      const res = await api.getAnnouncements({ limit: 25 });
      if (res && res.items) {
        this.announcements = res.items;
        this.renderAnnouncementList();
      }
    } catch (err) {
      console.warn("Failed to load announcements:", err);
    }
  }

  async markAsRead(notificationId) {
    try {
      await api.markNotificationRead(notificationId);
      const notif = this.notifications.find(n => n.notification_id === notificationId);
      if (notif && !notif.read_at) {
        notif.read_at = new Date().toISOString();
        this.unreadCount = Math.max(0, this.unreadCount - 1);
        this.updateBadge();
        this.renderNotificationList();
      }
    } catch (err) {
      this.showToast("Could not mark notification as read", "error");
    }
  }

  renderNotificationList() {
    const el = document.getElementById("notification-list-container");
    if (!el) return;

    if (this.notifications.length === 0) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">🔔</div>
          <div class="empty-state-title">No notifications</div>
          <div class="empty-state-subtitle">You are all caught up with your updates.</div>
        </div>
      `;
      return;
    }

    el.innerHTML = this.notifications.map(n => `
      <div class="glass-card" style="margin-bottom: 0.75rem; display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem; ${n.read_at ? 'opacity: 0.7;' : 'border-left: 3px solid var(--role-accent);'}">
        <div style="flex: 1;">
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
            <span style="font-weight: 600; color: var(--text-primary); font-size: 0.9375rem;">${this.escapeHtml(n.title || 'System Notification')}</span>
            ${!n.read_at ? '<span class="badge" style="background: var(--role-glow); color: var(--role-accent); font-size: 0.65rem;">NEW</span>' : ''}
          </div>
          <div style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 0.375rem;">${this.escapeHtml(n.message)}</div>
          <div style="color: var(--text-muted); font-size: 0.75rem;">${new Date(n.created_at).toLocaleString()}</div>
        </div>
        ${!n.read_at ? `
          <button class="btn btn-secondary btn-sm" onclick="window.notificationManager.markAsRead(${n.notification_id})">
            Mark Read
          </button>
        ` : ''}
      </div>
    `).join("");
  }

  renderAnnouncementList() {
    const el = document.getElementById("announcement-list-container");
    if (!el) return;

    if (this.announcements.length === 0) {
      el.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-icon">📢</div>
          <div class="empty-state-title">No announcements</div>
          <div class="empty-state-subtitle">No active announcements posted for your section or role.</div>
        </div>
      `;
      return;
    }

    el.innerHTML = this.announcements.map(a => `
      <div class="glass-card" style="margin-bottom: 1rem; border-left: 3px solid #38bdf8;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.5rem;">
          <h4 style="color: var(--text-primary); font-weight: 700; font-size: 1.05rem;">${this.escapeHtml(a.title)}</h4>
          <span class="badge" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8;">${a.audience_scope}</span>
        </div>
        <div style="color: var(--text-secondary); font-size: 0.9375rem; line-height: 1.5; white-space: pre-wrap; margin-bottom: 0.75rem;">${this.escapeHtml(a.body)}</div>
        <div style="display: flex; justify-content: space-between; color: var(--text-muted); font-size: 0.75rem;">
          <span>Posted: ${new Date(a.published_at || a.created_at).toLocaleDateString()}</span>
          ${a.expires_at ? `<span>Valid until: ${new Date(a.expires_at).toLocaleDateString()}</span>` : ''}
        </div>
      </div>
    `).join("");
  }

  escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

export const notifications = new NotificationManager();
window.notificationManager = notifications;
