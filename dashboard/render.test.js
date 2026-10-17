/*
 * Component tests for dashboard/render.js (Task 13.2). Run: node --test dashboard/
 * (tests/test_dashboard_ui.py runs them under pytest). No dependencies, no network.
 */
"use strict";

const test = require("node:test");
const assert = require("node:assert/strict");
const R = require("./render.js");

const drift = (caller, extra) => Object.assign({
  report_id: "github-500-1", environment: "dev", address: 'module.network.azurerm_network_security_group.this["app"]',
  type: "azurerm_network_security_group", classification: "external_drift", severity: "LOW",
  changes: [{ property: "tags.env", expected: { status: "value", value: "dev" }, actual: { status: "value", value: "changed" } },
    { property: "tags.drift_test", expected: { status: "absent" }, actual: { status: "value", value: "primary-r2" } }],
  operation: { op_id: "op-1", operation_name: "Microsoft.Resources/tags/write", start: "2026-10-02T08:00:00.000000Z" },
  ai_analysis: { available: true, narrative: ["Terraform reports external_drift."] },
  remediation: { decision: "recommended", kind: "restore_declared", policy_rule: "R4", approval_required: true,
    automatic_apply: false, option_id: "x#1" },
  caller_recorded_by_azure: caller,
}, extra || {});

const caller = (value, type, status) => ({ label: "Caller recorded by Azure", value, caller_type: type, status });

test("caller field: human user name", () => {
  const html = R.callerField(caller("alice@example.com", "user", "matched"));
  assert.match(html, /data-caller-status="matched"/);
  assert.match(html, /alice@example.com/);
  assert.match(html, />User</);
});

test("caller field: service principal and managed identity identifiers", () => {
  const sp = R.callerField(caller("11111111-2222-4333-8444-555555555555", "service_principal", "matched"));
  assert.match(sp, /11111111-2222-4333-8444-555555555555/);
  assert.match(sp, /Service principal/);
  const mi = R.callerField(caller("66666666-7777-4888-9999-000000000000", "managed_identity", "matched"));
  assert.match(mi, /66666666-7777-4888-9999-000000000000/);
  assert.match(mi, /Managed identity/);
});

test("caller field: Unknown with its reason, never a guessed name", () => {
  for (const [status, reason] of Object.entries(R.UNKNOWN_REASONS)) {
    const html = R.callerField(caller("Unknown", "user", status));
    assert.match(html, />Unknown</, status);
    assert.ok(html.includes(R.esc(reason)), status);
    assert.match(html, new RegExp('data-caller-status="' + status + '"'));
  }
  // an "Unknown" value is never shown as a recorded caller, whatever the status says
  assert.match(R.callerField(caller("Unknown", "user", "matched")), /caller-unknown/);
});

test("caller field: no single identified change lists each operation's recorded caller (R3 shape)", () => {
  const op = (opId, start, value, status) => ({ op_id: opId, operation_name: "Microsoft.Resources/tags/write", start,
    end: start, role: "capable", value, caller_type: "user", status });
  const ambiguous = Object.assign(caller("Unknown", "unknown", "no_decisive_operation"), { operations: [
    op("op-1", "2026-10-11T02:27:00.310062Z", "first@example.com", "matched"),
    op("op-2", "2026-10-11T03:34:30.341314Z", "<b>second@example.com</b>", "matched")] });
  for (const html of [R.driftRows([drift(ambiguous, { operation: null })]), R.detailModal(drift(ambiguous, { operation: null }), [])]) {
    assert.match(html, /data-caller-status="no_decisive_operation"/);
    assert.match(html, /No single identified change; caller recorded for each operation/);
    assert.match(html, /data-op-id="op-1"[\s\S]*first@example\.com[\s\S]*>User</);
    assert.match(html, /data-op-id="op-2"[\s\S]*&lt;b&gt;second@example\.com&lt;\/b&gt;/);  // escaped
    assert.ok(!html.includes("<b>second"));
    assert.ok(html.includes("2026-10-11 02:27:00 UTC") && html.includes("2026-10-11 03:34:30 UTC"));
    assert.equal((html.match(/data-caller-status="matched"/g) || []).length, 2);
  }
  // an operation whose caller is genuinely unavailable stays Unknown with its reason
  const partial = Object.assign(caller("Unknown", "unknown", "no_decisive_operation"), { operations: [
    op("op-1", "2026-10-11T02:27:00.310062Z", "Unknown", "retention_exceeded")] });
  const html = R.callerField(partial);
  assert.match(html, /data-caller-status="retention_exceeded"[\s\S]*>Unknown</);
  assert.ok(html.includes(R.esc(R.UNKNOWN_REASONS.retention_exceeded)));
  // without operations the field stays the plain Unknown reason
  assert.match(R.callerField(caller("Unknown", "unknown", "no_decisive_operation")), /caller-unknown/);
});

