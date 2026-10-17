/**
 * Student System — Admin Interface Component
 * System overview, master data management, timetable versions & publishing,
 * reallocation review & policies, pending lecture recovery, announcements, and reports.
 */

import { api } from "../api.js";
import { notifications } from "./notifications.js";

export class AdminView {
  constructor(appContainer) {
    this.container = appContainer;
    this.activeSection = "overview";
    this.currentResource = "users";
    this.masterDataList = [];
    this.offset = 0;
    this.limit = 25;
    this.schedulingWeights = {};
    this.reportDateTo = this.localDate(new Date());
    const firstReportDay = new Date();
    firstReportDay.setDate(firstReportDay.getDate() - 30);
    this.reportDateFrom = this.localDate(firstReportDay);
  }

  async render() {
    this.container.innerHTML = `
      <div class="view-header">
        <div>
          <div style="display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.25rem;">
            <h1 class="view-title">Administration Console</h1>
            <span class="badge badge-admin">ADMIN</span>
          </div>
          <div class="view-description">Academic Master Data, Timetable Scheduling, Reallocation Engine & Governance</div>
        </div>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" id="btn-refresh-admin">
            ↻ Refresh
          </button>
        </div>
      </div>

      <!-- Navigation Bar -->
      <div style="display: flex; gap: 0.5rem; border-bottom: 1px solid var(--glass-border); padding-bottom: 0.5rem; margin-bottom: 1.5rem; overflow-x: auto;">
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'overview' ? 'active' : ''}" data-admin-sec="overview">System Overview</button>
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'master-data' ? 'active' : ''}" data-admin-sec="master-data">Master Data</button>
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'timetables' ? 'active' : ''}" data-admin-sec="timetables">Timetables & Sessions</button>
        <button class="btn btn-primary ${this.activeSection === 'smart-timetable' ? 'active' : ''}" data-admin-sec="smart-timetable" style="font-weight:700; min-height:42px;">✦ Smart Timetable Creation</button>
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'reallocations' ? 'active' : ''}" data-admin-sec="reallocations">Reallocations & Policy</button>
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'announcements' ? 'active' : ''}" data-admin-sec="announcements">Publish Announcement</button>
        <button class="btn btn-secondary btn-sm ${this.activeSection === 'reports' ? 'active' : ''}" data-admin-sec="reports">Reports & Analytics</button>
      </div>

      <div id="admin-sec-content">
        <div class="loading-skeleton" style="height: 250px;"></div>
      </div>
    `;

    this.bindEvents();
    await this.renderSectionContent();
  }

