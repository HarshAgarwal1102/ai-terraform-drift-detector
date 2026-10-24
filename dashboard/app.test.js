/*
 * Controller tests for dashboard/app.js (Run History performance). Run: node --test dashboard/
 * (tests/test_dashboard_ui.py runs them under pytest). No dependencies, no network.
 *
 * render.js, loader.js and app.js run unchanged in a vm context with a minimal fake DOM and
 * a fake fetch whose responses the test releases one by one, so the order in which panels
 * render, which requests are sent and which responses are ignored is checked exactly.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

class El {
  constructor(id) {
    Object.assign(this, { id, innerHTML: "", textContent: "", value: "", hidden: false,
      type: id === "token" ? "password" : "text",  // as in index.html (the GitHub token field is type="text")
      checked: false, open: false, dataset: {}, attrs: {}, listeners: {} });
    this.classes = new Set();
    this.classList = { toggle: (name, on) => (on ? this.classes.add(name) : this.classes.delete(name)) };
  }
  setAttribute(k, v) { this.attrs[k] = String(v); }
  getAttribute(k) { return k in this.attrs ? this.attrs[k] : null; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(type, fn) { (this.listeners[type] = this.listeners[type] || []).push(fn); }
  fire(type, event) { (this.listeners[type] || []).forEach((fn) => fn(event || {})); }
  showModal() { this.open = true; }
  show() { this.open = true; }
  close() { this.open = false; this.fire("close"); }
  focus() {}
  scrollIntoView() {}
}

const flush = async () => { for (let i = 0; i < 30; i += 1) await new Promise((r) => setImmediate(r)); };
const RUNS = ["github-3-1", "github-2-1", "github-1-1"];
const summary = () => ({ reports_total: RUNS.length, environments: [], issues: { snapshot: false },
  overview: { total_resources: 5, active_drifts: 1, security_exposure: 0,
    monthly_cost_impact: { status: "no_drift_cost", monthly_cost_delta: null } },
  history: RUNS.map((id, i) => ({ report_id: id, finished_at: `2026-10-11T0${4 - i}:00:00Z`, environment: "dev",
    drifted_resources: 1, resources_total: 5, highest_severity: "LOW",
    unmanaged: { available: false, unmanaged: null, display: null } })) });
const row = (run, caller) => Object.assign({ report_id: run, environment: "dev", address: `res_${run}`,
  type: "azurerm_resource_group", classification: "external_drift", severity: "LOW", changes: [], operation: null,
  ai_analysis: { available: false, narrative: [] }, remediation: null, issue: null }, caller === undefined ? {}
  : { caller_recorded_by_azure: { label: "Caller recorded by Azure", value: caller, caller_type: "user", status: "matched" } });
const paths = (run) => {
  const q = run ? "report_id=" + run : "";
  return { plain: "/api/drifts" + (q ? "?" + q : ""), callers: "/api/drifts?include_caller=true" + (q ? "&" + q : ""),
    remediations: "/api/remediations" + (q ? "?" + q : ""), unmanaged: "/api/unmanaged" + (q ? "?" + q : "") };
};
const unmanagedDoc = (run) => ({ runs: [{ report_id: run || "latest", environment: "dev", available: false }] });

function harness(options) {
  const els = new Map();
  const $ = (id) => { if (!els.has(id)) els.set(id, new El(id)); return els.get(id); };
  const docListeners = {};
  const delays = [];  // every setTimeout delay the controller asked for (timers still fire at once)
  const calls = [];
  const auto = new Map();
  const fetch = (url, options) => {
    // As a browser does: a header value it cannot send (a line break, a character above U+00FF) makes fetch()
    // fail with a TypeError before any request exists. Node's Headers applies the same rule.
    try { new Headers(options.headers); } catch (err) { return Promise.reject(err); }
    return sendRequest(url, options);
  };
  const sendRequest = (url, options) => new Promise((resolve, reject) => {
    const call = { path: url, method: options.method || "GET", auth: options.headers.Authorization || null,
      credentials: options.credentials, cache: options.cache, answered: false };
    call.respond = (status, body, hdrs) => {
      call.answered = true;
      resolve({ ok: status >= 200 && status < 300, status, json: async () => body,
        headers: { get: (k) => (hdrs && k in hdrs ? hdrs[k] : null) } });
    };
    call.fail = () => { call.answered = true; reject(new TypeError("Failed to fetch")); };  // as a browser does
    calls.push(call);
    if (!call.auth) call.respond(401, { error: "unauthenticated" });
    else if (auto.has(url)) call.respond(...auto.get(url));
  });
  const ctx = vm.createContext({ fetch, console, setImmediate, setTimeout: (fn, ms) => { delays.push(ms); setImmediate(fn); },
    setInterval: () => 0, clearInterval: () => {}, __clock: { t: 1000000 },
    CSS: options && options.css ? { supports: (prop, value) => prop === "-webkit-text-security" && value === "disc" }
      : undefined,
    document: { getElementById: $, querySelector: () => $("topbar"), documentElement: { dataset: {} },
      addEventListener: (type, fn) => { (docListeners[type] = docListeners[type] || []).push(fn); } } });
  vm.runInContext("window = globalThis; window.location = { origin: 'http://127.0.0.1:8000' };" +
    "window.matchMedia = () => ({ matches: false, addEventListener() {} }); Date.now = () => __clock.t;", ctx);
  for (const file of ["render.js", "loader.js", "app.js"]) {
    vm.runInContext(fs.readFileSync(path.join(__dirname, file), "utf8"), ctx, { filename: file });
  }
  docListeners.DOMContentLoaded.forEach((fn) => fn());
  const R = ctx.DashboardRender;
  const open = (p) => calls.filter((c) => c.path === p && !c.answered);
  const sent = (p) => calls.filter((c) => c.path === p).length;
  const answer = (p, status, body) => {
    const pending = open(p);
    assert.equal(pending.length, 1, `exactly one open request for ${p}`);
    pending[0].respond(status, body);
  };
  const click = (run) => $("history").fire("click", { target: { closest: (sel) => (sel === "tr.run-row"
    ? { dataset: { run } } : null) } });
  const autoAnswer = (run, callers) => {
    const p = paths(run);
    auto.set("/api/summary", [200, summary()]);
    auto.set(p.plain, [200, { drifts: [row(run || "latest")] }]);
    auto.set(p.callers, callers || [200, { drifts: [row(run || "latest", "caller-latest")] }]);
    auto.set(p.remediations, [200, { remediations: [] }]);
    auto.set(p.unmanaged, [200, unmanagedDoc(run)]);
  };
  async function signIn(token, callers) {
    autoAnswer("", callers);
    $("token").value = token || "t0k3n";
    $("signin-form").fire("submit", { preventDefault() {} });
    await flush();
    auto.clear();
  }
  return { $, R, calls, auto, ctx, open, sent, answer, click, flush, signIn, autoAnswer, delays };
}

test("every API request is same-origin, uncached, and sends cookies only to this origin", async () => {
  // A protected Vercel deployment answers a request without its sign-in cookie with its own 401 before the
  // dashboard API sees it, so `omit` broke the deployed dashboard; `include` would also send cookies to
  // other origins. The bearer header stays the API's only sign-in.
  const h = harness();
  await h.signIn();
  h.click("github-2-1");
  await h.flush();
  assert.ok(h.calls.length >= 6);
  for (const call of h.calls) {
    assert.match(call.path, /^\/api\//);
    assert.equal(call.credentials, "same-origin", call.path);
    assert.equal(call.cache, "no-store", call.path);
  }
});

test("run click: the four panels' requests start in parallel, unchanged summary is not refetched", async () => {
  const h = harness();
  await h.signIn();
  assert.equal(h.$("app").hidden, false);
  assert.match(h.$("drift-rows").innerHTML, /caller-latest/);
  const before = h.sent("/api/summary");
  h.click("github-2-1");
  await h.flush();
  const p = paths("github-2-1");
  for (const key of ["plain", "callers", "remediations", "unmanaged"]) assert.equal(h.open(p[key]).length, 1, key);
  assert.equal(h.sent("/api/summary"), before);  // fresh: reused, not asked again
  assert.match(h.$("history").innerHTML, /aria-current|selected|github-2-1/);
});

test("run click: each panel renders as soon as its own data arrives; callers fill in last", async () => {
  const h = harness();
  await h.signIn();
  h.click("github-2-1");
  await h.flush();
  const p = paths("github-2-1");
  h.answer(p.unmanaged, 200, unmanagedDoc("github-2-1"));
  await h.flush();
  assert.equal(h.$("unmanaged").innerHTML, h.R.unmanagedPanel(unmanagedDoc("github-2-1")));
  assert.doesNotMatch(h.$("drift-rows").innerHTML, /res_github-2-1/);  // drifts not in yet: not waited for
  assert.doesNotMatch(h.$("drift-context").textContent, /github-2-1/);  // never names a run whose rows are loading
  h.answer(p.plain, 200, { drifts: [row("github-2-1")] });
  await h.flush();
  const rows = h.$("drift-rows").innerHTML;
  assert.match(rows, /res_github-2-1/);
  assert.match(rows, /data-caller-status="loading"/);  // rows shown before the Activity Log lookup returns
  assert.doesNotMatch(rows, /caller_reader/);  // never shown as "not allowed" while it is loading
  h.answer(p.remediations, 200, { remediations: [] });
  await h.flush();
  assert.match(h.$("status").textContent, /looking up callers recorded by Azure/);
  h.answer(p.callers, 200, { drifts: [row("github-2-1", "caller-two")] });
  await h.flush();
  assert.match(h.$("drift-rows").innerHTML, /caller-two/);
  assert.doesNotMatch(h.$("drift-rows").innerHTML, /data-caller-status="loading"/);
  assert.match(h.$("status").textContent, /^Updated /);
  assert.equal(h.$("refresh").getAttribute("aria-busy"), null);
});

test("repeated clicks send no duplicate requests; a recent run opens from memory", async () => {
  const h = harness();
  await h.signIn();
  h.click("github-2-1");
  h.click("github-2-1");
  await h.flush();
  h.click("github-2-1");
  await h.flush();
  const p = paths("github-2-1");
  for (const key of Object.keys(p)) assert.equal(h.sent(p[key]), 1, key);
  h.answer(p.plain, 200, { drifts: [row("github-2-1")] });
  h.answer(p.callers, 200, { drifts: [row("github-2-1", "caller-two")] });
  h.answer(p.remediations, 200, { remediations: [] });
  h.answer(p.unmanaged, 200, unmanagedDoc("github-2-1"));
  await h.flush();
  h.autoAnswer("github-1-1");
  h.click("github-1-1");
  await h.flush();
  h.auto.clear();
  const total = h.calls.length;
  h.click("github-2-1");  // back to a run opened under a minute ago
  await h.flush();
  assert.equal(h.calls.length, total);  // nothing sent: summary, drifts, callers, remediations, unmanaged reused
  assert.match(h.$("drift-rows").innerHTML, /caller-two/);
  assert.doesNotMatch(h.$("drift-rows").innerHTML, /data-caller-status="loading"/);
});

test("rapid switching: a late response for an earlier run never overwrites the selected run", async () => {
  const h = harness();
  await h.signIn();
  h.click("github-2-1");
  await h.flush();
  h.click("github-1-1");
  await h.flush();
  const a = paths("github-2-1");
  const b = paths("github-1-1");
  h.answer(b.plain, 200, { drifts: [row("github-1-1")] });
  h.answer(b.callers, 200, { drifts: [row("github-1-1", "caller-one")] });
  h.answer(b.remediations, 200, { remediations: [] });
  h.answer(b.unmanaged, 200, unmanagedDoc("github-1-1"));
  await h.flush();
  h.answer(a.plain, 200, { drifts: [row("github-2-1")] });  // the slow, obsolete responses arrive last
  h.answer(a.callers, 200, { drifts: [row("github-2-1", "caller-two")] });
  h.answer(a.remediations, 200, { remediations: [] });
  h.answer(a.unmanaged, 200, unmanagedDoc("github-2-1"));
  await h.flush();
  assert.match(h.$("drift-rows").innerHTML, /caller-one/);
  assert.doesNotMatch(h.$("drift-rows").innerHTML, /github-2-1/);
  assert.equal(h.$("unmanaged").innerHTML, h.R.unmanagedPanel(unmanagedDoc("github-1-1")));
  assert.match(h.$("drift-context").textContent, /github-1-1/);
});

test("Refresh and expiry ask the API again; responses are never served after a minute", async () => {
  const h = harness();
  await h.signIn();
  const p = paths("");
  assert.equal(h.sent(p.callers), 1);
  h.autoAnswer("");
  h.$("refresh").fire("click");  // Refresh: everything again, even if recent
  await h.flush();
  assert.equal(h.sent("/api/summary"), 3);  // pre-sign-in check, sign-in, Refresh
  assert.equal(h.sent(p.callers), 2);
  h.ctx.__clock.t += 60000;  // expiry: the next selection asks again
  h.$("filter-run").fire("change", { target: { value: "" } });
  await h.flush();
  assert.equal(h.sent("/api/summary"), 4);
  assert.equal(h.sent(p.plain), 3);
});

test("failures: errors are shown, nothing failed is kept, Refresh retries; empty runs say so", async () => {
  const h = harness();
  await h.signIn();
  h.click("github-2-1");
  await h.flush();
  const p = paths("github-2-1");
  h.answer(p.plain, 500, { error: "internal" });
  h.answer(p.callers, 500, { error: "internal" });
  h.answer(p.remediations, 200, { remediations: [] });
  h.answer(p.unmanaged, 200, unmanagedDoc("github-2-1"));
  await h.flush();
  assert.match(h.$("status").textContent, /internal/);
  assert.equal(h.$("unmanaged").innerHTML, h.R.unmanagedPanel(unmanagedDoc("github-2-1")));  // not held back
  h.$("refresh").fire("click");
  await h.flush();
  assert.equal(h.sent(p.plain), 2);  // retried
  h.answer("/api/summary", 200, summary());
  h.answer(p.plain, 200, { drifts: [] });
  h.answer(p.callers, 200, { drifts: [] });
  h.answer(p.remediations, 200, { remediations: [] });
  h.answer(p.unmanaged, 200, unmanagedDoc("github-2-1"));
  await h.flush();
  assert.match(h.$("drift-rows").innerHTML, /found no drift/);
  assert.match(h.$("status").textContent, /^Updated /);
  h.click("github-1-1");  // the drift rows load, but the caller lookup request fails
  await h.flush();
  const q = paths("github-1-1");
  h.answer(q.plain, 200, { drifts: [row("github-1-1")] });
  h.answer(q.remediations, 200, { remediations: [] });
  h.answer(q.unmanaged, 200, unmanagedDoc("github-1-1"));
  h.answer(q.callers, 502, { error: "query_failed" });
  await h.flush();
  assert.match(h.$("drift-rows").innerHTML, /res_github-1-1/);
  assert.match(h.$("drift-rows").innerHTML, /data-caller-status="lookup_failed"/);
  assert.match(h.$("status").textContent, /Caller recorded by Azure/);
});

test("authorization unchanged: a viewer is never sent callers; a rejected token signs out", async () => {
  const h = harness();
  await h.signIn("viewer-token", [403, { error: "caller_access_denied" }]);
  assert.match(h.$("drift-rows").innerHTML, /Not available \(needs the caller_reader role\)/);
  assert.doesNotMatch(h.$("drift-rows").innerHTML, /data-caller-status="loading"/);
  assert.match(h.$("status").textContent, /caller identity hidden for this user/);
  h.click("github-2-1");
  await h.flush();
  assert.equal(h.sent(paths("github-2-1").callers), 0);  // refused once: never asked again this session
  for (const key of ["plain", "remediations", "unmanaged"]) assert.equal(h.sent(paths("github-2-1")[key]), 1, key);
  h.$("refresh").fire("click");
  await h.flush();
  h.answer("/api/summary", 401, { error: "unauthenticated" });
  await h.flush();
  assert.equal(h.$("app").hidden, true);
  assert.match(h.$("signin-error").textContent, /not accepted/);
  const summaries = h.sent("/api/summary");
  await h.signIn();  // the next user's session starts with nothing from the previous one
  assert.equal(h.sent("/api/summary"), summaries + 1);
  assert.match(h.$("drift-rows").innerHTML, /caller-latest/);
});


// ---------------------------------------------------------------- Sign-in outcomes: access granted / denied

const UNAUTHENTICATED = [401, { error: "unauthenticated" }];
// What Vercel Authentication answers before the API sees the request (its `error` is not a string).
const PLATFORM_401 = [401, { error: { code: "401", message: "Protected deployment" }, message: "Protected by Vercel Authentication" }];
const emptySummary = () => Object.assign(summary(), { reports_total: 0, history: [], environments: [] });

// A harness page as index.html starts it: the dashboard and the sign-out button hidden.
function signInPage() {
  const h = harness();
  h.$("app").hidden = true;
  h.$("signout").hidden = true;
  return h;
}

async function submitSignIn(h, token) {
  h.$("token").value = token;
  h.$("signin-form").fire("submit", { preventDefault() {} });
  await h.flush();
}

// Answers the first load's open requests, `first` paths before the rest, each with answer(call, path).
async function answerFirstLoad(h, answer, first) {
  const p = paths("");
  for (const path of [...(first || []), "/api/summary", p.callers, p.plain, p.remediations, p.unmanaged]) {
    const open = h.open(path);
    if (open.length) { answer(open[0], path); await h.flush(); }
  }
  await h.flush();
}

function countPopups(h) {
  const dialog = h.$("auth-dialog");
  const counter = { shown: 0 };
  dialog.showModal = () => { counter.shown += 1; dialog.open = true; };
  return counter;
}

function assertSignedOut(h) {
  assert.equal(h.$("app").hidden, true);
  assert.equal(h.$("signin").hidden, false);
  assert.equal(h.$("signout").hidden, true);
}

test("sign-in: a rejected token is denied in the popup and on the sign-in screen, whatever answers first", async () => {
  const p = paths("");
  for (const first of [["/api/summary"], [p.callers], [p.unmanaged, p.callers]]) {  // the caller lookup may lose or win
    const h = signInPage();
    const popups = countPopups(h);
    await submitSignIn(h, "wrong-token");
    await answerFirstLoad(h, (call) => call.respond(...UNAUTHENTICATED), first);
    assertSignedOut(h);
    const dialog = h.$("auth-dialog");
    assert.equal(popups.shown, 1, first.join());
    assert.equal(dialog.open, true, first.join());
    assert.equal(dialog.dataset.state, "denied", first.join());
    assert.equal(dialog.getAttribute("role"), "alertdialog");
    assert.equal(h.$("auth-title").textContent, "Access denied");
    assert.equal(h.$("auth-retry").hidden, false);
    assert.match(h.$("signin-error").textContent, /^Access denied: the token was not accepted/);
    assert.equal(h.sent("/api/fetch/status"), 0);  // nothing is asked for a session that never started
    assert.equal(h.calls.filter((c) => c.auth === "Bearer wrong-token").length, 5);  // the first load only
    h.$("auth-retry").fire("click");  // "Try again": the popup closes, the reason stays on screen
    assert.equal(dialog.open, false);
    assert.match(h.$("signin-error").textContent, /^Access denied/);
  }
});

test("sign-in: granted only once every panel arrived; a valid empty dataset is a usable empty dashboard", async () => {
  const h = signInPage();
  await submitSignIn(h, "t0k3n");
  h.answer("/api/summary", 200, emptySummary());
  await h.flush();
  assert.equal(h.$("auth-dialog").dataset.state, "verifying");  // summary alone is not a loaded dashboard
  assert.equal(h.$("app").hidden, true);
  const p = paths("");
  h.answer(p.callers, 403, { error: "caller_access_denied" });
  h.answer(p.plain, 200, { drifts: [] });
  h.answer(p.remediations, 200, { remediations: [] });
  h.answer(p.unmanaged, 200, { runs: [] });
  await h.flush();
  assert.equal(h.$("auth-dialog").open, false);
  assert.equal(h.$("auth-dialog").dataset.state, "granted");
  assert.equal(h.$("app").hidden, false);
  assert.equal(h.$("signin").hidden, true);
  assert.equal(h.$("signin-error").textContent, "");
  assert.match(h.$("history").innerHTML, /No runs found\./);  // an explicit empty state, not an error
  assert.match(h.$("status").textContent, /^Updated .* from 0 run\(s\)/);
  assert.equal(h.$("status").classes.has("error"), false);
});

test("sign-in: server, network and platform failures are a retryable error, never 'access denied'", async () => {
  const cases = [
    ["server error", (call) => call.respond(500, { error: "internal" }), /Could not load data \(internal\)/],
    ["users file unusable", (call) => call.respond(503, { error: "auth_unavailable" }), /auth_unavailable/],
    ["network", (call) => call.fail(), /could not be reached/],
    ["platform 401", (call) => call.respond(...PLATFORM_401), /stopped before it reached the dashboard API/],
  ];
  for (const [name, fail, reason] of cases) {
    const h = signInPage();
    await submitSignIn(h, "t0k3n");
    await answerFirstLoad(h, fail);
    assertSignedOut(h);
    const dialog = h.$("auth-dialog");
    assert.equal(dialog.dataset.state, "error", name);
    assert.equal(dialog.getAttribute("role"), "alertdialog", name);
    assert.equal(h.$("auth-title").textContent, "Couldn’t load the dashboard", name);
    assert.match(h.$("auth-message").textContent, reason, name);
    assert.doesNotMatch(h.$("auth-title").textContent + h.$("signin-error").textContent, /Access denied/, name);
    assert.match(h.$("signin-error").textContent, reason, name);
    assert.match(h.$("signin-error").textContent, /The token was not rejected; try again\.$/, name);
    assert.equal(h.$("auth-retry").hidden, false, name);
    h.$("auth-retry").fire("click");
    await h.signIn();  // the retry path: the same sign-in works once the API answers
    assert.equal(h.$("app").hidden, false, name);
    assert.equal(h.$("signin-error").textContent, "", name);
  }
});

test("sign-in: pasted text the browser cannot send is denied at once, never reported as unreachable", async () => {
  // Observed live: a pasted paragraph showed "could not be reached", because fetch() refused the header and
  // no request was ever sent. Dummy text only; never a real token.
  const paragraphs = [["line break", "Terraform drift happens.\nA second line follows."],
    ["curly apostrophe", "It\u2019s a paragraph about drift, not a token"], ["em dash", "Drift \u2014 a paragraph"]];
  for (const [name, text] of paragraphs) {
    const h = signInPage();
    await h.flush();
    const before = h.calls.length;
    await submitSignIn(h, text);
    assertSignedOut(h);
    assert.equal(h.calls.length, before, name);  // nothing was sent
    const dialog = h.$("auth-dialog");
    assert.equal(dialog.open, true, name);
    assert.equal(dialog.dataset.state, "invalid", name);
    assert.equal(dialog.getAttribute("role"), "alertdialog", name);
    assert.equal(h.$("auth-title").textContent, "Access denied", name);
    assert.match(h.$("auth-message").textContent, /isn’t a valid token.*Nothing was sent/, name);
    assert.match(h.$("signin-error").textContent, /^Access denied: that is not a valid token/, name);
    for (const shown of [h.$("auth-message").textContent, h.$("signin-error").textContent]) {
      assert.doesNotMatch(shown, /could not be reached|not rejected|try again\.$/, name);
      assert.ok(!shown.includes(text), name);  // the pasted text is never echoed
    }
    h.$("auth-retry").fire("click");
    assert.equal(dialog.open, false, name);
    assert.match(h.$("signin-error").textContent, /^Access denied/, name);  // the reason stays on screen
    await h.signIn();  // a real token still works afterwards
    assert.equal(h.$("app").hidden, false, name);
  }
  const h = signInPage();  // a paragraph the browser can send reaches the API, and the API denies it
  const sendable = "Terraform drift happens when nobody notices it for weeks";
  await submitSignIn(h, sendable);
  assert.ok(h.calls.some((c) => c.auth === "Bearer " + sendable));
  await answerFirstLoad(h, (call) => call.respond(...UNAUTHENTICATED));
  assert.equal(h.$("auth-dialog").dataset.state, "denied");
  assert.match(h.$("signin-error").textContent, /^Access denied: the token was not accepted/);
});

test("sign-in popup: every failure is marked failed (red cross), never left looking like 'verifying'", async () => {
  // Observed live: "Access denied" for pasted text showed the verifying spinner, because styles.css only knew
  // the "denied" state. The failure look now follows data-failed, set for every failure state.
  const outcomes = [["denied", (c) => c.respond(...UNAUTHENTICATED)], ["forbidden", (c) => c.respond(403, { error: "forbidden" })],
    ["error", (c) => c.respond(500, { error: "internal" })], ["error", (c) => c.respond(...PLATFORM_401)]];
  for (const [state, answer] of outcomes) {
    const h = signInPage();
    await submitSignIn(h, "t0k3n");
    assert.equal(h.$("auth-dialog").dataset.state, "verifying", state);
    assert.equal(h.$("auth-dialog").dataset.failed, "false", state);  // verifying keeps its spinner
    await answerFirstLoad(h, answer);
    assert.equal(h.$("auth-dialog").dataset.state, state);
    assert.equal(h.$("auth-dialog").dataset.failed, "true", state);
  }
  const h = signInPage();
  await submitSignIn(h, "pasted\ntext");
  assert.equal(h.$("auth-dialog").dataset.state, "invalid");
  assert.equal(h.$("auth-dialog").dataset.failed, "true");
  await h.signIn();  // the next attempt starts unmarked and ends granted
  assert.equal(h.$("auth-dialog").dataset.state, "granted");
  assert.equal(h.$("auth-dialog").dataset.failed, "false");
});

test("sign-in: a valid token whose account lacks the viewer role is denied as such", async () => {
  const h = signInPage();
  await submitSignIn(h, "no-viewer");
  await answerFirstLoad(h, (call) => call.respond(403, { error: "forbidden" }));
  assertSignedOut(h);
  assert.equal(h.$("auth-dialog").dataset.state, "forbidden");
  assert.equal(h.$("auth-title").textContent, "Access denied");
  assert.match(h.$("auth-message").textContent, /viewer role/);
  assert.match(h.$("signin-error").textContent, /^Access denied: this token is valid, .*viewer role/);
});

test("sign-in: an empty token sends nothing; a repeated submit while verifying starts no second sign-in", async () => {
  const h = signInPage();
  await h.flush();
  const before = h.calls.length;  // the page's own pre-sign-in check
  const popups = countPopups(h);
  await submitSignIn(h, "   ");
  assert.equal(h.calls.length, before);
  assert.equal(popups.shown, 0);
  assert.equal(h.$("app").hidden, true);
  await submitSignIn(h, "t0k3n");
  await submitSignIn(h, "t0k3n");
  await submitSignIn(h, "other");
  assert.equal(popups.shown, 1);
  assert.equal(h.sent("/api/summary") - before, 1);
  assert.ok(h.calls.slice(before).every((c) => c.auth === "Bearer t0k3n"));
});

test("signed in: the API's 401 signs out with a message; a platform 401 or a network error keeps the session", async () => {
  let h = signInPage();
  await h.signIn();
  h.$("refresh").fire("click");
  await h.flush();
  h.answer("/api/summary", ...UNAUTHENTICATED);  // e.g. the token was revoked from the users file
  await h.flush();
  assertSignedOut(h);
  assert.match(h.$("signin-error").textContent, /^Signed out: the token was not accepted/);
  for (const [name, fail, reason] of [["platform 401", (c) => c.respond(...PLATFORM_401), /stopped before it reached/],
    ["network", (c) => c.fail(), /could not be reached/], ["server error", (c) => c.respond(502, { error: "bad_gateway" }), /bad_gateway/]]) {
    h = signInPage();
    await h.signIn();
    h.$("refresh").fire("click");
    await h.flush();
    fail(h.open("/api/summary")[0]);
    await h.flush();
    assert.equal(h.$("app").hidden, false, name);  // still signed in: the token was not rejected
    assert.match(h.$("status").textContent, reason, name);
    assert.equal(h.$("status").classes.has("error"), true, name);
    assert.match(h.$("history").innerHTML, /github-2-1/, name);  // the loaded data stays; Refresh retries
  }
});

test("sign-out: the session ends and later requests never carry the old token", async () => {
  const h = signInPage();
  await h.signIn("first-token");
  h.$("signout-confirm").fire("click");
  await h.flush();
  assertSignedOut(h);
  assert.equal(h.$("signin-error").textContent, "");
  const before = h.calls.length;
  await h.signIn("second-token");
  assert.ok(h.calls.slice(before).every((c) => c.auth !== "Bearer first-token"));
  assert.ok(h.calls.slice(before).some((c) => c.auth === "Bearer second-token"));
});


// ---------------------------------------------------------------- Task 13.4: Check GitHub for new runs

const fetchStatus = (status, extra) => Object.assign({ status, code: null, started_at: "2026-10-18T06:30:00Z",
  finished_at: status === "running" || status === "idle" ? null : "2026-10-18T06:31:00Z", counts: {},
  available: true, allowed: true, cooldown_seconds: 120, retry_after_seconds: null }, extra || {});

async function signedIn(statusDoc, options) {
  const h = harness(options);
  h.auto.set("/api/fetch/status", [200, statusDoc]);
  await h.signIn();
  h.auto.clear();
  return h;
}

const fetchCalls = (h) => h.calls.filter((c) => c.path.startsWith("/api/fetch"));

test("Check GitHub: hidden for users without data_refresher; Refresh and auto-refresh never fetch", async () => {
  const h = await signedIn(fetchStatus("idle", { allowed: false }));
  assert.equal(h.$("github-fetch").hidden, true);
  const before = fetchCalls(h).length;
  h.autoAnswer("");
  h.$("refresh").fire("click");
  await h.flush();
  assert.equal(fetchCalls(h).length, before);  // Refresh re-reads the local reports only
  assert.equal(h.calls.filter((c) => c.method !== "GET").length, 0);
});

test("Check GitHub: start, poll while running, then reload the local reports", async () => {
  const h = await signedIn(fetchStatus("idle"));
  const button = h.$("github-fetch");
  assert.equal(button.hidden, false);
  assert.equal(button.disabled, false);
  const summaries = h.sent("/api/summary");
  button.fire("click");
  await h.flush();
  const post = h.calls.filter((c) => c.path === "/api/fetch");
  assert.equal(post.length, 1);
  assert.equal(post[0].method, "POST");
  assert.ok(post[0].auth);  // the dashboard sign-in token only; the page never holds a GitHub token
  h.answer("/api/fetch", 202, fetchStatus("running"));
  await h.flush();
  assert.equal(button.disabled, true);
  assert.equal(button.getAttribute("aria-busy"), "true");
  assert.match(h.$("github-fetch-status").textContent, /Checking GitHub for new runs/);
  h.answer("/api/fetch/status", 200, fetchStatus("running"));  // still running: keeps polling
  await h.flush();
  h.autoAnswer("");
  h.answer("/api/fetch/status", 200, fetchStatus("new_artifacts", { counts: { fetched: 4, already_present: 77 } }));
  await h.flush();
  assert.match(h.$("github-fetch-status").textContent, /Downloaded 4 new artifact\(s\) from GitHub/);
  assert.equal(h.$("github-fetch-status").dataset.tone, "ok");
  assert.equal(button.disabled, false);
  assert.equal(button.getAttribute("aria-busy"), null);
  assert.equal(h.sent("/api/summary"), summaries + 1);  // cache invalidated, local reports reloaded
  assert.equal(h.open("/api/fetch/status").length, 0);  // polling stopped
});

test("Check GitHub: refusals and failures are explained; the local data stays", async () => {
  const h = await signedIn(fetchStatus("idle"));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 429, { error: "fetch_cooldown" });
  await h.flush();
  assert.match(h.$("github-fetch-status").textContent, /Checked recently: try again/);
  assert.equal(h.$("github-fetch").disabled, false);
  assert.equal(h.$("app").hidden, false);  // still signed in, dashboard unchanged
  const failed = h.R.fetchView(fetchStatus("failed", { code: "artifacts_listing_failed_urlerror" }));
  assert.match(failed.text, /GitHub could not be reached/);
  assert.match(failed.text, /keeps showing the reports already saved locally/);
});

test("Check GitHub: not enabled without a server token; sign-out stops polling", async () => {
  const off = await signedIn(fetchStatus("idle", { available: false, unavailable_reason: "not_connected" }));
  assert.equal(off.$("github-fetch").hidden, false);
  assert.equal(off.$("github-fetch").disabled, false);  // opens the "Connect GitHub first" popup
  assert.equal(off.$("github-connect").hidden, false);
  assert.match(off.$("github-connect-label").textContent, /Connect GitHub/);
  assert.equal(off.$("github-fetch-status").hidden, true);  // "not connected" is explained in the popup instead
  off.$("github-fetch").fire("click");
  assert.equal(off.$("github-first-dialog").open, true);
  assert.equal(off.$("github-dialog").open, false);
  assert.equal(off.sent("/api/fetch"), 0);
  off.$("github-first-later").fire("click");
  assert.equal(off.$("github-first-dialog").open, false);
  const h = await signedIn(fetchStatus("running"));
  h.$("signout-confirm").fire("click");
  await h.flush();
  assert.equal(h.$("github-fetch").hidden, true);
  const pending = h.open("/api/fetch/status").length;
  await h.flush();
  assert.equal(h.open("/api/fetch/status").length, pending);  // no new polls after sign-out
});


test("Check GitHub: failed polls back off, then stop in a clear 'lost contact' state", async () => {
  const h = await signedIn(fetchStatus("idle"));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 202, fetchStatus("running"));
  await h.flush();
  const before = h.delays.length;
  for (let i = 0; i < 5; i += 1) {
    h.answer("/api/fetch/status", 502, { error: "bad_gateway" });
    await h.flush();
  }
  assert.deepEqual(h.delays.slice(before).filter((ms) => ms >= 2000), [4000, 8000, 16000, 30000]);
  assert.equal(h.open("/api/fetch/status").length, 0);  // gave up: no further polls
  assert.match(h.$("github-fetch-status").textContent, /Lost contact with the dashboard server/);
  assert.equal(h.$("github-fetch-status").dataset.tone, "error");
  assert.equal(h.$("github-fetch").disabled, false);  // a new click is possible
  assert.equal(h.$("app").hidden, false);
});

test("Check GitHub: a successful poll resets the backoff; watching stops after 11 minutes", async () => {
  const h = await signedIn(fetchStatus("idle"));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 202, fetchStatus("running"));
  await h.flush();
  h.answer("/api/fetch/status", 502, { error: "bad_gateway" });
  await h.flush();
  const mark = h.delays.length;
  h.answer("/api/fetch/status", 200, fetchStatus("running"));  // success: back to the 2 s pace
  await h.flush();
  assert.deepEqual(h.delays.slice(mark).filter((ms) => ms >= 2000), [2000]);
  h.ctx.__clock.t += 11 * 60 * 1000;
  h.answer("/api/fetch/status", 200, fetchStatus("running"));
  await h.flush();
  assert.match(h.$("github-fetch-status").textContent, /still running after 11 minutes; stopped watching/);
  assert.equal(h.open("/api/fetch/status").length, 0);
});

test("Check GitHub: the cooldown message clears itself; unavailable refusals show the reason", async () => {
  const h = await signedIn(fetchStatus("idle"));
  h.$("github-fetch").fire("click");
  await h.flush();
  const before = h.delays.length;
  h.open("/api/fetch")[0].respond(429, { error: "fetch_cooldown" }, { "Retry-After": "37" });
  await h.flush();
  assert.ok(h.delays.slice(before).includes(37000));  // cleared when the cooldown ends
  assert.equal(h.$("github-fetch-status").textContent, "");  // (timers fire at once in this harness)
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 503, { error: "fetch_unavailable" });
  await h.flush();
  h.answer("/api/fetch/status", 200, fetchStatus("idle", { available: false, unavailable_reason: "fetch_script_missing" }));
  await h.flush();
  assert.match(h.$("github-fetch-status").textContent, /fetch script was not found/);
  assert.equal(h.$("github-fetch").disabled, true);
});

// ---------------------------------------------------------------- Task 13.5: GitHub connection and status window

const conn = (extra) => Object.assign({ connected: true, source: "dashboard", verified: true, verified_at: null,
  last_error: null, last_attempt: null }, extra || {});
const disconnected = () => fetchStatus("idle", { available: false, unavailable_reason: "not_connected",
  connection: conn({ connected: false, source: null, verified: false }) });
const GH_SECRET = "gh-sentinel-not-a-real-token";

const connectCalls = (h) => h.calls.filter((c) => c.path === "/api/github/connect");

async function submitToken(h, value) {
  h.$("github-token").value = value;
  h.$("github-token").fire("keydown", { key: "Enter", isComposing: false, preventDefault() {} });  // Enter submits
  await h.flush();
}

test("Connect GitHub: the token is sent once in a POST body, emptied at once and never shown or stored", async () => {
  const h = await signedIn(disconnected());
  assert.equal(h.$("github-connect").hidden, false);
  assert.match(h.$("github-connect-label").textContent, /Connect GitHub/);
  h.$("github-fetch").fire("click");  // not connected: "Connect GitHub first", whose button opens the dialog
  assert.equal(h.$("github-first-dialog").open, true);
  h.$("github-first-connect").fire("click");
  assert.equal(h.$("github-first-dialog").open, false);
  assert.equal(h.$("github-dialog").open, true);
  assert.equal(h.sent("/api/fetch"), 0);
  await submitToken(h, GH_SECRET);
  assert.equal(h.$("github-token").value, "");  // emptied before the response arrives
  // Locked while verifying: mask dots as the placeholder stand in for the token, which is no longer on the page.
  assert.equal(h.$("github-token").disabled, true);
  assert.match(h.$("github-token").placeholder, /^•+$/);
  assert.ok(!h.$("github-token").placeholder.includes(GH_SECRET));
  const [call] = connectCalls(h);
  assert.equal(call.method, "POST");
  assert.ok(call.auth && !call.auth.includes(GH_SECRET));  // the dashboard token is a different credential
  assert.equal(h.$("github-submit").disabled, true);  // no double submit while verifying
  h.answer("/api/github/connect", 200, Object.assign(fetchStatus("idle", { connection: conn() }),
    { verification: { ok: true, category: null, http_status: null, need: null } }));
  await h.flush();
  assert.equal(h.$("github-dialog").open, false);
  assert.match(h.$("github-connect-label").textContent, /GitHub: connected/);
  assert.match(h.$("github-fetch-status").textContent, /GitHub connected: token verified/);
  const page = [...["github-fetch-status", "fetch-body", "github-error", "github-connect-label"]
    .map((id) => h.$(id).textContent + h.$(id).innerHTML), h.$("github-token").value].join("|");
  assert.ok(!page.includes(GH_SECRET));
});

test("Connect GitHub: an invalid token is explained, and a corrected one works without a reload", async () => {
  const h = await signedIn(disconnected());
  h.$("github-connect").fire("click");
  await submitToken(h, "wrong-token");
  h.answer("/api/github/connect", 200, Object.assign(disconnected(),
    { verification: { ok: false, category: "invalid_token", http_status: 401, need: null } }));
  await h.flush();
  assert.equal(h.$("github-dialog").open, true);  // stays open for the corrected token
  assert.match(h.$("github-error").textContent, /invalid, expired or revoked/);
  assert.match(h.$("github-error").textContent, /HTTP 401/);
  assert.equal(h.$("github-submit").disabled, false);
  assert.equal(h.$("github-token").value, "");
  assert.equal(h.$("github-token").disabled, false);  // unlocked again, empty, for the corrected token
  assert.equal(h.$("github-token").placeholder, "github_pat_…");
  await submitToken(h, "right-token");
  assert.equal(connectCalls(h).length, 2);
  h.answer("/api/github/connect", 200, Object.assign(fetchStatus("idle", { connection: conn() }),
    { verification: { ok: true } }));
  await h.flush();
  assert.equal(h.$("github-dialog").open, false);
  assert.match(h.$("github-connect-label").textContent, /GitHub: connected/);
});

test("Connect GitHub: server refusals are shown in plain words and an empty field sends nothing", async () => {
  const h = await signedIn(disconnected());
  h.$("github-connect").fire("click");
  await submitToken(h, "   ");
  assert.equal(connectCalls(h).length, 0);
  assert.match(h.$("github-error").textContent, /Paste a GitHub token/);
  await submitToken(h, "some-token");
  h.answer("/api/github/connect", 429, { error: "verify_too_soon" });
  await h.flush();
  assert.match(h.$("github-error").textContent, /wait a moment/i);
  await submitToken(h, "some-token");
  h.answer("/api/github/connect", 409, { error: "fetch_in_progress" });
  await h.flush();
  assert.match(h.$("github-error").textContent, /check is running/);
});

test("Disconnect GitHub forgets the token through the server", async () => {
  const h = await signedIn(fetchStatus("idle", { connection: conn() }));
  h.$("github-connect").fire("click");
  assert.equal(h.$("github-disconnect").hidden, false);
  h.$("github-disconnect").fire("click");
  await h.flush();
  assert.equal(h.calls.filter((c) => c.path === "/api/github/disconnect")[0].method, "POST");
  h.answer("/api/github/disconnect", 200, disconnected());
  await h.flush();
  assert.match(h.$("github-connect-label").textContent, /Connect GitHub/);
  assert.equal(h.$("github-dialog").open, false);
});

test("Disconnect GitHub removes the Fetch status button and closes the status window", async () => {
  const h = await signedIn(fetchStatus("no_new_artifacts", { connection: conn() }));
  assert.equal(h.$("fetch-details").hidden, false);
  h.$("fetch-details").fire("click");
  assert.equal(h.$("fetch-dialog").open, true);
  h.$("github-connect").fire("click");
  h.$("github-disconnect").fire("click");
  await h.flush();
  h.answer("/api/github/disconnect", 200, Object.assign(disconnected(), { status: "no_new_artifacts" }));
  await h.flush();
  assert.equal(h.$("fetch-details").hidden, true);
  assert.equal(h.$("fetch-dialog").open, false);
});

test("Status window: opens on start, hiding it never stops the check, it can be reopened and shows the result", async () => {
  const h = await signedIn(fetchStatus("idle", { connection: conn() }));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 202, fetchStatus("running", { stage: "listing", connection: conn() }));
  await h.flush();
  assert.equal(h.$("fetch-dialog").open, true);
  assert.match(h.$("fetch-body").innerHTML, /Running/);
  assert.match(h.$("fetch-body").innerHTML, /data-state="active"[^>]*><span class="fw-mark"[^>]*><\/span>Listing artifacts/);
  assert.doesNotMatch(h.$("fetch-body").innerHTML, /%/);  // no invented progress percentage
  h.$("fetch-hide").fire("click");  // hide: the check continues
  assert.equal(h.$("fetch-dialog").open, false);
  assert.equal(h.calls.filter((c) => c.path === "/api/fetch" && c.method === "POST").length, 1);
  assert.equal(h.open("/api/fetch/status").length, 1);  // still being watched
  assert.equal(h.$("fetch-details").hidden, false);
  assert.equal(h.$("app").hidden, false);  // the dashboard stays usable
  h.answer("/api/fetch/status", 200, fetchStatus("running", { stage: "downloading", connection: conn() }));
  await h.flush();
  assert.equal(h.$("fetch-dialog").open, false);  // an update does not pop it open again
  h.$("fetch-details").fire("click");  // reopen: current stage
  assert.equal(h.$("fetch-dialog").open, true);
  assert.match(h.$("fetch-body").innerHTML, /Downloading new reports/);
  h.autoAnswer("");
  h.answer("/api/fetch/status", 200, fetchStatus("new_artifacts", { stage: "issues", elapsed_seconds: 14,
    counts: { fetched: 4, already_present: 77, skipped_not_main: 2 }, connection: conn() }));
  await h.flush();
  const body = h.$("fetch-body").innerHTML;
  assert.match(body, /Completed/);
  assert.match(body, /New artifacts downloaded<\/dt><dd>4</);
  assert.match(body, /Skipped \(already saved\)<\/dt><dd>77</);
  assert.match(body, /Skipped \(not eligible\)<\/dt><dd>2</);
  assert.match(body, /14 s/);
  h.$("fetch-hide").fire("click");  // minimise (the only close control); the result can still be reviewed
  h.$("fetch-details").fire("click");
  assert.match(h.$("fetch-body").innerHTML, /Completed/);
});

test("Status window: a failed check names the category and HTTP status, offers retry and token replacement", async () => {
  const h = await signedIn(fetchStatus("idle", { connection: conn() }));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 202, fetchStatus("running", { connection: conn() }));
  await h.flush();
  h.answer("/api/fetch/status", 200, fetchStatus("failed", { code: "artifacts_listing_failed_http_401",
    category: "invalid_token", http_status: 401, need: "actions", stage: "listing",
    connection: conn({ verified: false, last_error: { category: "invalid_token", http_status: 401, need: "actions" } }) }));
  await h.flush();
  const body = h.$("fetch-body").innerHTML;
  assert.match(body, /Failed/);
  assert.match(body, /invalid, expired or revoked/);
  assert.match(body, /HTTP 401/);
  assert.match(body, /\[invalid_token\]/);
  assert.match(body, /data-state="failed"/);
  assert.equal(h.$("fetch-retry").hidden, false);
  assert.equal(h.$("fetch-replace").hidden, false);
  assert.match(h.$("github-fetch-status").textContent, /invalid, expired or revoked/);
  h.$("fetch-replace").fire("click");  // replace the token without leaving the page
  assert.equal(h.$("github-dialog").open, true);
  assert.match(h.$("github-title").textContent, /Replace/);
  assert.equal(h.$("github-disconnect").hidden, false);
});

test("Status window: sign-out closes both dialogs and clears a half-typed GitHub token", async () => {
  const h = await signedIn(fetchStatus("running", { connection: conn() }));
  h.$("fetch-details").fire("click");
  h.$("github-connect").fire("click");
  h.$("github-token").value = GH_SECRET;
  h.$("signout-confirm").fire("click");
  await h.flush();
  assert.equal(h.$("fetch-dialog").open, false);
  assert.equal(h.$("github-dialog").open, false);
  assert.equal(h.$("github-token").value, "");
});


test("GitHub token field: no form submit, masked text field where supported, password field otherwise", async () => {
  const masked = await signedIn(disconnected(), { css: true });
  assert.equal(masked.$("github-token").type, "text");  // CSS-masked text field: no password-manager save prompt
  const plain = harness();  // no CSS masking support: fall back to a password field, so it is never shown in clear
  assert.equal(plain.$("github-token").type, "password");
  // the button submits too, and a second click while verifying sends nothing
  masked.$("github-connect").fire("click");
  masked.$("github-token").value = "some-token";
  masked.$("github-submit").fire("click");
  masked.$("github-submit").fire("click");
  await masked.flush();
  assert.equal(connectCalls(masked).length, 1);
  // Enter while an IME composition is open does not submit
  masked.$("github-token").value = "x";
  masked.$("github-token").fire("keydown", { key: "Enter", isComposing: true, preventDefault() {} });
  await masked.flush();
  assert.equal(connectCalls(masked).length, 1);
});

test("Connect GitHub: a token without Issues: Read connects with a clear warning", async () => {
  const h = await signedIn(disconnected());
  h.$("github-connect").fire("click");
  await submitToken(h, "token-without-issues");
  const warning = { category: "insufficient_permissions", http_status: 403, need: "issues" };
  h.answer("/api/github/connect", 200, Object.assign(fetchStatus("idle", { connection: conn({ warning }) }),
    { verification: { ok: true, category: null, http_status: null, need: null, warning } }));
  await h.flush();
  assert.equal(h.$("github-dialog").open, false);
  assert.match(h.$("github-fetch-status").textContent, /lacks Issues: Read/);
  assert.equal(h.$("github-connect").dataset.tone, "warn");
});

test("Status window: Escape hides it (a non-modal dialog does not do that by itself); the check keeps running", async () => {
  const h = await signedIn(fetchStatus("idle", { connection: conn() }));
  h.$("github-fetch").fire("click");
  await h.flush();
  h.answer("/api/fetch", 202, fetchStatus("running", { connection: conn() }));
  await h.flush();
  assert.equal(h.$("fetch-dialog").open, true);
  let prevented = false;
  h.$("fetch-dialog").fire("keydown", { key: "Escape", preventDefault() { prevented = true; } });
  assert.equal(h.$("fetch-dialog").open, false);
  assert.ok(prevented);
  assert.equal(h.open("/api/fetch/status").length, 1);  // still watched
  h.$("fetch-dialog").fire("keydown", { key: "a", preventDefault() {} });  // other keys do nothing
});

test("Status window: every token problem offers Replace GitHub token; neutral failures do not", async () => {
  for (const [category, replace] of [["sso_required", true], ["repository_not_accessible", true],
    ["invalid_token", true], ["rate_limited", false], ["network_error", false]]) {
    const h = await signedIn(fetchStatus("idle", { connection: conn() }));
    h.$("github-fetch").fire("click");
    await h.flush();
    h.answer("/api/fetch", 202, fetchStatus("running", { connection: conn() }));
    await h.flush();
    h.answer("/api/fetch/status", 200, fetchStatus("failed", { code: "artifacts_listing_failed", category,
      connection: conn() }));
    await h.flush();
    assert.equal(h.$("fetch-replace").hidden, !replace, category);
    assert.equal(h.$("fetch-retry").hidden, false, category);
  }
});
