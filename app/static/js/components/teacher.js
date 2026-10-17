/**
 * Student System — Teacher Interface Component
 * Assigned schedule, free period detection, live attendance workflows, self unavailability management.
 */

import { api } from "../api.js";
import { notifications } from "./notifications.js";

export class TeacherView {
  constructor(appContainer) {
    this.container = appContainer;
    this.profile = null;
    this.currentDate = this.localDate(new Date());
    this.activeTab = "schedule";
    this.activeAttendanceSession = null;
    this.attendanceRoster = [];
  }

  async render() {
    this.container.innerHTML = `
      <div class="view-header">
        <div>
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
            <h1 class="view-title">Teacher Portal</h1>
            <span class="badge badge-teacher">FACULTY</span>
          </div>
          <div class="view-description" id="teacher-meta-header">Loading faculty profile...</div>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" id="btn-refresh-teacher">
            ↻ Refresh
          </button>
        </div>
      </div>

      <!-- Navigation Tabs -->
      <div style="display: flex; gap: 0.5rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 0.5rem; margin-bottom: 1.5rem; overflow-x: auto;">
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'schedule' ? 'active' : ''}" data-teacher-tab="schedule">My Schedule & Free Periods</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'attendance' ? 'active' : ''}" data-teacher-tab="attendance">Take Attendance</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'availability' ? 'active' : ''}" data-teacher-tab="availability">Mark Unavailability</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'announcements' ? 'active' : ''}" data-teacher-tab="announcements">Announcements</button>
        <button class="btn btn-secondary btn-sm ${this.activeTab === 'notifications' ? 'active' : ''}" data-teacher-tab="notifications">Notifications</button>
      </div>

      <div id="teacher-tab-content">
        <div class="loading-skeleton" style="height: 250px;"></div>
      </div>
    `;

    this.bindEvents();
    await this.loadProfile();
    await this.renderTabContent();
  }

