/**
 * Student System — Main Frontend Application Entry Point
 * State orchestrator, role routing, theme management, and realtime connection lifecycle.
 */

import { api } from "./api.js";
import { realtime } from "./realtime.js";
import { notifications } from "./components/notifications.js";
import { AuthManager } from "./components/auth.js";
import { StudentView } from "./components/student.js";
import { TeacherView } from "./components/teacher.js";
import { AdminView } from "./components/admin.js";

export class Application {
  constructor() {
    this.currentUser = null;
    this.authManager = new AuthManager(this);
    this.currentViewInstance = null;
  }

  async init() {
    // Session expiration hook
    api.onSessionExpired = () => {
      realtime.disconnect(true);
      this.authManager.showSessionExpiredDialog();
    };

    // Realtime connection status listener
    realtime.on("statusChange", (status) => {
      this.updateConnectionStatus(status);
    });

    realtime.on("sessionExpired", () => {
      this.authManager.showSessionExpiredDialog();
    });

    // Check existing session
    const user = await api.initSession();
    if (user) {
      await this.onLoginSuccess(user);
    } else {
      this.renderLogin();
    }
  }

  async onLoginSuccess(user) {
    this.currentUser = user;
    // Set default active role if not assigned
    if (!this.currentUser.active_role && this.currentUser.roles && this.currentUser.roles.length > 0) {
      this.currentUser.active_role = this.currentUser.roles[0];
    }

    // Connect realtime websocket
    realtime.connect();
    notifications.loadNotifications();

    this.renderAppShell();
    await this.mountRoleInterface(this.currentUser.active_role);
  }

  renderLogin() {
    this.currentUser = null;
    document.body.removeAttribute("data-role");
    const root = document.getElementById("app-root");
    root.innerHTML = "";
    this.authManager.renderLoginForm(root);
  }

  renderAppShell() {
    const root = document.getElementById("app-root");
    root.innerHTML = `
      <header class="app-header">
        <div class="brand-section">
          <div class="brand-logo">B</div>
          <div>
            <div class="brand-title">BVP Academic System</div>
            <div class="brand-subtitle" id="connection-status-pill">Connecting realtime...</div>
          </div>
        </div>

        <div class="user-nav">
          <div id="role-switcher-slot"></div>

          <!-- Notification Bell -->
          <button class="btn btn-secondary btn-sm" id="btn-toggle-notifs" title="Notifications" style="position: relative;">
            🔔
            <span id="notif-unread-badge" class="badge" style="display: none; position: absolute; top: -6px; right: -6px; background: var(--color-danger); color: white; padding: 2px 6px; font-size: 0.7rem;">0</span>
          </button>

          <!-- User Display -->
          <div style="font-size: 0.875rem; color: var(--text-primary); font-weight: 600; display: flex; align-items: center; gap: 0.5rem;">
            <span>${this.escape(this.currentUser.display_name || this.currentUser.login_id)}</span>
          </div>

          <!-- Logout -->
          <button class="btn btn-secondary btn-sm" id="btn-logout" title="Sign Out">
            Logout
          </button>
        </div>
      </header>

      <div class="app-container">
        <main class="app-main" id="main-content-viewport"></main>
      </div>

    `;

    // Render role switcher
    this.authManager.renderRoleSwitcher(this.currentUser);

    // Bind logout
    document.getElementById("btn-logout").addEventListener("click", async () => {
      await api.logout();
      realtime.disconnect(true);
      notifications.showToast("Signed out successfully", "info");
      this.renderLogin();
    });

    // Bind notification drawer toggle
    document.getElementById("btn-toggle-notifs").addEventListener("click", () => {
      this.showNotificationModal();
    });
  }

  async switchRoleInterface(role) {
    if (!this.currentUser.roles.includes(role)) {
      notifications.showToast("You do not hold permissions for this role", "error");
      return;
    }
    this.currentUser.active_role = role;
    this.authManager.renderRoleSwitcher(this.currentUser);
    await this.mountRoleInterface(role);
  }

  async mountRoleInterface(role) {
    document.body.setAttribute("data-role", role);
    const viewport = document.getElementById("main-content-viewport");
    if (!viewport) return;

    viewport.innerHTML = `<div class="loading-skeleton" style="height: 300px;"></div>`;

    if (role === "STUDENT") {
      this.currentViewInstance = new StudentView(viewport);
      window.studentView = this.currentViewInstance;
      await this.currentViewInstance.render();
    } else if (role === "TEACHER") {
      this.currentViewInstance = new TeacherView(viewport);
      window.teacherView = this.currentViewInstance;
      await this.currentViewInstance.render();
    } else if (role === "ADMIN") {
      this.currentViewInstance = new AdminView(viewport);
      window.adminView = this.currentViewInstance;
      await this.currentViewInstance.render();
    } else {
      viewport.innerHTML = `
        <div class="empty-state">
          <div class="empty-state-title">Unknown Role Interface</div>
          <div class="empty-state-subtitle">No view registered for role "${this.escape(role)}".</div>
        </div>
      `;
    }
  }

  updateConnectionStatus(status) {
    const pill = document.getElementById("connection-status-pill");
    if (!pill) return;

    if (status.connected) {
      pill.innerHTML = `● Realtime Connected`;
      pill.style.color = "var(--color-success)";
    } else if (status.transport === "polling") {
      pill.innerHTML = `○ Polling Fallback Active`;
      pill.style.color = "var(--color-warning)";
    } else {
      pill.innerHTML = `○ Disconnected (${status.reason || 'Reconnecting...'})`;
      pill.style.color = "var(--text-muted)";
    }
  }

  showNotificationModal() {
    let modal = document.getElementById("notifs-modal");
    if (modal) {
      modal.remove();
      return;
    }

    modal = document.createElement("div");
    modal.id = "notifs-modal";
    modal.className = "modal-backdrop";
    modal.innerHTML = `
      <div class="modal-content glass-panel" style="max-width: 520px;">
        <div class="modal-header">
          <h3 style="font-size: 1.125rem; font-weight: 700;">Notification Center</h3>
          <button class="modal-close" id="modal-notifs-close">&times;</button>
        </div>
        <div id="notification-list-container" style="max-height: 60vh; overflow-y: auto;">
          <div class="loading-skeleton" style="height: 100px;"></div>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    modal.querySelector("#modal-notifs-close").addEventListener("click", () => modal.remove());
    modal.addEventListener("click", (e) => {
      if (e.target === modal) modal.remove();
    });

    notifications.renderNotificationList();
  }

  escape(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
}

// Bootstrap on DOM ready
document.addEventListener("DOMContentLoaded", () => {
  const app = new Application();
  window.appInstance = app;
  app.init();
});
