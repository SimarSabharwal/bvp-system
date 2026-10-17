/**
 * Student System — Shared API Client
 * Cookie session handling, session-bound CSRF token, normalized error formatting.
 */

export class ApiClient {
  constructor() {
    this.baseUrl = "/api/v1";
    this.csrfToken = null;
    this.currentUser = null;
    this.onSessionExpired = null;
    this.onRequestError = null;
  }

  async initSession() {
    try {
      const res = await this.getCurrentUser();
      if (res && res.user) {
        this.currentUser = res.user;
        await this.fetchCsrfToken();
        return this.currentUser;
      }
    } catch {
      this.currentUser = null;
    }
    return null;
  }

  async fetchCsrfToken() {
    try {
      const res = await fetch(`${this.baseUrl}/auth/csrf`, {
        method: "GET",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      if (res.ok) {
        const data = await res.json();
        this.csrfToken = data.csrf_token;
        return this.csrfToken;
      }
    } catch (err) {
      console.warn("CSRF fetch failed:", err);
    }
    return null;
  }

  async request(path, options = {}) {
    const method = (options.method || "GET").toUpperCase();
    const headers = {
      "Accept": "application/json",
      ...(options.headers || {})
    };

    if (options.body && typeof options.body === "object" && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(options.body);
    }

    // Require CSRF token for state-changing operations (except login which has no cookie yet)
    if (["POST", "PUT", "PATCH", "DELETE"].includes(method) && !path.includes("/auth/login")) {
      if (!this.csrfToken) {
        await this.fetchCsrfToken();
      }
      if (this.csrfToken) {
        headers["X-CSRF-Token"] = this.csrfToken;
      }
    }

    options.credentials = "same-origin";
    // Academic master data can change while an admin is working (for example,
    // after loading demo records). Avoid stale cached API lists in forms that
    // depend on related course/section/subject records.
    options.cache = options.cache || "no-store";
    options.headers = headers;

    const url = path.startsWith("http") ? path : `${this.baseUrl}${path.startsWith('/') ? '' : '/'}${path}`;
    
    let response;
    try {
      response = await fetch(url, options);
    } catch (networkError) {
      const err = {
        code: "network_error",
        message: "Failed to connect to the server. Please check your network connection.",
        details: [networkError.message]
      };
      if (this.onRequestError) this.onRequestError(err);
      throw err;
    }

    if (response.status === 401 && !path.includes("/auth/login")) {
      const hadAuthenticatedSession = Boolean(this.currentUser);
      this.currentUser = null;
      if (hadAuthenticatedSession && this.onSessionExpired) {
        this.onSessionExpired();
      }
      const err = {
        code: "session_expired",
        message: "Your session has expired. Please sign in again.",
        details: []
      };
      throw err;
    }

    let payload = null;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
      try {
        payload = await response.json();
      } catch {
        payload = null;
      }
    }

    if (!response.ok) {
      const apiError = payload && payload.error ? payload.error : {
        code: `http_${response.status}`,
        message: response.statusText || "Request failed",
        details: [],
        request_id: response.headers.get("X-Request-ID")
      };
      if (this.onRequestError) this.onRequestError(apiError);
      throw apiError;
    }

    return payload;
  }

  // --- Auth APIs ---
  async login(loginId, password, activeRole = null) {
    const body = { login_id: loginId, password };
    if (activeRole) body.active_role = activeRole;
    const res = await this.request("/auth/login", {
      method: "POST",
      body
    });
    const identity = await this.getCurrentUser();
    this.currentUser = identity.user;
    await this.fetchCsrfToken();
    return identity.user;
  }

  async logout() {
    try {
      await this.request("/auth/logout", { method: "POST" });
    } finally {
      this.currentUser = null;
      this.csrfToken = null;
    }
  }

  async getCurrentUser() {
    return await this.request("/auth/me");
  }

  // --- Student APIs ---
  async getStudentProfile() {
    return await this.request("/students/me");
  }

  async getStudentSchedule(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/schedule/me${q ? '?' + q : ''}`);
  }

  async getStudentAttendance(from, to) {
    const q = new URLSearchParams({ from, to }).toString();
    return await this.request(`/students/me/attendance?${q}`);
  }

  // --- Teacher APIs ---
  async getTeacherProfile() {
    return await this.request("/teachers/me");
  }

  async getTeacherSchedule(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/schedule/me${q ? '?' + q : ''}`);
  }

  async openAttendance(classSessionId) {
    return await this.request(`/class-sessions/${classSessionId}/attendance/open`, { method: "POST" });
  }

  async getAttendanceRoster(classSessionId) {
    return await this.request(`/teacher/class-sessions/${classSessionId}/attendance`);
  }

  async recordAttendance(attendanceSessionId, studentId, status) {
    return await this.request(`/attendance-sessions/${attendanceSessionId}/records/${studentId}`, {
      method: "PUT",
      body: { status }
    });
  }

