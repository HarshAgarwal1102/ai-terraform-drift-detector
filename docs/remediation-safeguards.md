# Remediation Safeguards — Human-Approved Remediation (Phase 11)

> **Status**: Task 11.1 specification, **revision 9, under review** (2026-10-12).
> **Phase 11 is on hold** (user decision 2026-10-13): this specification is paused under review,
> nothing in it is implemented, and `apply_enabled` stays `false`. It is published as part of the
> Level 1 documentation closeout (2026-10-18) as a design record only; the Level 1 baseline
> (`level1-v1.0.0`) contains no remediation workflow, approval environment or write permission.
> - Revision 1 review: D1, D3, D5, D6 and D8 approved; D2, D4 and D7 sent back.
> - Revision 2 review: C1 approved (no create in v1); D2 approved as a proposal, not as validated
>   Azure permissions; D4 sent back; D7 approved provisionally.
> - Revision 3 review: U1 (GnuPG), U4 (reviewer keys), U5 (auth-test runs) and U6 (Activity Log
>   evidence) approved conditionally; U2 (repository-secret HMAC key) and U3 (NSG
>   `security_rule` in the allowlist) not approved; the D4 binding sent back to separate the
>   Environment approval from the statement attestation.
> - Revision 4 review: R1 changed (recovery copy of the apply-job key), R2 deferred (hardware
>   token optional), R3 approved, R4 approved conditionally; five security corrections required:
>   the key/seal threat model traced from the actual cryptographic flow (§9.5–9.6), `apply_enabled`
>   kept false, the `terraform-auth-test.yml` full-plan logging made an enablement prerequisite
>   (E6), the A/B binding rechecked value by value (§8.5), and the tags-only eligibility hardened
>   against unrelated and apply-time-unknown changes (§7.2).
> - Revision 5 review (2026-10-12): R5 approved conditionally (no standing write roles;
>   just-in-time roles granted by the user, never by the workflow, only after review and both
>   approvals, immediately before apply; apply disabled until implemented and verified); R6
>   approved conditionally (verify the Environment protection configuration or fail closed); R7
>   changed (no blind deletion: determine the exposure of existing auth-test logs, preserve
>   evidence, restrict or delete where appropriate, document what cannot be removed).
> - Revision 6 review (2026-10-12): R8 approved (the local grant script verifies the Environment
>   settings itself and refuses otherwise), R9 approved (15-minute propagation timeout and
>   45-minute role lifetime as hard limits; cleanup, interruption, disconnection and removal
>   failure documented), R10 approved (per-run deletion only after local classification and a
>   private evidence copy). Strengthening required: the grant script and its trusted inputs as part
>   of the security boundary (§10.9); interruption and disconnection handling that never permits an
>   apply after a failed verification (§10.10); real-plan validation of the tag-only eligibility per
>   address (E9); verification of the auth-test fix including audit records (E6); a recheck of the
>   A, B and grant binding (§8.5, §9.5); and a statement of which checks need real execution
>   (§15.4).
> - Revision 7 review (2026-10-12): R11 decided (Azure-enforced expiry preferred; the local cleanup
>   is not an expiry; a stronger, verified fallback or apply stays disabled), R12 approved.
> - Revision 8 review (2026-10-12): R13 **not approved yet**. PIM time-bound assignments stay
>   preferred; the user verifies tenant licensing and configuration first. The Azure-side watchdog
>   is only a separate design for review (§10.11), not to be implemented or provisioned, and it is
>   not a strict 45-minute expiry. (Revision 8 had left this header at "revision 7"; corrected
>   here.)
>
> Nothing in this document is implemented. No remediation workflow, GitHub Environment, secret,
> key, Azure identity, role definition, role assignment or federated credential exists for it.
> **`apply_enabled` is `false`** and stays false until the enablement gate in
> [§10.8](#108-apply-enablement-gate) is passed and the user approves enabling apply. Open
> decisions and unverified assumptions are listed in [§15](#15-decisions-open-items-and-assumptions).
>
> **Authority**: [`PROJECT_PLAN.md`](../PROJECT_PLAN.md) (Phase 11, Execution Rules 4, 10, 12–14
> and the Core Project Principles) wins over this document. Drift semantics are defined in
> [`drift-detection-spec.md`](drift-detection-spec.md); access design in
> [`architecture.md`](architecture.md).

---

## 1. Purpose and scope

This specification defines how a change to Azure infrastructure or Terraform state can be
made **after** drift is detected, so that:

- nothing is applied without **two** independent checks by an authorised reviewer: GitHub's
  Environment deployment approval and a signed attestation of the exact approval statement,
  both bound to one run, one commit, one exact plan and one toolchain;
- the reviewer inspects the **exact** proposed change, without any value becoming public;
- what is applied is exactly what was approved, on a fresh plan, and never an old plan;
- detection stays read-only, is never cancelled by remediation and can never turn into an apply;
- the remediation identity cannot change or delete anything Terraform does not manage;
- every remediation leaves evidence without publishing values or identities.

Scope: the `dev` environment (`terraform/environments/dev`, state blob `dev.tfstate`). The
bootstrap module (`terraform/bootstrap`) and the state storage are **out of scope** and are never
applied from CI.

## 2. Baseline today (verified 2026-10-11)

These facts are the starting point; this specification keeps every one of them.

| Area | Current state |
|---|---|
| Workflows | `drift-detection.yml` (schedule + manual), `ai-analysis.yml` (`workflow_run`), `security-scan.yml` and `terraform-auth-test.yml` (push / PR / manual). None runs `terraform apply`; `drift-detection.yml` states "this workflow must never run `terraform apply`". |
| State users | `drift-detection.yml` (`scripts/generate_plan_json.sh`, `-lock-timeout=120s`) and `terraform-auth-test.yml` (`terraform -chdir=terraform/environments/dev init` with the same `azurerm` backend, key `dev.tfstate`, then `terraform plan -var-file=dev.tfvars -input=false -no-color` **without** `-lock-timeout`, so it fails at once on a held lock) both plan against `dev.tfstate`, verified from the workflow files. **The auth-test plan prints Terraform's full human-readable plan to the public job log**, including non-sensitive attribute values of every planned change (Terraform shows sensitive values only as `(sensitive value)`); this is a confirmed exposure and an apply-enablement prerequisite (E6, [§10.8](#108-apply-enablement-gate)). Existing logs (public API, 2026-10-12): 67 auth-test runs from 2026-10-01 to 2026-10-11, of which 63 successful pushes printed a plan; the workflow uploads no artifacts; unauthenticated log download is refused (HTTP 403), but any signed-in GitHub user can read logs of this public repository; all are within GitHub's 90-day log retention ([§12.1](#121-existing-auth-test-logs-r7)). Auth-test runs on push to `main`/`master`, on pull requests (which fail at Azure login, `AADSTS700213`) and on manual dispatch. |
| Concurrency | `drift-detection.yml`: group `drift-detection-<environment>`, `cancel-in-progress: false`. `terraform-auth-test.yml`: none. |
| CI identity | One Entra ID app, `aitdd-github-oidc`: **Reader** (subscription) and **Storage Blob Data Contributor** (`tfstate` container). Write actions such as `resourceGroups/write` and `listkeys` are denied ([architecture §4](architecture.md#azure-rbac-permissions-github-oidc-identity)). |
| OIDC trust | One federated credential, subject `…:ref:refs/heads/main`. No job uses `environment:`; a job that did would get an `…:environment:<name>` subject that this credential does not accept. |
| Runner images | Every workflow uses `ubuntu-latest`. GitHub announced (run annotations, 2026-10-11) that `ubuntu-latest` moves to Ubuntu 26 from 2026-10-19, which changes tool versions such as GnuPG. |
| Managed resources (dev) | `module.resource_group.azurerm_resource_group.this["main"]`, `module.network["main"].azurerm_virtual_network.this`, `…azurerm_network_security_group.this["app"]` (inline `security_rule = []`, so Terraform owns the rule set), `…azurerm_subnet.this["app"]`, `…azurerm_subnet_network_security_group_association.this["app"]`. No data sources. AzureRM `~> 5.0`, `resource_provider_registrations` defaulting to `"none"`. |
| Plan contract | `scripts/generate_plan_json.sh`: refresh on, lock on (`-lock-timeout=120s`), `-detailed-exitcode`, `TF_CLI_ARGS*` refused; `-refresh=false`, `-target`, `-lock=false` and `-var` forbidden ([spec §4](drift-detection-spec.md#4-terraform-command--exit-code-contract)). |
| Remediation options | The AI report lists deterministic options (Task 6.6) and a recommendation (Phase 9B policy v1). Every recommendation carries `approval.required = true`, `execution.allowed = false`, `automatic_apply = false`. Mutating command templates exist only as text; no workflow runs them. |
| Secret scanning | `security-scan.yml` runs TruffleHog on the full Git history on every push and PR; every result blocks (Task 9.3). |
| Issues and PRs | Drift issues are opened and closed only by deterministic evidence (Tasks 8.1, 8.3). Task 8.2 (remediation PRs) was superseded (R1). No workflow has `contents: write` or `pull-requests: write`. |
| Guards | RBAC (no write role) is the hard guard. A structural test guards forbidden commands only for the Task 10.4 inventory scope; there is **no repository-wide test** that keeps `terraform apply` out of the detection workflows yet (closed by AC-3.1). |

## 3. Detect, propose, apply

| Stage | What happens | Who acts | Azure / state access | Output |
|---|---|---|---|---|
| **Detect** | Refreshed `terraform plan`, deterministic classification, investigation, cost, unmanaged inventory | Scheduled or manually dispatched `drift-detection.yml` | Read-only (Reader; state lock only) | Drift report, issues, artifacts |
| **Propose** | Deterministic remediation options and a recommendation in the AI report; a human decides the direction | `ai-analysis.yml` (options only); the human (decision) | None | AI report; the human's decision. A PR only for the accept direction, authored by a human |
| **Apply** | A plan, an encrypted review bundle and an approval statement; the reviewer's Environment approval and signed attestation; pre-apply checks; a fresh plan that must match; `terraform apply` of that fresh saved plan | The human dispatches, reviews, approves and attests; the remediation workflow executes | Write, only in the approved job, through a separate, resource-scoped identity, only after the enablement gate | Applied change and a remediation record |

A recommendation is advice. It never selects, schedules or authorises an apply.

## 4. Safety invariants

Each invariant is normative for Tasks 11.2 and 11.3 and is backed by an acceptance criterion
([§16](#16-acceptance-criteria)).

1. **No apply without both approvals.** Every `terraform apply` runs only after (A) a GitHub
   Environment deployment approval and (B) a valid signed attestation of the approval statement,
   by the same authorised reviewer, for the same run and attempt ([§8.5](#85-two-approvals-environment-approval-and-statement-attestation)).
   Neither substitutes for the other; there is no standing, cached or implicit approval.
2. **No apply from detection.** `drift-detection.yml`, `ai-analysis.yml`, `security-scan.yml` and
   `terraform-auth-test.yml` never run `terraform apply`, `import`, `state` subcommands that write
   (`rm`, `mv`, `push`, `replace-provider`), `force-unlock` or `taint`, and never hold a
   write-capable Azure identity.
3. **Only the remediation workflow applies**, and only through `workflow_dispatch` on `main`.
   It is never triggered by `push`, `pull_request`, `pull_request_target`, `workflow_run`,
   `schedule`, `repository_dispatch`, a merge, an issue event or another workflow.
4. **A merge applies nothing.** Any infrastructure change after a merge needs its own dispatch,
   plan, review and approvals.
5. **No automatic merge or bot PRs.** No workflow creates, approves or merges PRs; repository
   auto-merge stays disabled; "Allow GitHub Actions to create and approve pull requests" stays off.
6. **Never an old or different plan.** The apply job applies only the saved plan it created itself
   after both approvals and the pre-apply checks, and only if eligibility and the fingerprint,
   recomputed from that fresh plan, equal the approved statement.
7. **Approved revision only.** The applied configuration is exactly the approved commit, and that
   commit is the current `main` HEAD at the last check before apply.
8. **Unmanaged resources are out of reach** of the remediation identity, including unmanaged
   resources of a managed type and unmanaged children of a managed parent ([§10](#10-azure-permissions-d2-proposal)).
   **No standing write roles** (R5): the identity holds read roles only; write roles exist only
   during one approved apply, granted and removed by the user ([§10.9](#109-just-in-time-write-roles-r5)).
9. **The same plan contract as detection.** Refresh on, lock on, no `-target`, `-replace`,
   `-refresh=false`, `-lock=false`, `-var` or `TF_CLI_ARGS*`; whole-configuration plans only.
10. **Metadata-only updates in v1.** A plan is eligible only if every change is an `update` of an
    existing managed resource whose **actual planned attribute changes** are limited to its
    allowlisted tag paths ([§7](#7-eligible-changes-c1-u3)). NSG `security_rule` changes need a
    separate security review before they can ever be allowed ([§7.4](#74-security-rule-changes-separate-security-review)).
11. **Apply is disabled until enabled.** `apply_enabled: false` until every enablement-gate item
    (E1–E11), including the auth-test log fix (E6), the just-in-time role procedure (E7), real-plan validation of the eligibility (E9) and an Azure-side role expiry control (E10), is
    verified, recorded and approved by the user
    ([§10.8](#108-apply-enablement-gate)).
12. **Detection is never cancelled or held** by remediation ([§11.2](#112-concurrency-d7-provisional)).
13. **Fail closed.** Any missing, mismatched, expired or unauthorised approval or attestation, and
    any unexpected input, plan shape, fingerprint, stale revision, conflicting run, lock conflict
    or tool error stops the run before apply. A stop is never retried automatically.
14. **No LLM in remediation.** No model output selects, edits, approves or executes anything.
15. **No public values; no confidentiality by hash.** No attribute value, HCL with values,
    plaintext plan, raw Terraform output, Azure resource ID or Azure caller identity is
    published. Confidentiality never depends on a hash or fingerprint ([§9.5](#95-key-and-seal-flow-traced),
    [§9.6](#96-compromise-analysis)).
16. **No private key in GitHub.** No reviewer private key ever enters GitHub, the repository,
    artifacts or logs ([§8.7](#87-reviewer-key-custody-u4-conditional)).
17. **No repository writes (D8).** The remediation workflow writes no issue, comment, label,
    branch, commit, PR, release or repository setting; its evidence is the run summary and
    artifacts.
18. **Issues close only on evidence** (Task 8.3), never through remediation.
19. **The workflow never changes permissions.** No job holds or uses any
    `Microsoft.Authorization/*` write action, and no workflow contains a role-assignment,
    role-definition or federated-credential command; only the user, with their own Azure
    credentials, grants or removes roles (§10.9).

## 5. Remediation directions

The direction is always a human choice (Task 6.6: `plan_default` is not a recommendation).

| Direction | Option kinds | Code change | v1 apply | Notes |
|---|---|---|---|---|
| **Revert** (restore the declared configuration) | `restore_declared`, `apply_pending_change` | None | Mode `plan`, if every change is an eligible metadata update | Applies the **whole** pending plan of `main`; one ineligible change makes the run ineligible |
| **Recreate / create** | `recreate_deleted_object`, `create_declared_object` | None | **Refused** (C1) | Manual, separately approved local work |
| **Accept** (keep the Azure value) | `accept_remote_value`, `keep_current_value` | A **human-authored** PR | Usually none; recording the accepted value in state is a `refresh_only` run, eligible only for allowlisted tag paths | Accept rules below |
| **Refresh state** | `refresh_state_only` | None | Mode `refresh_only`, same eligibility | State only, still approval-gated |
| **Stop managing** | `stop_managing_without_destroy` | Human-authored PR | **Refused** | Manual, separately approved `state rm` |
| **Investigate / no change** | `investigate`, `no_infrastructure_change` | None | None | Read-only `plan_review` only |
| **Destructive** | `replace_object`, `delete_undeclared_object` | — | **Refused** | Policy R2 already withholds a recommendation |
| **Security rule restore** | `restore_declared` on an NSG rule set | None | **Refused in v1** (U3) | Needs the §7.4 security review first |

**Accept rules** (Task 8.2 findings F2–F4): a human writes the PR with `Refs #<issue>` and no
closing keyword; no tool generates the HCL edit; committing a real Azure value publishes it
permanently, so personal, credential or security-relevant values need a separate review; merging
applies nothing.

Unmanaged resources (Task 10.4) are not remediated by this workflow and are out of the
remediation identity's reach (invariant 8).

## 6. Remediation workflow (D1, approved)

`.github/workflows/remediation-apply.yml` (name reserved; not created by Task 11.1). One run:
**plan → review → Environment approval + attestation → pre-apply checks → fresh plan →
eligibility and fingerprint verification → apply.**

### 6.1 Trigger, runner, inputs and permissions

- `workflow_dispatch` only; the run must be on `refs/heads/main`.
- `runs-on: ubuntu-24.04` (pinned, not `ubuntu-latest`), so the GnuPG and tool versions do not
  change silently with the image migration (§2, §8.2).
- Permissions: `contents: read`, `actions: read` (artifacts, run list and review history);
  `id-token: write` only on the two jobs that log in to Azure. No other permission.

| Input | Values | Rule |
|---|---|---|
| `environment` | `dev` | Choice; selects `terraform/environments/dev` |
| `mode` | `plan`, `refresh_only` | Terraform operation |
| `decision` | `revert`, `accept`, `refresh` | Recorded intent; consistent with `mode` (`revert` → `plan`; `refresh` → `refresh_only`; `accept` → either) |
| `reviewed_commit` | 40-hex SHA | Must equal `github.sha` and the current `main` HEAD |
| `drift_issue` | issue number, optional | Recorded as `Refs #n`; never closed or commented on (D8) |
| `jit_rehearsal` | `false` (default) or `true` | Accepted only while `apply_enabled` is false (otherwise `invalid_input`); lets the run go through the just-in-time window P12–P13 for verification (E4, E7) and still stop before apply |

Inputs are validated against these patterns before any other step; anything else stops the run.

### 6.2 Keys and secrets (U2 reworked, U4)

| Item | Where | Who can use it | Purpose |
|---|---|---|---|
| Reviewer OpenPGP **public** key (signing and encryption) | Committed, with its fingerprint pinned in the committed reviewer allowlist | Anyone (public by nature) | Encrypting the review bundle and the per-run key to the reviewer; verifying attestations |
| Reviewer **private** key | Only the reviewer's own key store (§8.7) | The reviewer | Decrypting the bundle; signing attestations. **Never in GitHub** |
| Apply-job OpenPGP **public** key (encryption only) | Committed, fingerprint pinned | Anyone | Sealing the per-run key for the `apply` job |
| Apply-job **private** key | **Environment secret** of `dev-remediation` only | Only jobs that reference `dev-remediation`, and only after its protection rules (required reviewer, `main` only) have passed | Opening the seal in the `apply` job |
| Per-run fingerprint key `K_run` | Generated in the `plan` job; leaves it only encrypted (in the bundle for the reviewer, in the seal for the `apply` job) | That run's `plan` job, the reviewer, that run's `apply` job | Keyed fingerprint `F` (§9) |
| Remediation identity client ID | Environment value of `dev-remediation` | Jobs in `dev-remediation` | Azure login in the `apply` job |

There is **no repository secret** in this design: every long-lived secret sits behind the
`dev-remediation` approval boundary, and the per-run key exists only for one run.

### 6.3 Jobs

1. **`plan`** (no `environment:`, the existing read-only identity, no secret):
   1. Inputs, revision, no other active remediation run (P3–P4), and no write role assignment
      held by the remediation identity (leftover check, §10.9; `write_roles_present`).
   2. GnuPG version check (§8.2); `terraform init` and the plan contract for `mode`; `-out` to a
      runner-local file; `terraform show -json` and `terraform show -no-color` on the runner.
   3. Eligibility (§7). Plan exit 0: `nothing_to_apply`; the run ends successfully; no review.
   4. `K_run` (32 random bytes); `F_plan` = HMAC-SHA256(`K_run`, fingerprint document) (§9).
   5. **Review bundle** encrypted to the reviewer key; **seal** (`K_run`) encrypted to the
      apply-job key; both uploaded (§8.2). Plaintext never leaves the runner; `K_run` is wiped
      from the runner's files before the job ends.
   6. **Approval statement** (§8.4) with both artifact digests, uploaded as
      `remediation-statement-<run_id>` and shown in the step summary with `S` = SHA-256 of its
      canonical form, together with the structural summary.
2. **`apply`** (`needs: plan`, `environment: dev-remediation`, the remediation identity, which
   holds **read roles only** at this point): GitHub holds the job until the Environment approval
   (A); then the checks P0–P11 (§11.3, including (B), the fresh plan and the fingerprint); then
   the **just-in-time window** P12: the job announces that it is ready and waits, bounded, until
   the user's local procedure has granted exactly the needed write roles and the job has verified
   its own effective permissions (§10.9); then P13: the final rechecks and a **new** fresh plan
   whose eligibility and fingerprint must still match; then P14: `terraform apply` of that P13
   plan file. Afterwards a read-only post-apply plan (`applied_clean` or `post_apply_not_clean`)
   and the remediation record (§13). The job ends either way; the user's procedure then removes
   the roles and confirms the removal.

### 6.4 Status and failure codes

Every run ends with exactly one code: `applied_clean`, `nothing_to_apply`, `invalid_input`,
`apply_disabled`, `revision_not_main_head`, `remediation_already_active`, `tool_version_mismatch`,
`plan_failed`, `plan_refused_action`, `update_not_allowlisted`, `unmanaged_child_present`,
`review_bundle_failed`, `approval_rejected`, `approval_expired`, `environment_approval_invalid`,
`attestation_missing`, `attestation_invalid`, `statement_mismatch`, `seal_invalid`,
`approval_stale`, `detection_active_timeout`, `state_locked`, `plan_changed_since_approval`,
`stale_plan`, `apply_failed`, `cancelled_during_apply`, `post_apply_not_clean`,
`environment_config_invalid`, `environment_config_unverified`, `write_roles_present`,
`jit_grant_timeout`, `jit_permissions_unexpected`, `jit_grant_not_confirmed`,
`jit_window_exceeded`, `detection_active`, `plan_format_unsupported`, `address_not_validated`.

## 7. Eligible changes (C1, U3)

### 7.1 Action rule

Mode `plan`:

- every `resource_changes` entry has `mode` = `managed` and `change.actions` exactly `["no-op"]`
  or `["update"]` (data-source `read` entries are refused: `dev` has none, so one would be
  unexpected);
- no entry has `action_reason`, `importing`, `previous_address`, `deposed`, `generated_config` or
  a non-empty `replace_paths`; `before_identity` and `after_identity`, if present, are equal;
- every entry and every `change` object contains only keys known to the pinned plan format;
  `format_version` is in the committed allowed set (initially `1.2`). An unknown key or format
  version stops the run with `plan_format_unsupported`, so a newer Terraform cannot add a field
  that is silently ignored;
- `output_changes` is empty or every entry is `no-op`.

Mode `refresh_only`: `resource_changes` is empty or all `no-op`, and every `resource_drift` entry
has `change.actions` exactly `["update"]` (a refresh that drops a deleted resource from state is a
`delete` and is refused).

Anything else stops the run with `plan_refused_action`.

### 7.2 Attribute rule: actual planned changes, not action types

An action type says nothing about **what** changes, so every eligible entry is checked path by
path, with exact JSON comparison (type-aware: `"1"` and `1` differ, `null` and absent differ,
lists compare by position and length; no normalisation):

1. **Which entries**: every `update` in `resource_changes` (the change Terraform makes in Azure)
   **and every entry in `resource_drift`, in both modes**. In mode `plan`, `terraform apply` also
   writes the refreshed values of every resource into state; drift outside the allowlist would
   otherwise be recorded in state silently.
2. **Changed paths**: every leaf path where `before` and `after` differ, including keys added or
   removed at any depth; for a `null` or absent side, every leaf of the other side counts.
3. **Apply-time unknowns are refused anywhere**: any `true` anywhere in `after_unknown` (not only
   under allowed paths) gives `update_not_allowlisted`. Nothing that is unknown until apply can be
   admitted, because neither the reviewer nor the fingerprint can see its value.
4. **Sensitivity changes are refused**: any difference between `before_sensitive` and
   `after_sensitive`, or any `true` under an allowed path in either of them (an empty marker such
   as `{"tags": {}}` means "not sensitive").
5. **Allowed paths only**: every changed path must be under an allowed path of the entry's address
   (§7.3). Any other changed path, on any entry, gives `update_not_allowlisted`; an entry whose
   address has no allowed paths may only be unchanged.
6. **Tag values**: under `tags`, `before` and `after` must each be an object (or `null`) whose
   values are strings; keys must not use Azure's reserved tag prefixes (`microsoft`, `azure`,
   `windows`, case-insensitive) or the special prefixes `hidden-` and `link:`.
7. **Result**: the per-address set of changed paths (paths only, no values) is the eligibility
   result. It is shown in the structural summary, bound in the statement and recomputed in P8.

The check runs in the `plan` job (before the bundle exists) and again on the fresh plan in the
`apply` job (P8), with the same `drift_engine` code from the approved commit. Unit tests use
real-shaped AzureRM 5.x plan JSON for each allowed and refused case (AC-3.5).

A run can therefore be refused because of drift that Terraform would merely record (for example
provider-computed attributes, Task 5A.1). That is intended: such runs are handled outside v1.

### 7.3 Initial allowlist: tags only (U3), enabled per address only after real-plan validation

| Address | Allowed paths | Not allowed | Real-plan validation (E9) |
|---|---|---|---|
| `module.resource_group.azurerm_resource_group.this["main"]` | `tags`, `tags.<key>` | Everything else | **Preliminary only**: the committed real fixture `tests/fixtures/plan_evidence/external_drift` (Terraform 1.14.7, plan format 1.2, a real tag drift on this resource, sanitised, recorded 2026-10-01 before the current provider lock of 2026-10-02) shows, under the §7.1–7.2 rules applied by hand: the only changed path in both `resource_changes` and `resource_drift` is `tags.<key>`; no `true` in `after_unknown`; `before_sensitive` = `after_sensitive` = `{"tags": {}}`; `before_identity` = `after_identity`; only known keys. Not yet validated with the actual validator on a fresh plan with the pinned AzureRM 5.7.0 |
| `module.network["main"].azurerm_virtual_network.this` | `tags`, `tags.<key>` | Everything else, including `address_space` and the computed `subnet` set | **None**: no real tag-drift plan exists for this resource |
| `module.network["main"].azurerm_network_security_group.this["app"]` | `tags`, `tags.<key>` | Everything else, **including `security_rule`** | **None**: no real tag-drift plan exists for this resource |
| `module.network["main"].azurerm_subnet.this["app"]` | none | — | — |
| `module.network["main"].azurerm_subnet_network_security_group_association.this["app"]` | none | — | — |

Each allowlist entry carries an `enabled` flag in the committed allowlist, `false` for all three
entries until E9 has validated that address (§10.8). A change to an address whose entry is not
enabled stops the run with `address_not_validated`. If real plan evidence for an address is not
available, its entry stays disabled; with no enabled entry, no tag remediation is possible.

An address not listed is not eligible. Extending the allowlist is a reviewed change, together with
the permission proposal (§10.3) and new enablement evidence (§10.8), approved by the user.

### 7.4 Security-rule changes: separate security review

NSG `security_rule` changes (restoring the declared empty rule set after an out-of-band rule, the
most important security case) stay **refused** until a separate, recorded security review
approves them. That review must at least cover:

- a rule-level presentation in the review bundle (each added, removed or changed rule with
  direction, access, priority, protocol, ports and prefixes) and how the reviewer checks it;
- rule-specific eligibility checks (for example: v1 of that feature only removes rules, never
  adds or widens one);
- the provider's write path for the NSG (whole-object `PUT`), the race in which a rule added after
  the fresh plan is removed by the apply, and how that is detected afterwards;
- the effect on any traffic and on Azure-managed or platform rules;
- its own enablement evidence (E1 for the NSG rule operations) and its own real test;
- the D5 multi-reviewer question for security changes.

Until then, a drift that includes an NSG rule change is remediated manually, outside this
workflow, with the user's own reviewed local apply.

## 8. Review and approval (D4, D5, U1, U4)

### 8.1 Environment `dev-remediation`

Configured in Task 11.2 (a GitHub setting that needs user approval, Execution Rule 13).

| Setting | Requirement |
|---|---|
| Required reviewers | The repository owner (single maintainer) |
| Prevent self-review | **Off** for now (D5, §8.6) |
| Deployment branches | `main` only |
| Wait timer | None |
| Environment secrets and values | Only the apply-job private key and the remediation identity's client ID |
| Administrator bypass | **Off** ("Allow administrators to bypass configured protection rules" disabled). The `apply` job reads the configuration at P0 and fails closed if it differs or cannot be read (R6). If a bypass still happens, the attestation check (B) still applies and the record shows a security event |

### 8.2 Encrypted review bundle and seal (U1: GnuPG, conditional)

**Tool and version.** GnuPG from the pinned `ubuntu-24.04` runner image. The `plan` job requires
`gpg --version` to report a version in the committed allowed set (initially 2.4.x, minimum
2.4.4, to be confirmed against the image in Task 11.3) and records the exact version in the
statement; otherwise `tool_version_mismatch`. The binary is trusted as part of the runner image,
like `bash` and `python3`; it is not downloaded. The reviewer uses GnuPG 2.4 or later locally.

**Isolation.** Every `gpg` call uses a fresh `GNUPGHOME` under `$RUNNER_TEMP` (mode 700),
`--batch --no-tty`, and keys imported only from the committed public-key files whose fingerprints
match the pinned values (`--recipient-file` for encryption); no key server, no agent forwarding,
no trust database decisions.

**Format.**

| Artifact | Plaintext (on the runner only) | Encryption |
|---|---|---|
| `remediation-review-<run_id>` | `bundle.tar` (POSIX ustar): `plan.json` (`terraform show -json`), `plan.txt` (`terraform show -no-color`), `eligibility.json`, `fingerprint.json` (`F_plan`, `K_run` hex, fingerprint document version) | `bundle.tar.gpg`: OpenPGP public-key encryption to the reviewer's encryption subkey (Curve25519), AES-256, integrity-protected (MDC or AEAD; a packet without integrity protection is refused on decryption), no compression (`--compress-algo none`), binary (no armor), not signed |
| `remediation-seal-<run_id>` | `k_run` (32 bytes) | `seal.gpg`: the same format, to the apply-job key |

- Retention: 2 days for both (longer than the 24-hour approval window). Retention limits how
  long the ciphertexts are offered, not who may already hold a copy (§9.5).
- Integrity and origin: OpenPGP encryption does not authenticate the sender. Origin comes from
  GitHub: both artifacts belong to this run, and their GitHub-reported SHA-256 digests are fixed in
  the statement, which the reviewer attests.
- Failure of version check, encryption or upload: `review_bundle_failed`; there is no plaintext
  fallback.
- Public exposure: ciphertext and its size only.

### 8.3 Reviewer procedure (tested)

All local work happens in the ignored `.artifacts/remediation-review/<run_id>/` (Rule 15), created
with mode 700, using the reviewer's own GitHub login.

1. **Dispatch** the workflow (§6.1). Wait for the `plan` job; read the run summary (code,
   structural summary, statement, `S`).
2. **Download** both artifacts as zip files through the GitHub API (`gh api
   repos/<owner>/<repo>/actions/artifacts/<id>/zip`), compute their SHA-256, and check them
   against `review_bundle_digest` and `seal_digest` in the downloaded statement.
3. **Decrypt** `bundle.tar.gpg` with `gpg --decrypt` (the private key stays in the reviewer's key
   store; the passphrase is entered locally) and extract `bundle.tar`.
4. **Inspect** `plan.txt` and `plan.json`: every change, with values, exactly as CI planned it.
5. **Verify** with the Task 11.3 helper, run from the approved commit (same `drift_engine` code):
   it recomputes eligibility and `F` from `plan.json` with `K_run` from the bundle, compares them
   and every statement field it can check (commit, Terraform and provider versions, lock-file and
   var-file hashes, GnuPG version, key fingerprints, mode, run id, digests) and prints `S`. Any
   difference: **reject**.
6. **Decide** with the checklist below. Reject in GitHub if anything is wrong.
7. **Approve (A)** the pending deployment in the GitHub "Review deployments" dialog.
8. **Attest (B)**: the helper writes the attestation document (§8.5) for this run, the apply
   job's attempt shown in the run page, and `S`, and signs it with the reviewer's private key
   (detached, armored). The reviewer pastes the helper's output (attestation and signature) into
   the comment field of the same "Review deployments" dialog. The comment field is only a
   transport (§8.5).
9. **Grant just in time** (§10.9, §10.10): from the separate, reviewed local clone, start the grant
   script for this run with your own GitHub and Azure logins. It runs its pre-grant checks from your
   trusted inputs, waits until the job reports `ready_for_jit_grant` at P12, grants only this run's
   roles (`pending`, then `confirmed`), and removes them when the job ends or at the 45-minute
   limit. Keep the machine awake and online until it reports a clean V2. If it reports a removal
   failure, follow the emergency procedure in §10.10 at once.
10. **Delete** the decrypted files after the run ends (`rm -rf` of the run directory; best effort on
   APFS/SSD, which is why the directory never leaves the encrypted disk).
11. **Afterwards**: read the final code; the drift issue closes only through a later valid
    detection run.

**Tested**: Task 11.3 runs steps 2–5 and 8 in CI with test keys and fixtures (AC-3.8), and the
reviewer rehearses the whole procedure with the real key in the Stage A run before enablement
(AC-3.E1).

Checklist before approving: the direction is intended; every change is an expected tag change;
the whole plan is acceptable; for accept, the PR is merged and its disclosure accepted; no other
Azure change is in progress; `expires_at` is later than the expected apply time.

### 8.4 Approval statement

Canonical JSON (§9.3 rules), no values. `S` = SHA-256 of its canonical bytes.

| Field | Content |
|---|---|
| `statement_version` | `1` |
| `repository`, `workflow` | `<owner>/<repo>`, `.github/workflows/remediation-apply.yml` |
| `run_id`, `plan_run_attempt` | The immutable GitHub run id and the attempt that ran the `plan` job |
| `environment`, `mode`, `decision`, `drift_issue` | The validated inputs (`drift_issue` absent when not given) |
| `commit` | The 40-hex commit checked out by the `plan` job |
| `terraform_version`, `provider_selections` | From `terraform version -json` after `init` |
| `lock_file_sha256`, `var_file_sha256` | SHA-256 of the committed `.terraform.lock.hcl` and `dev.tfvars` |
| `backend` | Backend type and state key (`azurerm`, `dev.tfstate`); no account or subscription identifiers |
| `gnupg_version`, `runner_image` | As checked in §8.2 |
| `reviewer_key_fingerprint`, `apply_key_fingerprint` | The pinned key fingerprints used |
| `allowlist_version`, `eligibility` | The allowlist version and the per-address changed paths (no values) |
| `plan_fingerprint` | `F_plan` (§9) |
| `review_bundle_digest`, `seal_digest` | GitHub-reported SHA-256 digests of the two artifacts |
| `plan_completed_at`, `expires_at` | UTC; `expires_at` = `plan_completed_at` + 24 hours (D6) |

### 8.5 Two approvals: Environment approval and statement attestation

The two checks are separate. GitHub's Environment approval does **not** supply, carry or validate
the attestation; the attestation does not replace the Environment approval.

| | (A) Environment deployment approval | (B) Statement attestation |
|---|---|---|
| What it is | GitHub's protection rule: the `apply` job does not start until a required reviewer approves the pending deployment | A detached OpenPGP signature over an attestation document that names `S`, the run and the attempt |
| Who may give it | A login that is a required reviewer of `dev-remediation` **and** listed in the committed reviewer allowlist | The holder of a signing key whose fingerprint the committed reviewer allowlist maps to that same login |
| How identity and authorisation are verified | GitHub authenticates the reviewer and enforces the reviewer list; the `apply` job then re-reads the review history (`GET /repos/{owner}/{repo}/actions/runs/{run_id}/approvals`, `actions: read`) and checks state, environment, login and time itself | The `apply` job verifies the signature with GnuPG in an isolated home against the pinned public key only; the signing key fingerprint must map to the login that gave (A) |
| Transport | GitHub's own record | The comment field of the same review entry. It is untrusted text: only the parsed attestation and a valid signature count, and nothing in an issue, PR or other comment is ever read |

**Attestation document** (canonical JSON, §9.3 rules, signed as bytes): `attestation_version`
`1`; `decision` = `approve`; `repository`; `workflow`; `run_id`; `plan_run_attempt`;
`apply_run_attempt` (the attempt of the `apply` job being approved); `reviewer_login`; `commit`;
`plan_fingerprint`; `review_bundle_digest`; `seal_digest`; `expires_at`; `statement_sha256` (`S`).
The bound values are repeated explicitly, not only through `S`, so each can be checked on its own.

**Independent validation.** The `apply` job validates (A) and (B) separately, before Azure login,
and neither result is derived from the other:

- **(A) alone**: in the run's review history, the latest review for `dev-remediation` is
  `approved`; no rejection follows it; its login is in the committed reviewer allowlist; its time
  is after `plan_completed_at`, after the start of the current attempt (from the run-attempt API)
  and before `expires_at`. GitHub's own enforcement that the job waited for a required reviewer is
  not taken on trust alone: if the review history has no matching approval, (A) is invalid.
- **(B) alone**: the attestation and signature are taken only from that review entry's comment
  field (untrusted text: exactly one attestation and one armored detached signature, nothing
  else); the signature verifies in an isolated GnuPG home against the pinned public keys only; the
  signing key is in the allowlist, not expired or revoked; the signature creation time is after
  `plan_completed_at` and before `expires_at`.

**Cross-binding.** Each value must match across all of its sources, or the run stops:

| Value | Source in (A) / run context | Source in (B) | Statement (this run's artifact) | Fresh plan / API | Mismatch or missing |
|---|---|---|---|---|---|
| Reviewer | Login of the approving review | `reviewer_login`; allowlist maps the signing key to this login | — | — | `attestation_invalid` |
| Run | The review history is read for `github.run_id` | `run_id` | `run_id` | Run API: the run id of this job | `attestation_invalid` / `statement_mismatch` |
| Attempt | Review time after the current attempt started | `apply_run_attempt` = `github.run_attempt`; `plan_run_attempt` | `plan_run_attempt` | `plan` job outputs | `attestation_invalid` / `statement_mismatch` |
| Commit | Run API `head_sha` = `github.sha` | `commit` | `commit` | `main` HEAD (P3, P10, P13) | `statement_mismatch` / `revision_not_main_head` |
| Plan fingerprint | — | `plan_fingerprint` | `plan_fingerprint` | HMAC-SHA256(`K_run`, fresh document) (P8) | `statement_mismatch` / `plan_changed_since_approval` |
| Bundle and seal | — | `review_bundle_digest`, `seal_digest` | Same fields | Artifact API digests of this run's artifacts; the opened seal must come from that artifact | `statement_mismatch` / `seal_invalid` |
| Expiry | Review time before `expires_at` | `expires_at`; signature time before it | `expires_at` = `plan_completed_at` + 24 h | Current time before it at P2, P11 and P13 | `approval_stale` |
| Statement | — | `statement_sha256` | SHA-256 of this run's statement = `S`; artifact digest = `plan` job output | — | `statement_mismatch` |
| Toolchain | — | (through `S`) | Terraform, provider, lock-file, var-file, backend, GnuPG, runner, key fingerprints, allowlist | Rebuilt in P6 | `statement_mismatch` |
| Eligibility | — | (through `S`) | `eligibility` | Recomputed from the fresh plan (P8) | `plan_changed_since_approval` |

**Third, independent binding: the just-in-time grant** (§10.9). The grant script authenticates
with the user's own GitHub and Azure logins and, from trusted inputs that do not come from the run,
re-verifies (A) and (B), the run id, attempt, commit and `S`, the trusted-code digest, the
Environment configuration and the absence of unexpected role assignments. It then grants, checks,
and marks the assignments `state=confirmed` with the same run id, attempt and `S`; the job applies
only with confirmed assignments for exactly those values. The user's Azure credentials are a factor
that neither (A), (B) nor the workflow can supply. Without a confirmed grant, P12 ends with
`jit_grant_timeout` and nothing is applied.

| Value | (A) | (B) | Grant script (user's credentials, trusted inputs) | Job (P12, before P14) |
|---|---|---|---|---|
| Run id and attempt | Review history of this run; time after the attempt started | `run_id`, `apply_run_attempt` | Equal to the user's attestation; job in P12 | Equal to the confirmed assignment descriptions |
| Commit | Run `head_sha` | `commit` | `head_sha` = statement `commit`; trusted digest of that commit | `main` HEAD (P13) |
| `S` (statement, fingerprint, digests, expiry) | — | `statement_sha256` and the repeated fields | Equal to the user's attestation; `expires_at` more than 45 minutes away | Prefix in the confirmed descriptions; fingerprint recomputed (P13) |
| Reviewer | Allowlisted login | Allowlisted key mapped to that login | Authenticated as that login; verifies (B) with the user's own key | — |
| Environment configuration | — | — | Read with the user's login; equal to the trusted policy; unchanged since the plan | P0 (fail closed, or warning under R8) |
| Permissions | — | — | Only the per-run least-privilege set, Azure-time-bound (§10.10); no unexpected assignment | Exact assignments (principal, role definition, scope), end time ≤ 45 minutes after start and ≥ 21 minutes away before P14, exact effective permissions; the marker is not a security check |

A missing value in any column counts as a mismatch. Codes: an invalid or missing (A) gives
`environment_approval_invalid`; a missing (B) `attestation_missing`; an invalid (B) or a reviewer,
run or attempt mismatch `attestation_invalid`; a statement, digest or toolchain difference
`statement_mismatch`; a changed plan `plan_changed_since_approval`; expiry `approval_stale`. All
stop before apply; none is retried.

**Security event (R3, approved).** If (B) is present and valid but (A) is missing or invalid (for
example after an admin bypass or a changed environment rule), the run stops with
`environment_approval_invalid` and the record and summary add `security_event:
attestation_without_environment_approval`. The event records only the run id, the attempt, the
public signing-key fingerprint and `S`; it never records the attestation body, the signature,
values, `K_run` or any key.

What the binding cannot prove: that the reviewer read the bundle (procedural, §8.6), or that the
workflow code itself is unmodified (see the account-compromise row in §9.6). A re-run of the
`apply` job needs a new (A) and a new (B) for the new attempt, and is still limited by
`expires_at`.

### 8.6 Self-approval (D5, retained) and the future multi-reviewer requirement

- **Now**: the only maintainer dispatches, approves (A) and attests (B). Self-approval is allowed
  and recorded (`self_approved: true` in the record; the login is not republished).
- **Risk accepted**: no independent second review. The two checks and the local verification are
  a deliberate pause, not a four-eyes control. (B) protects against an approval given without the
  key holder's verification, but **not** against an attacker who controls the maintainer's GitHub
  account: that account can change the workflow code and remove the (B) check (§9.6). With standing
  write roles, the account alone can therefore apply within the RBAC scope; decision R5 (§15.2)
  addresses this.
- **Future requirement**: before any of the following, the environment must require at least two
  reviewers with **Prevent self-review** on, the attestation must require signatures from two
  different allowlisted reviewers, and this document must be amended: a second person gets write
  access to the repository; any environment other than `dev` is added; any managed resource holds
  production or personal data; the remediation identity's scope grows beyond
  `aitdd-dev-main-rg`; or NSG rule changes are allowed (§7.4).

### 8.7 Reviewer key custody (U4, conditional)

- **Generation**: on the reviewer's own machine with GnuPG: an Ed25519 primary key (certify and
  sign) and a Curve25519 encryption subkey, one-year expiry, strong passphrase. A revocation
  certificate is created at the same time. A hardware token (OpenPGP smart card) is **optional
  hardening**, not enforced for `dev` (R2, deferred); it becomes required with the D5 multi-reviewer
  conditions (§8.6).
- **Custody**: the private key lives only in the reviewer's local GnuPG store (or token). It is
  never copied into the repository, a GitHub secret, an environment, an artifact, an issue, a
  comment or a log. The workflow never needs it: CI uses only the public key.
- **Backup and recovery**: one passphrase-protected export of the private key and the revocation
  certificate on offline media kept by the reviewer. A lost key cannot recover old bundles (they
  are short-lived anyway): the reviewer generates a new pair and commits the new public key and
  allowlist entry in a reviewed commit; approvals are impossible in between (fail closed).
- **Rotation**: yearly (the expiry forces it: an expired key makes the `plan` job's encryption or
  the attestation check fail closed) and immediately on suspicion; on compromise, publish the
  revocation, commit the new key, and treat attestations made with the old key as invalid.
- **Confirmation that it never enters GitHub**:
  - a structural test checks that every committed key file is public-only (`gpg --show-keys`
    lists no secret key) and matches its pinned fingerprint;
  - TruffleHog (Task 9.3) scans every push and blocks private-key material; Task 11.3 verifies
    with a generated test private key that the configured scan detects an OpenPGP private key
    block (if it does not, an explicit check for `BEGIN PGP PRIVATE KEY BLOCK` is added);
  - `.gitignore` covers the review directory and exported key file names;
  - the workflow references no secret for the reviewer key (structural test), and the leak scan of
    logs, statements and records includes private-key markers.
- **Apply-job key (R1, revised)**: an encryption-only OpenPGP key (Curve25519 subkey), one-year
  expiry, generated by the user on their own machine in a temporary GnuPG home. Its private part is
  stored as the `dev-remediation` environment secret. GitHub never shows a secret value again, so
  the secret itself cannot serve as a backup.
  - **Recovery trade-off**: what the key protects is short-lived (each seal is needed only within
    its own run, at most 24 hours), and no data stays encrypted to it, so losing it destroys
    nothing. A recovery copy only shortens the outage after a loss, but it is one more place the
    key can be stolen from: with the key, an attacker can open every seal they have collected
    (§9.6).
  - **Design (preferred in review)**: one **encrypted offline recovery copy**. The exported private
    key is encrypted symmetrically (OpenPGP, AES-256, a passphrase used for nothing else and kept
    in the user's password manager), stored on offline media in the user's sole custody, never on
    networked or cloud-synchronised storage, and never next to the reviewer key backup. Access is
    the user only. It is destroyed when the key is rotated. All plaintext copies on the user's
    machine are deleted after the upload and the backup.
  - **Key-loss consequences** (with or without the copy): every run whose seal was made for the
    lost key stops with `seal_invalid`; nothing is applied, and no data is lost.
  - **Recovery or rotation procedure** (each step user-approved and recorded; on suspected
    compromise, rotation is mandatory and the recovery copy must not be used):
    1. Restore from the recovery copy into the environment secret, if loss (not compromise) is the
       cause and the copy is intact; then finish.
    2. Otherwise: generate a new key pair; replace the `dev-remediation` secret value; commit the
       new public key and its pinned fingerprint in a reviewed commit; create a new encrypted
       recovery copy and destroy the old one.
    3. Dispatch new runs; runs sealed for the old key are never resumed.
    4. Record the rotation (date and new fingerprint only) in `PROJECT_PLAN.md`.

## 9. Plan fingerprint

### 9.1 Construction

`F` = lowercase hex HMAC-SHA256 with the per-run key `K_run` over the canonical JSON (§9.3) of the
fingerprint document (§9.2). `K_run` is 32 bytes from the operating system's random source,
generated in the `plan` job, and available afterwards only inside the reviewer's bundle and the
apply-job seal.

### 9.2 Exact inputs

| Field | Source |
|---|---|
| `fingerprint_version` | The integer `1` |
| `mode`, `environment` | The validated inputs |
| `commit` | The 40-hex commit of the checkout |
| `terraform_version` | `terraform_version` of the plan JSON (must equal `terraform version -json`) |
| `provider_selections` | From `terraform version -json` after `init` |
| `lock_file_sha256`, `var_file_sha256` | As in the statement |
| `format_version` | `format_version` of the plan JSON |
| `resource_changes` | Every entry with every key it has (§7.1 allows only known keys), including the **full** `change` object (`actions`, `before`, `after`, `after_unknown`, `before_sensitive`, `after_sensitive`, `replace_paths`, `importing`, `before_identity`, `after_identity` and any other allowed key); sorted by (`address`, `deposed` or `""`) |
| `resource_drift` | Every entry, complete and sorted the same way |
| `output_changes` | The full object, keyed by output name |

A key absent in the plan JSON is recorded as absent, never as `null`.

### 9.3 Canonical form

- JSON with keys sorted at every level, separators `,` and `:` with no whitespace, UTF-8 without
  ASCII escaping (the drift report hash convention).
- Numbers keep their exact JSON lexical form; never converted to binary floating point.
- Arrays keep their order; only the top-level `resource_changes` and `resource_drift` lists are
  sorted, by address.
- One `drift_engine` implementation computes the document, `F`, the eligibility result, `S` and the
  attestation document in both jobs and in the reviewer's helper, from the same commit. Tests pin
  its output on fixtures.

Not included, and why: `prior_state` and `planned_values` (derived; the changes bind every value
that changes); `configuration` and `variables` (bound through `commit`, `var_file_sha256`,
`lock_file_sha256`); `relevant_attributes`, `checks`, `timestamp`, `applyable`, `complete`,
`errored` (not part of the change set; `complete == true` and `errored == false` are required
separately); the plan file bytes (run-specific metadata).

### 9.4 What the fingerprint proves, and its limits

Equal fingerprints under the same `K_run` prove that two plans contain the same changes, values,
drift and outputs at the same commit, with the same var file, lock file, provider versions and
Terraform version. They do **not** prove that the changes are correct; anything about values
unknown until apply (bound only as "unknown"; refused anyway by §7.2); what the provider or Azure
does during apply; that nothing changes in Azure after the fresh plan (Terraform's saved-plan check
covers state only); or that the reviewer read the bundle. A different toolchain or a
non-deterministic provider gives a different `F`: a safe rejection.

### 9.5 Key and seal flow (traced)

Notation: `V` = the plan's values (all attribute values in `plan.json`, **including sensitive
values**, which `terraform show -json` contains in plaintext); `D` = the fingerprint document
(contains `V`); `Enc_R` / `Enc_P` = OpenPGP public-key encryption to the reviewer key / the
apply-job key.

| Step | Where | Computation | Plaintext present | Published |
|---|---|---|---|---|
| 1 | `plan` job runner | Plan; `D`; `K_run` ← 32 random bytes; `F` = HMAC-SHA256(`K_run`, `D`) | `V`, `K_run` | — |
| 2 | `plan` job runner | `C_B` = `Enc_R`(`plan.json`, `plan.txt`, eligibility, `F`, `K_run`) | same | — |
| 3 | `plan` job runner | `C_S` = `Enc_P`(`K_run`) | same | — |
| 4 | GitHub | Upload `C_B`, `C_S`; statement (paths, `F`, digests of `C_B` and `C_S`, toolchain, expiry); `S` = SHA-256(statement) | — | `C_B`, `C_S`, statement, `F`, `S`, structural summary. Artifacts of a public repository can be downloaded by anyone while retained, so **assume an attacker may archive every `C_B` and `C_S` ever published**; the 2-day retention does not bound what such an attacker holds |
| 5 | Reviewer machine | Decrypt `C_B` with the reviewer private key; recompute `F` from `plan.json` and `K_run`; build and sign the attestation | `V`, `K_run` | Attestation and signature (review comment) |
| 6 | `apply` job runner (after (A); read roles only) | Verify (B) against the reviewer's public key; decrypt `C_S` with the apply-job private key (environment secret); fresh plan, `D'`; HMAC-SHA256(`K_run`, `D'`) = `F`? | `V'` (fresh), `K_run` | Codes; `ready_for_jit_grant` with run id, attempt and `S` |
| 7 | User's machine (not cryptographic) | Authenticate with the user's GitHub and Azure logins; pre-grant checks 1–8 from trusted inputs (§10.9), including verifying (B) again with the user's own public key; grant Azure-time-bound assignments (§10.10) marked `pending`; check; mark `confirmed` (a handshake marker only) | — | Role assignment descriptions with run id, attempt and the first 16 hex of `S` (public values) |
| 8 | `apply` job runner (roles present) | Effective-permission check; new fresh plan `D''`; HMAC-SHA256(`K_run`, `D''`) = `F`?; apply; then the user removes the roles | `V''`, `K_run` | Codes only |

What follows from the flow:

- `V` is protected **only** by `Enc_R` (in `C_B`) and by the runners and the reviewer machine. `K_run`
  protects nothing confidential: it only keys `F`.
- `F` is public. Anyone holding `K_run` can test guesses of `D`, and so of low-entropy values in
  `V`, including sensitive ones, offline.
- OpenPGP encryption gives confidentiality, not origin authentication: anyone can produce a `C_B` or
  `C_S`. Origin comes only from GitHub (the artifacts belong to this run, and their digests are in
  the statement that (B) attests).
- There is no forward secrecy: the reviewer and apply-job keys are long-lived, so a later key
  compromise exposes every ciphertext encrypted to that key that the attacker holds.

### 9.6 Compromise analysis

Assumptions: OpenPGP and HMAC-SHA256 are secure; an attacker may hold every published artifact
(step 4); the maintainer's GitHub account is the only one with write and admin access (D5); write
roles are never standing (R5). Each row was checked against steps 1–8: which plaintext the
compromised item reveals, and which check it can or cannot satisfy.

| Compromised | The attacker **can** | The attacker **cannot** |
|---|---|---|
| `C_B` and/or `C_S` only (public anyway) | Learn their sizes | Learn `V` or `K_run` |
| One run's `K_run` | Test guesses of that run's `V` against its public `F` | Learn `V` directly; anything for other runs; approve, attest or apply |
| Apply-job private key | Decrypt **every** `C_S` held, so obtain `K_run` for all those runs, and so test guesses of their `V` against their public `F` | Decrypt `C_B` (not encrypted to it); learn `V` directly; produce (A); produce (B); get Azure tokens (those need an approved `dev-remediation` job); change a run's artifacts |
| Reviewer private key | Decrypt **every** `C_B` held: **all plan values `V` of those runs, including sensitive values**, and their `K_run`; sign valid attestations (B) for any run | Produce (A) (needs the reviewer's GitHub account); get Azure tokens; apply anything |
| Reviewer private key + apply-job private key | The union of both rows: all `V`, all `K_run`, attestations | Produce (A); apply |
| The maintainer's GitHub account (alone) | Dispatch runs; give (A); **change workflow code on `main`**, which can remove the (B) check, print current plan values from a `plan` job (the read-only identity can refresh every managed resource), exfiltrate the apply-job key and obtain read-only Azure tokens (as any workflow on `main` can today); change environment settings | **Apply** anything: no write role is standing, and the user's local procedure grants roles only to a run whose remediation code matches the user's own trusted record and whose run, attempt and `S` the user attested (§10.9). Also: act outside the RBAC scope; decrypt past `C_B` without the reviewer key |
| GitHub account + reviewer private key | All of the account row, plus all `V` in held `C_B`, plus a valid (B) | Apply, for the same reason: the grant needs the user's Azure credentials and passes the trusted-code check only for reviewed code |
| GitHub account + apply-job private key | Same as the account alone (the account can already obtain that key) | Apply (as above) |
| The grant script's clone or the user's trusted record (digest, configuration), without the user's credentials | Nothing by itself: a changed script or record only matters when the user runs it with their credentials | Grant roles (needs the user's Azure login) |
| The grant script or trusted record, **and** the user then runs it | Grant roles to a run the script should have refused (for example to modified workflow code); the job then applies within that run's granted scope | Act beyond the roles that script grants; this is why the script is reviewed like the workflow and kept in a separate, user-controlled clone |
| The user's machine disconnected after `confirmed` (not a compromise) | The job applies within its own window; the roles outlive the job until Azure ends them at their PIM end time (45 minutes after the start; the actual end timing is measured in E10) or, only if R13 is ever approved, the watchdog removes them (best effort, §10.11); a token taken from that job could use them until then | Obtain new tokens without an approved run; keep the roles beyond the Azure-side limit (unless that control itself fails, §10.10 residual risk) |
| The user's machine, or the user's Azure credentials | Everything the user can do: decrypt bundles (with the passphrase or an unlocked agent), sign (B), change the local trusted-code record, grant roles, and act in Azure with the user's own rights, **outside this design's scope limits** | Nothing this design can prevent: the user's machine and Azure account are the root of trust |
| A `plan` job runner (malicious step or dependency) | Read `V` and `K_run` of that run; use the read-only Azure token; publish anything | Write in Azure (read-only identity); produce (A) or (B) |
| An `apply` job runner (malicious step or dependency) | Read `V'`, `V''` and `K_run`; **during the just-in-time window only, use the write token within the roles granted for this run** (for a tag change on the NSG, that includes NSG rule writes) | Act outside the granted roles; act after the roles are removed; produce (A) or (B) for other runs |

Conclusions recorded for review:

- A leaked **apply-job key** is limited to guess-testing, but over **every seal the attacker has
  collected**, not only the retained ones.
- A leaked **reviewer key** is a **confidentiality breach of every collected bundle**, including
  sensitive values, and defeats (B); (A) still holds.
- The maintainer's **GitHub account** controls the workflow code, so (B) and the allowlist alone do
  not stop an attacker who holds it. With **no standing write roles** (R5), that account alone
  still cannot apply: the write roles come only from the user's local, trusted-code-checked grant.
  It can still disclose current values (through a modified `plan` job) and read Azure metadata with
  the existing read-only identity.
- The **user's machine and Azure credentials** are the root of trust; nothing in this design limits
  them.
- Runner compromise (supply chain) is bounded by the job's identity: read-only in `plan`; in
  `apply`, the roles granted for that one run, and only while they are granted. JIT shortens this
  but does not remove it (§10.9).

## 10. Azure permissions (D2, proposal)

**Status: a proposal, not validated Azure permissions.** The exact provider operations, inherited
permissions, dependency access and unmanaged-resource isolation are unverified. They must be
verified and recorded through the enablement gate (§10.8) before apply is enabled. Until then the
remediation identity holds no write role.

### 10.1 Why a resource-type allowlist is not enough

A custom role with only the managed resource types, assigned at the resource group, would still
allow the identity to:

- change or delete an **unmanaged resource of a managed type** in the same group (for example an
  NSG created in the portal), because Azure RBAC scope, not the Terraform state, decides what an
  action applies to;
- change an **unmanaged child** of a managed parent: `virtualNetworks/subnets/write` at the VNet or
  group scope covers every subnet, and a VNet `PUT` carries the VNet's subnet list, so
  `virtualNetworks/write` can reshape subnets through the parent;
- retag anything in the group if `Microsoft.Resources/tags/write` were included;
- delete, if any `*/delete` or `*` action slips in.

So the proposal scopes **each write role to an individual managed resource**, uses a **separate
role definition per scope**, adds **runtime guards** for hazards RBAC cannot express, and
**verifies** isolation from the unmanaged side (§10.7).

### 10.2 Identities

| Identity | Federated credential subject | Used by |
|---|---|---|
| `aitdd-github-oidc` (existing, unchanged) | `…:ref:refs/heads/main` | Detection, `terraform-auth-test.yml`, the remediation `plan` job |
| Remediation identity (new, Task 11.2) | `…:environment:dev-remediation` only (immutable subject format, as today) | The remediation `apply` job only |

The remediation identity has no client secret or certificate, no other federated credential, no
group membership, no directory role and no Microsoft Graph permission.

### 10.3 Proposed role definitions and assignments

All custom roles: `Actions` only (no `NotActions` relied on), no wildcard, no `*/delete`, no
`DataActions`; `assignableScopes` = the `aitdd-dev-main-rg` resource group. Every action is
**expected**, pending enablement evidence E1.

| Role (custom unless noted) | Expected actions | Assigned at | Needed for (v1 allowlist: tags only) |
|---|---|---|---|
| **Reader** (built-in) | `*/read` | `aitdd-dev-main-rg` | Refresh during the apply job's plans |
| `AITDD Remediation RG Update` | `Microsoft.Resources/subscriptions/resourceGroups/write` | `aitdd-dev-main-rg` (the group object) | Resource-group tags. The action applies to the group object only |
| `AITDD Remediation VNet Update` | `Microsoft.Network/virtualNetworks/write` | The managed VNet only | VNet tags |
| `AITDD Remediation NSG Update` | `Microsoft.Network/networkSecurityGroups/write` | The managed NSG only | NSG tags (security rules stay refused by §7.4, but the same write action could carry them, see §10.4) |
| **Storage Blob Data Contributor** (built-in) | Blob data actions | The `tfstate` container only | Read, write and lock `dev.tfstate` |

**Never granted**, at any scope: any `*/delete`; `Microsoft.Resources/tags/*`;
`Microsoft.Resources/deployments/*`; `Microsoft.Authorization/*` writes; resource-group delete;
`listKeys` or any action on `aitdd-tfstate-rg` beyond the container data plane; any subscription or
management-group scope role; `Owner`, `Contributor`, `User Access Administrator`;
`Microsoft.Network/virtualNetworks/subnets/*` writes; `networkSecurityGroups/join/action`; any
resource-provider registration.

### 10.4 Residual hazards that RBAC cannot express

| Hazard | Control |
|---|---|
| A VNet `PUT` can change or remove subnets through the parent, including an unmanaged subnet | Runtime guard: a plan that updates the VNet is refused (`unmanaged_child_present`) when the refreshed VNet lists any subnet that is not a managed `azurerm_subnet`. Whether a tag-only VNet update sends a whole-object `PUT` is part of E1 |
| A tag-only NSG update may send the whole NSG, including its rule set, in a `PUT` | §7.2 refuses any plan in which `security_rule` changes. Residual race: a rule added in Azure after the fresh plan (P7–P9) and before the apply would be removed by such a `PUT`; E1 establishes whether the provider uses `PUT` or a tags-only update, and V6 detects writes after the fact |
| An allowlisted update changes more than tags on the Azure side | The plan shows every changed path; §7.2 refuses any non-tag path |
| Delete, replace, create | C1 action rule (§7.1) |

### 10.5 Runtime guards

- **Action and attribute rules**: §7.1 and §7.2.
- **Unmanaged child guard**: §10.4, first row.
- **Apply switch**: a committed setting `apply_enabled: false`. While false, the `apply` job runs
  only P0–P11 and stops with `apply_disabled` before P12, so no role grant is requested; with
  `jit_rehearsal: true` it also runs P12–P13 and stops with `apply_disabled` immediately before
  P14. In both cases `terraform apply` is never invoked.

### 10.6 Creating resources (C1, approved)

Resource-scoped write roles cannot create a new resource without a parent-scope grant that would
also cover unmanaged resources of that type. v1 refuses every `create`. Recreating a deleted
managed resource is manual, separately approved local work by the user; whether a role assignment
at a deleted resource's scope survives recreation is not relied on and is re-verified (E2) after
any recreation.

### 10.7 Isolation checks

| Check | How | Pass |
|---|---|---|
| V1 Role definitions | `az role definition list --custom-role-only true` | Exactly the §10.3 actions (as amended by E1 evidence); no wildcard, delete, `NotActions` or `DataActions`; assignable scope = the group |
| V2 Direct assignments | `az role assignment list --assignee <remediation app> --all` | Exactly the §10.3 (role, scope) pairs; every write-role scope is the Azure ID of a managed resource in `dev.tfstate` (compared locally; IDs never published) |
| V3 Inherited, from the unmanaged side | For **every** resource in `aitdd-dev-main-rg` not in Terraform state (from `az resource list -g` and the Task 10.4 inventory), every unmanaged subnet of the managed VNet, the group itself, the subscription, `aitdd-tfstate-rg` and the state account: `az role assignment list --scope <id> --include-inherited --assignee <remediation app>` (includes management-group and subscription assignments) | At unmanaged scopes only roles inherited from the group: **Reader** and `AITDD Remediation RG Update` (group object only), plus, for an unmanaged subnet, the VNet role (covered by the §10.4 guard). Nothing at subscription or management-group scope. No NSG, subnet, delete or tags action anywhere unmanaged |
| V4 Effective permissions | From a job in `dev-remediation`, as the remediation identity: `GET <scope>/providers/Microsoft.Authorization/permissions` for each managed resource and each probe | Managed scopes: exactly the expected actions. Probe scopes: read only |
| V5 Probes | The user creates (Execution Rule 10) free, disposable unmanaged probes: an NSG in the group, a subnet in the managed VNet and one resource of an unmanaged type (for example an application security group). V3 and V4 run against them; a plan with a VNet tag change must stop with `unmanaged_child_present`. The user deletes the probes afterwards | All checks as above |
| V6 After every apply (detective) | The user checks the Activity Log locally, after the Phase 9B settling margin: every write by the remediation identity during the apply window is on a managed resource's ID. The next detection run's unmanaged inventory is unchanged by the remediation | No write outside managed IDs; recorded as a code, without IDs or caller data |

Write probes that attempt a real change or delete on an unmanaged resource are not used: if a
safeguard were broken they would modify the resource.

### 10.8 Apply enablement gate

`apply_enabled` stays `false`, and no write role is ever standing, until **every** item below is
verified, recorded in `PROJECT_PLAN.md` without identifiers, and approved by the user. An item with
missing or insufficient evidence stays **unverified**, and an unverified item **blocks**
enablement; it is never assumed, and the first real runs never substitute for it.

| Item | What must be established | How |
|---|---|---|
| **E1 Provider operations** (U6, R4: conditional) | For each allowlisted update (tags on the resource group, VNet and NSG), the exact HTTP method, resource type and RBAC action AzureRM performs with the locked provider version, including whether the VNet and NSG updates are whole-object `PUT`s | **Both** sources are required and must agree: (a) the AzureRM source at the locked version, with file and function references recorded; (b) **Activity Log records** of that exact operation on that resource. Evidence (b) comes from a **separately approved, narrowly scoped, reversible** local change by the user (Execution Rules 10 and 13): with the pinned Terraform and provider versions, add one probe tag (`aitdd_e1_probe`) to one resource's configuration on a local branch, `terraform apply` it, read the Activity Log locally, then revert the tag with a second approved apply and confirm detection is in sync; one resource per change. Only operation names, resource types and HTTP methods are recorded, never IDs or caller data. Older applies count only if they used the same provider version and are still retained. Missing, ambiguous or disagreeing evidence for any allowlisted update leaves E1 **unverified** and enablement blocked |
| **E2 Inherited permissions** | The remediation identity's effective permissions at every relevant scope | V1–V3 |
| **E3 Dependency access** | OIDC login works only from `dev-remediation`; the backend works with the `tfstate` container role (and whether it needs any ARM read on the state account); refresh works with Reader at the group; no provider registration is attempted | **Stage A**: read roles only; the user creates a reversible probe-tag drift (Task 3.6 script) and runs the full review procedure (§8.3) on a `revert` run; the `apply` job passes P0–P11 and stops with `apply_disabled`; the user removes the probe tag. Plus AC-2.5 |
| **E4 Unmanaged isolation** | No write or delete on any unmanaged resource or child | **Stage B**: the write roles, as amended by E1, granted temporarily through the §10.9 procedure in a `jit_rehearsal` run, `apply_enabled` still false; V2–V5 pass (V4 from that run's P12 permission check plus the probe scopes); the roles are removed and their removal confirmed |
| **E5 Workflow guards** | The Task 11.3 acceptance tests pass (AC-3.1–AC-3.31) | CI results on the commit that sets `apply_enabled: true` |
| **E6 Auth-test log exposure fixed** | `terraform-auth-test.yml` no longer prints plan content (values) to the public job log, and still leaves the audit record it exists for. The code fix is outside Task 11.1 (a separate, approved change, Phase 12 or a dedicated task) but is a **prerequisite** for enabling apply: a remediation makes real values current in Azure, and every later push would otherwise print them | (a) **Structural test**: the plan's stdout and stderr go to a runner-local file; the step prints only fixed lines: Terraform version, plan exit code, the add/change/destroy counts parsed from `terraform show -json`, and on failure a fixed failure code (never raw error text). (b) **Executed-step test** with a fake `terraform` that prints sentinel values in its plan, drift section and error output: none appears in the step output. (c) **Audit retention**: the job conclusion, step status, exit code and counts remain in the log and step summary, so a run still proves that OIDC login, init, validate and plan worked. (d) **Real check**, user-approved: with a temporary sentinel probe-tag value in Azure (Task 3.6 script), a push-triggered auth-test run on `main` succeeds, the user downloads its log locally, the sentinel is absent and the counts line is present; the probe tag is then removed. (e) Existing logs handled as in §12.1 (R7, R10) |
| **E7 Just-in-time roles verified** (R5, R9) | The §10.9–10.10 procedure works: every pre-grant refusal, the handshake, the job's security checks (exact assignments, Azure-side end times, effective permissions; never the marker alone), the time limits, cleanup in every case of §10.10 with success only on a clean V2, leftover detection and the emergency message | Script tests with a fake `az` and `gh` (AC-3.24, AC-3.27, AC-3.28) and job tests (AC-3.22, AC-3.23, AC-3.29); one real rehearsal (`jit_rehearsal: true`, `apply_enabled: false`) on a probe-tag run: grant at P12, confirmed handshake, the job's own checks, the P13 re-plan, the stop before P14 with `apply_disabled`, removal and a clean V2; plus one real rehearsal in which the user interrupts the script after the grant and restarts it, which must remove the roles first |
| **E8 Environment configuration verified** (R6, R8) | The Environment protection configuration is verified before every grant | The grant script's check (pre-grant step 5) always runs (R8, approved). In addition, P0 in the job: if E8 shows that the workflow token reads the configuration reliably, P0 fails closed on any difference; if not, P0 records `environment_config_unverified` as a warning and the script's check is the gate. Verified by a real P0 run and a real script run against the configured environment, and by tests with each setting changed (AC-3.26) |
| **E9 Eligibility validated on real plans** (U3) | For each allowlist address to be enabled, the actual validator (§7.1–7.2) accepts a real tag-only plan and refuses a real plan with any other change | A fresh, user-approved local plan with the pinned Terraform 1.14.7 and AzureRM 5.7.0 for one reversible probe-tag drift on that address (Task 3.6 script), passed through the validator in both modes (`plan` and `refresh_only`); plus a real plan with a non-tag change on the same address that must be refused. Only then is the address's `enabled` flag set, in a reviewed commit. Without real evidence for an address, its entry stays disabled; the committed `external_drift` fixture is preliminary evidence only (§7.3) |
| **E10 Role expiry control verified** (R11, R13) | Every just-in-time assignment ends without the user's machine: PIM time-bound active assignments (preferred), or, if PIM is unavailable and the user approves R13, the Azure-side watchdog | **PIM**: the user confirms the tenant licence and PIM onboarding for the subscription; a rehearsal creates a time-bound assignment of one custom remediation role to the remediation identity at its single scope with a short test end time, confirms the job reads the end time, disconnects the script, and confirms Azure ends the assignment on time (V2). **Watchdog**: its role can only read and delete assignments (V1–V3 for its identity); the §10.11 rehearsals (removal after the 45-minute threshold within the measured delay, alerts, failure handling, verification); this applies only if the user approves R13 after the PIM check. If neither control is verified, E10 stays unverified and `apply_enabled` stays `false` |
| **E11 User approval** | The user approves enabling apply, based on E1–E10 | A recorded decision; the enabling commit is reviewed |

There are no standing write roles (R5): Stage B and every real run use the §10.9 procedure.

After enablement, the first real runs (AC-3.20) confirm E1 in practice. Any mismatch
(`AuthorizationFailed` or an unexpected operation in V6) disables apply again until the evidence
and the proposal are corrected. Any later change to the allowlist, roles or scopes repeats the
affected items.

### 10.9 Just-in-time write roles (R5)

The remediation identity holds **read roles only** (Reader at the group, blob data on the
`tfstate` container). Write roles exist only inside one approved run's window and are granted and
removed by **the user**, with the user's own Azure credentials, through the local grant script.
The workflow never grants or removes roles (invariant 19): the identity has no
`Microsoft.Authorization/*` write action, and a structural test keeps role commands out of every
workflow.

**The grant script is part of the security boundary.** So are its trusted inputs, which never come
solely from the run being approved:

| Trusted input | Where it comes from | Why not from the run |
|---|---|---|
| The script itself | A separate local clone that the user updates only after reviewing the script's diff; the user records the reviewed commit locally | A script fetched from `main` could have been changed by whoever controls the repository |
| Trusted-code digest | A SHA-256 tree digest over the remediation code and policy (the workflow file, the scripts and `drift_engine` modules it runs, the constraints file, the pinned action references, the update allowlist with its `enabled` flags, the reviewer allowlist, the committed public keys and their pins, the expected Environment configuration, the `apply_enabled` setting and the grant script itself), computed by the user from a reviewed commit and stored outside the repository | The run's own files are what is being checked |
| Expected Environment configuration | The same reviewed policy file, covered by the digest | — |
| `S`, run id and apply attempt | The user's own attestation (B), kept locally when signing | The run log only announces them; it is not the source |
| The remediation identity's object ID, the scope IDs and the role-definition IDs | The user's local, private configuration, verified against Azure when first recorded | Not published anywhere |

**Authentication.** The script uses the user's own `gh` login and `az` login, never a workflow
token. Before anything else it checks that it is authenticated as the expected GitHub login and
the expected Azure tenant and account; otherwise it refuses.

**Pre-grant checks.** All must pass, in this order; any failure means **no grant** and a fixed
refusal message (the job then ends at P12 with `jit_grant_timeout`, no apply):

1. Self-check: the script's own clone is at the locally recorded reviewed commit and has no local
   modifications.
2. Run binding: the run id, apply attempt and `S` the job announced at P12 equal the values the
   user attested in (B); the run is on `main`, its workflow path is `remediation-apply.yml`, its
   `head_sha` equals the statement's `commit`, and the job is currently in the P12 step (GitHub
   API, with the user's login).
3. Trusted code: the digest computed from the run's `head_sha` equals the user's trusted digest.
4. Approvals: the run's review history shows (A) by the user's allowlisted login, after
   `plan_completed_at` and before `expires_at`, and the (B) in that review verifies against the
   user's own public key and names this run, attempt and `S` (the same checks as P1–P2, done
   independently with the user's credentials).
5. Environment configuration (R8): the script reads `dev-remediation` with the user's login and
   requires it to equal the trusted expected configuration (reviewers, self-review setting, `main`
   only, no wait timer, administrator bypass off) and its `updated_at` to be earlier than
   `plan_completed_at` (no change during the run). Unreadable, different or changed: refuse.
   This check runs before every grant, whether or not the workflow's P0 could read the
   configuration.
6. Existing assignments: the remediation identity holds exactly the Stage A read roles and nothing
   else, at any scope the user can list (management group, subscription, groups, resources), and
   no principal holds any of the custom remediation roles. Anything unexpected: refuse.
7. Least-privilege set: from the statement's eligibility, only the roles for the addresses this run
   changes, each at its single resource scope (§10.3), and only for addresses whose allowlist entry
   is enabled (E9).
8. Time: `expires_at` is more than 45 minutes away, so the whole window fits inside the approval.

**Grant and handshake.** The script grants through the expiry control chosen in §10.10 (Azure
Privileged Identity Management time-bound assignments, or the verified fallback); a grant method
without Azure-side expiry is never used. Each assignment gets the description
`aitdd-jit state=pending run=<run_id> attempt=<n> S=<first 16 hex of S>`; the script records it in
its local state file (§10.10) and lists the assignments again. Only if exactly the intended set
exists, each with the expected end time, and the re-read Environment configuration is still
unchanged, does it update each description to `state=confirmed`. If anything is wrong, it removes
what it created and never writes `confirmed`. Descriptions contain only public values.

**The description is a handshake marker, not a security boundary.** Anyone able to write role
assignments could also write that text. It only tells the job that the user's checks finished; the
job never treats it as proof of anything.

**In-job security checks (P12 and immediately before P14).** The job applies only if, each time:

1. its role assignments, read through its Reader role at the group, are **exactly** the expected
   set, compared by principal (the remediation identity), role-definition ID and exact scope
   (resource ID), with no other assignment of any role to the identity at the group or below;
2. each assignment is time-bound on the Azure side (§10.10): under PIM, its Azure-recorded end time
   is no more than 45 minutes after its start; under the approved fallback (R13), its end is its
   Azure-recorded creation time plus 45 minutes, after which the watchdog removes it on a best-effort
   basis (§10.11); either way at least 21
   minutes away before P14 (the 20-minute apply step plus a margin);
3. its **effective permissions** (`Microsoft.Authorization/permissions` at each expected scope) are
   exactly the expected write actions, and at the group scope nothing beyond Reader and, where the
   group's own tags change, the group-object action;
4. the handshake marker reads `state=confirmed` for this run, attempt and `S`.

Checks 1–3 are the security checks; check 4 only confirms that the user's procedure finished. Any
failure gives `jit_grant_not_confirmed`, `jit_permissions_unexpected` or `jit_window_exceeded`;
nothing is applied.

**Leftover detection.** The `plan` job's preflight (with the detection identity's subscription
Reader) and P0 of the `apply` job (with the remediation identity's Reader at the group, which
covers every write scope) stop the run with `write_roles_present` if the remediation identity
holds any write role assignment. The script's step 6 and its final V2 check the same.

### 10.10 Role expiry, time limits, lifecycle, cleanup and emergency (R9, R11)

#### Role expiry control (R11)

A cleanup that runs on the user's machine is **not** an expiry control: it stops when the machine
sleeps, loses its network or crashes. Apply therefore needs an expiry that Azure enforces or that
runs independently in Azure; otherwise `apply_enabled` stays `false` (E10).

| Control | What enforces the 45-minute maximum | Status |
|---|---|---|
| **Primary: Privileged Identity Management (PIM) time-bound active assignments** | The grant script creates each role assignment through a PIM role-assignment schedule request with an end time 45 minutes after its start; Azure ends the assignment itself, whether or not the user's machine is reachable | Preferred (R11). Usable only if the tenant's licensing (Microsoft Entra ID P2 or Entra ID Governance) and configuration support time-bound active assignments of these custom roles to a service principal at these scopes, with a 45-minute duration; verified in E10 |
| **Only if PIM is unavailable: Azure-side cleanup watchdog** (separate design, §10.11) | Nothing enforces a strict expiry. A timer-triggered job in Azure removes matching assignments once they pass the 45-minute threshold; with a 5-minute interval, removal can come **up to about 5 minutes after the threshold**, plus the job's run time, retries and RBAC propagation. It is independent of the user's machine, but it is best-effort cleanup, not Azure-enforced expiry | **Not approved** (R13). A separate design for review only; not to be implemented or provisioned. It would add an Azure resource and a privileged (delete-only) identity (Execution Rule 12) |
| Neither available or verified | — | `apply_enabled` stays `false` |

The local script's removal at the end of the job remains, as the **earliest** cleanup; it is never
counted as the expiry control.

#### Time limits, enforced consistently

| Limit | Value | Enforced by | On breach |
|---|---|---|---|
| Grant propagation | 15 minutes from `ready_for_jit_grant` to exact, Azure-time-bound assignments with matching effective permissions | The job (P12) | `jit_grant_timeout`; no apply |
| Final recheck | 5 minutes for P13 | The job | `jit_window_exceeded`; no apply |
| Apply | 20-minute step timeout for P14 | The job | The step fails; nothing more is applied |
| Remaining role lifetime before apply | At least 21 minutes (P14's 20 minutes plus a margin) | The job, from the Azure-recorded end time (PIM) or from the creation time (fallback, end = creation + 45 minutes) | `jit_window_exceeded`; no apply |
| Maximum role lifetime | 45 minutes from the start of the assignment | Azure, through the PIM end time (the actual end timing is measured in E10); the local script removes earlier when it can. Under the not-approved watchdog design (§10.11) this would be a removal threshold, not an expiry | Under PIM, the roles end regardless of the job and of the user's machine |

Consistency: the grant can only appear during P12 (at most 15 minutes after `ready_for_jit_grant`),
so at the start of P14 an assignment is at most 20 minutes old and has at least 25 minutes left;
the 21-minute rule refuses anything later. A legitimate apply therefore always ends before the
maximum lifetime.

#### Lifecycle

| Phase | Roles | Who acts | What enforces safety |
|---|---|---|---|
| 1. Plan job, review, (A), (B) | None (read only) | The workflow, the user | §8 binding |
| 2. P0–P11 in the `apply` job | None (read only) | The workflow | Fresh plan, fingerprint, leftover check |
| 3. P12: `ready_for_jit_grant` | None yet | The workflow | 15-minute timeout |
| 4. Grant | Created, Azure-time-bound, `pending` | The user's script (pre-grant checks 1–8) | Exact set, end time, configuration re-read |
| 5. Confirm | `confirmed` | The user's script | Marker only |
| 6. P12 checks pass | Present | The workflow | In-job security checks 1–3 |
| 7. P13: recheck and new fresh plan | Present | The workflow | Revision, conflicts, expiry, fingerprint |
| 8. Pre-P14 check, P14 apply | Present | The workflow | Checks 1–4 again; 21-minute rule; 20-minute step timeout |
| 9. Job ends (any outcome) | Present until removed | The user's script removes them; in any case Azure ends them at the PIM end time (or, only under an approved R13, the watchdog removes them after the threshold) | PIM end time 45 minutes after start; watchdog: threshold plus up to one interval and delays (§10.11) |
| 10. Verification | None | The user's script (V2), then every later run's preflight and P0 | `write_roles_present` stops later runs |

#### Cleanup and failure cases

| Case | What happens | Can an apply follow? |
|---|---|---|
| Job ends normally (applied, refused, failed, cancelled, timed out) | The script removes the assignments (and, under PIM, ends the schedule) and confirms with V2 | Only the apply already performed in that job |
| A pre-grant check fails | Nothing is granted | No |
| A post-grant check fails | The script removes what it created; it never writes `confirmed` | No: P12 and the pre-P14 check fail on the assignments themselves, and the marker is missing |
| Script interrupted (Ctrl-C, terminal closed, `SIGTERM`) | Its exit handler removes the assignments and confirms with V2 | Before `confirmed`: no. After: the roles disappear, so the pre-P14 check stops the job; only an apply already running in P14 can be affected, and it then fails part-way (`apply_failed`, visible in the post-apply plan) |
| Script killed (`SIGKILL`), crash, laptop sleep, network loss | No handler runs. Azure ends the assignments at their PIM end time (or, only under an approved R13, the watchdog removes them on a best-effort basis). On its next start the script first removes every unfinished grant in its state file | Before `confirmed`: no. After: only within the job's own window; the job cannot be resumed |
| Removal fails (Azure error, expired session, no network) | Retries with backoff for 5 minutes, then the **emergency** message and a non-zero exit. The Azure expiry or the watchdog still ends the roles | Every later run stops with `write_roles_present` until V2 is clean |

**A cleanup is successful only when** V2 shows that the remediation identity holds no write role
assignment (and, under PIM, no active schedule instance) at any scope the user can list. Only then
does the script exit 0 and delete its state entry. Any other outcome is a non-zero exit, keeps the
state entry, prints the emergency procedure and is recorded as `cleanup_unconfirmed` by the user.
The `apply` job ends before cleanup and cannot observe it, so its record states
`jit_cleanup: not_observed_by_job`; the evidence of cleanup is the script's V2 result and the next
run's leftover check.

**Emergency procedure** (whenever cleanup is unconfirmed, or the user is unsure):

1. From any device with the user's Azure access (for example the Azure portal on a phone), remove
   the remediation identity's write role assignments (under PIM, end the active assignments) and
   confirm none remain.
2. If that is not possible at once, block new tokens: delete the remediation identity's federated
   credential or disable its service principal. Already-issued tokens stay valid until they expire,
   so step 1 is still required.
3. Check the Activity Log (V6) for writes by the remediation identity after the run's apply step
   ended; any such write is a security incident.
4. Record the event in `PROJECT_PLAN.md` without identifiers; recreate the federated credential
   only after the roles are confirmed removed.

#### Residual risk

| Situation | Exposure | Bound |
|---|---|---|
| Roles active during a legitimate run | Any code in that `apply` job can use the write token within the granted scope | The run's window; JIT does **not** make a compromised workflow safe |
| Permanent assignments (only if neither PIM nor the watchdog is in place) | Roles stay until someone removes them | None: this is why apply then stays disabled |
| Local machine disconnected or cleanup interrupted | Roles outlive the job | PIM end time, 45 minutes after start (actual timing measured in E10). Watchdog (only if R13 is ever approved): no strict bound; typically the threshold plus up to about 5 minutes plus run time and propagation, and longer if the watchdog fails (§10.11) |
| Already-issued tokens | A token taken from the job stays valid until it expires (Entra access tokens typically live 60–90 minutes); it is only useful while the roles exist | Role removal, after RBAC propagation (Azure documents up to about 10 minutes, occasionally longer) |
| Delayed emergency response | If both the local cleanup and the Azure-side control fail (for example an Azure outage or a broken watchdog), roles stay until the user acts | The user's response time; later runs are blocked by `write_roles_present` |

### 10.11 Azure-side cleanup watchdog: separate design for review (R13, not approved)

**Status**: a design for review only, relevant only if the user's check shows that PIM time-bound
assignments are not available (E10). It is **not approved**, and nothing of it is implemented or
provisioned. Without PIM, and unless this design is approved and verified, apply stays disabled.

**What it is, and what it is not.** A timer-triggered job running in Azure (hosting to be chosen in
review, for example a consumption Azure Function or a Logic App) that removes just-in-time
remediation role assignments once they pass a **45-minute threshold**. It is cleanup, **not
expiry**:

- with a 5-minute interval, an assignment can stay **up to about 5 minutes after the threshold**
  before a run sees it, plus that run's own duration, its retries and RBAC propagation of the
  deletion;
- a delayed or missed timer execution, a platform outage or a failing watchdog extends this
  without a fixed bound (hence the missed-run alert below);
- so it must never be described as a strict 45-minute expiry. The job's own limits (§10.10) are
  unchanged: a legitimate apply always ends before 45 minutes.

**Trusted assignment-age record.** The age of an assignment comes only from Azure, never from text
a client wrote:

- primary: the role assignment's `createdOn`, which Azure Resource Manager sets;
- cross-check: the Activity Log event of the `Microsoft.Authorization/roleAssignments/write` that
  created that assignment ID. If both exist, the **earlier** time counts;
- `updatedOn` is never used (a description update must not reset the age), nor the handshake
  marker, the grant script's state file or any GitHub data;
- an assignment whose `createdOn` cannot be read is treated as overdue.

A deleted and re-created assignment has a new `createdOn`; that is a new grant, which needs the
user's credentials and pre-grant checks again.

**Exact restriction of deletions.** The watchdog deletes an assignment only if **all** of these
match, using values the user configured at deployment (never values read from GitHub or from the
assignments themselves):

1. principal ID = the remediation identity's object ID, and principal type = service principal;
2. role-definition ID = one of exactly the three custom remediation role definitions (§10.3);
3. scope = exactly one of the allowed scopes (the group or the single managed resources of §10.3);
4. age (above) ≥ 45 minutes, or the marker still reads `pending` and the age is ≥ 15 minutes.

Anything else is **never deleted**, even if it looks related. Anomalies are reported, not acted on:
the remediation identity holding any other role, or a custom remediation role assigned to any other
principal or at any other scope, raises an alert only.

**Its own identity and permissions.** A managed identity with no secret, holding only a custom role
with `Microsoft.Authorization/roleAssignments/read` and `Microsoft.Authorization/roleAssignments/delete`
at the `aitdd-dev-main-rg` scope (needed to see and delete assignments at that group and the
resources in it). It cannot create or change assignments, definitions or anything else. Azure RBAC
cannot narrow `delete` to particular role definitions, so the permission is broader than the code's
restriction: if the watchdog's code or identity were compromised, it could delete other assignments
at the group or below, which is an availability risk (lost access), not an escalation. Its code
would be deployed only from a reviewed commit, and its configuration (the IDs above) is private.

**API and deletion failures.**

| Failure | Handling |
|---|---|
| Listing fails (error, throttling, authorisation) | Bounded retries with backoff within the run; then alert `watchdog_list_failed`. Never treated as "nothing to delete" |
| Activity Log unavailable or late | Use `createdOn` alone; if that is also missing, treat as overdue |
| Deletion fails | Bounded retries within the run; then alert `watchdog_delete_failed`; retried in every later run and alerted again until it succeeds |
| Deletion returns "not found" | Treated as possibly removed, then confirmed by re-listing (below) |
| Several assignments | Each handled independently; one failure does not stop the others |
| The user's script deletes at the same time | Harmless: deletion is idempotent, and both confirm by re-listing |

**Alerts** (to the user, for example by e-mail through an Azure Monitor action group; they contain
role names, scope types and ages, no secrets):

- **overdue**: any matching assignment at or past the threshold, raised before the deletion is
  attempted and again in every run while it still exists;
- **removed**: every deletion, with the assignment's age;
- **failures**: `watchdog_list_failed`, `watchdog_delete_failed`, and every anomaly above;
- **missed runs**: an alert if no successful watchdog run has completed for 15 minutes (a
  heartbeat on its own executions), because a stopped watchdog cleans nothing.

**Cleanup verification.** After deleting, the watchdog re-lists the remediation identity's
assignments (and reads the deleted assignment ID, expecting "not found"); a removal counts only when
the assignment is absent. It logs each confirmed removal privately in Azure. The user's V2 and the
next run's leftover check (`write_roles_present`) remain independent confirmations.

**Verification plan, only if R13 is approved later** (part of E10):

- unit tests of the selection logic: exact matches only (each of the four conditions failing on
  its own), the age rule (earlier of `createdOn` and the Activity Log, `updatedOn` ignored, missing
  `createdOn` treated as overdue), and the `pending` rule;
- failure injection: listing and deletion errors, throttling, "not found", partial failure,
  concurrent deletion, each with the expected alert;
- real rehearsals with the grant script stopped: a test assignment past the threshold is removed
  and the actual delay after the threshold is measured and recorded; an anomaly is alerted and not
  deleted; disabling the timer raises the missed-run alert;
- V1–V3 for the watchdog's own identity: it can read and delete assignments only, and cannot create
  them.

## 11. Freshness, concurrency, cancellation and failure

### 11.1 Freshness (D6, retained)

- **Approval age (24 hours)**: `expires_at` in the statement; checked at P2, P11 and P13
  (`approval_stale`).
- **An expired approval needs a fresh plan and fresh approvals**: a new dispatch (new plan, bundle,
  seal, statement, review, (A) and (B)). Re-running the `apply` job of an old run is bound to the
  old statement and refused after `expires_at`; before it, the re-run needs a new (A) and a new (B)
  for the new attempt, and still re-plans and compares.
- GitHub's own pending-review limit (30 days) is not relied on.
- **Never an old plan** (invariant 6): only the latest plan created in P7 of the same job is
  applied, after its eligibility and fingerprint matched; Terraform also refuses a saved plan when
  the state changed after it was created (`stale_plan`).

### 11.2 Concurrency (D7, provisional)

**Requirements**: no two Terraform operations on `dev.tfstate` at the same time (remediation vs
detection, remediation vs remediation, remediation vs `terraform-auth-test.yml`); remediation never
cancels detection and never holds it while waiting for review; an old plan is never applied.

**No shared GitHub concurrency group**: in a GitHub concurrency group, a newly queued run replaces
and **cancels** any run already pending in that group, whatever `cancel-in-progress` says. Sharing
`drift-detection-dev` could cancel a pending scheduled detection, and a remediation run waiting up
to 24 hours could hold the group. `remediation-apply.yml` uses no concurrency group;
`drift-detection.yml` and `terraform-auth-test.yml` are not changed.

**Principles**: the Terraform state lock is the hard exclusion (`-lock-timeout=120s` as detection;
never `-lock=false`; CI never runs `force-unlock`; the lock is held only while Terraform runs, never
during the review wait). The run-list checks prevent most conflicts before they reach the lock.
Remaining conflicts fail visibly, never silently.

This stays provisional until Task 11.3 verifies the GitHub run states used below.

### 11.3 Pre-apply checks

| # | Check | Stops with |
|---|---|---|
| P0 | Environment protection configuration of `dev-remediation` read through the API and equal to the committed expectation: required reviewers exactly the allowlist, `prevent_self_review` as decided (D5), deployment branches `main` only, administrator bypass off, no wait timer (R6, [§8.1](#81-environment-dev-remediation)); under R8, the grant script repeats this with the user's login before every grant. The remediation identity holds no write role assignment (leftover check, §10.9) | `environment_config_invalid`; `environment_config_unverified` (a stop, or a recorded warning only if E8 established that the workflow token cannot read the configuration, in which case the grant script's check is the gate); `write_roles_present` |
| P1 | (A) Environment approval valid (§8.5) | `environment_approval_invalid` |
| P2 | (B) Attestation present and valid; statement artifact digest and `S` match; `expires_at` not passed (§8.5, bindings 2–3) | `attestation_missing`, `attestation_invalid`, `statement_mismatch`, `approval_stale` |
| P3 | `main` HEAD (GitHub API) equals the statement's `commit` and `github.sha` | `revision_not_main_head` |
| P4 | No other run of `remediation-apply.yml` queued, in progress, waiting or pending (this run excluded) | `remediation_already_active` |
| P5 | No `drift-detection.yml` run and no `terraform-auth-test.yml` run on `main`/`master` (push or manual) queued or in progress. If there is one: poll every 60 s, at most 20 minutes in total for this job. Auth-test runs on pull requests are ignored: they fail at Azure login before touching state. Remediation never cancels or delays either workflow | `detection_active_timeout` |
| P6 | Azure login as the remediation identity; seal opened; `terraform init` with the locked providers; toolchain fields equal the statement (§8.5, bindings 4–5) | `seal_invalid`, `statement_mismatch` |
| P7 | Fresh plan with the plan contract, lock acquired within 120 s | `state_locked`, `plan_failed` |
| P8 | Eligibility (§7) recomputed from the fresh plan equals the statement's `eligibility`; HMAC-SHA256(`K_run`, fresh document) equals `plan_fingerprint` | `plan_refused_action`, `update_not_allowlisted`, `unmanaged_child_present`, `plan_changed_since_approval` |
| P9 | Re-check P4 and P5. If a detection or auth-test run became active: wait as in P5 (same 20-minute budget), then repeat P7–P8 | `detection_active_timeout`, codes of P7–P8 |
| P10 | Re-check P3 | `revision_not_main_head` |
| P11 | Re-check `expires_at`; then `apply_enabled` must be true, otherwise the job ends here without applying (or, with `jit_rehearsal: true`, continues to P12–P13 and ends before P14) | `approval_stale`, `apply_disabled` |
| P12 | **Just-in-time window** (§10.9, §10.10): the job logs a fixed `ready_for_jit_grant` line with the run id, attempt and `S`, then every 20 s runs the in-job security checks of §10.9 (exact assignments by principal, role definition and scope; Azure-recorded end time at most 45 minutes after start; exact effective permissions; the handshake marker), for at most 15 minutes | `jit_grant_timeout`, `jit_grant_not_confirmed`, `jit_permissions_unexpected`, `jit_window_exceeded` |
| P13 | **Final recheck** with roles present, without further waiting so the window is not extended: P3 (revision), P4 and P5 (any active conflicting run stops the run), P11 (expiry and switch); then a **new** fresh plan (P7) with eligibility and fingerprint (P8); P13 must finish within 5 minutes | `revision_not_main_head`, `remediation_already_active`, `detection_active`, `approval_stale`, `jit_window_exceeded`, codes of P7–P8 |
| P14 | Immediately before apply: the in-job security checks again, with at least 21 minutes of Azure-recorded role lifetime left, and `apply_enabled` true (a rehearsal ends here with `apply_disabled`). Then `terraform apply` of the P13 plan file of this job, step timeout 20 minutes, lock acquired within 120 s; Terraform's stale-plan check passes | `jit_grant_not_confirmed`, `jit_permissions_unexpected`, `jit_window_exceeded`, `apply_disabled`, `state_locked`, `stale_plan`, `apply_failed` |

**Residual races (U5)**:

- A detection run that starts after P13 meets the lock during P14, waits up to 120 s, and then fails
  as it does today (`unknown`, red, never "no drift"); the next scheduled run recovers.
- An auth-test run (a push to `main` or a manual dispatch) that starts after P9 fails **at once** on
  the held lock, because it sets no `-lock-timeout`; its run is red and is simply re-run later.
  A push to `main` after P13 does not change what is applied (the approved commit was HEAD at P13).
- Both windows are bounded by the apply step's timeout (20 minutes). Remediation cancels neither.

**Stuck lock**: after `cancelled_during_apply`, a remaining lock makes detection and auth-test fail
visibly until a human reviews and releases it locally (§11.4). Automation never releases it.

### 11.4 Cancellation

| When | Effect |
|---|---|
| During `plan`, or while waiting for review | Nothing changed; no lock held; the artifacts expire after 2 days |
| During P0–P11 | Nothing changed; no write role was requested |
| During P12–P13 | Nothing changed in Azure; write roles may have been granted. The job ends, and the user's procedure removes them (§10.9) |
| During P14 | Terraform may stop part-way: some changes may be applied and the state lock may remain. Code `cancelled_during_apply`. The user's procedure removes the roles as for any other end |

After `cancelled_during_apply`, recovery is manual: a read-only local plan, review of the partial
result, release of a stale lock only after confirming no Terraform process is running, and a new,
separately approved run if needed. CI never force-unlocks, retries or rolls back.

### 11.5 Failed, rejected or expired review

- Rejection (`approval_rejected`) or expiry (`approval_expired`): the `apply` job never starts;
  nothing changes. A new attempt needs a new dispatch.
- Apply failure (`apply_failed`): the post-apply plan still runs (read-only) so the record shows
  what remains. No automatic retry.

## 12. Public exposure profile

- **Published**: resource addresses and types, actions, changed paths (no values), counts, the
  statement and `S`, the keyed `F`, ciphertexts (bundle, seal) and their digests, the attestation
  and signature (in the review comment), fixed codes, exit codes, the commit, the run, and the
  review record GitHub keeps.
- **Never published**: attribute values, HCL with values, the plaintext plan, raw
  `terraform plan` / `apply` output, Azure resource IDs, subscription or tenant IDs, Azure caller
  identity, Activity Log data, role assignment IDs, `K_run`, any private key.
- Terraform and GnuPG output is written to runner-local files and never printed; on failure the
  job prints only fixed codes.
- The GitHub logins of the dispatcher and approver are visible in GitHub's own history; the
  workflow does not republish them.

### 12.1 Existing auth-test logs (R7)

**Exposure, as determined on 2026-10-12** (public GitHub API, read-only, no log content read):

| Fact | Value |
|---|---|
| `terraform-auth-test.yml` runs | 67, from 2026-10-01 to 2026-10-11: 63 successful pushes, 1 failed push, 3 pull requests that failed at Azure login |
| Runs whose log contains a printed `terraform plan` | Up to 63 (every successful push). Whether a given plan showed values depends on what changed then: "No changes" shows none; drift or pending changes (for example the Task 3.6 and Task 9B.6 probe tags, or Phase 5A) show the non-sensitive values of those changes |
| Artifacts | None (the workflow uploads none) |
| Access | Any signed-in GitHub user (public repository). Unauthenticated API download is refused (HTTP 403); the web UI's behaviour for signed-out visitors is not verified |
| Retention | Within GitHub's 90-day log retention; the oldest expire around 2026-12-30 unless deleted earlier |
| Cited as audit evidence in `PROJECT_PLAN.md` | 9 runs: #1, #2, #37, #38, #39, #40, #43, #44, #55. The PR runs (#38, #40, #44) and #1 failed before the plan; #2, #37, #39, #43 and #55 printed a plan |

**Procedure** (user actions; part of E6, item c). Nothing is deleted blindly:

1. **Classify** locally: the user downloads every auth-test log with their own GitHub login into the
   ignored `.artifacts/auth-test-logs/` (Rule 15) and a local script classifies each one by fixed
   markers only: login failure, `No changes`, or plan with changes (and, for those, whether
   drift-section or change lines with values are present). The record is run number and class,
   never content.
2. **Preserve evidence**: for the 9 cited runs, the evidence used in `PROJECT_PLAN.md` is the run
   and job conclusion and step status, which GitHub keeps after a log is deleted. The local copies
   of their logs are kept privately in `.artifacts/` as long as they are needed.
3. **Delete per run, only where confirmed** (R10 and R12, approved): a log is deleted only if the local
   classification confirms that it exposes plan values, and, for the cited evidence runs, only
   after a private local copy is retained. Deletion uses `Delete logs` in the run menu or the REST
   endpoint for deleting workflow run logs; **runs are never deleted**, so their audit records
   (run, jobs, conclusions, step status) stay. "No changes" and login-failure logs expose no values
   and are left to expire.
4. **Record** the counts per class and the deletions in `PROJECT_PLAN.md`.

**What cannot be removed, and residual exposure**:

- Copies anyone already made while the logs were readable (download, screenshot, cache) cannot be
  recalled; deletion only stops further access through GitHub.
- GitHub's own internal retention of deleted data is outside the project's control.
- Values that the configuration already declares (in the public `dev.tfvars`) were public anyway;
  the concern is drift values (for example manually added tags) and refreshed values.
- Subscription and tenant IDs are GitHub secrets and appear masked (`***`) in logs.
- Until the E6 fix lands, every new successful push run adds a new log with a printed plan.

## 13. Audit evidence (D8, retained)

| Evidence | Where |
|---|---|
| Who dispatched, when, inputs, commit | GitHub run record |
| (A): who approved or rejected, when; (B): the attestation and signature | GitHub review history |
| The approval statement | Artifact `remediation-statement-<run_id>` and the step summary |
| Remediation record: run id and attempts, `S`, `F_plan`, `F_apply`, changed paths and counts, `self_approved`, the results of P0–P14 with wait times, the final code, apply and post-apply exit codes, timestamps | Artifact `remediation-record-<run_id>` (structure-only JSON, maximum retention) and the step summary |
| Enablement evidence (E1–E11), V6 results, just-in-time grants and removals, key rotations, security events | Recorded by the user as codes in `PROJECT_PLAN.md` (no IDs) |
| Proof the drift is gone | A later valid detection run; Task 8.3 closes the issue |

GitHub keeps artifacts for at most 90 days; the bundle and seal only 2 days.

## 14. Rollback and recovery limitations

- Terraform has no transactional apply and no rollback; a failed or cancelled apply can leave some
  changes applied.
- Undoing a remediation is another remediation, with a new dispatch and approvals.
- v1 changes only tags, so an apply loses no resource data; a changed tag value must be restored by
  another change if needed.
- State-only changes (`refresh_only`) can be reversed only by restoring an earlier state blob
  version (versioning, 7-day soft delete), a manual, separately approved operation outside CI.
- The workflow cannot see or undo changes made in Azure by anything else during the run.

## 15. Decisions, open items and assumptions

### 15.1 Decision status

| ID | Decision | Status |
|---|---|---|
| **D1** | Single run with fresh-plan verification (§6) | ✅ Approved |
| **C1** | No create, delete, replace or import in v1 (§7.1, §10.6) | ✅ Approved |
| **D2** | Resource-scoped roles, isolation checks, enablement gate (§10) | ✅ Approved as a proposal; unvalidated until E1–E11 |
| **D3** | Create and update only | ✅ Approved; narrowed by C1 and U3 |
| **D4** | Encrypted bundle; per-run keyed fingerprint with an environment-gated seal; (A) and (B) validated independently and cross-bound value by value (§8, §9) | 🔁 Rechecked in rev 5; awaiting review |
| **D5** | Self-approval allowed now; future multi-reviewer requirement (§8.6) | ✅ Retained |
| **D6** | 24-hour approval expiry (§11.1) | ✅ Retained |
| **D7** | No shared concurrency group; state lock; P0–P14 (§11) | 🟡 Provisional |
| **D8** | No repository writes (§13) | ✅ Retained |
| **U1** | GnuPG from the pinned runner image (§8.2, §8.3) | 🟡 Conditional |
| **U2** | No repository secret; per-run `K_run`; environment-gated apply-job key; flow-based compromise analysis (§6.2, §9.5, §9.6) | 🔁 Threat model corrected in rev 5; awaiting review |
| **U3** | Tags only; path-level validation of changes and drift; unknowns and sensitivity changes refused; separate review for `security_rule` (§7) | 🔁 Hardened in rev 5; awaiting review |
| **U4** | Reviewer key custody (§8.7) | 🟡 Conditional |
| **U5** | Auth-test runs in P5; races (§11.3) | 🟡 Conditional |
| **U6** | Missing Activity Log evidence leaves E1 unverified (§10.8) | 🟡 Conditional |
| **R1** | Apply-job key: encrypted offline recovery copy; loss consequences and rotation procedure (§8.7) | 🔁 Revised in rev 5; awaiting review |
| **R2** | Hardware token optional for `dev` (§8.7) | ✅ Deferred (optional hardening) |
| **R3** | (B) without valid (A) recorded as a security event, without sensitive content (§8.5) | ✅ Approved |
| **R4** | Local, narrowly scoped, reversible tag apply as E1 evidence, with provider-source evidence; missing evidence leaves E1 unverified (§10.8) | 🟡 Approved conditionally |
| **R5** | No standing write roles; just-in-time grant by the user only (§10.9) | 🟡 Approved conditionally; strengthened in rev 7 (script and trusted inputs in the boundary, pending/confirmed handshake); apply disabled until E7 |
| **R6** | Environment protection configuration verified before apply (P0, E8) | 🟡 Approved conditionally |
| **R7** | Existing auth-test logs: exposure determined; classify, preserve, delete per run (§12.1) | ✅ Approved with R10 |
| **R8** | The grant script verifies the Environment configuration with the user's login before every grant and refuses if unreadable, different, changed or not matched to the run (§10.9 step 5) | ✅ Approved |
| **R9** | 15-minute propagation timeout and 45-minute role lifetime as hard limits; cleanup, interruption, disconnection and removal-failure cases (§10.10) | ✅ Approved; specified in rev 7 |
| **R10** | Per-run log deletion only after local classification and a private evidence copy; run records kept (§12.1) | ✅ Approved |
| **R11** | Azure-enforced role expiry: PIM time-bound assignments preferred; the local script is never treated as the expiry; without a verified Azure-side control apply stays disabled (§10.10, E10) | ✅ Approved; specified in rev 8 |
| **R12** | Per-run deletion of cited evidence logs after classification confirms exposed values and a private copy is kept; run records preserved (§12.1) | ✅ Approved |

### 15.2 Remaining security decisions

| ID | Question | Recommendation |
|---|---|---|
| **R13** | Only if the tenant cannot use PIM time-bound assignments (E10): approve the Azure-side cleanup watchdog design (§10.11), or keep apply disabled | **Not approved; deferred** (user, 2026-10-12): the user first verifies tenant licensing and configuration. The watchdog is a separate design for review, not implemented or provisioned; it is best-effort cleanup, not a strict expiry. Without PIM and without an approved, verified watchdog, apply stays disabled |

### 15.3 Assumptions not yet verified

Each is verified in the Task 11.2 or 11.3 step named; until then nothing relies on it.

| Assumption | Verified in |
|---|---|
| The review-history API returns state, login, environment, time and the comment of each deployment review, and is readable with `GITHUB_TOKEN` and `actions: read` | Task 11.3, before P1–P2 are relied on |
| The deployment-review comment field carries an attestation plus an armored Ed25519 signature unchanged (length, characters) | Task 11.3 (AC-3.8) |
| The run-attempt API gives the start time of the current attempt, so an approval can be bound to it | Task 11.3 (AC-3.10) |
| How GitHub reports a run waiting for review, a queued scheduled run and a pending run in the run list (P4, P5, P9) | Task 11.3 (AC-3.14, AC-3.15) |
| Environment secrets are released only to jobs referencing the environment, after its protection rules pass, and never to pull-request runs | Task 11.2 (AC-2.5) |
| The environment API returns, to the workflow token, the reviewers, `prevent_self_review`, the branch policy, the wait timer and the administrator-bypass flag (R6; the environment list is readable without authentication, verified 2026-10-12, but no environment exists yet) | Task 11.2 / E8 |
| The permissions API (`Microsoft.Authorization/permissions`) is readable by the remediation identity at each expected scope and reflects a new assignment within the 15-minute window | E7 |
| The remediation identity's Reader at the group can list role assignments at the group and below, including each assignment's `description` and `createdOn` (leftover check at P0; confirmed check at P12 and P14) | E7 |
| `az role assignment update` changes an assignment's description in place, and the change is visible to the job within the P12 window | E7 |
| The user's GitHub login can read the full `dev-remediation` protection configuration, including `updated_at`, the reviewers, `prevent_self_review`, branch policy and administrator bypass (R8) | E8 |
| The tenant has the licence (Microsoft Entra ID P2 or Entra ID Governance) and PIM onboarding to create time-bound active assignments of these custom roles to a service principal at single-resource scopes, with a 45-minute duration, through the API (R11) | E10 |
| PIM ends an assignment at its end time within a few minutes, without any client being online | E10 |
| The remediation identity can read its role-assignment schedule instances and their end times through its Reader role | E10 |
| How long RBAC takes to stop honouring a removed assignment for an already-issued token | E10 (measured in the rehearsal) |
| AzureRM 5.7.0 tag-only plans for the VNet and NSG pass the eligibility rules (no unknowns, no sensitivity change, no other changed path); the resource-group case is only preliminarily supported by a fixture recorded before the current lock | E9 |
| Signed-out visitors cannot read logs in the GitHub web UI (§12.1) | Not relied on; exposure is assumed to be any GitHub user |
| GnuPG version and default packet format on `ubuntu-24.04`; integrity-protected encryption without compression; verification reports the signature creation time | Task 11.3 (AC-3.8) |
| TruffleHog's configured scan detects an OpenPGP private key block | Task 11.3 (AC-3.12) |
| AzureRM 5.x tag-only updates give `after_unknown` without `true` values and unchanged sensitivity markings in `terraform show -json` (otherwise §7.2 refuses every tag update and the allowlist must be revisited) | Task 11.3 (AC-3.5), with real-shaped fixtures from a local plan |
| The AzureRM write path for tag updates (whole-object `PUT` or not) and the RBAC actions it needs | E1 |
| Whether the backend needs ARM read on the state account | E3 |
| Effective permissions at unmanaged scopes match the proposal | E2, E4 |
| The auth-test log fix removes plan content from public logs | E6 |

### 15.4 What is verified now, and what needs real execution

| Check | Status | Kind |
|---|---|---|
| Links, anchors, `§` references, numbering, `git diff --check`, documentation tests, leak scan of the changes | Done for this revision | Documentation only |
| Auth-test run count, outcomes, dates, artifacts, unauthenticated log access (HTTP 403), cited runs; environment list readable without authentication | Done 2026-10-12 | Read-only public GitHub API; no log content read |
| `terraform-auth-test.yml` plans against `dev.tfstate` without a lock timeout and prints the plan | Done | Reading the workflow file |
| Resource-group tag drift passes the §7.1–7.2 rules | Preliminary only | Applied by hand to a committed, sanitised real fixture recorded before the current provider lock |
| PIM licensing and behaviour, the watchdog (if R13 is approved), role-assignment end times and removal propagation | **Not verified** | Needs the user's tenant check and real Azure rehearsals (E10) |
| Everything else in §15.3: GitHub API behaviour (review history, run attempts, run states, environment fields, comment transport), GnuPG on the runner, TruffleHog detection, permissions and role-assignment APIs, AzureRM write paths, backend access, isolation (V1–V6), the auth-test fix, real-plan eligibility per address | **Not verified** | Needs real GitHub and Azure execution in Tasks 11.2–11.3 and the enablement gate (E1–E11), each user-approved |

## 16. Acceptance criteria

### Task 11.1 (this specification)

- [x] AC-1.1 Specifies manual review, environment approval gates and a fresh `terraform plan`
  verification before any apply (§4, §6, §8, §11).
- [x] AC-1.2 Specifies that `terraform apply` is blocked in the detection workflows, with RBAC as
  the hard guard and a structural test to add (§2, §4 invariant 2, AC-3.1).
- [x] AC-1.3 Includes the requirements locked on 2026-10-03: human choice of direction; revert =
  reviewed apply of `main`; accept = human-authored PR; `Refs #n`; no closing keyword; no
  auto-merge; no apply on merge; real values published only through a human-authored change (§4, §5).
- [x] AC-1.4 Specifies the proposed roles, isolation verification and the enablement gate (§10).
- [x] AC-1.5 Specifies the review material, its encrypted delivery, the statement, the two separate
  approvals with independent validation and value-by-value cross-binding, the traced key and seal
  flow and a compromise analysis derived from it, without relying on a public fingerprint for
  confidentiality (§8, §9).
- [x] AC-1.6 Specifies concurrency rules and pre-apply checks that never cancel or indefinitely hold
  detection and never apply an old or different plan (§11).
- [x] AC-1.7 Specifies the v1 eligibility rule from actual planned attribute changes, tags only,
  and the separate security review for NSG rules (§7).
- [x] AC-1.8 Records the confirmed `terraform-auth-test.yml` full-plan logging as an apply-enablement
  prerequisite (E6) with its verification method (§2, §10.8).
- [x] AC-1.9 Specifies just-in-time write roles granted only by the user, their timing, scopes,
  verification, removal, recovery and residual risk (§10.9); the Environment configuration check
  (P0, E8); and the handling of existing auth-test logs (§12.1).
- [x] AC-1.10 Treats the grant script and its trusted inputs as part of the security boundary,
  with pre-grant refusals, a positive confirmation handshake, hard time limits and every cleanup,
  interruption and disconnection case (§10.9, §10.10); requires real-plan validation of the
  eligibility per address before it is enabled (§7.3, E9); defines the verification of the
  auth-test fix including audit retention (E6); and states which checks need real execution (§15.4).
- [x] AC-1.11 Requires an Azure-enforced role expiry (PIM) or a verified Azure-side fallback before
  apply, never the local script alone; makes effective permissions and exact assignments (not the
  handshake marker) the security checks; documents the full JIT lifecycle, consistent time limits,
  cleanup-success semantics and residual risk (§10.9, §10.10, E10).
- [ ] AC-1.12 User approval of this document, including the remaining decision R13 (Task 11.1
  validation).

### Task 11.2 (environment, keys, identity and read-only permissions)

- AC-2.1 Environment `dev-remediation`: the owner as required reviewer, Prevent self-review off
  (D5), deployment branches `main` only, no wait timer, administrator bypass off, only the
  apply-job private key and the client ID as environment secret and value; verified through the
  GitHub API and recorded, including which of these fields the workflow token can read (E8 input).
- AC-2.2 Remediation identity: only the environment-bound federated credential; no secret,
  certificate, group, directory role or Graph permission.
- AC-2.3 Reviewer and apply-job public keys committed with pinned fingerprints and the reviewer
  allowlist (login → signing and encryption key fingerprints); no repository secret for
  remediation; no private key in GitHub or the repository (§8.7 checks).
- AC-2.4 The identity holds the Stage A read roles only; V1–V3 pass for that set; no write role,
  no role assignment it could change, and no `Microsoft.Authorization/*` write action.
- AC-2.5 A job without `environment: dev-remediation` cannot obtain a token for the remediation
  identity and receives no environment secret (negative tests).
- AC-2.6 The `remediation-apply.yml` skeleton (Task 11.2 file) pauses before its environment job
  until the reviewer acts, and that job contains no Terraform write command.

### Task 11.3 (apply workflow): tests or a recorded real run for each

Structure and boundaries:

- AC-3.1 A repository-wide structural test: no workflow other than `remediation-apply.yml`
  contains `terraform apply`, `import`, writing `state` subcommands, `force-unlock` or `taint`, an
  `environment:` key, or a write permission beyond the existing `issues: write` of the drift issues
  job.
- AC-3.2 `remediation-apply.yml`: only `workflow_dispatch`; requires `main`; `runs-on:
  ubuntu-24.04`; validates every input; permissions exactly `contents: read`, `actions: read` and
  job-level `id-token: write`; no repository write (D8); no `concurrency` key; no repository secret;
  every action pinned by commit SHA; no role-assignment, role-definition or federated-credential
  command in any workflow (invariant 19); `drift-detection.yml` unchanged.
- AC-3.3 The plan contract matches invariant 9 (executed-step tests with a fake `terraform`).

Eligibility (C1, U3):

- AC-3.4 Each refused shape (`create`, `delete`, both replace orders, `forget`, a data-source
  `read`, `importing`, `previous_address`, `deposed`, `action_reason`, non-empty `replace_paths`, a
  refresh-only `delete`, a non-`no-op` output change) stops with `plan_refused_action` in the `plan`
  job and again in P8.
- AC-3.5 Path-level checks with real-shaped AzureRM 5.x plans: a tag change on each allowlisted
  address passes, in both modes; `update_not_allowlisted` for an NSG `security_rule` change, a VNet
  `address_space` change, a subnet change, a change outside `tags` on an `update` entry, a
  `resource_drift` entry outside `tags` in mode `plan` (state-only drift), a `true` anywhere in
  `after_unknown` (including outside `tags`), a sensitivity change, a sensitive tag path, a
  non-string tag value, a reserved or special tag key prefix, and type-only differences (`"1"` vs
  `1`, `null` vs absent). The eligibility result lists exactly the changed paths, without values.
- AC-3.6 `unmanaged_child_present` for a VNet tag update while the refreshed VNet lists an unmanaged
  subnet; without one, it passes.

Review, keys and binding (D4, U1, U2, U4):

- AC-3.7 Fingerprint unit tests: pinned values on fixtures with a test `K_run`; deterministic;
  changes when any §9.2 field or the key changes; unchanged by excluded fields and key order;
  numbers keep their lexical form; absent differs from `null`.
- AC-3.8 Tested reviewer procedure (§8.3) with test keys in CI: the `ubuntu-24.04` GnuPG version is
  in the allowed set; the bundle and seal have the §8.2 packet format (integrity-protected, no
  compression, no signature); the documented download, digest, decrypt, verify and attest steps
  succeed end to end; an unprotected or tampered ciphertext fails; no plaintext or `K_run` is
  uploaded or printed; the attestation survives the review-comment transport unchanged.
- AC-3.9 The same `drift_engine` code computes the document, `F`, eligibility, `S` and the
  attestation document in both jobs and in the reviewer helper; all paths agree on one fixture.
- AC-3.10 Binding (fake review history, run and attempt APIs, artifacts and clock), one test per
  row of the §8.5 cross-binding table and per missing value: missing, rejected, rejected-after,
  unlisted-login, before-plan, before-attempt and after-expiry Environment approvals give
  `environment_approval_invalid`; a missing attestation gives `attestation_missing`; a bad
  signature, an unlisted, expired or revoked key, a key mapped to another login, a signature time
  outside the window, and an attestation whose run, plan attempt, apply attempt, commit,
  fingerprint, bundle digest, seal digest, expiry or `S` differs give `attestation_invalid` or
  `statement_mismatch`; a tampered statement, another run's statement or a toolchain, lock-file,
  var-file, GnuPG, key-fingerprint or artifact-digest difference gives `statement_mismatch`; a seal
  that is not this run's artifact or does not open gives `seal_invalid`. A valid (B) with an invalid
  or missing (A) also records the R3 security event, which contains only the run id, attempt,
  public key fingerprint and `S`.
- AC-3.11 `plan_changed_since_approval` when the fresh eligibility or `F` differs, with no apply
  call.
- AC-3.12 Key checks: committed key files are public-only and match their pins; no workflow
  references a reviewer private key; the scan detects a test OpenPGP private key block.

Freshness and concurrency (D6, D7, U5):

- AC-3.13 `approval_stale` after `expires_at`, at P2, P11 and P13 (fake clock); a re-run of the `apply`
  job needs a new (A) and (B) for the new attempt and is refused after `expires_at`.
- AC-3.14 `revision_not_main_head` at P3, P10 and P13; `remediation_already_active` for another
  remediation run that is queued, in progress, waiting or pending; no run is ever cancelled.
- AC-3.15 P5/P9 with fake run lists: an active detection run or a push-triggered auth-test run on
  `main` causes a wait and then proceeds, or stops with `detection_active_timeout` after 20 minutes
  in total; a pull-request auth-test run is ignored; a run that becomes active between P5 and P9
  causes a wait and a new P7–P8; nothing is cancelled.
- AC-3.16 `state_locked` on a lock error at P7, P13 or P14; no `force-unlock`. `stale_plan` when
  Terraform refuses the saved plan; no other plan is applied.
- AC-3.17 Cancellation during P14 yields `cancelled_during_apply` in the record; cancellation during
  P12–P13 changes nothing in Azure and is recorded.
- AC-3.18 While `apply_enabled` is false, the `apply` job runs P0–P11 (P0–P13 with `jit_rehearsal`)
  and stops with
  `apply_disabled`; `terraform apply` is never invoked.

Exposure and evidence:

- AC-3.19 No value, plaintext plan, raw Terraform or GnuPG output, Azure ID, `K_run` or private key
  is printed or uploaded (sentinel values); the statement and record have the §8.4 and §13 fields,
  exactly one final code, and pass a leak scan that includes private-key markers.

Just-in-time roles and Environment configuration (R5, R6):

- AC-3.22 P12 and the pre-P14 check with fake role-assignment, schedule and permissions APIs:
  proceed only when the assignments are exactly the expected set by principal, role-definition ID
  and exact scope, each with an Azure-recorded end time at most 45 minutes after its start (and at
  least 21 minutes away before P14), the effective permissions are exactly the expected actions at
  exactly the expected scopes, and the marker reads `confirmed` for this run, attempt and `S`.
  Refused, each without apply: an assignment without an end time (permanent) when the committed
  policy does not record the approved fallback (R13); an end time too late
  or too close; an extra assignment or role, a wider or different scope, another principal's
  assignment counted as the identity's; extra effective actions; a `confirmed` marker on an
  otherwise wrong assignment set (the marker alone never passes); `pending` or missing markers;
  15 minutes without a valid grant (`jit_grant_timeout`); P13 over 5 minutes.
- AC-3.23 P13: with roles present, a newly active detection or auth-test run, a moved `main`, an
  expired approval or a changed plan each stop the run without waiting and without apply.
- AC-3.24 Grant script pre-grant refusals (fake `az` and `gh`), one test each: wrong GitHub login
  or Azure tenant/account; a local modification or another commit in the script's clone; another
  run, attempt, commit, workflow path or `S` than attested; the job not at P12; a trusted-digest
  mismatch in any covered file (workflow, scripts, modules, constraints, action pins, allowlists,
  key pins, expected configuration, `apply_enabled`, the script itself); a missing, late or
  unlisted (A); an invalid (B); an unreadable, different or recently updated Environment
  configuration; any unexpected existing assignment for the identity or of a custom remediation
  role; an address whose entry is not enabled; `expires_at` within 45 minutes. In every case: no
  assignment is created. With all checks passing, only the per-run least-privilege set is granted,
  first `pending`, then `confirmed`; scope IDs are never printed.
- AC-3.25 Leftover detection: an existing write assignment stops the `plan` job and P0 with
  `write_roles_present`.
- AC-3.26 P0 with a fake environment API: each changed setting (reviewers, self-review, branches,
  wait timer, administrator bypass) gives `environment_config_invalid`; an unreadable or incomplete
  response gives `environment_config_unverified` and a stop, or only a recorded warning when the
  committed policy records (from E8) that the workflow token cannot read it.
- AC-3.27 Grant script post-grant failures: an extra or missing assignment after the grant, or a
  configuration change between the checks, makes the script remove what it created and never write
  `confirmed`; a test job in P12 never proceeds.
- AC-3.28 Grant script cleanup (fake `az`, `gh` and clock): removal and a clean V2 after the job
  succeeds, fails, is cancelled or times out; removal at the 45-minute limit while the job still
  runs; removal on `SIGINT` and `SIGTERM`; after a simulated `SIGKILL` the next start removes the
  unfinished grant from the local state file before anything else; a failing removal retries for 5
  minutes, then prints the §10.10 emergency procedure and exits non-zero; the script exits 0 only
  when V2 shows no write assignment and no active PIM schedule instance, and keeps its state entry
  otherwise; the state file holds only what removal needs and stays in the user's ignored local
  directory.
- AC-3.29 Interruption never permits an apply after a failed verification: in combined tests (fake
  job and fake script), every interruption or failure before `confirmed` ends the job without an
  apply call; removal of confirmed roles before the pre-P14 check also ends it without an apply.
- AC-3.30 Eligibility validator on the committed real fixtures: `external_drift` (resource-group
  tag drift) passes in mode `plan`, and its drift entry passes the `refresh_only` rules; `converged_drift`
  passes in mode `refresh_only`; `replace`, `config_change`, `resource_added`, `resource_removed`,
  `external_deletion` and `drift_and_config_change` are refused with the expected code. This
  supports, but does not replace, E9.
- AC-3.31 Expiry control: the grant script only ever creates time-bound assignments (PIM schedule
  requests with an end time 45 minutes after start), never a plain role assignment, unless the
  committed policy records the approved fallback (R13); the job refuses any assignment whose end
  time it cannot read. The watchdog's tests (§10.11) apply only if R13 is approved later.

Enablement (§10.8, in this order, each user-approved; `apply_enabled` stays false until the last
step):

- AC-3.E1 Stage A (E3): the reviewer runs the full §8.3 procedure with the real key on a probe-tag
  `revert` run; the `apply` job passes P0–P11 with the read-only identity and stops with
  `apply_disabled`; the probe tag is removed afterwards.
- AC-3.E2 E1: provider-source references and Activity Log records, the latter from separately
  approved, one-resource, reversible probe-tag applies that were reverted and confirmed in sync,
  are recorded and agree for every allowlisted update; any gap leaves E1 unverified and enablement
  blocked; the role proposal is amended where the evidence differs.
- AC-3.E3 Stage B (E2, E4): write roles granted through the §10.9 procedure exactly as amended, only
  for the checks;
  V2–V5 pass for every unmanaged resource present and the three probe types; the probes are removed
  and their removal is confirmed by a detection run's unmanaged inventory.
- AC-3.E4 E6: the auth-test log fix (a separate, approved change) passes its structural and
  executed-step tests, keeps the audit lines (version, exit code, counts, fixed failure code), and
  passes the real sentinel check (§10.8, E6 items a–d); the existing logs are classified and handled
  as in §12.1 (R7, R10).
- AC-3.E5 E7: the grant script's and the job's tests pass (AC-3.22–AC-3.29), and two real
  rehearsals (`jit_rehearsal: true`, `apply_enabled: false`) succeed: one complete (grant, confirmed
  handshake, the job's checks, the P13 re-plan, the stop before P14, removal and a clean V2), and one
  in which the user interrupts the script after the grant and restarts it, which must remove the
  roles before anything else.
- AC-3.E6 E8: a real P0 run and a real grant-script run read the configured environment; the result
  (whether the workflow token can read it) is recorded in the committed policy; changed settings
  are detected in tests.
- AC-3.E7 E9: for each address to be enabled, a fresh, user-approved real tag-drift plan with the
  pinned versions passes the validator in both modes, and a real non-tag change on that address is
  refused; only then is its `enabled` flag set in a reviewed commit. Addresses without evidence stay
  disabled.
- AC-3.E8 E10: the role expiry control is verified as in §10.8 (PIM rehearsal with the script
  disconnected, or, after R13 is approved, the watchdog rehearsal); otherwise apply stays disabled.
- AC-3.E9 E5 and E11: the acceptance tests pass on the commit that sets `apply_enabled: true`, every
  E1–E10 item is recorded as verified, and the user approves that commit. Until then
  `apply_enabled` stays `false`.

Real runs (after enablement, user-approved, Execution Rules 10 and 13):

- AC-3.20 Confirmation of E1: one allowlisted tag update per managed resource, one per run, each
  with a just-in-time grant and removal and `applied_clean`, with the reviewer following §8.3; V6
  recorded; the operations performed match the E1 evidence.
- AC-3.21 End to end: a reversible probe-tag drift is detected, a revert run is reviewed, approved
  (A), attested (B) and applied, and a later detection run lets Task 8.3 close the issue. Plus one
  rejected run that changes nothing, one run with (A) but no (B) that stops with
  `attestation_missing`, and one run that stops with `plan_changed_since_approval` after a
  deliberate probe-tag change between the `plan` job and the `apply` job.

## 17. Non-goals

- Implementing any workflow, environment, secret, key, identity, role or credential in Task 11.1.
- Automatic or scheduled remediation, auto-merge, bot-generated PRs or LLM-generated patches.
- Remediation of unmanaged resources, resource-group recreation, or anything in the bootstrap
  module or state storage.
- Any change of Azure permissions, federated credentials or GitHub settings by a workflow
  (invariant 19); standing write roles (R5).
- Creating, deleting, replacing or importing resources (C1); any update beyond tags in v1,
  including NSG security rules until the §7.4 review.
- `terraform state rm`, `mv`, `import`, `force-unlock`, `taint`, `-target` or `-replace` in CI.
- A production environment.
- Automatic rollback, automatic retries, or restoring state versions from CI.
- Changes to `drift-detection.yml` or `terraform-auth-test.yml` within Task 11.1. The auth-test
  log fix is a separate, approved change (Phase 12 or a dedicated task), but it is an
  apply-enablement **prerequisite** (E6): apply cannot be enabled without it.
- Branch protection changes and long-term audit export.
- Dashboard work (Phase 13).

## 18. Open risks

- **Single maintainer** (D5): (A) and (B) come from the same person.
- **Unvalidated permissions** (D2): apply stays disabled until E1–E11 pass.
- **Just-in-time window** (R5): while roles are granted, any code in that `apply` job can use them
  within the granted scope; the trusted-code check does not cover the runner image or unpinned
  run-time downloads (§10.9).
- **Root of trust**: the user's machine and Azure credentials, the grant script's clone and the
  user's trusted record (§9.6).
- **No Azure-enforced role expiry** (R11): after a disconnection, roles stay until removed by hand
  (§10.10).
- **Write identity**: the NSG write action could carry rule changes; eligibility refuses them, and
  the residual `PUT` race is described in §10.4.
- **Whole-plan apply**: a revert applies every pending change of `main`; one ineligible change
  blocks the run.
- **Keys** (§9.6): a leaked reviewer private key discloses all values, including sensitive ones,
  in every review bundle the attacker has collected, and allows (B), but not (A); a leaked
  apply-job key allows guess-testing of values in every run whose seal the attacker has collected;
  a leaked `K_run` allows guess-testing for that run. Retention does not bound what an attacker
  collected while the artifacts were public.
- **GitHub account compromise** (§9.6): with standing write roles, it allows applying within the
  RBAC scope through modified workflow code, bypassing (B) and the allowlist (R5).
- **Lock contention**: detection or auth-test runs that start after P13 can fail red (§11.3).
- **Unverified GitHub and tool behaviour**: §15.3.
- **Accept disclosure**: a merged value cannot be removed from public history.

## 19. References

- `PROJECT_PLAN.md`: Phase 11 (Tasks 11.1–11.3); Task 8.2 design review (F1–F7, option R1);
  Task 6.6 (option kinds, `plan_default`); Phase 9B recommendation policy v1 and G8 settling
  margin; Task 9.3 TruffleHog; Task 10.4 unmanaged inventory; Execution Rules.
- [`drift-detection-spec.md`](drift-detection-spec.md): §4 plan contract, §6.3 limitations, §10 AI
  boundary.
- [`architecture.md`](architecture.md): §4 RBAC, OIDC and CI access.
- `.github/workflows/terraform-auth-test.yml`, `drift-detection.yml`: the current state users.
- `terraform/environments/dev`, `terraform/modules/`: the managed resources.
- `src/ai_engine/nodes/remediation.py`: option kinds and the command catalogue.
