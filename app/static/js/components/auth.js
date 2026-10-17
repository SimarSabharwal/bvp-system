/**
 * Student System — Authentication & Role Switcher Component
 * Sign-in form, multi-role switching, session expiry modal, and logout handling.
 */

import { api } from "../api.js";
import { realtime } from "../realtime.js";
import { notifications } from "./notifications.js";

export class AuthManager {
  constructor(app) {
    this.app = app;
    this.currentUser = null;
  }

  renderLoginForm(container) {
    container.innerHTML = `
      <div style="min-height: 80vh; display: flex; align-items: center; justify-content: center; padding: 1.5rem;">
        <div class="glass-panel" style="max-width: 440px; width: 100%; padding: 2.25rem; box-shadow: var(--glass-shadow-lg);">
          <div style="text-align: center; margin-bottom: 2rem;">
            <div style="width: 52px; height: 52px; border-radius: 14px; background: linear-gradient(135deg, #38bdf8, #6366f1); margin: 0 auto 1rem; display: flex; align-items: center; justify-content: center; font-size: 1.5rem; font-weight: 800; color: white; box-shadow: 0 0 20px rgba(99, 102, 241, 0.4);">
              B
            </div>
            <h2 style="font-size: 1.625rem; font-weight: 700; color: var(--text-primary); letter-spacing: -0.02em;">Welcome to Student System</h2>
            <p style="color: var(--text-muted); font-size: 0.875rem; margin-top: 0.375rem;">Real-Time Academic ERP & Dynamic Scheduler</p>
          </div>

          <div id="login-error-alert" style="display: none;" class="error-banner"></div>

          <form id="form-login">
            <div class="form-group">
              <label class="form-label" for="login-id">ERP ID / Faculty Code / Username</label>
              <input type="text" id="login-id" class="glass-input" placeholder="e.g. S101, T201, or admin" required autocomplete="username">
            </div>

            <div class="form-group">
              <label class="form-label" for="login-password">Password</label>
              <input type="password" id="login-password" class="glass-input" placeholder="Enter your password" required autocomplete="current-password">
            </div>

            <button type="submit" id="btn-submit-login" class="btn btn-primary" style="width: 100%; margin-top: 1rem; padding: 0.75rem;">
              Sign In to Portal
            </button>
          </form>

          <div style="margin-top: 1.75rem; padding-top: 1.25rem; border-top: 1px solid var(--glass-border); text-align: center; color: var(--text-muted); font-size: 0.8125rem;">
            Secured by session-bound CSRF & server-side role validation.
          </div>
        </div>
      </div>
    `;

    const form = container.querySelector("#form-login");
    const errorAlert = container.querySelector("#login-error-alert");
    const submitBtn = container.querySelector("#btn-submit-login");

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      errorAlert.style.display = "none";
      submitBtn.disabled = true;
      submitBtn.textContent = "Signing In...";

      const loginId = document.getElementById("login-id").value.trim();
      const password = document.getElementById("login-password").value;
      try {
        this.currentUser = await api.login(loginId, password);
        notifications.showToast(`Signed in successfully as ${this.currentUser.login_id}`, "success");
        await this.app.onLoginSuccess(this.currentUser);
      } catch (err) {
        errorAlert.style.display = "flex";
        errorAlert.textContent = `Sign-in failed: ${err.message || 'Invalid credentials or account throttled.'}`;
      } finally {
        submitBtn.disabled = false;
        submitBtn.textContent = "Sign In to Portal";
      }
    });
  }

  renderRoleSwitcher(user) {
    const container = document.getElementById("role-switcher-slot");
    if (!container) return;

    if (!user || !user.roles || user.roles.length <= 1) {
      const role = user?.active_role || user?.roles?.[0] || "USER";
      container.innerHTML = `
        <span class="badge badge-${role.toLowerCase()}">
          ${role}
        </span>
      `;
      return;
    }

    // Multi-role switcher
    container.innerHTML = `
      <div class="role-switcher-container" title="Switch your active role interface">
        <span class="role-switcher-label" style="font-size: 0.75rem; color: var(--text-muted); margin: 0 0.5rem; font-weight: 600;">ROLE:</span>
        ${user.roles.map(r => `
          <button class="role-switch-btn ${user.active_role === r ? 'active' : ''}" data-switch-role="${r}" type="button" aria-pressed="${user.active_role === r}">
            ${r}
          </button>
        `).join("")}
      </div>
    `;

    container.querySelectorAll("[data-switch-role]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        const selectedRole = e.currentTarget.getAttribute("data-switch-role");
        if (selectedRole === user.active_role) return;
        user.active_role = selectedRole;
        await this.app.switchRoleInterface(selectedRole);
      });
    });
  }

  showSessionExpiredDialog() {
    let modal = document.getElementById("session-expired-modal");
    if (!modal) {
      modal = document.createElement("div");
      modal.id = "session-expired-modal";
      modal.className = "modal-backdrop";
      modal.innerHTML = `
        <div class="modal-content glass-panel" style="max-width: 400px; text-align: center;">
          <div style="font-size: 2.5rem; margin-bottom: 0.75rem;">⏳</div>
          <h3 style="font-size: 1.25rem; font-weight: 700; color: var(--text-primary); margin-bottom: 0.5rem;">Session Expired</h3>
          <p style="color: var(--text-secondary); font-size: 0.875rem; margin-bottom: 1.5rem;">
            Your authenticated session has reached its expiry limit. Please sign in again to continue your work.
          </p>
          <button class="btn btn-primary" id="btn-re-login" style="width: 100%;">Sign In Again</button>
        </div>
      `;
      document.body.appendChild(modal);

      modal.querySelector("#btn-re-login").addEventListener("click", () => {
        modal.remove();
        this.app.renderLogin();
      });
    }
  }
}
