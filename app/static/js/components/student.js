/**
 * Student System — Student Interface Component
 * Today's schedule, weekly timetable, attendance breakdown, notifications & announcements.
 */

import { api } from "../api.js";
import { notifications } from "./notifications.js";

export class StudentView {
  constructor(appContainer) {
    this.container = appContainer;
    this.profile = null;
    this.currentDate = this.localDate(new Date());
    this.activeTab = "today";
    this.scheduleData = [];
    this.attendanceData = null;
  }

  async render() {
    this.container.innerHTML = `
      <div class="view-header">
        <div>
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
            <h1 class="view-title">Student Portal</h1>
            <span class="badge badge-student">STUDENT</span>
          </div>
          <div class="view-description" id="student-meta-header">Loading enrollment profile...</div>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" id="btn-refresh-student">
            ↻ Refresh
          </button>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <div style="display: flex; gap: 0.5rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 0.5rem; margin-bottom: 1.5rem; overflow-x: auto;">
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'today' ? 'active' : ''}" data-student-tab="today">Today's Schedule</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'weekly' ? 'active' : ''}" data-student-tab="weekly">Weekly Timetable</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'attendance' ? 'active' : ''}" data-student-tab="attendance">Attendance Summary</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'announcements' ? 'active' : ''}" data-student-tab="announcements">Announcements</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'notifications' ? 'active' : ''}" data-student-tab="notifications">Notifications</button>
      </div>

      <div id="student-tab-content">
        <div class="loading-skeleton" style="height: 250px;"></div>
      </div>
    `;

    this.bindEvents();
    await this.loadProfile();
    await this.renderTabContent();
  }