test("caller field: hidden from users without caller_reader", () => {
  const html = R.callerField(null);
  assert.match(html, /Not available \(needs the caller_reader role\)/);
  assert.match(R.driftRows([drift(undefined)]), /caller_reader/);
});

test("drift row shows resource, property, expected and actual value, operation time and caller", () => {
  const html = R.driftRows([drift(caller("alice@example.com", "user", "matched"))]);
  assert.ok(html.includes(R.esc('module.network.azurerm_network_security_group.this["app"]')));
  assert.match(html, /tags\.env/);
  assert.ok(html.includes(R.esc('"dev"')) && html.includes(R.esc('"changed"')));
  assert.match(html, /\(absent\)/);
  assert.match(html, /2026-10-02 08:00:00 UTC/);
  assert.match(html, /Microsoft\.Resources\/tags\/write/);
  assert.match(html, /alice@example.com/);
  assert.match(html, /data-index="0"/);
  assert.match(R.driftRows([]), /No drift matches the filters/);
});

test("every value is escaped", () => {
  const evil = '<img src=x onerror="alert(1)">';
  const html = R.driftRows([drift(caller(evil, "user", "matched"), { address: evil, environment: evil,
    changes: [{ property: evil, expected: { status: "value", value: evil }, actual: { status: evil } }],
    ai_analysis: { narrative: [evil] } })]) + R.detailModal(drift(caller(evil, "user", "matched"),
    { address: evil, ai_analysis: { narrative: [evil] } }), []);
  assert.ok(!html.includes("<img"), "raw markup must never pass through");
  assert.match(html, /&lt;img/);
});

test("filters by severity, resource type and environment", () => {
  const rows = [drift(null), drift(null, { severity: "HIGH", type: "azurerm_resource_group" }),
    drift(null, { environment: "prod" })];
  assert.equal(R.filterDrifts(rows, { severity: "HIGH" }).length, 1);
  assert.equal(R.filterDrifts(rows, { type: "azurerm_network_security_group" }).length, 2);
  assert.equal(R.filterDrifts(rows, { environment: "prod" }).length, 1);
  assert.equal(R.filterDrifts(rows, { severity: "LOW", environment: "dev" }).length, 1);
  assert.equal(R.filterDrifts(rows, {}).length, 3);
  assert.deepEqual(R.filterOptions(rows), { severity: ["HIGH", "LOW"],
    type: ["azurerm_network_security_group", "azurerm_resource_group"], environment: ["dev", "prod"] });
  assert.match(R.optionTags(["dev"], "dev"), /<option value="dev" selected>/);
});

test("overview cards come from the summary and never invent a cost", () => {
  const summary = { overview: { total_resources: 5, active_drifts: 1, security_exposure: 0,
    monthly_cost_impact: { monthly_cost_delta: null, complete: false } },
    environments: [{ security_exposure: { ai_security_findings: 2 }, severity_counts: { INFO: 4, LOW: 1 } }] };
  const html = R.overviewCards(summary);
  for (const title of ["Total Resources", "Active Drifts", "Security Exposure", "Monthly Cost Impact"]) {
    assert.ok(html.includes(title), title);
  }
  assert.match(html, />5</);
  assert.match(html, /Not available/);
  assert.match(html, /2 AI security finding/);
  const priced = R.overviewCards({ overview: { monthly_cost_impact: { status: "estimated", monthly_cost_delta: "12.50",
    complete: true } } });
  assert.match(priced, /\$12\.50/);
  assert.match(R.overviewCards({ overview: { monthly_cost_impact: { status: "estimated", monthly_cost_delta: "-3.10",
    complete: false } } }), /-\$3\.10[\s\S]*incomplete/);
  const none = R.overviewCards({ overview: { monthly_cost_impact: { status: "no_drift_cost", monthly_cost_delta: null } } });
  assert.match(none, /No drift cost/);
  assert.ok(!none.includes("$0"), "no drift cost line is never shown as $0");
  assert.match(R.severityBreakdown(summary), /<progress class="sev-low" max="5" value="1">/);
});

