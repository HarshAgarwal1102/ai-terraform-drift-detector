/*
 * Tests for dashboard/loader.js (Run History performance). Run: node --test dashboard/
 * (tests/test_dashboard_ui.py runs them under pytest). No dependencies, no network.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const { createLoader } = require("./loader.js");

function deferredFetch() {
  const calls = [];
  const fetchJson = (path) => new Promise((resolve, reject) => calls.push({ path, resolve, reject }));
  return { calls, fetchJson };
}

const tick = () => new Promise((resolve) => setImmediate(resolve));

test("loader: identical requests in flight are sent once and shared", async () => {
  const { calls, fetchJson } = deferredFetch();
  const loader = createLoader(fetchJson, { now: () => 0 });
  const a = loader.get("/api/drifts?report_id=r1");
  const b = loader.get("/api/drifts?report_id=r1");
  await tick();
  assert.equal(calls.length, 1);
  calls[0].resolve({ drifts: [1] });
  assert.deepEqual(await a, { drifts: [1] });
  assert.equal(await b, await a);
});

test("loader: a fresh response is reused, an expired one is fetched again", async () => {
  const { calls, fetchJson } = deferredFetch();
  let clock = 1000;
  const loader = createLoader(fetchJson, { ttlMs: 60000, now: () => clock });
  const first = loader.get("/api/summary");
  await tick();
  calls[0].resolve({ n: 1 });
  await first;
  clock += 59999;
  assert.deepEqual(await loader.get("/api/summary"), { n: 1 });
  assert.equal(calls.length, 1);
  assert.deepEqual(loader.cached("/api/summary"), { n: 1 });
  clock += 1;  // exactly ttlMs old: expired, never served
  assert.equal(loader.cached("/api/summary"), undefined);
  const again = loader.get("/api/summary");
  await tick();
  assert.equal(calls.length, 2);
  calls[1].resolve({ n: 2 });
  assert.deepEqual(await again, { n: 2 });
});

test("loader: failures are not cached, so the next request retries", async () => {
  const { calls, fetchJson } = deferredFetch();
  const loader = createLoader(fetchJson, { now: () => 0 });
  const failing = loader.get("/api/unmanaged");
  await tick();
  calls[0].reject(Object.assign(new Error("x"), { status: 500 }));
  await assert.rejects(failing);
  assert.equal(loader.cached("/api/unmanaged"), undefined);
  const retry = loader.get("/api/unmanaged");
  await tick();
  assert.equal(calls.length, 2);
  calls[1].resolve({ runs: [] });
  assert.deepEqual(await retry, { runs: [] });
});

test("loader: invalidate() drops entries and never stores a response that was in flight", async () => {
  const { calls, fetchJson } = deferredFetch();
  const loader = createLoader(fetchJson, { now: () => 0 });
  const done = loader.get("/api/summary");
  await tick();
  calls[0].resolve({ old: true });
  await done;
  const inflight = loader.get("/api/remediations");
  await tick();
  loader.invalidate();
  assert.equal(loader.size(), 0);
  const fresh = loader.get("/api/remediations");  // not shared with the pre-invalidation request
  await tick();
  assert.equal(calls.length, 3);
  calls[1].resolve({ stale: true });
  assert.deepEqual(await inflight, { stale: true });
  assert.equal(loader.cached("/api/remediations"), undefined);  // the stale response was not stored
  calls[2].resolve({ stale: false });
  assert.deepEqual(await fresh, { stale: false });
  assert.deepEqual(loader.cached("/api/remediations"), { stale: false });
});

test("loader: different paths are independent requests", async () => {
  const { calls, fetchJson } = deferredFetch();
  const loader = createLoader(fetchJson, { now: () => 0 });
  loader.get("/api/drifts?report_id=a");
  loader.get("/api/drifts?report_id=b");
  loader.get("/api/drifts?include_caller=true&report_id=a");
  await tick();
  assert.deepEqual(calls.map((c) => c.path),
    ["/api/drifts?report_id=a", "/api/drifts?report_id=b", "/api/drifts?include_caller=true&report_id=a"]);
});
