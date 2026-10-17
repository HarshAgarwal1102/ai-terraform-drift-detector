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
    activity_log_not_settled: "Activity Log evidence had not settled (10-minute margin); not looked up",
    azure_sign_in_unavailable: "Azure sign-in unavailable on the dashboard host (run az login)",
    azure_access_denied: "the signed-in Azure identity may not read the Activity Log",
  };
  const CALLER_NOTE = "The identity Azure recorded for this operation; not proof of which person made the change.";

  function esc(value) {
    return String(value === null || value === undefined ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  /* The error code of a failed API response. Every dashboard-api error is JSON
     {"error": "<code>"}; a 404 without that body means this page's origin does not serve
     the dashboard API (for example index.html opened from a static server or file preview). */
  function apiErrorCode(status, body) {
    if (body && typeof body === "object" && typeof body.error === "string") return body.error;
    return status === 404 ? "api_not_found" : "http_" + status;
  }

  /* Plain text (set with textContent): what a failed request means and what to do. */
  function errorMessage(code, origin) {
    if (code === "api_not_found") {
      return "The dashboard API was not found at " + origin + "/api/. Open the dashboard from the " +
        "dashboard-api server (by default 127.0.0.1, port 8000), not as a static file or file preview.";
    }
    if (code === "network_error") return "The dashboard API at " + origin + " could not be reached.";
    return "Could not load data (" + code + ").";
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
     signed-in user may not see caller identity. A drift with no single identified change
     (e.g. an ambiguous verdict) lists the recorded caller of each operation instead; none of
     them is the drift's caller. */
  function callerField(caller) {
    if (!caller) {
      return '<span class="caller caller-denied" data-caller-status="not_authorized">' +
        "Not available (needs the caller_reader role)</span>";
    }
    if (caller.status === "no_decisive_operation" && Array.isArray(caller.operations) && caller.operations.length) {
      return '<div class="caller caller-operations" data-caller-status="no_decisive_operation">' +
        '<span class="caller-reason">No single identified change; caller recorded for each operation:</span>' +
        '<ul class="caller-ops">' + caller.operations.map((op) =>
          '<li data-op-id="' + esc(op.op_id) + '"><span class="op-ref">' + esc(op.op_id) + " · " +
          esc(formatTime(op.start)) + "</span> " + callerField(Object.assign({}, op, { operations: undefined })) +
          "</li>").join("") + "</ul></div>";
    }
    const type = CALLER_TYPES[caller.caller_type] || CALLER_TYPES.unknown;
    if (caller.status === "matched" && caller.value !== "Unknown") {
      return '<span class="caller caller-recorded" data-caller-status="matched" title="' + esc(CALLER_NOTE) + '">' +
        '<span class="caller-value">' + esc(caller.value) + "</span> " +
        '<span class="caller-type">' + esc(type) + "</span></span>";
    }
    const reason = UNKNOWN_REASONS[caller.status] || caller.status || "not determinable";
    return '<span class="caller caller-unknown" data-caller-status="' + esc(caller.status) + '">' +
      '<span class="caller-value">Unknown</span> <span class="caller-reason">' + esc(reason) + "</span></span>";
  }

  /* A link only to a GitHub issue page; anything else is shown as text. */
  function issueLink(issue) {
    const label = "#" + issue.number;
    return /^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/issues\/[0-9]+$/.test(issue.url || "")
      ? '<a href="' + esc(issue.url) + '" target="_blank" rel="noopener noreferrer">' + esc(label) + "</a>"
      : esc(label);
  }

  /* The drift issue state (Tasks 8.1/8.3) from the GitHub snapshot; never guessed. */
  function issueField(issue) {
    if (!issue || issue.status === "no_snapshot") {
      return '<span class="issue issue-none" data-issue-status="no_snapshot">No issue data</span>';
    }
    if (issue.status === "none_found") {
      return '<span class="issue issue-none" data-issue-status="none_found">No drift issue found</span>';
    }
    const resolution = issue.status === "closed"
      ? "closed" + (issue.state_reason ? " · " + issue.state_reason : "") : "open";
    const when = issue.status === "closed" ? formatTime(issue.closed_at) : "since " + formatTime(issue.created_at);
    return '<span class="issue issue-' + esc(issue.status) + '" data-issue-status="' + esc(issue.status) + '">' +
      issueLink(issue) + ' <span class="badge status-' + esc(issue.status) + '">' + esc(resolution) + "</span>" +
      '<span class="issue-when">' + esc(when) + "</span></span>";
  }

  function remediationPrField(pr) {
    if (!pr) return '<span class="empty">n/a</span>';
    return '<span class="pr pr-' + esc(pr.status) + '" data-pr-status="' + esc(pr.status) + '">' +
      (pr.status === "not_enabled" ? "No remediation PR" : esc(pr.status)) +
      '<span class="issue-when">' + esc(pr.reason || "") + "</span></span>";
  }

  function issuesPanel(summary) {
    const data = (summary && summary.issues) || {};
    if (!data.snapshot) {
      return '<p class="empty">No GitHub issue snapshot in the data directory (run scripts/fetch_dashboard_data.py).</p>';
    }
    const head = '<p class="hint">' + esc(data.open) + " open, " + esc(data.closed) + " closed · snapshot " +
      esc(formatTime(data.fetched_at)) + "</p>";
    if (!data.items.length) return head + '<p class="empty">No drift issues.</p>';
    return head + '<div class="table-wrap"><table><thead><tr><th>Issue</th><th>Resource</th><th>State</th>' +
      "<th>Opened</th><th>Closed</th></tr></thead><tbody>" + data.items.map((i) =>
        "<tr><td>" + issueLink(i) + '</td><td><span class="address">' + esc(i.address || "(not in any report)") +
        "</span>" + (i.environment ? '<br><span class="rtype">' + esc(i.environment) + "</span>" : "") +
        '</td><td><span class="badge status-' + esc(i.state) + '">' + esc(i.state +
          (i.state_reason ? " · " + i.state_reason : "")) + "</span></td><td>" + esc(formatTime(i.created_at)) +
        "</td><td>" + esc(i.closed_at ? formatTime(i.closed_at) : "—") + "</td></tr>").join("") +
      "</tbody></table></div>";
  }

  const COST_STATUS = {
    complete: "estimated from Azure Retail Prices API list prices (not billing)",
    partial: "partly estimated: some resources could not be priced",
    failed: "pricing failed: no amounts",
    not_run: "pricing did not run: no amounts",
    not_available: "the AI report has no unmanaged estimate",
    rejected: "the AI report rejected the unmanaged input: no amounts",
    no_ai_report: "no AI report for this run: no amounts",
    not_in_ai_report: "this AI report predates unmanaged estimates: no amounts",
    inventory_mismatch: "the AI report priced a different inventory: no amounts",
    ai_section_invalid: "the AI report's unmanaged section is invalid: no amounts",
  };
  const CATEGORY = { unmanaged: "Not managed by Terraform", attached_to_managed: "Attached to a managed resource" };

  /* Resources in the Terraform-managed resource groups that Terraform does not manage (Task 10.4). */
  function unmanagedPanel(doc) {
    const runs = (doc && doc.runs) || [];
    if (!runs.length) return '<p class="empty">No run selected.</p>';
    return runs.map((run) => {
      const head = "<h3>" + esc(run.environment) + " · " + esc(run.report_id) + "</h3>";
      if (!run.available) {
        return head + '<p class="empty">No unmanaged-resource inventory for this run.</p>';
      }
      const counts = run.counts || {};
      const totals = (run.cost && run.cost.totals) || null;
      const total = totals && totals.display ? totals.display + (totals.complete ? "" : " (incomplete)")  // display is unmanaged_cost.format_usd: "$8.18/month"
        : "no estimate";
      const summary = '<p class="hint">Inventory ' + esc(run.outcome) + (run.failure ? " (" + esc(run.failure) + ")" : "") +
        " · " + esc(counts.unmanaged) + " not managed by Terraform · " + esc(counts.attached_to_managed) +
        " attached to a managed resource · collected " + esc(formatTime(run.collected_at)) + "</p>" +
        '<p class="hint">Estimated monthly cost: <strong>' + esc(total) + "</strong> — " +
        esc(COST_STATUS[run.cost.status] || run.cost.status) + ". Unmanaged resources are not drift.</p>";
      const failed = (run.scopes || []).filter((s) => s.status !== "complete");
      const scopes = failed.length ? '<p class="error">Not fully listed: ' + failed.map((s) =>
        esc(s.resource_group) + " (" + esc(s.status) + ", " + esc(s.error) + ")").join(", ") + "</p>" : "";
      const rows = (run.resources || []).length ? run.resources.map((r) =>
        "<tr><td>" + esc(r.name || "(name withheld)") + '<br><span class="rtype">' + esc(r.type) + "</span></td><td>" +
        esc(r.resource_group) + "</td><td>" + esc(r.location || "n/a") + "</td><td>" +
        esc(CATEGORY[r.category] || r.category) +
        (r.attached_to && r.attached_to.address ? '<br><span class="rtype">' + esc(r.attached_to.address) + "</span>" : "") +
        "</td><td>" + (r.estimate
          ? esc(r.estimate.display || "not priced") + '<br><span class="rtype">' +
            esc(r.estimate.status + (r.estimate.reason ? " · " + r.estimate.reason : "")) + "</span>"
          : '<span class="empty">no estimate</span>') + "</td></tr>").join("")
        : '<tr><td colspan="5" class="empty">No resources outside Terraform.</td></tr>';
      return head + summary + scopes + '<div class="table-wrap"><table class="unmanaged"><thead><tr><th>Resource</th>' +
        "<th>Resource group</th><th>Location</th><th>Category</th><th>Estimated monthly cost</th></tr></thead><tbody>" +
        rows + "</tbody></table></div>";
    }).join("");
  }

  /* Cost card states other than an amount (status "estimated"). Never an invented "$0". */
  const COST_CARD = {
    no_drift_cost: ["No drift cost", "validated estimate: no cost line for confirmed drift"],
    not_available: ["Not available", "no validated drift cost estimate in the AI report"],
  };

  function money(amount) {
    const text = String(amount === null || amount === undefined ? "" : amount);
    return text.startsWith("-") ? "-$" + text.slice(1) : "$" + text;
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
      cost.status === "estimated"
        ? ["Monthly Cost Impact", money(cost.monthly_cost_delta),
          "USD list prices of confirmed drift" + (cost.complete ? "" : " (incomplete: some lines unpriced)")]
        : ["Monthly Cost Impact"].concat(COST_CARD[cost.status] || COST_CARD.not_available),
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

  /* Runs whose run id (including the GitHub run number), finish time, environment or highest
     severity contains every word of the query (case-insensitive). */
  function filterHistory(history, query) {
    const words = String(query || "").toLowerCase().split(/\s+/).filter(Boolean);
    if (!words.length) return history;
    return history.filter((run) => {
      const text = [run.report_id, run.finished_at, formatTime(run.finished_at), run.environment,
        run.highest_severity].join(" ").toLowerCase();
      return words.every((word) => text.includes(word));
    });
  }

  /* Unmanaged resources of a run in the history: "5 · $44.85/month", "0", or "—" without an inventory. */
  function historyUnmanaged(run) {
    const u = run.unmanaged || {};
    if (!u.available) return '<span class="empty">—</span>';
    return esc(u.unmanaged) + (u.unmanaged && u.display ? " · " + esc(u.display) : "");
  }

  /* One row per run; a row opens that run (click or Enter). `selected` is the open run id. */
  function historyRows(summary, query, selected) {
    const all = (summary && summary.history) || [];
    if (!all.length) return '<tr><td colspan="6" class="empty">No runs found.</td></tr>';
    const history = filterHistory(all, query);
    if (!history.length) return '<tr><td colspan="6" class="empty">No run matches the search.</td></tr>';
    return history.map((run) =>
      '<tr class="run-row' + (run.report_id === selected ? " selected" : "") + '" tabindex="0" data-run="' +
      esc(run.report_id) + '"' + (run.report_id === selected ? ' aria-current="true"' : "") +
      ' title="Open this run">' +
      "<td>" + esc(formatTime(run.finished_at)) + "</td><td>" + esc(run.environment) + "</td><td>" +
      esc(run.report_id) + "</td><td>" + esc(run.drifted_resources) + "</td><td>" +
      severityBadge(run.highest_severity) + "</td><td>" + historyUnmanaged(run) + "</td></tr>").join("");
  }

  /* What the Active drifts table shows, and why it may be empty: a run in sync is not a filter miss. */
  function driftContext(summary, run, total, shown) {
    const history = (summary && summary.history) || [];
    const info = run ? history.find((h) => h.report_id === run) : null;
    const showing = run
      ? "Showing run " + run + (info ? " (" + formatTime(info.finished_at) + ", " + info.environment + ")" : "")
      : "Showing the latest run of each environment";
    let empty = null;
    if (!total) {
      empty = run
        ? "Run " + run + " found no drift" + (info && info.resources_total !== undefined
          ? ": all " + info.resources_total + " managed resource(s) were in sync." : ".")
        : "No drift in the latest run of each environment: all managed resources were in sync.";
    } else if (!shown) {
      empty = "No drift matches the filters (" + total + " drifted resource(s) hidden).";
    }
    return { showing: showing, empty: empty };
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
  function driftRows(drifts, indices, emptyText) {
    if (!drifts.length) {
      return '<tr><td colspan="8" class="empty">' + esc(emptyText || "No drift matches the filters.") + "</td></tr>";
    }
    return drifts.map((d, i) =>
      '<tr><td><span class="address">' + esc(d.address) + '</span><br><span class="rtype">' + esc(d.type) +
      "</span></td><td>" + esc(d.environment) + "</td><td>" + severityBadge(d.severity) + "</td><td>" +
      changeList(d) + "</td><td>" + operationTime(d) + "</td><td>" +
      callerField(d.caller_recorded_by_azure === undefined ? null : d.caller_recorded_by_azure) +
      "</td><td>" + issueField(d.issue) +
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
      "</dd><dt>GitHub issue</dt><dd>" + issueField(drift.issue) + "</dd><dt>Remediation PR</dt><dd>" +
      remediationPrField(drift.remediation_pr) + "</dd></dl><section><h3>Terraform diff</h3><pre class=\"hcl\">" + esc(hclDiff(drift)) + "</pre></section>" +
      "<section><h3>AI analysis</h3>" + (narrative.length
        ? "<ol class=\"narrative\">" + narrative.map((t) => "<li>" + esc(t) + "</li>").join("") + "</ol>"
        : '<p class="empty">No AI analysis for this resource.</p>') + "</section>" +
      "<section><h3>Remediation status</h3>" + remediationBlock(drift, remediations) + "</section>" +
      '<p class="hint">A recorded caller is the identity Azure logged for the operation; it is not proof of ' +
      "which person made the change.</p>";
  }

  const api = {
    esc, apiErrorCode, errorMessage, unmanagedPanel, filterHistory, driftContext, formatValue, formatTime, callerField, issueField, remediationPrField, issuesPanel, overviewCards, severityBreakdown, historyRows, filterOptions,
    filterDrifts, optionTags, runOptions, driftRows, hclDiff, detailModal, UNKNOWN_REASONS,
  };
  root.DashboardRender = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