  bindEvents() {
    this.container.querySelectorAll("[data-teacher-tab]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        this.activeTab = e.currentTarget.getAttribute("data-teacher-tab");
        this.container.querySelectorAll("[data-teacher-tab]").forEach(b => b.classList.remove("active"));
        e.currentTarget.classList.add("active");
        await this.renderTabContent();
      });
    });

    const refreshBtn = this.container.querySelector("#btn-refresh-teacher");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.renderTabContent());
    }
  }

  async loadProfile() {
    try {
      const res = await api.getTeacherProfile();
      if (res && res.teacher_id) {
        this.profile = res;
        const meta = document.getElementById("teacher-meta-header");
        if (meta) {
          meta.textContent = `Faculty: ${this.profile.full_name} · Code: ${this.profile.faculty_code || "—"} · Dept: ${this.profile.department || "Academics"}`;
        }
      }
    } catch (err) {
      console.warn("Could not load teacher profile:", err);
      const meta = document.getElementById("teacher-meta-header");
      if (meta) meta.textContent = "Authorized Teacher";
    }
  }

  async renderTabContent() {
    const content = document.getElementById("teacher-tab-content");
    if (!content) return;
    content.innerHTML = `<div class="loading-skeleton" style="height: 200px;"></div>`;

    try {
      if (this.activeTab === "schedule") {
        await this.renderSchedule(content);
      } else if (this.activeTab === "attendance") {
        await this.renderAttendanceWorkflow(content);
      } else if (this.activeTab === "availability") {
        await this.renderAvailability(content);
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
          <button class="btn btn-secondary btn-sm" onclick="window.teacherView.renderTabContent()">Retry</button>
        </div>
      `;
    }
  }

  async renderSchedule(container) {
    const data = await api.getTeacherSchedule({ date: this.currentDate, view_as: "TEACHER" });
    const sessions = (data?.items || []).map(item => this.normalizeSession(item));

    // Sort by start_time
    sessions.sort((a, b) => (a.start_time || "").localeCompare(b.start_time || ""));

    // Find free periods between sessions
    const freeGaps = [];
    for (let i = 0; i < sessions.length - 1; i++) {
      const currentEnd = sessions[i].end_time;
      const nextStart = sessions[i + 1].start_time;
      if (currentEnd && nextStart && currentEnd < nextStart) {
        freeGaps.push({ from: currentEnd, to: nextStart });
      }
    }

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600;">Today's Assigned Lectures (${this.currentDate})</h3>
        <span class="badge" style="background: rgba(255,255,255,0.06); color: var(--text-secondary);">${sessions.length} Session${sessions.length !== 1 ? 's' : ''}</span>
      </div>

      ${sessions.length === 0 ? `
        <div class="glass-card empty-state">
          <div class="empty-state-icon">☕</div>
          <div class="empty-state-title">No teaching sessions scheduled today</div>
          <div class="empty-state-subtitle">You have no assigned lectures for ${this.currentDate}.</div>
        </div>
      ` : `
        <div style="display: flex; flex-direction: column; gap: 1rem; margin-bottom: 2rem;">
              ${sessions.map((s, idx) => {
            const hasGapAfter = freeGaps.find(g => g.from === s.end_time);
            return `
              <div class="glass-card" style="display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 1rem;">
                <div>
                  <div style="display: flex; align-items: center; gap: 0.5rem;">
                    <span class="badge" style="background: var(--theme-teacher-glow); color: var(--theme-teacher);">${s.start_time} - ${s.end_time}</span>
                    <h4 style="font-size: 1.05rem; font-weight: 700;">${this.escape(s.subject_name || s.subject_code)}</h4>
                    <span class="badge badge-${(s.status || 'scheduled').toLowerCase()}">${s.status}</span>
                  </div>
                  <div style="font-size: 0.8125rem; color: var(--text-secondary); margin-top: 0.375rem;">
                    Section: <strong>${this.escape(s.section_code || s.section_id)}</strong> | Room: <strong>${this.escape(s.room_number || '')}</strong>
                  </div>
                </div>
                <div>
                  ${s.status === "SCHEDULED" ? `<button class="btn btn-primary btn-sm" onclick="window.teacherView.startAttendanceForSession(${s.session_id})">Take Attendance →</button>` : `<span class="badge badge-completed">${this.escape(s.status)}</span>`}
                </div>
              </div>

              ${hasGapAfter ? `
                <div style="padding: 0.625rem 1rem; border-radius: var(--radius-sm); background: rgba(52, 211, 153, 0.08); border: 1px dashed rgba(52, 211, 153, 0.3); color: var(--theme-teacher); font-size: 0.8125rem; display: flex; align-items: center; gap: 0.5rem;">
                  <span>☕ Free Period / Prep Gap: <strong>${hasGapAfter.from} - ${hasGapAfter.to}</strong></span>
                </div>
              ` : ''}
            `;
          }).join("")}
        </div>
      `}
    `;
  }

  async renderAttendanceWorkflow(container) {
    if (!this.activeAttendanceSession) {
      // Pick a session from today's schedule
      const data = await api.getTeacherSchedule({ date: this.currentDate, view_as: "TEACHER" });
      const sessions = (data?.items || []).map(item => this.normalizeSession(item)).filter(item => item.status === "SCHEDULED");

      container.innerHTML = `
        <div class="glass-panel" style="padding: 1.5rem;">
          <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.5rem;">Select Class Session for Attendance</h3>
          <p style="color: var(--text-muted); font-size: 0.875rem; margin-bottom: 1.25rem;">
            Choose a scheduled session assigned to you to open attendance, mark student records, and close the session.
          </p>

          ${sessions.length === 0 ? `
            <div class="empty-state">
              <div class="empty-state-subtitle">No sessions available today to take attendance.</div>
            </div>
          ` : `
            <div style="display: grid; gap: 0.75rem;">
              ${sessions.map(s => `
                <div class="glass-card" style="display: flex; justify-content: space-between; align-items: center; cursor: pointer;" onclick="window.teacherView.startAttendanceForSession(${s.session_id})">
                  <div>
                    <strong style="color: var(--text-primary);">${this.escape(s.subject_name)}</strong>
                    <div style="font-size: 0.8125rem; color: var(--text-muted);">
                      Time: ${s.start_time} - ${s.end_time} | Section: ${this.escape(s.section_code || s.section_id)}
                    </div>
                  </div>
                  <button class="btn btn-secondary btn-sm">Select Session</button>
                </div>
              `).join("")}
            </div>
          `}
        </div>
      `;
      return;
    }

    // Live attendance taking view
    const sess = this.activeAttendanceSession;
    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 1rem; margin-bottom: 1.5rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 1rem;">
          <div>
            <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
              <h3 style="font-size: 1.25rem; font-weight: 700;">${this.escape(sess.subject_name || 'Class Session')}</h3>
              <span class="badge badge-ongoing">ACTIVE SESSION</span>
            </div>
            <div style="font-size: 0.875rem; color: var(--text-secondary);">
              Section: <strong>${this.escape(sess.section_code || '')}</strong> | Room: <strong>${this.escape(sess.room_number || '')}</strong> | Date: <strong>${sess.date || this.currentDate}</strong>
            </div>
          </div>
          <div style="display: flex; gap: 0.5rem; align-items: center;">
            <button class="btn btn-secondary btn-sm" id="btn-mark-all-present">Mark All Present</button>
            <button class="btn btn-success btn-sm" id="btn-close-attendance">Close & Submit Attendance</button>
            <button class="btn btn-secondary btn-sm" id="btn-cancel-attendance">Back</button>
          </div>
        </div>

        <div id="attendance-roster-viewport">
          <div class="loading-skeleton" style="height: 150px;"></div>
        </div>
      </div>
    `;

    this.bindAttendanceActions();
    await this.loadAttendanceRoster();
  }

  async startAttendanceForSession(classSessionId) {
    try {
      // Step 1: Open session (or retrieve open session)
      let openRes;
      try {
        openRes = await api.openAttendance(classSessionId);
      } catch (openError) {
        // The API intentionally has no "get or open" operation. If already open,
        // the ownership-scoped roster endpoint returns its actual attendance ID.
        openRes = await api.getAttendanceRoster(classSessionId);
        if (!openRes?.attendance_session_id) throw openError;
      }

      this.activeAttendanceSession = {
        class_session_id: classSessionId,
        attendance_session_id: openRes && openRes.attendance_session_id ? openRes.attendance_session_id : classSessionId
      };
      this.activeTab = "attendance";
      await this.renderTabContent();
    } catch (err) {
      notifications.showToast(`Cannot open attendance: ${err.message}`, "error");
    }
  }

  async loadAttendanceRoster() {
    const viewport = document.getElementById("attendance-roster-viewport");
    if (!viewport || !this.activeAttendanceSession) return;

    try {
      const res = await api.getAttendanceRoster(this.activeAttendanceSession.class_session_id);
      this.attendanceRoster = (res?.items || []).map(item => ({
        student_id: item.student_id,
        roll_number: item.erp_id,
        student_name: item.full_name,
        status: item.attendance || "UNMARKED",
      }));
      if (res.attendance_session_id) {
        this.activeAttendanceSession.attendance_session_id = res.attendance_session_id;
      }

      if (this.attendanceRoster.length === 0) {
        viewport.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-subtitle">No enrolled students found in this section roster.</div>
          </div>
        `;
        return;
      }

      viewport.innerHTML = `
        <div class="table-container">
          <table class="glass-table">
            <thead>
              <tr>
                <th>Roll No</th>
                <th>Student Name</th>
                <th>Current Status</th>
                <th style="text-align: right;">Set Mark</th>
              </tr>
            </thead>
            <tbody>
              ${this.attendanceRoster.map(st => {
                const cur = st.status || "UNMARKED";
                return `
                  <tr>
                    <td style="font-weight: 600;">${this.escape(st.roll_number)}</td>
                    <td>${this.escape(st.student_name)}</td>
                    <td>
                      <span class="badge ${cur === 'UNMARKED' ? 'badge-cancelled' : 'badge-' + cur.toLowerCase()}">
                        ${cur}
                      </span>
                    </td>
                    <td style="text-align: right;">
                      <div style="display: inline-flex; gap: 0.25rem;">
                        <button class="btn btn-sm ${cur === 'PRESENT' ? 'btn-success' : 'btn-secondary'}" onclick="window.teacherView.setStudentMark(${st.student_id}, 'PRESENT')">P</button>
                        <button class="btn btn-sm ${cur === 'ABSENT' ? 'btn-danger' : 'btn-secondary'}" onclick="window.teacherView.setStudentMark(${st.student_id}, 'ABSENT')">A</button>
                        <button class="btn btn-sm ${cur === 'LATE' ? 'btn-primary' : 'btn-secondary'}" onclick="window.teacherView.setStudentMark(${st.student_id}, 'LATE')">L</button>
                        <button class="btn btn-sm ${cur === 'EXCUSED' ? 'btn-primary' : 'btn-secondary'}" onclick="window.teacherView.setStudentMark(${st.student_id}, 'EXCUSED')">E</button>
                      </div>
                    </td>
                  </tr>
                `;
              }).join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (err) {
      viewport.innerHTML = `
        <div class="error-banner">
          <div>Failed to load roster: ${this.escape(err.message)}</div>
          <button class="btn btn-secondary btn-sm" onclick="window.teacherView.loadAttendanceRoster()">Retry</button>
        </div>
      `;
    }
  }

  async setStudentMark(studentId, status) {
    if (!this.activeAttendanceSession || !this.activeAttendanceSession.attendance_session_id) return;
    try {
      await api.recordAttendance(this.activeAttendanceSession.attendance_session_id, studentId, status);
      const student = this.attendanceRoster.find(s => s.student_id === studentId);
      if (student) student.status = status;
      await this.loadAttendanceRoster();
    } catch (err) {
      notifications.showToast(`Failed to update mark: ${err.message}`, "error");
    }
  }

  bindAttendanceActions() {
    const markAllBtn = document.getElementById("btn-mark-all-present");
    if (markAllBtn) {
      markAllBtn.addEventListener("click", async () => {
        if (!this.attendanceRoster.length) return;
        markAllBtn.disabled = true;
        markAllBtn.textContent = "Marking...";
        try {
          for (const s of this.attendanceRoster) {
            await api.recordAttendance(this.activeAttendanceSession.attendance_session_id, s.student_id, "PRESENT");
            s.status = "PRESENT";
          }
          notifications.showToast("All students marked Present", "success");
          await this.loadAttendanceRoster();
        } catch (err) {
          notifications.showToast(`Marking error: ${err.message}`, "error");
        } finally {
          markAllBtn.disabled = false;
          markAllBtn.textContent = "Mark All Present";
        }
      });
    }

    const closeBtn = document.getElementById("btn-close-attendance");
    if (closeBtn) {
      closeBtn.addEventListener("click", async () => {
        const unmarked = this.attendanceRoster.filter(s => !s.status || s.status === "UNMARKED");
        if (unmarked.length > 0) {
          notifications.showToast(`Cannot close: ${unmarked.length} student(s) still unmarked`, "warning");
          return;
        }

        if (!confirm("Are you sure you want to close attendance? Closed sessions are submitted to institutional records.")) return;

        try {
          await api.closeAttendance(this.activeAttendanceSession.attendance_session_id);
          notifications.showToast("Attendance successfully closed and submitted!", "success");
          this.activeAttendanceSession = null;
          this.activeTab = "schedule";
          await this.renderTabContent();
        } catch (err) {
          notifications.showToast(`Could not close attendance: ${err.message}`, "error");
        }
      });
    }

    const cancelBtn = document.getElementById("btn-cancel-attendance");
    if (cancelBtn) {
      cancelBtn.addEventListener("click", () => {
        this.activeAttendanceSession = null;
        this.renderTabContent();
      });
    }
  }

  async renderAvailability(container) {
    const res = await api.getTeacherAvailability();
    const blocks = res?.items || [];

    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem; margin-bottom: 2rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.25rem;">Report Unavailability / Leave</h3>
        <p style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem;">
          Notify the dynamic reallocation engine of planned leaves or emergencies so lectures can be reorganized smoothly.
        </p>

        <form id="form-unavailability" style="display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));">
          <div class="form-group">
            <label class="form-label">Start Date & Time</label>
            <input type="datetime-local" class="glass-input" id="avail-start" required>
          </div>
          <div class="form-group">
            <label class="form-label">End Date & Time</label>
            <input type="datetime-local" class="glass-input" id="avail-end" required>
          </div>
          <div class="form-group" style="grid-column: 1 / -1;">
            <label class="form-label">Reason</label>
            <input type="text" class="glass-input" id="avail-reason" placeholder="e.g. Medical Leave, Academic Conference, Personal Emergency" required>
          </div>
          <div style="grid-column: 1 / -1;">
            <button type="submit" class="btn btn-primary">Submit Unavailability</button>
          </div>
        </form>
      </div>

      <div class="glass-panel" style="padding: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">My Unavailability Records</h3>
        ${blocks.length === 0 ? `
          <div class="empty-state">
            <div class="empty-state-subtitle">No unavailability blocks recorded. You are fully available.</div>
          </div>
        ` : `
          <div class="table-container">
            <table class="glass-table">
              <thead>
                <tr>
                  <th>Start Time</th>
                  <th>End Time</th>
                  <th>Reason</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                ${blocks.map(b => `
                  <tr>
                    <td>${new Date(b.starts_at).toLocaleString()}</td>
                    <td>${new Date(b.ends_at).toLocaleString()}</td>
                    <td>${this.escape(b.reason)}</td>
                    <td><span class="badge badge-reallocated">${this.escape(b.status)}</span></td>
                  </tr>
                `).join("")}
              </tbody>
            </table>
          </div>
        `}
      </div>
    `;

    const form = document.getElementById("form-unavailability");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const startVal = document.getElementById("avail-start").value;
        const endVal = document.getElementById("avail-end").value;
        const reasonVal = document.getElementById("avail-reason").value;

        if (new Date(startVal) >= new Date(endVal)) {
          notifications.showToast("Start time must precede end time", "warning");
          return;
        }

        try {
          await api.createTeacherAvailability({
            teacher_id: this.profile ? this.profile.teacher_id : null,
            starts_at: new Date(startVal).toISOString(),
            ends_at: new Date(endVal).toISOString(),
            status: "UNAVAILABLE",
            reason: reasonVal
          });
          notifications.showToast("Unavailability submitted. Schedule engine notified.", "success");
          form.reset();
          await this.renderAvailability(container);
        } catch (err) {
          notifications.showToast(`Submission failed: ${err.message}`, "error");
        }
      });
    }
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
      session_id: item.class_session_id,
      date: item.date,
      status: item.status,
      subject_code: item.subject?.code,
      subject_name: item.subject?.name,
      section_code: item.counterparty,
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
