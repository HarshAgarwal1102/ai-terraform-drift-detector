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
  const state = { token: null, summary: null, drifts: [], remediations: [], callerAccess: true, run: "",
    filters: { severity: "", type: "", environment: "" }, timer: null };
  const $ = (id) => document.getElementById(id);

  class ApiError extends Error {
    constructor(status, code) { super(code); this.status = status; this.code = code; }
  }

  async function api(path) {
    const response = await fetch(path, {
      headers: { Authorization: "Bearer " + state.token, Accept: "application/json" },
      cache: "no-store", credentials: "omit", referrerPolicy: "no-referrer",
    });
    let body = null;
    try { body = await response.json(); } catch (e) { body = null; }
    if (!response.ok) throw new ApiError(response.status, (body && body.error) || "http_" + response.status);
    return body;
  }

  function runQuery(prefix) {
    return state.run ? prefix + "report_id=" + encodeURIComponent(state.run) : "";
  }

  async function loadDrifts() {
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

  async function load() {
    setStatus("Loading…");
    try {
      const [summary, drifts, remediations] = await Promise.all([api("/api/summary"), loadDrifts(),
        api("/api/remediations" + runQuery("?"))]);
      state.summary = summary;
      state.drifts = drifts.drifts;
      state.remediations = remediations.remediations;
      render();
      setStatus("Updated " + new Date().toLocaleTimeString() + " from " + summary.reports_total + " run(s)" +
        (state.callerAccess ? "" : " — caller identity hidden for this user"));
    } catch (err) {
      if (err.status === 401) { signOut("Sign-in failed: the token was not accepted."); return; }
      if (err.status === 404 && state.run) { state.run = ""; return load(); }  // the run is gone
      setStatus("Could not load data (" + err.code + ").", true);
    }
  }

  function render() {
    $("cards").innerHTML = R.overviewCards(state.summary);
    $("severity-bars").innerHTML = R.severityBreakdown(state.summary);
    $("history").innerHTML = R.historyRows(state.summary);
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
    $("drift-rows").innerHTML = R.driftRows(shown, indices);
    $("drift-count").textContent = shown.length + " of " + state.drifts.length + " drifted resource(s)";
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

  function signOut(message) {
    state.token = null;
    state.summary = null;
    state.drifts = [];
    state.remediations = [];
    state.run = "";
    clearInterval(state.timer);
    $("app").hidden = true;
    $("signin").hidden = false;
    $("signin-error").textContent = message || "";
  }

  document.addEventListener("DOMContentLoaded", () => {
    $("signin-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const token = $("token").value.trim();
      $("token").value = "";
      if (!token) return;
      state.token = token;
      $("signin").hidden = true;
      $("app").hidden = false;
      load().then(schedule);
    });
    $("refresh").addEventListener("click", load);
    $("auto-refresh").addEventListener("change", schedule);
    $("signout").addEventListener("click", () => signOut(""));
    ["severity", "type", "environment"].forEach((key) => {
      $("filter-" + key).addEventListener("change", (event) => { state.filters[key] = event.target.value; render(); });
    });
    $("filter-run").addEventListener("change", (event) => { state.run = event.target.value; load(); });
    $("drift-rows").addEventListener("click", (event) => {
      const button = event.target.closest("button.details");
      if (button) openDetails(Number(button.dataset.index));
    });
    $("modal-close").addEventListener("click", () => $("modal").close());
    $("modal").addEventListener("click", (event) => { if (event.target === $("modal")) $("modal").close(); });
    $("theme").addEventListener("click", () => {
      const root = document.documentElement;
      const dark = root.dataset.theme ? root.dataset.theme === "dark"
        : window.matchMedia("(prefers-color-scheme: dark)").matches;
      root.dataset.theme = dark ? "light" : "dark";
    });
  });
})();