  bindEvents() {
    this.container.querySelectorAll("[data-admin-sec]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        this.activeSection = e.currentTarget.getAttribute("data-admin-sec");
        this.container.querySelectorAll("[data-admin-sec]").forEach(b => b.classList.remove("active"));
        e.currentTarget.classList.add("active");
        await this.renderSectionContent();
      });
    });

    const refreshBtn = this.container.querySelector("#btn-refresh-admin");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => this.renderSectionContent());
    }
  }

  async renderSectionContent() {
    const content = document.getElementById("admin-sec-content");
    if (!content) return;
    content.innerHTML = `<div class="loading-skeleton" style="height: 200px;"></div>`;

    try {
      if (this.activeSection === "overview") {
        await this.renderOverview(content);
      } else if (this.activeSection === "master-data") {
        await this.renderMasterData(content);
      } else if (this.activeSection === "timetables") {
        await this.renderTimetables(content);
      } else if (this.activeSection === "smart-timetable") {
        await this.renderSmartTimetable(content);
      } else if (this.activeSection === "reallocations") {
        await this.renderReallocations(content);
      } else if (this.activeSection === "announcements") {
        await this.renderAnnouncementPublisher(content);
      } else if (this.activeSection === "reports") {
        await this.renderReports(content);
      }
    } catch (err) {
      content.innerHTML = `
        <div class="error-banner">
          <div>
            <strong>Operation Failed</strong>
            <div style="font-size: 0.85rem; color: #fca5a5;">${this.escape(err.message || 'Error occurred')}</div>
          </div>
          <button class="btn btn-secondary btn-sm" onclick="window.adminView.renderSectionContent()">Retry</button>
        </div>
      `;
    }
  }

  async renderOverview(container) {
    let health = { status: "unknown" };
    let ready = { status: "unknown" };

    try { health = await api.getSystemHealth(); } catch {}
    try { ready = await api.getSystemReady(); } catch {}

    const isHealthy = health.status === "ok";
    const isReady = ready.status === "ready" || ready.ready === true;

    container.innerHTML = `
      <div class="grid-stats">
        <div class="glass-card stat-card">
          <span class="stat-label">API Health Service</span>
          <div class="stat-value" style="color: ${isHealthy ? 'var(--color-success)' : 'var(--color-danger)'};">
            ${isHealthy ? 'Operational' : 'Degraded'}
          </div>
          <span class="stat-meta">Process status: <strong>${health.status}</strong></span>
        </div>
        <div class="glass-card stat-card">
          <span class="stat-label">Database Readiness</span>
          <div class="stat-value" style="color: ${isReady ? 'var(--color-success)' : 'var(--color-warning)'};">
            ${isReady ? 'Connected' : 'Unavailable'}
          </div>
          <span class="stat-meta">PostgreSQL primary pool</span>
        </div>
        <div class="glass-card stat-card">
          <span class="stat-label">Reallocation Mode</span>
          <div class="stat-value" style="font-size: 1.5rem; color: var(--theme-admin);">
            Approval First
          </div>
          <span class="stat-meta">Cascade depth capped at 2</span>
        </div>
      </div>

      <div class="glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.75rem;">Quick Administrative Operations</h3>
        <div style="display: flex; gap: 0.75rem; flex-wrap: wrap;">
          <button class="btn btn-primary btn-sm" onclick="window.adminView.switchSection('reallocations')">
            Manage Reallocations & Policy →
          </button>
          <button class="btn btn-primary" style="font-size:1rem; font-weight:700; padding:.85rem 1.2rem; min-height:52px;" onclick="window.adminView.switchSection('smart-timetable')">
            ✦ Smart Timetable Creation →
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.adminView.switchSection('timetables')">
            Timetable Versions & Publishing →
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.adminView.switchSection('master-data')">
            Manage Master Catalog →
          </button>
          <button class="btn btn-secondary btn-sm" onclick="window.adminView.switchSection('reports')">
            Institutional Reports →
          </button>
        </div>
      </div>
    `;
  }

  switchSection(section) {
    this.activeSection = section;
    this.container.querySelectorAll("[data-admin-sec]").forEach(b => {
      b.classList.toggle("active", b.getAttribute("data-admin-sec") === section);
    });
    this.renderSectionContent();
  }

  // --- Master Data Section ---
  async renderMasterData(container) {
    const resources = [
      { id: "users", name: "User Accounts" },
      { id: "students", name: "Students" },
      { id: "teachers", name: "Teachers" },
      { id: "courses", name: "Courses" },
      { id: "sections", name: "Sections" },
      { id: "subjects", name: "Subjects" },
      { id: "rooms", name: "Classrooms" },
      { id: "academic-years", name: "Academic Years" }
    ];

    container.innerHTML = `
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; flex-wrap: wrap; gap: 0.75rem;">
        <div style="display: flex; gap: 0.375rem; overflow-x: auto; max-width: 100%; padding-bottom: 0.25rem;">
          ${resources.map(r => `
            <button class="btn btn-sm ${this.currentResource === r.id ? 'btn-primary' : 'btn-secondary'}" data-res-tab="${r.id}">
              ${r.name}
            </button>
          `).join("")}
        </div>
        <div style="display:flex; gap:.5rem; flex-wrap:wrap;">
          <button class="btn btn-secondary btn-sm" id="btn-seed-mock-data">Load linked mock data</button>
          <button class="btn btn-primary btn-sm" id="btn-create-master-data">+ Create Record</button>
        </div>
      </div>

      <div class="glass-panel" style="padding: 1.25rem;">
        <div id="master-data-table-viewport">
          <div class="loading-skeleton" style="height: 150px;"></div>
        </div>
      </div>
    `;

    container.querySelectorAll("[data-res-tab]").forEach(btn => {
      btn.addEventListener("click", async (e) => {
        this.currentResource = e.currentTarget.getAttribute("data-res-tab");
        this.offset = 0;
        await this.renderMasterData(container);
      });
    });

    const createBtn = container.querySelector("#btn-create-master-data");
    if (createBtn) {
      createBtn.addEventListener("click", () => this.showCreateModal());
    }
    container.querySelector("#btn-seed-mock-data")?.addEventListener("click", () => this.showMockDataForm());

    await this.loadMasterData();
  }

  async loadMasterData() {
    const viewport = document.getElementById("master-data-table-viewport");
    if (!viewport) return;

    try {
      const res = await api.listMasterData(this.currentResource, { limit: this.limit, offset: this.offset });
      const items = res && res.items ? res.items : [];

      if (items.length === 0) {
        viewport.innerHTML = `
          <div class="empty-state">
            <div class="empty-state-subtitle">No records found for ${this.currentResource}.</div>
          </div>
        `;
        return;
      }

      // Extract keys from first item for columns
      const sample = items[0];
      const keys = Object.keys(sample).filter(k => !k.includes("password") && !k.includes("hash") && !k.includes("secret"));

      viewport.innerHTML = `
        <div class="table-container">
          <table class="glass-table">
            <thead>
              <tr>
                ${keys.map(k => `<th>${this.formatHeader(k)}</th>`).join("")}
                <th style="text-align: right;">Actions</th>
              </tr>
            </thead>
            <tbody>
              ${items.map(it => `
                <tr>
                  ${keys.map(k => `<td>${this.escape(it[k] !== null && it[k] !== undefined ? String(it[k]) : '-')}</td>`).join("")}
                  <td style="text-align: right;">
                    ${this.currentResource === "users" ? `
                      <button class="btn btn-danger btn-sm" onclick="window.adminView.deactivateUser('${it.user_id}')">
                        Deactivate
                      </button>
                    ` : ''}
                  </td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (err) {
      viewport.innerHTML = `
        <div class="error-banner">
          <div>Error loading ${this.currentResource}: ${this.escape(err.message)}</div>
          <button class="btn btn-secondary btn-sm" onclick="window.adminView.loadMasterData()">Retry</button>
        </div>
      `;
    }
  }

  async showCreateModal() {
    const fields = {
      users: [["login_id","Login ID","text"],["password","Temporary password (12+ characters)","password"],["email","Email","email"],["roles","Roles (comma separated)","text"]],
      students: [["login_id","Login ID","text"],["password","Temporary password (12+ characters)","password"],["email","Email","email"],["erp_id","ERP ID","text"],["full_name","Full name","text"]],
      teachers: [["login_id","Login ID","text"],["password","Temporary password (12+ characters)","password"],["email","Email","email"],["faculty_code","Faculty code","text"],["full_name","Full name","text"],["department","Department","text"]],
      "academic-years": [["name","Name","text"],["starts_on","Starts on","date"],["ends_on","Ends on","date"],["status","Status","select",["PLANNED","ACTIVE","COMPLETED"]]],
      courses: [["code","Code","text"],["name","Name","text"]],
      sections: [["course_id","Course ID","number"],["academic_year_id","Academic year ID","number"],["semester","Semester","number"],["section_code","Section code","text"],["shift","Shift","select",["MORNING","AFTERNOON","EVENING"]],["capacity","Capacity (optional)","number"]],
      subjects: [["course_id","Course","select",[]],["semester","Semester","number"],["curriculum_version","Curriculum version","text"],["subject_type","Subject type (optional)","text"],["code","Code","text"],["name","Name","text"],["requires_lab","Requires lab","checkbox"]],
      rooms: [["building","Building","text"],["room_number","Room number","text"],["capacity","Capacity","number"],["room_type","Room type","select",["NORMAL","COMPUTER_LAB","SCIENCE_LAB"]],["status","Status","select",["ACTIVE","INACTIVE"]]],
    }[this.currentResource];
    if (!fields) {
      notifications.showToast("This resource has no create form in the current API scope.", "warning");
      return;
    }
    if (this.currentResource === "subjects") {
      try {
        const courses = await api.listMasterData("courses", { limit: 100, offset: 0 });
        const options = (courses.items || []).map(course => [String(course.course_id), `${course.code} · ${course.name}`]);
        if (!options.length) { notifications.showToast("Create a course first, then link its subjects.", "warning"); return; }
        fields[0][3] = options;
      } catch (err) { notifications.showToast(`Could not load courses: ${err.message}`, "error"); return; }
    }
    const modal = document.createElement("div");
    modal.className = "modal-backdrop";
    modal.innerHTML = `<form class="modal-content glass-panel" id="master-create-form"><div class="modal-header"><h3>Create ${this.formatHeader(this.currentResource)}</h3><button class="modal-close" type="button" aria-label="Close">×</button></div>
      ${fields.map(([name,label,type,options]) => `<label class="form-group">${label}${type === "select" ? `<select class="glass-select" name="${name}" required>${(options || []).map(option=>Array.isArray(option) ? `<option value="${this.escape(option[0])}">${this.escape(option[1])}</option>` : `<option value="${this.escape(option)}">${this.escape(option)}</option>`).join("")}</select>` : type === "checkbox" ? `<input type="checkbox" name="${name}" value="true">` : `<input class="glass-input" name="${name}" type="${type}" ${name === "capacity" ? "min=\"1\"" : ""} ${!name.includes("email") && !name.includes("department") && !name.includes("capacity") ? "required" : ""}>`}</label>`).join("")}
      <button class="btn btn-primary" type="submit">Create record</button></form>`;
    document.body.appendChild(modal);
    modal.querySelector(".modal-close").addEventListener("click", () => modal.remove());
    modal.addEventListener("click", event => { if (event.target === modal) modal.remove(); });
    modal.querySelector("form").addEventListener("submit", async event => {
      event.preventDefault();
      const payload = {};
      for (const [name, value] of new FormData(event.currentTarget)) {
        const field = fields.find(item => item[0] === name);
        if ((field?.[2] === "number" || field?.[2] === "select" && name.endsWith("_id")) && value !== "") payload[name] = Number(value);
        else if (field?.[2] === "checkbox") payload[name] = true;
        else payload[name] = value;
      }
      for (const [name, , type] of fields) {
        if (type === "checkbox") payload[name] = event.currentTarget.elements[name].checked;
        if (type === "number" && !event.currentTarget.elements[name].value) delete payload[name];
      }
      if (this.currentResource === "users") payload.roles = String(payload.roles || "").split(",").map(role => role.trim().toUpperCase()).filter(Boolean);
      try {
        await api.createMasterData(this.currentResource, payload);
        modal.remove();
        notifications.showToast("Record created", "success");
        await this.loadMasterData();
      } catch (err) { notifications.showToast(`Could not create record: ${err.message}`, "error"); }
    });
  }

  async deactivateUser(userId) {
    if (!confirm(`Are you sure you want to deactivate user #${userId}?`)) return;
    try {
      await api.deleteMasterData("users", userId);
      notifications.showToast("User deactivated successfully", "success");
      await this.loadMasterData();
    } catch (err) {
      notifications.showToast(`Failed: ${err.message}`, "error");
    }
  }

  showMockDataForm() {
    const modal = document.createElement("div");
    modal.className = "modal-backdrop";
    modal.innerHTML = `<form class="modal-content glass-panel" id="mock-data-form"><div class="modal-header"><h3>Load linked mock records</h3><button class="modal-close" type="button" aria-label="Close">×</button></div>
      <p class="stat-meta" style="margin-bottom:1rem">Creates clearly labeled BCA/BBA/B courses, the requested section counts, a first-year student per section, subject-linked demo teachers, classrooms, an academic year, enrollments, curriculum links, qualifications and assignments. B receives four clearly marked demo placeholder subjects because the PDF has no B catalog. Replace them before real use. Exam dates are not loaded.</p>
      <label class="form-group">Academic year name<input class="glass-input" name="academic_year_name" value="Mock Academic Year 2026-27" maxlength="80" required></label>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:.75rem"><label class="form-group">Starts on<input class="glass-input" name="starts_on" type="date" required></label><label class="form-group">Ends on<input class="glass-input" name="ends_on" type="date" required></label></div>
      <label class="form-group">Shared demo-account password<input class="glass-input" name="demo_password" type="password" minlength="12" autocomplete="new-password" required></label>
      <button class="btn btn-primary" type="submit">Create demo dataset</button></form>`;
    document.body.appendChild(modal);
    modal.querySelector(".modal-close").addEventListener("click", () => modal.remove());
    modal.addEventListener("click", event => { if (event.target === modal) modal.remove(); });
    modal.querySelector("form").addEventListener("submit", async event => {
      event.preventDefault();
      const submit = event.currentTarget.querySelector('[type="submit"]');
      submit.disabled = true; submit.textContent = "Creating linked mock records…";
      try {
        const result = await api.seedMockData(Object.fromEntries(new FormData(event.currentTarget)));
        modal.remove();
        notifications.showToast(`Created ${result.courses} courses, ${result.sections} sections, ${result.subjects} subjects, ${result.teachers} teachers, ${result.students} students and ${result.rooms} classrooms.`, "success");
        await this.renderMasterData(document.getElementById("admin-sec-content"));
      } catch (err) { submit.disabled = false; submit.textContent = "Create demo dataset"; notifications.showToast(`Could not seed mock data: ${err.message}`, "error"); }
    });
  }

  async renderSmartTimetable(container) {
    const [yearsResult, coursesResult, sectionsResult, subjectsResult] = await Promise.all([
      api.listMasterData("academic-years", { limit: 100 }), api.listMasterData("courses", { limit: 100 }),
      api.listMasterData("sections", { limit: 100 }), api.listMasterData("subjects", { limit: 100 })
    ]);
    const years = yearsResult.items || [], courses = coursesResult.items || [];
    const sections = sectionsResult.items || [], subjects = subjectsResult.items || [];
    const dateNow = new Date();
    const today = this.localDate(dateNow);
    const end = new Date(dateNow); end.setDate(end.getDate() + 28);
    const yearOptions = years.map(year => `<option value="${year.academic_year_id}">${this.escape(year.name)} · ${year.starts_on} to ${year.ends_on}</option>`).join("");
    const courseOptions = courses.map(course => {
      // Normalize IDs at the API boundary: older/imported rows can encode foreign keys
      // differently, and a strict comparison would silently hide linked catalog rows.
      const courseId = Number(course.course_id);
      const sectionCount = sections.filter(section => Number(section.course_id) === courseId).length;
      const subjectCount = subjects.filter(subject => Number(subject.course_id) === courseId).length;
      return `<label class="glass-card" style="display:flex;align-items:center;gap:.75rem;cursor:pointer"><input type="checkbox" name="course_ids" value="${course.course_id}" ${subjectCount ? "checked" : ""}><span><strong>${this.escape(course.code)}</strong><span class="stat-meta" style="display:block">${this.escape(course.name)} · ${sectionCount} sections · ${subjectCount} subjects</span></span></label>`;
    }).join("");
    container.innerHTML = `<div class="glass-panel" style="padding:1.5rem;margin-bottom:1.25rem;border-color:var(--theme-admin)">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:1rem;flex-wrap:wrap"><div><span class="badge badge-admin">ADMIN TOOL</span><h2 style="font-size:1.6rem;margin:.6rem 0">Smart Timetable Creation</h2><p class="stat-meta">Build conflict-checked draft schedules from the linked course, section, subject, teacher-assignment and classroom records.</p></div><span style="font-size:2.5rem;color:var(--theme-admin)">✦</span></div>
      <div class="glass-card" style="margin:1rem 0"><strong>Daily windows</strong><p class="stat-meta">Morning 09:10–13:15 · Afternoon 13:30–16:30 (latest end). Four lectures per selected weekday. The form checks each configured lecture and break length against these limits.</p></div>
      ${years.length ? `<form id="smart-timetable-form" style="display:grid;gap:1rem">
        <label class="form-group">Academic year<select class="glass-select" name="academic_year_id" required>${yearOptions}</select></label>
        <fieldset style="border:0"><legend style="font-weight:600;margin-bottom:.5rem">Courses to include</legend><div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:.6rem">${courseOptions}</div></fieldset>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:.75rem"><label class="form-group">Effective from<input class="glass-input" name="effective_from" type="date" min="${years[0].starts_on}" max="${years[0].ends_on}" value="${today < years[0].starts_on ? years[0].starts_on : today}" required></label><label class="form-group">Effective to<input class="glass-input" name="effective_to" type="date" min="${years[0].starts_on}" max="${years[0].ends_on}" value="${this.localDate(end) > years[0].ends_on ? years[0].ends_on : this.localDate(end)}" required></label></div>
        <fieldset style="border:0"><legend style="font-weight:600;margin-bottom:.5rem">Required weekdays</legend><div style="display:flex;gap:.75rem;flex-wrap:wrap">${["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((day,index)=>`<label class="glass-card" style="padding:.6rem .8rem;display:flex;gap:.5rem;align-items:center"><input type="checkbox" name="weekdays" value="${index}">${day}</label>`).join("")}</div></fieldset>
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:.75rem">
          <label class="form-group">Morning start<input class="glass-input" name="morning_start" type="time" value="09:10" required></label><label class="form-group">Morning latest end<input class="glass-input" name="morning_end" type="time" value="13:15" required></label><label class="form-group">Morning lecture minutes<input class="glass-input" name="morning_lecture_minutes" type="number" min="1" max="180" value="55" required></label><label class="form-group">Break between morning lectures (min)<input class="glass-input" name="morning_break_minutes" type="number" min="0" max="60" value="5" required></label>
          <label class="form-group">Afternoon start<input class="glass-input" name="afternoon_start" type="time" value="13:30" required></label><label class="form-group">Afternoon latest end<input class="glass-input" name="afternoon_end" type="time" value="16:30" required></label><label class="form-group">Afternoon lecture minutes<input class="glass-input" name="afternoon_lecture_minutes" type="number" min="1" max="180" value="40" required></label><label class="form-group">Break between afternoon lectures (min)<input class="glass-input" name="afternoon_break_minutes" type="number" min="0" max="60" value="5" required></label>
        </div>
        <p class="stat-meta">Default duration values are editable examples. The exam PDF supplied BCA/BBA Sem-I CBCS 2026 subject data only; its exam dates/times are not treated as class meetings. B has four clearly labeled synthetic placeholder subjects because the PDF contains no B catalog.</p>
        <button class="btn btn-primary" style="min-height:58px;font-size:1.1rem;font-weight:700" type="submit">✦ Generate conflict-checked draft timetables</button>
      </form>` : `<div class="empty-state"><div class="empty-state-subtitle">Create an academic year first. Use Master Data → Load linked mock data to create the demo records.</div></div>`}
      <div id="smart-timetable-result" style="margin-top:1rem"></div></div>`;
    const yearSelect = container.querySelector('[name="academic_year_id"]');
    const fromInput = container.querySelector('[name="effective_from"]');
    const toInput = container.querySelector('[name="effective_to"]');
    const syncDates = () => {
      const year = years.find(row => row.academic_year_id === Number(yearSelect.value));
      if (!year) return;
      fromInput.min = year.starts_on; fromInput.max = year.ends_on; toInput.min = year.starts_on; toInput.max = year.ends_on;
      if (fromInput.value < year.starts_on || fromInput.value > year.ends_on) fromInput.value = year.starts_on;
      if (toInput.value < year.starts_on || toInput.value > year.ends_on) toInput.value = year.ends_on;
    };
    yearSelect?.addEventListener("change", syncDates);
    container.querySelector("#smart-timetable-form")?.addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const resultEl = container.querySelector("#smart-timetable-result");
      const submit = form.querySelector('[type="submit"]');
      const values = Object.fromEntries(new FormData(form));
      const numeric = ["academic_year_id", "morning_lecture_minutes", "morning_break_minutes", "afternoon_lecture_minutes", "afternoon_break_minutes"];
      for (const name of numeric) values[name] = Number(values[name]);
      values.lectures_per_day = 4;
      values.course_ids = [...form.querySelectorAll('[name="course_ids"]:checked')].map(input => Number(input.value));
      values.weekdays = [...form.querySelectorAll('[name="weekdays"]:checked')].map(input => Number(input.value));
      submit.disabled = true; submit.textContent = "Checking academic records and overlaps…";
      try {
        const response = await api.generateSmartTimetable(values);
        const partials = response.partial_exclusions || [];
        resultEl.innerHTML = `<div class="glass-card" style="border-color:var(--color-success)"><div><strong>Drafts generated. Nothing has been published.</strong><p>${response.sections} sections · ${response.generated_entries} recurring entries · ${response.required_dates.length} required dates · ${response.excluded_dates.length} fully excluded dates.</p><details><summary>Show ${response.required_dates.length} required dates</summary><p>${response.required_dates.map(date=>this.escape(date)).join(", ") || "None"}</p></details>${response.excluded_dates.length ? `<p>Fully excluded dates: ${response.excluded_dates.map(date=>this.escape(date)).join(", ")}</p>` : ""}${partials.length ? `<details><summary>${partials.length} dates have partial holiday/exam exclusions</summary><ul>${partials.map(item=>`<li>${this.escape(item.date)} · ${item.excluded_class_count} class(es) excluded · ${item.exclusions.map(row=>this.escape(row.reason.join(", "))).join("; ")}</li>`).join("")}</ul></details>` : `<p>No holiday or exam overlaps were found in the selected date range.</p>`}<div style="display:grid;gap:.4rem;margin-top:.6rem">${response.versions.map(version=>`<button type="button" class="btn btn-secondary btn-sm" data-open-smart-version="${version.timetable_version_id}">Review ${this.escape(version.name)} (${version.entry_count} entries)</button>`).join("")}</div></div></div>`;
        resultEl.querySelectorAll("[data-open-smart-version]").forEach(button => button.addEventListener("click", () => this.openGeneratedVersion(Number(button.dataset.openSmartVersion))));
        notifications.showToast("Smart timetable drafts created; review before publishing.", "success");
      } catch (err) { resultEl.innerHTML = `<div class="error-banner">${this.escape(err.message || "Could not generate draft timetables")}</div>`; }
      finally { submit.disabled = false; submit.textContent = "✦ Generate conflict-checked draft timetables"; }
    });
  }

  async openGeneratedVersion(versionId) {
    this.activeSection = "timetables";
    this.container.querySelectorAll("[data-admin-sec]").forEach(button => button.classList.toggle("active", button.dataset.adminSec === "timetables"));
    await this.renderSectionContent();
    await this.loadTimetableVersion(versionId);
  }

  // --- Timetables Section ---
  async renderTimetables(container) {
    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem;">
          <h3 style="font-size: 1.125rem; font-weight: 600;">Timetable Versions & Publication</h3>
        </div>
        <p style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem;">
          Publishing a draft timetable atomically validates all constraints and generates dated class sessions across the academic term, skipping exams and holidays.
        </p>
        <form id="form-create-version" class="glass-card" style="display:grid; gap:.75rem; grid-template-columns:repeat(auto-fit,minmax(160px,1fr)); margin-bottom:1rem;">
          <label class="form-group">Section ID<input class="glass-input" name="section_id" type="number" min="1" required></label>
          <label class="form-group">Version name<input class="glass-input" name="name" maxlength="160" required></label>
          <label class="form-group">Effective from<input class="glass-input" name="effective_from" type="date" required></label>
          <label class="form-group">Effective to<input class="glass-input" name="effective_to" type="date" required></label>
          <button class="btn btn-primary" type="submit">Create draft</button>
        </form>
        <form id="form-load-version" style="display:flex; gap:.5rem; max-width:360px; margin-bottom:1rem;">
          <label class="form-group" style="flex:1">Load existing version by ID<input class="glass-input" name="version_id" type="number" min="1" required></label>
          <button class="btn btn-secondary" type="submit">Load</button>
        </form>
        <p class="stat-meta">The current API does not expose a version collection list, so existing versions must be loaded by ID.</p>
        <div id="timetable-versions-list">
          <div class="empty-state"><div class="empty-state-subtitle">Create a draft or load a version by ID.</div></div>
        </div>
      </div>

      <div class="glass-panel" style="padding: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">Academic Calendar & Events</h3>
        <div id="academic-events-list">
          <div class="loading-skeleton" style="height: 100px;"></div>
        </div>
      </div>
    `;

    this.container.querySelector("#form-create-version")?.addEventListener("submit", async event => {
      event.preventDefault();
      const form = event.currentTarget;
      const payload = Object.fromEntries(new FormData(form));
      payload.section_id = Number(payload.section_id);
      try {
        const created = await api.createTimetableVersion(payload);
        this.currentTimetableVersionId = created.timetable_version_id;
        notifications.showToast(`Draft version #${created.timetable_version_id} created`, "success");
        await this.loadTimetableVersion(created.timetable_version_id);
      } catch (err) { notifications.showToast(`Could not create draft: ${err.message}`, "error"); }
    });
    this.container.querySelector("#form-load-version")?.addEventListener("submit", async event => {
      event.preventDefault();
      await this.loadTimetableVersion(Number(new FormData(event.currentTarget).get("version_id")));
    });
    await this.loadAcademicEvents();
  }

  async loadTimetableVersion(versionId) {
    const el = document.getElementById("timetable-versions-list");
    if (!el) return;
    try {
      const version = await api.getTimetableVersion(versionId);
      this.currentTimetableVersionId = versionId;
      el.innerHTML = `
        <div class="glass-card">
          <div style="display:flex; justify-content:space-between; gap:1rem; flex-wrap:wrap; align-items:center">
            <div><h4>Version #${version.timetable_version_id} · Section ${version.section_id}</h4><p class="stat-meta">${this.escape(version.name)} · ${version.effective_from} to ${version.effective_to}</p></div>
            <span class="badge ${version.status === "PUBLISHED" ? "badge-present" : "badge-scheduled"}">${this.escape(version.status)}</span>
          </div>
          ${version.status === "DRAFT" ? `<button type="button" class="btn btn-secondary btn-sm" id="btn-add-timetable-entry">Add timetable entry</button> <button type="button" class="btn btn-success btn-sm" id="btn-publish-timetable">Publish version</button>` : ""}
          <div class="table-container"><table class="glass-table"><thead><tr><th>Entry</th><th>Assignment</th><th>Room</th><th>Weekday</th><th>Time</th><th>Actions</th></tr></thead><tbody>
          ${(version.entries || []).map(entry => `<tr><td>${entry.entry_id}</td><td>${entry.teaching_assignment_id}</td><td>${entry.room_id}</td><td>${["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][entry.weekday]}</td><td>${entry.starts_at_local}–${entry.ends_at_local}</td><td>${version.status === "DRAFT" ? `<button class="btn btn-secondary btn-sm" data-edit-entry="${entry.entry_id}">Edit</button> <button class="btn btn-danger btn-sm" data-delete-entry="${entry.entry_id}">Remove</button>` : "Immutable"}</td></tr>`).join("") || `<tr><td colspan="6">No entries yet.</td></tr>`}
          </tbody></table></div>
        </div>
      `;
      el.querySelector("#btn-add-timetable-entry")?.addEventListener("click", () => this.editTimetableEntry(version, null));
      el.querySelector("#btn-publish-timetable")?.addEventListener("click", () => this.publishVersion(versionId));
      el.querySelectorAll("[data-edit-entry]").forEach(button => button.addEventListener("click", () => this.editTimetableEntry(version, version.entries.find(row => row.entry_id === Number(button.dataset.editEntry)))));
      el.querySelectorAll("[data-delete-entry]").forEach(button => button.addEventListener("click", () => this.removeTimetableEntry(Number(button.dataset.deleteEntry), versionId)));
    } catch (err) {
      el.innerHTML = `<div class="error-banner"><div>Could not load timetable version: ${this.escape(err.message)}</div></div>`;
    }
  }

  async editTimetableEntry(version, entry) {
    const modal = document.createElement("div");
    modal.className = "modal-backdrop";
    modal.innerHTML = `<form class="modal-content glass-panel" id="timetable-entry-form"><div class="modal-header"><h3>${entry ? "Edit" : "Add"} draft entry</h3><button class="modal-close" type="button" aria-label="Close">×</button></div>
      <label class="form-group">Teaching assignment ID<input class="glass-input" name="teaching_assignment_id" type="number" min="1" required value="${entry?.teaching_assignment_id ?? ""}"></label>
      <label class="form-group">Room ID<input class="glass-input" name="room_id" type="number" min="1" required value="${entry?.room_id ?? ""}"></label>
      <label class="form-group">Weekday<select class="glass-select" name="weekday">${["Monday","Tuesday","Wednesday","Thursday","Friday","Saturday","Sunday"].map((name,index)=>`<option value="${index}" ${entry?.weekday===index?"selected":""}>${name}</option>`).join("")}</select></label>
      <label class="form-group">Start time<input class="glass-input" name="starts_at_local" type="time" required value="${entry?.starts_at_local?.slice(0,5) || "09:00"}"></label>
      <label class="form-group">End time<input class="glass-input" name="ends_at_local" type="time" required value="${entry?.ends_at_local?.slice(0,5) || "10:00"}"></label>
      <button class="btn btn-primary" type="submit">Save entry</button></form>`;
    document.body.appendChild(modal);
    modal.querySelector(".modal-close").addEventListener("click", () => modal.remove());
    modal.addEventListener("click", event => { if (event.target === modal) modal.remove(); });
    modal.querySelector("form").addEventListener("submit", async event => {
      event.preventDefault();
      const values = Object.fromEntries(new FormData(event.currentTarget));
      values.teaching_assignment_id = Number(values.teaching_assignment_id);
      values.room_id = Number(values.room_id);
      values.weekday = Number(values.weekday);
      try {
        if (entry) await api.updateTimetableEntry(entry.entry_id, values);
        else await api.createTimetableEntry(version.timetable_version_id, values);
        modal.remove();
        notifications.showToast("Draft entry saved", "success");
        await this.loadTimetableVersion(version.timetable_version_id);
      } catch (err) { notifications.showToast(`Could not save entry: ${err.message}`, "error"); }
    });
  }

  async removeTimetableEntry(entryId, versionId) {
    if (!confirm("Remove this draft timetable entry?")) return;
    try { await api.deleteTimetableEntry(entryId); await this.loadTimetableVersion(versionId); }
    catch (err) { notifications.showToast(`Could not remove entry: ${err.message}`, "error"); }
  }

  async publishVersion(versionId) {
    if (!confirm(`Publishing timetable version #${versionId} will generate dated sessions for the entire term. Continue?`)) return;
    try {
      await api.publishTimetableVersion(versionId);
      notifications.showToast("Timetable successfully published! Sessions generated.", "success");
      await this.loadTimetableVersion(versionId);
    } catch (err) {
      notifications.showToast(`Publishing failed: ${err.message}`, "error");
    }
  }

  async loadAcademicEvents() {
    const el = document.getElementById("academic-events-list");
    if (!el) return;
    try {
      const res = await api.getAcademicEvents();
      const events = res && res.items ? res.items : [];
      if (events.length === 0) {
        el.innerHTML = `<div class="empty-state"><div class="empty-state-subtitle">No holidays or exam closures recorded.</div></div>`;
        return;
      }
      el.innerHTML = `
        <div class="table-container">
          <table class="glass-table">
            <thead>
              <tr><th>Title</th><th>Type</th><th>Start</th><th>End</th></tr>
            </thead>
            <tbody>
              ${events.map(e => `
                <tr>
                  <td style="font-weight: 600;">${this.escape(e.title)}</td>
                  <td><span class="badge badge-reallocated">${e.event_type}</span></td>
                  <td>${new Date(e.starts_at).toLocaleString()}</td>
                  <td>${new Date(e.ends_at).toLocaleString()}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (err) {
      el.innerHTML = `<div class="error-banner"><div>Events: ${this.escape(err.message)}</div></div>`;
    }
  }

  // --- Reallocations & Policy Section ---
  async renderReallocations(container) {
    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.5rem;">Scheduling & Reallocation Policy</h3>
        <p style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem;">
          Configure engine behavior: automatic application mode and cascade depth bounds (default 1, max 2).
        </p>

        <form id="form-scheduling-policy" style="display: grid; gap: 1rem; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));">
          <div class="form-group">
            <label class="form-label">Auto-Apply Changes</label>
            <select class="glass-select" id="policy-auto-apply">
              <option value="false">Disabled (Suggest & Approve)</option>
              <option value="true">Enabled (Auto-apply within depth)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label">Max Automatic Cascade Depth</label>
            <input type="number" class="glass-input" id="policy-max-depth" min="1" max="2" value="1">
          </div>
          <div style="grid-column: 1 / -1;">
            <button type="submit" class="btn btn-primary">Save Policy</button>
          </div>
        </form>
      </div>

      <div class="glass-panel" style="padding: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.5rem;">Simulate / Trigger Unavailability Analysis</h3>
        <p style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem;">
          Run dynamic reallocation analysis on unavailable faculty or room blocks to generate atomic candidate proposals.
        </p>
        <div style="display: flex; gap: 0.5rem;">
          <button class="btn btn-secondary btn-sm" id="btn-run-realloc-check">Check Pending Reallocations</button>
        </div>
      </div>
    `;

    await this.loadSchedulingPolicy();
  }

  async loadSchedulingPolicy() {
    try {
      const res = await api.getSchedulingPolicy();
      const policy = (res?.items || []).find(item => item.scope === "INSTITUTION") || {};
      this.schedulingWeights = policy.scoring_weights || {};
      const autoSel = document.getElementById("policy-auto-apply");
      const depthInp = document.getElementById("policy-max-depth");
      if (autoSel) autoSel.value = String(policy.reallocation_mode === "AUTO_APPLY");
      if (depthInp) depthInp.value = String(policy.max_cascade_depth || 1);
    } catch (err) {
      console.warn("Could not load policy:", err);
    }

    const form = document.getElementById("form-scheduling-policy");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        try {
          await api.updateSchedulingPolicy({
            scope: "INSTITUTION",
            reallocation_mode: document.getElementById("policy-auto-apply").value === "true" ? "AUTO_APPLY" : "SUGGEST_AND_APPROVE",
            max_cascade_depth: parseInt(document.getElementById("policy-max-depth").value, 10),
            scoring_weights: this.schedulingWeights
          });
          notifications.showToast("Scheduling policy updated successfully!", "success");
        } catch (err) {
          notifications.showToast(`Failed to update policy: ${err.message}`, "error");
        }
      });
    }
  }

  // --- Announcement Publisher ---
  async renderAnnouncementPublisher(container) {
    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem; max-width: 650px;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 0.25rem;">Publish Institutional Announcement</h3>
        <p style="font-size: 0.875rem; color: var(--text-muted); margin-bottom: 1.25rem;">
          Post announcements to target audiences (All, Students, Teachers, or Specific Section). Notifications are delivered instantly via WebSocket.
        </p>

        <form id="form-publish-announcement">
          <div class="form-group">
            <label class="form-label">Announcement Title</label>
            <input type="text" class="glass-input" id="ann-title" placeholder="e.g. Schedule Revision Notice / Mid-Term Schedule" required>
          </div>

          <div class="form-group">
            <label class="form-label">Target Audience Scope</label>
            <select class="glass-select" id="ann-audience" required>
              <option value="ALL">Entire Institution (ALL)</option>
              <option value="STUDENTS">Students Only</option>
              <option value="TEACHERS">Teachers Only</option>
              <option value="SECTION">Specific Section</option>
            </select>
          </div>

          <div class="form-group" id="ann-section-wrapper" style="display: none;">
            <label class="form-label">Section ID</label>
            <input type="number" class="glass-input" id="ann-section-id" placeholder="Enter target Section ID">
          </div>

          <div class="form-group">
            <label class="form-label">Expiry Date & Time (Optional)</label>
            <input type="datetime-local" class="glass-input" id="ann-expires">
          </div>

          <div class="form-group">
            <label class="form-label">Announcement Body</label>
            <textarea class="glass-textarea" id="ann-body" rows="4" placeholder="Enter detailed announcement text..." required></textarea>
          </div>

          <button type="submit" class="btn btn-primary">Publish Announcement</button>
        </form>
      </div>
    `;

    const audSel = document.getElementById("ann-audience");
    const secWrap = document.getElementById("ann-section-wrapper");
    if (audSel && secWrap) {
      audSel.addEventListener("change", () => {
        secWrap.style.display = audSel.value === "SECTION" ? "block" : "none";
      });
    }

    const form = document.getElementById("form-publish-announcement");
    if (form) {
      form.addEventListener("submit", async (e) => {
        e.preventDefault();
        const title = document.getElementById("ann-title").value;
        const body = document.getElementById("ann-body").value;
        const audience_scope = document.getElementById("ann-audience").value;
        const sectionIdVal = document.getElementById("ann-section-id").value;
        const expiresVal = document.getElementById("ann-expires").value;

        const payload = {
          title,
          body,
          audience_scope
        };
        if (audience_scope === "SECTION" && sectionIdVal) {
          payload.section_id = parseInt(sectionIdVal, 10);
        }
        if (expiresVal) {
          payload.expires_at = new Date(expiresVal).toISOString();
        }

        try {
          await api.publishAnnouncement(payload);
          notifications.showToast("Announcement published and notifications queued!", "success");
          form.reset();
        } catch (err) {
          notifications.showToast(`Publish failed: ${err.message}`, "error");
        }
      });
    }
  }

  // --- Reports Section ---
  async renderReports(container) {
    const reportTypes = [
      { id: "attendance", name: "Attendance Summary" },
      { id: "teacher-workload", name: "Teacher Workload & Free Gaps" },
      { id: "room-utilization", name: "Room Booked Minutes" },
      { id: "sessions", name: "Session Status Counts" },
      { id: "curriculum-progress", name: "Curriculum Syllabus Progress" }
    ];

    container.innerHTML = `
      <div class="glass-panel" style="padding: 1.5rem; margin-bottom: 1.5rem;">
        <h3 style="font-size: 1.125rem; font-weight: 600; margin-bottom: 1rem;">Institutional Reports & Metrics</h3>
        <div style="display: flex; gap: 1rem; flex-wrap: wrap; align-items: flex-end;">
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">Report Category</label>
            <select class="glass-select" id="report-type-select">
              ${reportTypes.map(r => `<option value="${r.id}">${r.name}</option>`).join("")}
            </select>
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">From Date</label>
            <input type="date" class="glass-input" id="report-from" value="${this.reportDateFrom}">
          </div>
          <div class="form-group" style="margin-bottom: 0;">
            <label class="form-label">To Date</label>
            <input type="date" class="glass-input" id="report-to" value="${this.reportDateTo}">
          </div>
          <button class="btn btn-primary" id="btn-fetch-report">Generate Report</button>
        </div>
      </div>

      <div class="glass-panel" style="padding: 1.5rem;">
        <div id="report-results-viewport">
          <div class="empty-state">
            <div class="empty-state-subtitle">Select date parameters and click Generate Report.</div>
          </div>
        </div>
      </div>
    `;

    const fetchBtn = document.getElementById("btn-fetch-report");
    if (fetchBtn) {
      fetchBtn.addEventListener("click", () => this.generateReport());
    }
  }

  async generateReport() {
    const type = document.getElementById("report-type-select").value;
    const from = document.getElementById("report-from").value;
    const to = document.getElementById("report-to").value;
    const viewport = document.getElementById("report-results-viewport");
    if (!viewport) return;

    viewport.innerHTML = `<div class="loading-skeleton" style="height: 150px;"></div>`;

    try {
      const data = await api.getReports(type, from, to);
      const items = data?.items || (type === "sessions"
        ? Object.entries(data?.counts || {}).map(([status, count]) => ({ status, count }))
        : (Array.isArray(data) ? data : []));

      if (items.length === 0) {
        viewport.innerHTML = `<div class="empty-state"><div class="empty-state-subtitle">No records found for this period.</div></div>`;
        return;
      }

      const sample = items[0];
      const keys = typeof sample === 'object' && sample !== null ? Object.keys(sample) : ['value'];

      viewport.innerHTML = `
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.75rem;">
          <h4 style="font-weight: 700;">Report: ${type.toUpperCase()}</h4>
          <span class="badge" style="background: rgba(255,255,255,0.06);">${items.length} Record${items.length > 1 ? 's' : ''}</span>
        </div>
        <div class="table-container">
          <table class="glass-table">
            <thead>
              <tr>${keys.map(k => `<th>${this.formatHeader(k)}</th>`).join("")}</tr>
            </thead>
            <tbody>
              ${items.map(it => `
                <tr>
                  ${keys.map(k => `<td>${this.escape(it[k] !== undefined ? (typeof it[k] === "object" && it[k] !== null ? JSON.stringify(it[k]) : String(it[k])) : '-')}</td>`).join("")}
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      `;
    } catch (err) {
      viewport.innerHTML = `<div class="error-banner"><div>Report failed: ${this.escape(err.message)}</div></div>`;
    }
  }

  formatHeader(str) {
    return str.replace(/_/g, " ").toUpperCase();
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

  localDate(value) {
    const year = value.getFullYear();
    const month = String(value.getMonth() + 1).padStart(2, "0");
    const day = String(value.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }
}
