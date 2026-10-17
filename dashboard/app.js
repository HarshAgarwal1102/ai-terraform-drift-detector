/*
 * Dashboard controller (Task 13.2): sign-in, data loading from the dashboard API and
 * event handling. All data comes from the same-origin `/api/*` endpoints.
 *
 * The bearer token is held in memory only (a reload signs out). Nothing is written to
 * browser storage or cookies, the browser holds no Azure credential and never calls
 * Azure: the `Caller recorded by Azure` value arrives only from the backend.
 */
(function () {
  "use strict";

  const R = window.DashboardRender;
  const REFRESH_MS = 60000;
  const state = { token: null, summary: null, drifts: [], remediations: [], unmanaged: null, callerAccess: true, run: "",
    historyQuery: "",
    filters: { severity: "", type: "", environment: "" }, timer: null, loads: 0, signingIn: false };
  const $ = (id) => document.getElementById(id);

  class ApiError extends Error {
    constructor(status, code) { super(code); this.status = status; this.code = code; }
  }

  async function api(path) {
    const headers = { Accept: "application/json" };
    if (state.token) headers.Authorization = "Bearer " + state.token;
    let response;
    try {
      response = await fetch(path, { headers, cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer" });
    } catch (e) {
      throw new ApiError(0, "network_error");
    }
    let body = null;
    try { body = await response.json(); } catch (e) { body = null; }
    if (!response.ok) throw new ApiError(response.status, R.apiErrorCode(response.status, body));
    return body;
  }

  /* Before sign-in: the API must answer an unauthenticated request with 401 unauthenticated.
     Anything else (for example a 404 from a static server) is shown on the sign-in screen. */
  async function checkApi() {
    try {
      await api("/api/summary");
    } catch (err) {
      if (err.status === 401 && err.code === "unauthenticated") return;
      $("signin-error").textContent = R.errorMessage(err.code, window.location.origin);
    }
  }

  function runQuery(prefix) {
    return state.run ? prefix + "report_id=" + encodeURIComponent(state.run) : "";
  }

  async function loadDrifts() {
    if (!state.callerAccess) return api("/api/drifts" + runQuery("?"));  // refused once this session: ask no more
    try {
      const doc = await api("/api/drifts?include_caller=true" + runQuery("&"));
      state.callerAccess = true;
      return doc;
    } catch (err) {
      if (err.status === 403 && err.code === "caller_access_denied") {
        state.callerAccess = false;  // a viewer: the drift rows come without caller identity
        return api("/api/drifts" + runQuery("?"));
      }
      throw err;
    }
  }

  // Resolves to "ok", "denied" (401: the token was rejected) or "error" (anything else, shown in the status line).
  async function load() {
    const loadId = ++state.loads;  // a retried load() owns the busy flag until it finishes
    setStatus("Loading…");
    $("refresh").setAttribute("aria-busy", "true");
    try {
      const [summary, drifts, remediations, unmanaged] = await Promise.all([api("/api/summary"), loadDrifts(),
        api("/api/remediations" + runQuery("?")), api("/api/unmanaged" + runQuery("?"))]);
      state.summary = summary;
      state.drifts = drifts.drifts;
      state.remediations = remediations.remediations;
      state.unmanaged = unmanaged;
      render();
      setStatus("Updated " + new Date().toLocaleTimeString() + " from " + summary.reports_total + " run(s)" +
        (state.callerAccess ? "" : " — caller identity hidden for this user"));
      return "ok";
    } catch (err) {
      if (err.status === 401) {  // while signing in the popup says "Access denied"; no second message
        signOut(state.signingIn ? "" : "Sign-in failed: the token was not accepted.");
        return "denied";
      }
      if (err.status === 404 && state.run) { state.run = ""; return load(); }  // the run is gone
      setStatus(R.errorMessage(err.code, window.location.origin), true);
      return "error";
    } finally {
      if (loadId === state.loads) $("refresh").removeAttribute("aria-busy");
    }
  }

  function render() {
    $("cards").innerHTML = R.overviewCards(state.summary);
    $("severity-bars").innerHTML = R.severityBreakdown(state.summary);
    renderHistory();
    $("issues").innerHTML = R.issuesPanel(state.summary);
    $("unmanaged").innerHTML = R.unmanagedPanel(state.unmanaged);
    $("filter-run").innerHTML = R.runOptions(state.summary, state.run);
    const options = R.filterOptions(state.drifts);
    ["severity", "type", "environment"].forEach((key) => {
      if (state.filters[key] && !options[key].includes(state.filters[key])) state.filters[key] = "";
      $("filter-" + key).innerHTML = R.optionTags(options[key], state.filters[key]);
    });
    const indices = [];
    const shown = state.drifts.filter((d, i) => {
      const keep = R.filterDrifts([d], state.filters).length === 1;
      if (keep) indices.push(i);
      return keep;
    });
    const context = R.driftContext(state.summary, state.run, state.drifts.length, shown.length);
    $("drift-rows").innerHTML = R.driftRows(shown, indices, context.empty);
    $("drift-context").textContent = context.showing;
    $("drift-count").textContent = shown.length + " of " + state.drifts.length + " drifted resource(s)";
  }

  function renderHistory() {
    const all = (state.summary && state.summary.history) || [];
    $("history").innerHTML = R.historyRows(state.summary, state.historyQuery, state.run);
    $("history-count").textContent = R.filterHistory(all, state.historyQuery).length + " of " + all.length + " run(s)";
  }

  /* Open one run from the history: the Run filter, drifts, remediations and unmanaged panel follow. */
  function openRun(runId) {
    if (!runId) return;
    state.run = runId;
    load().then(() => $("drifts-panel").scrollIntoView({ behavior: "smooth", block: "start" }));
  }

  function openDetails(index) {
    const drift = state.drifts[index];
    if (!drift) return;
    $("modal-body").innerHTML = R.detailModal(drift, state.remediations);
    $("modal").showModal();
  }

  function setStatus(text, isError) {
    $("status").textContent = text;
    $("status").classList.toggle("error", Boolean(isError));
  }

  function schedule() {
    clearInterval(state.timer);
    state.timer = $("auto-refresh").checked && state.token ? setInterval(load, REFRESH_MS) : null;
  }

  // Sign-in popup: verifying -> granted (then the dashboard) or denied (Try again).
  const AUTH_TEXT = {
    verifying: ["Verifying token…", "Checking access with the dashboard API"],
    granted: ["Access granted", "Loading your drift data…"],
    denied: ["Access denied", "That token wasn’t accepted. Check it and try again."],
  };
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  function setAuthState(name) {
    const dialog = $("auth-dialog");
    dialog.dataset.state = name;
    dialog.setAttribute("role", name === "denied" ? "alertdialog" : "dialog");
    $("auth-title").textContent = AUTH_TEXT[name][0];
    $("auth-message").textContent = AUTH_TEXT[name][1];
    $("auth-retry").hidden = name !== "denied";
  }

  async function signIn(token) {
    state.token = token;
    setAuthState("verifying");
    $("auth-dialog").showModal();
    state.signingIn = true;
    const [result] = await Promise.all([load(), wait(900)]);  // the verify step stays readable on a fast API
    state.signingIn = false;
    if (result === "denied") {
      setAuthState("denied");
      $("auth-retry").focus();
      return;
    }
    if (result === "ok") {
      setAuthState("granted");
      await wait(1000);
    }
    $("auth-dialog").close();  // "error" too: the dashboard's status line explains it, as before
    $("signin").hidden = true;
    $("app").hidden = false;
    $("signout").hidden = false;
    schedule();
  }

  // Eye toggle on the token field: show or mask what was typed (never stored either way).
  function setTokenVisible(show) {
    $("token").type = show ? "text" : "password";
    $("token-toggle").setAttribute("aria-pressed", String(show));
    $("token-toggle").setAttribute("aria-label", show ? "Hide token" : "Show token");
  }

  // Phone-only account menu (on wide screens it is always shown inline and this is a no-op visually).
  function setMenu(open) {
    document.querySelector(".topbar").dataset.menu = open ? "open" : "";
    $("account-toggle").setAttribute("aria-expanded", String(open));
  }

  function signOut(message) {
    state.token = null;
    state.summary = null;
    state.drifts = [];
    state.remediations = [];
    state.unmanaged = null;
    state.run = "";
    state.callerAccess = true;  // the next user may hold caller_reader
    state.historyQuery = "";
    $("history-search").value = "";
    clearInterval(state.timer);
    $("signout").hidden = true;
    $("app").hidden = true;
    $("signin").hidden = false;
    $("signin-error").textContent = message || "";
  }

  document.addEventListener("DOMContentLoaded", () => {
    checkApi();
    $("signin-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const token = $("token").value.trim();
      $("token").value = "";
      setTokenVisible(false);
      if (token) signIn(token);
    });
    $("auth-dialog").addEventListener("cancel", (event) => {
      if ($("auth-dialog").dataset.state !== "denied") event.preventDefault();  // no Escape mid-verification
    });
    $("auth-dialog").addEventListener("close", () => {
      if ($("auth-dialog").dataset.state === "denied") $("token").focus();
    });
    $("auth-retry").addEventListener("click", () => $("auth-dialog").close());
    $("token-toggle").addEventListener("click", () => setTokenVisible($("token").type === "password"));
    $("refresh").addEventListener("click", load);
    $("auto-refresh").addEventListener("change", schedule);
    $("signout").addEventListener("click", () => { setMenu(false); $("signout-dialog").showModal(); });
    $("signout-cancel").addEventListener("click", () => $("signout-dialog").close());
    $("signout-confirm").addEventListener("click", () => {
      $("signout-dialog").close();
      signOut("");
      $("token").focus();
    });
    $("account-toggle").addEventListener("click", () => {
      const open = $("account-toggle").getAttribute("aria-expanded") !== "true";
      setMenu(open);
      if (open) $("theme").focus();
    });
    document.addEventListener("click", (event) => {
      if (!event.target.closest(".topbar-actions")) setMenu(false);
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && $("account-toggle").getAttribute("aria-expanded") === "true") {
        setMenu(false);
        $("account-toggle").focus();
      }
    });
    ["severity", "type", "environment"].forEach((key) => {
      $("filter-" + key).addEventListener("change", (event) => { state.filters[key] = event.target.value; render(); });
    });
    $("history-search").addEventListener("input", (event) => {
      state.historyQuery = event.target.value;
      renderHistory();
    });
    $("history").addEventListener("click", (event) => {
      const row = event.target.closest("tr.run-row");
      if (row) openRun(row.dataset.run);
    });
    $("history").addEventListener("keydown", (event) => {
      const row = event.target.closest("tr.run-row");
      if (row && (event.key === "Enter" || event.key === " ")) {
        event.preventDefault();
        openRun(row.dataset.run);
      }
    });
    $("filter-run").addEventListener("change", (event) => { state.run = event.target.value; load(); });
    $("drift-rows").addEventListener("click", (event) => {
      const button = event.target.closest("button.details");
      if (button) openDetails(Number(button.dataset.index));
    });
    $("modal-close").addEventListener("click", () => $("modal").close());
    $("modal").addEventListener("click", (event) => { if (event.target === $("modal")) $("modal").close(); });
    const systemDark = window.matchMedia("(prefers-color-scheme: dark)");
    const isDark = () => {
      const chosen = document.documentElement.dataset.theme;
      return chosen ? chosen === "dark" : systemDark.matches;
    };
    const syncThemeSwitch = () => {
      const dark = isDark();
      $("theme").setAttribute("aria-checked", String(dark));
      $("theme-state").textContent = dark ? "ON" : "OFF";
    };
    $("theme").addEventListener("click", () => {
      document.documentElement.dataset.theme = isDark() ? "light" : "dark";
      syncThemeSwitch();
    });
    systemDark.addEventListener("change", syncThemeSwitch);
    syncThemeSwitch();
  });
})();
