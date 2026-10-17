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
  const priced = R.overviewCards({ overview: { monthly_cost_impact: { monthly_cost_delta: "12.50", complete: true } } });
  assert.match(priced, /\$12\.50/);
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
