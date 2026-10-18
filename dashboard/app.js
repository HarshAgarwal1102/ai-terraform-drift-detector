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
  const FETCH_POLL_MS = 2000;  // first status poll delay; doubled after each failed poll ...
  const FETCH_POLL_MAX_MS = 30000;  // ... up to this
  const FETCH_POLL_FAILURES = 5;  // consecutive failed polls before giving up (terminal "lost contact" state)
  const FETCH_WATCH_LIMIT_MS = 11 * 60 * 1000;  // the server's 10-minute timeout plus a margin
  function newFetchState() {
    return { status: null, refusal: null, notice: null, polling: false, windowOpen: false, refreshing: false,
      flash: null, ticker: null, connecting: false };
  }
  const state = { token: null, summary: null, drifts: [], remediations: [], unmanaged: null, callerAccess: true, run: "",
    historyQuery: "",
    filters: { severity: "", type: "", environment: "" }, timer: null, loads: 0, signingIn: false, loadingRun: null,
    fetch: newFetchState(), session: 0 };
  const $ = (id) => document.getElementById(id);

  class ApiError extends Error {
    constructor(status, code, retryAfter) { super(code); this.status = status; this.code = code; this.retryAfter = retryAfter; }
  }

  // `method` is GET except for the write requests: POST /api/fetch ("Check GitHub for new runs") and the
  // GitHub connection (POST /api/github/connect with the GitHub token as a JSON body, /disconnect).
  async function request(path, method, body) {
    const headers = { Accept: "application/json" };
    if (state.token) headers.Authorization = "Bearer " + state.token;
    const options = { method: method || "GET", headers, cache: "no-store", credentials: "omit",
      referrerPolicy: "no-referrer" };
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
      options.body = JSON.stringify(body);
    }
    let response;
    try {
      response = await fetch(path, options);
    } catch (e) {
      throw new ApiError(0, "network_error");
    }
    let doc = null;
    try { doc = await response.json(); } catch (e) { doc = null; }
    if (!response.ok) {
      const retry = response.headers && response.headers.get ? Number(response.headers.get("Retry-After")) : NaN;
      throw new ApiError(response.status, R.apiErrorCode(response.status, doc), Number.isFinite(retry) ? retry : null);
    }
    return doc;
  }

  /* Every data request goes through the loader: a response younger than REFRESH_MS is reused,
     an identical request in flight is shared, failures are not kept (loader.js). Refresh,
     auto-refresh and sign-out invalidate it. */
  const loader = window.DashboardLoader.createLoader(request, { ttlMs: REFRESH_MS });
  const api = (path) => loader.get(path);

  /* Before sign-in: the API must answer an unauthenticated request with 401 unauthenticated.
     Anything else (for example a 404 from a static server) is shown on the sign-in screen. */
  async function checkApi() {
    try {
      await request("/api/summary");  // not cached: before sign-in
    } catch (err) {
      if (err.status === 401 && err.code === "unauthenticated") return;
      $("signin-error").textContent = R.errorMessage(err.code, window.location.origin);
    }
  }

  function runQuery(prefix) {
    return state.run ? prefix + "report_id=" + encodeURIComponent(state.run) : "";
  }

  /* The drift rows without caller identity come first (a fast read of the artifacts); the
     `Caller recorded by Azure` values need a live Activity Log query per operation (about a
     second each on real Azure), so they are fetched alongside and merged in when they arrive.
     Until then a caller_reader sees "Looking up…" in the caller field, never a wrong value. */
  function pendingCallers(rows) {
    return state.callerAccess ? rows.map((d) => Object.assign({}, d, { caller_recorded_by_azure: { status: "loading" } }))
      : rows;
  }

  function loadCallers(view, current) {
    if (!state.callerAccess) return Promise.resolve("skipped");
    return api("/api/drifts?include_caller=true" + runQuery("&")).then((doc) => {
      view.callerState = "done";
      if (current()) { view.callers = doc.drifts; state.drifts = doc.drifts; state.driftsRun = view.run; renderDrifts(); }
      return "ok";
    }, (err) => {
      if (err.status === 403 && err.code === "caller_access_denied") {
        state.callerAccess = false;  // a viewer: the drift rows come without caller identity
        view.callerState = "done";
        if (current() && view.plain) { state.drifts = view.plain; state.driftsRun = view.run; renderDrifts(); }
        return "skipped";
      }
      view.callerState = "failed";
      if (current() && !view.callers && view.plain) {  // keep the rows; say why no caller is shown
        state.drifts = view.plain.map((d) => Object.assign({}, d,
          { caller_recorded_by_azure: { status: "lookup_failed", value: "Unknown", caller_type: "unknown" } }));
        state.driftsRun = view.run;
        renderDrifts();
      }
      throw err;
    });
  }

  function statusLine() {
    return "Updated " + new Date().toLocaleTimeString() + " from " + state.summary.reports_total + " run(s)" +
      (state.callerAccess ? "" : " — caller identity hidden for this user");
  }

  /* Loads the selected run. Each panel renders as soon as its own response arrives; a response
     for an earlier selection (the user clicked another run meanwhile) is ignored. `force`
     (Refresh, auto-refresh) asks the API again instead of reusing recent responses.
     Resolves to "ok", "denied" (401: the token was rejected) or "error" (shown in the status
     line) once summary, drifts, remediations and the unmanaged panel are in; the caller
     lookup may still be running then and updates its fields and the status line itself. */
  async function load(force) {
    if (force === true) loader.invalidate();
    const loadId = ++state.loads;
    const run = state.run;
    const current = () => loadId === state.loads && Boolean(state.token);
    const view = { run, plain: null, callers: null, callerState: "pending" };
    state.loadingRun = run;
    setStatus("Loading…");
    $("refresh").setAttribute("aria-busy", "true");
    const show = (promise, apply) => promise.then((doc) => { if (current()) apply(doc); return doc; });
    const callerPath = "/api/drifts?include_caller=true" + runQuery("&");
    const callersReady = state.callerAccess && loader.cached(callerPath) !== undefined;
    const callers = loadCallers(view, current);
    const core = [
      show(api("/api/summary"), (doc) => { state.summary = doc; renderSummary(); }),
      callersReady ? callers : show(api("/api/drifts" + runQuery("?")), (doc) => {
        view.plain = doc.drifts;
        if (!view.callers) { state.drifts = pendingCallers(doc.drifts); state.driftsRun = run; renderDrifts(); }
      }),
      show(api("/api/remediations" + runQuery("?")), (doc) => { state.remediations = doc.remediations; }),
      show(api("/api/unmanaged" + runQuery("?")), (doc) => { state.unmanaged = doc; renderUnmanaged(); }),
    ];
    const finish = () => { if (loadId === state.loads) { $("refresh").removeAttribute("aria-busy"); state.loadingRun = null; } };
    callers.then(() => {
      if (current() && state.summary) setStatus(statusLine());
    }, (err) => {
      if (!current()) return;
      if (err.status === 401) signOut(state.signingIn ? "" : "Sign-in failed: the token was not accepted.");
      else setStatus("Caller recorded by Azure: " + R.errorMessage(err.code, window.location.origin), true);
    }).finally(finish);
    try {
      await Promise.all(core);  // fails fast: a rejected token signs out without waiting for slower panels
    } catch (err) {
      if (!current()) return "error";
      if (err.status === 401) {  // while signing in the popup says "Access denied"; no second message
        signOut(state.signingIn ? "" : "Sign-in failed: the token was not accepted.");
        return "denied";
      }
      if (err.status === 404 && run) { state.run = ""; return load(); }  // the run is gone
      setStatus(R.errorMessage(err.code, window.location.origin), true);
      return "error";
    }
    if (!current()) return "ok";
    if (view.callerState === "pending" && state.callerAccess) {
      setStatus(statusLine() + " — looking up callers recorded by Azure…");
    } else if (view.callerState !== "failed") {
      setStatus(statusLine());  // a failed caller lookup keeps its message in the status line
    }
    return "ok";
  }

  function renderSummary() {
    $("cards").innerHTML = R.overviewCards(state.summary);
    $("severity-bars").innerHTML = R.severityBreakdown(state.summary);
    renderHistory();
    $("issues").innerHTML = R.issuesPanel(state.summary);
    $("filter-run").innerHTML = R.runOptions(state.summary, state.run);
    renderDriftContext();
  }

  function renderUnmanaged() {
    $("unmanaged").innerHTML = R.unmanagedPanel(state.unmanaged);
  }

  // Only the drift table and its filters: the other panels are left as they are.
  function renderDrifts() {
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
    state.shown = shown.length;
    const context = R.driftContext(state.summary, state.run, state.drifts.length, shown.length);
    $("drift-rows").innerHTML = R.driftRows(shown, indices, context.empty);
    $("drift-context").textContent = context.showing;
    $("drift-count").textContent = shown.length + " of " + state.drifts.length + " drifted resource(s)";
  }

  // The "Showing run …" line follows the rows on screen, never a run whose rows are still loading.
  function renderDriftContext() {
    if (state.summary === null || state.shown === undefined || state.driftsRun !== state.run) return;
    $("drift-context").textContent = R.driftContext(state.summary, state.run, state.drifts.length, state.shown).showing;
  }

  function renderHistory() {
    const all = (state.summary && state.summary.history) || [];
    $("history").innerHTML = R.historyRows(state.summary, state.historyQuery, state.run);
    $("history-count").textContent = R.filterHistory(all, state.historyQuery).length + " of " + all.length + " run(s)";
  }

  /* Open one run from the history: the Run filter, drifts, remediations and unmanaged panel follow. */
  function openRun(runId) {
    if (!runId) return;
    const scroll = () => $("drifts-panel").scrollIntoView({ behavior: "smooth", block: "start" });
    if (runId === state.run && state.loadingRun === runId) { scroll(); return; }  // already loading it
    state.run = runId;
    renderHistory();  // the clicked row is highlighted at once
    load().then(scroll);
  }

  function openDetails(index) {
    const drift = state.drifts[index];
    if (!drift) return;
    $("modal-body").innerHTML = R.detailModal(drift, state.remediations);
    $("modal").showModal();
  }

  /* "Check GitHub for new runs" (Task 13.4). The browser only asks the dashboard server: the server
     runs the GitHub fetch with a token this page never sees. Status requests bypass the cache.
     Refresh and auto-refresh never come here: they only re-read the local reports. */
  function renderFetch() {
    const status = state.fetch.status;
    const view = R.fetchView(status, state.fetch.refusal, state.fetch.notice);
    const running = Boolean(status && status.status === "running");
    const button = $("github-fetch");
    button.hidden = !view.visible;
    button.disabled = view.disabled;
    if (running) button.setAttribute("aria-busy", "true");
    else button.removeAttribute("aria-busy");
    // "Not connected" is explained in the Connect GitHub first popup, not on the page.
    const text = state.fetch.flash && !running && !state.fetch.refusal ? state.fetch.flash
      : (view.connect ? "" : view.text);
    $("github-fetch-status").hidden = !text;
    $("github-fetch-status").textContent = text;
    $("github-fetch-status").dataset.tone = state.fetch.flash && !running && !state.fetch.refusal ? "ok" : view.tone;
    // Connection chip: shown to users who may fetch, whenever GitHub access itself is possible.
    const conn = R.connectionView(status);
    const usable = Boolean(status && status.allowed && (status.available || status.unavailable_reason === "not_connected"));
    $("github-connect").hidden = !usable;
    $("github-connect-label").textContent = conn.connected ? "GitHub: connected" : "Connect GitHub";
    $("github-connect").dataset.tone = conn.tone;
    $("fetch-details").hidden = !(status && status.allowed && status.status !== "idle" && conn.connected);
    renderFetchWindow();
  }

  /* The status window is non-modal: the dashboard behind it stays usable. Hiding it only hides it. */
  function renderFetchWindow() {
    const status = state.fetch.status;
    clearInterval(state.fetch.ticker);
    state.fetch.ticker = null;
    if (!state.fetch.windowOpen || !status) return;
    $("fetch-body").innerHTML = R.fetchWindow(status, { now: Date.now(), refreshing: state.fetch.refreshing });
    const failed = status.status === "failed" || status.status === "partial";
    const problem = status.category || (status.connection && status.connection.last_error &&
      status.connection.last_error.category);
    $("fetch-retry").hidden = !(failed && status.available);
    $("fetch-replace").hidden = !["invalid_token", "insufficient_permissions", "repository_not_accessible",
      "sso_required"].includes(problem);  // the backend's AUTH_CATEGORIES
    const refusal = state.fetch.refusal ? R.fetchView(status, state.fetch.refusal, null).text : "";
    $("fetch-refusal").textContent = refusal;
    $("fetch-refusal").hidden = !refusal;
    if (status.status === "running") state.fetch.ticker = setInterval(renderFetchWindow, 1000);
  }

  function openFetchWindow() {
    if (!state.fetch.status) return;
    state.fetch.windowOpen = true;
    if (!$("fetch-dialog").open) $("fetch-dialog").show();
    renderFetchWindow();
  }

  function hideFetchWindow() {
    state.fetch.windowOpen = false;
    clearInterval(state.fetch.ticker);
    state.fetch.ticker = null;
    if ($("fetch-dialog").open) $("fetch-dialog").close();
  }

  /* GitHub connection dialog (Task 13.5). The GitHub token goes to the dashboard server once, in a
     POST body; it is never kept by this page and the field is emptied the moment it is submitted. */
  function openConnect() {
    const conn = R.connectionView(state.fetch.status);
    $("github-token").value = "";
    $("github-error").textContent = "";
    $("github-disconnect").hidden = !conn.connected;
    $("github-submit-label").textContent = conn.connected ? "Verify and replace" : "Verify and connect";
    $("github-title").textContent = conn.connected ? "Replace GitHub token" : "Connect GitHub";
    $("github-dialog").dataset.state = "idle";
    $("github-dialog").showModal();
    $("github-token").focus();
  }

  // While verifying the field is locked and shows one mask dot per character as its placeholder; its value
  // is already empty, so the real token is not on the page. Afterwards it is unlocked (and still empty).
  function setConnecting(busy, maskLength) {
    state.fetch.connecting = busy;
    $("github-dialog").dataset.state = busy ? "verifying" : "idle";
    $("github-token").disabled = busy;
    $("github-token").placeholder = busy ? "•".repeat(Math.min(Math.max(maskLength || 0, 8), 40)) : "github_pat_…";
    $("github-help").hidden = busy;
    $("github-checking").hidden = !busy;
    $("github-submit").disabled = busy;
    $("github-cancel").disabled = busy;
    $("github-disconnect").disabled = busy;
    $("github-submit-label").textContent = busy ? "Verifying…" : $("github-disconnect").hidden
      ? "Verify and connect" : "Verify and replace";
  }

  async function connectGitHub() {
    const token = $("github-token").value.trim();
    $("github-token").value = "";  // gone from the page before the request leaves
    if (!token) { $("github-error").textContent = "Paste a GitHub token first."; return; }
    const session = state.session;
    $("github-error").textContent = "";
    setConnecting(true, token.length);
    try {
      const doc = await request("/api/github/connect", "POST", { token });
      if (session !== state.session) return;
      state.fetch.status = doc;
      const v = doc.verification || {};
      if (v.ok) {
        state.fetch.flash = v.warning
          ? "GitHub connected: the token can read reports, but lacks Issues: Read, so drift issue states won't update."
          : "GitHub connected: token verified. You can now check for new runs.";
        state.fetch.refusal = null;
        setConnecting(false);
        $("github-dialog").close();
      } else {
        setConnecting(false);
        $("github-error").textContent = R.githubProblem(v.category, v.http_status, v.need) ||
          "The token could not be verified.";
        $("github-token").focus();
      }
      renderFetch();
    } catch (err) {
      if (session !== state.session) return;
      setConnecting(false);
      if (err.status === 401) { signOut("Sign-in failed: the token was not accepted."); return; }
      $("github-error").textContent = {
        network_error: "The dashboard server could not be reached. Try again.",
        fetch_in_progress: "A GitHub check is running. Try again when it finishes.",
        verification_in_progress: "A verification is already running. Wait for it to finish.",
        verify_too_soon: "Please wait a moment before trying again.",
        invalid_token_format: R.githubProblem("invalid_token_format"),
        fetch_access_denied: "Your sign-in may not connect GitHub (needs the data_refresher role).",
        local_only: "Connecting GitHub is local-only and refused here.",
        disabled: "GitHub access is turned off for this dashboard (started with --no-github).",
      }[err.code] || "The token could not be verified (" + err.code + ").";
      $("github-token").focus();
    }
  }

  async function disconnectGitHub() {
    const session = state.session;
    setConnecting(true);
    try {
      const doc = await request("/api/github/disconnect", "POST", {});
      if (session !== state.session) return;
      state.fetch.status = doc;
      state.fetch.flash = "GitHub disconnected: the token was forgotten.";
      setConnecting(false);
      $("github-dialog").close();
      hideFetchWindow();  // and renderFetch() hides the Fetch status button until GitHub is connected again
      renderFetch();
    } catch (err) {
      if (session !== state.session) return;
      setConnecting(false);
      if (err.status === 401) { signOut("Sign-in failed: the token was not accepted."); return; }
      $("github-error").textContent = err.code === "fetch_in_progress"
        ? "A GitHub check is running. Try again when it finishes." : "Could not disconnect (" + err.code + ").";
    }
  }

  async function checkFetchStatus() {
    const session = state.session;
    try {
      const doc = await request("/api/fetch/status");
      if (session !== state.session) return;
      state.fetch.status = doc;
      state.fetch.refusal = null;
      state.fetch.notice = null;
      renderFetch();
      if (doc.status === "running") pollFetch();
    } catch (err) {
      if (session === state.session && err.status === 401) signOut("Sign-in failed: the token was not accepted.");
      // otherwise: the button stays hidden; the rest of the dashboard is unaffected
    }
  }

  /* While a fetch runs: ask for its state, every FETCH_POLL_MS while the answers come, backing off
     (doubling, up to FETCH_POLL_MAX_MS) after failed polls. It always ends: when the job ends (the
     local reports are reloaded), after FETCH_POLL_FAILURES failed polls in a row ("lost contact"),
     after FETCH_WATCH_LIMIT_MS ("stopped watching"), or at sign-out. */
  async function pollFetch() {
    if (state.fetch.polling) return;
    state.fetch.polling = true;
    state.fetch.notice = null;
    const session = state.session;
    const started = Date.now();
    let delay = FETCH_POLL_MS;
    let failures = 0;
    try {
      for (;;) {
        await wait(delay);
        if (session !== state.session || !state.token) return;
        let doc;
        try {
          doc = await request("/api/fetch/status");
        } catch (err) {
          if (session !== state.session) return;
          if (err.status === 401) { signOut("Sign-in failed: the token was not accepted."); return; }
          failures += 1;
          if (failures >= FETCH_POLL_FAILURES) { state.fetch.notice = "poll_failed"; renderFetch(); return; }
          delay = Math.min(delay * 2, FETCH_POLL_MAX_MS);
          continue;
        }
        if (session !== state.session) return;
        failures = 0;
        delay = FETCH_POLL_MS;
        state.fetch.status = doc;
        renderFetch();
        if (doc.status !== "running") {
          state.fetch.refreshing = true;  // the last stage: the local reports are read again
          renderFetch();
          try {
            await load(true);  // invalidates the request cache, then reloads every panel from the local reports
          } finally {
            if (session === state.session) { state.fetch.refreshing = false; renderFetch(); }
          }
          return;
        }
        if (Date.now() - started >= FETCH_WATCH_LIMIT_MS) {
          state.fetch.notice = "watch_limit";
          renderFetch();
          return;
        }
      }
    } finally {
      if (session === state.session) state.fetch.polling = false;
    }
  }

  async function startFetch() {
    const status = state.fetch.status;
    if (status && !status.available && status.unavailable_reason === "not_connected") {
      $("github-first-dialog").showModal();  // explain first; its Connect GitHub button opens the token dialog
      return;
    }
    const session = state.session;
    state.fetch.refusal = null;
    state.fetch.notice = null;
    state.fetch.flash = null;
    $("github-fetch").disabled = true;
    try {
      const doc = await request("/api/fetch", "POST");
      if (session !== state.session) return;
      state.fetch.status = doc;
      state.fetch.windowOpen = true;
      if (!$("fetch-dialog").open) $("fetch-dialog").show();
      renderFetch();
      pollFetch();
    } catch (err) {
      if (session !== state.session) return;
      if (err.status === 401) { signOut("Sign-in failed: the token was not accepted."); return; }
      const refusal = { code: err.code, retryAfter: err.retryAfter };
      state.fetch.refusal = refusal;
      renderFetch();
      if (err.code === "fetch_in_progress") pollFetch();
      if (err.code === "fetch_unavailable" || err.code === "local_only" || err.code === "disabled") checkFetchStatus();  // shows why
      if (err.code === "fetch_cooldown" && err.retryAfter) {
        // The cooldown message clears itself when the cooldown is over.
        setTimeout(() => {
          if (session === state.session && state.fetch.refusal === refusal) { state.fetch.refusal = null; renderFetch(); }
        }, err.retryAfter * 1000);
      }
    }
  }

  function setStatus(text, isError) {
    $("status").textContent = text;
    $("status").classList.toggle("error", Boolean(isError));
  }

  function schedule() {
    clearInterval(state.timer);
    state.timer = $("auto-refresh").checked && state.token ? setInterval(() => load(true), REFRESH_MS) : null;
  }

  // Sign-in popup: verifying -> granted (then the dashboard) or denied (Try again).
  const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const AUTH_TEXT = {
    verifying: ["Verifying token…", "Checking access with the dashboard API"],
    granted: ["Access granted", "Loading your drift data…"],
    denied: ["Access denied", "That token wasn’t accepted. Check it and try again."],
  };

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
    checkFetchStatus();  // shows "Check GitHub for new runs" to data_refresher users
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
    loader.invalidate();  // nothing of this user's responses outlives the session
    state.loads += 1;  // responses still in flight are ignored
    state.loadingRun = null;
    state.shown = undefined;
    state.driftsRun = undefined;
    state.token = null;
    state.summary = null;
    state.drifts = [];
    state.remediations = [];
    state.unmanaged = null;
    state.run = "";
    state.callerAccess = true;  // the next user may hold caller_reader
    state.session += 1;  // ends any fetch polling of this session
    clearInterval(state.fetch.ticker);
    state.fetch = newFetchState();
    $("github-token").value = "";  // a half-typed GitHub token does not outlive the session
    ["github-dialog", "github-first-dialog", "fetch-dialog"].forEach((id) => { if ($(id).open) $(id).close(); });
    renderFetch();
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
    $("refresh").addEventListener("click", () => load(true));
    $("github-fetch").addEventListener("click", startFetch);
    $("github-connect").addEventListener("click", openConnect);
    // The GitHub token field is a masked text field outside any <form> (no password-manager save prompt);
    // where CSS masking is unsupported it falls back to a password field. Enter and the button submit it.
    if (!(window.CSS && CSS.supports && CSS.supports("-webkit-text-security", "disc"))) $("github-token").type = "password";
    $("github-submit").addEventListener("click", () => { if (!state.fetch.connecting) connectGitHub(); });
    $("github-token").addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.isComposing) {
        event.preventDefault();
        if (!state.fetch.connecting) connectGitHub();
      }
    });
    $("github-cancel").addEventListener("click", () => $("github-dialog").close());
    $("github-disconnect").addEventListener("click", disconnectGitHub);
    $("github-dialog").addEventListener("cancel", (event) => { if (state.fetch.connecting) event.preventDefault(); });
    $("github-dialog").addEventListener("close", () => { $("github-token").value = ""; });
    $("fetch-details").addEventListener("click", openFetchWindow);
    $("fetch-hide").addEventListener("click", hideFetchWindow);
    $("github-first-later").addEventListener("click", () => $("github-first-dialog").close());
    $("github-first-connect").addEventListener("click", () => { $("github-first-dialog").close(); openConnect(); });
    $("fetch-dialog").addEventListener("close", () => { state.fetch.windowOpen = false; });
    // A non-modal <dialog> does not close on Escape by itself: hide it (the check keeps running).
    $("fetch-dialog").addEventListener("keydown", (event) => {
      if (event.key === "Escape") { event.preventDefault(); hideFetchWindow(); $("fetch-details").focus(); }
    });
    $("fetch-retry").addEventListener("click", startFetch);
    $("fetch-replace").addEventListener("click", openConnect);
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
      $("filter-" + key).addEventListener("change", (event) => { state.filters[key] = event.target.value; renderDrifts(); });
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
