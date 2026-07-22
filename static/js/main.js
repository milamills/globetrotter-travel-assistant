// ---------------------------------------------------------------------
// GlobeTrotter — shared front-end logic
// Talks to the same-origin Flask API (no CORS needed: pages are served
// by the same monolith that serves /register, /login, /destinations...).
// ---------------------------------------------------------------------

const GT = {
  TOKEN_KEY: "gt_token",
  USER_KEY: "gt_username",

  getToken() { return localStorage.getItem(this.TOKEN_KEY); },
  getUsername() { return localStorage.getItem(this.USER_KEY); },
  isAuthed() { return !!this.getToken(); },

  setSession(token, username) {
    localStorage.setItem(this.TOKEN_KEY, token);
    localStorage.setItem(this.USER_KEY, username);
  },
  clearSession() {
    localStorage.removeItem(this.TOKEN_KEY);
    localStorage.removeItem(this.USER_KEY);
  },

  async api(path, { method = "GET", body = null, auth = false } = {}) {
    const headers = { "Content-Type": "application/json" };
    if (auth) {
      const token = this.getToken();
      if (!token) throw { status: 401, error: "not_logged_in" };
      headers["Authorization"] = "Bearer " + token;
    }
    const resp = await fetch(path, {
      method,
      headers,
      body: body ? JSON.stringify(body) : undefined,
    });
    let data = {};
    try { data = await resp.json(); } catch (e) { /* no body */ }
    if (!resp.ok) {
      throw { status: resp.status, error: data.error || "request_failed" };
    }
    return data;
  },

  requireAuth() {
    if (!this.isAuthed()) {
      window.location.href = "/login?next=" + encodeURIComponent(window.location.pathname);
    }
  },

  // Region -> accent color, used for the destination card left-stripe.
  regionColor(region) {
    const map = {
      "Centre": "#0F6B4C",
      "Littoral": "#2472A6",
      "Southwest": "#3E8E7E",
      "South": "#57A639",
      "West": "#D9A441",
      "Northwest": "#8C6BAF",
      "North": "#C2703D",
      "Far North": "#B3432D",
      "Adamawa": "#B98A2E",
      "East": "#4E7C59",
    };
    return map[region] || "#9AA79D";
  },

  showBanner(el, message, type = "error") {
    el.textContent = message;
    el.className = "banner show " + type;
  },
  hideBanner(el) {
    el.className = "banner";
  },
};

function renderNavUser() {
  const slot = document.getElementById("navUserSlot");
  if (!slot) return;
  if (GT.isAuthed()) {
    slot.innerHTML = `
      <span class="pill">👋 ${GT.getUsername()}</span>
      <button class="btn-ghost" id="logoutBtn">Log out</button>
    `;
    document.getElementById("logoutBtn").addEventListener("click", () => {
      GT.clearSession();
      window.location.href = "/";
    });
  } else {
    slot.innerHTML = `
      <a href="/login" class="btn-ghost"><span class="linktext">Log in</span></a>
      <a href="/register" class="navlinks cta" style="padding:8px 16px;border-radius:8px;">Sign up</a>
    `;
  }
}
document.addEventListener("DOMContentLoaded", renderNavUser);