  async closeAttendance(attendanceSessionId) {
    return await this.request(`/attendance-sessions/${attendanceSessionId}/close`, { method: "POST" });
  }

  async getTeacherAvailability() {
    return await this.request("/admin/teacher-availability");
  }

  async createTeacherAvailability(data) {
    return await this.request("/admin/teacher-availability", { method: "POST", body: data });
  }

  async updateTeacherAvailability(id, data) {
    return await this.request(`/admin/teacher-availability/${id}`, { method: "PATCH", body: data });
  }

  // --- Admin Master Data & Operations ---
  async getSystemHealth() {
    return await this.request("/health");
  }

  async getSystemReady() {
    return await this.request("/ready");
  }

  async listMasterData(resource, params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/admin/${resource}${q ? '?' + q : ''}`);
  }

  async createMasterData(resource, data) {
    return await this.request(`/admin/${resource}`, { method: "POST", body: data });
  }

  async seedMockData(data) {
    return await this.request("/admin/mock-data/seed", { method: "POST", body: data });
  }

  async getMasterData(resource, id) {
    return await this.request(`/admin/${resource}/${id}`);
  }

  async updateMasterData(resource, id, data) {
    return await this.request(`/admin/${resource}/${id}`, { method: "PATCH", body: data });
  }

  async deleteMasterData(resource, id) {
    return await this.request(`/admin/${resource}/${id}`, { method: "DELETE" });
  }

  async getLookups(resource) {
    return await this.request(`/lookups/${resource}`);
  }

  // Timetable
  async createTimetableVersion(data) {
    return await this.request("/admin/timetable-versions", { method: "POST", body: data });
  }

  async generateSmartTimetable(data) {
    return await this.request("/admin/smart-timetables/generate", { method: "POST", body: data });
  }

  async getTimetableVersion(id) {
    return await this.request(`/admin/timetable-versions/${id}`);
  }

  async createTimetableEntry(versionId, data) {
    return await this.request(`/admin/timetable-versions/${versionId}/entries`, { method: "POST", body: data });
  }

  async updateTimetableEntry(entryId, data) {
    return await this.request(`/admin/timetable-entries/${entryId}`, { method: "PATCH", body: data });
  }

  async deleteTimetableEntry(entryId) {
    return await this.request(`/admin/timetable-entries/${entryId}`, { method: "DELETE" });
  }

  async publishTimetableVersion(versionId) {
    return await this.request(`/admin/timetable-versions/${versionId}/publish`, { method: "POST" });
  }

  async getAdminSchedules(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/admin/schedules${q ? '?' + q : ''}`);
  }

  async getFreeSlots(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/admin/free-slots${q ? '?' + q : ''}`);
  }

  // Reallocation
  async analyzeReallocation(data) {
    return await this.request("/admin/reallocations/analyze", { method: "POST", body: data });
  }

  async reallocationDecision(id, status) {
    return await this.request(`/admin/reallocations/${id}/decision`, {
      method: "POST",
      body: { status }
    });
  }

  async revertReallocation(id) {
    return await this.request(`/admin/reallocations/${id}/revert`, { method: "POST" });
  }

  async getSchedulingPolicy() {
    return await this.request("/admin/scheduling-policy");
  }

  async updateSchedulingPolicy(data) {
    return await this.request("/admin/scheduling-policy", { method: "PUT", body: data });
  }

  async getPendingCandidates(pendingId) {
    return await this.request(`/admin/pending-lectures/${pendingId}/candidates`);
  }

  async proposePendingRecovery(pendingId, data) {
    return await this.request(`/admin/pending-lectures/${pendingId}/propose-recovery`, { method: "POST", body: data });
  }

  async resolvePendingLecture(pendingId, data) {
    return await this.request(`/admin/pending-lectures/${pendingId}/resolve`, { method: "POST", body: data });
  }

  // Calendar & Events
  async getAcademicEvents() {
    return await this.request("/admin/academic-events");
  }

  async createAcademicEvent(data) {
    return await this.request("/admin/academic-events", { method: "POST", body: data });
  }

  // Communications & Notifications
  async getNotifications(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/notifications${q ? '?' + q : ''}`);
  }

  async markNotificationRead(id) {
    return await this.request(`/notifications/${id}/read`, { method: "PUT" });
  }

  async getAnnouncements(params = {}) {
    const q = new URLSearchParams(params).toString();
    return await this.request(`/announcements${q ? '?' + q : ''}`);
  }

  async publishAnnouncement(data) {
    return await this.request("/admin/announcements", { method: "POST", body: data });
  }

  // Reports
  async getReports(type, from, to) {
    const q = new URLSearchParams({ from, to }).toString();
    return await this.request(`/admin/reports/${type}?${q}`);
  }
}

export const api = new ApiClient();
