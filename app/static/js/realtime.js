/**
 * Student System — Realtime WebSocket & Polling Fallback Client
 * Connects to the existing /api/v1/ws/events route, tracks notification cursor,
 * auto-reconnects, and falls back to polling.
 */

import { api } from "./api.js";

export class RealtimeClient {
  constructor() {
    this.socket = null;
    this.cursor = 0;
    this.isConnected = false;
    this.shouldReconnect = false;
    this.connectionGeneration = 0;
    this.reconnectAttempts = 0;
    this.maxReconnectDelay = 30000;
    this.reconnectTimer = null;
    this.pollingTimer = null;
    this.listeners = {
      notification: [],
      refresh: [],
      statusChange: [],
      sessionExpired: []
    };
  }

  on(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event].push(callback);
    }
  }

  off(event, callback) {
    if (this.listeners[event]) {
      this.listeners[event] = this.listeners[event].filter(cb => cb !== callback);
    }
  }

  emit(event, data) {
    if (this.listeners[event]) {
      this.listeners[event].forEach(cb => {
        try { cb(data); } catch (e) { console.error(`Error in ${event} listener:`, e); }
      });
    }
  }

  connect(cursor = null) {
    if (cursor !== null) {
      this.cursor = cursor;
    }
    this.disconnect(true);
    this.shouldReconnect = true;
    const generation = this.connectionGeneration;

    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    const wsUrl = `${protocol}//${window.location.host}/api/v1/ws/events?after_id=${this.cursor}`;

    try {
      const socket = new WebSocket(wsUrl);
      this.socket = socket;

      socket.onopen = () => {
        if (generation !== this.connectionGeneration || this.socket !== socket) return;
        this.isConnected = true;
        this.reconnectAttempts = 0;
        this.stopPollingFallback();
        this.emit("statusChange", { connected: true, transport: "websocket" });
      };

      socket.onmessage = (event) => {
        if (generation !== this.connectionGeneration || this.socket !== socket) return;
        try {
          const msg = JSON.parse(event.data);
          this.handleMessage(msg);
        } catch (err) {
          console.warn("Failed to parse WebSocket message:", err);
        }
      };

      socket.onerror = (err) => {
        if (generation !== this.connectionGeneration || this.socket !== socket) return;
        console.warn("WebSocket error:", err);
      };

      socket.onclose = (event) => {
        if (generation !== this.connectionGeneration || this.socket !== socket) return;
        this.socket = null;
        this.isConnected = false;
        this.emit("statusChange", { connected: false, reason: event.reason });
        if (event.reason === "Session expired") {
          this.disconnect(true);
          this.emit("sessionExpired");
          return;
        }
        if (this.shouldReconnect) this.scheduleReconnect();
      };
    } catch (err) {
      console.warn("Could not initiate WebSocket:", err);
      if (this.shouldReconnect) this.scheduleReconnect();
    }
  }

  handleMessage(msg) {
    if (!msg || !msg.type) return;

    switch (msg.type) {
      case "connected":
        if (typeof msg.after_id === "number") {
          this.cursor = Math.max(this.cursor, msg.after_id);
        }
        break;

      case "notification":
        if (msg.data) {
          if (msg.data.notification_id && msg.data.notification_id > this.cursor) {
            this.cursor = msg.data.notification_id;
          }
          this.emit("notification", msg.data);
        }
        break;

      case "refresh":
        if (typeof msg.cursor === "number") {
          this.cursor = Math.max(this.cursor, msg.cursor);
        }
        this.emit("refresh", { cursor: this.cursor });
        break;

      case "heartbeat":
        if (typeof msg.cursor === "number") {
          this.cursor = Math.max(this.cursor, msg.cursor);
        }
        break;

      case "session_expired":
        this.disconnect(true);
        this.emit("sessionExpired");
        break;

      default:
        console.debug("Unhandled realtime message:", msg);
    }
  }

  scheduleReconnect() {
    if (!this.shouldReconnect || this.reconnectTimer) return;
    this.startPollingFallback();

    const delay = Math.min(1000 * Math.pow(1.5, this.reconnectAttempts), this.maxReconnectDelay);
    this.reconnectAttempts++;

    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null;
      if (this.shouldReconnect) this.connect();
    }, delay);
  }

  startPollingFallback() {
    if (this.pollingTimer) return;
    this.emit("statusChange", { connected: false, transport: "polling" });
    
    // Poll immediately, then every 20 seconds
    this.pollNotifications();
    this.pollingTimer = setInterval(() => {
      this.pollNotifications();
    }, 20000);
  }

  stopPollingFallback() {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer);
      this.pollingTimer = null;
    }
  }

  async pollNotifications() {
    const generation = this.connectionGeneration;
    try {
      const res = await api.getNotifications({ after_id: this.cursor, limit: 50 });
      if (res && Array.isArray(res.items)) {
        res.items.forEach(item => {
          if (item.notification_id > this.cursor) {
            this.cursor = item.notification_id;
          }
          this.emit("notification", item);
        });
        if (res.items.length > 0) {
          this.emit("refresh", { cursor: this.cursor });
        }
      }
    } catch (err) {
      if (err.code === "session_expired" && generation === this.connectionGeneration && this.shouldReconnect) {
        this.disconnect(true);
        this.emit("sessionExpired");
      }
    }
  }

  disconnect(clearTimers = true) {
    this.shouldReconnect = false;
    this.connectionGeneration++;
    const socket = this.socket;
    this.socket = null;
    if (socket) {
      socket.onopen = null;
      socket.onmessage = null;
      socket.onerror = null;
      socket.onclose = null;
      try { socket.close(); } catch {}
    }
    this.isConnected = false;
    if (clearTimers) {
      if (this.reconnectTimer) {
        clearTimeout(this.reconnectTimer);
        this.reconnectTimer = null;
      }
      this.stopPollingFallback();
    }
  }
}

export const realtime = new RealtimeClient();
