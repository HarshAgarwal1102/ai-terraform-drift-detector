/*
 * Dashboard render functions (Task 13.2).
 *
 * Pure functions from API documents to escaped HTML strings, shared by app.js in the
 * browser and by render.test.js under `node --test`. Every value from the API is
 * escaped: artifacts carry text that may be crafted (injection fixtures exist).
 * Nothing here touches the network, the DOM or browser storage.
 */
(function (root) {
  "use strict";

  const SEVERITY_ORDER = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"];
  const CALLER_TYPES = {
    user: "User",
    service_principal: "Service principal",
    managed_identity: "Managed identity",
    unknown: "Unknown type",
  };
  const UNKNOWN_REASONS = {
    no_investigation: "no bound investigation",
    no_decisive_operation: "no single identified change",
    caller_missing: "Azure recorded no caller",
    caller_inconsistent: "Azure recorded different callers",
    no_match: "no matching Activity Log record",
    multiple_matches: "more than one matching record",
    retention_exceeded: "older than the 90-day Activity Log retention",
    query_failed: "Activity Log query failed",
    address_unknown: "resource not in the local Terraform state",
    invalid_resource_id: "unusable Azure resource ID",
    resource_ids_unavailable: "no local Terraform state configured",
    local_only: "lookups are local-only",
  };

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function severityClass(level) {
    return SEVERITY_ORDER.includes(level) ? "sev-" + level.toLowerCase() : "sev-unknown";
  }

  function severityBadge(level) {
    return '<span class="badge ' + severityClass(level) + '">' + esc(level || "n/a") + "</span>";
  }

  /* An expected/actual value of the drift report: {status: "value", value} or a status only. */
  function formatValue(view) {
    if (!view || typeof view !== "object") return "(unknown)";
    if (view.status === "value") return JSON.stringify(view.value);
    return "(" + (view.status || "unknown") + ")";
  }

  function formatTime(timestamp) {
    if (!timestamp) return "n/a";
    return String(timestamp).replace("T", " ").replace(/\.\d+Z$|Z$/, " UTC");
  }

  /* The `Caller recorded by Azure` field. `caller` is the API object, or null when the
     signed-in user may not see caller identity. */
  function callerField(caller) {
    if (!caller) {
      return '<span class="caller caller-denied" data-caller-status="not_authorized">' +
        "Not available (needs the caller_reader role)</span>";
    }
    const type = CALLER_TYPES[caller.caller_type] || CALLER_TYPES.unknown;
    if (caller.status === "matched" && caller.value !== "Unknown") {
      return '<span class="caller caller-recorded" data-caller-status="matched">' +
        '<span class="caller-value">' + esc(caller.value) + "</span> " +
        '<span class="caller-type">' + esc(type) + "</span></span>";
    }
    const reason = UNKNOWN_REASONS[caller.status] || caller.status || "not determinable";
    return '<span class="caller caller-unknown" data-caller-status="' + esc(caller.status) + '">' +
      '<span class="caller-value">Unknown</span> <span class="caller-reason">' + esc(reason) + "</span></span>";
  }

  function overviewCards(summary) {
    const o = (summary && summary.overview) || {};
    const cost = o.monthly_cost_impact || {};
    const exposure = ((summary && summary.environments) || []).reduce(
      (sum, env) => sum + (((env.security_exposure || {}).ai_security_findings) || 0), 0);
    const cards = [
      ["Total Resources", o.total_resources, "managed resources in the latest run per environment"],
      ["Active Drifts", o.active_drifts, "drifted resources in the latest run per environment"],
      ["Security Exposure", o.security_exposure,
        "HIGH or CRITICAL drifts; " + exposure + " AI security finding(s)"],
      ["Monthly Cost Impact", cost.complete ? "$" + cost.monthly_cost_delta : "Not available",
        cost.complete ? "USD list prices, confirmed drift" : "no validated cost estimate in the AI report"],
    ];
    return cards.map(([title, value, hint]) =>
      '<article class="card"><h2>' + esc(title) + '</h2><p class="card-value">' +
      esc(value === undefined || value === null ? "n/a" : value) + '</p><p class="card-hint">' + esc(hint) +
      "</p></article>").join("");
  }

  function severityBreakdown(summary) {
    const counts = {};
    ((summary && summary.environments) || []).forEach((env) => {
      Object.entries(env.severity_counts || {}).forEach(([level, n]) => { counts[level] = (counts[level] || 0) + n; });
    });
    const total = Object.values(counts).reduce((a, b) => a + b, 0);
    if (!total) return '<p class="empty">No resources in the latest runs.</p>';
    return SEVERITY_ORDER.filter((level) => counts[level]).map((level) =>
      '<div class="bar-row"><span class="bar-label">' + severityBadge(level) + "</span>" +
      '<progress class="' + severityClass(level) + '" max="' + total + '" value="' + counts[level] + '"></progress>' +
      '<span class="bar-count">' + counts[level] + "</span></div>").join("");
  }

  function historyRows(summary) {
    const history = (summary && summary.history) || [];
    if (!history.length) return '<tr><td colspan="5" class="empty">No runs found.</td></tr>';
    return history.map((run) =>
      "<tr><td>" + esc(formatTime(run.finished_at)) + "</td><td>" + esc(run.environment) + "</td><td>" +
      esc(run.report_id) + "</td><td>" + esc(run.drifted_resources) + "</td><td>" +
      severityBadge(run.highest_severity) + "</td></tr>").join("");
  }

  function filterOptions(drifts) {
    const unique = (key) => Array.from(new Set(drifts.map((d) => d[key]).filter(Boolean))).sort();
    return {
      severity: SEVERITY_ORDER.filter((level) => drifts.some((d) => d.severity === level)),
      type: unique("type"),
      environment: unique("environment"),
    };
  }

  function filterDrifts(drifts, filters) {
    const f = filters || {};
    return drifts.filter((d) => (!f.severity || d.severity === f.severity) && (!f.type || d.type === f.type) &&
      (!f.environment || d.environment === f.environment));
  }

  function optionTags(values, selected) {
    return '<option value="">All</option>' + values.map((v) =>
      '<option value="' + esc(v) + '"' + (v === selected ? " selected" : "") + ">" + esc(v) + "</option>").join("");
  }

  /* The run selector: the latest run per environment (default) or one run of the history. */
  function runOptions(summary, selected) {
    const runs = ((summary && summary.history) || []);
    return '<option value="">Latest per environment</option>' + runs.map((run) =>
      '<option value="' + esc(run.report_id) + '"' + (run.report_id === selected ? " selected" : "") + ">" +
      esc(formatTime(run.finished_at) + " · " + run.environment + " · " + run.drifted_resources + " drift(s)") +
      "</option>").join("");
  }

  function changeList(drift) {
    const changes = drift.changes || [];
    if (!changes.length) return '<span class="empty">no attribute changes listed</span>';
    return '<ul class="changes">' + changes.map((c) =>
      '<li><code class="prop">' + esc(c.property) + "</code> " +
      '<span class="expected" title="expected (declared configuration)">' + esc(formatValue(c.expected)) + "</span>" +
      ' <span class="arrow">&rarr;</span> ' +
      '<span class="actual" title="actual (what Azure returned)">' + esc(formatValue(c.actual)) + "</span></li>")
      .join("") + "</ul>";
  }

  function operationTime(drift) {
    const op = drift.operation;
    if (!op || !op.op_id) return '<span class="empty">no identified change</span>';
    return '<span class="op-time">' + esc(formatTime(op.start)) + '</span><br><span class="op-name">' +
      esc(op.operation_name) + "</span>";
  }

  /* One table row per drifted resource; `index` is the drift's position in the full list. */
  function driftRows(drifts, indices) {
    if (!drifts.length) return '<tr><td colspan="7" class="empty">No drift matches the filters.</td></tr>';
    return drifts.map((d, i) =>
      '<tr><td><span class="address">' + esc(d.address) + '</span><br><span class="rtype">' + esc(d.type) +
      "</span></td><td>" + esc(d.environment) + "</td><td>" + severityBadge(d.severity) + "</td><td>" +
      changeList(d) + "</td><td>" + operationTime(d) + "</td><td>" +
      callerField(d.caller_recorded_by_azure === undefined ? null : d.caller_recorded_by_azure) +
      '</td><td><button type="button" class="details" data-index="' + esc(indices ? indices[i] : i) +
      '">Details</button></td></tr>').join("");
  }

  /* A Terraform-style diff of one drifted resource: what apply would change back. */
  function hclDiff(drift) {
    const lines = ["# " + drift.address + " (" + (drift.classification || "drift") + ")",
      "# - expected: declared configuration   + actual: value in Azure"];
    (drift.changes || []).forEach((c) => {
      lines.push("  ~ " + c.property);
      lines.push("    - " + formatValue(c.expected));
      lines.push("    + " + formatValue(c.actual));
    });
    return lines.join("\n");
  }

  function remediationBlock(drift, remediations) {
    const rec = drift.remediation;
    const options = (remediations || []).filter((o) => o.address === drift.address && o.report_id === drift.report_id);
    let html = rec
      ? "<p>Recommendation: <strong>" + esc(rec.kind) + "</strong> (" + esc(rec.decision) + ", policy " +
        esc(rec.policy_rule) + "). Approval required: " + esc(rec.approval_required ? "yes" : "no") +
        ". Automatic apply: " + esc(rec.automatic_apply ? "yes" : "no") + ".</p>"
      : '<p class="empty">No remediation recommendation in the AI report.</p>';
    if (options.length) {
      html += '<table class="options"><thead><tr><th>Option</th><th>Approval</th><th>Execution</th></tr></thead><tbody>' +
        options.map((o) => "<tr><td>" + esc(o.kind) + (o.recommended ? ' <span class="badge rec">recommended</span>' : "") +
          '<br><span class="hint">' + esc(o.description) + "</span></td><td>" +
          '<span class="status status-' + esc(o.approval.status) + '">' + esc(o.approval.status) + "</span></td><td>" +
          esc(o.execution.allowed ? "allowed" : "not allowed") + " (" + esc(o.execution.mode) + ")</td></tr>").join("") +
        "</tbody></table>";
    }
    return html;
  }

  function detailModal(drift, remediations) {
    const narrative = ((drift.ai_analysis || {}).narrative) || [];
    return '<header class="modal-head"><h2>' + esc(drift.address) + "</h2>" + severityBadge(drift.severity) +
      '</header><dl class="facts"><dt>Run</dt><dd>' + esc(drift.report_id) + "</dd><dt>Environment</dt><dd>" +
      esc(drift.environment) + "</dd><dt>Operation time</dt><dd>" + operationTime(drift) +
      "</dd><dt>Caller recorded by Azure</dt><dd>" +
      callerField(drift.caller_recorded_by_azure === undefined ? null : drift.caller_recorded_by_azure) +
      "</dd></dl><section><h3>Terraform diff</h3><pre class=\"hcl\">" + esc(hclDiff(drift)) + "</pre></section>" +
      "<section><h3>AI analysis</h3>" + (narrative.length
        ? "<ol class=\"narrative\">" + narrative.map((t) => "<li>" + esc(t) + "</li>").join("") + "</ol>"
        : '<p class="empty">No AI analysis for this resource.</p>') + "</section>" +
      "<section><h3>Remediation status</h3>" + remediationBlock(drift, remediations) + "</section>" +
      '<p class="hint">A recorded caller is the identity Azure logged for the operation; it is not proof of ' +
      "which person made the change.</p>";
  }

  const api = {
    esc, formatValue, formatTime, callerField, overviewCards, severityBreakdown, historyRows, filterOptions,
    filterDrifts, optionTags, runOptions, driftRows, hclDiff, detailModal, UNKNOWN_REASONS,
  };
  root.DashboardRender = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