  bindEvents() {
    this.container.querySelectorAll("[data-student-tab]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        this.activeTab = e.currentTarget.getAttribute("data-student-tab");
        this.container.querySelectorAll("[data-student-tab]").forEach(b => b.classList.remove("active"));
        e.currentTarget.classList.add("active");
        await this.renderTabContent();
      });
    });

    const refreshBtn = this.container.querySelector("#btn-refresh-student");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.renderTabContent());
    }
  }

  async loadProfile() {
    try {
      const res = await api.getStudentProfile();
      if (res && res.student_id) {
        this.profile = res;
        const meta = document.getElementById("student-meta-header");
        if (meta) {
          const enrollment = this.profile.enrollment || {};
          meta.textContent = `ERP ID: ${this.profile.erp_id || "—"} · ${enrollment.section_code ? `Section ${enrollment.section_code}` : "Section not assigned"}${enrollment.semester ? ` · Semester ${enrollment.semester}` : ""}`;
        }
      }
    } catch (err) {
      console.warn("Could not load student profile:", err);
      const meta = document.getElementById("student-meta-header");
      if (meta) meta.textContent = "Self-enrolled student";
    }
  }

  async renderTabContent() {
    const content = document.getElementById("student-tab-content");
    if (!content) return;
    content.innerHTML = `<div class="loading-skeleton" style="height: 200px;"></div>`;

    try {
      if (this.activeTab === "today") {
        await this.renderTodaySchedule(content);
      } else if (this.activeTab === "weekly") {
        await this.renderWeeklySchedule(content);
      } else if (this.activeTab === "attendance") {
        await this.renderAttendance(content);
      } else if (this.activeTab === "announcements") {
        content.innerHTML = `<div id="announcement-list-container"></div>`;
        await notifications.loadAnnouncements();
      } else if (this.activeTab === "notifications") {
        content.innerHTML = `<div id="notification-list-container"></div>`;
        await notifications.loadNotifications();
      }
    } catch (err) {
      content.innerHTML = `
        <div class="error-banner">
          <div>
            <strong>Failed to load data</strong>
            <div style="font-size: 0.85rem; color: #fca5a5;">${this.escape(err.message || 'Unknown error')}</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="window.studentView.renderTabContent()">Retry</button>
        </div>
      `;
    }
  }

  async renderTodaySchedule(container) {
    if (this.profile && !this.profile.enrollment) {
      this.renderUnassignedSectionState(container);
      return;
    }

    const data = await api.getStudentSchedule({ date: this.currentDate, view_as: "STUDENT" });
    const sessions = (data?.items || []).map(item => this.normalizeSession(item));

    if (sessions.length === 0) {
      container.innerHTML = `
        <div class="glass-card empty-state">
          <div class="empty-state-icon">📅</div>
          <div class="empty-state-title">No lectures scheduled today</div>
          <div class="empty-state-subtitle">Enjoy your day or check the weekly timetable for upcoming classes.</div>
        </div>
      `;
      return;
    }

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600;">Today's Classes (${this.currentDate})</h3>
        <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-secondary);">${sessions.length} Session${sessions.length > 1 ? 's' : ''}</span>
      </div>
      <div style="display: grid; gap: 1rem; grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));">
        ${sessions.map(s => this.renderSessionCard(s)).join("")}
      </div>
    `;
  }

  async renderWeeklySchedule(container) {
    if (this.profile && !this.profile.enrollment) {
      this.renderUnassignedSectionState(container);
      return;
    }

    // Compute current week range (Mon-Sat)
    const now = new Date();
    const day = now.getDay();
    const diffToMonday = (day === 0 ? -6 : 1) - day;
    const monday = new Date(now);
    monday.setDate(now.getDate() + diffToMonday);
    const saturday = new Date(monday);
    saturday.setDate(monday.getDate() + 5);

    const fromStr = this.localDate(monday);
    const toStr = this.localDate(saturday);

    const data = await api.getStudentSchedule({ from: fromStr, to: toStr, view_as: "STUDENT" });
    const sessions = (data?.items || []).map(item => this.normalizeSession(item));

    if (sessions.length === 0) {
      container.innerHTML = `
        <div class="glass-card empty-state">
          <div class="empty-state-icon">📆</div>
          <div class="empty-state-title">No weekly timetable available</div>
          <div class="empty-state-subtitle">Timetables may not be published for this period yet.</div>
        </div>
      `;
      return;
    }

    // Group by date
    const byDate = {};
    sessions.forEach(s => {
      if (!byDate[s.session_date]) byDate[s.session_date] = [];
      byDate[s.session_date].push(s);
    });

    const dates = Object.keys(byDate).sort();

    container.innerHTML = `
      <div style="margin-bottom: 1rem; display: flex; justify-content: space-between; align-items: center;">
        <h3 style="font-size: 1.125rem; font-weight: 600;">Weekly Schedule (${fromStr} to ${toStr})</h3>
      </div>
      <div style="display: flex; flex-direction: column; gap: 1.5rem;">
        ${dates.map(dateKey => {
          const dayName = new Date(dateKey + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' });
          return `
            <div class="glass-panel" style="padding: 1.25rem;">
              <h4 style="font-size: 1rem; font-weight: 700; color: var(--role-accent); margin-bottom: 0.75rem;">${dayName}</h4>
              <div style="display: grid; gap: 0.75rem; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));">
                ${byDate[dateKey].map(s => this.renderSessionCard(s, true)).join("")}
              </div>
            </div>
          `;
        }).join("")}
      </div>
    `;
  }

  renderUnassignedSectionState(container) {
    container.innerHTML = `
      <div class="glass-card empty-state">
        <div class="empty-state-icon">📚</div>
        <div class="empty-state-title">No section assigned yet</div>
        <div class="empty-state-subtitle">Your timetable will appear here after your student profile is linked to a section.</div>
      </div>
    `;
  }

  async renderAttendance(container) {
    const now = new Date();
    const fromStr = this.localDate(new Date(now.getFullYear(), 0, 1));
    const toStr = this.localDate(now);

    const data = await api.getStudentAttendance(fromStr, toStr);
    const overall = data?.overall?.percentage;
    const subjects = data && data.subjects ? data.subjects : [];

    const isGood = overall !== null && overall !== undefined && overall >= 75;

    container.innerHTML = `
      <div class="grid-stats">
        <div class="glass-card stat-card">
          <span class="stat-label">Overall Attendance</span>
          <div class="stat-value" style="color: ${isGood ? 'var(--color-success)' : 'var(--color-danger)'};">
            ${overall === null || overall === undefined ? "—" : `${Number(overall).toFixed(1)}%`}
          </div>
          <span class="stat-meta">
            ${overall === null || overall === undefined ? 'No closed attendance records yet' : isGood ? '✓ Meets minimum 75% requirement' : '⚠ Below institutional threshold (75%)'}
          </span>
        </div>
        <div class="glass-card stat-card">
          <span class="stat-label">Total Attended Sessions</span>
          <div class="stat-value">${data?.overall?.attended_sessions || 0}</div>
          <span class="stat-meta">Out of ${data?.overall?.counted_sessions || 0} counted sessions</span>
        </div>
        <div class="glass-card stat-card">
          <span class="stat-label">Excused Absences</span>
          <div class="stat-value" style="color: var(--color-info);">—</div>
          <span class="stat-meta">Excused records are excluded by the server</span>
        </div>
      </div>

      <div class="glass-panel" style="padding: 1.25rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">Subject-wise Attendance Breakdown</h3>
        ${subjects.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state-subtitle">No attendance records found for this period.</div>
          </div>
        ` : `
          <div class="table-container">
            <table class="glass-table">
              <thead>
                <tr>
                  <th>Subject Code</th>
                  <th>Subject Name</th>
                  <th>Attended</th>
                  <th>Total Held</th>
                  <th>Excused</th>
                  <th>Percentage</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${subjects.map(sub => {
                  const pct = sub.percentage;
                  const displayPct = pct === null || pct === undefined ? "—" : `${Number(pct).toFixed(1)}%`;
                  const ok = pct >= 75;
                  return `
                    <tr>
                      <td style="font-weight: 600;">${this.escape(sub.code)}</td>
                      <td>${this.escape(sub.name)}</td>
                      <td>${sub.attended_sessions}</td>
                      <td>${sub.counted_sessions}</td>
                      <td>—</td>
                      <td style="font-weight: 700; color: ${ok ? 'var(--color-success)' : 'var(--text-secondary)'};">${displayPct}</td>
                      <td>
                        <span class="badge ${ok ? 'badge-present' : 'badge-absent'}">
                          ${ok ? 'GOOD' : 'LOW'}
                        </span>
                      </td>
                    </tr>
                  `;
                }).join("")}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;
  }

  renderSessionCard(s, compact = false) {
    const statusClass = `badge-${(s.status || 'scheduled').toLowerCase()}`;
    const isReallocated = s.status === "REALLOCATED";

    return `
      <div class="glass-card" style="${isReallocated ? 'border-left: 3px solid #fbbf24;' : ''}">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 0.5rem;">
          <div>
            <div style="font-size: 0.75rem; font-weight: 700; color: var(--role-accent); text-transform: uppercase;">
              ${this.escape(s.subject_code || '')}
            </div>
            <h4 style="font-size: 1rem; font-weight: 700; color: var(--text-primary); margin-top: 0.125rem;">
              ${this.escape(s.subject_name || 'Class Session')}
            </h4>
          </div>
          <span class="badge ${statusClass}">${s.status}</span>
        </div>

        <div style="display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.8125rem; color: var(--text-secondary); margin-bottom: 0.5rem;">
          <div>⏱ <strong>${s.start_time || ''} - ${s.end_time || ''}</strong></div>
          <div>👨‍🏫 Teacher: <strong>${this.escape(s.teacher_name || 'Assigned Faculty')}</strong></div>
          <div>🏛 Room: <strong>${this.escape(s.room_number || 'Room TBA')}${s.building ? ' (' + this.escape(s.building) + ')' : ''}</strong></div>
        </div>

        ${isReallocated ? `
          <div style="background: rgba(245, 158, 11, 0.1); border-radius: var(--radius-sm); padding: 0.375rem 0.5rem; font-size: 0.75rem; color: #fbbf24;">
            ⚠ Reallocated: ${this.escape(s.reallocation_reason || 'Schedule adjusted')}
          </div>
        ` : ''}
      </div>
    `;
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

  normalizeSession(item) {
    return {
      session_date: item.date,
      status: item.status,
      subject_code: item.subject?.code,
      subject_name: item.subject?.name,
      teacher_name: item.counterparty,
      room_number: item.room,
      start_time: item.starts_at?.slice(11, 16),
      end_time: item.ends_at?.slice(11, 16),
    };
  }

  localDate(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
}