test("detail modal: AI analysis, HCL diff and remediation status", () => {
  const remediations = [{ report_id: "github-500-1", address: drift(null).address, kind: "restore_declared",
    recommended: true, description: "Apply the reviewed plan.", approval: { status: "pending" },
    execution: { allowed: false, mode: "manual_after_approval" } }];
  const html = R.detailModal(drift(caller("Unknown", "user", "no_match")), remediations);
  assert.match(html, /Terraform reports external_drift\./);
  assert.match(html, /~ tags\.env\n    - &quot;dev&quot;\n    \+ &quot;changed&quot;/);
  assert.match(html, /restore_declared/);
  assert.match(html, /status-pending/);
  assert.match(html, /not allowed \(manual_after_approval\)/);
  assert.match(html, /Caller recorded by Azure/);
  assert.match(html, /not proof of/);
  assert.equal(R.hclDiff(drift(null)).split("\n")[0], '# module.network.azurerm_network_security_group.this["app"] (external_drift)');
});

test("run selector lists the history and keeps the selection", () => {
  const summary = { history: [{ report_id: "github-2-1", finished_at: "2026-10-11T04:23:49Z", environment: "dev",
    drifted_resources: 0 }, { report_id: "github-1-1", finished_at: "2026-10-11T02:36:54Z", environment: "dev",
    drifted_resources: 1 }] };
  const html = R.runOptions(summary, "github-1-1");
  assert.match(html, /<option value="">Latest per environment<\/option>/);
  assert.match(html, /<option value="github-1-1" selected>2026-10-11 02:36:54 UTC · dev · 1 drift\(s\)<\/option>/);
  assert.equal((html.match(/<option/g) || []).length, 3);
});

