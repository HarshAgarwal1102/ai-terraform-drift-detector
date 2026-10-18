/*
 * Request cache for the dashboard controller (Run History performance).
 *
 * `createLoader(fetchJson, options)` wraps the controller's `/api/*` request function:
 * - a fresh response (younger than `ttlMs`, default 60 s: the auto-refresh interval) is
 *   reused, so opening a run again or going back to one does not ask the API again;
 * - an identical request already in flight is shared, never sent twice;
 * - failures are never cached, so the next request retries;
 * - `invalidate()` (Refresh, auto-refresh, sign-out) drops every entry, and a request that
 *   was in flight when it was called is not stored when it finishes.
 * Entries live in memory only, never in browser storage, and expire; nothing is kept
 * across a reload. No DOM access here, so `node --test` runs it (loader.test.js).
 */
(function (root) {
  "use strict";

  function createLoader(fetchJson, options) {
    const ttlMs = (options && options.ttlMs) || 60000;
    const now = (options && options.now) || Date.now;
    const entries = new Map();  // path -> {value, at}
    const pending = new Map();  // path -> {promise, generation}
    let generation = 0;

    function get(path) {
      const hit = entries.get(path);
      if (hit && now() - hit.at < ttlMs) return Promise.resolve(hit.value);
      if (hit) entries.delete(path);  // expired: never served
      const inflight = pending.get(path);
      if (inflight && inflight.generation === generation) return inflight.promise;
      const started = generation;
      const promise = Promise.resolve().then(() => fetchJson(path)).then((value) => {
        if (started === generation) entries.set(path, { value, at: now() });
        return value;
      }).finally(() => {
        const current = pending.get(path);
        if (current && current.promise === promise) pending.delete(path);
      });
      pending.set(path, { promise, generation: started });
      return promise;
    }

    function cached(path) {
      const hit = entries.get(path);
      return hit && now() - hit.at < ttlMs ? hit.value : undefined;
    }

    function invalidate() {
      generation += 1;
      entries.clear();
    }

    return { get, cached, invalidate, size: () => entries.size };
  }

  const api = { createLoader };
  root.DashboardLoader = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