test("issue field: open, closed with resolution, none found and no snapshot", () => {
  const url = "https://github.com/owner/repo/issues/12";
  const open = R.issueField({ status: "open", number: 12, url, created_at: "2026-10-17T03:00:00Z" });
  assert.match(open, /data-issue-status="open"/);
  assert.match(open, /<a href="https:\/\/github\.com\/owner\/repo\/issues\/12" target="_blank" rel="noopener noreferrer">#12<\/a>/);
  assert.match(open, /since 2026-10-17 03:00:00 UTC/);
  const closed = R.issueField({ status: "closed", state_reason: "completed", number: 12, url,
    closed_at: "2026-10-17T04:00:00Z" });
  assert.match(closed, /closed · completed/);
  assert.match(closed, /2026-10-17 04:00:00 UTC/);
  assert.match(R.issueField({ status: "none_found" }), /No drift issue found/);
  assert.match(R.issueField({ status: "no_snapshot" }), /No issue data/);
  assert.match(R.issueField(undefined), /No issue data/);
  const spoofed = R.issueField({ status: "open", number: 1, url: "javascript:alert(1)", created_at: "x" });
  assert.ok(!spoofed.includes("href"), "only GitHub issue URLs become links");
});

test("remediation PR field never invents a PR", () => {
  const html = R.remediationPrField({ status: "not_enabled", reason: "Automated remediation pull requests are not enabled" });
  assert.match(html, /No remediation PR/);
  assert.match(html, /data-pr-status="not_enabled"/);
});

test("issues panel lists states with the snapshot time", () => {
  const summary = { issues: { snapshot: true, fetched_at: "2026-10-17T05:00:00Z", open: 1, closed: 1, items: [
    { number: 13, url: "https://github.com/o/r/issues/13", state: "open", state_reason: null,
      created_at: "2026-10-17T04:30:00Z", closed_at: null, environment: "dev", address: "a" },
    { number: 12, url: "https://github.com/o/r/issues/12", state: "closed", state_reason: "completed",
      created_at: "2026-10-16T04:30:00Z", closed_at: "2026-10-17T04:00:00Z", environment: null, address: null }] } };
  const html = R.issuesPanel(summary);
  assert.match(html, /1 open, 1 closed · snapshot 2026-10-17 05:00:00 UTC/);
  assert.match(html, /closed · completed/);
  assert.match(html, /\(not in any report\)/);
  assert.match(R.issuesPanel({ issues: { snapshot: false } }), /No GitHub issue snapshot/);
  assert.match(R.detailModal(Object.assign({ address: "a", report_id: "r", changes: [] },
    { issue: { status: "none_found" }, remediation_pr: { status: "not_enabled", reason: "x" } }), []),
    /GitHub issue[\s\S]*No drift issue found[\s\S]*Remediation PR[\s\S]*No remediation PR/);
});

test("API error codes: dashboard-api JSON errors pass through, a bare 404 means no API here", () => {
  assert.equal(R.apiErrorCode(401, { error: "unauthenticated" }), "unauthenticated");
  assert.equal(R.apiErrorCode(404, { error: "report_not_found" }), "report_not_found");  // real API 404s unchanged
  assert.equal(R.apiErrorCode(404, null), "api_not_found");  // e.g. the HTML 404 page of a static server
  assert.equal(R.apiErrorCode(404, { detail: "Not Found" }), "api_not_found");
  assert.equal(R.apiErrorCode(500, null), "http_500");
  const message = R.errorMessage("api_not_found", "http://127.0.0.1:5500");
  assert.match(message, /dashboard API was not found at http:\/\/127\.0\.0\.1:5500\/api\//);
  assert.match(message, /dashboard-api server \(by default 127\.0\.0\.1, port 8000\)/);
  assert.equal(R.errorMessage("data_unavailable", "x"), "Could not load data (data_unavailable).");
  assert.match(R.errorMessage("network_error", "http://h"), /could not be reached/);
});

test("unmanaged panel: resources, AI estimates, statuses and never invented amounts", () => {
  const run = { report_id: "github-1-1", environment: "dev", available: true, outcome: "complete", failure: null,
    collected_at: "2026-10-11T12:00:00.000000Z", counts: { unmanaged: 2, attached_to_managed: 1 },
    scopes: [{ resource_group: "aitdd-dev-main-rg", status: "complete", error: null }],
    cost: { status: "complete", totals: { display: "$17.11/month", complete: true } },  // format_usd output
    resources: [
      { name: "manual-vm", type: "Microsoft.Compute/virtualMachines", resource_group: "aitdd-dev-main-rg",
        location: "centralindia", category: "unmanaged", attached_to: null,
        estimate: { status: "estimated", reason: null, display: "$8.18/month" } },
      { name: null, type: "Microsoft.Compute/disks", resource_group: "aitdd-dev-main-rg", location: "centralindia",
        category: "attached_to_managed", attached_to: { kind: "managed", address: "azurerm_linux_virtual_machine.tf" },
        estimate: null }] };
  const html = R.unmanagedPanel({ runs: [run] });
  assert.match(html, /2 not managed by Terraform · 1 attached to a managed resource/);
  assert.match(html, /Estimated monthly cost: <strong>\$17\.11\/month<\/strong>/);
  assert.match(html, /Unmanaged resources are not drift/);
  assert.match(html, /manual-vm/);
  assert.match(html, /\$8\.18\/month/);
  assert.ok(!html.includes("/month/month"), "the display already carries /month");
  assert.match(html, /\(name withheld\)/);
  assert.match(html, /Attached to a managed resource/);
  assert.match(html, /no estimate/);
  const mismatch = R.unmanagedPanel({ runs: [Object.assign({}, run, { cost: { status: "inventory_mismatch", totals: null },
    resources: [Object.assign({}, run.resources[0], { estimate: null })] })] });
  assert.match(mismatch, /no estimate<\/strong> — the AI report priced a different inventory: no amounts/);
  assert.ok(!mismatch.includes("$8.18"));
  assert.match(R.unmanagedPanel({ runs: [{ report_id: "r", environment: "dev", available: false }] }),
    /No unmanaged-resource inventory for this run/);
  const failed = R.unmanagedPanel({ runs: [Object.assign({}, run, { outcome: "failed", failure: "listing_failed",
    scopes: [{ resource_group: "aitdd-dev-main-rg", status: "failed", error: "authorization_failed" }] })] });
  assert.match(failed, /Not fully listed: aitdd-dev-main-rg \(failed, authorization_failed\)/);
  assert.ok(!R.unmanagedPanel({ runs: [Object.assign({}, run, { resources: [Object.assign({}, run.resources[0],
    { name: "<script>x</script>" })] })] }).includes("<script>"));
});

test("run history search: run id, GitHub run number, date, environment, severity", () => {
  const history = [
    { report_id: "github-38862516764-1", finished_at: "2026-10-16T06:41:00Z", environment: "dev", drifted_resources: 0, highest_severity: "INFO" },
    { report_id: "github-38105671846-1", finished_at: "2026-10-11T02:36:54Z", environment: "dev", drifted_resources: 1, highest_severity: "LOW" },
    { report_id: "github-38000000000-2", finished_at: "2026-10-10T01:00:00Z", environment: "prod", drifted_resources: 2, highest_severity: "HIGH" }];
  const ids = (q) => R.filterHistory(history, q).map((r) => r.report_id);
  assert.deepEqual(ids(""), history.map((r) => r.report_id));
  assert.deepEqual(ids("38105671846"), ["github-38105671846-1"]);          // the GitHub run number
  assert.deepEqual(ids("GITHUB-38862516764-1"), ["github-38862516764-1"]); // case-insensitive full id
  assert.deepEqual(ids("2026-10-11"), ["github-38105671846-1"]);           // date
  assert.deepEqual(ids("prod high"), ["github-38000000000-2"]);            // every word must match
  assert.deepEqual(ids("low"), ["github-38105671846-1"]);
  assert.deepEqual(ids("nothing-like-this"), []);
  const summary = { history };
  assert.equal((R.historyRows(summary, "38105671846").match(/data-run=/g) || []).length, 1);
  assert.match(R.historyRows(summary, "zzz"), /No run matches the search/);
  assert.match(R.historyRows({ history: [] }, ""), /No runs found/);
  assert.ok(!R.historyRows(summary, "<img src=x>").includes("<img"));
});

test("run history rows open a run and show unmanaged resources with cost", () => {
  const summary = { history: [
    { report_id: "github-38140497702-1", finished_at: "2026-10-11T12:46:27Z", environment: "dev", drifted_resources: 0,
      resources_total: 5, highest_severity: "INFO", unmanaged: { available: true, unmanaged: 5, display: "$44.85/month" } },
    { report_id: "github-38105671846-1", finished_at: "2026-10-11T02:36:54Z", environment: "dev", drifted_resources: 1,
      resources_total: 5, highest_severity: "LOW", unmanaged: { available: false } }] };
  const html = R.historyRows(summary, "", "github-38105671846-1");
  assert.match(html, /<tr class="run-row" tabindex="0" data-run="github-38140497702-1"/);
  assert.match(html, /<tr class="run-row selected" tabindex="0" data-run="github-38105671846-1" aria-current="true"/);
  assert.match(html, /5 · \$44\.85\/month/);
  assert.match(html, /<span class="empty">—<\/span>/);  // no inventory: never "0"
  assert.equal((html.match(/data-run=/g) || []).length, 2);
});

test("Active drifts says why it is empty: an in-sync run is not a filter miss", () => {
  const summary = { history: [{ report_id: "github-38140497702-1", finished_at: "2026-10-11T12:46:27Z",
    environment: "dev", drifted_resources: 0, resources_total: 5 }] };
  const inSync = R.driftContext(summary, "github-38140497702-1", 0, 0);
  assert.equal(inSync.showing, "Showing run github-38140497702-1 (2026-10-11 12:46:27 UTC, dev)");
  assert.equal(inSync.empty, "Run github-38140497702-1 found no drift: all 5 managed resource(s) were in sync.");
  assert.match(R.driftContext(summary, "", 0, 0).empty, /latest run of each environment: all managed resources were in sync/);
  assert.equal(R.driftContext(summary, "", 0, 0).showing, "Showing the latest run of each environment");
  assert.equal(R.driftContext(summary, "github-1-1", 2, 0).empty, "No drift matches the filters (2 drifted resource(s) hidden).");
  assert.equal(R.driftContext(summary, "github-1-1", 2, 1).empty, null);
  assert.match(R.driftRows([], [], inSync.empty), /found no drift: all 5 managed resource\(s\) were in sync/);
  assert.ok(!R.driftRows([], [], "<b>x</b>").includes("<b>"));
});
