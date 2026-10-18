# AI-Powered Terraform Drift Detection & Remediation Platform — Master Project Plan

> **SINGLE SOURCE OF TRUTH**: This document is the authoritative roadmap, progress tracker, and specification for the AI-Powered Terraform Drift Detection & Remediation Platform. All development workflows and task executions must be driven directly from this plan.

---

## 📌 Status System & Rules

Every task in this plan must have exactly one status from the following lifecycle:

- ⬜ **NOT STARTED**: Task is queued and pending work.
- 🔵 **STARTED**: Work has officially begun on the task.
- 🟡 **WORK IN PROGRESS**: Active implementation work is underway.
- 🟢 **COMPLETED**: Implementation finished, all acceptance criteria met, and validation passed.
- 🔴 **BLOCKED**: Progress halted due to external dependency or unfulfilled prerequisite.

### Execution Rules
1. **Single Source of Truth**: Before starting any task, read this file to identify the active phase and first incomplete task.
2. **Immediate Status Transition**: The moment work starts on a task, update its status from ⬜ **NOT STARTED** → 🔵 **STARTED**, then 🟡 **WORK IN PROGRESS**.
3. **Validation Required**: Do not mark a task 🟢 **COMPLETED** until code is implemented and empirical validation/testing succeeds.
4. **Non-Destructive Operations Only**: Automated execution must never perform destructive infrastructure operations without explicit user approval.
5. **Resume-First Execution**:
   Always resume from the `Current Active Task` in this file.
   Do not rediscover project progress from the repository.

6. **Minimal Context Loading**:
   Read only:
   - this PROJECT_PLAN.md,
   - files listed under the current task's `Files/Areas`,
   - and files directly required by its dependencies.

   Do not scan the entire repository unless the current task cannot
   be completed without doing so.

7. **Completed Task Protection**:
   Do not re-execute, revalidate, or re-analyze completed tasks unless
   the current task explicitly depends on their implementation details
   or evidence shows they are broken.

8. **One Task at a Time**:
   Work only on the Current Active Task.
   Do not begin the next task automatically.

9. **Progress Persistence**:
   Before implementation, update the current task status.
   After successful validation, mark it COMPLETED, record concise
   completion notes, and update `Current Active Task` to the next
   eligible incomplete task.

10. **Human Action Boundary**:
    If the task requires Azure login, terraform apply, GitHub settings,
    credentials, approval, or another user-controlled action, stop and
    request that action rather than proceeding automatically.

11. **Trust Recorded Progress**:
    Trust completed task records in this file. Do not rescan the entire
    repository to rediscover project progress; verify a completed task
    only when the current task specifically requires it.

12. **No Scope Expansion**:
    Do not expand scope without explicit approval.
    Do not introduce additional Azure resources, services, or frameworks
    unless they are required by the current task.

13. **Consequential Operations Require Approval**:
    Never execute consequential external operations — `terraform apply`,
    destructive Azure operations, credential changes, or GitHub
    configuration changes — without explicit user approval.

14. **Stop on Incorrect Plans**:
    If a planned implementation is technically incorrect, unnecessary,
    insecure, or inconsistent with actual Terraform/Azure behavior, stop
    and explain the issue instead of blindly implementing it.

15. **Project-Local Artifact Handling**:
    - Any downloaded GitHub Actions artifacts, reports, logs, test
      outputs, or other validation files that need to be inspected
      locally must be downloaded/extracted inside the project workspace,
      preferably under the ignored `.artifacts/` directory
      (e.g. `.artifacts/<artifact-name>/`).
    - Do not use the user's general `~/Downloads` folder for project
      validation artifacts.
    - `.artifacts/` must stay gitignored so downloaded/generated
      validation artifacts cannot be accidentally committed.
    - Do not overwrite source files or tracked project files with
      downloaded artifacts.
    - Temporary files may still use system temporary locations when
      technically required, but the final locally retained
      artifact/report used for inspection must be kept inside the
      project workspace.
    - This rule applies to all future tasks unless a task explicitly
      requires a different location.

16. **Filesystem Access Boundary (strict security rule)**:
    - Normal project work is restricted to the project directory
      `~/Developer/DevOps/Project/AI-Terraform-Drift-Detector`.
    - Temporary validation/scratch work uses only the **current**
      Claude session's scratchpad (not scratchpads of earlier sessions).
    - Never run home-directory-wide searches (e.g. `find ~`) or
      recursive scans of `~/Desktop`, `~/Documents`, `~/Downloads`,
      `~/Music` or similar personal folders.
    - To locate a tool or dependency, search the project and the current
      session scratchpad first; if it is not there, install it into the
      current scratchpad or ask the user. Never scan the home directory.
    - Do not access files or directories outside the project unless the
      user explicitly asks. If a task genuinely requires outside access,
      STOP and ask the user before accessing it.
    - Do not request additional macOS filesystem permissions unless they
      are genuinely required, and explain why before requesting them.
      Do not use Full Disk Access for this project.
    - This rule applies to all future tasks and takes precedence over
      convenience (e.g. reusing tools found elsewhere on the machine).

### Core Project Principles
- **Deterministic source of truth**: Terraform/Azure deterministic tooling is the source of truth for drift. AI interprets, classifies, explains, and recommends; AI is NOT the source of truth for detecting drift.
- **Evidence vs inference**: AI must distinguish evidence from inference, and must not hallucinate who changed infrastructure.
- **LLM-independent detection**: Drift detection must work even when the LLM is unavailable.
- **No autonomous apply**: AI must never directly execute destructive `terraform apply`. Remediation requires human approval.
- **Security gates**: Security scan failures should fail the relevant CI/CD pipeline.
- **Drift is a valid result**: "Drift detected" is a valid detection result and does not by itself mean the detection pipeline failed. Detection/process errors should fail appropriately. The binding CI result policy for `drift-detection.yml` is Phase 9B **G18** (user-approved 2026-10-09).
- **Real data only**: The final dashboard must use real project data/artifacts; no mock or fake metrics.

---

## 📊 Master Project Overview

- **Current Active Phase**: none. Level 1 was released as the stable baseline on 2026-10-18: tag `level1-v1.0.0` (annotated tag `fe07743` → commit `daa95f8`, the merge of PR #14 after PR #13), with CI green on `main`. Further development happens in the separate Level 2 repository (see **Level 2** below). Phase 13 stays 🟡: Tasks 13.1 and 13.2 are 🟢; Tasks 13.3–13.5 are implemented, merged and tested by the user, with the open validation items listed under each task. Phase 12 stays 🟡: all its tasks are 🟢 (Task 12.1A 2026-10-14; Tasks 12.1, 12.2 and 12.3 2026-10-16), but the scope deferred into it is still open (see Phase 12). Phase 11 is on hold (user decision 2026-10-13; see below). Phase 14 has not started.
- **Current Active Task**: none in Level 1. Not scheduled, and done only if the owner reopens them: Task 13.3's browser check of the GitHub issue column and panel on the issue snapshot; Task 13.5's real-Chrome check that no password-save prompt appears for the GitHub token, and a recorded check of the current implementation against real GitHub (good, invalid and Issues-less tokens). Last completed: Task 13.2 — UI Component Development & Visual Analytics and Task 13.1 — Dashboard Data API & State Engine (both 🟢 2026-10-17; branch `phase-13-dashboard`, commits `b6aaa4f` and `ad3cde1`, merged to `main` through PR #10).
- **On hold**: Phase 11 — Human-Approved Remediation (🔴 BLOCKED — on hold, user decision 2026-10-13): intentionally deferred while Phase 12 testing and security hardening are prioritized; no Phase 12 task depends on it. It resumes at Task 11.1 on user instruction. Task 11.1 — Safe Remediation Architecture & Controls stays 🟡 WORK IN PROGRESS (since 2026-10-11; dependency Task 8.3 🟢), paused. Documentation only: `docs/remediation-safeguards.md` revision 9 awaits user review, with the remaining security decision R13 (not approved; deferred until the user's PIM licensing check), unverified assumptions and a verification-status matrix in its §15; `apply_enabled` stays `false` until every enablement gate (E1–E11, including the auth-test log fix E6, the just-in-time role procedure E7, the Environment configuration check E8, real-plan eligibility validation E9 and an Azure-side role expiry control E10) is verified and approved; not complete until the user approves it. No apply, Azure write, GitHub environment or RBAC change is part of it (Tasks 11.2–11.3 need separate user approval, Execution Rules 10 and 13).
- **Last completed**: Phase 10 — FinOps / Cost Analysis (🟢 2026-10-11). Tasks 10.3 and 10.4 were verified together by the user-approved drift-detection dispatch #44 `38140497702` on commit `8ef89b6` and its AI analysis run #27 `38140599354` (see the Task 10.3 and 10.4 completion notes). Phase 9B was completed on 2026-10-11 by Task 9B.6: real Azure cycle 2 on commit `4d89c94` (R1 in-sync anchor #37 `38104177960`, primary R2 #38 `38105671846`, Control A R3 #39 `38109121618`, Control B R4 #40 `38111406531`); see the Task 9B.6 completion notes.
- **Phases Completed**: 10 of 14 (Phases 1–10). Phases 6 and 7, reopened on 2026-10-04 after a requirement gap found in a real Azure test, returned to 🟢 on 2026-10-11 when Task 9B.6 passed (see Phase 9B). Lettered phases (5A, 9A, 9B) are not counted.
- **Level 2 (separate codebase, 2026-10-18)**: a more user-friendly, local-first application is developed in the separate private repository `HarshAgarwal1102/ai-terraform-drift-detector-v2` (package `aitdd-drift`, command `aitdd`), with its own plan, dependencies, CI and releases. It copied only the nine drift-engine modules and the public report schema from `level1-v1.0.0`, with recorded provenance and compatibility tests, and never installs or imports Level 1. Its plan is kept there, not in this file, and this repository is not changed for Level 2. Level 2 Milestone 1 (package skeleton, copied engine, compatibility tests) was merged there on 2026-10-18 (PR #1).

---

## 🗺️ Detailed Roadmap & Task Breakdown

---

### PHASE 1 — Minimal Terraform Foundation
**Status**: 🟢 COMPLETED

> **SCOPE REVISION NOTE (2026-09-30)**:
>
> Phase 1 is intentionally limited to the minimum infrastructure required
> to establish and validate the Terraform foundation for the drift detection
> platform.
>
> **Active Azure infrastructure:**
> - Azure Resource Group only: `aitdd-dev-main-rg`
> - Location: `Central India`
>
> **Current Phase 1 infrastructure scope:**
> - Resource Group only
>
> **Current Terraform modules:**
> - `terraform/modules/resource-group` only
>
> VNet, Subnet, NSG, application Storage Account, and Key Vault are
> not part of the current codebase, modules, or active infrastructure
> scope.
>
> These resources may be introduced later as part of a dedicated
> infrastructure expansion phase after the core drift detection workflow
> has been validated.
>
> The initial MVP must prove the complete drift lifecycle using the
> smallest practical Terraform-managed infrastructure footprint.
> Deterministic drift detection and AI analysis remain the core objective.

Phase 1 establishes the minimum Terraform foundation required for the
platform MVP.

The initial infrastructure intentionally contains only one managed Azure
Resource Group. The purpose is to validate Terraform structure, state
management, authentication, and eventually deterministic drift detection
without introducing unnecessary infrastructure complexity.

#### Task 1.1 — Resource Group Terraform Module
- **Status**: 🟢 COMPLETED
- **Completed**: 2026-09-28
- **Objective**: Create a modular Terraform module for Azure Resource Groups supporting dynamic tag merging and region parameters.
- **Dependencies**: None
- **Files/Areas**: `terraform/modules/resource-group/`
- **Acceptance Criteria**:
  - [x] Module defines `azurerm_resource_group` resource using standard input variables.
  - [x] Supports variable tags and default tag merging.
  - [x] Outputs Resource Group ID, Name, and Location.
- **Validation**:
  - [x] `terraform -chdir=terraform/modules/resource-group init`
  - [x] `terraform -chdir=terraform/modules/resource-group validate`
- **Completion Notes**:
  - Implemented modular RG definition with `main.tf`, `variables.tf`, `outputs.tf`.

#### Task 1.2 — Data-driven for_each Architecture Pattern
- **Status**: 🟢 COMPLETED
- **Completed**: 2026-09-28
- **Objective**: Standardize variable definitions across environment root modules to use `map(object(...))` schemas for scalability.
- **Dependencies**: Task 1.1
- **Files/Areas**: `terraform/environments/dev/variables.tf`, `main.tf`
- **Acceptance Criteria**:
  - [x] Environment root module accepts a map of objects for Resource Groups.
  - [x] Root module passes map structures into module instances using `for_each`.
- **Validation**:
  - [x] `terraform -chdir=terraform/environments/dev validate`
- **Completion Notes**:
  - Refactored `dev` environment to consume map variables for declarative infrastructure provisioning.

#### Task 1.3 — Dev Environment Infrastructure Configuration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-28
- **Completed**: 2026-09-29
- **Objective**: Configure dev environment with minimal, clean Terraform foundation (Azure Resource Group `aitdd-dev-main-rg`) in Central India.
- **Dependencies**: Task 1.2
- **Files/Areas**: `terraform/environments/dev/`
- **Acceptance Criteria**:
  - [x] Simplify `terraform/environments/dev/main.tf` to activate `Azure Resource Group` as the minimal infrastructure foundation.
  - [x] Streamline `outputs.tf` and `dev.tfvars` for the single Resource Group baseline in `Central India`.
  - [x] Local validation via `./scripts/validate.sh` passes cleanly with zero errors.
- **Validation**:
  - [x] `terraform -chdir=terraform/environments/dev init -backend=false`
  - [x] `terraform -chdir=terraform/environments/dev validate`
- **Implementation Notes**:
  - Scope revised on 2026-09-29 to maintain the smallest practical infrastructure footprint (Resource Group) for drift detection MVP.
- **Completion Notes**:
  - Dev environment simplified to manage Azure Resource Group (`aitdd-dev-main-rg`) in `Central India` as the only application infrastructure resource. Offline validation passed cleanly.

#### Task 1.4 — Automated Local Validation Script
- **Status**: 🟢 COMPLETED
- **Completed**: 2026-09-28
- **Objective**: Implement a shell script `scripts/validate.sh` to validate Terraform syntax and formatting across all modules without requiring Azure login.
- **Dependencies**: Task 1.3
- **Files/Areas**: `scripts/validate.sh`
- **Acceptance Criteria**:
  - [x] Script checks recursive formatting (`terraform fmt -check`).
  - [x] Script validates bootstrap and dev environment configurations offline (`init -backend=false`).
  - [x] Script exits cleanly with status 0 on success.
- **Validation**:
  - [x] `./scripts/validate.sh` executes successfully.
- **Completion Notes**:
  - Created executable script `./scripts/validate.sh` for offline verification.

#### Task 1.5 — Phase 1 Documentation and Architecture
- **Status**: 🟢 COMPLETED
- **Completed**: 2026-09-28
- **Objective**: Create project README and architecture documentation detailing modular design, naming conventions, and directory structures.
- **Dependencies**: Task 1.4
- **Files/Areas**: `README.md`, `docs/architecture.md`
- **Acceptance Criteria**:
  - [x] README includes overview, architecture diagram, tech stack, and module structure.
  - [x] `docs/architecture.md` documents design principles, state management strategy, and security model.
- **Validation**:
  - [x] Markdown files verified for clarity and formatting.
- **Completion Notes**:
  - Published initial architecture guide and README. Updated on 2026-09-29 to document the minimal Resource Group foundation in `Central India` and the deferred infrastructure-expansion model.

---

### PHASE 2 — Remote State & Secure Azure Authentication
**Status**: 🟢 COMPLETED

Phase 2 provisions dedicated remote state storage (`aitdd-tfstate-rg`, `aitddtfstatesa001`, `tfstate`), configures remote state backend for the `dev` environment, establishes OIDC Workload Identity authentication for GitHub Actions, and documents RBAC security controls.

**Architecture (two separate Terraform configurations):**
1. `terraform/bootstrap` → creates the dedicated Terraform state infrastructure (`aitdd-tfstate-rg`, `aitddtfstatesa001`, `tfstate`) using local state.
2. `terraform/environments/dev` → uses the AzureRM remote backend hosted by that state infrastructure.

The application Resource Group `aitdd-dev-main-rg` is managed by `terraform/environments/dev` and is separate from the Terraform state bootstrap infrastructure.

#### Task 2.1 — Bootstrap Backend Validation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-28
- **Completed**: 2026-09-28
- **Objective**: Validate `terraform/bootstrap` configuration and syntax offline to ensure bootstrap module readiness.
- **Dependencies**: Task 1.4
- **Files/Areas**: `terraform/bootstrap/`
- **Acceptance Criteria**:
  - [x] `terraform/bootstrap` contains valid configuration for resource group, storage account, and blob container.
  - [x] Offline `terraform init` and `validate` pass with zero errors.
- **Validation**:
  - [x] `./scripts/validate.sh` passes cleanly.
- **Implementation Notes**:
  - Executed `./scripts/validate.sh` which runs `terraform fmt -check -recursive`, `terraform init -backend=false`, and `terraform validate` on `terraform/bootstrap`.
- **Completion Notes**:
  - Offline bootstrap validation passed cleanly with zero syntax or provider initialization errors. Bootstrap module is verified ready for deployment.

#### Task 2.2 — Deploy Dedicated Terraform State Infrastructure
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-30
- **Completed**: 2026-09-30
- **Objective**: Manually or via CLI authenticate to Azure and deploy `terraform/bootstrap` to create state RG, storage account, and container.
- **Dependencies**: Task 2.1
- **Files/Areas**: `terraform/bootstrap/`
- **Acceptance Criteria**:
  - [x] Azure CLI authentication confirmed (`az login`).
  - [x] `terraform apply` in `terraform/bootstrap` completes successfully.
  - [x] Storage Account `aitddtfstatesa001` and container `tfstate` exist in Azure.
- **Validation**:
  - [x] `az storage container show --name tfstate --account-name aitddtfstatesa001`
- **Implementation Notes**:
  - Manual deployment task. State stored locally in bootstrap folder.
  - Project deployment region updated from `East US 2` to `Central India` across bootstrap and dev configurations prior to initial cloud deployment.
  - 2026-09-30: `az account show` initially returned "No subscription found"; resolved after user authenticated.
  - 2026-09-30: Azure CLI authenticated to subscription `Azure subscription 1` (`<AZURE_SUBSCRIPTION_ID>`). `ARM_SUBSCRIPTION_ID` exported from `az account show` for Terraform.
  - 2026-09-30: `terraform init` succeeded (azurerm v5.7.0 from lock file). `terraform plan -detailed-exitcode` returned exit code 2 with **3 to add, 0 to change, 0 to destroy** — `aitdd-tfstate-rg`, `aitddtfstatesa001`, and container `tfstate`, all in `centralindia`. No unexpected resources.
  - 2026-09-30: Corrected stale backend key in the `backend_config_instructions` output of `terraform/bootstrap/outputs.tf` from `environments/dev/terraform.tfstate` to `dev.tfstate`, matching `terraform/environments/dev/backend.tf` and Tasks 2.3/2.4. `fmt`, `validate`, and re-plan all clean (still 3 to add, 0 to change, 0 to destroy).
  - 2026-09-30: `terraform apply` executed after explicit user approval. Result: **3 added, 0 changed, 0 destroyed**.
- **Completion Notes**:
  - Terraform remote state infrastructure deployed to subscription `<AZURE_SUBSCRIPTION_ID>` in `centralindia`:
    - Resource Group `aitdd-tfstate-rg` (provisioningState: Succeeded)
    - Storage Account `aitddtfstatesa001` (Standard_LRS, StorageV2, HTTPS-only, TLS1_2, blob public access disabled, versioning enabled, 7-day delete retention)
    - Blob Container `tfstate` (publicAccess: null → private)
  - Verified independently via Azure CLI (`az group show`, `az storage account show`, `az storage container show --auth-mode login`, `az storage account blob-service-properties show`).
  - Post-apply `terraform plan -detailed-exitcode` returned **exit code 0 — "No changes. Your infrastructure matches the configuration."**, confirming a clean baseline with zero drift.
  - Bootstrap state stored locally in `terraform/bootstrap/terraform.tfstate` (~13 KB) by design; this configuration does not use the remote backend it creates.

#### Task 2.3 — Verify AzureRM Remote Backend Configuration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-30
- **Completed**: 2026-09-30
- **Objective**: Verify that the existing AzureRM backend configuration in `terraform/environments/dev/backend.tf` points to the state storage location created by `terraform/bootstrap` and is ready for remote-state migration.
- **Dependencies**: Task 2.2
- **Files/Areas**: `terraform/environments/dev/backend.tf`
- **Acceptance Criteria**:
  - [x] `backend.tf` declares the `azurerm` backend with `resource_group_name = "aitdd-tfstate-rg"`, `storage_account_name = "aitddtfstatesa001"`, `container_name = "tfstate"`, and `key = "dev.tfstate"`.
  - [x] These values match the state infrastructure deployed by `terraform/bootstrap` in Task 2.2.
  - [x] Configuration adheres to provider version constraints (~> 5.0).
  - [x] Backend initializes successfully, confirming readiness for remote-state migration (Task 2.4).
- **Validation**:
  - [x] `terraform -chdir=terraform/environments/dev init` (without `-backend=false`).
- **Implementation Notes**:
  - `backend.tf` is already uncommented and configured; this task verifies it rather than authoring it.
  - Requires deployed bootstrap storage account.
  - 2026-09-30: Verification only — no configuration changes were required. `backend.tf` was already correct as authored.
  - 2026-09-30: Backend block values cross-checked against live `terraform -chdir=terraform/bootstrap output`: `resource_group_name = aitdd-tfstate-rg`, `storage_account_name = aitddtfstatesa001`, `container_name = tfstate`. All three match exactly; `key = "dev.tfstate"` matches the bootstrap `backend_config_instructions` output corrected in Task 2.2.
  - 2026-09-30: `terraform -chdir=terraform/environments/dev init -input=false` run with `ARM_SUBSCRIPTION_ID` exported from `az account show` (subscription `<AZURE_SUBSCRIPTION_ID>`). Output: "Successfully configured the backend \"azurerm\"!" and "Terraform has been successfully initialized!" Provider resolved from lock file as azurerm v5.7.0 (satisfies `~> 5.0` in `versions.tf`).
- **Completion Notes**:
  - AzureRM remote backend verified and initialized successfully against the Task 2.2 state infrastructure.
  - Recorded backend config in `terraform/environments/dev/.terraform/terraform.tfstate` confirms the four intended settings with `access_key`, `client_secret`, `sas_token`, and all other credential fields `null` — no secrets are persisted in the working directory or in configuration.
  - `terraform fmt -check -recursive terraform/environments/dev` clean; `terraform validate` returned "Success! The configuration is valid."
  - Backend reachability confirmed empirically: `terraform state list` exited 0 against the remote backend, and `az storage blob list --container-name tfstate --account-name aitddtfstatesa001 --auth-mode login` now lists the `dev.tfstate` blob created by init.
  - **Note for Task 2.4**: the dev environment has never been applied — no local `terraform.tfstate` exists in `terraform/environments/dev/`, and `az group list` shows only `aitdd-tfstate-rg` (no `aitdd-dev-main-rg`). There is therefore no local state to migrate; init has already created an empty `dev.tfstate` in the container. Task 2.4 was therefore executed as verification only — confirming the empty remote state rather than running `-migrate-state` on existing local state. (Applying the dev configuration is **not** in Task 2.4's scope; an earlier revision of this note wrongly implied that it was.)

#### Task 2.4 — Migrate Dev Terraform State
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-30
- **Completed**: 2026-09-30
- **Objective**: Perform `terraform init -migrate-state` for `terraform/environments/dev` to move local state file to Azure Storage Blob container.
- **Dependencies**: Task 2.3
- **Files/Areas**: `terraform/environments/dev/`
- **Acceptance Criteria**:
  - [x] Local state (if any) migrated to `dev.tfstate` in `tfstate` container. — Satisfied vacuously: no local state existed. See Completion Notes.
  - [x] Azure Storage Blob contains `dev.tfstate`.
- **Validation**:
  - [x] `az storage blob exists --container-name tfstate --name dev.tfstate --account-name aitddtfstatesa001`
- **Implementation Notes**:
  - Must confirm prompt to copy state into remote blob backend.
  - 2026-09-30: Executed as a **verification-only** task under explicit user direction. No `terraform apply` was run, no Terraform configuration was modified, and `aitdd-dev-main-rg` was **not** deployed.
  - 2026-09-30: `terraform init -migrate-state` was intentionally **not** re-run. The backend was already initialized in Task 2.3 and there is no local state to relocate, so Terraform has nothing to copy and does not present the state-migration confirmation prompt referenced in the note above. That prompt presupposes a local-to-remote transition that never occurred in this project.
- **Completion Notes**:
  - Remote state blob confirmed present. `az storage blob exists --container-name tfstate --name dev.tfstate --account-name aitddtfstatesa001 --auth-mode login` returned `{"exists": true}`. Blob detail: name `dev.tfstate`, size **181 bytes**, lastModified `2026-09-30T16:49:45+00:00` — the timestamp of the Task 2.3 backend `init`, not a migration.
  - Blob contents inspected and confirmed to be an **empty remote-state skeleton**: `version: 4`, `terraform_version: 1.14.7`, `serial: 1`, `lineage: a501803d-874f-488a-8266-c0771b0bc104`, `outputs: {}`, `resources: []`, `check_results: null`.
  - No local state to migrate, verified two ways: `ls terraform/environments/dev/terraform.tfstate` → "No such file or directory", and `find terraform/environments/dev -maxdepth 1 -name '*.tfstate*'` returned no matches (no `terraform.tfstate` and no `.tfstate.backup`).
  - Both acceptance criteria are therefore met: criterion 1 is satisfied by its own `(if any)` clause, which anticipates the no-local-state case; criterion 2 is satisfied empirically by the validation command above.
  - Net effect: the dev environment is now backed by an initialized, reachable, empty remote state in Azure Blob Storage. State plumbing for Phase 2 is complete; no infrastructure was provisioned by this task.
  - **Known gap, since resolved**: at the time this task completed, the dev Resource Group `aitdd-dev-main-rg` had never been applied and no task in Phase 2 deployed it. Resolved on 2026-09-30 by the approved insertion of **Task 2.4a — Deploy Dev Baseline Infrastructure** between this task and Task 2.5. Task 2.5's objective and acceptance criteria remain **unchanged**; only its dependency (→ 2.4a) and validation command (`-var-file="dev.tfvars"`) were corrected.

#### Task 2.4a — Deploy Dev Baseline Infrastructure
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-30
- **Completed**: 2026-09-30
- **Objective**: Deploy the existing Phase 1 Terraform-managed application infrastructure for the `dev` environment through the remote AzureRM backend, establishing the real Terraform-managed baseline required for deterministic drift detection in Phase 3.
- **Dependencies**: Task 2.4
- **Files/Areas**: `terraform/environments/dev/`, `terraform/environments/dev/dev.tfvars`
- **Scope Boundary**:
  - In scope — the current application infrastructure **only**:
    - Resource Group `aitdd-dev-main-rg` in `Central India`, created via the existing `terraform/modules/resource-group` module from the `resource_groups` map in `dev.tfvars`.
  - Explicitly out of scope: VNet, Subnet, NSG, Storage Account, Key Vault, or any other application resource. This task introduces **no new Terraform source code** and adds no resources beyond what Phase 1 already defines.
- **Acceptance Criteria**:
  - [x] `terraform plan -var-file="dev.tfvars"` produces exactly **1 to add, 0 to change, 0 to destroy** (`aitdd-dev-main-rg`), with no unexpected resources.
  - [x] Explicit human approval obtained before `terraform apply` is executed.
  - [x] `terraform apply -var-file="dev.tfvars"` completes successfully with **1 added, 0 changed, 0 destroyed**.
  - [x] Terraform state is written to the **remote backend** (`dev.tfstate` blob advances beyond the empty skeleton recorded in Task 2.4; no local `terraform.tfstate` is created).
  - [x] Resource Group `aitdd-dev-main-rg` exists in Azure in `centralindia` with `provisioningState: Succeeded`.
  - [x] Terraform subsequently sees the deployed Resource Group as managed state.
- **Validation**:
  - [x] `terraform -chdir=terraform/environments/dev plan -var-file="dev.tfvars"` (pre-apply review)
  - [x] `terraform -chdir=terraform/environments/dev apply -var-file="dev.tfvars"` (**requires explicit user approval**)
  - [x] `az group show --name aitdd-dev-main-rg --query "{name:name,location:location,provisioningState:properties.provisioningState}" -o json`
  - [x] `terraform -chdir=terraform/environments/dev state list` lists `module.resource_group.azurerm_resource_group.this["main"]`
  - [x] `az storage blob show --container-name tfstate --name dev.tfstate --account-name aitddtfstatesa001 --auth-mode login` confirms the blob grew beyond the 181-byte empty skeleton
- **Implementation Notes**:
  - Added 2026-09-30 as an approved roadmap correction (Option A). No task in Phase 2 previously deployed the dev application infrastructure; Task 2.2 deployed the **state** backend only. Without this task, the dev environment would remain un-provisioned through the end of Phase 2.
  - Inserted as `2.4a` deliberately so that Tasks 2.5–2.8 keep their existing numbers and all downstream dependency references (including Task 3.1 → Task 2.8) remain valid.
  - **Consequential operation**: per Execution Rules 4 and 13, `terraform apply` must not run without explicit user approval. Present the plan output first and wait.
  - `-var-file="dev.tfvars"` is mandatory. `variables.tf` defaults `resource_groups` to `{}`, so omitting the var-file declares zero resources and silently deploys nothing.
  - Required for Phase 3: Task 3.6 injects external drift into a mutable property of `aitdd-dev-main-rg`, which presupposes the resource exists and is Terraform-managed.
- **Completion Notes**:
  - **Pre-apply plan review** (2026-09-30): `terraform plan -var-file="dev.tfvars" -detailed-exitcode` returned exit code 2 with **1 to add, 0 to change, 0 to destroy**. Plan file exported to JSON and machine-verified: `resource_changes` length **1**, action tally `{create: 1}`, resource types present `['azurerm_resource_group']`, zero non-create actions. No VNet, Subnet, NSG, Storage Account, or Key Vault in the plan. State lock acquired and released cleanly against the remote backend.
  - **Explicit human approval** for `terraform apply` was requested and granted by the user on 2026-09-30 before any consequential operation was executed (Execution Rules 4 and 13 satisfied).
  - **Apply result** (2026-09-30): `terraform apply -var-file="dev.tfvars"` → **"Apply complete! Resources: 1 added, 0 changed, 0 destroyed."** Creation completed in 29s. Resource ID `/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/aitdd-dev-main-rg`.
  - **Azure verification**: `az group show --name aitdd-dev-main-rg` → `location: centralindia`, `provisioningState: Succeeded`, tags `{environment: dev, managed_by: terraform, project: ai-terraform-drift-detector}`. (`centralindia` is the azurerm provider's canonical form of `Central India` as supplied in `dev.tfvars`; not a discrepancy.)
  - **Terraform state verification**: `terraform -chdir=terraform/environments/dev state list` returns exactly one managed resource — `module.resource_group.azurerm_resource_group.this["main"]` — read through the remote backend.
  - **Remote state verification**: `dev.tfstate` blob grew from the **181-byte** empty skeleton recorded in Task 2.4 to **2907 bytes**, lastModified `2026-09-30T17:09:14+00:00`. No local state created: `find terraform/environments/dev -maxdepth 1 -name '*.tfstate*'` returns no matches.
  - **Outputs**: `resource_groups.main` = `{ id, location: centralindia, name: aitdd-dev-main-rg }`.
  - No Terraform source code was modified by this task. Azure resource footprint for the dev application environment is exactly one Resource Group, as scoped.
  - The real Terraform-managed baseline required for Phase 3 deterministic drift detection (notably Task 3.6, which mutates a property of `aitdd-dev-main-rg` externally) now exists.

#### Task 2.5 — Verify Remote State and Zero Unexpected Changes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-09-30
- **Completed**: 2026-09-30
- **Objective**: Run `terraform plan` against dev environment with remote backend to confirm state match and zero unexpected drift.
- **Dependencies**: Task 2.4a
- **Files/Areas**: `terraform/environments/dev/`
- **Acceptance Criteria**:
  - [x] `terraform plan` executes cleanly using remote backend state.
  - [x] Output confirms zero unexpected infrastructure modifications.
- **Validation**:
  - [x] `terraform -chdir=terraform/environments/dev plan -var-file="dev.tfvars"`
- **Implementation Notes**:
  - Ensures local state and remote cloud resources match expectations.
  - 2026-09-30: Validation command corrected to pass `-var-file="dev.tfvars"`. `variables.tf` defaults `resource_groups` to `{}`, so a bare `terraform plan` declares zero resources and returns "No changes" regardless of actual infrastructure — a false green that would satisfy both acceptance criteria while verifying nothing. Objective and acceptance criteria are unchanged; this task remains **verification-only**.
  - 2026-09-30: Dependency changed from Task 2.4 to Task 2.4a. Following the Task 2.4a baseline deployment, this task's criteria are satisfiable exactly as originally written — the plan should report "No changes. Your infrastructure matches the configuration." (exit code 0), a genuine zero-drift baseline.
- **Completion Notes**:
  - **Genuine zero-drift baseline confirmed** (2026-09-30). `terraform -chdir=terraform/environments/dev plan -var-file="dev.tfvars" -detailed-exitcode` returned **exit code 0** with output: **"No changes. Your infrastructure matches the configuration."** Terraform refreshed `module.resource_group.azurerm_resource_group.this["main"]` from Azure (id `/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/aitdd-dev-main-rg`) and found no differences.
  - Plan executed cleanly against the **remote backend**: state lock acquired and released without error; no local state involved.
  - **Machine-verified** via JSON plan export rather than relying on the human-readable summary: `resource_changes` length **1**, action tally `{no-op: 1}`, zero non-no-op changes, and `resource_drift` **empty (0 entries)** — no out-of-band drift detected during refresh.
  - The corrected `-var-file="dev.tfvars"` validation command proved its value: the real configuration was loaded (1 resource tracked and refreshed), so the "No changes" result reflects an actual match between config, remote state, and live Azure — not the false green that a bare `terraform plan` would have produced from the empty `resource_groups` default.
  - Phase 2 state and drift baseline is now verified end to end: remote backend → populated remote state → live Azure resource → zero diff. This is the deterministic zero-drift reference point Phase 3 detection work measures against.

#### Task 2.5a — Initialize Git Repository and Establish GitHub Remote
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Establish the Git and GitHub repository prerequisite required by Task 2.6 OIDC configuration: initialize version control, publish the project to GitHub, and confirm the exact `owner/repository` identity that federated credentials must be bound to.
- **Dependencies**: Task 2.5
- **Files/Areas**: repository root, `.gitignore`, `.github/workflows/terraform-auth-test.yml` (existence verification only)
- **Rationale**: Discovered 2026-09-30 during read-only inspection of Task 2.6. The project directory is **not** a Git repository (`git rev-parse --is-inside-work-tree` → "fatal: not a git repository"), has no commits, and has no remote. Every Task 2.6 acceptance criterion depends on a GitHub repository that does not yet exist: the federated credential subject requires a concrete `repo:<owner>/<repo>:...` value, repo secrets require a repository to hold them, and the workflow cannot run until GitHub has received it. No existing task in this plan initializes Git or creates the GitHub repository.
- **Scope Boundary**:
  - In scope: local Git initialization, GitHub repository/remote creation, initial push, verification of the pushed workflow file, confirmation of the `owner/repository` identity, and verification that sensitive artifacts are excluded from version control.
  - Explicitly out of scope — these remain Task 2.6 / 2.7 concerns: Azure App Registration, Federated Identity Credentials, Azure RBAC assignments, GitHub Actions secrets, and any OIDC configuration.
- **Acceptance Criteria**:
  - [x] Local Git repository initialized (or confirmed already present) at the project root.
  - [x] Intended GitHub repository created and configured as the remote.
  - [x] Project pushed to GitHub; the default branch is published and matches the branches the workflow triggers on (`main` or `master`).
  - [x] `.github/workflows/terraform-auth-test.yml` verified present in the **GitHub repository** (not only locally).
  - [x] Exact GitHub `owner/repository` identity recorded in this plan, for use as the Task 2.6 federated credential subject.
  - [x] Terraform state and other sensitive artifacts verified excluded from Git — no such file appears in the pushed tree.
- **Required `.gitignore` Exclusions**:
  - [x] `*.tfstate`
  - [x] `*.tfstate.*`
  - [x] `.terraform/`
  - [x] `tfplan`
  - [x] `*.tfplan`
  - [x] `plan.json`
- **Validation**:
  - [x] `git rev-parse --is-inside-work-tree` returns `true`
  - [x] `git remote -v` shows the intended GitHub remote
  - [x] `git status --porcelain` shows no untracked/uncommitted sensitive artifacts
  - [x] `git ls-files | grep -E '\.tfstate|\.terraform/|tfplan|plan\.json'` returns **no matches**
  - [x] Workflow file confirmed present in the remote repository
- **Implementation Notes**:
  - Added 2026-09-30 as an approved roadmap correction. Inserted as `2.5a` so Tasks 2.6–2.8 keep their numbers and all downstream references (including Task 3.1 → Task 2.8) remain valid.
  - **Human Action Boundary (Execution Rule 10)**: creating a GitHub repository and pushing to it are user-controlled operations. The `owner/repository` slug is not currently derivable from the working directory and must be supplied by the user.
  - Current `.gitignore` already covers `.terraform/`, `*.tfstate`, `*.tfstate.*`, `*.tfvars` (with `!dev.tfvars` re-included), and intentionally does **not** ignore `.terraform.lock.hcl`. The plan-artifact patterns `tfplan`, `*.tfplan`, and `plan.json` must be verified and added if absent — `plan.json` matters from Phase 3 onward, where Task 3.2 generates machine-readable plan output.
  - `terraform/bootstrap/terraform.tfstate` (~13 KB) exists locally and holds real resource IDs. It must remain excluded; see the related Task 2.6 note on the bootstrap CI step.
  - **2026-10-01 — local work completed (partial)**:
    - `.gitignore` updated: added the three missing plan-artifact patterns `tfplan`, `*.tfplan`, and `plan.json` under a new "Terraform plan artifacts" comment block. The other three required patterns (`*.tfstate`, `*.tfstate.*`, `.terraform/`) were already present. All six verified by exact-line match.
    - Local repository initialized: `git init -b main`. `git rev-parse --is-inside-work-tree` → `true`; `git symbolic-ref --short HEAD` → `main`, matching the workflow's `push`/`pull_request` branch triggers.
    - All files staged with `git add -A` (**staged only — no commit made**, see blockers below). `git ls-files` lists **24 files**, all source/docs/config.
    - **Sensitive-artifact exclusion verified**: `git ls-files | grep -E '\.tfstate|\.terraform/|tfplan|plan\.json'` → **no matches**. `git status --porcelain --ignored` confirms the three sensitive paths are present on disk but correctly ignored: `terraform/bootstrap/terraform.tfstate`, `terraform/bootstrap/.terraform/`, `terraform/environments/dev/.terraform/`.
    - `dev.tfvars` is intentionally tracked (re-included via `!dev.tfvars`) and contains no secrets — only `project_name`, `environment`, `location`, tags, and the `resource_groups` map.
    - `.github/workflows/terraform-auth-test.yml` confirmed staged; its presence in the **remote** repository remains unverified pending push.
  - **2026-10-01 — BLOCKED on user-controlled actions (Execution Rule 10)**. Three blockers stop further progress:
    1. **Git identity not configured.** `git config --global user.name` and `user.email` are both unset, so no commit can be created (`git commit` will refuse). User must set these, or supply the name/email to use.
    2. **GitHub CLI not installed.** `gh` is not on PATH (`command not found: gh`), so the repository cannot be created programmatically. User must create it via the GitHub web UI, or install and authenticate `gh`.
    3. **`owner/repository` slug unknown.** Not derivable from the working directory; required both for the remote URL and as the Task 2.6 federated credential subject.
  - No remote was added, no GitHub repository was created, and nothing was pushed.
  - **2026-10-01 — resume attempt, BLOCKED again. Two blockers:**
    1. **Target GitHub repository does not exist.** `git remote add origin https://github.com/HarshAgarwal1102/ai-terraform-drift-detector.git` succeeded (local config only), but `git ls-remote --heads origin` returned `remote: Repository not found`. Characterized definitively rather than assumed: the `osxkeychain` credential helper holds a working GitHub credential, and an authenticated `GET /user` confirms the session is **HarshAgarwal1102** (id `117922914`) — the owner named in the slug. An authenticated `GET /repos/HarshAgarwal1102/ai-terraform-drift-detector` still returns **404**. Since an authenticated owner receives `200` for their own private repositories, this is **not** a visibility or authentication problem: the repository genuinely does not exist under that exact `owner/name`. Likely created under a different name, a different owner/organization, or creation did not complete.
    2. **Git commit identity still not configured.** Reported as configured, but `git config --list --show-origin | grep -i user` finds **no `user.*` key in any scope** (local, global, system all empty), no `GIT_AUTHOR_*`/`GIT_COMMITTER_*` environment overrides, and neither `~/.gitconfig` nor `~/.config/git/config` exists. `git commit` will refuse. No identity was guessed or invented, since commit authorship is permanent and is published on push.
  - **2026-10-01 — state at stop**: local repo on branch `main`, 24 files staged, exclusions re-verified clean (`git ls-files | grep -E '\.tfstate|\.terraform/|tfplan|plan\.json'` → no matches). Remote `origin` configured locally but unreachable. **No commit created, nothing pushed, no GitHub repository created or modified.**

- **Completion Notes**:
  - **GitHub repository identity (required by Task 2.6)**: `HarshAgarwal1102/ai-terraform-drift-detector` — URL `https://github.com/HarshAgarwal1102/ai-terraform-drift-detector`. Published default branch: **`main`**. The Task 2.6 federated credential subjects are therefore `repo:HarshAgarwal1102/ai-terraform-drift-detector:ref:refs/heads/main` and `repo:HarshAgarwal1102/ai-terraform-drift-detector:pull_request`.
  - **Remote verified** (2026-10-01): the repository became reachable on this attempt — `git ls-remote --heads origin` succeeded where it had previously returned "Repository not found". `origin` already matched the supplied URL exactly, so no `git remote set-url` was required. Git identity confirmed present in global scope: `Harsh Agarwal <harshagarwal.4404@gmail.com>`.
  - **Initial commit**: `172765ef8939fab8547ea3c895729d2418c2e673` (short `172765e`), author `Harsh Agarwal <harshagarwal.4404@gmail.com>`, dated 2026-10-01, subject "Initial commit: Phase 1-2 Terraform foundation and remote state". Contains **24 files**.
  - **Push result**: `git push -u origin main` → `* [new branch]  main -> main`, with upstream tracking established (`branch 'main' set up to track 'origin/main'`). Local `HEAD` and `origin/main` both resolve to `172765ef...` — in sync, zero divergence.
  - **Remote tree verification** performed against the server-side `origin/main` ref after `git fetch` (not against the local index): **24 files**, matching the commit exactly. `.github/workflows/terraform-auth-test.yml` confirmed present in `origin/main` at **1459 bytes**, matching the local file.
  - **Sensitive-artifact exclusion verified remotely**: `git ls-tree -r --name-only origin/main` filtered for state/provider/plan artifacts returned **no matches**. Per-pattern counts against the remote tree — `tfstate`: **0**, `.terraform/`: **0**, `tfplan`: **0**, `plan.json`: **0**. The three sensitive paths remain on disk and correctly ignored: `terraform/bootstrap/terraform.tfstate`, `terraform/bootstrap/.terraform/`, `terraform/environments/dev/.terraform/`.
  - Tracked by design: both `.terraform.lock.hcl` files (reproducible provider versions) and `dev.tfvars` (re-included via `!dev.tfvars`; no secrets — only project name, environment, location, tags, and the `resource_groups` map).
  - The Git/GitHub prerequisite for Task 2.6 OIDC configuration is now satisfied. No Azure App Registration, Federated Identity Credential, GitHub Actions secret, or RBAC assignment was created by this task — all remain Task 2.6 / 2.7 scope.
  - Housekeeping: this `Completion Notes` heading was inadvertently removed from Task 2.5a by an earlier progress edit on 2026-10-01 and has been restored here. No other section was affected.
  - Note: `PROJECT_PLAN.md` was committed at its pre-completion state (these notes were written after the commit), so the working tree now shows an uncommitted `PROJECT_PLAN.md` diff. Expected; no code or configuration file differs from `origin/main`.

#### Task 2.6 — Configure and Verify GitHub Actions OIDC
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Validate OIDC Workload Identity federated credentials and execute `.github/workflows/terraform-auth-test.yml` pipeline.
- **Dependencies**: Task 2.5a
- **Files/Areas**: `.github/workflows/terraform-auth-test.yml`
- **Acceptance Criteria**:
  - [x] Azure App Registration & Federated Identity Configured for GitHub repository.
  - [x] GitHub Actions Secrets (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`) configured.
  - [x] Workflow successfully logs into Azure via OIDC and runs `terraform plan`.
- **Validation**:
  - [x] GitHub Actions workflow run completes with green status.
- **Implementation Notes**:
  - Requires GitHub repo secrets and Azure AD app registration.
  - **PREREQUISITE (added 2026-09-30)**: the GitHub repository established by **Task 2.5a** must exist, contain the pushed workflow file, and have a known `owner/repository` identity before OIDC configuration can begin. Federated Identity Credentials are bound to a concrete subject of the form `repo:<owner>/<repo>:ref:refs/heads/main` (and `repo:<owner>/<repo>:pull_request` for the workflow's pull_request trigger), which cannot be constructed until 2.5a completes. Task 2.6's core purpose is unchanged.
  - **Workflow defect 1 — bootstrap CI step (discovered 2026-09-30, NOT yet fixed)**: the "Validate Bootstrap Configuration" step runs `terraform init`, `validate`, **and `plan`** in `terraform/bootstrap`, which uses **local state**. `.gitignore` excludes `*.tfstate`, so `terraform/bootstrap/terraform.tfstate` (~13 KB, holding real resource IDs) will never reach CI. Planning against empty state would propose re-creating the already-deployed state resource group, storage account, and container, and would fail on the globally-unique storage account name `aitddtfstatesa001` already being taken. This step must be redesigned to perform **only safe validation/format checks** (e.g. `terraform init -backend=false` + `validate`), or else adopt an explicitly managed bootstrap-state strategy. It must not plan against missing local bootstrap state.
  - **Workflow defect 2 — Terraform version misalignment (discovered 2026-09-30, NOT yet fixed)**: the workflow pins `terraform_version: "1.7.0"` via `hashicorp/setup-terraform@v3`, but the project runs **v1.14.7** locally and the remote `dev.tfstate` was written by v1.14.7. Terraform refuses to read state written by a newer version, so the dev plan step would fail on state incompatibility. The workflow version must be aligned with the project's supported Terraform version and the remote state version; `1.7.0` must not remain if incompatible.
  - Fixing the workflow file is deliberately **deferred** — no workflow changes were made during the 2026-09-30 inspection. These notes record the defects for action when Task 2.6 is executed.
  - **2026-10-01 — OIDC behavior verified against current official documentation (per user instruction, not reused from memory):**
    - **CRITICAL FINDING — the previously recorded subject format is WRONG for this repository.** GitHub's OIDC reference states that repositories created **after 2026-07-15** use an **immutable default subject format** embedding numeric owner and repository IDs: `repo:OWNER@OWNER-ID/REPO@REPO-ID:ref:refs/heads/BRANCH`. The legacy `repo:OWNER/REPO:ref:refs/heads/BRANCH` form applies only to repositories created before that date. This repository was created **2026-10-01T14:31:38Z** (confirmed via GitHub REST API), so it uses the **immutable** format. The subjects recorded in the 2026-09-30 prerequisite note above and in Task 2.5a's completion notes are therefore **superseded**.
    - Verified repository identifiers (GitHub REST API `/repos/HarshAgarwal1102/ai-terraform-drift-detector`): `owner.id` = **117922914**, repository `id` = **1400148970**, `default_branch` = `main`, `private` = false, `created_at` = `2026-10-01T14:31:38Z`.
    - **Correct subject for this repository**: `repo:HarshAgarwal1102@117922914/ai-terraform-drift-detector@1400148970:ref:refs/heads/main`
    - Issuer: `https://token.actions.githubusercontent.com`. Audience: `api://AzureADTokenExchange`. Required workflow permission: `id-token: write` (without it the OIDC JWT cannot be requested).
    - Microsoft Entra requires the federated credential `subject` to **exactly** match the token's `sub` claim — wildcards are unsupported, and a mismatch fails the token exchange **silently, with no error**. Microsoft's own GitHub Actions examples still show the legacy format (and in places the typo `pull-request` rather than GitHub's actual `pull_request`), so GitHub's reference is authoritative for the claim value and Entra simply string-matches it.
    - `azure/login`: **v3** is the current supported major version; **v2 is in maintenance mode** (security fixes only) and v1 is end-of-life.
    - `azurerm` backend: `ARM_USE_OIDC` enables workload identity federation; `ARM_USE_AZUREAD` switches storage **data-plane** auth to Entra ID instead of storage account access keys, allowing least privilege via **Storage Blob Data Contributor** on the state container rather than key-listing rights on the storage account.
  - **2026-10-01 — workflow corrections applied locally** to `.github/workflows/terraform-auth-test.yml` (local, non-destructive; both previously recorded defects resolved):
    - **Defect 1 fixed**: the bootstrap step no longer runs `terraform plan`. It now performs offline validation only — `terraform -chdir=terraform/bootstrap init -backend=false -input=false` followed by `validate` — matching the pattern already established in `scripts/validate.sh`. No fake or mock bootstrap state was introduced and no bootstrap state or secret is exposed. Rationale recorded as an in-file comment.
    - **Defect 2 fixed**: Terraform version raised from `1.7.0` to **`1.14.7`**, matching the version installed locally and the version that wrote the remote `dev.tfstate`. Declared once as a job-level `env.TERRAFORM_VERSION`. Deliberately **not** upgraded to the latest release (1.16.4) to avoid an unrelated dependency bump.
    - `azure/login@v2` → `azure/login@v3` (v2 is maintenance-only).
    - Added an explicit **Verify Azure OIDC Authentication** step (`az account show`) so a failed credential exchange fails the job loudly at the authentication boundary instead of surfacing later as a confusing backend error.
    - Added `ARM_USE_AZUREAD: "true"` alongside the existing `ARM_USE_OIDC: "true"` so state blob access uses Entra ID (enables least-privilege RBAC; no storage account keys).
    - Dev plan now runs with `-var-file="dev.tfvars" -input=false -no-color`; `set -euo pipefail` added to every multi-line step for reproducible, fail-fast logs.
    - Verified post-edit: no `client-secret`, `ARM_CLIENT_SECRET`, `password`, or `access_key` reference anywhere in the workflow; only the three intended `secrets.AZURE_*` references; no tab characters.
  - **2026-10-01 — AWAITING EXPLICIT USER APPROVAL.** All local, non-destructive work for this task is complete. The remaining acceptance criteria require consequential external operations that must not be performed without approval (Execution Rules 10 and 13). Verified current Azure state (read-only): **no** app registration named `aitdd-github-oidc` exists (`az ad app list` → `[]`); tenant `<AZURE_TENANT_ID>` and subscription `<AZURE_SUBSCRIPTION_ID>` confirmed live. Pending, in order: (1) create App Registration + service principal; (2) add the federated identity credential using the **immutable** subject above; (3) assign RBAC — `Storage Blob Data Contributor` scoped to the `tfstate` container and `Reader` on the subscription (plan-only needs no write); (4) create the three GitHub repository secrets; (5) commit and push the corrected workflow; (6) trigger the workflow and verify a green run. `AZURE_CLIENT_ID` is intentionally **not** guessed — it must come from the real App Registration.
  - **2026-10-01 — APPROVED EXECUTION: steps 1, 2 and 6 (local) COMPLETED; steps 3, 5, 7, 8 BLOCKED.**
    - **Step 1 — App Registration + service principal CREATED and verified.** `aitdd-github-oidc`; **Application (client) ID `<AZURE_CLIENT_ID>`**; app object ID `<AZURE_APP_OBJECT_ID>`; service principal object ID `<AZURE_SERVICE_PRINCIPAL_OBJECT_ID>`; `signInAudience: AzureADMyOrg`. Verified by read-back (`az ad app show`, `az ad sp show`). **No long-lived credential exists**: `passwordCredentials: []` and `keyCredentials: []`.
    - **Step 2 — Federated identity credential CREATED and verified.** FIC id `<FEDERATED_CREDENTIAL_ID>`, name `github-main-branch`. Read back via `az ad app federated-credential list` and asserted character-exact: issuer `https://token.actions.githubusercontent.com` ✓, audience `["api://AzureADTokenExchange"]` ✓, subject `repo:HarshAgarwal1102@117922914/ai-terraform-drift-detector@1400148970:ref:refs/heads/main` ✓ (verified immutable format).
    - **Step 3 — RBAC assignment BLOCKED (insufficient privileges).** `az role assignment create` for `Storage Blob Data Contributor` on the `tfstate` container failed: `(AuthorizationFailed) The client '<SIGNED_IN_USER_UPN>' with object id '<SIGNED_IN_USER_OBJECT_ID>' does not have authorization to perform action 'Microsoft.Authorization/roleAssignments/write'`. Root cause established: the signed-in account has **no direct role assignments** (`az role assignment list --assignee ... --all` → `[]`); it inherits **Contributor** and **Storage Blob Data Contributor** through an Entra ID group membership. Contributor can create resources (which is why Task 2.4a's apply succeeded) but **cannot create role assignments** — that requires **Owner** or **User Access Administrator**. At subscription scope those are held by a subscription Owner and a User Access Administrator (other accounts in the tenant). Confirmed **0** role assignments exist on the new service principal — nothing partial was created.
    - **Step 5 — GitHub repository secrets BLOCKED.** `gh` CLI still not installed (`command -v gh` → not found), so secrets cannot be created programmatically. Must be entered manually in the GitHub UI. No credential was invented or bypassed.
    - **Step 6 — workflow corrections COMMITTED locally** as `da7ecbaf69bc9b0a4cb3a203bea74eb06e9ef992` (short `da7ecba`). **Deliberately NOT pushed**: the workflow triggers on push to `main`, and pushing before RBAC and secrets exist would fire a run that is guaranteed to fail at `azure/login`, adding a misleading red run to repository history while the task cannot complete regardless. Local branch is `ahead 1`, awaiting user decision.
    - **Steps 7 and 8 — NOT ATTEMPTED.** The workflow run and the no-storage-key remote-state verification both depend on steps 3 and 5. No run was triggered; no success was assumed or fabricated.
    - **Step 9** — `pull_request` federated credential **not** created, per instruction: it is not required by the current acceptance criteria (the `main`-branch subject covers the push and `workflow_dispatch` paths used for verification).
- **Completion Notes**:
  - **OIDC authentication verified end to end via a real GitHub Actions run.** Run **#2**, id `36890678435`, head `da7ecbaf69bc9b0a4cb3a203bea74eb06e9ef992`, event `push`, **conclusion: success** — <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/36890678435> (2026-10-01T16:16:00Z → 16:16:32Z). Every step verified individually rather than trusting the aggregate green: `Azure OIDC Login` ✓, `Verify Azure OIDC Authentication` ✓, `Setup Terraform` ✓, `Check Terraform Formatting` ✓, `Validate Bootstrap Configuration (offline, no state)` ✓, `Validate Dev Environment Configuration` ✓.
  - **Identity**: App Registration `aitdd-github-oidc`, client ID `<AZURE_CLIENT_ID>`, SP object ID `<AZURE_SERVICE_PRINCIPAL_OBJECT_ID>`. FIC `github-main-branch` (id `<FEDERATED_CREDENTIAL_ID>`), issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, subject `repo:HarshAgarwal1102@117922914/ai-terraform-drift-detector@1400148970:ref:refs/heads/main` (GitHub **immutable** format — the legacy format would have failed the exchange silently).
  - **RBAC verified final state** — exactly two assignments, least privilege as intended: `Reader` at subscription scope `/subscriptions/<AZURE_SUBSCRIPTION_ID>`, and `Storage Blob Data Contributor` scoped to the container `.../aitddtfstatesa001/blobServices/default/containers/tfstate`. No subscription-level `Storage Blob Data Contributor` remains.
  - **Backend init + state access**: the `Validate Dev Environment Configuration` step runs `terraform init` (remote AzureRM backend), `validate`, and `plan -var-file="dev.tfvars"` under `set -euo pipefail`, so its success means all three succeeded — `init` reached the backend and read `dev.tfstate`, and the plan completed.
  - **No long-lived credential — proven structurally, not merely by absence in logs.** (a) The app has `passwordCredentials: []` and `keyCredentials: []`. (b) The remote workflow file contains no `client-secret`, `client_secret`, `ARM_CLIENT_SECRET`, `ARM_ACCESS_KEY`, `access_key`, `sas_token`, or `password`. (c) Decisively: the service principal **cannot** obtain a storage account key — `Reader` grants only `*/read`, and `listkeys` is a POST action not covered by it, while container-scoped `Storage Blob Data Contributor` grants only container read/write/delete plus `generateUserDelegationKey`. Since the plan succeeded without any key-listing permission, state access must have gone through Entra ID via `ARM_USE_AZUREAD: "true"`.
  - **Authentication failures are not swallowed**: the dedicated `Verify Azure OIDC Authentication` step runs `az account show` immediately after login under `set -euo pipefail`, failing the job at the auth boundary. Corroborated empirically by run **#1** (id `36877293894`, head `172765e`), which **failed** when the old workflow ran before any OIDC configuration existed — a broken credential produces a red run, not a silent pass.
  - **Workflow changes** (commit `da7ecba`, pushed; `origin/main` content verified byte-identical to the reviewed local file): bootstrap step reduced to offline `init -backend=false` + `validate` (no plan against absent local state, no mock state); Terraform `1.7.0` → **`1.14.7`**; `azure/login@v2` → **v3**; added the OIDC auth-verification step; added `ARM_USE_AZUREAD: "true"`; dev plan given `-var-file="dev.tfvars" -input=false -no-color`.
  - **Note on verification method**: GitHub Actions *log* downloads require authentication (anonymous `GET .../logs` → HTTP 403) and `gh` is not installed, so raw log text was not retrieved. Per-step conclusions came from the public Actions API, and the no-credential claim rests on the stronger structural proof above. GitHub secret *names* were likewise not enumerated directly; their presence and correctness is proven empirically — OIDC login cannot succeed unless all three `AZURE_*` secrets are present and correct.
  - `pull_request` federated credential intentionally **not** created — not required by these acceptance criteria.

#### Task 2.7 — Validate RBAC Permissions
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Verify least privilege RBAC permissions for state storage and application resource management.
- **Dependencies**: Task 2.6
- **Files/Areas**: `docs/architecture.md`
- **Acceptance Criteria**:
  - [x] Storage Blob Data Contributor role assigned to Service Principal for state container.
  - [x] Contributor / Reader roles scoped appropriately to resource groups. — passes with a recorded observation; see Completion Notes.
- **Validation**:
  - [x] `az role assignment list --assignee <CLIENT_ID> --output table`
- **Implementation Notes**:
  - Audit RBAC assignments against security guide.
- **Completion Notes**:
  - **Audit performed read-only** on 2026-10-01 against the Task 2.6 identity `aitdd-github-oidc` (client ID `<AZURE_CLIENT_ID>`, SP object ID `<AZURE_SERVICE_PRINCIPAL_OBJECT_ID>`). **No RBAC assignment was created, modified, or deleted by this task.**
  - **Actual assignments — exactly 2**, confirmed via `az role assignment list --assignee <SP> --all --include-inherited`:
    | Role | Scope | Type |
    | --- | --- | --- |
    | `Storage Blob Data Contributor` | `/subscriptions/<AZURE_SUBSCRIPTION_ID>/resourceGroups/aitdd-tfstate-rg/providers/Microsoft.Storage/storageAccounts/aitddtfstatesa001/blobServices/default/containers/tfstate` | direct |
    | `Reader` | `/subscriptions/<AZURE_SUBSCRIPTION_ID>` | direct |
  - **Subscription-level Reader verified** present and read-only (`Reader` grants `actions: ["*/read"]`, `notActions: []`, `dataActions: []`).
  - **Container-scoped Storage Blob Data Contributor verified**: scoped to the `tfstate` **container**, not the storage account. No subscription-level or storage-account-level `Storage Blob Data Contributor` exists.
  - **No unnecessary or unexpected permissions.** No `Contributor`, `Owner`, or `User Access Administrator` anywhere. The SP has **no group or directory-role memberships** (`/servicePrincipals/{id}/transitiveMemberOf` → `[]`), so there are no inherited permission paths. The app requests **no** Microsoft Graph or API permissions (`requiredResourceAccess: []`, `appRoles: []`, `oauth2PermissionScopes: []`). Still no long-lived credential (`passwordCredentials: []`, `keyCredentials: []`).
  - **Plan-capable but not apply-capable — verified against role definitions:**
    - Granted control-plane actions in total: `*/read`, plus `Microsoft.Storage/storageAccounts/blobServices/containers/{read,write,delete}` and `.../generateUserDelegationKey/action`. Data-plane: 5 blob actions, confined to the `tfstate` container.
    - Plan-required `Microsoft.Resources/subscriptions/resourceGroups/read` → **GRANTED** (via `*/read`).
    - Apply-required actions all **DENIED**: `resourceGroups/write`, `resourceGroups/delete`, `Microsoft.Storage/storageAccounts/write`, `Microsoft.Storage/storageAccounts/listkeys/action`, `Microsoft.Resources/deployments/write`.
  - **OBSERVATION (not a failure, no change made)**: `Reader` is scoped at **subscription** level rather than to the two project resource groups. It is read-only so it grants no modification capability, and subscription-level read is the conventional minimum for a plan identity that must refresh resources across resource groups. A tighter alternative would be `Reader` on `aitdd-dev-main-rg` and `aitdd-tfstate-rg` only. **Not changed — would require explicit user approval.**
  - **FINDING — documentation drift for Task 2.8 to reconcile.** `docs/architecture.md` (lines ~106–111, "Minimum Azure RBAC Permissions") documents an intent that differs from the verified actual state in two ways: (a) it specifies `Storage Blob Data Contributor` at **storage account** scope, whereas the actual assignment is **container** scope — actual is *tighter* than documented; (b) it specifies **`Contributor` on `aitdd-dev-main-rg`** "to plan and apply application infrastructure changes", but **no `Contributor` assignment exists** — deliberately, since CI is plan-only and Core Project Principle "No autonomous apply" forbids CI applying. `docs/architecture.md` was **not modified** by this task (documentation is Task 2.8's scope).
  - **FINDING — the task's own validation command under-reports.** `az role assignment list --assignee <CLIENT_ID> --output table` returns only **1** of the 2 assignments (just `Reader`), because without `--all` it is limited to subscription scope and omits the nested container-scope assignment. The command was run as specified for criterion compliance, and the complete audit used `--all --include-inherited`. Any future RBAC audit should use `--all`.
  - **LIMITATIONS — stated explicitly; these tests were NOT performed.** (a) No empirical negative test was run: no `terraform apply`, and no write operation was attempted as the service principal to observe an `AuthorizationFailed`. Apply-denial is established from Azure role **definitions**, not from an executed denial. (b) The audit could not be performed *as* the service principal (that would require an OIDC token obtainable only inside a GitHub Actions run); it was performed as the signed-in user reading assignment and role-definition metadata. (c) The positive read path is corroborated empirically by the Task 2.6 run `36890678435`, where `terraform init` + `plan` succeeded using only these two roles.

#### Task 2.8 — Complete Phase 2 Documentation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Update README and architecture docs with remote state backend details, OIDC setup steps, and state verification log.
- **Dependencies**: Task 2.7
- **Files/Areas**: `README.md`, `docs/architecture.md`
- **Acceptance Criteria**:
  - [x] Documentation reflects active remote backend configuration.
  - [x] Step-by-step OIDC setup guide included.
- **Validation**:
  - [x] Manual documentation review.
- **Implementation Notes**:
  - Final documentation sync for Phase 2.
- **Completion Notes**:
  - Documentation reconciled against the **actual deployed implementation** and the Task 2.7 audit findings as source of truth. Files changed: `docs/architecture.md`, `README.md`. **No** Terraform code, Azure resource, RBAC assignment, workflow, or GitHub configuration was modified.
  - **`docs/architecture.md`:**
    - Phase 2 status row: `🟡 In Progress (Deployment Pending)` → `✅ Complete`, scope reworded to "Remote State, GitHub OIDC (plan-only CI)".
    - **RBAC table rewritten to verified reality.** Removed two claims for assignments that do not exist: `Contributor` on `aitdd-dev-main-rg` ("plan and apply") and `Key Vault Secrets Officer` on `aitdd-dev-kv-001`. Corrected `Storage Blob Data Contributor` from **storage-account** scope to the actual, tighter **`tfstate` container** scope. Added the actual `Reader` (subscription) row. Added an explicit **"Deliberately not assigned"** table covering subscription/account-scope blob roles, `Contributor`, `Owner`, `User Access Administrator`, and `Key Vault Secrets Officer`, each with its reason. Recorded that the identity has no group/directory-role memberships and requests no Graph/API permissions.
    - Added a **"CI Security Model — Plan-Only"** section: CI has no autonomous `terraform apply` capability, enforced by RBAC rather than convention, listing the five write actions verified denied, and explaining that because `listkeys` is denied, state access uses Entra ID (`ARM_USE_AZUREAD=true`) with no account key.
    - Future apply capability appears **only** as a clearly labelled "Future / conditional only — not current access" block requiring explicit human approval; it is not represented as current access, and `Contributor` is not recommended merely to match the old text.
    - Federated-credential diagram node updated from `(repo:org/repo:ref)` to the **immutable** subject form actually in use.
    - Remote-state controls table: recorded the `dev.tfstate` blob, the full `.gitignore` artifact list, and that bootstrap keeps local state deliberately so CI validates it offline only.
  - **`README.md`:**
    - Current-phase banner: `🟡 (Pending Deployment)` → `✅ Complete`; removed the stale "deployment is pending authentication (`az login`)" claim; states CI is plan-only.
    - Roadmap table: Phase 2 → `✅ Complete`; Phase 3 marked `🟡 Next`.
    - OIDC setup guide rewritten as an accurate step-by-step: real app name `aitdd-github-oidc`; issuer and audience; the **exact-match / no-wildcards / silent-failure** warning; the **immutable vs legacy subject format** rule with the 2026-07-15 cutoff and how to retrieve the owner/repo IDs; the actual two-role least-privilege RBAC with `Contributor` explicitly **not** assigned; the note that role assignments require Owner or User Access Administrator; the three secret names; and a final verification step.
    - Technology stack: replaced the vague "v4 / v2 / v3" with the actual pinned actions (`actions/checkout@v4`, `azure/login@v3`, `hashicorp/setup-terraform@v3`) plus CI Terraform 1.14.7.
    - Added the `dev.tfstate` state blob row; expanded Security Principles with "Plan-Only CI" and "No Storage Account Keys" rows and a precise Least Privilege row.
  - **Validation performed**: stale-claim grep across `README.md`, `docs/architecture.md`, `PROJECT_PLAN.md` for `Contributor` on the dev RG, Key Vault Secrets Officer, and "Deployment Pending"/"pending authentication" — **clean** (remaining matches are the intentional "not assigned" and "future/conditional" entries, plus Task 2.7's historical finding record). Verified no document claims autonomous apply. Ran the repository's own `./scripts/validate.sh` → **"All local validations passed ✓"** (`fmt -check -recursive`, `init -backend=false`, `validate` for bootstrap and dev), confirming this task broke nothing; afterwards re-verified the dev remote backend config is intact and that no local `*.tfstate` was created. Markdown structure checked: code fences balanced (14 / 10), no ragged tables, all 4 mermaid blocks intact.
  - **Secret-exposure check**: no tenant, subscription, client, SP object, FIC, or GitHub owner/repo numeric ID appears in either document, and no `password`/`client_secret`/`access_key`/`sas_token`/private-key string. This repository is **public**, so concrete identifiers were deliberately kept out of the docs; secrets are referenced only by name (`AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, `AZURE_SUBSCRIPTION_ID`).
  - **Not committed**: these documentation and plan changes remain **uncommitted** in the working tree. Task 2.8 does not instruct a commit, so none was created.

---

### PHASE 3 — Deterministic Terraform Drift Detection
**Status**: 🟢 COMPLETED

Phase 3 builds the core deterministic drift detection engine using Terraform state files, machine-readable `terraform plan` JSON outputs, and resource diff parsing prior to AI involvement.

**Initial MVP drift scenario (Resource Group only):**

The first end-to-end drift scenario uses ONLY `aitdd-dev-main-rg`. No VNet, Subnet, NSG, Storage Account, or Key Vault is introduced to demonstrate drift.

1. Terraform configuration and Azure infrastructure are in sync.
2. A supported mutable property of the Resource Group is changed externally (outside Terraform).
3. Terraform detects the difference.
4. `terraform plan -detailed-exitcode` is used to distinguish:
   - `0` = no changes
   - `2` = changes detected
   - `1` = Terraform error
5. The plan is saved and converted to machine-readable JSON using `terraform show -json`.
6. The deterministic drift engine produces a normalized drift report.
7. AI analysis is added only after deterministic drift detection succeeds.

> **Note**: Which Resource Group property is used has not been proven yet. Tags are the candidate, but it must be empirically verified that an external tag change is detected by `terraform plan` before the scenario is implemented.
>
> **Verified 2026-10-02 (Task 3.6):** an external tag addition on the real `aitdd-dev-main-rg` (Azure CLI, approved) was detected by `terraform plan` (`resource_drift` update, exit 2). Tags are the verified mutable property for the MVP scenario.

#### Task 3.1 — Drift Detection Strategy & Execution Plan
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Define exact CLI strategy for generating, exporting, and parsing machine-readable Terraform plans.
- **Dependencies**: Task 2.8
- **Files/Areas**: `docs/drift-detection-spec.md`
- **Acceptance Criteria**:
  - [x] Document specifying `terraform plan -detailed-exitcode -out=tfplan` strategy.
  - [x] Document specifying conversion to JSON via `terraform show -json tfplan`.
- **Validation**:
  - [x] Specification review.
- **Implementation Notes**:
  - Deterministic engine foundation.
- **Completion Notes**:
  - Created `docs/drift-detection-spec.md` — the Phase 3 contract: command and flag contract (required / forbidden flags), exit-code contract, `plan.json` field contract and integrity gate, drift vs configuration-change classification (resource- and attribute-level), Resource Group MVP signatures, evidence bundle and Phase 4 input contract, sensitive-data handling, future extensibility, AI source-of-truth boundary, and acceptance criteria for downstream implementations.
  - **Core decision**: exit codes govern **process outcome only**; drift is determined from `plan.json` (`resource_drift` × `resource_changes`). Exit 1 or any non-0/2 ⇒ run FAILED, drift `unknown`, never "no drift".
  - **Verified on Terraform 1.14.7** (not assumed), in a scratch copy outside the repo with a local backend, seeded by a read-only `terraform state pull`, providers reused (no downloads), refreshing against the real `aitdd-dev-main-rg` read-only. **No `apply`, no Azure modification, real remote state neither locked nor written.** Findings that shaped the contract:
    - Configuration change and external drift **both** return exit 2; only `resource_drift` separates them.
    - **Converged drift returns exit 0 with a non-empty `resource_drift`** — exit 0 is not proof of no drift.
    - Output-only changes return exit 2 with all resources `no-op` — exit 2 is not proof of drift.
    - **On plan failure (provider auth error, variable validation error) Terraform still writes the `-out` plan file; `show -json` on it succeeds and yields `errored: true`, `complete: false`, no change arrays** — a naive parser would report "no drift". The spec rejects this via the exit code and an independent JSON integrity gate.
    - `-refresh=false` hides real drift (exit 0) → forbidden. `-refresh-only` returns exit 2 on any drift (supplementary signal only).
    - `resource_drift` is **omitted** (not `[]`) when empty; `format_version` = `1.2`.
    - External deletion signature: `resource_drift` `delete` + `resource_changes` `create`.
    - The azurerm provider refreshes `tags` from Azure and reports divergence in `resource_drift` — supports (by simulation) the tags candidate for the Phase 3 MVP scenario.
  - The documented §4.1 command sequence was executed verbatim (against the scratch copy) and a throwaway rule checker (scratchpad only, not committed) applied the §5.3 gate and §6 classification to every captured plan: all scenarios classified as specified, and both errored plan files were rejected even with the exit code ignored.
  - `./scripts/validate.sh` → "All local validations passed ✓"; dev backend configuration (`.terraform/terraform.tfstate`) unchanged; no local `*.tfstate` created; markdown fences/mermaid/tables checked. No secrets, credentials, or Azure tenant/subscription/client GUIDs in the new document.
  - **Limitations recorded in the spec (not resolved by guessing)**: "configuration change" means desired ≠ recorded state (cannot distinguish `.tf` edit vs tfvars vs provider-default change); `resource_drift` means remote ≠ recorded (not necessarily a human change — attribution is Phase 7); unmanaged resources/properties are invisible; whether Terraform filters "irrelevant" drift out of `resource_drift` could not be isolated in this configuration; move/import-only exit behavior unverified. A **real** external Azure mutation was not performed — that remains Task 3.6/3.7 (requires approval).
  - **Note for Task 3.2**: its Implementation Note "exit code … 2 (drift found)" is superseded by spec §4.2 — exit 2 means *changes pending*, not drift. Task 3.2 must also capture the plan exit code explicitly (exit 2 under `set -e` would otherwise abort the job) and write artifacts outside the tracked tree. Task 3.2 text was intentionally not edited.

#### Task 3.2 — Machine-Readable Terraform Plan Generation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Implement script to execute non-interactive Terraform plan and convert plan file to JSON format.
- **Dependencies**: Task 3.1
- **Files/Areas**: `scripts/generate_plan_json.sh`
- **Acceptance Criteria**:
  - [x] Script runs `terraform plan -out=tfplan` cleanly. (Plan file written to `$ARTIFACT_DIR/tfplan`, outside the repository, per spec §4.1.)
  - [x] Script runs `terraform show -json tfplan > plan.json`. (`$ARTIFACT_DIR/plan.json`.)
  - [x] Valid JSON file produced.
- **Validation**:
  - [x] `jq . plan.json` executes without errors.
- **Implementation Notes**:
  - Script must handle detailed exit code 0 (no pending changes), 2 (pending changes — **not** by itself drift; corrected 2026-10-01 per `docs/drift-detection-spec.md` §4.2, superseding the original "2 (drift found)" wording), and 1 / any other code (detection failed).
- **Completion Notes**:
  - Implemented `scripts/generate_plan_json.sh` (Bash + `jq`, no Python), following `docs/drift-detection-spec.md` §4, §5.3 and §8 exactly: `init -input=false` → `plan -var-file=dev.tfvars -input=false -no-color -lock-timeout=120s -detailed-exitcode -out=$ARTIFACT_DIR/tfplan` (refresh and locking left at defaults) → `show -json` only when plan exit ∈ {0, 2} → integrity gate → run manifest. No `set -e`; every exit code is captured explicitly, so exit 2 never aborts the run. The script accepts no Terraform arguments, so forbidden flags cannot be passed, and it refuses `TF_CLI_ARGS*`, which could inject them. No `apply` anywhere.
  - **Evidence bundle** in `ARTIFACT_DIR`, which must be absolute, outside the repository and empty (default `$RUNNER_TEMP/drift` in CI, else `mktemp -d`): `detection_run.json` (manifest; always written), `plan.log` (init/plan/show output; always), `plan.json` (plan exit 0/2 only), `tfplan` (transient). The manifest carries the spec §8.1 fields plus `failure_reason`. It contains **no** drift verdict; classification remains Task 3.3+.
  - **Integrity gate (spec §5.3)**: exactly one JSON object; `format_version` major 1; `terraform_version` = pinned 1.14.7; `errored == false`; `complete == true`; `resource_changes` / `resource_drift` / `output_changes` well-formed where present; exit-code ↔ pending-change consistency. Any violation ⇒ `outcome: failed`, `failure_stage: integrity`.
  - **Script exit status**: 0 = run succeeded (plan 0 or 2), 1 = detection failed, 64 = unusable `ARTIFACT_DIR` (the only case with no manifest). A partial `plan.json` from a failed `show` is deleted; a signal or unexpected termination still writes a `failed` manifest (EXIT trap).
  - **Validation — real backend, read-only**: an unmodified run against the real `dev` remote state → script 0, plan exit 0, `backend_key: dev.tfstate`, state lock acquired and released, `jq . plan.json` OK, `.terraform.lock.hcl` and backend config byte-identical afterwards.
  - **Validation — Task 3.1 scratch copy** (local backend, read-only state pull, live Azure read only): config change → plan 2, succeeded; simulated drift → plan 2, succeeded, `resource_drift` present; converged drift → plan 0, succeeded, `resource_drift` present (passed through for Task 3.3); provider auth failure and variable-validation failure → plan 1, `failed/plan`, **no `plan.json`** although Terraform wrote an errored `tfplan`.
  - **Validation — stub `terraform`** (scratchpad only, not committed) for paths real Terraform cannot produce safely: errored JSON with exit 0, exit 2 with only no-op, exit 0 with pending changes, truncated JSON, `format_version` 2.0, non-array `resource_changes`, entry without `actions`, missing `complete`, JSON `terraform_version` mismatch, `show` failure with partial output (deleted), plan exit 3, `TF_CLI_ARGS` set, Terraform version mismatch → all `failed` at the correct stage; output-only exit 2 and valid exit 0/2 → `succeeded`. The plan arguments passed to Terraform were captured and match the contract exactly. `ARTIFACT_DIR` guards (inside the repository, including via `..`; relative; non-empty) → exit 64 and no directory left behind. SIGTERM during plan → `failed`, "interrupted by signal during plan". **16/16 stub cases pass.**
  - `./scripts/validate.sh` → "All local validations passed ✓". `git status` shows only this task's files. No evidence/state artifact in the repository tree (only the pre-existing, ignored `terraform/bootstrap/terraform.tfstate`). Sensitive-data scan of all changed files: no GUIDs, UPNs, keys or secrets. No Azure resource modified.
  - `docs/drift-detection-spec.md` §8.1 synced with the implementation: `preflight` failure stage, `failure_reason` field, and script exit statuses. The contract itself is unchanged.
  - **Limitations**: (a) a **real** external Azure change was not exercised (Task 3.6/3.7, requires approval); exit 2 with drift was proven via the state-copy simulation. (b) The script is not wired into any GitHub workflow; CI integration is Phase 5 (Tasks 5.1–5.4), and `terraform-auth-test.yml` was not modified. (c) Validated locally on bash 3.2 (macOS); the CI runner's bash 5 is expected to be compatible but was not exercised. (d) Move/import-only exit-code consistency remains unverified, as recorded in spec §5.3.

#### Task 3.3 — State vs Infrastructure Change Detection
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-01
- **Completed**: 2026-10-01
- **Objective**: Develop core logic to parse `resource_changes` in `plan.json` for `create`, `update`, `delete`, and `no-op` actions.
- **Dependencies**: Task 3.2
- **Files/Areas**: `scripts/detect_drift.py`, `tests/test_detect_drift.py`, `tests/fixtures/plan_evidence/`
- **Acceptance Criteria**:
  - [x] Evaluates `resource_changes[].change.actions`.
  - [x] Identifies added, modified, deleted, and replaced resources correctly.
- **Validation**:
  - [x] Test execution against sample Terraform plan JSON.
- **Implementation Notes**:
  - Pure deterministic evaluation without AI.
- **Completion Notes**:
  - Implemented `scripts/detect_drift.py` (Python standard library only; no Terraform, Azure, network or LLM calls). It consumes a Task 3.2 evidence bundle and writes `drift_classification.json`. It **re-applies the spec §5.3 integrity gate itself** and never parses human-readable plan output. Output is byte-deterministic: sorted keys and addresses, no generated timestamps.
  - **Three-view classification (spec §6)** per managed address: S = recorded state (`resource_drift.before`, else `resource_changes.before`), R = refreshed (`resource_drift.after`), D = desired (`resource_changes.after`). Resource classes: `in_sync`, `external_drift`, `external_deletion`, `converged_drift`, `config_change` (update/replace/move/import), `resource_added`, `resource_removed`, `drift_and_config_change`, plus `undetermined` when the evidence does not explain a pending change. Attribute classes (§6.2, top-level, **names only**): `drifted`, `drifted_converged`, `config_changed`, `drifted_and_config_changed`, `unknown_until_apply`. `ambiguous` is set for `undetermined` and for same-attribute `drifted_and_config_changed`; Terraform evidence cannot attribute those, so they are never resolved.
  - `has_drift` = a managed resource appears in `resource_drift` — **not** the exit code. Failed runs (manifest `outcome: failed`) and rejected evidence → `outcome: failed`, `has_drift: null`, a `failure` object (source `detection_run` or `classifier`), process exit 1. Never "no drift". Output-only changes are reported as the plan-level `summary.output_only_change` flag; all resources stay `in_sync`. Data sources are ignored. No causality is inferred: classes describe how Terraform's views differ, never who/what changed Azure (Phase 7).
  - `docs/drift-detection-spec.md` synced: §6.1 adds `resource_added` / `resource_removed` as config-side refinements of `config_change`, `undetermined`, and `output_only_change` as a summary flag; §8.2 documents the classifier output and exit codes. `in_sync` is the spec's name for "no change".
  - **Fixtures — real Terraform evidence, read-only**: 11 bundles generated by `scripts/generate_plan_json.sh` against the Task 3.1 scratch copy (local backend seeded from a read-only state pull; only the scratch state/tfvars altered; live Azure read only; **plan only — binary plans deleted, never applied**): in_sync, config_change, external_drift, drift_and_config_change, converged_drift (exit 0), resource_added, resource_removed (`delete_because_each_key`), external_deletion, replace (`replace_because_cannot_update`), output_only_change, failed_run (auth failure). Sanitized: subscription ID → `<AZURE_SUBSCRIPTION_ID>`, scratch paths → repo-relative; `backend_key` is null because they come from the local-backend scratch copy. Plans are stored as `plan.sanitized.json` because `.gitignore` deliberately ignores every `plan.json`. The tests materialize the bundles in a temp directory, so `.gitignore` was **not** weakened.
  - **Tests**: `python3 -m unittest discover -s tests` → **43 passed** (also passed in a simulated fresh clone containing only git-visible files, and with ResourceWarnings as errors). Covers all 10 required scenarios. Invalid-evidence cases: missing manifest/plan, truncated JSON, multiple documents, non-object, errored plan with a succeeded manifest, missing `complete`, `format_version` 2.0, Terraform version mismatch, malformed arrays, exit-code inconsistency both ways, succeeded manifest with exit 1, unknown outcome. Also synthetic §6.2 rule tests, undetermined, drift on different attributes, move/import, data sources, CLI exit codes 0/1/64, and byte-determinism.
  - **End-to-end on the real `dev` backend (read-only)**: `generate_plan_json.sh` → `detect_drift.py` → `outcome: succeeded`, `has_drift: false`, `in_sync`, plan exit 0, `backend_key: dev.tfstate`; `drift_classification.json` valid JSON; lock file and backend config unchanged; no apply markers in the log.
  - Regression: Task 3.2 stub suite 16/16; `./scripts/validate.sh` passed. Sensitive scan of every new file: no GUIDs, real subscription ID, UPNs, paths or secrets. `git status` shows only Task 3.1–3.3 files. No Azure resource modified, no `terraform apply`.
  - **Limitations**: (a) Comparison is per **top-level** attribute; nested diffs (individual tag keys) and before/after values are Task 3.4. (b) For `replace`, D describes the *new* object, so optional attributes not set in configuration can show as `config_changed` (observed: `managed_by` `""` → `null`). This is recorded in the resource `notes`, not suppressed; noise rules are later, declarative work (spec §9). (c) `resource_drift` means remote ≠ recorded; provider normalization can also produce it. (d) Move/import classification and `undetermined` are exercised only by synthetic tests; move/import exit behavior remains unverified (spec §5.3). (e) Drift was simulated by altering a state copy; a real external Azure change is Task 3.6/3.7 (requires approval).

#### Task 3.4 — Resource Identification & Categorization
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Map detected changes to resource addresses, types, names, and exact attribute diffs.
- **Dependencies**: Task 3.3
- **Files/Areas**: `scripts/detect_drift.py`, `tests/test_detect_drift.py`, `docs/drift-detection-spec.md` (§8.2)
- **Acceptance Criteria**:
  - [x] Captures before and after states for changed attributes. (As the three spec §6 views — `state`/`real`/`desired` — because a single before/after pair cannot separate drift from configuration change.)
  - [x] Group drifts by resource type (initially `azurerm_resource_group`).
- **Validation**:
  - [x] Verify attribute diff outputs against test drift plans.
- **Implementation Notes**:
  - Extracts `before` and `after` dictionaries from JSON schema.
- **Completion Notes**:
  - **Boundary verified before coding**: Task 3.3 already emitted the resource identity (`address`, `module_address`, `mode`, `type`, `name`, `index`, `provider_name`), the resource classification and the top-level attribute names/classes. These were preserved, not re-implemented. Genuinely missing: values, nested paths, redaction, grouping. `docs/MASTER_PROJECT_GUIDE.md` agreed with the spec and code; no discrepancy.
  - **Implemented** by extending `scripts/detect_drift.py`; no new module, no new dependency (stdlib only):
    - Per resource **`attribute_changes`**: one entry per changed leaf path. Maps/objects are descended key by key (e.g. `tags.probe`), generically for any resource type; lists are compared whole. Each entry has `path`, `attribute`, `class`, and `state` / `real` / `desired` as `{"status": "value"|"absent"|"unknown"|"redacted"}`, with `null` kept distinct from absent, plus `redacted`.
    - `class` reuses the spec §6.2 rule at the leaf via a shared `_attribute_class()` (refactored out of Task 3.3 code; output proven byte-identical), so there is no second classifier. It is `null` for create/delete, where §6.2 is undefined.
    - **Redaction (§8.3)**: a path flagged in any drift/change `before_sensitive`/`after_sensitive` mask is redacted in every view, and a sensitive subtree is reported once. Unknown desired values are reported as `unknown`, never invented.
    - Top-level **`resource_types`**: resources grouped by Terraform `type`, sorted, with `resource_count`, `addresses` and `classification_counts`. Failed or rejected evidence yields `resource_types: []` and `resources: []` (existing failure semantics unchanged).
  - **Task 3.3 contract preserved**: for all 11 real fixtures, the new output minus `attribute_changes`/`resource_types` is **byte-identical** to the Task 3.3 golden output captured before any change. All 43 existing tests pass **unmodified** (0 test lines removed). Every classification is unchanged.
  - **Spec synced**: `docs/drift-detection-spec.md` §8.2 replaced "attribute values are withheld (Task 3.4 scope)" with the Task 3.4 output description and the value/redaction format. §8.3 had defined no format.
  - **Tests**: 20 new (63 total, all passing, ResourceWarnings as errors). On real fixtures: in_sync (no changes), tag-key change (external_drift / config_change / drift_and_config_change / converged_drift), scalar + multiple attributes + unknown + null (replace), resource_added, resource_removed, external_deletion values, same-type grouping, output-only (no attribute changes, still `in_sync`), failed run, Task 3.3 key-set preservation, and Task 3.3/3.4 agreement on changed attributes. Synthetic: nested object, multiple resource types, sensitive values (whole attribute, map key, subtree, unchanged secret, drift-mask-only; no secret string anywhere in the output), nested unknown, null vs absent, `{}` vs absent, invalid evidence, ordering determinism.
  - **Validation**: `./scripts/validate.sh` passed. CLI output valid JSON and byte-identical across two runs for 11/11 fixtures. CLI redaction check on a scratch bundle with a sensitive-flagged tag: 0 secret occurrences. Task 3.2 stub regression 16/16 (scratch harness rebuilt from committed fixtures after the earlier scratch copy was cleared); chained Task 3.2 → 3.4 run OK. Classifier imports only `argparse`, `json`, `os`, `sys`, `typing`: no Azure, Activity Log, network, LLM, randomness or time. No `terraform apply`, no Azure change, no live plan run in this task. Sensitive scan of all changed lines clean. `tests/fixtures` unchanged.
  - **Limitations**: (a) Lists/sets are compared as whole values (no element-level diff). (b) Create/delete entries list every leaf of the object with `class: null`, including null-valued optional attributes (e.g. `timeouts`). (c) Non-sensitive identifiers such as resource `id` values (which contain the subscription ID) are emitted as values; the output must stay outside the repository like all evidence. (d) The replace quirk from Task 3.3 is now visible at value level (`managed_by` `""` → `null`). (e) `classification_version` stays `"1"`; the change is additive. Task 3.5 will define the formal schema.

#### Task 3.5 — Structured Drift Schema Definition
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Create standard JSON schema (`drift_report.json`) representing normalized drift findings.
- **Dependencies**: Task 3.4
- **Files/Areas**: `schemas/drift_report.schema.json`, `schemas/examples/drift_report.json`, `docs/drift-detection-spec.md` (§8.2)
- **Acceptance Criteria**:
  - [x] Schema defines header (timestamp, environment, target), summary counts, and detailed resource drift list. (Header items map to existing fields; see Completion Notes.)
  - [x] Each drift item includes address, type, action, attribute_changes array.
- **Validation**:
  - [x] Validate sample `drift_report.json` against JSON schema.
- **Implementation Notes**:
  - Contract for Python engine and AI analysis pipeline.
  - 2026-10-02: paused for two decisions (Execution Rule 14); resolved by the user the same day. (1) The schema describes the **existing classifier output**: no new artifact, no converter, no change to `scripts/detect_drift.py`. (2) Validation uses `jsonschema` in a temporary venv **outside** the repository; it is not a project dependency.
- **Completion Notes**:
  - **Naming mapping (documented, not resolved by renaming)**: the plan's `drift_report.json` is the document `scripts/detect_drift.py` writes as `drift_classification.json`. One document, one contract: `schemas/drift_report.schema.json`. Recorded in spec §8.2. The plan still uses `drift_report.json` in Tasks 3.7, 5.3, 5.4, 6.2, 6.7 and 13.3. Read those as this same file. The output file was not renamed, because that would change the Task 3.3 contract.
  - **No header/target object invented**: timestamp = `plan.timestamp` (run times: `run.started_at` / `run.finished_at`), environment = `run.environment`, target = `run.working_dir` + `run.backend_key`. Summary counts = `summary`. Detailed resource list = `resources[]`, each requiring `address`, `type`, `action` and `attribute_changes` (plus every other existing Task 3.3/3.4 field).
  - **Schema** (JSON Schema Draft 2020-12): mirrors the existing output exactly. `additionalProperties: false` throughout; enums for the 9 resource classes, 5 attribute classes and normalized actions; `classification_version` const `"1"`; view values as `value` (may be null) / `absent` / `unknown` / `redacted`, where a redacted view cannot carry a value.
  - Outcome invariants: `succeeded` ⇒ boolean `has_drift`, null `failure`, `run`/`plan`/`summary` present, and `plan.errored` false / `complete` true. `failed` ⇒ `has_drift: null`, a `failure` object, and empty `resources` / `resource_types` / `output_changes`, so a failed run can never validate as "no drift".
  - **Sample**: `schemas/examples/drift_report.json`, generated by the **unchanged** classifier from the committed `external_drift` real-evidence fixture (not hand-written): `external_drift`, attribute change `tags.probe` = `drifted`.
  - **Validation** (jsonschema 4.26.0 `Draft202012Validator`, scratch venv): schema meta-validation OK; sample VALID; classifier output for all 11 real-evidence fixtures VALID; 5 failure/rejected-evidence/redaction outputs (missing manifest, truncated plan, errored plan, exit-code mismatch, sensitive tag) VALID, with the secret absent; **19/19 invalid structures rejected** (each required drift-item field removed, unknown class names, redacted view with a value, value view without a value, empty path, failed outcome with `has_drift: false` or with results, errored plan, data-source mode, extra top-level `header`, wrong version).
  - Existing test suite (63) passes unchanged. `./scripts/validate.sh` passed. Sensitive scan of the schema, the sample and changed lines: clean. No Terraform, Python code, test, workflow or dependency file changed by this task. The Task 3.4 contract is intact (`scripts/detect_drift.py` diff unchanged since Task 3.4). No Azure action.
  - **Limitations**: (a) The sample's `run.backend_key` is `null` because the source fixture came from the local-backend scratch copy; live runs record `dev.tfstate`. (b) Schema validation is **not** part of the committed test suite, because the project has no JSON Schema validator dependency (Task 4.1 owns dependencies). The sample can therefore go stale if the classifier output changes; re-validate then. (c) The naming difference above remains until a future task chooses to rename the output or the plan wording.

#### Task 3.6 — Reproducible Drift Scenarios Suite
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Create reproducible test scenarios, starting with an external change to a verified mutable property of `aitdd-dev-main-rg` (candidate: tags, subject to empirical verification). Scenarios for other resource types are added only if those resources are introduced in a later infrastructure-expansion phase.
- **Dependencies**: Task 3.5
- **Files/Areas**: `tests/scenarios/`
- **Acceptance Criteria**:
  - [x] Azure CLI / Azure PowerShell scripts to introduce controlled drift into non-production sandbox.
  - [x] Scripts to revert manual drift.
- **Validation**:
  - [x] Execute script -> run detection -> confirm expected drift captured.
- **Implementation Notes**:
  - Test suite for validating detection accuracy.
  - 2026-10-02: paused for explicit user approval of the Azure change (Execution Rules 10, 13); approved by the user the same day before any mutation.
- **Completion Notes**:
  - **Scripts** (`tests/scenarios/`, Azure CLI + bash, no new dependency):
    - `rg_tag_drift_common.sh`: shared settings and guards.
    - `rg_tag_drift_inject.sh`: `az tag update --operation Merge --tags aitdd_drift_probe=task-3.6`.
    - `rg_tag_drift_revert.sh`: `--operation Delete` of the probe key with its current value; idempotent.
    - `run_rg_tag_drift_scenario.sh`: baseline → inject → detect → verify → revert → detect, using `scripts/generate_plan_json.sh` + `scripts/detect_drift.py`.
  - **Safety design**: dry-run by default (`--apply` required to change Azure). Only the dedicated probe tag is touched; the Terraform-managed tags (`environment`, `managed_by`, `project`) are verified unchanged after every change, and the probe key may never be one of them. Merge/Delete only, never Replace. The inject refuses if the probe is already present. The resource ID is looked up at runtime and the subscription is masked in all output. The runner arms the revert **before** injecting and runs it on success, failure or interrupt. Evidence is written outside the repository. No `terraform apply` anywhere.
  - **Offline tests** against a stub `az`: 15/15 (dry-run makes no call, Merge-only, managed tags preserved, exact baseline restored, idempotent revert, revert of an unexpected probe value, double-inject refused, bad flag / logged-out refused, subscription masked).
  - **Real execution (approved by user, 2026-10-02)**: `tests/scenarios/run_rg_tag_drift_scenario.sh --apply` → **SCENARIO PASSED, 18/18 checks**.
    - Baseline `in_sync` (plan exit 0).
    - After inject: `has_drift: true`, plan exit 2, `external_drift`, `drift_action`/`action` `update`, `attributes` `[tags = drifted]`, exactly one `attribute_changes` entry `tags.aitdd_drift_probe` = `drifted` (state absent, real `"task-3.6"`, desired absent, not redacted). Raw evidence: `resource_drift` update on `this["main"]` with the probe absent → `"task-3.6"`, and `resource_changes` update proposing its removal.
    - After revert: `in_sync` (plan exit 0) again.
    - All 3 live reports validate against `schemas/drift_report.schema.json` (scratch-venv jsonschema). `backend_key` = `dev.tfstate` in every manifest.
  - **Azure end state**: `aitdd-dev-main-rg` tags back to exactly `{environment, managed_by, project}`, `provisioningState: Succeeded`. The only Azure mutations were the approved tag add and its removal.
  - Regression: 63 unit tests pass; `./scripts/validate.sh` passed. Sensitive scan of `tests/scenarios/`: no IDs, UPNs, paths or keys. No other project file changed by this task (`PROJECT_PLAN.md` only for status/notes).
  - **Limitations**: (a) One scenario only (external tag **addition** on the single MVP resource). Tag modification/removal, deletion, and other resource types are not scripted; per the objective, other types wait for an infrastructure-expansion phase. (b) The scenario is run manually; it is not wired into CI (Phase 5). (c) Overlap noted: Task 3.7 (real-drift validation, `drift_report.json` = `drift_classification.json` per Task 3.5) repeats this run's essence; Task 3.7 can reuse these scripts and their evidence format.

#### Task 3.7 — Validation Against Real Azure Drift Scenarios
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Validate deterministic detection engine against live Azure drift scenario in `dev` environment.
- **Dependencies**: Task 3.6
- **Files/Areas**: `scripts/detect_drift.py`
- **Acceptance Criteria**:
  - [x] Introduce real drift in Azure dev environment (external change to the verified mutable property of `aitdd-dev-main-rg` via Azure CLI).
  - [x] Run drift detection script.
  - [x] Confirm `drift_report.json` accurately reflects exact modified attribute.
- **Validation**:
  - [x] Verify `drift_report.json` matches manual Azure CLI modification.
- **Implementation Notes**:
  - Revert manual change immediately after test.
- **Completion Notes**:
  - Satisfied by the approved Task 3.6 live run (`tests/scenarios/run_rg_tag_drift_scenario.sh --apply`, 2026-10-02 05:24Z, remote `dev.tfstate`). Not re-run, to avoid duplicating an Azure change; reviewed and approved by the user. **No Azure change was made by Task 3.7.**
  - Criteria mapped to that evidence:
    - Real drift introduced via Azure CLI: `az tag update --operation Merge` added `aitdd_drift_probe=task-3.6` to `aitdd-dev-main-rg`; tags are the property verified in Task 3.6.
    - Detection run: `scripts/generate_plan_json.sh` → `scripts/detect_drift.py`, plan exit 2.
    - The report (`drift_report.json` = `drift_classification.json`, per Task 3.5) reflects exactly the modified attribute: `external_drift`, `has_drift: true`, one and only one `attribute_changes` entry, `tags.aitdd_drift_probe` = `drifted`.
    - Matches the manual CLI modification: key `aitdd_drift_probe`, real value `"task-3.6"` (the value set and read back from Azure), state and desired absent. Raw `resource_drift` shows absent → `"task-3.6"`.
    - Immediate revert: rollback ran straight after the check; detection returned `in_sync` (plan exit 0); Azure tags back to `{environment, managed_by, project}`.
  - Optional, not required by the criteria (not done): modifying an existing tag value, so that state, real and desired all hold values. The scenario evidence lives in a temp directory outside the repository; these notes and Task 3.6's are the durable record.

---

### PHASE 4 — Python Drift Engine
**Status**: 🟢 COMPLETED

Phase 4 modularizes the Python drift engine into a production-grade library with structured models, custom CLI entry points, logging, and unit tests.

#### Task 4.1 — Python Project Structure & Environment
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Set up Python package structure, virtualenv configuration, dependencies, and `pyproject.toml` / `requirements.txt`.
- **Dependencies**: Task 3.5
- **Files/Areas**: `src/drift_engine/`, `pyproject.toml`, `requirements.txt`
- **Acceptance Criteria**:
  - [x] Standard Python package layout (`src/drift_engine/`).
  - [x] `pyproject.toml` configured with dependencies (Pydantic, click/argparse, pytest).
- **Validation**:
  - [x] `pip install -e .` succeeds in clean virtual environment.
- **Implementation Notes**:
  - Clean Python library architecture.
- **Completion Notes**:
  - **Layout**: `src/drift_engine/__init__.py` (exposes `__version__` from installed metadata) and `py.typed`. No engine logic: parser, models, comparator, severity and CLI belong to Tasks 4.2–4.6. `scripts/detect_drift.py` was **not** moved or changed; whether it migrates into the package (guide §18 #2) remains a Task 4.2+ decision.
  - **`pyproject.toml`**: setuptools build backend, src layout, distribution `drift-engine` 0.1.0, `requires-python >=3.11`. Runtime dependency: `pydantic>=2.7,<3`. **CLI: standard-library `argparse`** (same as `scripts/detect_drift.py`), so no `click` dependency. Dev extra `[dev]`: `pytest`, `pytest-cov` (Task 4.7 coverage gate), `jsonschema` (the validator Task 3.5 limitation (b) deferred to this task; not yet used by any committed test). pytest configured with `testpaths = ["tests"]`. No console script yet (Task 4.6).
  - **`requirements.txt`**: `-e .[dev]`, so dependencies are declared once, in `pyproject.toml`. Virtualenv convention: `.venv/` in the repo root (already ignored); setup commands are in the `pyproject.toml` header.
  - **Test framework (guide §18 #7)**: pytest is the runner; it runs the existing `unittest` suite unchanged. `tests/test_package.py` (2 smoke tests) skips cleanly when the package is not installed, so the stdlib-only `python3 -m unittest discover -s tests` still passes without a venv.
  - `.gitignore`: added `build/`, `dist/`, `.pytest_cache/`, `.coverage*`, `htmlcov/`.
  - **Validation** (fresh venvs in a scratch directory outside the repo, Python 3.14.7 and 3.13): `pip install -e .` OK; `import drift_engine` → `0.1.0`, pydantic 2.13.5, resolved to `src/drift_engine/`; `pip install -r requirements.txt` OK. `pytest`: 65 passed (63 existing + 2 new). `unittest discover` in venv: 65 OK; system `python3` without install: 65 OK (2 skipped), ResourceWarnings as errors. Wheel build contains `drift_engine/__init__.py` and `py.typed`. `./scripts/validate.sh` passed. Build byproducts removed from the working tree. No Terraform, Azure, workflow or `scripts/` change.
  - **Limitations**: (a) Dependencies use version ranges, not a lock file; reproducible pinning can be added when CI installs the package (Phase 5). (b) CI does not yet install or test the package. (c) README is not updated (already out of date, guide §18 #3; deferred to a documentation task).

#### Task 4.2 — Terraform Plan JSON Parser
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Implement robust Python parser module to read Terraform plan JSON files and extract state changes safely.
- **Dependencies**: Task 4.1
- **Files/Areas**: `src/drift_engine/parser.py`
- **Acceptance Criteria**:
  - [x] Safely parses `plan.json` files up to 50MB.
  - [x] Handles missing fields, null states, and unknown values gracefully without throwing unhandled exceptions.
- **Validation**:
  - [x] `pytest tests/test_parser.py` passes.
- **Implementation Notes**:
  - Defensive parsing for all Terraform resource change fields.
- **Completion Notes**:
  - **Packaging decision (guide §18 #2): migrate, not rewrite, one slice per task.** Task 4.2 moved the plan-parsing slice of `scripts/detect_drift.py` into `src/drift_engine/parser.py`: JSON loading, `normalize_action`, `is_pending`, the §5.3 integrity gate, `EvidenceError` and the S/R/D extraction. The script imports it by putting `src/` on `sys.path`, so it still runs with plain `python3` and no install (scenario scripts unchanged). Classification stays in the script; Tasks 4.3–4.6 can migrate their own slices the same way. No logic is duplicated.
  - **Parser API** (stdlib only): `parse_plan_file(path, plan_rc=None, expected_tf_version=None, max_bytes=MAX_PLAN_BYTES)` and `parse_plan(plan, …)` gate then extract; `extract_plan(plan)` extracts an already-gated plan. They return a frozen `ParsedPlan` (`header`, `resources`, `output_changes`). Each `ResourceEvidence` holds identity, `actions`/`drift_actions`, `action_reason`, `previous_address`, `importing`, the `state`/`real`/`desired` views, `after_unknown` and the four sensitivity masks. When `plan_rc` or the version is `None` (a plan without its manifest, for the Task 4.6 CLI), that check is skipped. Any bad input raises `EvidenceError(stage, reason)` and nothing else.
  - **Safety**:
    - 50 MiB limit (`MAX_PLAN_BYTES`), checked by size before reading and again on read.
    - Missing optional fields read as `None`. Missing arrays default to empty only after the gate passes (spec §5.2). `null` views (create/delete/external deletion) are preserved.
    - Unknown values are passed through as `after_unknown`, never invented.
    - `RecursionError` while decoding is reported as `EvidenceError`.
  - **New gate checks** (spec §5.3 updated). Each closes a confirmed defect in the old script, and Terraform does not emit any of these inputs:
    - Action lists containing non-strings: the old script crashed with `TypeError`.
    - A repeated address within an array: the old script silently dropped an entry, turning `external_drift` into `converged_drift`.
    - Entries nested deeper than `MAX_VALUE_DEPTH` (100): the old script raised `RecursionError` in classification from about 1,000 levels.
    - Plans over 50 MiB.
    - **Extended 2026-10-02 (follow-up to Task 4.6):** resource identity fields are now checked as well; see Task 4.6 "Gate gap resolved".
  - **Contract preserved**: script output is **byte-identical** before and after (output, exit code and message) across 36 bundles: all 11 real fixtures and 25 malformed, sensitive and unknown-value variants. `tests/test_detect_drift.py` is unmodified (63 passing). `tests/test_package.py` (Task 4.1) now detects installation from package metadata, because the script makes `src/` importable.
  - **Tests**: `tests/test_parser.py`, 31 tests (52 subtests), unittest-style so they run under both pytest and plain unittest:
    - all real fixtures, with and without the manifest;
    - the S/R/D views for drift, config change, create, delete and external deletion;
    - missing and null fields, unknown values, move/import, data sources excluded;
    - 24 invalid structures and 8 invalid files (empty, truncated, two documents, BOM, non-UTF-8, deeply nested, missing, a directory);
    - the depth-limit boundary;
    - the size limit: exactly at the limit, one byte over, a 50 MiB + 1 sparse file rejected without reading, and a generated ~49.9 MiB plan parsed;
    - a seeded fuzz test (1,500 mutated real plans).
  - **Validation**:
    - `pytest tests/test_parser.py`: 31 passed in fresh venvs on Python 3.14.7 and 3.13.
    - Full suite: pytest 96 passed; system `python3 -m unittest discover -s tests` without install OK (2 skipped), with ResourceWarnings as errors.
    - `pip install -e ".[dev]"` in a clean venv OK.
    - Fuzzing 20,000 mutated plans through parser **and** classifier: 0 unhandled exceptions on both Pythons. The same inputs on the pre-change script gave 66 crashes.
    - A 49.9 MiB plan (10,096 resources) through the CLI: exit 0 in about 0.7 s. 50 MiB + 1 byte: exit 1, `has_drift: null`.
    - The script also works from another working directory.
    - `./scripts/validate.sh` passed.
    - No Terraform, Azure, workflow or scenario-script change.
  - **Limitations**:
    - (a) Python 3.11/3.12 (allowed by `requires-python`) were not tested; only 3.13 and 3.14 are installed. The code avoids 3.12+ syntax.
    - (b) The 50 MiB plan is read fully into memory; there is no streaming parser. Peak memory was not measured.
    - (c) Duplicate checks run per array, not across `resource_changes`/`resource_drift`, where one address is expected in both.
    - (d) `sys.path` bootstrapping in the script is transitional, until Task 4.6 provides the packaged CLI.

#### Task 4.3 — Drift Normalization & Pydantic Data Models
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Define strong Pydantic models for `DriftItem`, `AttributeChange`, `DriftSummary`, and `DriftReport`.
- **Dependencies**: Task 4.2
- **Files/Areas**: `src/drift_engine/models.py`
- **Acceptance Criteria**:
  - [x] Pydantic models enforce strict types for all drift attributes.
  - [x] Supports JSON serialization and deserialization seamlessly.
- **Validation**:
  - [x] `pytest tests/test_models.py` passes.
- **Implementation Notes**:
  - Types used across Python engine and LangGraph pipeline.
- **Completion Notes**:
  - **Design: the models are the Python form of the existing report contract**, not a new format. They mirror `schemas/drift_report.schema.json` (Task 3.5) field for field, so "normalization" means one typed shape for the classifier output (`drift_classification.json` = the plan's `drift_report.json`). Model mapping:
    - `DriftReport`: the whole document.
    - `DriftSummary`: `summary`.
    - `DriftItem`: `resources[]`.
    - `AttributeChange`: `attribute_changes[]`, with S/R/D views as a discriminated union `ValueView` (`value`, which may be null) | `StatusView` (`absent`/`unknown`/`redacted`, no value key).
    - Supporting models: `AttributeSummary`, `ResourceTypeGroup`, `OutputChange`, `Failure`, `RunInfo`, `PlanInfo`.
    - Enumerations are `Literal`s, so strict mode accepts plain strings from both JSON and Python dicts.
  - **Strictness**: every model is `strict`, `extra="forbid"` and frozen. There is no coercion ("1"≠1, 1≠True, 1.5≠int); unknown classes, actions and fields are rejected; non-negative counts and minimum lengths are enforced. `DriftReport` enforces the schema's outcome invariants: a succeeded report needs a boolean `has_drift` plus `run`/`plan`/`summary`; a failed report needs `has_drift: null`, a `failure` object and empty results, so a failed run can never load as "no drift". `errored`/`complete` use a strict bool with a value check, because `Literal[False]` accepts `0` (found by the agreement fuzz; fixed).
  - **Serialization**: `model_validate_json` / `model_validate` load reports; `model_dump(mode="json")` reproduces the classifier JSON exactly. The JSON key `class` is exposed as `class_`, accepted under both names and serialized as `class`.
  - **Task 4.2 contract preserved**: `parser.py` and `scripts/detect_drift.py` are unchanged; neither imports pydantic, so the script stays stdlib-only. Script output is byte-identical to the Task 4.2 golden baseline (36 bundles). The models are not yet wired into the script or a CLI (Task 4.6).
  - **Dependency**: the pydantic floor was raised to `>=2.11` (needed for `validate_by_name` / `serialize_by_alias`). Verified: tests pass on 2.11.0 and fail on 2.10.6.
  - **Fix to Task 4.1/4.2 test helper**: `tests/test_package.py` could error under plain `python3` when a venv's editable install had left `src/drift_engine.egg-info` behind (reproduced). It now treats the package as installed only when pydantic is also importable.
  - **Tests**: `tests/test_models.py`, 25 tests (213 subtests). They skip without pydantic, so the plain unittest suite still runs. Inputs are real classifier output for all 11 fixtures, plus sensitive, unknown-value, null-value and 4 failure/rejected variants, plus the Task 3.5 sample. Coverage:
    - validation from dict and JSON;
    - byte-identical round trip in the script's serialization;
    - `model_dump_json` round trip;
    - typed access;
    - null vs absent vs unknown vs redacted;
    - redacted values never emitted;
    - 57 invalid structures rejected, plus failed reports carrying results;
    - no coercion from JSON;
    - immutability;
    - construction by field name;
    - **agreement with the JSON Schema** (jsonschema): every valid report is valid in both, all 57 invalid ones are invalid in both, and 3,000 seeded random mutations get the same verdict.
  - **Validation**:
    - `pytest tests/test_models.py`: 25 passed in clean venvs on Python 3.14.7 and 3.13.
    - Full suite: pytest 121 passed; plain `python3 -m unittest discover -s tests` OK (27 skipped) both with a clean tree and with a stale egg-info.
    - `pip install -e ".[dev]"` in a clean venv OK.
    - Scratch agreement fuzz: 60,000 mutated reports, 0 disagreements between models and schema on both Pythons.
    - `./scripts/validate.sh` passed.
    - No Terraform, Azure, workflow, schema or script change.
  - **Limitations**:
    - (a) One deliberate difference from the schema: the strict models reject whole-number floats (`1.0`) where the schema accepts them as integers. The classifier never emits these. Recorded in spec §8.2.
    - (b) The models check per-field types and the outcome invariants only. Cross-field totals, such as `resources_total == len(resources)`, are not checked, matching the schema.
    - (c) The JSON Schema file remains hand-written. Pydantic's generated schema is not used as a replacement.
    - (d) Python 3.11/3.12 still not tested locally.

#### Task 4.4 — Resource Difference & Comparison Engine
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Build comparison module to extract deep attribute diffs between `before` and `after` resource definitions.
- **Dependencies**: Task 4.3
- **Files/Areas**: `src/drift_engine/comparator.py`
- **Acceptance Criteria**:
  - [x] Filters out noise (e.g., computed IDs, timestamps, read-only metadata).
  - [x] Isolates user-configured drifts (e.g., IP whitelist changes, tag changes, security setting modifications).
- **Validation**:
  - [x] `pytest tests/test_comparator.py` passes.
- **Implementation Notes**:
  - Intelligent diffing ignoring non-consequential metadata changes.
- **Completion Notes**:
  - **Deep diff migrated, not rewritten** (same pattern as Task 4.2): the spec §6.2 rule, `classify_attributes` and the Task 3.4 `attribute_changes` walk (S/R/D views, nested maps, whole lists, null vs absent, unknown, redaction) moved verbatim from `scripts/detect_drift.py` into `src/drift_engine/comparator.py`. The script imports them, and resource classification stays in the script. Script output is **byte-identical** to the Task 4.2 golden baseline (36 bundles).
  - **Noise and user intent, as an annotation only** (spec §9: declarative, applied after classification, never removes anything):
    - **Evidence for "user-configured"**: the plan's `configuration` section. `configured_attributes(plan)` returns the top-level attributes set in configuration expressions per config address, walking nested `module_calls`. `config_address()` strips module and resource instance keys, including quoted keys with `.`, `[`, `]` and escaped quotes. The real module yields `{location, name, tags}`.
    - **`NOISE_RULES`** (declarative `NoiseRule` data: path-prefix fnmatch patterns, resource-type patterns, optional action and desired-unset conditions):
      - `computed-id`;
      - `timeouts`;
      - `timestamps` (`created_at`, `creation_time`, `last_modified*`, `*_timestamp`, …);
      - `read-only-metadata` (`etag`, `provisioning_state`, `resource_guid`);
      - `replace-unset-optional`: the documented Task 3.3 quirk where a replace shows `managed_by` `""`→`null`.
    - **Categories** per changed path:
      - `configured`;
      - `noise` (rule matched **and** proven not configured);
      - `unconfigured` (e.g. a security setting left at its provider default and changed in Azure: still significant);
      - `undetermined` (no configuration evidence).
      Configuration always wins over a rule, whose id is still recorded. Anything not proven to be noise is significant.
    - **API**: `compare_plan(parsed, configured, rules=NOISE_RULES)` returns a `ResourceComparison` per resource, with `changes` (all of them), `significant`, `noise` and `configured_drift` (spec §6.2 drift classes on configured attributes). A frozen `ChangeAssessment` carries the unmodified change entry, `category`, `configured` and `rule`. The module is stdlib-only, so the script stays installation-free.
  - **Contracts preserved**: `parser.py` and `models.py` are byte-for-byte unchanged (checksums). The report, schema and models are unchanged, and nothing is wired into the report yet (see limitations). Resource classifications are unchanged by comparison (tested).
  - **Real-data results**:
    - `external_drift`: `tags.probe` is configured drift.
    - `replace`: `location` is configured; `managed_by` is noise (`replace-unset-optional`); `id` is noise.
    - create/delete: `id` and `timeouts` are noise; `managed_by` is unconfigured (kept).
    - `config_change`: significant but not drift.
  - **Tests**: `tests/test_comparator.py`, 35 tests (64 subtests), unittest-style, run with and without installation:
    - the migrated diff equals the classifier output for every fixture, and the script uses the comparator's functions;
    - diff units;
    - configuration extraction: nested modules, malformed input, address stripping;
    - acceptance cases: real tag drift, plus synthetic Azure-shaped IP allow-list (storage `network_rules`), NSG inbound rule and `public_network_access_enabled` drift;
    - noise mixed with real drift (id, etag, timestamp, provisioning state);
    - the real replace quirk;
    - rule conditions, configuration-over-rule priority, undetermined and removed resources, custom rules, prefix matching;
    - tags never noise;
    - nothing dropped, partition complete, classification unchanged, redaction kept, deterministic.
  - **Validation**:
    - `pytest tests/test_comparator.py`: 35 passed on Python 3.14.7 and 3.13.
    - Full suite: pytest 156 passed; plain `python3 -m unittest discover -s tests` OK (27 skipped).
    - Clean `pip install -e ".[dev]"` OK.
    - **Mutation check**: 10 deliberate breakages of the comparator were each caught by the tests. One untestable branch (nested brackets in addresses) was simplified away.
    - **Fuzz**: 20,000 mutated plans (entries and configuration) give 0 unhandled exceptions on both Pythons, after fixing one crash it found (a non-list `configuration.resources`; now a regression test).
    - `./scripts/validate.sh` passed.
    - No Terraform, Azure, workflow, schema or model change.
  - **Limitations**:
    - (a) "Configured" is decided per **top-level** attribute and per configuration **block**, not per instance or nested argument. A change inside a configured `network_rules` block counts as configured; for a `for_each` instance being deleted while its block remains, its attributes still count as configured.
    - (b) Lists, such as `ip_rules` and `security_rule`, are compared whole (Task 3.4 behavior), so drift is reported on the list attribute, not the element.
    - (c) Noise rules are name-based defaults, verified on synthetic cases only. The MVP manages only a resource group, and no Azure timestamp or etag drift has been observed live. Rules should be extended per resource type as resources are added.
    - (d) The assessment is not yet recorded in the report (spec §9 asks for that eventually). That needs a schema/model change and is left for Task 4.5/4.6 or a later decision.
    - (e) Expressions only show *which* attributes are set, not their values. Computed `references` are not evaluated.

#### Task 4.5 — Drift Severity Classifier Foundation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Build deterministic rules-based severity classifier (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
- **Dependencies**: Task 4.4
- **Files/Areas**: `src/drift_engine/severity.py`
- **Acceptance Criteria**:
  - [x] Classifies security-sensitive resources (Key Vault access policy, NSG inbound rules, public storage access) as `CRITICAL`/`HIGH`.
  - [x] Classifies tag/description changes as `LOW`/`INFO`.
- **Validation**:
  - [x] `pytest tests/test_severity.py` passes.
- **Implementation Notes**:
  - Rules-based fallback classifier prior to AI enrichment.
- **Completion Notes**:
  - **Design**: rates the Task 4.4 comparator output. Inputs:
    - `ResourceComparison`, which gives per-change category and drift class;
    - optionally `ResourceEvidence`, for whole-object value checks;
    - optionally the classifier's resource classification.

    The module is stdlib-only, deterministic and annotation-only: every change is rated, nothing is dropped, and no classification or report field changes.
  - **Change severity**:
    - proven noise is `INFO`;
    - otherwise the **highest** severity among matching `SEVERITY_RULES`, so rule order does not matter (tested);
    - an unmatched significant change is `MEDIUM`, because unknown impact is never rated down.
  - **Rule format**: declarative `SeverityRule` data: resource-type and path-prefix fnmatch patterns, base severity, optional value-based escalation, and `redacted_only`. Escalation reads the **real and desired** values. Redacted and unknown values are never read; they keep the base severity.
  - **Rules are path-specific**, so a tag change on a Key Vault is `LOW` while its access policy is `CRITICAL`.
  - **Resource severity**: the highest change severity, raised to a floor:
    - `external_deletion`: `HIGH`, or `CRITICAL` for security-sensitive types;
    - planned `replace`: `HIGH`, because it destroys and recreates the object;
    - `undetermined`: `MEDIUM`.

    Each result carries `reasons` (rule ids or floor) and `is_drift` per change.
  - **Default rules**:
    - Key Vault: access policy (attribute and standalone resource) and RBAC mode `CRITICAL`; network ACLs and public access `HIGH`→`CRITICAL` when Allow or enabled; purge protection / soft delete `HIGH`.
    - NSG: `security_rule` and standalone rule `HIGH`→`CRITICAL` when an **inbound Allow** rule has an open source (`*`, `Internet`, `0.0.0.0/0`, `Any`, including `source_address_prefixes`; case-insensitive).
    - Storage: public network access, public blob access, network rules (attribute and standalone) and container access `HIGH`→`CRITICAL` when public or Allow; TLS / HTTPS / shared key `HIGH`.
    - Any resource: redacted (sensitive) value `HIGH`; `tags` and `description` `LOW`.
  - **API**:
    - `change_severity(...)`, `resource_severity(...)`, `plan_severity(parsed, comparisons, classifications)`;
    - `highest()` / `rank()` and `SEVERITIES` (ascending).

    Mismatched inputs raise `ValueError`.
  - **Contracts preserved**: `parser.py`, `models.py`, `comparator.py` and `scripts/detect_drift.py` are byte-for-byte unchanged (checksums). Script output is byte-identical to the golden baseline (36 bundles). Rating does not modify comparator results (tested). Not wired into the report, schema or a CLI (Task 4.6 / later).
  - **Real-data results**:
    - Tag drift and changes (`external_drift`, `converged_drift`, `drift_and_config_change`, `config_change`): `LOW`.
    - `in_sync` and `output_only_change`: `INFO`.
    - `external_deletion`: `HIGH`.
    - `replace`: `HIGH` (floor; `id`/`managed_by` noise are `INFO`).
    - Create/delete: `MEDIUM`, with `id` `INFO` and tags `LOW`.
  - **Tests**: `tests/test_severity.py`, 45 tests (54 subtests), unittest-style, run with and without installation.
    - **Acceptance 1**: Key Vault access policy (attribute and resource), public access (including desired-on), network ACLs, purge protection; NSG rule change `HIGH`, inbound-open `CRITICAL` (5 source spellings, prefixes list), outbound/deny-open `HIGH`, standalone rule; storage public access, public blob, IP allow list (`HIGH`, Allow→`CRITICAL`), TLS, container access, standalone network rules; unconfigured or undetermined settings not downgraded; external deletion of a security resource `CRITICAL`; planned open inbound rule `CRITICAL`.
    - **Acceptance 2**: real tag fixtures `LOW`; tags on a Key Vault `LOW`; tags + access policy gives `CRITICAL` with tags `LOW`; description `LOW`; noise `INFO`; in-sync `INFO`.
    - **Edge cases**: default `MEDIUM`; replace and deletion floors; undetermined floor; no classification means no floor; redacted values; unknown desired value; odd value shapes; resource `type` of any JSON shape; rule-order independence; custom rules; rule validation; unique ids; mismatched inputs; every change rated; comparator output unmodified; classifier output unchanged; deterministic.
  - **Validation**:
    - `pytest tests/test_severity.py`: 45 passed on Python 3.14.7 and 3.13.
    - Full suite: pytest 201 passed; plain `python3 -m unittest discover -s tests` OK (27 skipped).
    - Clean `pip install -e ".[dev]"` OK.
    - **Mutation check**: 15 deliberate breakages of the rating logic were each caught.
    - **Fuzz**: 20,000 mutated real and synthetic plans through parser, comparator, classifier and severity give 0 unhandled exceptions on both Pythons, after fixing the one crash it found (a non-string resource `type` in the security-type lookup; now a regression test).
    - `./scripts/validate.sh` passed.
    - No Terraform, Azure, workflow, schema or model change.
  - **Limitations**:
    - (a) Default rules cover the three security areas in the criteria plus obvious neighbours. Other types (role assignments, SQL firewall, public IPs, …) fall to `MEDIUM` until rules are added.
    - (b) Lists are compared whole (Task 3.4/4.4), so an NSG with one open rule among others escalates the whole `security_rule` attribute; it is not rated per rule element.
    - (c) Rules check names and values from azurerm 4.x/5.x; deprecated aliases (e.g. `allow_blob_public_access`, `enable_https_traffic_only`) are included where known. Rules are verified on synthetic plans only, since the MVP manages only a resource group.
    - (d) Severity covers changes in a **succeeded** report. A failed detection has no resources to rate and must stay "unknown", never `INFO`; callers must check `outcome` first.
    - (e) Severity is not yet in the report, schema or models (spec §10). That is a later change.

#### Task 4.6 — Structured Output Generator (JSON/YAML)
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Implement CLI output formatters for console human readability and machine JSON/YAML output.
- **Dependencies**: Task 4.5
- **Files/Areas**: `src/drift_engine/cli.py`, `src/drift_engine/formatters.py`
- **Acceptance Criteria**:
  - [x] CLI command `drift-engine analyze --plan plan.json --output report.json` produces formatted report.
  - [x] CLI command supports `--format console` for rich terminal output.
- **Validation**:
  - [x] Test CLI invocation with sample plan JSON files.
- **Implementation Notes**:
  - Use rich or standard formatting for terminal output.
- **Completion Notes**:
  - **Integration**: `drift-engine analyze` connects the components as follows:
    - `classifier.evaluate` builds the report from parser + comparator;
    - `models.DriftReport` validates it before anything is written;
    - for the console view, `comparator.compare_plan` and `severity.plan_severity` add the assessment and severity.
    - The installed `drift-engine` entry point and `python -m drift_engine.cli` both work.
    - No LLM or network use; Terraform's plan stays the only source of truth.
  - **Classification moved, outside the listed Files/Areas** (necessary): resource classification still lived only in `scripts/detect_drift.py`, which a package command cannot import.
    - It moved verbatim into `src/drift_engine/classifier.py`, the same pattern as Tasks 4.2/4.4.
    - `classify_bundle` is now a wrapper over the new `evaluate(plan_path, manifest_path=None)`, which also returns the parsed and raw plan.
    - The script is a ~110-line wrapper that re-exports its former names (declared in `__all__`).
    - Script output is **byte-identical** to the golden baseline (36 bundles).
    - One Task 4.4 test was repointed: its identity check now targets `classifier` instead of the script, because the script no longer calls the diff itself.
  - **Formats** (`formatters.py`):
    - `json` (default) and `yaml` are the unchanged report contract. JSON is byte-identical to the script output when `--manifest` is given. YAML uses `yaml.safe_dump` and loads back equal to the JSON.
    - `console` is a deterministic standard-library view: header (outcome, drift, highest severity, plan, run, counts, pending), resources sorted by severity then address, per-change class / category / severity / rule ids, state / real / desired values (`(absent)`, `(known after apply)`, `(sensitive)`, truncated at 60 characters), noise **listed not hidden**, severity-floor reasons, ambiguity and notes. Optional ANSI color (`--color auto|always|never`; auto means terminal only and honours `NO_COLOR`).
    - A failed run is shown as "drift status UNKNOWN", never "no drift".
    - Severity and assessment appear in the console only. The report, schema and models are unchanged.
  - **CLI semantics**:
    - `--plan` is required, as in the acceptance command.
    - `--manifest` is optional and enables the full integrity gate. Without it, the exit-code and Terraform-version checks are skipped, `run` is all null, and a warning goes to stderr.
    - With `--output`, a one-line summary is printed (`has_drift=… [counts] severity=…`).
    - Exit codes: `0` classified; `1` evidence failed or rejected (failed report still written); `2` usage; `70` the report would break the contract (nothing written); `73` output not writable.
  - **Dependency**: `PyYAML>=6.0,<7` added (runtime) for `--format yaml`, plus the `[project.scripts] drift-engine` entry point. No `rich`; standard formatting per the implementation note.
  - **Known gap found (pre-existing, needs a decision)**: the CLI fuzz showed the §5.3 gate does not type-check resource identity fields (`type`, `name`, `index`, `module_address`, `provider_name`, `action_reason`) or reject empty `address`/`actions`.
    - For such malformed plans (not produced by Terraform), the classifier's report breaks the schema; this already applied to `scripts/detect_drift.py` since Task 3.3.
    - The CLI refuses those reports (exit `70`, nothing written, drift UNKNOWN); covered by a regression test.
    - The proper fix is to extend the parser's gate, which changes the Task 4.2 parser contract and was **not** done here (constraint: preserve established contracts). Documented in spec §8.2 and README known limitations.
  - **Gate gap resolved (2026-10-02, approved follow-up)**:
    - **What changed**: `src/drift_engine/parser.py` integrity gate. Every `resource_changes` / `resource_drift` entry (managed and data) must have:
      - a non-empty `address`;
      - `mode` `managed` or `data`;
      - string `type` and `name`;
      - a non-empty action list;
      - `index` absent, null, integer (not bool or float) or string;
      - `module_address`, `provider_name`, `action_reason` and `previous_address` absent, null or string.

      `output_changes` action lists must be non-empty. Violations are reported once per kind, in a fixed order, as `integrity` failures: a failed report with drift unknown.
    - **Rules came from evidence**: an inventory of all 17 real fixture entries (all identity fields strings, `action_reason` present on 2, every action list non-empty) and the report schema's field requirements.
    - **Valid input unchanged**:
      - script golden output: byte-identical for all 36 bundles;
      - all 66 CLI outputs on real fixtures (11 fixtures × with/without manifest × 3 formats): byte-identical;
      - `models.py`, `comparator.py`, `severity.py`, `classifier.py`, `formatters.py` and the schema: unchanged (checksums).
    - **Behavior change for malformed input only**: such plans now get a failed, schema-valid report (exit 1) from both the script and the CLI. Previously the script wrote a schema-invalid "succeeded" report and the CLI exited 70. A missing `mode` silently dropped the resource. CLI exit `70` remains as defense in depth, and its message now names an engine defect.
    - **Tests**:
      - `tests/test_parser.py` +7 tests (`TestIdentityFields`): 17 malformed shapes × both arrays; empty actions in all three arrays; data entries checked; multi-problem ordering; 17 valid Terraform shapes accepted; real fixtures accepted; classifier gives a failed report.
      - The `entry()` helper now builds entries with `type`/`name`, as Terraform does. `test_entry_with_only_required_fields` now expects them.
      - `tests/test_cli.py`: the malformed-identity test now expects exit 1 with a failed report (6 cases); the mocked exit-70 test is kept.
    - **Validation**:
      - Full suite 243 passed on Python 3.14.7 and 3.13 (ResourceWarnings and unraisable exceptions as errors); plain unittest OK (62 skipped).
      - **Mutation check**: 10 breakages of the new checks, including 2 that make the gate over-strict (`module_address` required, `data` mode rejected), were each caught.
      - **Fuzz**: pipeline contract violations went from 288 to **0** (5,000 plans, both Pythons). Parser (20k ×2), comparator (20k), severity (20k) and CLI-pipeline fuzzers all show 0 unhandled. Models and schema agree on 60k mutations.
      - `pyflakes` clean; Python 3.11 grammar OK; `./scripts/validate.sh` passed.
    - **Docs**: spec §5.3 (identity checks) and §8.2 (exit 70 is defense in depth, gap removed); README parser row, exit-code row, test counts, and the known limitation removed.
  - **Contracts preserved**: `parser.py`, `models.py`, `comparator.py`, `severity.py` and `schemas/drift_report.schema.json` are byte-for-byte unchanged (checksums). The report contract is unchanged (tested: top-level keys, schema validation of every CLI output).
  - **Tests**: `tests/test_cli.py`, 35 tests (87 subtests); they skip without pydantic/PyYAML.
    - **Acceptance**: the exact command on every fixture, with a contract-valid report and summary line.
    - **Equivalence**: with `--manifest`, byte-identical to the script and the same exit code for all 11 fixtures, including the failed run.
    - **Schema validation** of every output, with and without a manifest.
    - **Plan-only mode**: warning, null run, other gate checks still apply; manifest checks apply when given.
    - *(Pre-follow-up result, superseded by "Gate gap resolved" above.)* **Failures**: failed manifest, missing or invalid plan in all three formats (console never says "none detected"), unwritable output (73), contract violation (70) including malformed identity fields, five usage errors (2).
    - **Formats**: JSON default; YAML equal to JSON for every fixture; ambiguous YAML strings; deterministic in every format; file output equal to stdout.
    - **Console**: drift, in-sync, replace (noise listed, floor reason, outputs), external deletion, severity matches `severity.py` for every fixture, sort by severity before address, failed run, plan-only line, sensitive value never printed in any format, unknown value, truncation, color rules.
    - **Real process**: `python -m drift_engine.cli` and the installed `drift-engine` executable, including `--version`.
  - **Validation**:
    - Fresh `pip install -e ".[dev]"` on Python 3.14.7 and 3.13: `drift-engine --version` works, and the acceptance command was run by hand on a real fixture.
    - *(Pre-follow-up result, superseded by "Gate gap resolved" above.)* `pytest tests/test_cli.py`: 35 passed on both Pythons. Full suite: 236 passed on both, with ResourceWarnings and unraisable exceptions as errors (4 file-handle leaks in the new tests were found and fixed).
    - Plain `python3 -m unittest discover -s tests`: OK (62 skipped).
    - **Mutation check**: 10 deliberate breakages of the CLI and formatters were each caught; 0 tests skipped.
    - *(Pre-follow-up result, superseded by "Gate gap resolved" above.)* **Pipeline fuzz** (5,000 mutated plans through evaluate, models, comparator, severity and all three renderers): 0 unhandled exceptions; 288 contract violations, all on the known gap above.
    - `pyflakes` clean; all files parse with the Python 3.11 grammar.
    - `./scripts/validate.sh` passed.
    - README and spec links and anchors resolve; the README commands and library example were run for real.
    - No Terraform, Azure, workflow, schema or model change.
  - **Docs updated**: `README.md` (status 4.1–4.6, CLI usage, options, exit codes, formats, dependency, tree, test counts, known limitation) and spec §8.2 (classifier location, CLI, plan-only semantics, exit codes, known gap).
  - **Limitations**:
    - (a) ~~The known gate gap above~~: resolved (see "Gate gap resolved").
    - (b) Severity and assessment are not in the JSON/YAML report (schema change, later).
    - (c) Plan-only mode is weaker than manifest mode by design; `--manifest` is optional because the acceptance command omits it.
    - (d) No structured logging yet (Task 4.7).
    - (e) Python 3.11/3.12 still not executed locally (syntax checked).

#### Task 4.7 — Logging, Error Handling & Unit Tests
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Add comprehensive logging, exception handling, and test coverage >= 85% for `drift_engine`.
- **Dependencies**: Task 4.6
- **Files/Areas**: `src/drift_engine/`, `tests/`
- **Acceptance Criteria**:
  - [x] Structured logging using standard library `logging`.
  - [x] Unit test suite covering all modules, edge cases, and invalid inputs.
- **Validation**:
  - [x] `pytest --cov=src/drift_engine tests/` achieves >= 85% coverage.
- **Implementation Notes**:
  - Production readiness check for Python package.
- **Completion Notes**:
  - **Baseline before changes**: 98% line coverage (97% with branches) on the exact validation command. The gap was not coverage but missing logging and error handling, `classifier.py` (moved in 4.6) without its own tests, and 18 untested branches.
  - **Structured logging** (`src/drift_engine/logs.py`, standard `logging` only):
    - **Silent by default**: the package logger gets a `NullHandler` (idempotent), so library callers, `scripts/detect_drift.py` and default CLI runs see no new output.
    - **Event format**: every record has a stable `event` name plus a `fields` mapping (one attribute, so it cannot collide with `LogRecord` names). `stacklevel=2` makes records point at the emitting module and function, not the helper.
    - **Formatters**: `TextFormatter` (`time LEVEL logger event: message key=value …`) and `JsonFormatter` (one object per line, UTC timestamps, exceptions included).
    - **`configure_logging(level, fmt, stream)`** replaces its own earlier handler.
    - **Events** (aggregate, not per resource):
      - parser: `evidence_loaded`, `plan_parsed`, `integrity_gate_failed` (DEBUG);
      - classifier: `classification_finished` (INFO), `classification_failed` and `manifest_not_given` (WARNING);
      - comparator: `comparison_finished`; severity: `severity_rated` (DEBUG);
      - CLI: `report_written` (INFO), `output_write_failed`, `contract_violation` and `unexpected_error` (ERROR, with the traceback at DEBUG).
    - **No values**: event fields carry identifiers, counts, stages and reasons only, never attribute values (tested with sensitive and plain values in both formats). The one exception is an *unexpected* internal error: its exception message is printed to stderr, and at DEBUG its traceback is logged. These engine-defect diagnostics carry whatever text that exception holds (documented in README and spec §8.2).
  - **CLI**: `--log-level debug|info|warning|error` (default off) and `--log-format text|json`; logs go to stderr, never into the report.
  - **Exception handling** (CLI):
    - an unexpected exception exits 70 with "INTERNAL ERROR … drift status UNKNOWN" and no traceback dump (the traceback is logged at DEBUG);
    - Ctrl-C exits 130 (`Interrupted.`);
    - a closed stdout (broken pipe) exits 141 quietly, with stdout redirected to devnull so the interpreter's final flush cannot fail;
    - `--output` is written **atomically**: temp file in the same directory, fsync, then `os.replace`. A failed or interrupted write leaves no partial file and keeps an existing report, including its permissions.
    - **Permissions (fixed after the final review, Issue A)**: an existing regular report keeps its own rwx bits, so a `0600` report stays `0600`; setuid/setgid/sticky bits are not carried over. A new report gets `0666` minus the umask. A report we may not write (e.g. `0444`) is refused with 73, as the earlier in-place write did. The first implementation always applied the umask default, which widened a `0600` report to `0644`.
    - **Rename semantics (safest atomic choice; no non-atomic fallback)**:
      - the directory must be writable (otherwise 73);
      - a symlink at the output path is replaced by a regular file and **never written through**, so the link's target is untouched (no symlink clobbering);
      - a hard-linked report gets a new inode, and other names keep the old content.
  - **Behavior preserved**: per-stream comparison against the committed `HEAD` CLI gives identical stdout, stderr and exit code for all 66 real-fixture runs (11 fixtures × with/without manifest × 3 formats). Script golden output is byte-identical (36 bundles). The only observable difference is that the report on stdout is now flushed before a failure message on stderr; it is visible only when both streams are merged into one file, and the flush is needed to catch a broken pipe. The report contract, schema, models, comparator and severity rules are unchanged; `__init__`, parser, classifier, comparator and severity changed only by adding log events.
  - **Coverage gate**: `pyproject.toml` `[tool.coverage]` adds `branch = true`, `fail_under = 85` and `show_missing`, so `pytest --cov=src/drift_engine tests/` fails below 85%.
  - **Tests** (+76; 319 total):
    - new `tests/test_logging.py` (24): silent default, script output unchanged, report unchanged by logging, every event with exact fields, caller location, JSON-serializable fields, aggregate-only, no values in logs, both formatters, configuration;
    - new `tests/test_classifier.py` (15): `evaluate()` with and without a manifest, every manifest failure, both undetermined branches, determinism;
    - `tests/test_cli.py` +28: logging flags and events, unexpected error (70), interrupt (130), broken pipe in process and in a real subprocess (141), console without ratings, `__main__` via runpy;
    - atomic output (14 tests): new file follows the umask (3 umasks); existing `0600` stays `0600`; other modes kept exactly under a tight umask; setgid not carried over; read-only report refused; failed and interrupted writes keep the previous report and its mode; interrupted write leaves no new file; directory target; read-only directory refused with no fallback; hard link gets a new inode while the other name keeps the old content; symlink replaced and its target untouched; dangling symlink.
    - +3 each in parser and comparator, +2 in severity, +1 in package (version fallback; reload does not stack handlers).
  - **Validation**:
    - `pytest --cov=src/drift_engine tests/`: **319 passed, 99.87% line and branch coverage** (gate 85%) on Python 3.14.7 and 3.13, with ResourceWarnings, unraisable exceptions and RuntimeWarnings as errors; 0 skipped. Only uncovered: two race-only lines in the temp-file cleanup.
    - Plain `python3 -m unittest discover -s tests`: 319 run, OK (90 skipped).
    - **Mutation check**: 12 breakages of logging and error handling, plus 6 of the permission fix (including re-introducing the original bug, which fails 7 tests), were each caught. A Ctrl-C test that would have aborted the whole session now fails cleanly.
    - **Output files vs the committed `HEAD` CLI**: new `--output` files are identical in content and mode for all 11 fixtures.
    - **Fuzz with DEBUG JSON logging on**: 5,000 plans through the full pipeline, 0 unhandled and 27,538 log lines all valid JSON (both Pythons). Parser, comparator and severity fuzzers 0 unhandled; models and schema agree on 60k.
    - `pyflakes` clean; Python 3.11 grammar OK; the script path stays stdlib-only; `./scripts/validate.sh` passed.
    - README and spec links resolve, and the README logging example was run for real.
  - **Docs**: README (Phase 4 complete; logging section and example; `--log-level`/`--log-format`; exit codes 70/130/141; atomic output; coverage command; test table, counts and tree) and spec §8.2 (exit codes, atomic output, logging and its no-values guarantee).
  - **Limitations**:
    - (a) The script `scripts/detect_drift.py` has no logging flags (silent library logs only); `drift-engine` is the logging-capable entry point.
    - (b) CI does not run the Python tests or the coverage gate yet (Phase 5 or 12).
    - (c) By design of the atomic rename: `--output` needs a writable directory; a symlinked output path is replaced, not written through; a hard-linked report is detached from its other names; the new file belongs to the user running the CLI.
    - (d) Python 3.11/3.12 still only syntax-checked.

---

### PHASE 5 — Automated Drift Detection Workflow
**Status**: 🟢 COMPLETED

Phase 5 automates drift scanning in GitHub Actions on a schedule and manual dispatch trigger.

#### Task 5.1 — Scheduled & Manual GitHub Actions Workflows
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Create `.github/workflows/drift-detection.yml` triggered via `schedule` (cron) and `workflow_dispatch`.
- **Dependencies**: Tasks 2.6, 4.7
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [x] Workflow contains daily cron trigger (e.g., `0 2 * * *`) and `workflow_dispatch`.
  - [x] Supports inputs for `environment` selection.
- **Validation**:
  - [x] Manual trigger test via GitHub Actions UI / CLI. Run **#1**, id `36993949705`, triggered manually from the Actions UI (`gh` not installed) — see Completion Notes.
- **Implementation Notes**:
  - CI pipeline for continuous drift monitoring.
- **Completion Notes**:
  - **Real GitHub validation**: run **#1**, id `36993949705` — <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/36993949705>. Event `workflow_dispatch`, branch `main`, head `68133e8dcd938f74ecf3929003b33e7f5ff7198d` (commit `feat: add scheduled and manual drift detection workflow`), actor `HarshAgarwal1102`, 2026-10-02T10:10:00Z → 10:10:10Z, **conclusion: success**.
  - **Verified via the public Actions API** (log download needs auth: HTTP 403): job `Drift Detection (dev)` (id `110796271473`) succeeded — its name is rendered from the input, confirming `environment=dev` was accepted. Steps, all `success`: Set up job, Require main branch, Checkout Code, Resolve Environment, Run Summary, Post Checkout Code, Complete job. The two validation steps exit 1 with `::error::` on failure, so their success means the main-branch guard and the environment/path checks passed; Run Summary succeeding under `set -euo pipefail` means the step summary was written (its rendered text was not retrieved without sign-in).
  - **No Azure/Terraform access**: the step list contains no login or Terraform step, and the workflow has `permissions: contents: read` only (no `id-token: write`), so no OIDC token could be requested.
  - **Annotations** (2, neither an error): a warning that `actions/checkout@v4` targets the deprecated Node.js 20 and was forced onto Node.js 24; a notice that `ubuntu-latest` migrates to Ubuntu 26 from 2026-10-19. Not acted on in 5.1; the same `actions/checkout@v4` pin is used by `terraform-auth-test.yml`.
  - **Scheduled trigger**: the `0 2 * * *` cron is active on `main`; a scheduled run has not yet occurred, so it is validated by configuration (and schema), not by an executed run.
- **Progress Notes (2026-10-02)**:
  - **File**: `.github/workflows/drift-detection.yml` (new). Triggers: `schedule` cron `0 2 * * *` (daily 02:00 UTC) and `workflow_dispatch` with a required `environment` `choice` input (options: `dev`, the only environment in `terraform/environments/`; default `dev`). Scheduled runs carry no inputs and default to `dev`.
  - **Job `detect-drift`**: (1) fails unless `GITHUB_REF` is `refs/heads/main`; (2) checkout with `persist-credentials: false`; (3) resolves and validates the environment (name regex `^[a-z0-9-]+$`, directory and `<env>.tfvars` must exist) and exposes `environment`, `working_directory`, `var_file` as step and job outputs for Tasks 5.2–5.3; (4) writes a run summary. `timeout-minutes: 30`; per-environment `concurrency` without cancel-in-progress.
  - **Security model preserved**: `permissions: contents: read` only — no Azure access in 5.1; Task 5.2 adds `id-token: write` and `azure/login@v3` with the existing OIDC secrets. **No job-level `environment:` key**: a GitHub Environment changes the OIDC `sub` to `...:environment:<name>`, which does not match the only federated credential (`...:ref:refs/heads/main`, Task 2.6) and would need a new Azure FIC. Schedules run on the default branch, and the main-only guard keeps manual runs on the trusted subject and the reviewed configuration. No `terraform apply`, client secret, storage key or SAS token.
  - **Not in 5.1 (by plan)**: Azure login/Terraform setup (5.2), plan + `drift-engine analyze` (5.3), artifacts (5.4), drift/failure semantics (5.5). The workflow is currently a trigger and context skeleton.
  - **Local validation**: `check-jsonschema --builtin-schema vendor.github-workflows` passes for both workflows; parsed YAML confirms the cron, dispatch input, permissions and absence of a job `environment:` key; no `terraform apply`/secret/key strings outside comments. Each `run:` step was extracted and executed under simulated runner variables: main ref passes, `refs/heads/feat` fails; `dev` resolves to `terraform/environments/dev` + `dev.tfvars`; `../../x` and missing `prod` fail with `::error::`; the summary renders. `actionlint` was not available locally.
  - **README**: workflow tree and status line updated.

#### Task 5.2 — OIDC Authentication & Terraform Setup in Pipeline
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Integrate Azure OIDC login and Terraform CLI setup steps into drift detection workflow.
- **Dependencies**: Task 5.1
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [x] `azure/login@v2` authenticates via OIDC. *(Implemented with `azure/login@v3`; v2 is maintenance-only, see Task 2.6.)*
  - [x] `hashicorp/setup-terraform` installs Terraform.
  - [x] `terraform init` connects to AzureRM remote backend.
- **Validation**:
  - [x] Pipeline confirms successful backend initialization: run #3 `36995803123`, see Completion Notes.
- **Implementation Notes**:
  - Non-interactive Terraform execution.
- **Completion Notes**:
  - **Real GitHub validation**: run **#3**, id `36995803123`, <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/36995803123>.
    - Event `workflow_dispatch`, branch `main`, head `03f87d708f53d9e2290601af0ee559c24c0326b0` (`fix: add linux terraform provider lock checksum`), `ubuntu-latest`, 2026-10-02T10:30:03Z → 10:30:27Z. **Conclusion: success.**
    - Job `Drift Detection (dev)` (id `110802131397`). All 13 steps `success`: Set up job, Require main branch, Checkout Code, Resolve Environment, **Azure OIDC Login**, **Verify Azure OIDC Authentication**, **Setup Terraform**, **Terraform Init (remote backend)**, **Terraform Validate**, Run Summary, Post Azure OIDC Login, Post Checkout Code, Complete job.
    - Terraform Validate passing on the Linux runner confirms the `linux_amd64` `h1:` lock fix; run #2 failed there.
  - **Evidence basis**: step conclusions come from the public Actions API. Raw log text was not downloaded (it needs auth).
    - Backend initialization is established by the init step's success: under `set -euo pipefail`, against the AzureRM backend (no `-backend=false`), with `ARM_USE_OIDC`/`ARM_USE_AZUREAD`.
    - Validate and Run Summary ran after it, and Run Summary reports "AzureRM remote state, initialized and validated".
  - **Security**: OIDC only (no client secret, storage key or SAS); `permissions` `id-token: write` + `contents: read`; no job `environment:` key, so the token subject still matches the existing `ref:refs/heads/main` FIC. No GitHub/Azure configuration changed, and no `plan`/`apply`.
  - **Annotations** (not errors): a Node.js 20 deprecation warning (`actions/checkout@v4`, `hashicorp/setup-terraform@v3` forced onto Node 24), and the `ubuntu-latest` → Ubuntu 26 migration notice (2026-10-19).
- **Progress Notes (2026-10-02)**:
  - **Workflow** (`.github/workflows/drift-detection.yml`): `permissions` now `id-token: write` + `contents: read` (workflow level, nothing at job level). Workflow `env`: `TERRAFORM_VERSION: "1.14.7"` (same pin as `terraform-auth-test.yml` and `generate_plan_json.sh`; `dev.tfstate` was written by 1.14.7), `TF_IN_AUTOMATION`, `TF_INPUT=0`.
  - **New steps after `Resolve Environment`** (so the main-branch guard and path validation run before any credential is used):
    1. `Azure OIDC Login`: `azure/login@v3` with only `client-id`/`tenant-id`/`subscription-id` from the existing secrets.
    2. `Verify Azure OIDC Authentication`: `az account show`, which fails the job at the auth boundary.
    3. `Setup Terraform`: `hashicorp/setup-terraform@v3`, `terraform_wrapper: false`, so Task 5.3 sees real exit codes and unmodified stdout.
    4. `Terraform Init (remote backend)`: `init -input=false -lockfile=readonly` in the resolved directory. `ARM_USE_OIDC` + `ARM_USE_AZUREAD` are set on this step only, so state access uses Entra ID and never a storage key. The committed lock file is used and never rewritten.
    5. `Terraform Validate`.
  - **Run summary**: adds the Terraform version, the auth mode and the backend status.
  - **Unchanged**: triggers, the `environment` input (choice `dev`, schedule default `dev`), the main-branch guard and environment resolution. There is still no job-level `environment:` key, so the OIDC subject stays `...:ref:refs/heads/main`, the existing FIC. No GitHub or Azure configuration changes are needed.
  - **`dev.tfvars`**: the resolve step checks that it exists and exposes it as `var_file`; `init`/`validate` take no var file, and it is first consumed by `plan` in Task 5.3.
  - **Not in 5.2**: no `plan`, `drift-engine analyze`, artifacts or drift semantics; no `apply`.
  - **Local validation**:
    - `check-jsonschema` (GitHub workflow schema) passes for both workflows.
    - YAML structure and security assertions all pass: exact permissions; no job `environment:`/`permissions`; `azure/login@v3` with exactly the three IDs; wrapper off; version 1.14.7; OIDC + AzureAD env on init; `-lockfile=readonly` and no `-backend=false`; step order guard → login → init → validate; no `apply`/`plan`/`destroy`/`import`/`drift-engine`/secret/key/SAS/password outside comments.
    - Offline `init -backend=false -lockfile=readonly` + `validate` on a scratch copy of `dev` with Terraform 1.14.7: OK, and the lock file is unchanged (its registry `zh:` hashes cover the linux runner).
    - `./scripts/validate.sh` passed.
    - The Run Summary step was executed locally and renders correctly.
    - Backend init with OIDC cannot be exercised locally (it needs a GitHub OIDC token).
  - **Real run #2 — FAILED** (id `36995005632`, `workflow_dispatch`, `main`, head `229e686`): <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/36995005632>.
    - **Passed**: Require main branch, Checkout, Resolve Environment, **Azure OIDC Login**, **Verify Azure OIDC Authentication**, Setup Terraform, **Terraform Init (remote backend)**. This is real evidence that OIDC login and remote-backend init work; init log text was not yet reviewed.
    - **Failed**: `Terraform Validate`, with `the cached package for registry.terraform.io/hashicorp/azurerm 5.7.0 (in .terraform/providers) does not match any of the checksums recorded in the dependency lock file`. Run Summary was skipped.
    - **Root cause**: the committed `terraform/environments/dev/.terraform.lock.hcl` held a single `h1:` hash (darwin_arm64) plus registry `zh:` hashes.
      - `init` verifies the downloaded zip against `zh:` (passes on Linux). It would normally record the platform's `h1:`, but `-lockfile=readonly` forbids it.
      - `validate` then checks the installed package against `h1:` only, finds no linux entry, and fails.
      - The local check missed it because it ran on darwin_arm64. `terraform-auth-test.yml` never hit it because its init is not readonly.
      - Reproduced locally: with this platform's `h1:` removed, readonly init exits 0 and validate fails with the identical error.
  - **Fix (approved 2026-10-02)**: ran `terraform -chdir=terraform/environments/dev providers lock -platform=linux_amd64 -platform=darwin_arm64 -platform=darwin_amd64` (registry download and checksum only; no Azure access).
    - The lock diff is exactly +2 `h1:` lines: linux_amd64 `h1:qLCQoAAScE4EqdO9QanAzdhTFFhtCX5LlvsPTevqpds=` and darwin_amd64 `h1:Cf19TigA8GkMlsJPRw+gMuypB45vk4/zmhhxQzOGVaU=`. Each was mapped by locking one platform at a time.
    - Unchanged: provider version `5.7.0`, constraint `~> 5.0`, all `zh:` hashes and the existing darwin_arm64 `h1:`.
    - The workflow is unchanged: `-lockfile=readonly` kept, same auth model.
  - **Re-validation (local)**:
    - Readonly `init -backend=false` + `validate` on a scratch copy pass, and the lock is not rewritten.
    - `./scripts/validate.sh` passed (lock unchanged afterwards).
    - Workflow schema and security assertions pass.
    - A linux/amd64 container check was not run (Docker daemon not running), so the linux fix is confirmed only by the next real GitHub run.

#### Task 5.3 — Automated Drift Engine Execution
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Execute plan generation and Python `drift-engine` inside GitHub Actions step.
- **Dependencies**: Task 5.2
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [x] Plan output generated and converted to JSON.
  - [x] Python engine produces `drift_report.json`.
  - [x] Step captures exit codes accurately. Exit 0 was proven in the real run; exit 2 and failure paths were proven by the local step harness (see Progress Notes).
- **Validation**:
  - [x] Workflow step succeeds and outputs drift summary in job logs: run #5 `36998087535`, see Completion Notes.
- **Implementation Notes**:
  - Pipeline distinguishes between process errors and valid drift findings.
- **Completion Notes**:
  - **Real GitHub/Azure validation**: run **#5**, id `36998087535`, <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/36998087535>.
    - Event `workflow_dispatch`, branch `main`, commit `ed84bac73dacd36a2cbef16b32a97a3827df0a34` (`feat: run plan evidence and drift-engine analyze in drift workflow`).
    - Job `Drift Detection (dev)` (id `110809307594`), 2026-10-02T10:54:47Z → 10:55:29Z. **Conclusion: success.** All 18 steps succeeded, including Setup Python, Install drift-engine, Generate Plan Evidence, Analyze Drift and Run Summary.
  - **Read from the job logs** (signed-in browser):
    - **Terraform Init (remote backend)**: "Successfully configured the backend "azurerm"!" and "Terraform has been successfully initialized!". This also closes the Task 5.2 log-confirmation gap.
    - **Generate Plan Evidence**: evidence directory `/home/runner/work/_temp/drift` (outside the checkout); `terraform plan (-detailed-exitcode)` → `terraform show -json` → "Plan succeeded: no pending changes (exit 0)" → "Valid plan evidence: terraform plan exit 0".
    - **Analyze Drift**: `has_drift=false [in_sync=1] severity=INFO`, `Report: /home/runner/work/_temp/drift/drift_report.json`; "resources: 1, drifted: 0, ambiguous: 0, pending output changes: false"; `in_sync module.resource_group.azurerm_resource_group.this["main"]`.
    - **Run Summary**: plan exit code `0`, drift status **none**, classification `{"in_sync":1}`, commit `ed84bac…`.
  - **Result**: the real `dev` resource group is in sync, so the workflow is green with drift status `none`.
    - A real exit-2 run (drift or a configuration change) has not been executed in CI. That path, and all failure paths, are covered by the local 15-case harness running the same step scripts.
  - **Annotations** (not errors): Node.js 20 deprecation (`actions/checkout@v4`, `actions/setup-python@v5`, `hashicorp/setup-terraform@v3` forced to Node 24); `ubuntu-latest` → Ubuntu 26 from 2026-10-19.
  - **No artifacts are uploaded yet** (Task 5.4). The evidence and the report exist only on the runner during the job.
- **Progress Notes (2026-10-02)**:
  - **New steps** in `.github/workflows/drift-detection.yml`, after Terraform Validate (only that file changed for 5.3; README lines updated):
    1. `Setup Python` (`actions/setup-python@v5`, 3.12).
    2. `Install drift-engine`: `pip install .`, runtime deps only.
    3. `Generate Plan Evidence` (id `evidence`): runs the existing Phase 3 `scripts/generate_plan_json.sh`, unchanged, with `TF_DIR` set to the resolved directory and `ARTIFACT_DIR=$RUNNER_TEMP/drift` (outside the checkout).
       - The script does init, `plan -detailed-exitcode -out` (refresh and lock on, `-lock-timeout=120s`), `show -json` of that same plan file, and the integrity gate.
       - `ARM_USE_OIDC`/`ARM_USE_AZUREAD` are set on this step and the 5.2 init step only.
    4. `Analyze Drift` (id `analyze`): `drift-engine analyze --plan … --manifest … --output $RUNNER_TEMP/drift/drift_report.json`. All classification is the engine's; the workflow only maps exit codes and prints the summary.
    5. `Run Summary` adds the plan exit code, drift status and classification counts.
  - **Exit-code handling**: each exit code is captured with `|| rc=$?` under GitHub's `bash -eo pipefail`.
    - **Script**: 0 = valid evidence. The plan exit code (0 or 2) is read from the manifest; any other value with exit 0 is rejected. 1 = detection failed. 64 = unusable `ARTIFACT_DIR`; any manifest found then is treated as stale and ignored.
    - **Terraform plan exit codes** are mapped by the script: 0/2 valid; 1 and other codes (e.g. 137) mean FAILED.
    - **Engine**: 0 = valid classification, drift or not. Anything else (1 rejected, 70 internal, 73 write, …) = UNKNOWN.
  - **Process failure vs drift**:
    - The job fails only for process failures: the evidence step on script ≠ 0, manifest outcome ≠ `succeeded`, or a modified provider lock; the analyze step on engine ≠ 0, an evidence failure, report outcome ≠ `succeeded` or a non-boolean `has_drift`. Each emits `::error:: … Drift status: UNKNOWN`.
    - Detected drift (`has_drift=true`) ends the step successfully with a `::warning::`.
    - Analyze also runs after a failed detection whenever a manifest exists, so a failed run gets an explicit `outcome: failed` / `has_drift: null` report (spec §8.2). It never reports "no drift".
    - Step outputs: `script_exit_code`, `manifest_present`, `outcome`, `plan_exit_code`, `engine_exit_code`, `has_drift`, `drift_status` (`detected` / `none` / `UNKNOWN`), `classification_counts`. No job-level `drift_detected` output (Task 5.5).
  - **`-lockfile=readonly` preserved**: the 5.2 init step still uses it. The script's own init has no such flag and the script refuses `TF_CLI_ARGS_init`, so the evidence step fails if `git diff` shows the committed `.terraform.lock.hcl` changed. The Phase 3 script is unchanged.
  - **On failure**, the last 50 lines of `plan.log` are printed in a collapsed group. This is Terraform's own `-no-color` output, which redacts sensitive values; `terraform-auth-test.yml` already prints full plans.
  - **Local validation**:
    - `check-jsonschema` and `actionlint` 1.7.12 with shellcheck 0.11.0 pass on both workflows.
    - Structure and security assertions pass: permissions unchanged; no job `environment:`; ARM env only on the init and evidence steps; the workflow's own `terraform` calls are `version`/`init`/`validate` only; no `apply`/`-auto-approve`/`-refresh=false`/`-target`/`-lock=false`/`TF_CLI_ARGS`/secrets/`continue-on-error`; no inline classification (`resource_drift`/`resource_changes`/`change.actions` absent).
    - **Step harness** (15 cases): the real evidence/analyze/summary scripts, extracted from the YAML and run with `bash --noprofile --norc -eo pipefail` like GitHub, against the real `generate_plan_json.sh` (in a scratch clone), the installed `drift-engine` and a fake `terraform` fed Phase 3 fixtures.
      - **Valid**: rc0 in_sync → none; rc2 external_drift → detected (warning, step green); rc2 config_change → none; rc0 converged_drift → detected. The summary renders for all four.
      - **Failed → UNKNOWN, job red**: rc1 with an errored plan; rc137; rc2 with `errored:true` JSON; rc2 with malformed JSON; rc0 with pending changes; rc2 with no changes; show exit 1; provider lock modified (engine 0 but still UNKNOWN); plan.json corrupted between steps (engine re-gate → 1); stale non-empty `ARTIFACT_DIR` (64, stale manifest ignored, analyze skipped); non-dev var file.
      - All logged Terraform calls are `version`/`init`/`plan -var-file=dev.tfvars -input=false -no-color -lock-timeout=120s -detailed-exitcode -out=…`/`show -no-color -json`. No forbidden flags.
    - `pytest --cov=src/drift_engine tests/`: 319 passed, 99.87% coverage (Python 3.13). `./scripts/validate.sh` passed.
  - **Not exercised locally**: real Azure plan/OIDC inside the script, Python 3.12 on the runner, and `pip install .` on Linux.

#### Task 5.4 — Structured Artifact Storage & Pipeline Handling
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Publish the contract drift report (`drift_report.json`) and the run manifest (`detection_run.json`) as a downloadable workflow artifact for downstream inspection. Raw Terraform plan evidence (`tfplan`, `plan.json`, `plan.log`) is still generated, validated and consumed by `drift-engine` during the workflow; it is kept only on the ephemeral GitHub runner and is not uploaded or otherwise persisted by this public-repository workflow.
- **Dependencies**: Task 5.3
- **Files/Areas**: `.github/workflows/drift-detection.yml` (plus `docs/drift-detection-spec.md` §8.3 and `README.md` wording)
- **Acceptance Criteria**:
  - [x] Artifact `drift-report-<run_id>` uploaded using `actions/upload-artifact@v4`, containing exactly `drift_report.json` and `detection_run.json`.
  - [x] Raw Terraform plan/state evidence (`tfplan`, `plan.json`, `plan.log`) is not uploaded; it stays on the ephemeral runner, and the evidence model is unchanged (generated, integrity-gated and analyzed in the workflow).
  - [x] Uploaded only for valid evidence (Generate Plan Evidence and Analyze Drift both succeeded, drift or no drift), from this run's `$RUNNER_TEMP/drift`; never failed or stale evidence. Valid path proven in the real run; skip on failure proven by the local harness.
  - [x] Retention policy set to 30 days.
- **Validation**:
  - [x] Download and inspect artifact from completed workflow run; confirm it contains only `drift_report.json` and `detection_run.json`. See Completion Notes.
- **Implementation Notes**:
  - Artifacts serve as input for Phase 6 AI analysis. Phase 6 consumes `drift_report.json`, not raw plans.
  - **Scope revision (2026-10-02, user-approved)**: "raw plan" removed from the published artifact because the repository is public and plan files can contain clear-text sensitive and state values (spec §8.3). The published report is the contract report (sensitive values redacted by the engine).
  - **Known limitation**: the report is not free of identifiers. Values Terraform does not flag sensitive are not redacted, so when a resource's `id` attribute changes (deletion, replacement, removal) its before/after values, including the subscription ID, appear in `attribute_changes`.
  - **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: the known limitation above is resolved by an internal/public split, not by changing this report.
    - The engine's `drift_report.json` (the Phase 3/4 contract) is unchanged, but it becomes **internal**: runner-only (or local), never uploaded, and never hashed into anything public.
    - The `drift-report-<run_id>` artifact carries the deterministic, verified **public** drift report (`public_version: "1"`, still named `drift_report.json`) plus `detection_run.json`.
    - If the public report cannot be produced and verified, `drift-engine analyze` fails (fixed code, exit 70). The existing Task 5.5 mapping makes the result UNKNOWN, and nothing is uploaded.
    - Wiring: Task 9B.5. The record below is historical.
- **Progress Notes (2026-10-02)**:
  - **Workflow**: one new step, `Upload Drift Report`, between Analyze Drift and Run Summary.
    - `actions/upload-artifact@v4`; `name: drift-report-${{ github.run_id }}`.
    - `path` lists exactly `${{ runner.temp }}/drift/drift_report.json` and `${{ runner.temp }}/drift/detection_run.json` (no globs, nothing from the checkout).
    - `retention-days: 30`; `if-no-files-found: error`; `overwrite: true` so a re-run attempt replaces its own run's artifact instead of failing on the name.
    - Default `success()` condition: the step runs only when Generate Plan Evidence and Analyze Drift both succeeded.
  - **Run Summary**: gains an `Artifact` row.
  - **Unchanged**: permissions, OIDC, Terraform, `drift-engine` and exit-code logic. Raw plan evidence is still generated, gated and analyzed.
  - **Docs**: spec §8.3 gains a "CI publication (Task 5.4)" paragraph. README: status line, Planned list, and the known limitation (artifact contents, no raw evidence persisted, `id` identifier caveat).
  - **Local validation**:
    - `check-jsonschema` and `actionlint` 1.7.12 + shellcheck 0.11.0 pass.
    - Assertions pass: exactly one upload step, with the exact name, two exact paths (no `tfplan`/`plan.json`/`plan.log`/globs/workspace), retention 30, no `if`/`continue-on-error`; step order Analyze → Upload → Summary; earlier controls unchanged (permissions, no job `environment:`, `-lockfile=readonly`, ARM env only on init and evidence, no apply/forbidden flags/secrets).
    - **15-case step harness** with an upload-selection check:
      - Valid runs 01–04 (rc0 in_sync, rc2 external_drift, rc2 config_change, rc0 converged_drift): upload selects exactly `drift_report.json` + `detection_run.json`, while `plan.json`, `plan.log` and `tfplan` sit in the same directory and are **not** selected. The manifest and report carry the current `run_id`.
      - Failure cases 05–15 (plan errors, integrity failures, show failure, lock change, tampered JSON, stale directory, non-dev var file): upload skipped.
    - `./scripts/validate.sh` passed. No Python code changed.
- **Completion Notes**:
  - **Real GitHub validation**: run **#6**, id `37000123885` (attempt 1), <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37000123885>.
    - Event `workflow_dispatch`, branch `main`, commit `4ad55e741f684bbb406fa896077ea4d58438c486` (`feat: upload drift report and run manifest as workflow artifact`), 2026-10-02T11:16:42Z → 11:17:32Z. **Conclusion: success.**
    - All 19 steps succeeded, including Generate Plan Evidence, Analyze Drift, **Upload Drift Report** and Run Summary.
  - **Artifact (Actions API)**: exactly one, `drift-report-37000123885` (id `11223520945`), 1,232 bytes, created 2026-10-02T11:17:27Z, expires 2026-11-01T11:17:26Z (30 days), digest `sha256:fe74b8c427ef27f0d4cdea013b79a523e5153da954a172eb2703a700be54c942`.
  - **Downloaded and inspected**: the zip was downloaded through the signed-in browser. Its SHA-256 equals the API digest.
    - `unzip -Z1` lists exactly 2 entries, `drift_report.json` (2,095 B) and `detection_run.json` (439 B). No `tfplan`, `plan.json`, `plan.log` or any other file.
    - Both files are valid JSON.
    - Manifest: `outcome: succeeded`, `plan_exit_code: 0`, `show_exit_code: 0`, `terraform_version: 1.14.7`, `environment: dev`, `backend_key: dev.tfstate`, `git_commit: 4ad55e7…`, `run_id: github-37000123885-1`, 11:17:08Z → 11:17:25Z.
    - Report: `outcome: succeeded`, `has_drift: false`, `failure: null`, `in_sync` = 1 (`module.resource_group.azurerm_resource_group.this["main"]`, no attribute changes). Its `run` block repeats the manifest's run ID, commit, exit codes and timestamps, and its `plan` block carries metadata only (`format_version 1.2`, `errored false`, `complete true`, plan timestamp 11:17:19Z).
    - Run ID and attempt, commit and timestamps match the actual run.
    - **No raw plan or state content**: the report's top-level keys are only the contract keys; no `prior_state`/`resource_changes`/`resource_drift`/`configuration`/`planned_values`/`variables`/`*_sensitive` keys in either file; no subscription paths, GUIDs, tenant, client or secret strings.
  - **Plan/drift result**: plan exit 0, drift status `none` (`dev` in sync).
  - **Not exercised in CI**: an artifact from a real drifted run (exit 2) and the skip-on-failure path. Both are covered by the local harness; Task 5.5 owns failure-path validation.
  - **Annotations** as in Task 5.3 (Node.js 20 deprecation; `ubuntu-latest` → Ubuntu 26 notice); none from upload-artifact.

#### Task 5.5 — Pipeline Error Handling & Failure Reporting
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Ensure execution failures (auth failure, terraform syntax errors) fail the job, while detected drift is reported without failing execution unexpectedly.
- **Dependencies**: Task 5.4
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [x] Infra/CLI failures cause job status to fail (red).
  - [x] "Drift detected" sets pipeline output variable `drift_detected=true` while step completes successfully.
- **Validation**:
  - [x] Test execution with valid plan, drifted plan, and syntax error. The valid plan was run for real (run #7). The drifted plan and the syntax error were run in the local job simulator (real `terraform` for the syntax error); by user decision, Azure was not mutated and broken Terraform was not pushed to `main`.
- **Implementation Notes**:
  - Clear separation of operational failure vs drift finding.
- **Progress Notes (2026-10-02)**:
  - **Existing behavior kept (Task 5.3)**: every infra/CLI failure already fails its step (auth: `azure/login` / `az account show`; init/validate; install; evidence script ≠ 0 or invalid manifest; engine ≠ 0 or invalid report), and detected drift already ends Analyze Drift successfully with a `::warning::`. No classification logic was added to the workflow.
  - **New in 5.5** (`.github/workflows/drift-detection.yml` only):
    - **`drift_detected` output**: the Analyze Drift step writes `drift_detected=true`/`false` only on the valid path (engine 0, evidence success, report `succeeded`, boolean `has_drift`), and `drift_detected=unknown` otherwise.
    - **Job outputs**: `drift_detected: ${{ steps.analyze.outputs.drift_detected || 'unknown' }}` and `drift_status` (`detected`/`none`/`UNKNOWN`). If analysis never ran, the job output is `unknown`, never `false`. A valid `"false"` is a non-empty string and passes through `||`.
    - **Failure reporting**: Run Summary now runs with `if: ${{ !cancelled() }}`, so failed runs also get a summary. It shows Result (`VALID` / `FAILED - drift status UNKNOWN`), the first failed stage (from step `outcome`s; steps gained ids for this), drift status, `drift_detected`, and Backend and Artifact rows that reflect what actually happened. It never changes the job's red/green status and exits 0 in every tested case.
    - **Unchanged**: upload condition, artifact contents, permissions, OIDC, `-lockfile=readonly`, exit-code mapping.
  - **Local validation**:
    - `check-jsonschema` and `actionlint` 1.7.12 + shellcheck 0.11.0 pass.
    - Structure/security assertions pass: job outputs exact; `drift_detected=false` is never written literally (only `${has_drift}` on the valid path or `unknown`); only Analyze Drift and Run Summary have non-default `if`; Upload unchanged; step ids unique and all referenced; permissions, ARM env scope, lockfile and forbidden-flag checks unchanged.
    - `pytest --cov=src/drift_engine tests/`: 319 passed, 99.87%. `./scripts/validate.sh` passed.
    - **Job simulator** (14 cases; results in `.artifacts/task-5.5-validation/`): runs the real `run:` scripts from the YAML in order (guard, Resolve Environment, Generate Plan Evidence with the real `generate_plan_json.sh` and a fake `terraform` on Phase 3 fixtures, Analyze Drift with the installed `drift-engine`, Run Summary) under GitHub's step-condition semantics, then derives the job conclusion and evaluates the job-output expressions. The upload step is simulated from its declared paths.
      - **Required cases**: (1) valid in-sync plan → job success, `drift_detected=false`, status `none`, artifact; (2) valid drifted plan (exit 2, external drift) → job **success**, `drift_detected=true`, status `detected`, artifact; (3) a real Terraform syntax error (malformed resource block; real `terraform init -backend=false` exits 1, "Missing name for resource") → job **failure** at Terraform Init, `drift_detected=unknown`, no artifact.
      - **Also valid**: converged drift (exit 0) → `true`; config change (exit 2) → `false`; both green.
      - **Also failed → red, `unknown`, no artifact**: auth failure, install failure, plan exit 1, plan exit 137, malformed plan JSON, `errored:true` JSON, `show` failure, Analyze Drift failure, and provider-lock modification. In the lock case the engine itself returned 0 with `has_drift=true`, yet `drift_detected` stays `unknown`.
- **Completion Notes**:
  - **Real GitHub validation (valid in-sync path)**: run **#7**, id `37002989936`, <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37002989936>.
    - Event `workflow_dispatch`, branch `main`, commit `188aebdbf4ae9f3b5c9256c00f5ff65e40de6364` (`feat: add drift_detected output and failure reporting to drift workflow`).
    - Job `Drift Detection (dev)` (id `110824725713`), 2026-10-02T11:48:01Z → 11:48:47Z. **Conclusion: success.** All 19 steps succeeded.
  - **Logs** (signed-in browser):
    - Analyze Drift: `has_drift=false [in_sync=1] severity=INFO`; "resources: 1, drifted: 0, ambiguous: 0, pending output changes: false"; `in_sync module.resource_group.azurerm_resource_group.this["main"]`.
    - Run Summary: "Drift detection for 'dev' (workflow_dispatch): result VALID; drift_detected=false; failed stage: none".
  - **Run Summary table**: Result **VALID**; Failed stage none; Drift status **none**; `drift_detected` `false`; Backend "AzureRM remote state, initialized and validated"; Plan exit code `0`; Classification `{"in_sync":1}`; Artifact `drift-report-37002989936` (drift_report.json + detection_run.json, 30 days); commit `188aebd…`.
  - **Artifact behavior unchanged**: exactly one artifact, `drift-report-37002989936` (id `11224194401`, 1,233 B, expires 2026-11-01T11:48:42Z, `sha256:ecfa15c3…4989e26`).
  - **`drift_detected` evidence**: the summary reads `steps.analyze.outputs.drift_detected` with the same `|| 'unknown'` fallback as the job output and printed `false`. The job-level output itself is not displayed by the GitHub UI and has no consuming job yet.
  - **Not exercised for real (by user decision)**: real drift (would require an Azure change) and a real syntax error on `main`. Both, plus auth, install, plan, integrity, lock and analysis failures, are covered by the 14-case local job simulator (Progress Notes).
  - **Annotations** (not errors): Node.js 20 deprecation (now also listing `actions/upload-artifact@v4`); `ubuntu-latest` → Ubuntu 26 notice.
  - **Phase 5 complete**: Tasks 5.1–5.5 all 🟢.

---

### PHASE 5A — Dev Infrastructure Expansion (pre-Phase 6)
**Status**: 🟢 COMPLETED

The dedicated infrastructure expansion anticipated by the Phase 1 scope note: adds networking resource types so drift detection (and later AI analysis) can be exercised on more than the single Resource Group. Key Vault, an application Storage Account and any compute remain out of scope.

#### Task 5A.1 — VNet, Subnet & NSG in the Dev Environment
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Add one Virtual Network, one Subnet and one Network Security Group associated with that Subnet to the dev environment, inside the existing Resource Group `aitdd-dev-main-rg`, leaving the Resource Group unchanged.
- **Dependencies**: Phase 5
- **Files/Areas**: `terraform/modules/network/` (new), `terraform/environments/dev/{main,variables,outputs}.tf`, `terraform/environments/dev/dev.tfvars`
- **Acceptance Criteria**:
  - [x] Reusable `network` module (VNet + `for_each` subnets/NSGs + subnet-NSG association), driven by a `virtual_networks` map in `dev.tfvars`; location and resource group come from the existing Resource Group module (looked up by key).
  - [x] No Key Vault, application Storage Account, compute or other resources; backend, OIDC, drift engine and workflow unchanged.
  - [x] Real `terraform plan` against the remote backend shows only the 4 intended creates and no Resource Group change.
  - [x] `terraform apply` executed **only after explicit user approval**; post-apply plan is clean (exit 0).
- **Implementation Notes**:
  - Names: `aitdd-dev-main-vnet` (10.10.0.0/16), `aitdd-dev-main-app-snet` (10.10.1.0/24), `aitdd-dev-main-app-nsg`.
  - NSG declares `security_rule = []` (azurerm 5.7.0 marks it Optional+Computed, so omitted rules would hide out-of-band rules from the plan); Azure default rules only. Subnet sets `default_outbound_access_enabled = false` explicitly to avoid provider/API default ambiguity.
  - Known limitation: the VNet's inline `subnet` attribute is Optional+Computed and is left unset (subnets are separate resources), so a subnet created outside Terraform in this VNet is not visible to the plan.
- **Progress Notes (2026-10-02)**:
  - Offline: `terraform fmt`, `init -backend=false -lockfile=readonly` + `validate` pass; lock file unchanged; `./scripts/validate.sh` passes; `pytest` 319 passed. Mocked-provider `terraform test` (scratchpad only, not committed) with the real `dev.tfvars` confirms names, CIDRs, single association, empty NSG rule set, and rejection of an undefined NSG key / invalid CIDR.
  - Drift run #9 (2026-10-02) found `external_drift` on the Resource Group: the user's intentional `owner=Harsh` drift-test tag. The user removed it in the Azure Portal before the real plan.
  - **Real plan (2026-10-02, user-approved, local Azure CLI auth, `ARM_USE_AZUREAD=true`)**: run against commit `f1b2ccd` plus the uncommitted Task 5A.1 changes. `init -lockfile=readonly` against the remote `dev.tfstate`; `plan -detailed-exitcode -var-file=dev.tfvars` exit **2**; JSON `errored=false`, `complete=true`. **Plan: 4 to add, 0 to change, 0 to destroy**: create `azurerm_virtual_network` (`aitdd-dev-main-vnet`, 10.10.0.0/16), `azurerm_subnet` (`aitdd-dev-main-app-snet`, 10.10.1.0/24, default outbound false), `azurerm_network_security_group` (`aitdd-dev-main-app-nsg`, `security_rule = []`), and the subnet-NSG association, all in `aitdd-dev-main-rg` / `centralindia` with the common tags. Resource Group **no-op** (before == after, tags back to the 3 common tags); `resource_drift` empty; no replace/delete. No warnings. `Microsoft.Network` is Registered. Evidence (tfplan, plan.json, logs, `TF_DATA_DIR`) kept in the session scratchpad only; lock file unchanged.
- **Completion Notes**:
  - **Apply (user-approved)**: the exact reviewed saved plan was applied: `Apply complete! Resources: 4 added, 0 changed, 0 destroyed` (NSG, VNet, subnet, association). No other Azure change.
  - **Post-apply state refresh**: the first fresh plan printed "No changes" (exit 0) but its JSON still carried 2 `resource_drift` entries, which the engine classified as `converged_drift` (has_drift=true, MEDIUM). They were provider-computed values filled in after creation: subnet `network_security_group_id` (set by the later association) and `service_endpoint_policy_ids` (null→[]), and the VNet's computed `subnet` list. A `plan -refresh-only` showing exactly those attributes (no resource actions, no output changes) was reviewed and then applied as the saved plan with user approval: `0 added, 0 changed, 0 destroyed` (state only).
  - **Final verification** (via `scripts/generate_plan_json.sh` + `drift-engine analyze --manifest`, evidence in the session scratchpad only): manifest `outcome=succeeded`, `plan_exit_code=0`; plan.json `errored=false`, `complete=true`, `resource_drift` empty, all actions no-op; "No changes. Your infrastructure matches the configuration."; report `outcome=succeeded`, **`has_drift=false`, `in_sync=5`**, severity INFO. Provider lock file unchanged.
  - **Lesson for later phases**: creating a subnet and its NSG association in one apply leaves computed attributes stale in state until a refresh is persisted; the engine reports that as `converged_drift`. After applies that add associated network resources, run a reviewed `apply -refresh-only` (or expect one converged-drift scan).

### PHASE 6 — LangGraph AI Analysis Engine
**Status**: 🟢 COMPLETED — returned to 🟢 on 2026-10-11 when Task 9B.6 passed (reopened 2026-10-04 for a requirement gap, closed by Phase 9B; see the Task 9B.6 completion notes)

Phase 6 constructs the AI analysis engine using LangGraph, LangChain, and OpenAI-compatible models to analyze detected drift, evaluate security and cost implications, and recommend remediation steps based on strict empirical evidence.

> **Requirement-gap amendment (2026-10-04, user decision):**
> - **Evidence**: a real Azure test produced a report without the required content. The user added a tag to `aitdd-dev-main-rg` in the Azure Portal; drift run `37197574080` detected it; the AI artifact `ai-analysis-report-37197574080` holds no Azure evidence, no WHO/WHEN, no AI analysis (CI runs with `AI_LLM_PROVIDER=none`) and no recommended action.
> - **Gap**: Tasks 6.1–6.7 met their recorded acceptance criteria, but the phase objective is not delivered end to end:
>   - `run_analysis` takes only the drift report (no Azure evidence input);
>   - the report contract fixes `attribution` to `{actor: unknown, confirmed: false, pending: phase_7_activity_log}`;
>   - the report has no WHEN (event time vs detection time);
>   - remediation options are deliberately unranked (no recommended action);
>   - without an LLM there is no investigation narrative.
> - **Ownership**: Phase 9B (Tasks 9B.4–9B.6, incl. 9B.4A) owns the remaining work. The task records below are kept unchanged as history; amendment lines point to the superseding 9B task.
> - **Closure**: Phase 6 returns to 🟢 when Task 9B.6 passes.

#### Task 6.1 — LangGraph Infrastructure & LLM Configuration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Initialize Python LangGraph state graph framework and set up OpenAI / Azure OpenAI client providers with environment configuration.
- **Dependencies**: Tasks 4.3, 5.4
- **Files/Areas**: `src/ai_engine/config.py`, `src/ai_engine/graph.py`
- **Acceptance Criteria**:
  - [x] `AiState` TypedDict defined for LangGraph state propagation.
  - [x] Config handles API keys, endpoint URLs, and model deployment names safely.
  - [x] Graceful fallback when LLM API keys are missing or unreachable.
- **Validation**:
  - [x] `pytest tests/test_ai_config.py` passes.
- **Implementation Notes**:
  - Robust LLM integration layer.
  - New package `src/ai_engine/` (`__init__.py`, `config.py`, `graph.py`, `py.typed`). LangGraph/LangChain deps live in a new opt-in `ai` extra (`langgraph>=1.0,<2`, `langchain-openai>=1.0,<2`); `requirements.txt` now installs `.[dev,ai]`. The drift workflow's `pip install .` is unchanged and pulls no LLM stack; `ai_engine.config` imports without the extra.
  - **Config** (`load_config(env)`): environment variables only, no `.env` reading. LLM use is **opt-in** via `AI_LLM_PROVIDER` (`none` default | `openai` | `azure_openai`), so credentials merely present on a runner never send evidence to an LLM. `openai` needs `OPENAI_API_KEY` + `AI_LLM_MODEL` (optional `OPENAI_BASE_URL` for OpenAI-compatible endpoints); `azure_openai` needs `AZURE_OPENAI_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_DEPLOYMENT` (optional `AZURE_OPENAI_API_VERSION`, default `2024-10-21`). Tunables: `AI_LLM_TEMPERATURE` (default 0), `AI_LLM_TIMEOUT_SECONDS` (60), `AI_LLM_MAX_RETRIES` (2; changed to **0**, i.e. opt-in, in the Task 6.3 final review). No default model name is hard-coded.
  - **Safety**: keys held as `SecretStr` (absent from repr/str/`summary()`/log events); endpoints must be http(s) with a host, no userinfo, no query/fragment, https except localhost; error messages never echo a URL value. Missing credentials → disabled config with a reason (no exception); malformed values (unknown provider, bad numbers, unsafe URL) → `AiConfigError`.
  - **Clients**: `create_chat_model(config)` returns `(ChatOpenAI|AzureChatOpenAI, None)` or `(None, reason)` (disabled, extra not installed, client construction failure); no network call at construction.
  - **Graph**: `AiState` (total=False) separates evidence from inference: `drift_report` (deterministic input, never modified), `inferences` (model output keyed by node, dict-merge reducer), `llm` (`LlmStatus`: available/provider/model/reason), `warnings` (append reducer). `build_graph()` compiles START → `initialize` → END; the LLM is bound by closure, not stored in state. `invoke_llm()` converts an absent/unreachable/failing LLM (`openai.OpenAIError`, `TimeoutError`, `ConnectionError`) into an `LLMCallResult` carrying only the exception type; programming errors still raise. Analysis nodes are left to Tasks 6.2–6.6.
- **Completion Notes**:
  - Validation in a session-scratchpad venv (Python 3.14, langgraph 1.2.12, langchain-openai 1.6.7, openai 3.23.0): `pytest tests/test_ai_config.py` **40 passed**; full suite **359 passed** (607 subtests); `--cov=src/drift_engine` gate 99.87% (≥85); `ai_engine` coverage 98%.
  - Unreachable endpoint verified for real against a closed port on 127.0.0.1 (`max_retries=0`): returns `LLM call failed (OpenAIConnectionError)`, no exception. No real LLM or external network was contacted.
  - Core-only install (`pip install .` + pytest, no `ai` extra): `drift-engine` CLI works, `langgraph` absent, `test_ai_config.py` 27 passed / 13 skipped (graph/client tests marked `requires_ai`).
  - No Terraform, Azure, drift-engine or GitHub Actions changes.
  - **Post-review follow-up (2026-10-02)**, from a focused review of this task:
    - *Evidence immutability enforced* (was convention only; a probe showed a node could mutate the caller's nested data and overwrite `drift_report`). `drift_report` now uses the reducer `write_once_evidence`: it accepts the graph input once and deep-copies it via `freeze_evidence` into `FrozenDict`/`FrozenList` (dict/list subclasses whose mutating methods raise `EvidenceMutationError`; still JSON-serializable and accepted by the strict `DriftReport` model). Any later write to `drift_report` raises `EvidenceMutationError`; non-JSON values are rejected. `initialize` now also rejects an empty/unset report.
    - *`invoke_llm` hardening*: AzureChatOpenAI raises a plain `ValueError` when Azure's content filter blocks a response; that exact type + message (`AZURE_CONTENT_FILTER_MESSAGE`) now returns `LLMCallResult(error="LLM response blocked by content filter")`. Every other `ValueError` (including subclasses and other messages) still raises. Blocked prompts already arrive as `openai.BadRequestError`.
    - *Setup docs*: `pyproject.toml` header, `requirements.txt` header and the README install snippet now distinguish `.[dev]` (drift engine only, AI tests skipped) from `.[dev,ai]` (= `requirements.txt`).
    - Validation: `pytest tests/test_ai_config.py` **76 passed** (adds nested-mutation, top-level replacement, per-method blocking, copy/pickle/JSON, non-JSON rejection, a real fixture report validated by `DriftReport`, and an AzureChatOpenAI content-filter regression via `httpx.MockTransport`); full suite **395 passed** (607 subtests); `drift_engine` coverage gate 99.87%; `ai_engine` coverage 97%. Core-only install: no LLM packages, 27 passed / 49 skipped, CLI works.

#### Task 6.2 — Drift Parsing & Resource Identification Nodes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Implement LangGraph node `parse_drift` to read `drift_report.json` and populate graph state with structured resource diffs.
- **Dependencies**: Task 6.1
- **Files/Areas**: `src/ai_engine/nodes/parse_drift.py`
- **Acceptance Criteria**:
  - [x] Extracts target resource types, addresses, and attribute changes into graph memory.
  - [x] Generates initial resource summary list.
- **Validation**:
  - [x] Test node execution with sample `drift_report.json`.
- **Implementation Notes**:
  - Deterministic state preparation node.
  - New `src/ai_engine/nodes/{__init__,parse_drift}.py`; wired in `src/ai_engine/graph.py` (START → `initialize` → `parse_drift` → END). No LLM call, network or Terraform access; the module imports without the `ai` extra.
  - **Contract reuse, no second schema**: `parse_drift` validates `AiState.drift_report` with `drift_engine.models.DriftReport` (strict, mirrors `schemas/drift_report.schema.json`). `load_drift_report(path)` reads a `drift_report.json` file (rejecting invalid JSON and NaN/Infinity) and validates it the same way. Contract violations raise `DriftReportError`, whose message lists field locations only (pydantic's message would quote values).
  - **Output** `AiState.parsed_drift` (`ParsedDrift`): `outcome`, `has_drift`; `resources` = every non-`in_sync` resource as the contract's own `DriftItem` JSON (`model_dump(mode="json")`, attribute changes with state/real/desired views); `resource_types` = sorted types of those; `resource_summaries` = value-free `ResourceSummary` per resource (address, type, classification, action, drift_action, `is_drift`, changed attribute names, change and redacted counts, ambiguous). All classification fields are copied from the report; `is_drift` is the classifier's own rule (`drift_actions` present), and its total equals `summary.drifted_resources` on every fixture.
  - **Separation/immutability**: `parsed_drift` is deterministic derived data, separate from `drift_report` (evidence) and `inferences` (AI output). Its channel uses the same write-once reducer as `drift_report` (Task 6.1 reducer generalized to `_write_once(field)`): frozen on first write, any later write or in-place change raises `EvidenceMutationError`.
  - A `failed` report (drift status unknown) is valid input: empty `parsed_drift` plus a warning naming the failure source/stage. Log event `drift_parsed` carries counts and type names only.
  - Severity is intentionally absent: `drift_engine.severity` needs the raw plan, and Phase 6 consumes only `drift_report.json` (Task 5.4). *(Superseded by Task 6.2A: severity is now in the report and copied into `ResourceSummary.severity`.)*
- **Completion Notes**:
  - Validation (session-scratchpad venv): `tests/test_ai_parse_drift.py` **44 passed**: the node and the full graph run on a sample `drift_report.json` for every fixture scenario (11, incl. `failed_run`), written to disk and loaded with `load_drift_report`, generated by drift_engine from `tests/fixtures/plan_evidence` so samples always match the contract; exact expected output for `external_drift`; in_sync/config_change/resource_added targeting; contract violations rejected without echoing values; bad files rejected; an LLM stub that fails if called proves no LLM use; later nodes cannot modify or replace `parsed_drift`; exact graph edges.
  - `tests/test_ai_config.py` (Task 6.1) updated to use a real contract report instead of a non-contract stand-in, now required because the graph validates the report: 76 passed. Full suite **439 passed** (607 subtests); `drift_engine` coverage gate 99.87%; `ai_engine` 98% (`parse_drift.py` 100%). Core-only install: no LLM packages, 55 passed / 65 skipped.
  - No Terraform, Azure, drift_engine or GitHub Actions changes.

#### Task 6.2A — Pre-6.3 Prerequisites: Nested Redaction Fix & Deterministic Severity in the Report
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Close the blocking findings of the Task 6.3 design review before any LLM call: fix sensitive values leaking through list/nested-block values, and make the deterministic `drift_engine.severity` rating part of the `drift_report` contract so later AI nodes consume it instead of deciding it.
- **Dependencies**: Task 6.2; Task 6.3 design review (2026-10-02, accepted)
- **Files/Areas**: `src/drift_engine/{comparator,classifier,models,formatters}.py`, `schemas/drift_report.schema.json`, `schemas/examples/drift_report.json`, `src/ai_engine/nodes/parse_drift.py`, affected tests, `docs/drift-detection-spec.md`, `README.md`
- **Acceptance Criteria**:
  - [x] A value emitted whole (list / nested block) whose sensitivity mask flags anything inside it is redacted in every view; regression tests prove it.
  - [x] Every attribute change, resource and summary of a succeeded report carries the deterministic severity from `drift_engine.severity` (no second implementation).
  - [x] Schema, models, example, tests and docs updated consistently; existing classification output otherwise unchanged.
  - [x] Plan/spec record: deterministic severity is authoritative; AI may explain but not lower/replace it; Task 6.3 `classify_drift` = deterministic security-relevant routing.
- **Validation**:
  - [x] Focused regression tests, full suite, schema/model agreement (incl. random mutations), fuzz, core-only install.
- **Out of scope**: LLM evidence builder, `analyze_security`, any LLM call (Task 6.3).
- **Completion Notes**:
  - **Redaction fix** (`comparator._walk`): descending still requires a flag at the node itself, but a node emitted **whole** (a list, i.e. every nested block in plan JSON, or a scalar/undescended object) is now redacted when any mask flags it *or anything inside it* (`_contains_true`), in all three views, `redacted: true`. Spec §8.2 already required this; the old code only checked `mask is True` at the list node, so `{"site_config": [{"password": true}]}` leaked both values. Every existing fixture report is byte-identical after the fix (the dev resources have no sensitive fields inside lists, so earlier published artifacts are not expected to have leaked; not re-verified against past artifacts).
  - **Severity in the report** (`classification_version` **"1" → "2"**): `classifier._add_severity` runs the existing `comparator.compare_plan(parsed, configured_attributes(plan))` and `severity.plan_severity(...)` while the raw plan is available, then annotates: per attribute change `severity` `{level, rules}` and `assessment` `{category, noise_rule}`; per resource `severity` `{level, reasons}`; `summary.highest_severity` and `summary.severity_counts`. A failed report carries none (drift unknown, never `INFO`). A comparator/report change mismatch raises `RuntimeError` instead of attaching a mis-attributed rating. No rating logic was copied; ratings on all fixtures equal the Task 4.5 real-data results (tags `LOW`, deletion/replace `HIGH`, create/delete `MEDIUM`, in-sync `INFO`).
  - **Backward compatibility**: purely additive — on all 11 fixtures, removing the new fields and resetting the version reproduces the pre-change report byte for byte. The version is bumped because the new fields are required, so v2 readers (models/schema/`ai_engine`) reject v1 reports with a `classification_version` error; old v1 artifacts must be regenerated to be analysed. Top-level keys and every v1 field are unchanged; the drift workflow is untouched (it produces v2 automatically from the same commit).
  - **AI side**: `parse_drift` copies `severity.level` into each `ResourceSummary` (the full `{level, reasons}` and per-change ratings stay in the contract `resources`). A test proves it copies rather than computes (an injected `CRITICAL` passes through), and an AST test proves no `ai_engine` module imports `drift_engine.severity`, `.comparator` or `.parser`, so `plan.json` stays out of the AI workflow.
  - **Known duplication (follow-up, not a blocker)**: `drift-engine analyze --format console` still rates the plan a second time for its view (same function, same inputs); a new test pins console ratings == report severity on every fixture. Switching the console renderer to read the report would change formatter internals beyond this task.
  - **Validation** (session-scratchpad venv): new `TestNestedSensitiveRedaction` (7 tests, 12 subtests; 11 of them fail against the pre-fix comparator) plus report-level, model (`sensitive_block` variant, severity typed access, 16 new invalid cases in both the model and the schema) and classifier severity tests; full suite **453 passed** (667 subtests); `drift_engine` coverage gate 99.87% (`classifier`/`comparator`/`models` 100%); `ai_engine` 98%; `python -m unittest discover -s tests` OK (327 tests); schema/model agreement incl. 3,000 random mutations passes. **Ad hoc fuzz** (scratchpad only): 20,000 mutated real plans, half with a secret planted inside a nested block and flagged in a random mask shape, through parse → classify → severity → models + schema: 0 unhandled exceptions, 0 leaks in 6,125 planted-secret reports, models and schema agree on all; the same harness detects the leak immediately on the pre-fix comparator. 172 mutated plans break the contract only in fuzzed `plan` header fields (pre-existing; the CLI reports them as contract violations). Core-only install: no LLM packages, 381 passed / 69 skipped, `drift-engine analyze` writes a v2 report.
  - No Terraform, Azure or GitHub Actions changes; no LLM calls.

#### Task 6.3 — Classification & Security Analysis Nodes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Implement LangGraph nodes `classify_drift` and `analyze_security` to evaluate compliance and security exposure.
- **Dependencies**: Task 6.2
- **Files/Areas**: `src/ai_engine/nodes/security_analysis.py`
- **Acceptance Criteria**:
  - [x] Analyzes firewall rule removals, open ports, public storage access, or disabled encryption.
  - [x] Assigns security impact rating backed by specific attribute evidence.
- **Validation**:
  - [x] Test node with security-drift report.
- **Implementation Notes**:
  - AI must explicitly cite attribute evidence in prompt response.
  - **Scope clarification (Task 6.3 design review, 2026-10-02):**
    - `classify_drift` is **deterministic routing**, not drift re-classification: it selects the security-relevant changes (from the report's severity rules, redacted changes and security-sensitive types) into a deterministic, write-once state field. Terraform/engine classifications are never re-decided.
    - The **security impact rating is the report's deterministic severity** (Task 6.2A, authoritative). `analyze_security` may add an AI-assessed impact and explanation, labelled inference and stored in `inferences`, shown next to but never lowering or replacing the deterministic level.
    - "Cite attribute evidence" is **enforced deterministically**: every AI finding must cite (address, path) pairs that exist in `parsed_drift`; findings citing anything else are dropped.
    - Prerequisites still to build in 6.3 before the first LLM call: a single allowlist prompt-evidence builder (no `run`/`plan` metadata; redacted views passed as status only; fail closed on any redaction inconsistency; values framed as untrusted data), a strict AI finding schema, and status handling (`skipped` / `failed` / `invalid_output`) so the graph always completes deterministically.
    - Validation uses synthetic security-drift plans run through `drift_engine` (open inbound NSG rule, removed rule, public storage access, TLS/encryption downgrade) and a fake chat model; a live LLM check is optional and needs user credentials.
- **Completion Notes**:
  - **Files**: new `src/ai_engine/evidence.py`, `src/ai_engine/llm.py` (Task 6.1 `invoke_llm` moved out of `graph.py` to avoid a graph↔node import cycle; `graph.py` re-exports it), `src/ai_engine/nodes/security_analysis.py`, `tests/test_ai_security.py`, `tests/fixtures/security_plans/` (generator `build.py` + 6 synthetic scenarios); `graph.py` wiring; Task 6.1/6.2 tests updated for the new graph (state keys, edges, `inferences` now holds the `analyze_security` record).
  - **Graph**: START → `initialize` → `parse_drift` → `classify_drift` → `analyze_security` → END. New write-once, frozen deterministic field `security_targets`; AI output only in `inferences["analyze_security"]`.
  - **`classify_drift` (deterministic routing, no re-classification)**: reads only report fields. Routes a change when its deterministic severity is HIGH/CRITICAL (`rated …`, every security rule and the sensitive-value rule rate ≥ HIGH), it is redacted, or it is MEDIUM with no rule (`unrated`, impact unknown: covers uncovered attributes of security-sensitive types). LOW (tags/description) and INFO (noise) are excluded and counted. The `ai_engine` imports no rule catalogue (AST test from 6.2A still holds), so "security-sensitive types" is honored through the deterministic ratings and floors rather than a copied type list.
  - **`build_llm_evidence` (the only prompt input)**: explicit allowlist — resource `address, type, classification, action, drift_action, ambiguous, notes, severity{level,reasons}`; change `path, attribute, class, redacted, severity{level,rules}, assessment, routing_reason` and the S/R/D views (value only for status `value`). Never `run`, `plan`, provider/module/previous address, importing, in-sync resources, outputs or `plan.json`. **Fail closed**: any change that is flagged redacted yet carries a value, or mixes redacted and value views, raises `EvidenceIntegrityError` (checked across all resources, before any call; the value is not echoed). **Limits** (`EvidenceLimits`: 20 resources, 60 changes, 2,000 chars per value, 40,000 chars total): changes ordered by deterministic severity then address/path, long values cut to a prefix (`value_truncated`), lowest-priority changes dropped; everything recorded in `truncation` and surfaced as a warning and a prompt note.
  - **Prompt framing**: system prompt states that tagged evidence is untrusted data, never instructions; forbids re-classification, lowering severity and attribution; requires citations and JSON only. Evidence is deterministic JSON inside `<terraform_evidence>` with `<`/`>` escaped, so a value cannot close the block (tested with an injection string in an NSG rule description).
  - **Output contract & validation**: strict Pydantic `AiSecurityOutput` / `AiSecurityFinding` (`address, cited_paths, exposure` enum, `ai_assessed_impact`, `explanation`, `basis: "inference"`; no extra fields; no field for any deterministic decision). One ```json fence tolerated. Every cited (address, path) must be in the evidence actually sent, else the finding is rejected `unsupported_citation`. Each kept finding carries `deterministic_severity` = max deterministic level of its cited changes (authoritative) next to `ai_assessed_impact` and `ai_impact_below_deterministic`; the AI value never replaces it.
  - **LLM-call behavior**: at most one `invoke` per run, only when the report succeeded, something was routed, the LLM is available and evidence remains after limits. With the **default configuration (`AI_LLM_MAX_RETRIES=0`) that is at most one HTTP attempt per run**; additional attempts of the same prompt occur only when retries are explicitly configured (`AI_LLM_MAX_RETRIES=N` allows up to N+1 attempts on connection errors, 408/409/429 and 5xx). The configured `max_retries` is recorded in the result. Statuses: `skipped` (LLM unavailable, failed report, nothing routed, or no evidence left after limits — no call), `failed` (connection, timeout, auth, rate limit, server error, Azure content filter, via `invoke_llm`; error type only, plus a warning), `invalid_output` (non-JSON, refusal text, schema violation; reply discarded, never stored), `ok`. Genuine bugs (KeyError, TypeError, other ValueError, AssertionError) raise. No structured-output API is used, so refusals arrive as text and end as `invalid_output`.
  - **Validation** (session-scratchpad venv; fake chat models only, no real LLM or network): `tests/test_ai_security.py` **81 passed** (after the final-review fixes) — routing per scenario and on real fixtures; allowlist; redacted status-only; fail-closed (incl. unrouted resources, nothing sent); limit ordering/omission/value-cut/char-cap records; determinism; prompt framing and injection escaping; citation rejection (unrouted, invented path/address, partly unsupported); 14 invalid-output shapes; all statuses; 7 failure kinds; bugs raise; the four acceptance exposure kinds end-to-end (open inbound NSG CRITICAL, removed deny rule HIGH, public storage/network rules CRITICAL, TLS/HTTPS downgrade HIGH, plus a redacted secret change HIGH) with a citing fake model; LangChain `FakeListChatModel` through the full graph; `security_targets` immutable. Mutation check: 8 deliberate breakages of the safeguards (integrity check, delimiter escaping, allowlist, citation check, severity replacement, routing, `basis`, availability guard) are each caught. Full suite **534 passed** (667 subtests); `drift_engine` gate 99.87%; `ai_engine` 99% (`evidence.py`, `security_analysis.py` 100%); `unittest discover` OK; core-only install: no LLM packages, 432 passed / 102 skipped.
  - **Final review fixes (2026-10-02)**: the review measured that the old default `AI_LLM_MAX_RETRIES=2` made one logical call send the same prompt up to 3 times on 429/5xx (hidden resends) — the default is now `0` (opt-in) and the result records `max_retries`; evidence limits that remove every change now give `skipped` / "no evidence left after limits" with no call (previously an empty-evidence call reported `ok`); `create_chat_model` gained an optional `http_client` so tests drive the real client factory over a local `httpx.MockTransport` (OpenAI and Azure: default = exactly 1 request on 429/500/503 and on success; `AI_LLM_MAX_RETRIES=2` = 3 identical requests); added a test that a later node cannot *replace* `security_targets`; `evidence.py` docstring now states that engine `notes` are included and may mention an address (e.g. a previous address). Mutation check: 18 deliberate breakages of the safeguards (the 14 from the review plus default retries, empty-evidence call, unrecorded retries, ignored `http_client`) are each caught.
  - **Limitations**: (a) analysis quality of a real model is unverified — no live call was made (needs user credentials; optional). (b) `unrated` routing also sends uncovered changes of non-security resources (e.g. a newly created resource group's `name`/`location`), costing a call; bounded by the limits. (c) Attribution claims inside free-text `explanation`/`summary` are forbidden by the prompt but only checked by Task 6.5/6.7. (d) Citation checks are at change-path granularity; a finding about one element of a whole-list value (e.g. one NSG rule) cites the list path. (e) Synthetic fixtures model azurerm plan shapes; they are not real Azure evidence.
  - No Terraform, Azure or GitHub Actions changes; no commit.

#### Task 6.4 — Cost & Configuration Analysis Nodes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-02
- **Completed**: 2026-10-02
- **Objective**: Implement LangGraph nodes `analyze_cost` and `analyze_configuration` to inspect resource SKU changes, instance counts, or settings.
- **Dependencies**: Task 6.3
- **Files/Areas**: `src/ai_engine/nodes/cost_analysis.py`; plus (approved design) `src/ai_engine/nodes/analyze_drift.py`, `src/ai_engine/nodes/security_analysis.py`, `src/ai_engine/evidence.py`, `src/ai_engine/graph.py`, `tests/fixtures/cost_config_plans/`, tests
- **Acceptance Criteria**:
  - [x] Evaluates SKU upgrades/downgrades or resource additions/deletions.
  - [x] Summarizes configuration drift relative to declared Terraform specs.
- **Validation**:
  - [x] Test node with SKU change drift report.
- **Implementation Notes**:
  - Synthesizes configuration differences into clear explanations.
  - **Approved design (Task 6.4 design review, 2026-10-02) — one LLM call per run:**
    - `analyze_cost` and `analyze_configuration` are **section handlers** inside a single LLM node `analyze_drift`, which also takes over Task 6.3's security call (the `inferences["analyze_security"]` contract is preserved). A deterministic `route_cost_config` node runs before it and writes write-once `cost_targets` / `config_targets` (incl. a deterministic configuration summary).
    - **Phase 6 guarantee: at most one logical LLM call per run across all analysis sections**; with the default configuration at most one HTTP attempt; extra attempts only when `AI_LLM_MAX_RETRIES > 0`. Only `analyze_drift` receives the LLM client.
    - Output: one JSON object with `security_analysis`, `cost_analysis`, `configuration_analysis` sections; findings `basis: "inference"`, citations **section-scoped** to evidence actually sent; deterministic severity/classification attached by code; no remediation or attribution fields.
    - **Cost is pricing-free in Phase 6**: only a qualitative `direction` (increase/decrease/neutral/undetermined); `monetary_impact = "not_determinable_from_evidence"`; no amounts, prices, savings or currency claims (enforced by a deterministic guard). Infracost figures arrive in Task 10.3 as a deterministic, allowlisted input to the same `cost_analysis` section, not as an extra call.
    - Evidence via the single `build_llm_evidence` gateway, extended with section tags, deduplication (a change routed to several sections is sent once) and per-section caps; redaction fail-closed, allowlist and delimiter escaping unchanged; no raw plan.
    - Cost routing list is routing-only data in `ai_engine` (may move to `drift_engine` with `cost.py` in Phase 10). "Declared Terraform specs" = the plan's desired view plus the `configured` assessment, not HCL source or variable origins.
    - **Knock-on (decided in 6.5/6.6)**: their planned LLM nodes must respect the one-call rule — either further sections of the same call or deterministic/rendering-only steps.
- **Completion Notes**:
  - **Files**: new `src/ai_engine/nodes/analyze_drift.py` (the single LLM node), `src/ai_engine/nodes/cost_analysis.py` (`route_cost_config`, deterministic configuration summary, cost/configuration section schemas and validators), `src/ai_engine/nodes/common.py` (strict base model, cited-path type, cost-claim guard), `tests/test_ai_cost_config.py`, `tests/fixtures/cost_config_plans/` (generator + 9 synthetic scenarios, no pricing data), `tests/conftest.py` (blocks every non-loopback connection in tests, so no real LLM/network call is possible); changed `evidence.py` (section tags, dedupe, per-section caps/applicability, section-scoped `cited_keys`), `security_analysis.py` (reduced to routing + security section handler; prompt/node moved to `analyze_drift`), `graph.py`; Task 6.1–6.3 tests updated for the new graph and envelope. No `drift_engine`, Terraform, Azure or workflow change; README unchanged (no new user-facing command).
  - **Graph**: START → `initialize` → `parse_drift` → `classify_drift` → `route_cost_config` → `analyze_drift` → END. All deterministic nodes run before the only LLM node. New write-once/frozen fields `cost_targets`, `config_targets`, `llm_call`.
  - **One-call guarantee**: `analyze_drift` is the only node holding the client; one `invoke_llm` per run for all three sections; default one HTTP attempt (retries opt-in, recorded in `llm_call.max_retries`). No call when the report failed, nothing is routed in any section, the LLM is unavailable, or limits leave no evidence.
  - **Routing (deterministic, report fields only)**: cost = lifecycle (`resource_added`/`resource_removed`/`external_deletion`/`replace`: every non-noise change) or a cost-attribute name pattern (SKU, tier, replication, size, capacity, counts, instances, MB/GB, throughput, zones, autoscale; never tags/description); configuration = every non-noise change of a changed resource; plus a per-resource configuration summary (counts by class/assessment, reverted on apply, pending config changes, ambiguous, unknown until apply, unconfigured-but-reverted).
  - **Evidence**: one `build_llm_evidence` call; a change routed to several sections is sent once with per-section reasons; per-section caps (security 30, cost 20, configuration 30) plus global caps, priority security → cost → configuration; a section is `applicable` only if evidence for it was included. Allowlist, fail-closed redaction check, value/char caps and delimiter escaping unchanged.
  - **Output contract**: envelope with exactly `security_analysis`, `cost_analysis`, `configuration_analysis`. Cost findings: `cost_driver`, qualitative `direction`, constant `monetary_impact = "not_determinable_from_evidence"`; code adds `pricing_source: null`, `classification`, `action`, `deterministic_severity`. Configuration findings: `topic`; code adds `evidence_facts` (deterministic attribute class + assessment per cited path), `topic_conflicts_with_evidence`, `deterministic_severity`. No field for classification, severity, remediation or attribution in any schema.
  - **Validation rules**: envelope invalid → every applicable section `invalid_output` (raw reply discarded); one section failing its schema → only that section `invalid_output`; citations must be sent **for that section**; findings in a non-applicable section rejected (`section_not_applicable`); free text with amounts/currency/rates/numeric savings rejected (`unsupported_cost_claim`) in every section, and such a summary is dropped.
  - **Tests** (session-scratchpad venv, fake models / local `httpx.MockTransport` only): `test_ai_cost_config.py` **92 passed**; `test_ai_security.py` 82, `test_ai_parse_drift.py` 47, `test_ai_config.py` 76 (all AI: 297). Covers routing per scenario and on real fixtures, lifecycle and noise exclusion, the configuration summary, dedupe, per-section caps, ≤ 1 call for every scenario and the whole graph, 1 HTTP request by default for three sections (3 with `AI_LLM_MAX_RETRIES=2`), section-scoped citations, non-applicable sections, cost-claim guard (12 positive / 9 negative phrasings), strict cost and configuration schemas, topic-conflict flags, envelope variants, failed call, bugs raise, injection values escaped and echoed amounts rejected, SKU changes end-to-end, frozen `cost_targets`/`config_targets`/`llm_call`, and deterministic output identical with and without an LLM. The test-wide network guard caught one pre-existing test that would now have contacted `api.openai.com` (tag drift now routes to configuration); that test now uses an in-sync report. Mutation check: **33/33** deliberate breakages caught (two survivors on the first run led to added assertions). Full suite **627 passed** (667 subtests); `drift_engine` gate 99.87%; `ai_engine` 99% (`analyze_drift`, `security_analysis`, `common` 100%; `cost_analysis` 98%); `unittest discover` OK; core-only install: no LLM packages, 465 passed / 162 skipped.
  - **Limitations**: (a) no pricing: cost output is qualitative until Phase 10 (Infracost); (b) the cost pattern list is heuristic routing and can miss provider-specific cost attributes or include free ones; lifecycle routing also sends tag changes of added/deleted resources; (c) the cost-claim guard is pattern-based (conservative: it may reject a legitimate text containing e.g. `$` or "cost: 3"); (d) updates carry only changed paths, so unchanged context (current tier, region, usage) is absent; (e) analysis quality of a real model is unverified (no live call); (f) attribution/remediation wording in free text is forbidden by the prompt but checked only in Task 6.7.

#### Task 6.5 — Root Cause & Risk Assessment Nodes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Implement LangGraph nodes `analyze_root_cause` and `assess_risk` to hypothesize drift origin based strictly on available evidence.
- **Amendment (2026-10-04, requirement gap — see Phase 6 header)**: the constant `actor = "unknown"` / `confirmed = false` and the `confirmation_requires = "activity_log"` placeholder are superseded by Task 9B.4. There, deterministic investigation evidence (never the LLM) supplies the recorded operation, timing, caller type and channel; actor attribution is `confirmed` only where Phase 9B's correlation proves it. The record below is historical.
- **Dependencies**: Task 6.4
- **Files/Areas**: `src/ai_engine/nodes/root_cause.py`; plus (approved design) `src/ai_engine/nodes/analyze_drift.py`, `src/ai_engine/evidence.py`, `src/ai_engine/nodes/common.py`, `src/ai_engine/graph.py`, `tests/fixtures/root_cause_plans/`, tests
- **Acceptance Criteria**:
  - [x] Analyzes whether drift stems from a change outside Terraform (actor and channel unknown; the portal is one possibility, never asserted), a configuration-side change (code, tfvars, module or provider default; not distinguishable), or out-of-band updates. *(Reworded 2026-10-03 per the Task 6.5 design review: the original "manual portal edits" / "missing HCL variables" asked for distinctions Terraform evidence cannot make.)*
  - [x] Explicitly labels speculative claims as inferences vs facts.
- **Validation**:
  - [x] Test prompt outputs against strict Evidence vs Inference criteria.
- **Implementation Notes**:
  - Prompt engineering enforcing zero hallucination of untracked events.
  - **Approved design (Task 6.5 design review, 2026-10-03):**
    - A deterministic node `derive_origin_risk` (no LLM) writes write-once `origin_facts`: per change the origin category (from resource classification + attribute class + assessment) and deterministic risk factors; per resource moved/importing/action_reason/ambiguous and the union of risk factors. It also routes the `root_cause` and `risk` sections.
    - `analyze_root_cause` and `assess_risk` are **sections** (`root_cause_analysis`, `risk_assessment`) of the existing single `analyze_drift` call: five sections, still **at most one logical LLM call per run** (default one HTTP attempt).
    - Root cause = deterministic change-origin category + AI-ranked hypotheses labelled inference, with constant `actor = "unknown"` and `confirmed = false` until Phase 7 Activity Log evidence (only deterministic code may ever change them). A hypothesis that contradicts the cited changes' origin is rejected (`hypothesis_contradicts_evidence`).
    - Risk = deterministic risk factors + AI-explained consequences. **No AI risk level**: deterministic severity remains the only authoritative rating. A `risk_kind` must match a deterministic factor of the cited changes (`other` is kept and flagged).
    - Deterministic guards on every section's free text: attribution (no actor claims: emails, UPNs, GUIDs, "changed by …", "an administrator changed …") and remediation (no fix instructions; remediation is Task 6.6), alongside the existing cost-claim guard and section-scoped citations.
    - Evidence: the single gateway gains the allowlisted per-change `origin` and per-resource `risk_factors` (no previous-address string); run metadata and the plan timestamp stay excluded.
- **Completion Notes**:
  - **Files**: new `src/ai_engine/nodes/root_cause.py` (`derive_origin_risk`, origin table, risk factors, root-cause/risk section schemas and validators), `tests/test_ai_root_cause.py`, `tests/fixtures/root_cause_plans/` (generator + 8 synthetic scenarios); changed `analyze_drift.py` (five-section envelope, prompt rules), `evidence.py` (five sections + caps, allowlisted `origin` / `risk_factors` / `moved` / `importing` / `action_reason`), `common.py` (attribution and remediation guards, `free_text_violation`), `security_analysis.py` and `cost_analysis.py` (all three guards on every section), `graph.py`; Task 6.1–6.4 tests updated for the five-section envelope and new node. No `drift_engine`, Terraform, Azure or workflow change; README unchanged (no new user-facing command).
  - **Graph**: … → `route_cost_config` → `derive_origin_risk` → `analyze_drift` → END. New write-once/frozen `origin_facts` (with `actor = "unknown"`, `confirmed = false`). Still **one logical LLM call per run**, now five sections; default one HTTP attempt.
  - **Deterministic origin**: per change from the attribute class (object-level from the resource class; `undetermined` resources stay undetermined): `outside_terraform`, `outside_terraform_converged`, `configuration_side`, `both_sides`, `value_unknown_until_apply`, `undetermined`, plus `lifecycle`. **Risk factors**: `apply_reverts_external_change` (update + drifted/drifted-and-config), `apply_destroys_or_recreates` (replace/delete/external deletion), `ambiguous_intent`, `unmanaged_setting` (unconfigured), `value_unknown_until_apply`, `redacted_unreadable`, `moved_or_importing`. Noise changes have no origin. Root-cause routes: every non-noise change; risk routes: changes with ≥ 1 factor.
  - **Contracts**: root cause `hypothesis` (6 kinds), `possible_channels` (structured only), constants `actor = "unknown"`, `confirmed = false`; code adds `confirmation_requires = "activity_log"`, `origin_facts`, `deterministic_severity`. Risk `risk_kind` (7 kinds), **no level**; code adds `risk_factors`, `risk_kind_unverified` (for `other`), `deterministic_severity`. Both: max 20 findings, 600-char explanations (reply-length mitigation for five sections).
  - **Deterministic checks**: section-scoped citations; every cited change must agree with the hypothesis (`hypothesis_contradicts_evidence`); `risk_kind` must match a factor of a cited change (`evidence_incomplete` needs a redacted change or truncated evidence); attribution guard (emails/UPNs, GUIDs, "changed by …", actor + change verb) and remediation guard (terraform commands, "you/we should", "we recommend", "to fix this", "please/consider …") on findings and summaries of **all five sections**, beside the cost-claim guard.
  - **Tests** (session-scratchpad venv, fake models / local `httpx.MockTransport` only, network guard active): `test_ai_root_cause.py` **123 passed** — origin table on 12 real/synthetic fixtures, risk factors on 11, previous address never a field, noise-only drift makes no call, routing, five-section envelope, **one call and one HTTP request with all five sections applicable**, origin facts identical for no/ok/failed/invalid LLM, `origin_facts` cannot be replaced, mutated or confirmed, allowlisted origin in the prompt, redaction status-only + fail-closed, a 15-case hypothesis/origin matrix, all-citations-must-agree, schema constants and caps, risk-kind support (incl. redaction/truncation), no risk rating, section-scoped citations, 9+8 attribution and 9+5 remediation phrasings, guards in every section and summary, injected actor/fix text escaped and echoes rejected, consistent output accepted end-to-end on 9 fixtures. Earlier AI suites: 76 + 47 + 82 + 92 (all AI: 420). Mutation check **58/58** caught (25 new for 6.5; three first-run survivors led to added tests). Full suite **750 passed** (667 subtests); `drift_engine` gate 99.87%; `ai_engine` 99% (`root_cause`, `analyze_drift`, `common`, `security_analysis` 100%); `unittest discover` OK; core-only: no LLM packages, 526 passed / 224 skipped.
  - **Limitations**: (a) actor, time and channel remain unknown until Phase 7; hypotheses are unconfirmed by design; (b) the origin category restates Terraform's three-view comparison and cannot separate code, tfvars, module or provider-default changes; (c) attribution/remediation guards are pattern-based and conservative (may reject a legitimate sentence, e.g. "a user-assigned identity was added"); free-text claims they do not match are evaluated in Task 6.7; (d) engine `notes` (allowlisted since 6.3) may mention a previous address in text; (e) no live model call, so real-model quality and reply length with five sections are unverified; a cut-off reply ends as `invalid_output` for every section.

#### Task 6.6 — Remediation Recommendation & Report Generation Nodes
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Implement LangGraph nodes `recommend_remediation` and `generate_report` to synthesize full Markdown AI analysis report.
- **Amendment (2026-10-04, requirement gap — see Phase 6 header)**: "options are never ranked or recommended" and the report contract v1 (constant `attribution.pending = "phase_7_activity_log"`, Root Cause "unconfirmed until Phase 7") are superseded by Task 9B.4 (report v2 and the deterministic recommendation policy v1). The record below is historical.
- **Dependencies**: Task 6.5
- **Files/Areas**: `src/ai_engine/nodes/report_generator.py`; plus (approved design) `src/ai_engine/nodes/remediation.py`, `src/ai_engine/graph.py`, `tests/fixtures/report_plans/`, tests
- **Acceptance Criteria**:
  - [x] Generates clean Markdown report containing Summary, Security Impact, Cost Impact, Root Cause (unconfirmed until Phase 7), and deterministic remediation options with HCL value fragments (where a value is defined is not determined; no file edits — Phase 8.2). *(Reworded 2026-10-03 per the Task 6.6 design review.)*
  - [x] Outputs structured JSON alongside Markdown report.
- **Validation**:
  - [x] Run full LangGraph pipeline end-to-end and inspect `ai_analysis_report.md` (via `write_report(state, out_dir)`; no CLI in this task).
- **Implementation Notes**:
  - Final graph output node producing user-facing artifacts.
  - **Approved design (Task 6.6 design review, 2026-10-03):**
    - `recommend_remediation` is the deterministic node **`plan_remediation`** (runs before the LLM; write-once `remediation_plan`); `generate_report` is **deterministic rendering** (after the LLM; write-once `report`). **No new LLM section, no prompt change**: the one-logical-LLM-call-per-run guarantee is unchanged, and AI text cannot create or alter remediation options (the existing remediation guard stays).
    - Options come from a deterministic table over classification, action, attribute class, assessment, origin and risk factors; commands only from a fixed catalogue; destructive/mutation flags derived from the plan action; HCL **value fragments** only from the `real` view, with `${`/`%{` escaped and `location = "not_determined"`; no fragment for redacted, unknown-until-apply, absent or object-level values.
    - **`plan_default` means only "this option corresponds to the current Terraform plan direction/action"** — it is not a recommendation; options are never ranked or recommended as a business decision.
    - **No execution in Phase 6**: every option has `approval.required = true`, `approval.status = "pending"`, `execution.allowed = false`, `automatic_apply = false`. Approval gates and apply are Phase 11; PR / file edits are Phase 8.
    - Report: strict JSON (`ai_analysis_report.json`) built from validated state only; Markdown (`ai_analysis_report.md`) rendered **only from that JSON**; untrusted text Markdown/HTML-escaped with links neutralized, values in dynamically fenced code. Attribution stays `unknown` / unconfirmed; monetary impact `not_determinable_from_evidence`; deterministic severity/classification authoritative.
    - **No CLI or workflow integration in Task 6.6**: only the deterministic `write_report(state, out_dir)` function (a later task integrates it).
  - **Constraint (recorded 2026-10-03, Task 6.5 design review):** Task 6.6 must not introduce an independent additional LLM call; the Phase 6 guarantee of at most one logical LLM call per run stands. The final remediation architecture is decided in Task 6.6.
- **Completion Notes**:
  - **Files**: new `src/ai_engine/nodes/remediation.py` (command catalogue, HCL value rendering, option table, strict `RemediationPlan`/`RemediationOption` schema, `plan_remediation`), `src/ai_engine/nodes/report_generator.py` (strict `AiAnalysisReport`, `build_report`, `generate_report`, `render_markdown`, `write_report`), `tests/test_ai_report.py`, `tests/fixtures/report_plans/` (generator + 5 synthetic scenarios: Markdown/HTML/link payloads, HCL interpolation, injected destructive instructions, every HCL value type, multi-resource); `graph.py` wiring; Task 6.1/6.2 tests updated for the new state keys and edges. No prompt change, no new LLM section or call, no `drift_engine`/Terraform/Azure/workflow change; README unchanged (no CLI).
  - **Graph**: … → `derive_origin_risk` → `plan_remediation` → `analyze_drift` → `generate_report` → END. New write-once/frozen `remediation_plan` and `report`. Still one logical LLM call per run (default one HTTP attempt); remediation never enters the prompt.
  - **Options (deterministic)**: one option mirrors the current plan (`plan_default`: restore_declared, apply_pending_change, create_declared_object, delete_undeclared_object, replace_object, recreate_deleted_object, no_infrastructure_change), plus alternatives by evidence: accept_remote_value (drift classes), keep_current_value (config change update/replace), refresh_state_only (converged drift), stop_managing_without_destroy (planned delete / external deletion), investigate (ambiguous / drift-and-config / undetermined, all options `human_decision_required`). `plan_default` marks only the plan direction (exactly one per resource; alternatives carry no plan action); `ranking = "none"`. `destructive` from replace/delete (with `destructive_confirmation_required`); `data_not_restored` for recreate; `mutates` infrastructure/state/configuration.
  - **Commands**: fixed catalogue only (`plan_review`, `plan_save`, `apply_reviewed_plan`, `plan_refresh_only`, `apply_refresh_only`, `state_rm`); no `-auto-approve`, no `destroy`; working dir and address from the report, shell-quoted; var file stays the placeholder `<var_file>` (not in the evidence). Every option: `approval.status = "pending"`, `execution.allowed = false`, `automatic_apply = false`.
  - **HCL fragments**: from the `real` view only; strings escaped (quotes, backslash, control chars) and `${`→`$${`, `%{`→`%%{`; numbers/bools/null/lists/maps rendered deterministically; `location = "not_determined"`; no fragment for redacted, unknown-until-apply, absent, object-level or oversized values (recorded as gaps); nested paths have no assignment line.
  - **Report**: strict JSON (provenance with `drift_report_sha256`, deterministic summary/resources, the five validated AI sections with rejected findings counted not shown, remediation plan, constant attribution unknown/unconfirmed, constant monetary impact not determinable, LLM call record, limitations). Markdown rendered from the serialized JSON only; untrusted text escaped (Markdown punctuation, `<`/`>`/`&`, links broken with a zero-width space after `:`/`@` and in `www`), values/fragments/commands in code spans or fenced blocks longer than any backtick run, table pipes escaped. Byte-identical output for identical state; atomic writes.
  - **Tests** (session-scratchpad venv, fake models / local `httpx.MockTransport`, network guard active): `test_ai_report.py` **104 passed** — option table on 9 fixtures, delete/replace destructive with non-destructive alternatives, data-not-restored, human-decision cases, `plan_default` semantics (exactly one, matches the plan action, destructive plan direction still marked, no ranking/recommendation in schema or Markdown), failed report → no options, **no execution + catalogue-only commands + scope (only affected resources/paths) on all 41 fixtures**, shell quoting/placeholders, options unchanged by AI output, 11 HCL value cases and 6 escaping cases, value-type fixture, no fragment for redacted/absent/unknown/object-level/oversized, strict report schema and constants, deterministic JSON/Markdown and Markdown == render(JSON), all sections present, hostile payloads inert (no raw HTML/links/autolinks/heading injection outside code; fences never closable from inside; table rows intact), all AI statuses (skipped/failed/invalid_output/ok) incl. rejected findings hidden, deterministic report parts identical with and without an LLM (incl. accepted findings), one call / one HTTP request through the whole graph, `remediation_plan` and `report` write-once and frozen. Earlier AI suites unchanged: 76 + 47 + 82 + 92 + 123 (all AI: 524). Mutation check **93/93** caught (35 new for 6.6; five first-run survivors led to added tests). Full suite **854 passed** (667 subtests); `drift_engine` gate 99.87%; `ai_engine` 99% (`remediation` 99%, `report_generator` 97%); `unittest discover` OK; core-only: no LLM packages, 606 passed / 248 skipped.
  - **Limitations**: (a) the var file is not in the evidence, so commands carry the placeholder `<var_file>`; (b) fragments never locate the value (resource block, module input or tfvars) and cover only "keep the Azure value" — removing a key (`value_absent`) has no fragment; (c) Markdown safety is tested against GFM-style rules by a line-aware checker, not a full Markdown renderer; (d) no CLI or workflow integration yet (later task); (e) the report is not written anywhere automatically.

#### Task 6.7 — Evidence vs Inference Validation & Unit Testing
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Create automated evaluation test suite to verify that LLM outputs never invent non-existent resource attributes or false attributions.
- **Dependencies**: Task 6.6
- **Files/Areas**: `tests/test_ai_engine.py`; plus (approved design) `src/ai_engine/nodes/common.py`, `src/ai_engine/nodes/analyze_drift.py`, `src/ai_engine/nodes/security_analysis.py`, `src/ai_engine/nodes/report_generator.py`, `src/ai_engine/graph.py`, new `src/ai_engine/verify.py`, `tests/corpora/`, `tests/mutation/`, `scripts/run_mutation_checks.py`, tests
- **Acceptance Criteria**:
  - [x] Unit tests for all individual nodes.
  - [x] Assertion tests checking that all cited attributes exist in `drift_report.json`.
- **Validation**:
  - [x] `pytest tests/test_ai_engine.py` passes.
- **Implementation Notes**:
  - AI reliability guardrails.
  - **Approved scope (Task 6.7 design review, 2026-10-03)** — cross-cutting hardening/validation of the Phase 6 engine; no new feature, no new LLM call or section, no prompt change unless strictly required:
    - Harden the attribution, remediation and cost guards: `Cf` (format) characters and mixed-script words are detected **on the original text** and rejected as `suspicious_text`; matching then runs on a separately normalized copy (HTML-unescape, NFKC, `Cf` removal, lookalike folding, `[at]`/`[dot]` folding, spaced-letter collapsing) **and** on the original. Broadened patterns; targeted false-positive fixes only (no rule weakened); tradeoffs documented and asserted in the corpus.
    - Protect state: `llm` write-once; `inferences` write-once per section key (frozen). Reject duplicate JSON keys in model replies.
    - Record `llm_call.evidence_sent` (address, path, sections only — no values) and keep it in the final report.
    - Strict per-section report finding models (`extra="forbid"`), so AI output cannot introduce deterministic-authority fields.
    - Deterministic `verify_report(report_json, drift_report_json)` that validates the final report against the drift report **independently** (its own checks from the report contract, not a re-run of the report path).
    - Data-driven guard and prompt-injection corpora; injection tests require deterministic state and remediation unchanged and unsafe AI findings rejected (not byte-identical AI sections).
    - Committed, opt-in mutation harness (`scripts/run_mutation_checks.py` + `tests/mutation/mutants.json`) with a cheap staleness check in the default suite; no CI change.
    - Close the identified uncovered paths (failed-report Markdown, atomic-write cleanup, client-construction failure, missing `openai`, non-JSON HCL, frozen-list copies, non-object writes).
  - **Phase 7 boundary**: no Activity Log, `caller_identity` or attribution confirmation; `actor` stays `unknown` and `confirmed` false, enforced by `verify_report`.
- **Completion Notes**:
  - **Files**: new `src/ai_engine/verify.py`, `tests/test_ai_engine.py`, `tests/test_mutation_corpus.py`, `tests/corpora/{guards,injection}.json`, `tests/mutation/mutants.json`, `scripts/run_mutation_checks.py`; changed `nodes/common.py` (guards), `graph.py` (state), `nodes/analyze_drift.py` (strict JSON, `evidence_sent`), `nodes/security_analysis.py` (strict JSON), `nodes/report_generator.py` (strict finding models, `evidence_sent`), one Task 6.4 test (`llm_call` record now has `evidence_sent`). No prompt, LLM-call, `drift_engine`, Terraform, Azure, workflow or README change.
  - **Guards**: `suspicious_text` (format characters or Latin mixed with a lookalike script inside a word) decided on the **original** text; matching then runs on the original **and** a normalized copy (HTML-unescape ×3, NFKC, `Cf`/`Mn` removed, Cyrillic/Greek lookalikes folded, `[at]`/`[dot]` folded, spaced letters collapsed), so normalization only adds detections. Broadened: bare/flagged/written Terraform commands, `az …`, `*-Az…` cmdlets, sentence-initial imperatives, "set … back", advice phrasing, passive "should be restored"; actor statements, "per the Activity Log", more actor nouns/verbs, `changed-by:` separators; "bucks", price multiples. Targeted false-positive fixes only: passive auxiliaries ("a managed identity *was* added") and "save(s) N <count noun>"; no existing rule weakened (all earlier guard tests unchanged). A dead lookahead found by the mutation harness was removed.
  - **State / parsing**: `llm` write-once; `inferences` write-once per key and frozen (new keys may still be added); duplicate JSON keys (any depth) and NaN rejected in the envelope and the standalone security parser.
  - **Evidence chain**: `llm_call.evidence_sent` = exactly the (address, path, sections) the model was given (empty without a call), copied to `report.llm.evidence_sent`; strict per-section report finding models (`extra="forbid"`, constants for actor/confirmed/monetary impact).
  - **`verify_report(report_json, drift_report_json)`**: independent checks from the drift report's contract fields with its own restated rules (origin table, risk factors, routing eligibility, hypothesis table) — provenance, summary, every resource/change/origin/factor, `evidence_sent` existence and eligibility, section status/applicability, section-scoped citations, every code-attached finding field, guards re-run on all AI text, and remediation (scope, one `plan_default` per resource matching the plan action, destructive/data/human flags, readable-value fragments with escaped interpolation, catalogue-exact commands, dangerous commands rejected even if the catalogue regressed). `verify_markdown` checks the Markdown is the rendering of the JSON; a template-skeleton test proves the Markdown carries no word absent from the JSON or the renderer's template text.
  - **Tests** (session-scratchpad venv; fake models / local `httpx.MockTransport`; network guard active): `test_ai_engine.py` **603 passed** — guard corpus (**139 cases**, each through the guards and end-to-end as an explanation and a summary; 4 documented tradeoffs asserted as-is), independent rule tables agree with the nodes on all 41 fixtures, redaction fail-closed corpus, **injection corpus 12 values × 3 placements** (value stays escaped data inside one delimiter; deterministic state/remediation unchanged vs. a no-LLM run; unrelated citations always and unsafe echoes rejected; `verify_report` and `verify_markdown` pass), duplicate keys, truncation at ~60 structural boundaries, framing variants, list content, oversized sections, **`verify_report` + determinism matrix on 41 fixtures × 4 LLM modes**, **54 tampered-report cases** (plus isolating tests for failed reports, noise evidence, unreadable fragments, no-call `evidence_sent` and a regressed catalogue) each detected, different-drift-report and Markdown tampering, write-once `llm`/`inferences`/`llm_call`, one HTTP attempt by default with `evidence_sent` == what the model saw, and the previously uncovered paths (failed-report Markdown, atomic-write cleanup, client-construction failure, missing `openai`, non-JSON HCL, frozen-list copies, non-object writes, duplicate routes, cost-section rejections). `test_mutation_corpus.py` 3 passed (154 mutants still apply). Earlier AI suites unchanged: 76 + 47 + 82 + 92 + 123 + 104.
  - **Mutation harness**: `python scripts/run_mutation_checks.py` (opt-in, copies of `src/`+`tests/`, verifies the copy is imported and the baseline passes) — **154 / 154 caught** (93 earlier + 61 for 6.7; first runs found 6 + 2 survivors, each fixed by an isolating test or by removing dead code).
  - **Totals**: full suite **1460 passed** (821 subtests); `drift_engine` gate 99.87%; `ai_engine` 99% with **0 missed lines** (3 partial branches: an unreachable section fall-through, the atomic-write "temp already gone" branch, package `__init__`); `unittest discover` OK; core-only: no LLM packages, 802 passed / 658 skipped.
  - **Known gaps / tradeoffs**: (a) a plain person's name doing something ("alice did this") is not detectable without NER — mitigated by schema constants, the fixed attribution block and "AI inference" labelling; (b) conservative rejections: a sentence starting "Set …", emoji ZWJ sequences, any `Cf` character; gerund advice ("Restoring … is the way forward") passes; (c) guards are pattern-based — evasion beyond the corpus is possible, but evasions only affect inference text, never deterministic state, remediation or execution; (d) `verify_report` re-uses the shared guard code, the HCL renderer's output contract and the command catalogue (data), while deterministic facts are checked independently; (e) the mutation harness is opt-in (minutes), not in CI.

---

### PHASE 7 — Azure Activity Log Investigation
**Status**: 🟢 COMPLETED — returned to 🟢 on 2026-10-11 when Task 9B.6 passed (reopened 2026-10-04 for a requirement gap, closed by Phase 9B; see the Task 9B.6 completion notes)

Phase 7 queries Azure Activity Logs to correlate detected drift with actual Azure control plane events (caller identity, timestamp, operation name).

> **Requirement-gap amendment (2026-10-04, user decision):**
> - **Evidence**: the same real Azure test as Phase 6 (drift run `37197574080`). No Activity Log evidence was collected and nothing reached the report.
> - **Gap**: Tasks 7.1–7.3 met their recorded acceptance criteria, but the phase objective (caller identity, timestamp and operation name for detected drift) is delivered neither in CI nor for update drift:
>   - collection is local-only and not in any workflow;
>   - normalization discards every claim, so caller type and client application are lost;
>   - correlation considers only exact-resource `<type>/write|delete`, but the verified tag operation is `Microsoft.Resources/tags/write` (Phase 9B, verified event shape), so it lands in `related`;
>   - rule R0 stops all update drift with no evidence;
>   - the ±5-minute skew and the 20 + 5-minute settling rule misclassify the verified timing (operation 1 min 41 s before plan evidence started; event available after 49–112 s);
>   - Anchor B (last in-sync observation, blocker B1) has no producer;
>   - no restricted path exists for the recorded caller.
> - **Ownership**: Phase 9B (Tasks 9B.1–9B.3, 9B.5, 9B.6) owns the remaining work. The task records below are kept unchanged as history; amendment lines point to the superseding 9B task.
> - **Closure**: Phase 7 returns to 🟢 when Task 9B.6 passes.

#### Task 7.1 — Azure Activity Log API Integration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Implement Python module using `azure-mgmt-log` / Azure REST API to query activity logs for target resource IDs within drift timeframe. *(Design review 2026-10-03: `azure-mgmt-log` does not exist — the SDK is `azure-mgmt-monitor` + `azure-identity`. Terraform records no drift start time, so "drift timeframe" is a lookback window of N days ending at the query time; correlation with the drift is Task 7.2.)*
- **Amendment (2026-10-04, requirement gap — see Phase 7 header)**: superseded in part by Task 9B.1:
  - evidence v2 adds claims-derived `caller_type`, `client_app` and `pipeline_identity`, plus the event phase and the `extension` relation;
  - the run-level `window_start` (G9) and `not_before`/`queried_at` (G8) are added; the 20-minute `settled_until` stays as a legacy field until Task 9B.2 replaces its use;
  - CI collection moves to Task 9B.5.
  Limitation (a)'s open check "which operation name a tag edit uses" is answered by the verified event shape recorded in Phase 9B. The record below is historical.
- **Dependencies**: Task 6.6
- **Files/Areas**: `src/drift_engine/activity_logs.py`; plus (approved design) `src/drift_engine/cli.py` (`activity-logs` subcommand), `src/drift_engine/__init__.py` (package rule), `pyproject.toml` / `requirements.txt` (`[azure]` extra), `tests/test_activity_logs.py`
- **Acceptance Criteria**:
  - [x] Queries Azure Activity Logs for resource operations in past N days.
  - [x] Extracts `caller`, `eventTimestamp`, `operationName`, and `status` (and, per the design review, `resourceId`).
- **Validation**:
  - [x] Test query against Azure environment (or mocked log responses). — mocked responses (fake source + real SDK over a fake HTTP transport); no real Azure query was run (Execution Rule 10).
- **Implementation Notes**:
  - Integrates empirical Azure management plane telemetry.
  - **Approved design (2026-10-03)**: `azure-mgmt-monitor` + `azure-identity` in an opt-in `[azure]` extra; drift detection stays Azure-free. Separate deterministic `activity_log_evidence.json` (drift report contract unchanged), `trust: untrusted_external`. Collect, validate, normalize and scope only — **no** caller attribution/correlation (7.2), no `caller_identity`, no `actor`/`confirmed` change, no AI-layer change, no fallback semantics (7.3). Resource-group-scoped queries; no `$select` (`caller` is not a documented `$select` property). CLI `drift-engine activity-logs` for local/manual collection only; **not** in the workflow; evidence **not** uploaded as an artifact (callers are personal data; artifact policy deferred).
- **Completion Notes**:
  - **Files**: new `src/drift_engine/activity_logs.py`, `tests/test_activity_logs.py`; changed `src/drift_engine/cli.py` (`activity-logs` subcommand; `_write_atomic(private=True)` creates new evidence files 0600; command-aware internal-error message; `analyze` unchanged), `src/drift_engine/__init__.py` (package rule: only `activity_logs.AzureMonitorSource` reads Azure, read-only, lazy SDK import), `pyproject.toml` (`azure = ["azure-mgmt-monitor>=7,<8", "azure-identity>=1.19,<2"]`), `requirements.txt` (`-e .[dev,ai,azure]`). No Terraform, Azure, workflow, AI-engine, schema or README change.
  - **Targets**: every managed `resource_drift` entry of the parsed plan (the `has_drift` definition), from `classifier.evaluate` on the same plan + manifest (the report is contract-checked first; a failed/rejected run is `failed`/`input`/`evidence_failed`). **Selection never depends on Terraform actions or the report's classification** (review fix 2026-10-03): external updates, external deletions (ID from the drift entry's `before` state) and create/replace-style drift entries are all targets. ARM ID = drift `before` (recorded state) `id`, else `after` (refreshed) `id`; an `id` marked sensitive is not used. A drifted resource without a usable ID is kept with an explicit non-queried status (`no_resource_id`, `invalid_resource_id`, `unsupported_scope` = no resource group), never dropped; queried statuses: `queried`, `query_incomplete`, `query_failed`. Resources without a drift entry (configuration-only changes: `config_change`, `resource_added`, `resource_removed`, planned replace) and data sources are never targets; **no drift → no Azure call** (and no SDK needed).
  - **Query**: one per (subscription, resource group), resource groups compared case-insensitively: `eventTimestamp ge '<start>' and eventTimestamp le '<end>' and resourceGroupName eq '<rg>'`; window = query time (whole seconds, UTC) minus `lookback_days` (1–89, default 30), plus `settled_until` = end − 20 min (ingestion delay). RG names validated against Azure's charset (no quote: no OData injection).
  - **Normalization**: allowlisted fields only (`event_data_id`, `correlation_id`, `operation_id`, `event_timestamp`, `submission_timestamp`, `operation_name`, `status`, `sub_status`, `category`, `level`, `resource_id`, `caller`); `claims`, `authorization`, `httpRequest`/client IP, `properties`, `description`, `tenantId`, tokens are never stored. Dropped and counted (`scopes[].dropped`): malformed records, invalid eventDataId / timestamp (UTC `Z`/`+00:00` only, ASCII digits, ≤ 9 fractional digits truncated to µs) / resource ID / operation name, outside the window, category not Administrative/Policy/Autoscale, outside every target, identical duplicates (kept once), conflicting duplicates (every copy dropped; IDs compared case-insensitively). Caller kept verbatim only as printable text (no control/format/bidi/zero-width/private/unassigned chars, only inner ASCII spaces, ≤ 256) else `null` + `caller_rejected`; absent → `null` + `caller_missing`. Other bad optional fields → `null` + a fixed anomaly. Each kept event records the most specific target(s) it is `exact` or `descendant` of (NSG security-rule events → the NSG; the subnet and its NSG association share one ID → both).
  - **Contract**: strict, frozen Pydantic models (`extra="forbid"`, no coercion) with cross-checks (outcome ⇔ scopes/targets, failure ⇔ failed, sorted/unique events/targets/scopes, matches ⇔ targets and recomputed relation, `matched_events`, `events_returned = events_kept + Σ dropped`, events inside window and scopes). `render_evidence`: sorted keys, 2-space indent, ASCII — byte-identical for identical inputs, independent of event and page order. Outcome `complete` / `incomplete` / `failed` (input failure, or every scope failed).
  - **Azure access** (`AzureMonitorSource`): `AzureCliCredential` only (never `DefaultAzureCredential` or a secret), created lazily; per-request hook allows only GET to this subscription's Activity Log path on `management.azure.com` (blocks foreign/HTTP nextLinks, redirects — also `permit_redirects=False` — and the SDK's automatic provider-registration POST), nextLink also checked before it is followed; retries 3 with bounded backoff, Retry-After capped at 30 s, 120 s per page, connect 10 s / read 90 s. Limits: 100 pages and 10 000 events per scope, 180 s per run → `truncated`. Fixed error codes only (`authentication_failed`, `authorization_failed`, `bad_request`, `throttled`, `service_error`, `timeout`, `connection_failed`, `credential_unavailable`, `invalid_response`, `blocked_request`, `azure_sdk_unavailable`, `http_error`, `azure_error`); a source that stops without a final page is `invalid_response`. Logs: counts, RG names and codes only.
  - **CLI**: `drift-engine activity-logs --plan --manifest [--lookback-days N] [--output]`; exit 0 complete, 1 incomplete/failed (evidence still written), 2 usage, 70 internal, 73 write error; prints that drift detection results are unaffected. Real RBAC unchanged: the CI identity's subscription `Reader` (`*/read`) covers `Microsoft.Insights/eventtypes/values/read`.
  - **Tests** (session-scratchpad venv, azure-mgmt-monitor 7.0.0, azure-identity 1.26.0, azure-core 1.41.0; no credentials, network guard active): `tests/test_activity_logs.py` **122 passed** (329 subtests) — target extraction on all plan fixtures (placeholder IDs → `invalid_resource_id`; synthetic-GUID copies → queried; targets = exactly the managed drift entries of every fixture), an action matrix (external update; external deletion with recreate planned or no longer declared, ID from `before`; drift `create`/`delete+create`/`create+delete`/`no-op` entries; update drift with planned replace/delete/create → all targets; config-only update/create/delete/replace → no target; missing/unknown/null/invalid/subscription-scope IDs → explicit non-queried statuses; order-independent selection; two deliberately action-filtering mutants of `select_targets` are caught), no Azure call for no-drift/config-only/failed runs, RG and child-resource scoping, timestamps/window edges, caller validation, duplicates/conflicts, categories, determinism under shuffling/paging, page/event/deadline limits, every failure code, malformed responses, strict contract (unknown fields at every level incl. `caller_identity`/`actor`/`confirmed`), and the real SDK over a fake HTTP transport (request shape, no `$select`, bearer token, timeouts, paging, blocked nextLinks/redirects/registration POST, 400/401/403/404/409/429/5xx, retries and capped waits, timeouts, credential errors, SDK missing); import boundary in subprocesses (no `azure.*` module loaded by `analyze` or by `activity-logs` without drift; both work with the SDK blocked; `analyze` output identical). Full suite **1582 passed** (1150 subtests); `drift_engine` gate **99.92%** (`activity_logs.py` 100% lines and branches); `unittest discover` OK; core-only venv (`.[dev]`, no Azure/LLM packages): **906 passed / 676 skipped**, `drift-engine analyze` OK and `activity-logs` writes a 0600 failed evidence file (`azure_sdk_unavailable`). `./scripts/validate.sh` passed. Secrets: gitleaks 8.30.1 on all changed files — no finding in new/changed lines (one pre-existing false positive, "TLS/encryption", in the Task 6.3 notes); manual scan: only synthetic GUIDs, `example.com` callers, TEST-NET-3 IPs.
  - **Not done / limitations**: (a) no real Azure query (needs `az login` and approval) — empirical checks still open: whether `$select=caller` works, the resource ID a portal NSG-rule edit is logged under, which operation name a tag edit uses, actual ingestion delay; (b) a resource-group target collects every other event in its group as `descendant` (labelled; 7.2 decides); (c) one bad event in a page makes the SDK reject the whole page (`invalid_response`, fail-closed); (d) the SDK logs its own warning when it would register a provider (the request is still blocked); (e) the run deadline is checked between pages, so one page may take up to its 120 s retry budget beyond it; (f) workflow integration and the artifact/PII policy have no owning task yet; (g) README/architecture docs not updated (no task in scope).
  - **Remains for 7.2/7.3**: which operations/statuses/relations count, the causal window (last apply time is unknown), ambiguity rules, separating Terraform's own applies from out-of-band changes, binding to `subject.run_id`, where attribution lives (report version vs separate document), deterministic `actor`/`confirmed`; 7.3: meaning of `incomplete`/`failed`/empty/pre-retention/unsettled evidence.

#### Task 7.2 — Caller Identity & Action Correlation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Deterministically correlate drifted resources with exact-resource write/delete operation groups in the Task 7.1 Activity Log evidence, and record the caller Azure logged only where the approved correlation rules establish it. *(Reworded 2026-10-03 per the approved Task 7.2 design and the read-only Azure verification: Activity Log events carry no property diffs, so drift **attributes** cannot be correlated; only external deletions can be confirmed.)*
- **Amendment (2026-10-04, requirement gap — see Phase 7 header)**: superseded in part by Task 9B.2:
  - correlation v2 (capable operations, five verdicts, property link) replaces R0's blanket `update_not_attributable` for presentation;
  - `external_deletion_v1` stays the only rule that can confirm (rules version 2): re-parameterized to Phase 9B's timing (G7/G8), blocked by unreadable target-scope events, R7 kept at ±5 min;
  - blocker B1 (Anchor B producer) is resolved by Phase 9B's last-in-sync anchor (G9), accepted as existence anchor `prior_detection_run` (G5);
  - `drift-engine attribute` and `drift_attribution.json` are retained and adapted (attribution version 2);
  - B4 (caller exposure) is settled for investigation artifacts by Phase 9B's privacy profile (G11/G12).
  The record below is historical.
- **Dependencies**: Task 7.1
- **Files/Areas**: `src/drift_engine/attribution.py` (new), `src/drift_engine/cli.py` (`attribute` subcommand), `src/drift_engine/__init__.py` (docstring), `tests/test_attribution.py` (new). *(Approved design: separate module and separate `drift_attribution.json`; `activity_logs.py`, the drift report schema and the AI layer unchanged.)*
- **Acceptance Criteria** *(reworded per the approved design)*:
  - [x] Matches the exact resource ID (case-insensitive), exact operation name (case-insensitive, derived from the resource ID), operation groups `(correlationId, operation, resource)`, event status and the detection time window with the evidence, under the fixed precondition and rule order.
  - [x] Writes a separate deterministic `drift_attribution.json` (drift report schema unchanged) with `confirmed` only for rule `external_deletion_v1` (successful exact-resource delete, existence anchor A, unambiguous caller, no concurrency/automated overlap) and `unknown` with a fixed reason code otherwise; update/create/replace drift stays `unknown`.
- **Validation**:
  - [x] Test matrix: positive, negative, ambiguous, delayed, multiple-event, missing-log and existence-anchor sequences; contract invariants; byte-identical output; safeguard mutants.
- **Implementation Notes**:
  - Provides empirical attribution when log evidence exists.
  - Claim wording is fixed: "Azure recorded caller X performing the successful delete of this exact resource under the correlation rules." Never "X caused the drift" or "X made the out-of-band change". AI never performs attribution; `actor`/`confirmed` in the AI report stay `unknown`/`false`.
  - Anchor A (successful exact-resource write before the candidate delete) only; Anchor B (trusted prior detection run) is defined but has no producer/input yet (blocker B1).
- **Completion Notes**:
  - **Files**: new `src/drift_engine/attribution.py`, `tests/test_attribution.py`; changed `src/drift_engine/cli.py` (`attribute` subcommand; command-aware internal-error message), `src/drift_engine/__init__.py` (module list). **Unchanged**: `activity_logs.py`, `models.py`, `schemas/`, `src/ai_engine/`, `pyproject.toml`/`requirements.txt` (no new dependency), Terraform, workflows.
  - **Algorithm** (as approved): document level — `report_invalid` / `evidence_invalid` / `report_failed` (input), `evidence_mismatch` (binding: run_id + plan_timestamp, both non-null, **and** evidence targets = report's drifted addresses), `evidence_failed` (evidence outcome failed); per drifted resource P3 detection time → P4 7.1 target status → P5 settled (`settled_until ≥ finished_at + 5 min`) → R0 delete only (`update_not_attributable`) → R1 `order_ambiguous` (overlap or touch) → R2 `no_deletion_event` / `latest_operation_is_write` → R3 Anchor A = latest successful exact-resource write, else `no_existence_anchor` → R4 exactly one successful delete after the anchor (`multiple_successful_deletes`) and no unresolved group (`unresolved_operation`) → R5 `caller_missing` / `caller_inconsistent` → R6 candidate ends before `started_at − 5 min` (`concurrent_with_detection`) → R7 no Policy/Autoscale event on the exact resource within candidate ± 5 min (`automated_activity_overlap`) → `confirmed` (rule `external_deletion_v1`, claim `recorded_successful_delete`). Groups = (correlationId, case-folded operation) on the case-folded exact resource; successful = any Succeeded row (mixed Failed+Succeeded included); subStatus unused (204 is a successful delete); only Administrative events are lifecycle events; failed groups and non-lifecycle events → `related_event_ids`; groups starting after `finished_at + 5 min` → `after_detection_event_ids`.
  - **Output** `drift_attribution.json` (`attribution_version`/`rules_version` 1): binding (run_id, plan_timestamp, evidence SHA-256, evidence outcome, window, 20/5-minute margins), per resource `drift_action`, `resource_id`, attribution (`status`, `reason`, `rule`, `claim`, `caller`, `anchor` {kind `write_event`, event_ids, run_id null, time}, decisive/candidate/related/after-detection event ids). Strict frozen models with invariants (confirmed ⇔ rule+claim+caller+anchor+decisive, unknown ⇔ reason; disjoint sorted id lists; non-delete never confirmed; precondition reasons list no events; outcome ⇔ failure/reasons). `verify_against_evidence` independently re-checks hash, subject, every id, decisive/anchor groups, caller and anchor-before-delete; the CLI refuses to write (exit 70) if it fails. Claim text only via `render_claim` template. Output 0600; summary and logs carry counts and reason codes only (no callers, IDs).
  - **CLI**: `drift-engine attribute --report <drift report JSON> --evidence activity_log_evidence.json [--output]`; exit 0 complete, 1 incomplete/failed (written), 2 usage, 70 re-check failure/internal, 73 write error. Not in any workflow.
  - **Tests** (session-scratchpad venv; no Azure/credentials; evidence produced by the real 7.1 collector over a fake source): `tests/test_attribution.py` **82 passed** (126 subtests) — anchor sequences 17 (write→delete confirmed; write→delete→delete unknown for both; write→delete→write→delete confirmed on the final delete; no anchor; rewrite; unresolved; failed/canceled ignored; mixed-outcome counted successful; disk-case regression; failed/unresolved/pre-window writes not anchors; old in-window write; 204; Succeeded-only), grouping/matching 13, callers 4, ambiguity/concurrency/automation/after-detection 6 (boundaries ±1 s), preconditions 10 (settled boundary, detection time, incomplete/failed scopes, non-queried targets, update/create/replace drift, binding mismatches, 10 input failures), determinism 3 (byte-identical under shuffling with equal paging; decisions identical under any paging; `decide` order-independent), contract 12 (unknown fields incl. `actor`/`confirmed`/`caller_identity` at every level, each invariant, re-check tampering), safety 5 (claim wording, AST: no Azure/network/clock imports or calls, subprocess: no `azure.*` loaded, AI layer never imports attribution, input files byte-unchanged), CLI 10, **safeguard mutants 25/25 caught** (in-process mutated copies of `attribution.py`: anchor ×3, multiple-delete, unresolved ×2, after-detection, caller ×2, concurrency ×3, mixed-outcome, order, latest-write, update drift, automation, category, operation casing, descendants, settle, binding, target set, target status, correlation; a no-op control is not caught). Full suite **1664 passed** (1276 subtests); `drift_engine` gate **99.94%** (`attribution.py` 100% lines and branches); core-only venv (no Azure/LLM packages) **988 passed / 676 skipped** with all 82 attribution tests passing; `unittest discover` OK in both venvs; `./scripts/validate.sh` passed; gitleaks 8.30.1 on changed files: no finding in new/changed lines (pre-existing "TLS/encryption" false positive only); manual scan: synthetic GUIDs and `example.com` callers only.
  - **Implementation decisions within the approved design**: binding failures and failed evidence are document-level failures (every resource `evidence_mismatch` / `evidence_failed`); binding additionally requires the evidence's target set to equal the report's drifted addresses; statuses compared exactly (`Succeeded`, `Failed`, `Canceled`); the report input must be JSON; safeguard mutants run in the default suite (the Task 6.7 harness is scoped to `src/ai_engine/`).
  - **Limitations / blockers**: B1 — Anchor B has no producer, so deletions without an in-window successful write stay `no_existence_anchor`; B4 — downstream caller exposure (Phase 8, public repo) undecided; evidence and report from two different plans that share run_id, plan timestamp and drifted addresses cannot be told apart (the report carries no resource IDs); no deletion of a project resource has been observed in real Azure (mechanics verified on other resources, 2026-10-03).

#### Task 7.3 — Unknown/Missing Log Handling & Fallback Logic
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Implement fallback behavior when Activity Logs are disabled, expired, or lack relevant events.
- **Amendment (2026-10-04, requirement gap — see Phase 7 header)**: the AI-boundary statement ("`ai_engine` never imports `activity_logs`/`attribution` … the AI report is identical with and without evidence/attribution files") is superseded by Tasks 9B.3/9B.4. `ai_engine` may read only the public investigation model (`drift_engine.investigation_public`), never raw evidence or the restricted investigation, and never imports `activity_logs`/`attribution`. Investigation reports use the Phase 9B requirement wording "not confirmed by available evidence" for every unconfirmed fact. `origin_statement` ("Change origin could not be confirmed") remains only for the Task 7.2 attribution document. The record below is historical.
- **Dependencies**: Task 7.2
- **Files/Areas**: `src/drift_engine/attribution.py` (fallback display mapping), tests. *(Corrected 2026-10-03 per the approved Task 7.3 design review: the Activity Log collector `activity_logs.py` is unchanged.)*
- **Acceptance Criteria**:
  - [x] Every drifted resource whose origin is not confirmed (any Task 7.2 `unknown` reason; failed, mismatched, invalid or missing evidence; no attribution document; address not listed) resolves to the fixed display statement "Change origin could not be confirmed", with the machine-readable `status`/`reason` kept and `caller` null. *(Reworded 2026-10-03 per the approved design: a rendering/display mapping, not a stored `caller_identity` field; the drift report schema is unchanged. Confirmed attributions keep the Task 7.2 claim template.)*
  - [x] Prevents AI layer from inventing or assuming caller identities without log data.
- **Validation**:
  - [x] Test execution with empty log response.
- **Implementation Notes**:
  - Strict compliance with anti-hallucination rules.
- **Completion Notes**:
  - **Files**: `src/drift_engine/attribution.py` (additions only: `UNCONFIRMED_ORIGIN = "Change origin could not be confirmed"`, `origin_statement(document, address)`, docstring), new `tests/test_attribution_fallback.py`. **Unchanged**: `activity_logs.py`, `cli.py`, the `drift_attribution.json` contract (no new field, no version change), the drift report schema, `src/ai_engine/` (code and contract), dependencies, Terraform, workflows, the Task 7.1/7.2 tests. No Anchor B.
  - **Fallback**: `origin_statement` returns the Task 7.2 claim template only for a non-failed document that lists the address as `confirmed`; every other case — any of the 19 `unknown` reasons (missing/expired/empty/unsettled/incomplete/ambiguous evidence), a failed document (`report_invalid`, `report_failed`, `evidence_invalid`, `evidence_mismatch`, `evidence_failed`), an unlisted address, or no document (`None`) — returns "Change origin could not be confirmed". Display text only: never stored in any output; `status`/`reason` stay machine-readable and `caller` stays null unless confirmed (Task 7.2 contract). Activity Logs cannot be disabled at subscription level; "disabled" appears as collection failures (`authorization_failed`, `credential_unavailable`, `azure_sdk_unavailable`, …) → `evidence_failed`.
  - **AI layer** (criterion 2, no AI change): `ai_engine` never imports `activity_logs`/`attribution` or reads their files, `run_analysis` has no Activity Log input, and a model that names a caller is rejected (`unsupported_attribution`, `summary_unsupported_attribution`) while the AI report keeps `attribution = {actor: unknown, confirmed: false, pending: phase_7_activity_log}`, contains no caller, and passes `verify_report`; the AI report is identical with and without evidence/attribution files.
  - **Tests** (session-scratchpad venv; no Azure/credentials): `tests/test_attribution_fallback.py` **19 passed** (64 subtests) — empty Activity Log response end to end (7.1 collector → 7.2 → fallback) and through the real CLI pipeline (`analyze` → `activity-logs` with a fake source and pinned clock → `attribute`, drift report bytes unchanged), every 7.1 failure code, one failed scope, missing/invalid/mismatched evidence and report, no document / unlisted addresses, SDK unavailable, out-of-window and pre-window anchors, not settled, **all 19 reason codes produced and mapped** (caller null, statement never contains a caller), confirmed positive control (UPN and GUID), fallback never stored, failed-document defense in depth, determinism, AI boundary (always) and 3 AI anti-caller tests (`[ai]` extra). Three ad hoc fallback mutants (failed-document guard, claim for unknown, `None` document) are each caught. Task 7.2 suite unchanged and passing (82, incl. 25/25 safeguard mutants). Full suite **1683 passed** (1340 subtests); `drift_engine` gate **99.94%** (`attribution.py` 100% lines and branches); core-only venv **1004 passed / 679 skipped** (the 3 AI tests skip); `unittest discover` OK in both venvs; `./scripts/validate.sh` passed; gitleaks 8.30.1: no finding in new/changed lines (pre-existing "TLS/encryption" false positive only).
  - **Note (no change, out of scope)**: the AI report's `attribution.pending = "phase_7_activity_log"` label remains; integrating deterministic attribution into presentation (and caller exposure, blocker B4) is for a later task.

---

### PHASE 8 — GitHub Issue / PR Automation
**Status**: 🟢 COMPLETED

Phase 8 automates workflow actions upon drift detection by creating structured GitHub Issues and proposing remediation PRs.

> **Phase 8 completion and scope change (Task 8.2 design review, 2026-10-03, user-approved option R1):** Phase 8 is complete once Tasks 8.1 and 8.3 are complete (both 🟢 COMPLETED 2026-10-03). Task 8.2 (automated remediation branch/PR generation) is 🔴 BLOCKED — superseded by Phase 11; its remediation scope moved to Phase 11 (Tasks 11.1 and 11.3), where it is designed together with the human approval gates. No Task 8.2 implementation, workflow, permission or repository-setting change was made.

> **Phase 8 restructuring (approved 2026-10-03, Task 8.1 design review and final architectural review):**
> - **Execution order: 8.1 → 8.3 → 8.2** (tasks keep their numbers; they are listed here in execution order and the dependency fields enforce it).
> - **Public-repository profile** for every Phase 8 GitHub surface (issue titles/bodies, comments, PRs, labels, workflow logs, step summary): no Activity Log caller identity in any form (UPN, object ID, claim text, hash); no Phase 7 inputs (`activity_log_evidence.json`, `drift_attribution.json`) and no import of `drift_engine.activity_logs` / `drift_engine.attribution`; no LLM; `GITHUB_TOKEN` only, job-level permissions. **This resolves blocker B4 (Task 7.2).**
> - **Phase 9B note (2026-10-04)**: this profile is unchanged for every Phase 8 surface. Phase 9B adds no investigation content, caller type, client application or Activity Log data to GitHub issues, comments or the issues job. Investigation data appears only in the separate investigation and AI artifacts, under the Phase 9B public profile (G11).
> - **No AI analysis in Phase 8**: the deferred Task 6.6 AI CLI/workflow integration is owned by Phase 9A, not by Phase 8.

#### Task 8.1 — Deterministic Drift Issue Creator
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: For a valid drifted detection run, deterministically create or update one structured GitHub Issue per drifted resource from the run's drift report artifact. *(Reworded 2026-10-03 per the approved Task 8.1 design review: the drift report is the only input; "AI security analysis", "cost impact" and "recommended HCL fix" are removed — the AI report is not produced in CI (Phase 9A) and Task 6.6 options are never ranked or recommended.)*
- **Dependencies**: Task 4.6 (drift report contract), Task 5.4 (`drift-report-<run_id>` artifact), Task 5.5 (`drift_detected` output)
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: the issue job's input becomes the **public** drift report of the `drift-report-<run_id>` artifact. `scripts/github_automation.py` validates it against the public model and renders the new S/R/D status `withheld` like any other status. The issue profile is unchanged (never values; GUID/ARM-ID masking stays as a second layer). Issue fingerprints are unchanged. An issue whose canonical content changes (a status becoming `withheld`) is updated once. The record below is historical.
- **Files/Areas**: new `scripts/github_automation.py` (not in `src/drift_engine/`: that package must not call the network), new `tests/test_github_automation.py` (incl. workflow structure tests), `.github/workflows/drift-detection.yml` (one new issues job; other jobs unchanged; workflow change requires explicit approval), `README.md`, `docs/drift-detection-spec.md` §8.3. **Unchanged**: `src/drift_engine/`, `src/ai_engine/`, `schemas/`, Terraform, `pyproject.toml` / `requirements.txt` (no new dependency), other workflows. *(Expanded 2026-10-03 per the approved Task 8.1 detailed design review.)*
- **Acceptance Criteria** *(revised 2026-10-03 per the approved Task 8.1 detailed design review and marker-semantics review)*:
  - [x] **Gating**: acts only when the workflow output `drift_detected` is the literal `'true'` and the report validates with `DriftReport` (`drift_engine.models`) with `outcome = succeeded` and `has_drift = true`; no action for `false`, `unknown`, failed or invalid reports.
  - [x] **Exact attempt binding**: `run.run_id` must equal `github-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}` exactly and `run.environment` must equal the workflow environment; otherwise `attempt_mismatch` / `run_mismatch` and no API write (a "re-run failed jobs" attempt never publishes; "re-run all jobs" produces fresh evidence).
  - [x] **Publish only in GitHub Actions**: dry-run is the default (zero API calls, rendered requests written locally); `--publish` is accepted only when `GITHUB_ACTIONS == "true"` and the run binding holds. Local runs are dry-run only.
  - [x] **Serialization required**: issue publication runs only inside the existing workflow-level `concurrency` group (`drift-detection-<env>`, `cancel-in-progress: false`); no second workflow writes issues. The stale-run guard depends on this.
  - [x] **Exact issue set**: one issue per resource with `drift_action != null` (the `has_drift` set, incl. converged and noise-only drift; no severity threshold); `config_change`, `resource_added`, `resource_removed` and `in_sync` resources never get an issue.
  - [x] **Input**: the drift report from the same run's artifact only — no AI report, no Activity Log evidence or attribution, no caller/origin line.
  - [x] **Public-repository content**: full structure-only body (environment, address, type, classification, drift action, severity, ambiguous flag, changed paths with attribute class and S/R/D value status, link to the run) only when resource severity is INFO or LOW, the type is not in `drift_engine.severity.SECURITY_SENSITIVE_TYPES` and no change is redacted; otherwise the reduced body (no paths). Never real/state/desired values, HCL fragments or `severity.reasons`. Subscription/tenant GUIDs and ARM IDs masked in title and body; after masking, path segments not matching `[A-Za-z0-9_.-]{1,64}` are replaced by a fixed placeholder; at most 50 paths listed ("…and N more").
  - [x] **Safe rendering**: untrusted text (addresses, path segments) only inside dynamically fenced code spans, after stripping control, bidi, zero-width and format characters; no tables, no assignees, no milestones, no `@` outside code spans; title = fixed template + validated environment + address restricted to `[A-Za-z0-9_.\-\[\]"]` (others replaced), ≤ 200 characters with deterministic truncation + short hash. Byte-identical title/body for identical input.
  - [x] **Marker contract** (versioned, first body line, validated tokens only; consumed by 8.3): marker version; SHA-256 fingerprint of `(environment, address)` with version prefix; `content_hash` = SHA-256 of the canonical title/body excluding the marker and run-specific lines, including the renderer version; `run_id` and `plan.timestamp` of the run that **last changed** the content (never the last-seen run).
  - [x] **Matching / deduplication**: open issues only, listed by label and creator with pagination; pull requests filtered out; an issue matches only with the automation label, `user.login == "github-actions[bot]"`, `user.type == "Bot"` and a first-line marker with the same fingerprint (spoofed issues ignored). More than one matching issue → update the lowest number, leave the others untouched, report `duplicate_issues`.
  - [x] **PATCH / no-op rules**: PATCH title and body only (never labels, assignees, state or milestone) when `new plan.timestamp > marker plan.timestamp` **and** `new content_hash ≠ marker content_hash`; the marker then takes this run's `run_id`, `plan.timestamp` and `content_hash`. Otherwise unchanged: older timestamp + different content → `stale_evidence`; equal timestamp + different content → `conflicting_evidence`; older or equal timestamp + identical content and newer timestamp + identical content → silent no-op (marker not advanced). Equal timestamps never update.
  - [x] **Invalid marker fails closed**: a matching fingerprint with an unparsable marker or unsupported marker version → `marker_invalid` / `marker_version_unsupported`, no PATCH, no replacement issue, exit 1.
  - [x] **Labels**: created once by the user (documented); the script verifies the label exists before any listing or creating (`label_missing`, fail closed — GitHub would otherwise create missing labels on issue creation) and never creates labels.
  - [x] **API client**: standard-library `urllib` REST client (no PyGithub, no new dependency); `GITHUB_API_URL` must be `https://api.github.com`, `GITHUB_REPOSITORY` validated, redirects disabled, `next` links validated against the same host and repository path; fixed headers; fixed error codes only; token never logged.
  - [x] **Retries and limits**: GET and PATCH retried at most 3 attempts with `Retry-After` capped at 60 s; issue-creating POST never retried; secondary rate limit → `rate_limited`; deterministic per-run cap (order: severity descending, then address) → `cap_exceeded`, exit 1. A GitHub API failure never changes the drift result or `drift_detected`.
  - [x] **Least-privilege job**: dedicated issues job, `needs: [preflight, plan-and-analyze]`, `if: needs.plan-and-analyze.outputs.drift_detected == 'true'`, permissions exactly `contents: read` and `issues: write` (`actions: read` only if the real run proves the same-run artifact download needs it); no `id-token`, no Azure login, no raw plan evidence; checkout with `persist-credentials: false`; core `pip install .` only; downloads `drift-report-${{ github.run_id }}`; `GITHUB_TOKEN` only in the script step's environment; no `continue-on-error`; own step summary with counts and codes only.
  - [x] **Task 8.3 contract**: 8.3 must reuse the same exact attempt binding, publish-only-in-Actions rule, serialization requirement and timestamp rules (close only on a valid run with `plan.timestamp > marker plan.timestamp`; equal timestamps never act); the versioned marker lets 8.3 record its closing run.
- **Validation**:
  - [x] Fake-transport test suite: gating matrix, attempt/run/environment binding, issue set on all `plan_evidence` and `report_plans` fixtures, dedup/spoofing (wrong author/type, missing label, marker not on first line or inside a code span, closed issue, PR item, two matches), pagination incl. a foreign `next` link, every marker case (older/equal/newer × same/different content, invalid and unsupported markers), hostile rendering (backticks, `<!--`, `@user`, `#1`, URLs, bidi/zero-width, emails, GUIDs, ARM IDs: no live mention/reference/link/HTML, no GUID or `/subscriptions/` survives), no-caller/no-value (a confirmed `drift_attribution.json` and evidence file beside the report never affect output), every error code, retries/no POST retry, blocked redirect/host, token never logged, per-run cap, determinism under shuffling.
  - [x] Import boundary (subprocess): no `ai_engine`, `drift_engine.activity_logs`, `drift_engine.attribution`, `azure*`, `openai`, `langchain*` or `github` module loaded; network code only in the client class (AST).
  - [x] Workflow structure test (PyYAML): issues job permissions, condition, `needs`, artifact name, token scope, no `id-token`/Azure steps, no `continue-on-error`, concurrency group unchanged, triggers still exactly `schedule` and `workflow_dispatch`, other jobs unchanged.
  - [x] `scripts/github_automation.py` 100% line and branch coverage (own `--cov` run); in-process safeguard mutants (gates, binding, author, label, marker position, stale/equal comparison, no-edit-when-unchanged, masking, key allowlist, reduced-body rule, POST no-retry, label check, PR filter, cap) all caught, a no-op control not caught; full suite, core-only venv and `./scripts/validate.sh` pass.
  - [x] Real validation order, with explicit user approval of each step: inject tag drift (`tests/scenarios/rg_tag_drift_inject.sh`) → dispatch the **current** workflow → download its artifact to `.artifacts/` → local dry-run reviewed by the user → commit the issues job → dispatch → issue created → re-dispatch → no duplicate and no edit → revert (`rg_tag_drift_revert.sh`); the issue stays open for 8.3.
- **Out of Scope**: AI report input or any LLM; Activity Log evidence/attribution and caller identity in any form; closing or reopening issues (8.3); PRs and branches (8.2); label creation by the script; local publication (`--publish` is accepted only inside GitHub Actions); new workflow triggers (`pull_request_target`, `issue_comment`, `issues`); test-input paths in the production workflow; changes to other workflow jobs; Azure changes other than the approved tag-drift validation scenario.
- **Implementation Notes**:
  - Automated tracking of active infrastructure drifts.
  - The GitHub API client approach (REST client vs PyGithub) was decided in the Task 8.1 detailed design review (2026-10-03): standard-library `urllib` REST client; no new dependency may be added without explicit approval.
  - Untrusted text is rendered only in code spans, so the Task 6.6 `md_text` escaping is not reused and `ai_engine` is never imported.
  - Known limitation (accepted, decision C): a reduced body still shows type, address and severity.
- **Progress Notes (2026-10-03)** — implementation and local validation (real-run validation recorded under Completion Notes).
  - **Files**: new `scripts/github_automation.py`, `tests/test_github_automation.py`; changed `.github/workflows/drift-detection.yml` (new `issues` job + header comment only; pushed in `b7363a9` after the dry-run review), `README.md` (Task 8.1 section, label setup, local preview, Phase 8 status/limitation), `docs/drift-detection-spec.md` §8.3 ("Issue publication (Task 8.1)"). No dependency, `src/`, schema or Terraform change.
  - **Implementation decisions within the approved design**: label `drift-detected`; per-run write cap 10 (creates + updates; unchanged issues do not count); dry-run requires `--out-dir` and an empty directory (`out_dir_not_empty`); dry-run and publish both require a `github-<run>-<attempt>` run ID (it is written raw into the marker); `duplicate_issues` is a warning (exit 0), `stale_evidence` / `conflicting_evidence` / marker errors / `cap_exceeded` exit 1; the first API failure stops the run; line breaks in untrusted text become spaces before stripping.
  - **Local validation** (session-scratchpad venvs, Python 3.14; script syntax checked for 3.12): `tests/test_github_automation.py` **63 passed** (209 subtests), `scripts/github_automation.py` **100% lines and branches**; safeguard mutants **32/32 caught**, no-op control not caught; full suite **1746 passed** (1549 subtests), `drift_engine` gate 99.94%; core-only venv **1067 passed / 679 skipped**; `unittest discover` OK in both venvs; `./scripts/validate.sh` passed; gitleaks 8.30.1 on the changed files: no leaks. Two defects found by the tests and fixed: `$` accepted a trailing newline (all patterns now `\Z`); stripping `\n` joined words.
  - **Remaining**: none (see Completion Notes).
- **Completion Notes**:
  - **Commit**: `b7363a9` (`feat: add deterministic drift issue automation`): script, tests, workflow `issues` job, README, spec §8.3, plan. Label `drift-detected` (color `B60205`, "Opened by the drift detection workflow") created once by approval before the push.
  - **Real validation** (each step user-approved, 2026-10-03):
    - Drift injected with `tests/scenarios/rg_tag_drift_inject.sh --apply` (dry run first): only `aitdd_drift_probe=task-3.6` added to `aitdd-dev-main-rg`; Terraform-managed tags and the two child resources (NSG, VNet: tags and `changedTime`) unchanged.
    - Pre-job run **37119797461** (current workflow without the issues job, commit `5a5db47`): all jobs success; artifact `drift-report-37119797461` (SHA-256 `80b38235…3734` verified) downloaded by the user to `.artifacts/`; report valid (strict model + JSON schema), `outcome=succeeded`, `has_drift=true`, bound to `github-37119797461-1`; local dry-run: one request for `module.resource_group.azurerm_resource_group.this["main"]` (LOW, `external_drift`, `tags.aitdd_drift_probe`), 20/20 checks passed (no value/GUID/ARM ID/caller/AI data, marker valid, deterministic), reviewed by the user.
    - **Run 37120331032** (#14, `workflow_dispatch`, `main`, commit `b7363a9`, attempt 1): Preflight, Plan & Drift Analysis (`drift_detected=true`, `{"external_drift":1,"in_sync":4}`), Drift Issues and Report & Summary all **success**; script output `{"codes": [], "created": [1], "mode": "publish", "outcome": "ok", ...}`. **Issue #1** created: title `Drift detected: module.resource_group.azurerm_resource_group.this["main"] (dev)`, author `github-actions[bot]` (Bot), label `drift-detected` only, no assignee/milestone; title and body identical to the dry run except the run-specific marker fields and run line; content hash `179e956d…238b` equal to the dry run's (run-independent); marker v1 valid, fingerprint `5ae4bb28…bed9f1` = SHA-256(v1, dev, address), bound to `github-37120331032-1` / plan `2026-10-03T11:39:46Z`; no tag value, GUID, ARM ID, caller, Activity Log or AI data; 18/18 checks passed.
    - **Run 37120591116** (#15, same commit, attempt 1): all jobs **success**; script output `{"codes": [], "created": [], "unchanged": [1], "updated": [], "outcome": "ok", ...}`; issue #1 byte-identical (title, body, content hash, marker still bound to run 37120331032), `updated_at` unchanged (`2026-10-03T11:40:13Z`), no comments; still exactly one `drift-detected` issue — dedup and no-edit-when-unchanged proven.
    - **`actions: read` not needed**: the same-run `actions/download-artifact@v4` download succeeded with `contents: read` + `issues: write` only; the job permissions stay unchanged.
    - **Drift reverted** with `tests/scenarios/rg_tag_drift_revert.sh --apply`: probe tag removed; `aitdd-dev-main-rg` tags again exactly the Terraform `common_tags` (`environment=dev`, `managed_by=terraform`, `project=ai-terraform-drift-detector`), identical to the pre-injection snapshot; NSG and VNet unchanged (tags and `changedTime`). No workflow dispatched after the revert.
  - **State left for Task 8.3**: issue #1 stays open by design (8.1 never closes issues); evidence-based closure, e.g. on the next valid no-drift run, is Task 8.3. The deprecation annotations (Node.js 20 actions, `ubuntu-latest` → Ubuntu 26) are pre-existing notices, not errors.

#### Task 8.3 — Drift Issue Lifecycle / Resolution
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Design**: 🔒 locked 2026-10-03 (Task 8.3 design review + edge-case review, user-approved).
- **Objective**: Close 8.1-owned open drift issues, based on evidence, when a later valid detection run of the same environment reports the issue's resource as present and no longer drifted. *(Reframed 2026-10-03 per the approved Phase 8 restructuring: executes second, after 8.1; deduplication is owned by 8.1; PR lifecycle/closure moved to 8.2. Matching, gating, closing and failure scope revised 2026-10-03 per the Task 8.3 design and edge-case reviews; the earlier "closing comment" and "resolution line" are removed.)*
- **Dependencies**: Task 8.1 (fingerprint/marker/label contract, GitHub client, issues job)
- **Amendment (2026-10-05, Task 9B.4A)**: the lifecycle gate validates the **public** drift report (same script and input as Task 8.1's amendment). Closure semantics and the fingerprint are unchanged. The record below is historical.
- **Files/Areas**: `scripts/github_automation.py` (lifecycle gate, resolvable set, close decision, close request, summary field `closed`, new codes), new `tests/test_github_issue_lifecycle.py` (reuses the 8.1 test fakes; mutants added to the existing safeguard harness), `.github/workflows/drift-detection.yml` (existing `issues` job condition and step name/comments only; workflow change requires explicit approval), `README.md`, `docs/drift-detection-spec.md` §8.3. **Unchanged**: marker v1, `src/`, schemas, Terraform, dependencies, triggers, permissions, concurrency, other jobs.
- **Interaction with completed Task 8.1** (planned extension, not a change to 8.1's record): the `issues` job condition is widened from `'true'` to `'true' || 'false'` (anticipated in this task's original Files/Areas). A `'false'` run may **only close** issues; 8.1 create/update gating (`'true'`, `has_drift = true`) is unchanged. 8.1 matching stays open-issues-only. The closing run is not recorded in the marker (the 8.1 contract allows but does not require it).
- **Acceptance Criteria**:
  - [x] **Lifecycle gate** (`'true'` and `'false'` runs): report valid under `DriftReport`, `outcome = succeeded`, `has_drift` agrees with `drift_detected` (`'true'` ⇔ true, `'false'` ⇔ false; otherwise `report_inconsistent`), exact attempt binding `run.run_id == github-${GITHUB_RUN_ID}-${GITHUB_RUN_ATTEMPT}`, `run.environment` equals the workflow environment, well-formed `plan.timestamp`, all report addresses unique, `--publish` only inside GitHub Actions. `unknown`, failed or invalid runs never close anything (the job does not run for them).
  - [x] **Serialization**: lifecycle actions run only inside the existing workflow-level concurrency group (`drift-detection-<env>`, `cancel-in-progress: false`), in the existing `issues` job.
  - [x] **Matching**: reuses the 8.1 contract unchanged — open issues only, listed by label and creator with pagination, pull requests filtered out, automation label + `user.login == "github-actions[bot]"` + `user.type == "Bot"` + first-line marker v1.
  - [x] **Resolvable set / closure rule**: an open 8.1-owned issue is closable only if its marker fingerprint equals `fp(environment, address)` for an address **present in this run's report** whose resource has `drift_action == null`. Issues whose fingerprint is drifted in this run follow the 8.1 create/update path and are never closed.
  - [x] **`resource_not_in_report`**: an issue whose fingerprint matches no address in the report (resource removed or moved, or another environment) stays open — no write — and is reported as a warning; such issues need a manual close (documented).
  - [x] **Timestamp ordering**: close only if this run's `plan.timestamp` is newer than the marker's `plan`. Equal → `conflicting_evidence`, older → `stale_evidence`; the issue stays open.
  - [x] **Close request**: exactly one `PATCH /repos/{repo}/issues/{issue_number}` with payload exactly `{"state":"closed","state_reason":"completed"}` — no `body`, `title`, `labels`, `assignees` or `milestone`, and no comment POST. The close is an idempotent PATCH and is retried under the existing PATCH retry rules (at most 3 attempts, `Retry-After` capped at 60 s). Closing never overwrites human edits. Closure evidence is the GitHub issue timeline plus the workflow step summary (closed issue numbers and the run).
  - [x] **Duplicates**: every valid matching duplicate of a resolvable fingerprint is closed (each with its own timestamp check); `duplicate_issues` is reported.
  - [x] **One pass, shared cap**: one label check and one issue listing per run; 8.1 create/update (drifted resources, severity descending then address) then 8.3 closes (issue number ascending); creates, updates and closes share the deterministic per-run cap.
  - [x] **Failure scope — run-level failures** (exit 1, before any write): invalid/failed/inconsistent evidence; `run_mismatch` / `attempt_mismatch`; invalid or mismatched environment; publish outside GitHub Actions; invalid repository or API URL; missing token; `label_missing`; issue-listing/API failures; `pagination_limit`; `invalid_response`; `blocked_request`.
  - [x] **Failure scope — during writes**: any API failure stops all further writes and exits 1; `cap_exceeded` stops all further writes and exits 1.
  - [x] **Failure scope — per-issue anomalies** (`marker_invalid`, `marker_version_unsupported`, `conflicting_evidence`, `stale_evidence`): skip the affected issue, perform no write for it, continue processing the remaining issues/resources in deterministic order, and exit 1 at the end.
  - [x] **Failure scope — warnings** (`resource_not_in_report`, `duplicate_issues`): no write for the affected issue, processing continues, reported in the step summary, exit 0 if there is no other failure.
  - [x] **Recurrence**: a resource that drifts again after its issue was closed gets a **new** issue from 8.1 (8.1 matches open issues only); 8.3 never reopens issues.
  - [x] **Human actions** (documented): 8.1 owns the automation-generated title/body and may rewrite them on an update; human discussion belongs in comments; removing the `drift-detected` label opts the issue out of automation; a human-closed issue whose drift persists gets a new issue on the next drifted run; a human-reopened issue whose resource is still not drifted is closed again by the next valid newer run; 8.3 close never rewrites the body, so human edits are preserved even if they occur between issue listing and the close PATCH.
  - [x] **Public-repository profile and security**: closing writes no values, GUIDs, ARM IDs, caller identity, Activity Log/attribution data or AI output; no Phase 7 input or import; no LLM; no Terraform action; permissions unchanged (`contents: read`, `issues: write`); `GITHUB_TOKEN` only in the script step; existing API-host, redirect, `next`-link and retry rules reused; no new triggers.
  - [x] **Workflow**: the existing `issues` job condition becomes `${{ needs.plan-and-analyze.outputs.drift_detected == 'true' || needs.plan-and-analyze.outputs.drift_detected == 'false' }}` (implicit `success()` kept); `needs`, permissions, artifact download, concurrency and triggers unchanged; `unknown` never runs the job.
- **Validation**:
  - [x] Gating matrix: `'true'` / `'false'` / `unknown` × report succeeded/failed/invalid × `has_drift` true/false/mismatched; attempt/environment binding; publish outside Actions; duplicate addresses; a `'false'` run never creates or updates.
  - [x] Resolvable set on every fixture (present minus drifted); another environment's fingerprint never matches; `resource_not_in_report` causes no write.
  - [x] Lifecycle transitions: open → closed (newer); equal → `conflicting_evidence`; older → `stale_evidence`; invalid/unsupported marker; all valid duplicates closed; partial resolution in a `'true'` run (one updated, one closed, one created).
  - [x] Recurrence: a closed issue is never reopened; the next drifted run creates a new issue with a fresh marker; closed issues never appear in matching.
  - [x] Human actions: human-closed, human-reopened, label removed, body edited with marker intact or broken.
  - [x] Close payload contains exactly `state` and `state_reason` and never contains `body`; no comment POST.
  - [x] Human-edit race between listing and PATCH preserves the edited body.
  - [x] Mixed run with an invalid marker, a stale timestamp, an equal timestamp, a `resource_not_in_report` issue, a valid closure and a valid update: only the valid writes occur, processing continues deterministically, exit 1.
  - [x] Warnings-only run (`resource_not_in_report` and/or `duplicate_issues`) exits 0.
  - [x] API failure on the first close prevents all subsequent writes; close retried on 5xx/429 and given up after 3 attempts; `rate_limited`; pagination and foreign `next` link reuse.
  - [x] No-leakage: closing writes no values/GUIDs/callers; Phase 7 files beside the report have no effect.
  - [x] Workflow structure test: exact new condition; `unknown` excluded; permissions, `needs`, triggers and concurrency unchanged (replaces a real `unknown` run, which cannot be produced safely).
  - [x] Safeguard mutants (existing in-process harness), each caught: no timestamp check; `>` → `>=`; resolvable set includes fingerprints not in the report; drifted exclusion removed; close in an `unknown` run; create/update in a `'false'` run; only the lowest duplicate closed; closed issue reopened; `state_reason` dropped; comment POST added; marker check skipped on close; cap not applied to closes; close payload includes `body`; per-issue anomaly aborts the run; per-issue anomaly exits 0; `resource_not_in_report` causes a close. A no-op control is not caught.
  - [x] `scripts/github_automation.py` keeps 100% line and branch coverage; full suite, core-only venv, `unittest discover`, `./scripts/validate.sh` and gitleaks pass.
  - [x] Real validation, each step user-approved: push the job change → dispatch on the current reverted Azure state (`drift_detected=false`): issue #1 closed with `state_reason=completed`, body and marker unchanged, step summary lists #1 → re-dispatch: no API writes, #1 stays closed and unchanged. Optional recurrence cycle (separate Azure approval): re-inject drift → dispatch → new issue (#1 still closed) → revert → dispatch → new issue closed.
- **Out of Scope**: PRs and PR closure (8.2); executing `terraform apply` (8.3 never applies; it only observes valid detection runs); Activity Log evidence, attribution and caller identity; AI/LLM; reopening issues; comments; mapping moved resources (`previous_address`); marker version changes; new workflow triggers; closing on anything other than evidence from a valid run.
- **Implementation Notes**:
  - Complete issue lifecycle management.
- **Progress Notes (2026-10-03)** — implementation and local validation (real-run validation recorded under Completion Notes).
  - **Files**: `scripts/github_automation.py` (lifecycle gate via `evidence_from_report(..., drift_detected)`, `Evidence.resolved`, `plan_closures`, `GitHubClient.close_issue` with `CLOSE_PAYLOAD`, closure pass after the unchanged 8.1 loop, summary field `closed`, warning `resource_not_in_report`, step summary lists closed issues); `.github/workflows/drift-detection.yml` (job condition `'true' || 'false'`, step renamed "Manage Drift Issues", comments; pushed in `dca6f4c`); new `tests/test_github_issue_lifecycle.py`; `tests/test_github_automation.py` (fake PATCH applies the payload as sent + edit-race hook; 15 lifecycle mutants and scenarios added to the shared harness); `README.md`; `docs/drift-detection-spec.md` §8.3. No dependency, `src/`, schema or Terraform change.
  - **8.1 tests adjusted for the locked extension only**: `'false'` is no longer a skip value (now `unknown`/other values); the workflow condition assertion; a bot-owned issue whose fingerprint matches no report address now yields the `resource_not_in_report` warning (still no write); mutant strings for the two changed gate lines. 8.1 create/update behaviour is unchanged.
  - **Implementation decisions within the locked design**: closures run after the 8.1 create/update loop (so a cap hit there skips closures); `not_processed` counts remaining closes when the cap is hit in the closure pass; issues whose first line has no readable fingerprint are ignored (as in 8.1 matching); a dry-run of a `'false'` run validates the evidence and writes an empty `requests.json` (closures need the issue list); "closed issue reopened" is covered by the existing `open-state` mutant (closed issues never match).
  - **Local validation** (session-scratchpad venvs; no GitHub/Azure calls): lifecycle + 8.1 suites **94 passed** (286 subtests); `scripts/github_automation.py` **100% lines and branches**; safeguard harness **45/45 mutants caught** (15 for 8.3), no-op control not caught; full suite **1777 passed** (1626 subtests), `drift_engine` gate 99.94%; core-only venv **1098 passed / 679 skipped**; `unittest discover` OK in both venvs (650 tests); `./scripts/validate.sh` passed; gitleaks 8.30.1 on changed files: no leaks; no unsafe Unicode; Python 3.12 syntax checked.
  - **Remaining**: none (see Completion Notes).
- **Completion Notes**:
  - **Commit**: `dca6f4c` (`feat: add evidence-based drift issue lifecycle`): script, workflow condition/step name, lifecycle tests, 8.1 test adjustments, README, spec §8.3, plan.
  - **Real validation** (user-approved, 2026-10-03; Azure state reverted after Task 8.1 and unchanged — `aitdd-dev-main-rg` tags exactly the Terraform `common_tags`; no Azure change in this task). Pre-run snapshot of issue #1: open, `state_reason` null, `updated_at` `2026-10-03T11:40:13Z`, body SHA-256 `6405eab7…5589a6b`, events `labeled` only, no comments, the only issue in the repository.
    - **Run 37122119622** (#16, `workflow_dispatch`, `main`, commit `dca6f4c`, attempt 1): Preflight, Plan & Drift Analysis, Report & Summary and Drift Issues all **success**; `drift_detected=false`, plan exit 0, classification `{"in_sync":5}`; script output `{"closed": [1], "codes": [], "created": [], "updated": [], "unchanged": [], "outcome": "ok", ...}`; step summary "closed: 1 … Closed issues: #1 … Codes: none". **Issue #1 closed**: `state=closed`, `state_reason=completed`, `closed_by` `github-actions[bot]`, `closed_at`/`updated_at` `2026-10-03T12:13:38Z`; body byte-identical (SHA-256 `6405eab7…5589a6b`), title identical, marker unchanged (`run=github-37120331032-1 plan=2026-10-03T11:39:46Z`), label `drift-detected` kept, no assignees, **no comment**; events `labeled`, `closed`; still exactly one issue in the repository.
    - **Run 37122243650** (#17, same commit, attempt 1): all jobs **success**; `drift_detected=false`, `{"in_sync":5}`; script output `{"closed": [], "codes": [], "created": [], "updated": [], "unchanged": [], "outcome": "ok", ...}`; step summary "closed: 0 … Codes: none". **Zero writes**: issue #1 state, `state_reason`, `updated_at`, `closed_at`, title, body and comment count identical to the post-run-1 snapshot; events unchanged (`labeled`, `closed`); repository issue listing identical (1 issue) — not reopened, recreated or updated.
  - **Not exercised in real runs** (covered by tests): conflicting/stale/invalid markers, duplicates, `resource_not_in_report`, cap, partial resolution, API failures. The optional real recurrence cycle was not run (needs a separate Azure approval).

#### Task 8.2 — Automated Remediation Branch & PR Generator
- **Status**: 🔴 BLOCKED — superseded by Phase 11, design review 2026-10-03
- **Objective**: Implement workflow step to generate a Git remediation branch and PR updating Terraform HCL to match desired/remediated state. *(Executes third per the approved Phase 8 restructuring, 2026-10-03; requires its own design review before implementation.)* **Not implemented in Phase 8:** the 2026-10-03 design review found this objective unsafe and non-deterministic under the locked Phase 8 rules (see Design Review); the remediation scope moved to Phase 11.
- **Dependencies**: Task 8.3, Task 6.6
- **Files/Areas**: `scripts/create_remediation_pr.py` — **not created**. No Task 8.2 implementation, workflow, job, permission (`contents: write` / `pull-requests: write`) or repository-setting change ("Allow GitHub Actions to create and approve pull requests") was made.
- **Acceptance Criteria** *(superseded by Phase 11 — not applicable in Phase 8; none of these were implemented or completed)*:
  - [ ] *(superseded)* Creates a remediation branch (proposed name `drift-remediation/<resource_name>-<date>`; not final — subject to the Task 8.2 design review).
  - [ ] *(superseded)* Proposes HCL patch or state sync.
  - [ ] *(superseded → Task 11.1 requirement)* Opens GitHub PR referencing the original drift issue with `Refs #n`, never a closing keyword (issues are closed only by 8.3 evidence-based resolution).
  - [ ] *(superseded)* Owns PR lifecycle, including closing stale remediation PRs.
- **Validation**:
  - [ ] *(superseded)* Test PR generation against the validation target decided in the Task 8.2 design review (a separate test repository is one candidate, not final).
- **Design-review items (unresolved, must be decided before implementation)**: *(resolved 2026-10-03 by the Task 8.2 design review: scope moved to Phase 11)*
  - Public-PR value/HCL disclosure versus the Phase 8 public-repository profile (e.g. non-security drift only, or state sync only).
  - Fragment location: Task 6.6 fragments are `location = "not_determined"`.
  - PR permission scope (`contents` / `pull-requests: write`), branch naming and validation target.
- **Design Review (2026-10-03, user-approved option R1 — move remediation PR scope to Phase 11)**:
  - **F1 Objective inconsistent**: the desired state already is the HCL. For the default plan direction (restore declared) there is no code change; remediation is a reviewed `terraform apply` of `main` (Phase 11). Only "accept the Azure value" changes HCL, and choosing that direction is a human decision (Task 6.6: options are never ranked or recommended; `plan_default` is not a recommendation).
  - **F2 Disclosure**: an "accept" PR must commit the *real* value; a public commit diff is permanent and indexed and real values can be personal data — conflicts with the Phase 8 public-repository profile (decision C: no values published).
  - **F3 Value location not determinable**: values flow through tfvars → modules → `merge(var.common_tags, each.value.extra_tags)`; a generic deterministic HCL edit needs Terraform-aware resolution and format-preserving HCL writing (no standard-library parser; no faithful round-trip parser) or a hand-maintained allowlist; `common_tags`-sourced values affect every resource.
  - **F4 Drift laundering**: an automated PR that codifies an out-of-band (possibly malicious, e.g. an opened NSG) change into Terraform invites approval through review fatigue.
  - **F5 Permissions/configuration**: branch + PR creation needs `contents: write` (can push to any unprotected branch) and `pull-requests: write` plus the repository setting allowing Actions to create PRs; PRs created with `GITHUB_TOKEN` trigger no workflows, so no CI evidence.
  - **F6 Idempotency/human edits**: a scheduled generator facing repeated drift needs branch reuse, never-force-push and closed/merged-PR handling; recurrence after a merge conflicts with `main`.
  - **F7 No implicit apply today**: `drift-detection.yml` never applies; `terraform-auth-test.yml` runs only `plan`; this boundary is locked into Task 11.1.
  - Options considered: R1 (chosen) move to Phase 11; R2 human-authored PR contract (template + docs only); R3 human-dispatched "accept" PR generator with an allowlist and explicit disclosure consent (not chosen: new write permissions, repository-setting change, brittle tfvars editing, decision-C exception).
- **Implementation Notes**:
  - PR must await human review before apply. The Phase 11 human approval boundary is preserved: no apply or merge automation, no LLM-generated patches.
- **Completion Notes**:
  - None — not implemented; superseded by Phase 11 (Tasks 11.1 and 11.3).

---

### PHASE 9 — DevSecOps Integration
**Status**: 🟢 COMPLETED

Phase 9 integrates deterministic security scanners into CI/CD to validate Terraform code security and prevent secret leaks.

> **Phase 9 completion and scope change (2026-10-04, user decision):** Phase 9 is complete once Tasks 9.1, 9.2 and 9.3 are complete (all 🟢 COMPLETED). This follows the Phase 8 precedent, where Task 8.2 was moved to Phase 11.
> - Task 9.4 (Super-Linter / Docker-based code-quality enforcement) is 🔴 BLOCKED — **deferred to Phase 12**. Its locked design (D1–D10) is preserved in Task 9.4 for that later work.
> - Nothing from Task 9.4 was implemented: no files, workflow, image download or Docker run, and no baseline measured.
> - **Terraform linting stays solely Task 9.1 (TFLint).** Any future Super-Linter work keeps its bundled TFLint, `terraform fmt`, Trivy, Checkov and GitLeaks disabled (Task 9.4, D2), so nothing duplicates Tasks 9.1–9.3.

> **Phase 9 rules (apply to Tasks 9.1–9.4; recorded 2026-10-03 per the Phase 9 design re-evaluation).** Task 9.1 already implements these rules in its locked design; Tasks 9.2–9.4 must follow them.
> - **Separation of responsibilities**: Terraform/Azure tooling produces the deterministic drift evidence (Phases 3–5); Phase 9 scanners and linters check code and security quality only; AI only interprets (Phases 6/9A). A scanner or linter finding is never a drift result, and a valid drift result is never a scan failure.
> - **Existing workflows unchanged**: `.github/workflows/drift-detection.yml` and `.github/workflows/terraform-auth-test.yml` are not modified by any Phase 9 task, and Phase 9 scanning is not added to the drift-detection execution path.
> - **No Azure access**: Phase 9 workflows need no Azure credentials and no OIDC (`id-token`).
> - **No drift semantics**: Phase 9 does not create, update, close or label drift issues, and does not publish drift-detection outputs (`drift_detected`, `drift_status`, drift report artifacts).
> - **No suppression to get green**: findings are fixed or escalated as plan-level decisions. They are never suppressed (ignores, disabled rules, lowered thresholds, `continue-on-error`, forced success, exit-code remapping) merely to make CI pass. Any severity threshold must be an explicit, documented design decision.
> - **Exact version pins** for every tool, plugin and image, fixed in the task's design before implementation.
> - **Failures fail the job**: a finding at a blocking severity, the scanner/linter failing to run, and a tool/plugin/image download failure each fail the relevant job.
> - **Design review per task**: every Phase 9 task requires its own design review, with its decisions recorded in this plan, before implementation.

#### Task 9.1 — TFLint Integration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Integrate TFLint (static Terraform linting) with the AzureRM ruleset through one shared script used both locally and in a separate, credential-free GitHub Actions workflow. TFLint is **not** a drift detector: a TFLint failure is a static lint failure, never a drift result. *(Reworded 2026-10-03 per the Task 9.1 design review.)*
- **Dependencies**: Task 1.3 (dev root + resource-group module), Task 2.2 (bootstrap state configuration), Task 5A.1 (network module)
- **Dependency note**: changed 2026-10-03 from Task 5.1. TFLint depends only on the Terraform layout it lints, not on the drift-detection workflow.
- **Locked versions** *(exact; no floating/`latest`; one reviewed change bumps them everywhere)*:
  - TFLint **v0.64.0**: `.tflint.hcl` `tflint { required_version = "= 0.64.0" }`, the CI binary (`terraform-linters/setup-tflint@v6`, `tflint_version: v0.64.0`) and local runs.
  - `tflint-ruleset-azurerm` **v0.32.0** (signed release, `source = "github.com/terraform-linters/tflint-ruleset-azurerm"`): the release selected for Task 9.1.
  - Bundled `ruleset.terraform` 0.15.0 (ships with TFLint v0.64.0), `preset = "recommended"`.
- **Files/Areas**:
  - new `.tflint.hcl` (repository root)
  - new `scripts/run_tflint.sh`
  - new `.github/workflows/security-scan.yml` (job `tflint`; Tasks 9.2/9.3 add their own jobs later)
  - new `tests/test_tflint_integration.py`
  - `README.md`
  - **Baseline Terraform fixes** (prerequisites that make the new lint gate clean and stay compatible with the locked provider `5.7.0`):
    - new `terraform/modules/network/versions.tf` and new `terraform/modules/resource-group/versions.tf`: `required_version = ">= 1.6.0"`; `azurerm = { source = "hashicorp/azurerm", version = "~> 5.0" }` (fixes `terraform_required_version` / `terraform_required_providers`).
    - `terraform/environments/dev/variables.tf` + `terraform/environments/dev/dev.tfvars`: remove the unused root variable `location` from both files (fixes `terraform_unused_declarations`). Confirmed unreferenced 2026-10-03: no `var.location` in the dev root, no `-var location` anywhere; `drift_engine` does not read plan `variables`. Resource locations come from `resource_groups[*].location` and do not change.
    - `terraform/bootstrap/main.tf`: add `lifecycle { prevent_destroy = true }` to `azurerm_storage_account.tfstate` and `azurerm_storage_container.tfstate` (fixes `azurerm_resources_missing_prevent_destroy`). This is a real safety control for the Terraform remote-state infrastructure, not a lint workaround.
  - **Unchanged**:
    - `.github/workflows/drift-detection.yml` and `.github/workflows/terraform-auth-test.yml` (byte-identical)
    - both `.terraform.lock.hcl` files
    - `scripts/validate.sh`, `scripts/generate_plan_json.sh`
    - `src/`, `schemas/`, `pyproject.toml` / `requirements.txt`
    - all other Terraform files
- **Acceptance Criteria** *(revised 2026-10-03 per the Task 9.1 design review)*:
  - [x] **`.tflint.hcl`**:
    - `tflint { required_version = "= 0.64.0" }`
    - `config { call_module_type = "local" }`, with no `varfile`
    - `plugin "terraform" { enabled = true, preset = "recommended" }`
    - `plugin "azurerm" { enabled = true, version = "0.32.0", source = "github.com/terraform-linters/tflint-ruleset-azurerm" }`
    - Forbidden: `signature = "none"`, global rule disables, `rule` blocks with `enabled = false`, `exclude` lists and `plugin_dir`.
  - [x] **Failure threshold**: TFLint's default threshold applies, so warnings and errors both fail. Forbidden anywhere: `--minimum-failure-severity`, `--force`, `--fix`, `continue-on-error`, `|| true`, exit-code remapping and `tflint-ignore` annotations. Any non-zero TFLint exit fails the script and the job (unlike Phase 5, where `terraform plan` exit 2 is a valid result).
  - [x] **Shared execution**: `scripts/run_tflint.sh` is the only command, used both locally and in CI. It:
    1. resolves the config to an absolute path;
    2. fails if `TFLINT_PLUGIN_DIR` is unset or inside the repository;
    3. runs `tflint --init --config <abs>`, the only command that receives `GITHUB_TOKEN`, then unsets `GITHUB_TOKEN` so the version check and the lint run never see it;
    4. checks that `tflint --version --config <abs>` reports `ruleset.azurerm (0.32.0)`, otherwise it fails. If the real output format differs from this check, stop and report it; do not substitute another check;
    5. runs `tflint --recursive --config <abs>` from `terraform/` only. The scan never depends on `.artifacts/` being hidden.
  - [x] **Plugin directory**: locally, `TFLINT_PLUGIN_DIR` points at the session scratchpad (never the home directory and never inside the repository); in CI it points at `${{ runner.temp }}`.
  - [x] **Clean baseline**: zero TFLint findings at the default threshold over `terraform/`, using TFLint v0.64.0 and ruleset v0.32.0. This includes zero applicable AzureRM findings, reached only through the baseline fixes listed above. If the first real baseline run with the downloaded plugin reports any finding not listed in the Design Review, stop and return to design review; suppression is not allowed.
  - [x] **Workflow `security-scan.yml`**:
    - triggers: `push` and `pull_request` to `main`, plus `workflow_dispatch`
    - permissions exactly `contents: read`
    - checkout with `persist-credentials: false`
    - `terraform-linters/setup-tflint@v6` with `tflint_version: v0.64.0`, `cache` and `tflint_wrapper` left at their default `false`
    - token handling follows the documented `setup-tflint` behaviour (decided 2026-10-03):
      - the action's `github_token` input stays at its documented default (the workflow token, used only to fetch TFLint release data; the action does not export it to later steps). No explicit override.
      - the `run_tflint.sh` step passes `GITHUB_TOKEN: ${{ github.token }}` for `tflint --init` only (the documented plugin-download pattern); the script removes it before running TFLint (see Shared execution).
      - no other step receives the token.
    - concurrency group `security-scan-${{ github.ref }}`, cancelling in progress only for pull requests
    - Not allowed: `azure/login`, `id-token`/OIDC, `ARM_*`/`TF_VAR_*`/Azure secrets, cache, SARIF/`security-events`, artifacts, path filters.
  - [x] **No drift semantics**: no `drift_detected` / `drift_status` outputs, no drift issues or labels, and no `drift-report-*` artifacts. The step summary or log states "static lint, not drift detection".
  - [x] **Phase 5 protected**:
    - `drift-detection.yml` and `terraform-auth-test.yml` are byte-identical to before. This is verified once during implementation with `git diff --exit-code ca1caad -- .github/workflows/drift-detection.yml .github/workflows/terraform-auth-test.yml` and recorded in the Completion Notes. No permanent hash or fingerprint of those workflows is committed (decided 2026-10-03);
    - both `.terraform.lock.hcl` files are unchanged;
    - `terraform init -backend=false` and `terraform validate` pass for `terraform/bootstrap` and `terraform/environments/dev` (with `-lockfile=readonly` on dev, as the drift workflow uses it);
    - `./scripts/validate.sh` passes.
  - [x] **`prevent_destroy` documented**: README states that the bootstrap Storage Account and Blob Container hold Terraform remote state and are intentionally protected from accidental destruction. Intentionally destroying them requires an explicit, reviewed change that removes `prevent_destroy` before Terraform can destroy them. No `terraform apply` is needed or performed for this change: the lifecycle argument is evaluated at plan time and is not stored in state.
  - [x] **README**: documents the local command (`TFLINT_PLUGIN_DIR=<scratch> ./scripts/run_tflint.sh`), the locked versions and the upgrade procedure (one reviewed change updates `.tflint.hcl`, the workflow and README together), the AzureRM v5 limitation below, and that TFLint needs no Azure access.
- **Validation**:
  - [x] Static pytest (`tests/test_tflint_integration.py`, no TFLint binary needed). It checks:
    - the exact version pins match across `.tflint.hcl`, the workflow and README;
    - an unpinned TFLint `required_version` (not `= X.Y.Z`) or an azurerm plugin without an exact `version` is rejected;
    - all forbidden flags and attributes are absent;
    - triggers and `permissions: contents: read` only;
    - no `id-token`, `azure/login`, `ARM_*`, `TF_VAR_*` or Azure secrets;
    - no drift outputs;
    - `security-scan.yml` contains the TFLint design above;
    - `drift-detection.yml` and `terraform-auth-test.yml` contain no TFLint or `security-scan` integration (no fingerprints of their contents);
    - the script scans `terraform/` with an absolute config path.
  - [x] Local run: `TFLINT_PLUGIN_DIR=<scratchpad> ./scripts/run_tflint.sh` → exit 0 with zero findings, and the azurerm 0.32.0 check passes. User-approved 2026-10-03: downloading the pinned `tflint-ruleset-azurerm` v0.32.0 release from GitHub for local validation and mutation testing. The approval covers that download only; no GitHub repository changes.
  - [x] Mutation checks on a **scratchpad copy** of `terraform/` and `.tflint.hcl` (never on tracked files). Each must fail with a non-zero exit:
    - (a) a `terraform_deprecated_interpolation` violation in each of the 4 directories (`bootstrap`, `environments/dev`, `modules/network`, `modules/resource-group`), proving the config applies everywhere;
    - (b) an invalid AzureRM value (e.g. `account_kind = "InvalidKind"` on the bootstrap storage account), proving the azurerm ruleset is active;
    - (c) an HCL syntax error;
    - (d) a missing config, a misnamed config, or a relative `--config` under `--recursive`;
    - (e) the azurerm plugin without `version`, and a `required_version` that does not match the binary;
    - (f) removing either `prevent_destroy`;
    - (g) a no-op control mutation that must still pass.
  - [x] Offline Terraform checks (validate/init/lock-file diff, see the Phase 5 criterion). No Azure calls.
  - [x] CI proof, approval-gated: one green `push` run on `main`, and one pull request run with a deliberate lint finding that fails the `tflint` job, with no Azure step executed in `security-scan.yml`. *(Wording corrected 2026-10-03, Phase 9 re-evaluation.)* The approval must acknowledge that these events also trigger the existing, unmodified `terraform-auth-test.yml`:
    - a push to `main` runs its Azure OIDC login and its read-only `terraform plan` against the dev state;
    - on a pull request, its Azure login fails, because no `pull_request` federated credential exists (Task 2.6). This is existing behaviour, not a Task 9.1 result.
- **Design Review (2026-10-03)**:
  - **Findings that drove this revision**:
    - The original acceptance criteria could not pass. An offline TFLint v0.64.0 baseline found 5 warnings: `terraform_required_providers` and `terraform_required_version` in both modules, and `terraform_unused_declarations` for dev `var.location`. Default exit is 2; `--minimum-failure-severity=error` would hide them.
    - The original validation (`tflint --init && tflint` at repo root) passes vacuously, because there are no `.tf` files at the root.
    - Under `--recursive`, a relative `--config` resolves per module directory and fails; an absolute path is required.
    - `terraform-auth-test.yml` is unsuitable: it needs Azure, and the `pull_request` federated credential does not exist (Task 2.6), so PR runs fail at login.
    - `drift-detection.yml` must not carry lint results.
  - **AzureRM ruleset compatibility (researched 2026-10-03)**:
    - v0.32.0 (released 2026-04-25) is the latest signed release. It requires TFLint ≥ 0.46 and uses tflint-plugin-sdk 0.24.0, so it is compatible with TFLint v0.64.0.
    - **Limitation**: v0.32.0 was generated from the AzureRM **4.65.0** schema. It does not contain the later AzureRM v5 schema work: upstream PR #527, merged 2026-09-24, which is unreleased.
    - That v5 work only removes 5 rules for 8 resources that v5 dropped (`azurerm_hpc_cache*`, `azurerm_network_packet_capture`, `azurerm_postgresql_*`). This repository uses none of them; its resources are resource group, virtual network, subnet, NSG, subnet–NSG association, storage account and storage container. So the repository's resources are unaffected.
    - Task 9.1 is not blocked waiting for a v5 release. Moving to a release with explicit AzureRM v5 support is a separate, reviewed version bump.
  - **Expected ruleset finding**: v0.32.0 enables `azurerm_resources_missing_prevent_destroy` by default. Its default list includes `azurerm_storage_account` and `azurerm_storage_container`, so the bootstrap state resources are fixed with `prevent_destroy` (user decision), not by suppressing the rule.
- **Out of Scope**:
  - tfsec, TruffleHog, Super-Linter and any other lint/security tool
  - SARIF/code-scanning upload and caching
  - changed-file scanning
  - pinning actions by commit SHA (Phase 12)
  - any change to the drift-detection or auth workflows
  - any Azure access or `terraform apply`
- **Implementation Notes**:
  - Static analysis for Terraform best practices.
  - TFLint needs no `terraform init`, backend or provider download, because all modules are local.
  - Output contains only values from committed public `.tf` / `dev.tfvars` files; do not enable `TFLINT_LOG` debug output.
- **Completion Notes** *(2026-10-03)*:
  - **Implemented**:
    - new `.tflint.hcl`, `scripts/run_tflint.sh` (executable), `.github/workflows/security-scan.yml` (job `tflint`), `tests/test_tflint_integration.py`
    - baseline fixes: new `terraform/modules/{network,resource-group}/versions.tf`; `location` removed from dev `variables.tf` and `dev.tfvars`; `prevent_destroy` on `azurerm_storage_account.tfstate` and `azurerm_storage_container.tfstate`
    - README: TFLint section, `prevent_destroy` note, repository structure
  - **First real baseline**: the ruleset v0.32.0 was downloaded (the approved download only). Artifact attestation verified and checksum matched (debug log). The run reported exactly the 7 findings recorded in the Design Review (exit 2): the 5 bundled-rule warnings plus `azurerm_resources_missing_prevent_destroy` on `bootstrap/main.tf:17` and `:46`. After the baseline fixes: 0 findings, exit 0. `tflint --version --config` prints `+ ruleset.azurerm (0.32.0)`, as the planned check expects.
  - **Mutation matrix** (scratchpad copies only): (a) `terraform_deprecated_interpolation` caught in all 4 directories (exit 2); (b) `account_kind = "InvalidKind"` → `azurerm_storage_account_invalid_account_kind` (exit 2); (c) syntax error, (d) missing / misnamed / relative config, (e) unpinned plugin and `required_version` mismatch → exit 1 each; (f) each `prevent_destroy` removed → exit 2; (g) no-op control → exit 0.
  - **Tests**:
    - `tests/test_tflint_integration.py`: 17 tests pass. A scratch-copy sensitivity check caught all 17 regression mutations (workflow, script, config, Terraform, README); the control passed.
    - Full suite (scratchpad venv, Python 3.13, `.[dev]`): 1115 passed, 679 skipped (optional `ai`/`azure` extras absent); `drift_engine` coverage 96.05% (gate 85%).
  - **Phase 5 protected**:
    - `git diff --exit-code ca1caad` on `drift-detection.yml` and `terraform-auth-test.yml`: clean;
    - both lock files unchanged;
    - `init -backend=false` + `validate` pass for bootstrap and for dev (`-lockfile=readonly`);
    - `./scripts/validate.sh` passes (`fmt -check` included);
    - every `dev.tfvars` key is a declared variable.
    No Azure call, no `terraform apply`.
  - **Choices within the locked design**: `TFLINT_PLUGIN_DIR` must be an existing directory (the script never creates it); TFLint output uses `--format compact`; job `timeout-minutes: 10`; workflow name "Phase 9 - Security Scan".
  - **CI proof** (user-approved 2026-10-03; push of `ca1caad`, `64f6693` and `b34803f` to `main`):
    - `main` push, commit `b34803f`:
      - `security-scan.yml` run `37131296792`: success. Job steps were only Checkout, Setup TFLint and Run TFLint; no Azure/OIDC step. TFLint 0.64.0 with `+ ruleset.azurerm (0.32.0)` and `+ ruleset.terraform (0.15.0-bundled)`; 0 findings; 0 artifacts.
      - `terraform-auth-test.yml` run `37131296809`: success. The real read-only dev plan reported `No changes. Your infrastructure matches the configuration.`, so the baseline fixes do not change dev.
    - Draft PR #2 (branch `ci-proof/task-9.1-tflint-failure`, head `3b3d1cb` = `b34803f` + one unused variable `ci_proof_unused` in `terraform/modules/network/variables.tf`):
      - `security-scan.yml` run `37131473701`: failed as intended. `modules/network/variables.tf:89:1: Warning - variable "ci_proof_unused" is declared but not used (terraform_unused_declarations)`, TFLint exit 2. No Azure/OIDC step, no token value in the log, 0 artifacts.
      - `terraform-auth-test.yml` run `37131473689`: failed at Azure OIDC login (`AADSTS700213`, no federated identity record for the `pull_request` subject). Existing behaviour (Task 2.6).
    - Cleanup: PR #2 closed unmerged (2026-10-03T14:58:09Z, `merged=false`); the remote and local branches were deleted; `main` = `origin/main` = `b34803f`, and `ci_proof_unused` is absent from `main`.
    - Evidence summary kept in `.artifacts/task-9.1-ci-proof/evidence.md` (gitignored).
    - Observation: the `pull_request` OIDC subject uses GitHub's ID-qualified format (`repo:<owner>@<id>/<repo>@<id>:pull_request`). Relevant only if a `pull_request` federated credential is added (Task 12.3).

#### Task 9.2 — Infrastructure Security Scanner (Trivy config)
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-03
- **Completed**: 2026-10-03
- **Objective**: Integrate static Terraform security scanning with Trivy (`trivy config`, misconfiguration scanning only) to check for Azure security misconfigurations. It runs in its own job in `security-scan.yml`, credential-free. A finding is a security-scan failure, never a drift result. *(Retitled and reworded 2026-10-03; originally "tfsec Infrastructure Security Scanner". Task ID unchanged. tfsec and Checkov were rejected; see the Design Review.)*
- **Dependencies**: Task 9.1
- **Locked versions and flags** *(exact; one reviewed change bumps them everywhere)*:
  - Trivy **v0.75.0**, installed as the pinned release binary (`trivy_0.75.0_Linux-64bit.tar.gz` in CI). Its SHA-256 is committed in the repository and verified before use.
    - The hash is established once during implementation from the official checksums file, with that file's cosign signature verified (D4 approves the downloads).
    - Only this Linux CI hash is committed. A local macOS Trivy v0.75.0 is verified once against the official checksums during validation (recorded in the Completion Notes). No macOS hash is committed unless the repository itself comes to install or manage the macOS binary. *(Decided 2026-10-03.)*
    - No `aquasecurity/trivy-action`, no `setup-trivy`, no Docker image tag.
  - Embedded checks only: `--skip-check-update`, so the checks bundle is the one built into v0.75.0 and is never fetched from `mirror.gcr.io/aquasec/trivy-checks`. No embedded checks-bundle version is recorded or inferred: Trivy v0.75.0 does not report one (`trivy --version` prints only `Version: 0.75.0`). The embedded bundle is fixed by the binary, which is pinned by its version (`0.75.0`) and its committed SHA-256. *(Decision C, 2026-10-03.)*
  - Always passed: `--disable-telemetry`, `--skip-version-check`, `--misconfig-scanners terraform`, `--cache-dir <fresh dir>`, and JSON output for the gate.
  - **Fresh cache per scan** *(Decision D, 2026-10-03)*: every scan uses a newly created, empty cache directory outside the repository. With `--skip-check-update`, Trivy would otherwise use a checks bundle already present in its cache; a fresh cache guarantees the embedded checks of the verified binary.
    - Trivy's expected log line `ERROR … Falling back to embedded checks` is not a failure when the command exits 0 and the JSON output is valid.
  - **JSON parsing with `jq`** (preinstalled on `ubuntu-latest`). The script checks that `jq` is available before scanning and fails if it is missing. *(Decided 2026-10-03.)*
  - Forbidden: `.trivyignore` / `.trivyignore.yaml`; `--ignorefile` pointing at any real file; `--ignore-policy`; `--skip-dirs` / `--skip-files` on Terraform paths; `--exit-code 0` on the gate; `--severity` filtering on the gate other than `HIGH,CRITICAL`; secret or vulnerability scanners.
- **Files/Areas**:
  - `.github/workflows/security-scan.yml`: new job `trivy-config`, independent of `tflint` (no `needs`); the `tflint` job is unchanged
  - new `scripts/run_trivy_config.sh`: the single local/CI command
  - new `security/trivy-risk-acceptance.json`: the committed risk-acceptance record (see Risk acceptance)
  - new `tests/test_trivy_config.py`
  - `tests/test_tflint_integration.py`: only its whole-workflow assertions change, to job-scoped ones. Today it asserts the job list is exactly `["tflint"]` and bans strings such as `cache` anywhere in the workflow, which a second job legitimately breaks. All `tflint` job assertions keep their meaning.
  - `README.md`
  - **Unchanged**:
    - `drift-detection.yml` and `terraform-auth-test.yml`
    - all Terraform files, including `terraform/bootstrap/main.tf` (no code change for AZU-0012)
    - lock files, `.tflint.hcl`, `scripts/run_tflint.sh`
    - `src/`, `schemas/`, `pyproject.toml` / `requirements.txt`
- **Scan scope**: one invocation per Terraform root:
  - `terraform/environments/dev` with `--tf-vars terraform/environments/dev/dev.tfvars`, which evaluates the `modules/resource-group` and `modules/network` calls with the real values;
  - `terraform/bootstrap`.
  
  Scans run **from the repository root** with these repo-relative paths, so Trivy's JSON `ArtifactName` is exactly `terraform/environments/dev` or `terraform/bootstrap`. Nothing outside `terraform/` is scanned. Module coverage must be proven by mutations (see Validation): passing a scan of a root is not evidence that its modules were evaluated.
- **Failure policy (D2)**:
  - HIGH and CRITICAL findings fail the job.
  - MEDIUM and LOW are printed on every run (full report) but do not block. This severity threshold is an explicit Phase 9 design decision; it differs from TFLint, where warnings fail.
  - A scanner execution error, a download or hash-verification failure, a wrong Trivy version, or unreadable/unexpected JSON fails the job.
  - No `continue-on-error`, `|| true` or forced success.
- **Risk acceptance (D3, script-enforced; not a Trivy ignore)**:
  - **Record** (`security/trivy-risk-acceptance.json`, committed) for exactly one finding:
    - rule `AZU-0012` ("storage account network rules default action should be Deny", CRITICAL), matched exactly against the Trivy JSON field `ID`. `AVD-AZU-0012` appears only as a documentation alias/reference; there is no `AVD-` prefix mapping, and Trivy v0.75.0's JSON has no `AVDID` field *(Decision A, 2026-10-03)*;
    - resource `azurerm_storage_account.tfstate`;
    - source `terraform/bootstrap/main.tf`;
    - justification;
    - scope;
    - expiry/review date **`2027-03-31`** *(decided 2026-10-03)*. After this date the gate fails until the acceptance is reviewed and renewed, or the risk is fixed, through a reviewed plan change.
  - **Justification**: the Terraform remote-state account is reached over its public endpoint, authenticated with Entra ID and without account keys in CI (`ARM_USE_AZUREAD`), from GitHub-hosted runners with dynamic IPs. A default-Deny network rule would cut off drift detection and the auth workflow. Restricting network access (allowlist, private endpoint or self-hosted runners) is an architecture change outside Phase 9 that needs an approved Azure apply.
  - **Scope**: this rule on this resource in this file only. It never covers another rule, resource, file or severity.
  - **Enforcement by `scripts/run_trivy_config.sh`**: it parses Trivy's JSON and:
    - fails on any HIGH/CRITICAL finding that does not exactly match the record on all three of: `ID` = `AZU-0012`; `CauseMetadata.Resource` = `azurerm_storage_account.tfstate`; and the repo-relative path derived as `ArtifactName + "/" + Target` = `terraform/bootstrap/main.tf`. This derivation is the locked file-matching rule *(Decision B, 2026-10-03)*;
    - fails if no current finding matches the record (stale acceptance);
    - fails if the record matches more than one finding;
    - fails if today is after the expiry date;
    - fails if the record is missing, malformed or has more than one entry;
    - fails if `jq` is missing.
  - **Never hidden**: the accepted finding is printed on every run, labelled "ACCEPTED RISK", with its justification and expiry.
  - **No suppression**: no `.trivyignore` and no Trivy suppression flag. Trivy still reports the finding; only the script's gate classifies it.
- **Acceptance Criteria**:
  - [x] **Pinned install**: CI downloads the exact v0.75.0 binary and verifies the committed SHA-256; a mismatch fails before any scan. The script fails unless `trivy --version` is exactly 0.75.0 (locally too), and prints the binary version. In CI it also prints the verified SHA-256. No checks-bundle version is reported.
  - [x] **Invocation**: `trivy config` per root as in Scan scope, with every locked flag; no forbidden flag, file or scanner.
  - [x] **Gate**: HIGH/CRITICAL findings fail except the single exact AZU-0012 match. All stale, multiple-match, expired and malformed-record cases fail. MEDIUM/LOW are reported and non-blocking. The exit code comes only from these rules, applied to Trivy's own findings.
  - [x] **Baseline**: the first real run (v0.75.0, embedded checks) must match the expected baseline in the Design Review. Expected: exactly one HIGH/CRITICAL finding (AZU-0012 on `azurerm_storage_account.tfstate`) and MEDIUM/LOW findings only among AZU-0057/0058/0060/0061 on the same account. Any other HIGH/CRITICAL finding, or a different AZU-0012 match: stop and return to design review (no new acceptance without approval).
  - [x] **Workflow job `trivy-config`**:
    - triggers inherited from `security-scan.yml` (`push`/`pull_request` to `main`, `workflow_dispatch`);
    - permissions exactly `contents: read`;
    - checkout with `persist-credentials: false`;
    - no `GITHUB_TOKEN` (public download);
    - no `needs` on `tflint`;
    - not allowed: `azure/login`, `id-token`, `ARM_*`/`TF_VAR_*`/Azure secrets, cache action, SARIF/`security-events`, artifacts, `continue-on-error`.
  - [x] **No drift semantics**: no `drift_detected` / `drift_status` outputs, no drift issues or labels, no drift artifacts. The log states "static security scan, not drift detection".
  - [x] **Existing workflows protected**: `drift-detection.yml` and `terraform-auth-test.yml` unchanged, verified once with `git diff --exit-code` against the pre-implementation commit. The `tflint` job is unchanged (diff), and `scripts/run_tflint.sh` still passes.
  - [x] **README**: documents:
    - the local command;
    - the pinned version, hash and upgrade procedure (one reviewed change updates the version, the hash, the tests and the README);
    - the failure policy;
    - the AZU-0012 risk acceptance (justification, scope, expiry, how it is enforced and reviewed);
    - that no Azure access is needed.
- **Validation**:
  - [x] Static pytest (`tests/test_trivy_config.py`), checking:
    - version, hash and flag pins;
    - no forbidden flags, files or scanners;
    - job permissions, triggers and absence of Azure/OIDC/drift elements;
    - the acceptance record schema (exactly one entry, rule `AZU-0012`, resource `azurerm_storage_account.tfstate`, file `terraform/bootstrap/main.tf`, expiry `2027-03-31`);
    - the path derivation `ArtifactName + "/" + Target`, and scans run from the repository root;
    - a fresh cache directory per scan;
    - the script's gate logic, on synthetic Trivy JSON: an exact accepted match passes; plus failure cases for an unexpected HIGH, an unexpected CRITICAL, a stale record, a double match, an expired record, a malformed record, and malformed/missing JSON; and MEDIUM/LOW only passing.
    
    `tests/test_tflint_integration.py` still passes with job-scoped assertions.
  - [x] Local real run with the pinned v0.75.0 binary (hash verified) matches the expected baseline, with the accepted finding printed.
  - [x] Mutation checks on **scratchpad copies only**. Each must fail with a non-zero exit except the control:
    - `https_traffic_only_enabled = false` (the AzureRM v4/v5 name) on the bootstrap account;
    - `min_tls_version = "TLS1_0"`;
    - `container_access_type = "blob"`;
    - an inbound NSG rule from `0.0.0.0/0` (e.g. port 22) inside `modules/network`, proving module coverage through dev's tfvars;
    - a HIGH/CRITICAL finding in `modules/resource-group` or on a dev resource, if a check exists for it (otherwise record that none applies);
    - a tampered SHA-256;
    - a wrong local Trivy version;
    - an expired acceptance;
    - a stale acceptance (the finding removed in the scratch copy);
    - a widened acceptance (matching a second resource);
    - `jq` missing from `PATH`;
    - a no-op control, which must pass with the accepted finding printed.
  - [x] CI proof (D6, approval-gated, same pattern as Task 9.1):
    - a green `main` push run whose `trivy-config` log shows the AZU-0012 finding printed as accepted and the job passing;
    - a draft PR with one deliberate unexpected HIGH/CRITICAL finding (planned: an open inbound NSG rule in `modules/network`) whose `trivy-config` job fails on that finding while AZU-0012 is still shown as accepted;
    - no Azure/OIDC step in `security-scan.yml`; the PR closed unmerged and its branch deleted.
    
    The approval must acknowledge that these events also trigger the existing `terraform-auth-test.yml` (an Azure plan on push; the Azure login fails on a PR).
- **Design Review (2026-10-03)**:
  - **Scanner choice (D1: Trivy)**:
    - **tfsec rejected**: deprecated (v1.28.14, 2025-05-02, "joining the Trivy family"). False pass shown: `https_traffic_only_enabled = false` reported `azure-storage-enforce-https` as passed. `tfsec terraform/` scanned only bootstrap; dev needs `--tfvars-file`.
    - **Checkov rejected**: `CKV_AZURE_3` (3.3.21) reads only `enable_https_traffic_only`, with `missing_block_result=PASSED`, so it has the same false pass. Severities come from Prisma Cloud (`--skip-download` "will omit … severities"), so the High/Critical gate would need a third-party account and key.
    - **Trivy chosen**: actively maintained (v0.75.0, 2026-10-01). Its v0.75.0 storage adapter reads `enable_https_traffic_only` *or* `https_traffic_only_enabled` (the v4+ name). Built-in severities.
      - Known v5 gap: the adapter reads only `public_network_access_enabled` (AzureRM v5 uses `public_network_access`). No current storage check uses that value, so there is no false result today. Re-check on version bumps.
  - **Supply chain**: in March 2026 Trivy binary v0.69.4 (and Docker images v0.69.5/0.69.6), `trivy-action` <0.35.0 (76 of 77 tags force-pushed) and `setup-trivy` <0.2.6 were replaced with credential-stealing code for hours (advisory GHSA-69fq-xp46-6x23). The vendor recommends pinning actions by full commit SHA and verifying signatures; Homebrew built from source and was unaffected.
    - Hence: no Trivy action and no mutable image tag; a pinned binary verified against a committed SHA-256; a credential-free job (`contents: read`, no token).
  - **Checks bundle**: by default Trivy pulls its checks from `mirror.gcr.io/aquasec/trivy-checks:1` every 24 h, which would change findings without a version bump. `--skip-check-update` uses the bundle embedded in the release. Telemetry is on by default, hence `--disable-telemetry` and `--skip-version-check`.
  - **Expected baseline** (from the check definitions; to be confirmed by the first real run): on `azurerm_storage_account.tfstate`:
    - AZU-0012 CRITICAL (no `network_rules` block);
    - AZU-0057 MEDIUM (logging);
    - AZU-0060 MEDIUM (customer-managed key);
    - AZU-0061 MEDIUM (infrastructure encryption; enabling it forces replacement of the state account);
    - AZU-0058 LOW (geo-redundant replication).
    
    Expected to pass: HTTPS (AZU-0008), TLS, container public access (AZU-0007) and the network checks on dev.
  - **Overlap**: TFLint checks value validity and lint; Trivy checks security policy. Trivy's secret scanning stays off (TruffleHog, Task 9.3). Task 9.4 must exclude Super-Linter's bundled Trivy and Checkov.
- **Out of Scope**:
  - fixing AZU-0012 or the MEDIUM/LOW findings (they need Azure architecture or apply decisions, Phase 11/12)
  - SARIF/code scanning, caching, secret and vulnerability scanning
  - pinning other actions by SHA (Phase 12)
  - any Azure access or change to the drift-detection or auth workflows
- **Implementation Notes**:
  - Runs on code changes (push/PR) in `security-scan.yml`. It is not part of the deterministic drift-detection path and never gates or runs inside the scheduled drift-detection workflow.
  - **Stop rule (preserved)**: if Trivy v0.75.0's JSON does not expose sufficient stable fields (rule ID, resource address, source file) to enforce the exact-match acceptance safely, stop and report. Do not change the design or improvise the match rule.
  - **Resolved 2026-10-03 (decisions A–D)**: the first real v0.75.0 JSON exposes `ID`, `Severity`, `Status`, `CauseMetadata.Resource`, `ArtifactName` and `Target`. Matching uses `ID` (A) and `ArtifactName + "/" + Target` (B). No checks-bundle version is reported (C), and the fresh cache is required (D).
    - The first real baseline matched the expected one: dev 60 passed / 0 failed; bootstrap 46 passed plus 5 failures, all on `azurerm_storage_account.tfstate` (AZU-0012 CRITICAL; AZU-0057, AZU-0060, AZU-0061 MEDIUM; AZU-0058 LOW).
    - Verified 2026-10-03: the official checksums file's cosign signature (cosign v3.1.3, identity `https://github.com/aquasecurity/trivy/.github/workflows/…`), and the Linux SHA-256 `c6e65abddb348e25f10549df887045629cf28cc72453cd1c63acb717316b3f3f`.
- **Completion Notes** *(2026-10-03)*:
  - **Implemented**:
    - new `scripts/run_trivy_config.sh`, `security/trivy-risk-acceptance.json` (`AZU-0012`, `azurerm_storage_account.tfstate`, `terraform/bootstrap/main.tf`, expires `2027-03-31`) and `tests/test_trivy_config.py` (22 tests);
    - new `trivy-config` job in `security-scan.yml`: checkout, then install of the pinned Linux binary with `sha256sum -c` before unpacking, then the script;
    - `tests/test_tflint_integration.py` workflow assertions made job-scoped;
    - README "Terraform security scan" section and repository-structure entries.
    
    Unchanged: the `tflint` job and workflow-level keys (YAML-identical), both protected workflows (`git diff --exit-code 402eccf` clean), all Terraform files, lock files, `.tflint.hcl`, `scripts/run_tflint.sh`.
  - **Supply chain**: cosign v3.1.3 (its own SHA-256 matched the official checksums and the GitHub asset digest) verified the cosign bundle of `trivy_0.75.0_checksums.txt` ("Verified OK", identity `https://github.com/aquasecurity/trivy/.github/workflows/…`, GitHub OIDC issuer). The Linux (`c6e65abd…3f3f`, committed) and macOS ARM64 (`4a77108c…4568`, local use only, not committed) archives match the signed checksums.
  - **First real baseline**: matches the expected baseline. Dev: 60 checks passed, 0 failed. Bootstrap: 46 passed and 5 failures, all on `azurerm_storage_account.tfstate`: AZU-0012 CRITICAL (printed as `ACCEPTED RISK`); AZU-0057, AZU-0060, AZU-0061 MEDIUM and AZU-0058 LOW (`REPORTED (non-blocking)`). Script exit 0.
  - **Real-Trivy mutation matrix** (scratchpad copies only; all as expected):
    - `https_traffic_only_enabled = false` → AZU-0008 + AZU-0059 HIGH;
    - `TLS1_0` → AZU-0011 CRITICAL + AZU-0059 HIGH;
    - `container_access_type = "blob"` → AZU-0007 HIGH;
    - open inbound SSH rule in `modules/network` → AZU-0047 + AZU-0050 CRITICAL on `module.network["main"]` (module coverage proven through dev's tfvars);
    - expired record → fails before scanning;
    - stale (a `network_rules` Deny block added) → stale + AZU-0010 HIGH;
    - widened record (wildcard resource, or a second entry) → fails;
    - no-op control → passes with the accepted finding printed.
    
    No HIGH/CRITICAL check applies to `modules/resource-group` or to dev-only attributes: a subnet outbound-access probe produced no finding.
  - **Install step** (run with a stubbed `curl` serving the verified archive): the correct hash passes; a tampered hash or a tampered archive fails at `sha256sum -c`, before unpacking or `GITHUB_PATH`.
  - **Gate tests** (fake `trivy` emitting v0.75.0-shaped JSON in a temporary repository copy):
    - baseline pass with every finding printed;
    - exact argv per root, run from the repository root, a fresh empty cache per scan outside the repository, `TRIVY_*` environment cleared;
    - unexpected HIGH/CRITICAL, near misses (other rule, resource, file or root), stale, double match, expired, 17 malformed-record variants, unsafe/invalid JSON, Trivy failure, wrong version, missing `trivy`, missing `jq` (checked before any external command);
    - `.trivyignore` / `.trivyignore.yaml` / `trivy.yaml` / inline `trivy:ignore`, and a work directory inside the repository.
    
    Sensitivity: the suites caught 19/19 regression mutations (workflow, script, record, README) on a scratch copy; the control passed.
  - **Regression**: full suite 1137 passed, 679 skipped (optional `ai`/`azure` extras absent); coverage 96.05% (gate 85%); `scripts/run_tflint.sh` 0 findings; `./scripts/validate.sh` passes. No Azure call.
  - **Implementation details within the locked design**:
    - `--ignorefile` is not passed at all: v0.75.0 exits with a fatal error for a non-existent ignore file, and pointing it at a real file is forbidden. Instead, the script fails if `.trivyignore`, `.trivyignore.yaml`, `trivy.yaml` or an inline `trivy:ignore` exists, and it clears `TRIVY_*` variables.
    - Module findings carry the module call address as their resource (e.g. `module.network["main"]`) and a `Target` relative to the root (`../../modules/network/main.tf`), so they can never match the bootstrap acceptance.
    - The work directory is under `RUNNER_TEMP` (or `TMPDIR`), checked to be outside the repository and removed on exit.
    - Job `timeout-minutes: 10`.
  - **D6 CI proof** (user-approved 2026-10-03; checkpoint commits `2754172` design and `49eea22` implementation pushed together with `402eccf`, `b34803f..49eea22`):
    - `main` push, commit `49eea22`:
      - `security-scan.yml` run `37133573650`: success, 0 artifacts.
        - Job `trivy-config` (`111233391283`): the install step verified SHA-256 `c6e65abd…3f3f`; Trivy 0.75.0; AZU-0012 printed as `ACCEPTED RISK` with its justification, scope and expiry `2027-03-31`; AZU-0057/0058/0060/0061 `REPORTED (non-blocking)`; "passed: no unaccepted HIGH/CRITICAL findings".
        - Job `tflint` (`111233391437`): success.
        - Steps were only Checkout, Install Trivy and Run Trivy config; no Azure/OIDC step.
      - `terraform-auth-test.yml` run `37133573651`: success, dev plan `No changes`.
    - Draft PR #3 (branch `ci-proof/task-9.2-trivy-failure`, head `f7b195d` = `49eea22` + one `azurerm_network_security_rule.ci_proof`, inbound TCP 22 from `0.0.0.0/0`, in `terraform/modules/network/main.tf`):
      - `security-scan.yml` run `37133731365`:
        - Job `trivy-config` (`111233858578`) failed as intended: AZU-0012 still `ACCEPTED RISK`; `BLOCKING CRITICAL AZU-0047` and `BLOCKING CRITICAL AZU-0050` on `module.network["main"]` (`terraform/environments/dev/../../modules/network/main.tf`); "2 HIGH/CRITICAL finding(s) not covered by the risk acceptance", exit 1.
        - Job `tflint` (`111233858732`): success (the probe is lint-clean).
        - No other security-scan failure; 0 artifacts.
      - `terraform-auth-test.yml` run `37133731442`: failed at Azure OIDC login (`AADSTS700213`; existing behaviour, Task 2.6).
    - Cleanup: PR #3 closed unmerged (2026-10-03T15:35:41Z, `merged=false`); the remote and local branches were deleted; `main` = `origin/main` = `49eea22`, and the probe is absent from `main`.

#### Task 9.3 — TruffleHog Secret Scanning
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Objective**: Configure TruffleHog in GitHub Actions to scan the repository's Git history for exposed credentials or keys, failing on every detected result. It **detects** committed secrets; it does not prevent a commit. *(Reworded 2026-10-04; previously "Credentials leakage prevention".)*
- **Dependencies**: Task 9.2
- **Locked version and flags (D1, D2)**:
  - TruffleHog **v3.97.9**, installed as the pinned Linux amd64 release binary `trufflehog_3.97.9_linux_amd64.tar.gz`. SHA-256 **`40377e6572495412fb9ba0bc21c9401f73b72f1d2afd11b9931bc4a5ed622866`** is committed and checked with `sha256sum -c` before unpacking. No TruffleHog GitHub Action, no Docker image, no install script.
  - **`--no-update` is always passed.** TruffleHog updates itself at runtime by default, which would defeat the pin.
  - **`--no-verification`** (D2): no candidate secret is sent to any provider API, results don't depend on the network, and every result is blocking. Verified-only behaviour is not allowed.
  - Invocation: `trufflehog git file://<repository root> --no-update --no-verification --json --fail`, run from the repository root.
  - Forbidden:
    - TruffleHog's inline ignore annotation (the comment `trufflehog` + `:ignore`, written split here so this plan never contains it), anywhere in the files or the history; `--exclude-paths`, `--exclude-globs`, `--exclude-detectors`, `--include-paths`/`--include-detectors`;
    - `--results` narrowing, `--only-verified`, `--filter-unverified`;
    - `--since-commit`, `--max-depth`, `--branch` (the scan is always full history);
    - `--github-actions` or plain output in the log, and `--sarif`;
    - any verifier flags.
- **Files/Areas**:
  - `.github/workflows/security-scan.yml`: new job `trufflehog`, independent of `tflint` and `trivy-config`; both of those stay unchanged.
  - new `scripts/run_trufflehog.sh`: the single local/CI command.
  - new `tests/test_trufflehog.py`.
  - `tests/test_tflint_integration.py` / `tests/test_trivy_config.py`: job-scoped adjustments only if a whole-workflow assertion is legitimately affected. The new job must not use `GITHUB_TOKEN`, so the existing "exactly one `GITHUB_TOKEN`" check stays valid.
  - `README.md`.
  - An acceptance-record file is **not** needed (D3; see baseline).
  - **Unchanged**: `drift-detection.yml`, `terraform-auth-test.yml`, Terraform, `src/`, `.tflint.hcl`, `scripts/run_tflint.sh`, `scripts/run_trivy_config.sh`, `security/trivy-risk-acceptance.json`.
- **Scan scope**: the job checks out with `fetch-depth: 0` and `persist-credentials: false`. The `git` source clones that checkout into a temporary directory and runs `git log --patch --full-history --all --diff-filter=AM` (v3.97.9 `gitparse`).
  - **Covered:** every commit reachable from the clone's refs. On a `main` push that is all of `main`'s history; on a PR it is the merge commit and the PR's commits. Additions and modifications of every file type are scanned. A secret later deleted is still found in the commit that added it (proven locally, see Validation). Tags would be included if any existed; there are none today.
  - **Not covered (documented limitations):**
    - merge-commit combined diffs (git's default; the repository has 0 merges);
    - GitHub `refs/pull/*` refs, which `main` runs don't fetch;
    - untracked or ignored files (the `filesystem` source is not used).

    The working tree in CI equals the checked-out commit.
- **Failure policy**: `--fail` makes TruffleHog exit **183** when results are found, **1** on a scanner error, **0** when clean. The script passes the exit code through unchanged (no remapping) and states which case occurred. Any of the following also fails the job:
  - exit 0 with results present in the JSON;
  - a missing binary, wrong version, missing `jq`, or unparseable JSON;
  - a download or hash-verification failure.

  A detected secret (183) is reported as a finding, never as a tool failure.
- **Secret exposure**: plain output and the JSON fields `Raw`/`RawV2` contain the raw secret (v3.97.9 `pkg/output`). So stdout JSON is written to a file outside the repository (`RUNNER_TEMP`) that is never printed, uploaded, cached or turned into SARIF.
  - The script prints only detector name, verification status, file path, line and commit SHA. It never prints `Raw`, `RawV2`, `Redacted`, `ExtraData`, `StructuredData` or author email.
  - Log level stays at the default. In the local probe the planted value appeared 0 times in stderr.
- **False positives (D3)**: only if a baseline needs it, via an exact, expiring, script-enforced acceptance record (detector, commit, file, line; never the value), the same mechanism as Task 9.2's AZU-0012. The 2026-10-04 baseline found **no results**, so the mechanism is **not** part of Task 9.3. Adding one later needs a plan change.
- **Real historical secrets (D4)**: rotate the secret first (user action). History rewriting is outside Task 9.3, needs explicit approval, and is never automatic.
- **Acceptance Criteria**:
  - [x] **Pinned install**:
    - CI downloads the exact v3.97.9 Linux amd64 archive and verifies the committed SHA-256 before unpacking; a mismatch fails before any scan;
    - the script fails unless `trufflehog --version` reports exactly 3.97.9 (locally too);
    - `--no-update` is always passed.
  - [x] **Invocation and scope**: the locked command over the full history from the repository root after a `fetch-depth: 0` checkout; no forbidden flag or mechanism.
  - [x] **Failure policy**: exit 183 (finding) and exit 1 (error) both fail the job, and the log says which; exit 0 with results present fails; no remapping, `continue-on-error` or `|| true`.
  - [x] **No secret exposure**: no output, log, step summary or artifact contains a secret value; only the safe metadata fields are printed.
  - [x] **Clean baseline**: the real scan of the repository history reports 0 results (matching the 2026-10-04 baseline). Any new result means stop and decide per D3/D4; never suppress.
  - [x] **Workflow job `trufflehog`**:
    - triggers inherited (`push`/`pull_request` to `main`, `workflow_dispatch`);
    - permissions exactly `contents: read`, inherited;
    - no `GITHUB_TOKEN`;
    - checkout with `fetch-depth: 0` and `persist-credentials: false`;
    - no `needs`;
    - not allowed: `azure/login`, `id-token`, `ARM_*`/`TF_VAR_*`/secrets, cache, SARIF/`security-events`, artifacts.
  - [x] **No drift semantics**: no drift outputs, issues, labels or remediation. The log states "secret scan, not drift detection".
  - [x] **Existing jobs and workflows protected**:
    - `tflint` and `trivy-config` jobs unchanged (YAML-identical);
    - `drift-detection.yml` and `terraform-auth-test.yml` unchanged (`git diff --exit-code` against the pre-implementation commit);
    - the existing test suites still pass.
  - [x] **README**: documents the local command, pinned version and hash, upgrade procedure, failure policy, scope and limitations, the no-output-of-secrets rule, the D3/D4 policy, and that no Azure access is needed.
- **Validation**:
  - [x] Static pytest (`tests/test_trufflehog.py`): version, hash and flag pins (including `--no-update`, `--no-verification`, `--json`, `--fail`); no forbidden flags or annotations; job permissions, checkout options and absence of Azure/OIDC/drift elements; the script prints no secret fields.
  - [x] Gate tests with a fake `trufflehog` emitting v3.97.9-shaped JSON whose `Raw`/`RawV2` hold a sentinel value. They prove the sentinel never appears in stdout/stderr, and cover:
    - exit 0 clean;
    - exit 183 findings;
    - exit 1 error;
    - exit 0 with results;
    - malformed JSON;
    - missing `jq` or binary;
    - wrong version;
    - the exact argument list, run from the repository root.
  - [x] Install step: correct hash passes; tampered hash and tampered archive fail at `sha256sum -c` (with `curl` stubbed).
  - [x] **Real local scratch-repository proof (D6)** with the verified binary and a randomly generated synthetic secret that is never committed to this repository and never published. It must show:
    - detection with exit 183;
    - detection of a secret deleted in a later commit (historical);
    - the value absent from the script's stdout/stderr;
    - a clean scratch repository exits 0;
    - a no-op control passes.
  - [x] Real local baseline over this repository's history: 0 results.
  - [x] **CI proof** (approval-gated):
    - a green `main` push whose `trufflehog` job scans the full history with 0 results (`tflint` and `trivy-config` stay green);
    - **D7(a), decided 2026-10-04:** a temporary draft PR that **only** changes the committed TruffleHog SHA-256 in `security-scan.yml`. The `trufflehog` job must fail at the integrity check (`sha256sum -c`), before unpacking or scanning. The PR is closed unmerged, its branch deleted, and `main` confirmed unchanged. The approval acknowledges that the PR also triggers `terraform-auth-test.yml` (its Azure login fails on a PR, existing behaviour).
    - **No secret or synthetic credential is ever committed to the repository, a branch or a PR (D6).** PR head refs stay publicly reachable permanently, and GitHub secret scanning or push protection may react.
    - **Limitation:** detection failure is proven by the real local scratch-repository proof (the detection positive control) and by the gate tests, not by a failing public CI run.
    - No CI positive-control repository and no test mode of the production scan are added (D7(b) rejected).
- **Design Review (2026-10-04)**:
  - **Supply chain (D5)**:
    - cosign v3.1.3 (SHA-256 `5cf948c2…2a76`, matching its official checksums and the GitHub asset digest) verified `trufflehog_3.97.9_checksums.txt` with its `.sig`/`.pem`: "Verified OK".
    - Certificate identity `https://github.com/trufflesecurity/trufflehog/.github/workflows/release.yml@refs/tags/v3.97.9`, issuer `https://token.actions.githubusercontent.com`, issued 2026-09-24.
    - The signed checksums list Linux amd64 `40377e65…2866` and darwin arm64 `3d25c178…51f7`; both downloaded archives matched, and both equal the GitHub asset digests.
  - **Why no action or image**: the official action's `version` input defaults to `"latest"` and runs `ghcr.io/trufflesecurity/trufflehog:latest`, so pinning the action by SHA doesn't pin the scanner. The March 2026 compromises of security-tool actions (Trivy, Checkmarx) apply too.
  - **Advisories**: GHSA-3r74-v83p-f4f4 / CVE-2024-43379 (low severity, blind SSRF in some detectors), fixed in v3.81.9. v3.97.9 is not affected.
  - **Baseline (2026-10-04, verified binary, `--no-verification --fail`)**: **0 results**.
    - Local repository (45 commits): 958 chunks, exit 0.
    - Read-only mirror of everything published on GitHub (47 commits, including the retained `refs/pull/2/head` and `refs/pull/3/head`): 962 chunks, exit 0. A bare mirror needs `--bare`; without it the scan errored with exit 1, which confirms that scanner errors exit 1.
    - The gitleaks proxy's single prose false positive is not a TruffleHog result.
  - **Local probe**: a random synthetic GitHub-token-format value, committed and then deleted in a scratch repository, was detected (`Github` detector, unverified) with exit 183. It appeared 0 times in stderr but was present in the stdout JSON's `Raw` field (hence the private-file rule). The probe repository and value were deleted.
  - **Overlap**:
    - TFLint: Terraform lint and value validity;
    - Trivy config: Terraform misconfigurations, secret scanner off;
    - **TruffleHog: credentials in all files across Git history**;
    - Task 9.4 must exclude Super-Linter's bundled GitLeaks and Trivy secret scanning;
    - GitHub's native secret scanning is complementary and outside repository control.
  - **Task 12.3** runs TruffleHog as part of its audit and depends on this task.
  - **`--max-depth` probe**: in the local probe, `--max-depth=1` still reported the deleted-secret finding. This doesn't change the design: `--max-depth` stays forbidden and full-history scanning stays mandatory.
- **Out of Scope**:
  - rotating or rewriting history (D4)
  - provider verification of candidates
  - SARIF/code scanning, caching, artifacts
  - pinning other actions by SHA (Phase 12)
  - scanning non-Git sources
  - any Azure access or change to the drift-detection or auth workflows
- **Implementation Notes**:
  - Secret **detection** in committed history.
  - Runs on code changes in `security-scan.yml`; it never runs inside or gates the drift-detection workflow.
- **Completion Notes** *(2026-10-04)*:
  - **Implemented**:
    - new `scripts/run_trufflehog.sh` (executable) and `tests/test_trufflehog.py` (17 tests);
    - new `trufflehog` job in `security-scan.yml`: checkout (`fetch-depth: 0`, `persist-credentials: false`), install of the pinned Linux binary with `sha256sum -c` before unpacking, then the script;
    - README "Secret scanning" section, security row, tech-stack row, repository tree, status lines.

    The `tflint` and `trivy-config` jobs, workflow-level keys, both protected workflows (`git diff --exit-code 0cd0f4e`), Terraform, `src/`, the TFLint/Trivy files and their tests are unchanged. The 9.1/9.2 test suites needed no change.
  - **Script behaviour**:
    - checks `jq` first, then `git`/`trufflehog`, then `trufflehog --no-update --version` = `trufflehog 3.97.9`;
    - runs the locked command from the repository root, with stdout JSON written to a private file under `RUNNER_TEMP`/`TMPDIR` (outside the repository, removed on exit);
    - prints TruffleHog's log as level, message and error only, and findings as detector, verified, file, line and commit only;
    - passes exit codes 0/183/other through unchanged, and fails on exit 0 with results or unreadable output.
  - **Ignore-annotation enforcement**: TruffleHog honours its inline ignore annotation per line, so any exemption would be a loophole. The script therefore fails if the annotation appears in any tracked file (`git grep`) or anywhere in the history (`git log --all -G`). The script, tests and README build the string by concatenation. The one plan line that named it literally was reworded (meaning unchanged).
  - **Real local proofs** (verified v3.97.9 darwin arm64 binary, the real script, scratch repositories; random synthetic value never printed, never committed here, deleted afterwards):
    - clean repository → exit 0;
    - secret at HEAD → exit 183;
    - secret deleted in a later commit → exit 183;
    - secret only on another local branch → exit 183 (`--all` covers local branches);
    - no-op control → exit 0.

    In every case the value appeared 0 times in the script's stdout and stderr. The real baseline of this repository via the script: no secrets, exit 0.
  - **Install step** (run with a stubbed `curl` serving the verified Linux archive): the correct hash passes; a tampered hash or a tampered archive fails at `sha256sum -c` before unpacking or `GITHUB_PATH`.
  - **Tests**:
    - `tests/test_trufflehog.py`: 17 passed (fake `trufflehog`, sentinel in `Raw`/`RawV2`/`Redacted`/`ExtraData` never printed);
    - TFLint + Trivy + TruffleHog suites: 56 passed;
    - sensitivity: 16/16 regression mutations caught on a scratch copy, control passed;
    - full suite: 1154 passed, 679 skipped (optional `ai`/`azure` extras absent); coverage 96.05%; `./scripts/validate.sh` passes.

    No Azure call.
  - **CI proof** (user-approved 2026-10-04; commits `6e9f35e` design and `3e86419` implementation pushed, `0cd0f4e..3e86419`):
    - `main` push, commit `3e86419`:
      - `security-scan.yml` run `37170270400`: success, 0 artifacts.
        - Job `trufflehog` (`111341658999`): every step succeeded, including "Install TruffleHog (pinned binary, SHA-256 verified)" and "Run TruffleHog" over the full history.
        - Jobs `tflint` (`111341658984`) and `trivy-config` (`111341659012`): success.
      - `terraform-auth-test.yml` run `37170270430`: success.
    - **D7(a)**, draft PR #4 (branch `ci-proof/task-9.3-trufflehog-hash`, head `28ea13f` = `3e86419` with **only** the committed SHA-256 changed, `…2866` → `…2867`; no secret or credential published):
      - `security-scan.yml` run `37170658769`: the `trufflehog` job (`111342777719`) failed at "Install TruffleHog (pinned binary, SHA-256 verified)" (`sha256sum -c`), and "Run TruffleHog" was **skipped**, so nothing was unpacked or scanned. `trivy-config` (`111342777858`) and `tflint` (`111342777870`) succeeded. 0 artifacts.
      - `terraform-auth-test.yml` run `37170658799`: failed at Azure OIDC login (existing behaviour on PRs).
    - **Cleanup:** PR #4 closed unmerged (2026-10-04T02:21:05Z, `merged=false`; closed by GitHub when the head branch was deleted). The remote and local branches were deleted, and no branch contains `28ea13f`. `main` = `origin/main` = `3e86419`, carrying the correct SHA-256.
    - The browser session was signed out of GitHub, so the user opened PR #4 and confirmed the failing step in the log. The step results above come from the public Actions API.

#### Task 9.4 — Super-Linter Code Quality Enforcement
- **Status**: 🔴 BLOCKED — deferred to Phase 12 (user decision 2026-10-04); not implemented
- **Deferral record (2026-10-04)**:
  - Task 9.4 was paused before its baseline. The Docker daemon was not running on the host, and the user decided not to download or run the Super-Linter image in Phase 9.
  - Nothing was implemented: no `super-linter.yml`, no `scripts/run_super_linter.sh`, no `.github/linters/` configs, no tests, no image pulled, no baseline measured.
  - The design below (D1–D10) stays recorded for Phase 12. Before reuse it must be re-validated in a Phase 12 design review: the image digest and version, the variable names, and the repository baselines (Python, shell, YAML and Markdown counts, and the 19-comment `# noqa` inventory) may have changed.
  - TFLint remains owned by Task 9.1 and is not duplicated.
  - **Scope of D5 (user decision 2026-10-13, Task 12.1 design review, WF-1)**: D5's workflow rule (`.github/workflows/**` neither modified nor linted, protected workflows unchanged) applies in full to the Super-Linter work of this task. It is not a blanket prohibition on later workflow changes; those follow WF-1 (see the Task 12.1 design review).
- **Objective**: Run Super-Linter, from a digest-pinned image, as a code-quality gate in its own workflow. The scope is Python (Ruff, lint only), shell (ShellCheck), non-workflow YAML (yamllint) and Markdown (markdownlint, including `PROJECT_PLAN.md`). A finding is a code-quality failure: never a security result, never a drift result. *(Reworded 2026-10-04 per the Task 9.4 design review.)*
- **Dependencies**: Task 9.3
- **Locked version and execution (D1)**:
  - Image `ghcr.io/super-linter/super-linter@sha256:7620fb6f07a1908b0642d9ddc4f49da7d9f2b9497bcafee4d3d151d1e5567c0b`: the OCI index of tag `v9.0.0`, the standard image the v9.0.0 action references. It contains only linux/amd64 plus a build attestation.
  - Run directly with `docker run --rm --platform linux/amd64 … <image>@sha256:…`. The Super-Linter action is not used, because it references the **mutable** tag `docker://ghcr.io/super-linter/super-linter:v9.0.0`. A pull or run failure fails the job.
  - Environment (each name and value must be confirmed against the v9.0.0 configuration table during implementation; stop if one differs):
    - `RUN_LOCAL=true`, repository mounted at `/tmp/lint` (Super-Linter's documented local mode);
    - `VALIDATE_ALL_CODEBASE=true` (the whole codebase, deterministic, no changed-file mode);
    - `IGNORE_GITIGNORED_FILES=true` (ignored local files such as `.artifacts/` are never linted);
    - `LINTER_RULES_PATH=.github/linters`;
    - `FILTER_REGEX_EXCLUDE` matching only `.github/workflows/` (D5);
    - `MULTI_STATUS=false`, `ENABLE_GITHUB_PULL_REQUEST_SUMMARY_COMMENT=false`, `SAVE_SUPER_LINTER_OUTPUT=false`;
    - `DISABLE_ERRORS` not set.
- **Linter allowlist (D2)**: exactly `VALIDATE_PYTHON_RUFF=true`, `VALIDATE_BASH=true` (ShellCheck), `VALIDATE_YAML=true` (yamllint) and `VALIDATE_MARKDOWN=true` (markdownlint). No other `VALIDATE_*` variable is set.
  - Verified in v9.0.0 `lib/functions/validation.sh`: when any `VALIDATE_*` is `true` and none is `false`, every unset one defaults to `false`; mixing `true` and `false` is a fatal error.
  - So TFLint, `terraform fmt`, Trivy, Checkov, GitLeaks (owned by Tasks 9.1–9.3), formatters (`VALIDATE_PYTHON_RUFF_FORMAT`, black, isort, shfmt, Prettier), GitHub Actions linting (actionlint, zizmor), JSON, copy-paste detection and every other validator stay off.
- **Configuration**: four committed files under `.github/linters/` (`.ruff.toml`, `.shellcheckrc`, `.yaml-lint.yml`, `.markdown-lint.yml`), each copied **verbatim** from Super-Linter v9.0.0 `TEMPLATES/`.
  - Without them, v9.0.0 `lib/functions/linterRules.sh` silently falls back to those templates. Committing them keeps the rules visible and fixed before the baseline.
  - Template content at v9.0.0:
    - Ruff: `line-length = 120`, `[lint] ignore = ["E203"]`, Ruff's default rule selection, which does not include line length; lint only, no formatter (D3);
    - ShellCheck: `source-path=SCRIPTDIR`, `external-sources=true`;
    - yamllint: document start required, line length 80, other rules as in the template;
    - markdownlint: `MD013` line length 400, `MD004`/`MD029`/`MD033`/`MD036` off, other rules as in the template.
  - Any change from the templates is a plan decision taken **before** a baseline is measured, never to turn a measured baseline green.
- **Scope**:
  - all tracked Python, shell, YAML and Markdown files, except `.github/workflows/**` (D5: no changes to protected workflows; GitHub Actions linting and zizmor are deferred to Phase 12);
  - **yamllint**: no non-workflow YAML is tracked today, so only the two YAML config files added by this task are linted;
  - **Markdown**: all tracked `.md` files, including `PROJECT_PLAN.md` (D4).
- **Suppression policy (D8, strengthened 2026-10-04)**:
  - **No new inline suppressions** of any kind:
    - Python: `# noqa`, `# ruff: noqa`;
    - shell: `# shellcheck disable=`;
    - Markdown: `<!-- markdownlint-disable… -->`, `<!-- markdownlint-capture -->`/`restore`;
    - YAML: `# yamllint disable…`.
  - **No increase in the existing `# noqa` count:** exactly the 19 legacy comments below, and no new ones in any Python file.
  - **No other suppression mechanism to make the baseline green:**
    - no extra `FILTER_REGEX_EXCLUDE` or `FILTER_REGEX_INCLUDE`;
    - no `DISABLE_ERRORS`, no `--fix`;
    - no `per-file-ignores`, `extend-ignore` or other rule loosening in the configs (they stay byte-identical to the v9.0.0 templates unless a plan decision taken before measuring says otherwise);
    - no new `.gitignore` entries used to hide tracked files.
  - **Tests detect any new suppression:**
    - the static tests compare the exact per-file, per-code `# noqa` inventory below and fail on any addition (new comment, new code or new file);
    - they also fail on any of the other inline directives in files of the matching type. The four verbatim template config files are checked by SHA-256 instead, because the templates' own comments mention directive syntax.
    - The test file builds these patterns by concatenation, so it never adds an occurrence itself.
  - If a legitimate exception is needed, stop and decide it in the plan.
- **D10 — legacy `# noqa` comments, decided 2026-10-04: option (a), retain.** The repository already contains **19 `# noqa` comments in 11 Python files**. They predate Task 9.4, were not added to make CI green, and are recorded here as **legacy, pre-existing exceptions only**. They are **not** removed or refactored in Task 9.4. Inventory (file:line, rule):
  - `scripts/detect_drift.py`: 46 `E402`, 71 `E402`
  - `scripts/github_automation.py`: 503 `D401`
  - `src/ai_engine/graph.py`: 59 `F401` (re-export)
  - `tests/test_attribution.py`: 53 `E402`, 201 `N802`, 204 `N802`
  - `tests/test_attribution_fallback.py`: 32 `E402`, 35 `E402`
  - `tests/test_classifier.py`: 26 `E402`, 27 `E402`
  - `tests/test_comparator.py`: 24 `E402`, 25 `E402`
  - `tests/test_github_automation.py`: 381 `E731`
  - `tests/test_logging.py`: 26 `E402`
  - `tests/test_parser.py`: 28 `E402`
  - `tests/test_severity.py`: 23 `E402`, 24 `E402`, 25 `E402`

  Totals: 14 `E402`, 2 `N802`, 1 `D401`, 1 `F401`, 1 `E731`; one comment per line. Line numbers may shift when unrelated code moves, so tests compare per-file, per-code counts.
  - Not suppressions in scope: the 2 `# type: ignore` (mypy is not enabled) and the 3 `# shellcheck source=` lines (path directives).
- **Files/Areas**:
  - new `.github/workflows/super-linter.yml` (D7)
  - new `scripts/run_super_linter.sh`: the single local/CI command
  - new `.github/linters/.ruff.toml`, `.shellcheckrc`, `.yaml-lint.yml`, `.markdown-lint.yml`
  - new `tests/test_super_linter.py`
  - `README.md`
  - files that need baseline fixes, only as decided after the baseline (see Acceptance)
  - **Unchanged**:
    - `drift-detection.yml`, `terraform-auth-test.yml`, `security-scan.yml` (its three jobs)
    - Terraform, `.tflint.hcl`, the 9.1–9.3 scripts and tests, `security/trivy-risk-acceptance.json`
    - no mass formatting of Python (D3)
- **Acceptance Criteria** *(deferred with the task: not applicable in Phase 9 and none implemented; objective; the baseline is **not** assumed clean)*:
  - [ ] **Pinned image**: the workflow and script reference only the v9.0.0 index digest above; no tag, no `latest`, no Super-Linter action. A pull or run failure fails the job.
  - [ ] **Allowlist**: exactly the four `VALIDATE_*=true` variables of D2; no other `VALIDATE_*`; the environment exactly as locked above.
  - [ ] **Configuration**: the four `.github/linters/` files byte-identical to Super-Linter v9.0.0 `TEMPLATES/`, unless a later plan decision changes them.
  - [ ] **Suppression inventory (D8/D10)**: the `# noqa` inventory is exactly the 19 legacy comments above (per file and per code); there are no other inline suppressions in Python, shell, Markdown or YAML files; the configs match the template hashes.
  - [ ] **Baseline**: the first real run with the pinned image records the findings per linter and per file in the Completion Notes. The gate is green only after every finding is resolved by a reviewed fix or a recorded plan decision. **Stop and report** after the baseline and before any fix, with options per linter. No suppression or config loosening to get green (D8).
  - [ ] **Workflow `super-linter.yml`**:
    - triggers `push`/`pull_request` to `main` and `workflow_dispatch`;
    - permissions exactly `contents: read`;
    - checkout with `persist-credentials: false`;
    - no `GITHUB_TOKEN` passed to the container (statuses and PR comments are off);
    - concurrency group `super-linter-${{ github.ref }}`, cancelling only pull-request runs;
    - not allowed: `id-token`, `azure/login`, `ARM_*`/`TF_VAR_*`/secrets, cache, artifacts, SARIF, `continue-on-error`.
  - [ ] **No drift or security semantics**: no drift outputs, issues or labels. The log states "code-quality lint, not drift detection".
  - [ ] **Protected**:
    - `drift-detection.yml`, `terraform-auth-test.yml` and `security-scan.yml` unchanged (`git diff --exit-code` against the pre-implementation commit);
    - `.github/workflows/**` never modified or linted;
    - the 9.1–9.3 jobs and tests still pass.
  - [ ] **README**: documents the local command (Docker; on arm64 hosts amd64 emulation via `--platform linux/amd64`), the pinned digest and upgrade procedure, the allowlist and scope, the suppression policy, and D10 (19 retained legacy `# noqa` comments; no new ones).
- **Validation** *(deferred with the task)*:
  - [ ] Static pytest (`tests/test_super_linter.py`):
    - digest pin;
    - exact allowlist and environment;
    - no forbidden variables, flags or actions;
    - configs equal to the recorded template SHA-256s;
    - the exact D10 `# noqa` inventory (per file, per code; fails on any new comment, new code or new file) and no other inline directives (D8);
    - job permissions, no token, no Azure/drift elements;
    - protected workflows contain no Super-Linter.
  - [ ] Real local baseline with the pinned image (D9 approved the download), recorded per linter.
  - [ ] Mutation checks on **scratchpad copies** with the real image. Each must fail except the last two:
    - an unused import (Ruff `F401`);
    - an unquoted variable expansion (ShellCheck `SC2086`);
    - a Markdown rule violation;
    - a YAML rule violation in a non-workflow YAML file;
    - a wrong digest (pull failure);
    - a new `# noqa` added in a scratch copy, which must fail the static test (D8).

    Must still pass:
    - a violation placed under `.github/workflows/` (exclusion works);
    - a Terraform or secret-like pattern (overlapping validators off).

    Plus a no-op control.
  - [ ] **CI proof (approval-gated)**:
    - a green `main` push of `super-linter.yml`;
    - a draft PR adding one deliberate ShellCheck violation in a scratch shell file (no secret, no protected file), which must fail the job; the PR closed unmerged and its branch deleted.

    The PR also triggers `security-scan.yml` (expected green) and `terraform-auth-test.yml` (Azure login fails on PRs, existing behaviour).
- **Design Review (2026-10-04)**:
  - **Verified semantics (v9.0.0 source)**: allowlist rules in `lib/functions/validation.sh`; template fallback in `lib/functions/linterRules.sh`; local mode in `docs/run-linter-locally.md` (`RUN_LOCAL=true`, code mounted at `/tmp/lint`, use a specific version rather than `latest`).
  - **Image** (manifest metadata only, nothing downloaded):
    - v9.0.0 index `sha256:7620fb6f…567c0b` → linux/amd64 manifest `sha256:496fe2e1…db73`, 1.89 GB compressed (85 layers);
    - `slim-v9.0.0` index `sha256:7d0b4d33…d9e4`, 1.37 GB, also contains the four D2 linters (not chosen; a future reviewed change).
    - The upstream workflow example requests `issues`, `pull-requests` and `statuses` write; all of those features are off here (D6).
  - **Baseline facts (2026-10-04, measured without Super-Linter)**:
    - 59 tracked Python files (24,370 lines; no Ruff/black/flake8 configuration);
    - 9 shell scripts, one of them without a shebang (`tests/scenarios/rg_tag_drift_common.sh`, a sourced library), which ShellCheck may report;
    - 0 non-workflow YAML files;
    - 5 Markdown files with **204 lines longer than 400 characters** (longest 2,261), so the template's `MD013` limit is expected to report findings;
    - 19 pre-existing `# noqa` comments (D10).
  - **Overlap**: TFLint (9.1), Trivy config (9.2) and TruffleHog (9.3) keep sole ownership of Terraform lint, Terraform security and secret scanning; Super-Linter's copies of those tools are off (D2).
- **Out of Scope**:
  - formatters and mass formatting (D3)
  - GitHub Actions linting and zizmor (Phase 12, D5)
  - other languages
  - changing protected workflows
  - pinning actions by SHA (Phase 12)
  - any Azure access
- **Implementation Notes**:
  - Code-quality linting only. It never runs inside or gates the drift-detection workflow.
- **Completion Notes**:
  - None — not implemented; deferred to Phase 12 (2026-10-04).

---

### PHASE 9A — AI Analysis Integration (pre-Phase 10)
**Status**: 🟢 COMPLETED

Phase 9A is a lettered pre-phase (like Phase 5A) placed before its first consumers. It owns the deferred Task 6.6 AI CLI/workflow integration (Task 6.6 limitation (d): "no CLI or workflow integration yet"). Phase 6 stays COMPLETED and is not reopened. *(Recorded 2026-10-03 per the approved Phase 8 restructuring.)*

#### Task 9A.1 — AI Analysis CLI & No-LLM CI Integration
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Objective**: Provide an `ai-analysis` CLI over `run_analysis` / `write_report`, and run it without an LLM in a separate CI workflow after every valid drift-detection run. It publishes the AI report as its own artifact for downstream consumers. The deterministic drift result is never changed.
- **Amendment (2026-10-04, Phase 9B)**: D5's "No Activity Log data or caller identity: `ai_engine` never reads Phase 7 output" is superseded by Phase 9B's public investigation profile (G11), integrated in Task 9B.5. The caller identity, subscription/tenant/resource/event IDs, IPs and raw Activity Log content remain excluded from every public artifact. `AI_LLM_PROVIDER=none` in CI stays unchanged (G14). The record below is historical.
- **Amendment (2026-10-05, Task 9B.5 decision 6)**: D4's "an invalid report is unknown" is narrowed, effective with Task 9B.5:
  - a valid public report with `outcome: failed` (or a missing artifact) is still UNKNOWN with no AI analysis;
  - a present report that is invalid or not the public contract fails the job, with no result artifact.
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: the AI workflow's input is the **public** drift report. The AI report's "same exposure profile as the drift report artifact" now means the public drift report profile: Terraform configuration values (incl. configured IPs/CIDRs and URLs) can appear, while ARM/resource IDs, subscription/provider paths, GUIDs and UPN/email-like identities are `withheld`. The AI report's `drift_report_sha256` is the public report's canonical SHA-256. The record below is historical.
- **Dependencies**: Task 6.6, Task 5.4 (Phase 6's evidence-vs-inference checks are also complete)
- **Downstream consumers**: Task 10.3 (AI cost explanation), Task 13.1 (consumes real AI report artifacts).
- **Locked decisions (2026-10-04)**:
  - **D1 — CLI**: a separate console entry point, `ai-analysis = "ai_engine.cli:main"`.
    - Nothing is added to `drift-engine`; `drift_engine` never imports `ai_engine`, and `pip install .` still pulls no LLM stack.
    - Usage: `ai-analysis --report <drift_report.json> --output-dir <dir>`. It validates the report as `DriftReport`, runs `run_analysis` and writes `ai_analysis_report.json` / `.md` with `write_report`.
    - Exit codes, mirroring `drift-engine`:
      - `0` report written;
      - `1` input rejected (invalid report, or `outcome` not `succeeded`): nothing written;
      - `2` usage, or the `ai` extra not installed (clear message);
      - `70` internal error;
      - `73` write error.
  - **D2 — Pinned AI dependencies in CI**: a CI-only constraints file pins the **complete resolved dependency set** of `.[ai]` with exact `==` versions (including transitive packages). The versions are resolved at implementation and recorded in the Completion Notes, and must satisfy the `pyproject.toml` ranges. Local development keeps the ranges; only CI is pinned.
  - **D3 — Separate workflow, isolated status**:
    - New `.github/workflows/ai-analysis.yml` triggered by `workflow_run` (`types: [completed]`, `workflows: ["Phase 5 - Drift Detection"]`, `branches: [main]`). An AI failure can never change the drift-detection run's result.
    - `drift-detection.yml` stays unchanged, so the existing workflow-structure tests stay valid.
    - Because a `workflow_run` workflow can access secrets and write tokens, its permissions are set explicitly and it references **no secrets other than `github.token`**, used only for the cross-run artifact download.
  - **D4 — When it runs: every valid detection result, never `unknown`.**
    - Validity is decided from evidence, **not** from the source run's conclusion. A valid run whose `issues` job failed still counts as valid.
    - The job checks the source run (`github.event.workflow_run.id`). If its `drift-report-<source run id>` artifact doesn't exist (a failed or `unknown` run uploads none), it writes a summary line ("detection result unknown: no AI analysis") and ends without an AI artifact. That's not an AI failure.
    - If the artifact exists, the report must validate as `DriftReport` with `outcome == "succeeded"` and a boolean `has_drift` (`true` or `false`). Otherwise it's treated as `unknown` and no AI analysis runs.
  - **Exact source-run binding (preserved from Phase 8)**:
    - The downloaded report's `run.run_id` must equal `github-<workflow_run.id>-<workflow_run.run_attempt>`.
    - `workflow_run.head_branch` must be `main`.
    - `workflow_run.event` must be `schedule` or `workflow_dispatch`.

    Otherwise the job fails without writing an AI artifact (stale or foreign evidence is never analysed).
  - **No LLM in CI**:
    - the job sets `AI_LLM_PROVIDER: none` explicitly and passes no LLM secrets (`OPENAI_*`, `AZURE_OPENAI_*`, `AI_LLM_*` keys);
    - when `GITHUB_ACTIONS == "true"`, the CLI refuses to run unless `AI_LLM_PROVIDER` is **explicitly** `none` (an unset or default value isn't enough);
    - enabling a real LLM in CI remains a separate gated decision (secrets, data leaving the runner, cost) needing explicit approval.
  - **D5 — Artifact**:
    - `ai-analysis-report-<source run id>` (the drift-detection run it analysed), holding `ai_analysis_report.json` and `ai_analysis_report.md` only, retained 30 days;
    - `if-no-files-found: error` once analysis has run;
    - **public-exposure profile explicitly accepted (2026-10-04):** the same profile as the existing `drift-report-<run_id>` artifact (Task 5.4). That includes real non-sensitive attribute values, HCL value fragments from the real view, remediation command templates with working directory and resource addresses, and the deterministic summary. Sensitive values stay redacted, as in the source report. No Activity Log data or caller identity: `ai_engine` never reads Phase 7 output.
  - **D6 — Publication**: the step summary contains **counts only** (resources, options, sections; LLM status "none"), no AI text. **No AI content in GitHub issues:** `scripts/github_automation.py` and the issues job are unchanged.
- **Files/Areas**:
  - new `src/ai_engine/cli.py`
  - `pyproject.toml`: the `[project.scripts]` entry only
  - new CI-only constraints file `ci/ai-constraints.txt`
  - new `.github/workflows/ai-analysis.yml`
  - new `tests/test_ai_cli.py` (CLI, environment enforcement and workflow-structure tests)
  - `README.md`
  - `docs/drift-detection-spec.md` §8.3: publication of the AI artifact
  - **Unchanged**:
    - `drift-detection.yml`, `security-scan.yml`, `terraform-auth-test.yml`
    - `src/drift_engine/`, `scripts/github_automation.py`, and the existing `ai_engine` modules (graph, nodes, config, verify)
    - Terraform, `schemas/`
- **Acceptance Criteria**:
  - [x] **CLI (D1)**: `ai-analysis` behaves exactly as specified (usage, outputs, exit codes 0/1/2/70/73). A failed or invalid report writes nothing. Output is byte-identical for identical input. `drift-engine` is unchanged, with no import of `ai_engine` and no new dependency in a core `pip install .`.
  - [x] **No LLM**: in CI the CLI runs only with `AI_LLM_PROVIDER` explicitly `none`; the workflow passes no LLM secrets; with provider `none`, no network connection is attempted (verified under the test network guard); the report records the LLM as unavailable/none.
  - [x] **Pinned dependencies (D2)**: CI installs `.[ai]` only through `ci/ai-constraints.txt`, which pins every resolved package with `==`. A missing or unpinned entry fails a test.
  - [x] **Workflow (D3)**:
    - `workflow_run` on completed `Phase 5 - Drift Detection` runs on `main` only;
    - permissions exactly `contents: read`, `actions: read`;
    - no `id-token`, `azure/login`, `ARM_*`/`TF_VAR_*`, or secrets other than `github.token` (download step only);
    - checkout with `persist-credentials: false`;
    - concurrency per source run;
    - no `continue-on-error` hiding an AI failure (the AI workflow's own status reflects AI success; detection is unaffected).
  - [x] **Validity and binding (D4)**: never runs analysis for `unknown`; runs for both `has_drift` `true` and `false`; enforces the exact `run.run_id`, branch and event binding; never analyses evidence from another run or attempt.
  - [x] **Detection unchanged**: `drift_detected`, the drift report, its artifact and the drift-detection run status are unchanged (the drift workflow is byte-identical; AI output is a separate artifact).
  - [x] **Artifact (D5)**: `ai-analysis-report-<source run id>`, the two files only, 30 days. The content matches the accepted exposure profile (no caller identity, no Activity Log data, sensitive values redacted).
  - [x] **Publication (D6)**: the step summary holds counts only; no AI content appears in issues (the issues job and `github_automation.py` are unchanged).
  - [x] **Documentation**: README (CLI usage, workflow, artifact, exposure profile, no-LLM rule) and spec §8.3 updated.
- **Validation**:
  - [x] CLI tests over the existing report fixtures, with the network guard active. They cover:
    - exit codes and failed/invalid reports;
    - determinism;
    - environment enforcement: the CLI refuses in CI unless the provider is explicitly `none`;
    - core install without the `ai` extra: clear exit 2;
    - an unchanged `drift-engine` CLI.
  - [x] Workflow-structure tests:
    - triggers, filters, permissions, no secrets or Azure elements;
    - the binding and validity checks present;
    - artifact name and retention;
    - counts-only summary;
    - the constraints file used, and all its entries pinned exactly;
    - the constraints equal the complete `drift-engine[ai]` dependency closure (indirect dependencies included);
    - `drift-detection.yml` and `github_automation.py` unchanged.
  - [x] Synthetic gate tests:
    - missing source artifact → skipped with "unknown" and no AI artifact;
    - `outcome: failed` → no analysis;
    - wrong `run_id` or attempt, wrong branch or event → failure without an artifact;
    - `has_drift` `true` and `false` both analysed.

    These replace a real `unknown` run, which cannot be produced safely.
  - [x] **Real CI proof (approval-gated)**:
    - push to `main`, then a manual `drift-detection` dispatch (an Azure read-only plan, needing approval);
    - the triggered `ai-analysis` run succeeds;
    - download `ai-analysis-report-<source run id>` to `.artifacts/` and check `generated_from.drift_report_sha256` (the SHA-256 of the canonical JSON of the report, not of the file bytes) against the source run's `drift-report-<run id>` artifact, LLM status none, counts matching the summary;
    - the drift-detection run's status and `drift_detected` unchanged.
- **Implementation Notes**:
  - With provider `none`, the "AI" report contains only deterministic content: summary, resources, remediation options. AI sections are recorded as unavailable.
  - Real LLM in CI remains a separate gated decision (secrets, data egress, cost) requiring explicit approval.
- **Completion Notes**:
  - **Local implementation and validation (2026-10-04; checkpoint commit `de22b01`)**:
    - Files as locked: new `src/ai_engine/cli.py`, `ci/ai-constraints.txt`, `.github/workflows/ai-analysis.yml`, `tests/test_ai_cli.py`; `pyproject.toml` (the `ai-analysis` entry in `[project.scripts]` only); README (new "AI Analysis (Task 9A.1)" section, status, structure, roadmap, limitations); spec §8.3 ("AI analysis publication").
    - The protected files are byte-identical to `HEAD` (`git diff --exit-code`): `drift-detection.yml`, `security-scan.yml`, `terraform-auth-test.yml`, `scripts/`, `src/drift_engine/`, `schemas/`, `terraform/`; the existing `ai_engine` modules are unchanged (only `cli.py` is new).
    - **Resolved pins (D2)**: 43 packages, resolved 2026-10-04 for CPython 3.12 / manylinux x86_64 (the CI runner), every one within the `pyproject.toml` ranges. They are listed with `==` in `ci/ai-constraints.txt`. Key versions: langgraph 1.2.12, langchain-core 1.6.6, langchain-openai 1.6.7, openai 3.24.0, pydantic 2.13.5 (pydantic_core 2.46.5), PyYAML 6.0.3, httpx 0.28.1. The workflow installs `.[ai]` only with `-c ci/ai-constraints.txt` and fails if any installed distribution (other than drift-engine, pip, setuptools and wheel) is missing from the file or differs from its pin. The same pins also install on Python 3.13 / macOS arm64 (the local test environment).
    - **Tests**: `tests/test_ai_cli.py` has 44 tests, all passing:
      - CLI: exit codes 0/1/2/70/73 and usage errors; nothing written for failed or invalid reports; byte-identical output across two runs; `has_drift` true and false; LLM `none`/`not_attempted` with no evidence sent; actor `unknown`; the drift report is unchanged;
      - environment: a refusal in GitHub Actions when the provider is unset, empty, `openai` or `azure_openai`;
      - a missing `ai` extra exits 2 with a clear message (a subprocess blocks the langgraph/langchain imports);
      - `drift_engine` and `scripts/github_automation.py` never import `ai_engine`, and the core dependencies are still PyYAML and pydantic;
      - dependency pins (D2): `test_constraints_equal_the_complete_ai_closure` replaces the earlier check of five direct packages. It builds the complete `drift-engine[ai]` dependency closure from `pyproject.toml` (core dependencies plus the `ai` extra) and the installed package metadata, evaluating markers for the test interpreter and following requested extras. That closure is 43 packages, including indirect dependencies such as `jiter`. The test requires `ci/ai-constraints.txt` to equal it exactly, every entry as `name==version`. It fails on a missing, duplicate, extra (not required), non-exact or version-mismatched pin, and on a pin outside a declared requirement range. It is skipped when the `ai` extra is not installed. It checks the test environment's platform (here Python 3.13 / macOS arm64), and assumes that environment was installed with the constraints;
      - workflow structure, plus the gate steps actually run with synthetic inputs: a missing artifact gives `present=false` with the "unknown" summary and exit 0; failed, malformed or contract-invalid reports give `valid=false` and exit 0; a wrong attempt, wrong run, local run id or `run: null` exits 1; a wrong branch or event (push, pull_request) exits 1;
      - the summary step's output holds counts only.
    - **Full suite**: 1855 passed, 22 skipped (the opt-in `azure` extra), drift_engine coverage 96.05% (gate 85%).
    - **Sensitivity check**: 11 mutations on a scratch copy; 10 were caught, each failing a test:
      - binding without the attempt;
      - every report treated as valid;
      - `has_drift: false` not analysed;
      - the branch check broken;
      - the CLI accepting `openai` in CI;
      - `name` instead of `pattern` for the download;
      - an `OPENAI_API_KEY` secret added;
      - 90-day retention;
      - an unpinned `langgraph` entry;
      - an `issues: write` permission.

      The surviving mutant (dropping the CLI's `outcome != "succeeded"` check) is equivalent: the `DriftReport` contract already rejects a failed report with a boolean `has_drift`, so that check is defence in depth.
    - **Pin-test sensitivity check**: 7 tampered constraints files on a scratch copy; the closure test failed for each:
      - `jiter` removed (indirect): "required but not pinned";
      - `langgraph` removed (direct): "required but not pinned";
      - `tenacity>=9` instead of `==9.1.4`: the non-exact entry is reported;
      - `six==1.17.0` added, which nothing requires: "pinned but not required";
      - `jiter==0.16.0`, while 0.17.0 is installed: "installed versions differ from the pins";
      - `langgraph==2.0.0`: "pins outside the declared ranges";
      - `jiter` listed twice: "duplicate pin".
    - **End-to-end (local)**: `drift-engine analyze` on the `external_drift` fixture, then `ai-analysis` with `GITHUB_ACTIONS=true AI_LLM_PROVIDER=none`, exits 0: 1 resource, 2 remediation options, all 5 AI sections `skipped`, LLM `none/not_attempted`. With the provider unset under `GITHUB_ACTIONS=true` it exits 2.
    - `git diff --check` is clean. Like the other pytest-based test modules, `test_ai_cli.py` is not collected by the stdlib-only `python3 -m unittest discover` run.
    - Not done here: the actual install of a core-only (no `ai` extra) environment, which would need a package download; the missing extra is simulated instead.
    - **Clean-environment pin verification (2026-10-04)**: in fresh Python 3.13 venvs (only `pip` pre-installed; `pip --isolated --no-cache-dir`), `pip install -c ci/ai-constraints.txt ".[ai]"` installed exactly the 43 pins plus drift-engine, with no "already satisfied" requirement. Two independent installs gave identical `pip freeze` output. A resolver-only run for CPython 3.12 / manylinux x86_64 gave the same 43 pins. The workflow's pin check, extracted verbatim, passed on the clean install and failed (exit 1) for a removed indirect pin (`jiter`), a removed direct pin (`langgraph`), a range entry (`tenacity>=9`), an extra unpinned package (`six`) and a pinned package changed after install (`sniffio` 1.3.0).
  - **Real CI proof (user-approved, 2026-10-04)**: the user dispatched the drift workflow manually; I monitored it through the public Actions API, and the user downloaded the artifacts into `.artifacts/` (gitignored; extracted copies in `.artifacts/task-9A.1-ci-proof/`).
    - **Source run** `37178020110` (Phase 5 - Drift Detection #18, `workflow_dispatch`, `main`, commit `de22b01`, attempt 1, 04:47:39–04:49:01Z): Preflight, Terraform Plan & Drift Analysis, Drift Issues and Report & Summary all **success**.
      - Plan job steps: Azure OIDC login and verify, Setup Terraform, `init` (remote backend), `validate`, Generate Plan Evidence, Analyze Drift, Upload Drift Report. No apply or state-changing step; the manifest records plan exit 0 and show exit 0 (Terraform 1.14.7).
      - Result: valid no-drift. `outcome: succeeded`, `has_drift: false`, `{"in_sync": 5}`, `run_id` `github-37178020110-1`. No issue was created, updated or closed.
      - Artifact `drift-report-37178020110` (`drift_report.json`, `detection_run.json`; 30 days).
    - **AI run** `37178086052` (Phase 9A - AI Analysis (no LLM), `workflow_run`, `main`, `de22b01`, attempt 1, 04:49:03–04:49:29Z, started 2 s after the source run completed): **success**, all 10 steps successful.
      - Verify source run: `main` / `workflow_dispatch`. The download and presence check found the artifact.
      - Install (pinned): the exact-pin check passed on the Linux runner.
      - Validate and bind: valid report bound to `github-37178020110-1`.
      - The analysis, the counts-only summary and the upload all ran. No `::error::` annotations; the only annotations are GitHub's Node.js 20 deprecation and `ubuntu-latest` migration notices, which every workflow shows (Phase 12 hardening).
    - **Artifacts** (downloaded unchanged):
      - `drift-report-37178020110.zip`: SHA-256 `fc5bba15797ae9fd2d52ce95664fb4cbb4d92a92973113c2a2dfea4040b1e29a`, equal to the GitHub artifact digest;
      - `ai-analysis-report-37178020110.zip`: SHA-256 `8a05e87cfef409174fc27c567fd8be3ce72ca1074e2b41f126b37018bbf80e2e`, equal to the GitHub artifact digest. Name bound to the source run id; it contains exactly `ai_analysis_report.json` and `ai_analysis_report.md`; 30 days (expires 2026-11-03).
    - **Report checks**: the AI report validates as `AiAnalysisReport`.
      - `generated_from.drift_report_sha256` = `744d4284…cf86e7` equals `drift_report_sha256()` (canonical JSON: sorted keys, compact separators, UTF-8) of the downloaded `drift_report.json`. The raw-file hash is different by design.
      - `generated_from.run_id` = `github-37178020110-1`; environment `dev`.
      - `llm`: `attempted: false`, provider `none`, status `not_attempted`, `evidence_sent: []`, model `null`.
      - All 5 AI sections `skipped`; attribution actor `unknown`, `confirmed: false`.
      - Counts match the drift report: `has_drift: false`, `resources_total: 5`, `{"in_sync": 5}`, 0 drifted resources, 0 remediation options.
      - Regenerating locally from the downloaded drift report with `ai-analysis` (`AI_LLM_PROVIDER=none`) gives **byte-identical** JSON and Markdown to the CI artifact.
    - **Exposure checks** on both AI files: no GUIDs or subscription IDs, no ARM resource IDs, no emails or UPNs, no caller, claim or principal fields, no Activity Log fields, no secret-like strings. "Activity Log" appears only as the constant `pending: phase_7_activity_log` marker and the standard limitation sentence.
    - **Coverage of D4**: the real run exercised the valid `has_drift: false` path. The `true` path, the `unknown`/missing-artifact path and the binding failures are covered by the synthetic gate tests and the local end-to-end run (a real `unknown` run cannot be produced safely). The step-summary text itself is not available through the public API, so the summary counts were not compared against the rendered summary; that step succeeded, and it renders these counts from this same artifact JSON.

---

### PHASE 9B — Drift Investigation (WHO / WHEN / WHAT)
**Status**: 🟢 COMPLETED — 2026-10-11 (Tasks 9B.1–9B.6 and 9B.4A complete; Task 9B.6 passed on real Azure cycle 2, runs #37–#40 on commit `4d89c94`, under the plan locked on 2026-10-10 with D-4 to D-6)

Phase 9B owns the end-to-end drift investigation requirement. When Terraform detects drift on an Azure resource, the platform produces an investigation report. It answers, as far as the evidence allows: WHAT changed, WHEN, WHO (which identity Azure recorded), WHY / what it means, and WHAT TO DO. Created 2026-10-04 by user decision, after the requirement gap recorded in the Phase 6 and Phase 7 headers. Phase 6 and Phase 7 return to 🟢 when Task 9B.6 passes. Phase 10 is on hold until then.

> **Product requirement (user, 2026-10-04)**: for each drifted resource the report answers:
> 1. **WHAT**: resource; the property/attribute where deterministically knowable; expected and actual values; the relevant Azure operation(s).
> 2. **WHEN**: Activity Log event time; detection time; the correlation window. Event time and detection time are always distinguished.
> 3. **WHO**: the Activity Log caller identity and caller type where safely available. Confirmed evidence is separated from inference, and an actor is never invented.
> 4. **WHY**: AI analysis in context: impact, risk, and whether the recorded operation is consistent with the detected drift. Inference is always labelled.
> 5. **WHAT TO DO**: deterministic remediation options, a recommended action, human approval required, and never an autonomous destructive change.
>
> Any fact the evidence cannot prove is reported as **"not confirmed by available evidence"**. It is never omitted, guessed or invented.

> **Verified Azure event shape (2026-10-04, read-only check by Claude, user-requested)**:
> - **Method**: `az monitor activity-log list` on `aitdd-dev-main-rg` for 2026-10-03 to 2026-10-04, run in the user's logged-in CLI session. No write.
> - **Raw output**: `.artifacts/task-activity-log-shape-check/raw_rg_events.json` (gitignored, 0600; it contains the caller UPN, IP address and claims, so it is never committed and only sanitized fixtures derive from it).
> - **Operation**: a portal tag edit on the resource group is the operation `Microsoft.Resources/tags/write`, category `Administrative`, level `Informational`, HTTP `PATCH`, logged as two rows that share one `correlationId`:
>   - `BeginRequest` / `Started` (no subStatus): `resourceId = <rg-id>/providers/Microsoft.Resources/tags/default`;
>   - `EndRequest` / `Succeeded` (subStatus `OK`, `properties.statusCode`): `resourceId = <rg-id>` (the resource group itself).
>   - `authorization.action = Microsoft.Resources/tags/write` on both rows, and `authorization.scope = <rg-id>/providers/Microsoft.Resources/tags/default`.
>   - `operationId` equalled `correlationId` in two of three operations, so it is not relied on.
> - **No property data**: `properties` holds only `entity`, `eventCategory`, `hierarchy`, `message` (plus `statusCode`). There is no request/response body, no tag name and no value. The Activity Log does not prove which property changed.
> - **Caller**: `caller` equals the `upn` claim. `claims.idtyp = user`. `claims.appid` was the Azure Portal first-party application for the 2026-10-04 operation and the Azure CLI first-party application for two 2026-10-03 tag writes.
> - **Ingestion delay**: `submissionTimestamp − eventTimestamp` was 49–112 s across 6 rows. Microsoft publishes no ingestion SLA.
> - **Test-run timeline** (drift run `37197574080`, public job timings):
>   - operation 11:04:56.09Z–11:04:58.19Z;
>   - Generate Plan Evidence 11:06:39–11:06:57Z (manifest `started_at` = script start);
>   - plan timestamp 11:06:49Z;
>   - previous valid run `37178020110` (04:47:39–04:49:01Z): `has_drift: false`, all 5 resources `in_sync`.
> - **Under the Phase 7 rules**:
>   - not collected (no CI step);
>   - grouped as `related` (not the resource-group lifecycle operation; the Started row is a descendant);
>   - R0 `update_not_attributable`;
>   - P5 `evidence_not_settled` if collected in-job;
>   - "during detection" under the ±5-minute skew.

#### Phase 9B locked decisions (user-approved 2026-10-04)

- **G1 — Ownership and status**: Phase 9B owns the requirement end to end. Phase 6 and Phase 7 are 🟡 with requirement-gap amendments; their completed task records stay unchanged as history. Phase 10 is 🔴 BLOCKED (on hold) until Phase 9B is completed and verified. Tasks run strictly one at a time: 9B.1 → 9B.2 → 9B.3 → 9B.4 → 9B.4A → 9B.5 → 9B.6 (9B.4A added 2026-10-05, user-approved P4). Each task starts with a design review that refines details inside these locked rules; changing a G-decision needs user approval.
- **G2 — Sources of truth**:
  - **Terraform** (the drift report) owns resource, attribute path, expected value and actual value.
  - **The Azure Activity Log** owns the recorded operation, its timestamps and status, the recorded caller and the event context.
  - **The correlation layer** (deterministic code) decides how strongly the two relate.
  - **The AI** only interprets this evidence.
  - No design relies on the Activity Log carrying property values.
- **G3 — Three separate claims, never merged**:
  1. **Recorded operation**: evidence, "Azure recorded operation O on this resource at T, status S, caller type C, channel A".
  2. **Relationship to the drift**: verdict (G4) plus property link (G5).
  3. **Actor attribution**: `confirmed` only when the property link is `confirmed`; otherwise "not confirmed by available evidence".

  A recorded caller is never presented as the author of the drift unless claim 3 is confirmed.

  **Meaning of the verdicts (amended 2026-10-04, Task 9B.2 design review)**: `sole_capable_operation` / `latest_capable_operation` mean only that the operation *can explain every relevant drifted property area* (G6) under the timing and completeness rules. They never mean that the exact Terraform property or value was proven. Update drift can never become property-confirmed; only the deletion path (G5) can produce `property_link = confirmed`.
- **G4 — Correlation verdicts (exactly five, per drifted resource)** *(amended 2026-10-04, Task 9B.2 design review, user-approved issues 1, 2, 4)*:
  - **Inputs**: Administrative operation groups only (G6), classified by timing (G7), and the resource's *relevant property areas* (G6). A **candidate** is a successful (or unresolved) group of a capable or unclassified operation inside the resource's window (G9) or `during_observation`.
  - `sole_capable_operation`: all of the following hold:
    - a last-in-sync anchor exists (G9);
    - exactly one successful capable group is `before_observation` within [anchor window start, observation start], and it is capable for **every** relevant property area;
    - there is no other candidate in that window, and no candidate `during_observation`;
    - there is no automated-activity signal, no unresolved group and no unreadable event in the target's scope (below).
  - `latest_capable_operation`: no anchor, and all of the following hold:
    - the most recent successful candidate `before_observation` in the lookback window is a capable group that explains **every** relevant property area (the earlier ones are counted);
    - there is no candidate `during_observation`;
    - there is no automated-activity signal, no unresolved group and no unreadable event in the target's scope.
  - `ambiguous`: anything that prevents the two verdicts above while some candidate or signal exists. One fixed reason code says which:
    - `multiple_capable_operations`, `partial_capability` (no single capable group explains every relevant area);
    - `unclassified_operation`, `during_observation`, `unresolved_operation`, `automated_activity`;
    - `unreadable_events_in_scope` (a verdict that would otherwise be `sole` or `latest`).
  - `no_capable_operation_found`: the investigation completed and found no candidate and no signal in the window. It is always qualified by completeness (G8) and never phrased as "no change happened". It is not allowed when the target's scope has unreadable events: that case is `not_investigated`.
  - `not_investigated`: no usable evidence for the resource, with a fixed reason code: collection failed or incomplete for its scope, no or invalid or unsupported resource ID, evidence binding failure, failed evidence, unknown detection time, the artifact missing (Task 9B.4), or `unreadable_events_in_scope` instead of `no_capable_operation_found`. In the AI report (Task 9B.4) the artifact missing is `investigation_not_provided` and a bindable failed investigation is `investigation_failed` (D3).
  - **Window membership and ordering (user-approved 2026-10-04, rule details 1 and 3)**:
    - A group is in a resource's window when its **end** is at or after the window start. Groups that straddle the start are included, which only adds candidates.
    - `latest_capable_operation` needs a well-defined latest group. If any other successful candidate overlaps the latest one in time (its end is at or after the latest's start), the verdict is `ambiguous`: `multiple_capable_operations` when that other group is capable, else `unclassified_operation`.
  - **Unreadable events in the target's scope**: the collector dropped events of the target's (subscription, resource group) scope for `malformed_event`, `invalid_event_data_id`, `invalid_timestamp`, `invalid_resource_id`, `invalid_operation_name` or `conflicting_duplicate`. Such events could belong to the target and cannot be read, so these verdicts are conservative. Other drop reasons (`excluded_category`, `out_of_scope`, `timestamp_outside_window`, `duplicate`) do not count.
- **G5 — Property link** *(amended 2026-10-04, Task 9B.2 design review, user-approved issues 6, 7)*:
  - `inferred_not_provable` whenever at least one successful capable group exists for the resource in its window, whatever the verdict (the Activity Log carries no property values).
  - `confirmed` only where deterministic evidence proves it: only for a **deletion** (`drift_action = delete`), and only through the deletion rule `external_deletion_v1` under rules version 2. The rule id is unchanged; Task 7.2's rule is re-parameterized:
    - the detection skew becomes 60 s (G7);
    - "settled" becomes `queried_at ≥ run.finished_at + M` (G8);
    - a deletion cannot be confirmed when the target's scope has unreadable events (G4);
    - **existence anchor** may be A (`write_event`, as before) or B (`prior_detection_run`: the trusted last-in-sync anchor of G9 for that address, proving the resource existed at the anchor's observation);
    - every other safeguard (R1–R7) is unchanged, including R7's **±5-minute** automated-activity overlap window around the candidate delete, which stays independent of the 60 s observation skew.
  - `none` when there is no successful capable group (`no_capable_operation_found`, `not_investigated`, or an `ambiguous` verdict with no capable group).
  - **Invariant**: update, create and replace drift is never `confirmed`.
  - **Invariant (Option A, user decision 2026-10-04)**: `property_link = confirmed` requires **both**:
    1. the deletion rule `external_deletion_v1` (rules version 2) confirms; and
    2. the G4 verdict is `sole_capable_operation` or `latest_capable_operation`.

    An `ambiguous` (or any other) verdict never coexists with a confirmed property link or confirmed actor attribution. A deletion the rule confirms under another verdict stays `inferred_not_provable`, with reason `verdict_not_decisive`.
  - **Existence-anchor ordering (user-approved 2026-10-04, rule detail 2)**:
    - When both A (latest successful exact-resource write) and B (`prior_detection_run`) exist, the **later** existence proof is used: A's time is its latest Succeeded row; B's time is the anchor run's `run.finished_at`.
    - With B, the candidate delete must start after B's `run.finished_at + 60 s`. Any lifecycle group overlapping B's observation window [`run.started_at − 60 s`, `run.finished_at + 60 s`] gives `order_ambiguous`.
    - The R4 "exactly one successful delete after the anchor" and every other R1–R7 check apply unchanged.

  Actor attribution (G3 claim 3) is `confirmed` only with `confirmed` property link.
- **G6 — Capable-operations model (versioned table, v1 = verified operations only)**:
  - **Verified extension types** (amended 2026-10-04, Task 9B.1 design review): an event is an `extension` of a target only when its resource ID is `<id>` followed by an allowlisted extension suffix. v1 allows exactly one: `/providers/Microsoft.Resources/tags/default` (verified). Everything else below a target is `descendant`.
    - **Why an allowlist**: a resource group's contained resources (e.g. `…/resourceGroups/rg/providers/Microsoft.Resources/deployments/x`) have the same path shape as extension resources. A namespace rule such as `<id>/providers/Microsoft.Resources/*` would misclassify them and make every resource-group verdict `ambiguous`.
    - A new extension type needs a recorded real-Azure shape check, like a new table entry.
  - **Categories (amended 2026-10-04, Task 9B.2 design review, issue 4)**: only `Administrative` operation groups can be capable or unclassified.
    - A `Policy` or `Autoscale` event on `<id>` or a verified extension with the same `correlationId` as an Administrative candidate group is attached to that group (no effect).
    - Any other such event in the resource's window or `during_observation` is an **automated-activity signal**: `ambiguous` (`automated_activity`).
  - **Relevant property areas (amended 2026-10-04, Task 9B.2 design review, issue 2)**:
    - update drift: the areas of its drifted paths (`attribute_changes` of class `drifted`, `drifted_converged` or `drifted_and_config_changed` whose assessment is not `noise`). Area `tags` when the first path element is `tags`, else `other`. With no such path, the area is `other`.
    - deletion drift: `existence_delete`. Create drift: `existence_create`. Replace drift: both.
    - A group is capable for an area per the table below. `sole` / `latest` need one group capable for **every** relevant area.
    - A known table operation that is capable only for areas that did not drift (e.g. a tags write when only `other` drifted) is listed and has no effect.
  - **Tags family** (drifted path starts with `tags`): the operation `Microsoft.Resources/tags/write`. Its rows may sit on `<id>` (`exact`) or `<id>/providers/Microsoft.Resources/tags/default` (`extension`) and are grouped by `correlationId` (the verified shape).
  - **Any attribute family** (areas `tags`, `other`, `existence_create`): the resource's own lifecycle write `<namespace>/<type>/write` on exactly `<id>` (as Task 7.2).
  - **Deletion** (area `existence_delete`): `<namespace>/<type>/delete` on exactly `<id>`.
  - **Group key**: (`correlationId`, case-folded operation name) over the target's `exact` and `extension` rows; an event without a correlationId is a group of its own.
  - **Unclassified**: any other successful or unresolved Administrative write/delete/action group on exactly `<id>` or on one of its verified extensions (`extension` relation). It is listed, and in the window it makes the verdict `ambiguous`.
  - **Never decide**: operations on other resources (for a resource-group target, the resources it contains), on ARM child resources or on unverified extension types (all `descendant`). They are counted and named by operation only. The statement mentions recorded child operations when they exist.
  - **Table growth**: a new entry needs a recorded real-Azure shape check. Unverified shapes may be fixture-tested but stay out of the table.
- **G7 — Timing model**:
  - **Observation window** = [`run.started_at`, `run.finished_at`] of the detection run's plan evidence (Terraform's refresh happens inside it). Skew = **60 s**.
  - **Operation group interval** = [first row, last Succeeded row] (or last row when nothing succeeded).
  - **Classification**: `before_observation` if the group ends before `started_at − 60 s`; `after_observation` if it starts after `finished_at + 60 s`; otherwise `during_observation`.
  - **Reported separately**: operation start and end (event time), availability (`submissionTimestamp`), observation window, plan timestamp, and the last-in-sync observation (detection times).
- **G8 — Settling, redesigned**:
  - A recorded positive finding needs no settling.
  - Completeness matters only for `sole_capable_operation`, `no_capable_operation_found` and the deletion rule.
  - The first query runs no earlier than observation **end** (`run.finished_at`) + **M = 10 min** *(amended 2026-10-04, Task 9B.2 design review, issue 3: measured from the end, so every `during_observation` event has at least M to be ingested)*.
  - If any queried drifted resource has no capable operation, re-query every **2 min** until `run.finished_at` + **C = 20 min**.
  - Recorded completeness: `queried_at`, M, C, the poll count and the maximum observed `submissionTimestamp − eventTimestamp`.
  - **Ownership (amended 2026-10-04, Task 9B.1 design review)**:
    - Each poll is one collection. The collector (Task 9B.1) never sleeps or polls. It records `queried_at`, `not_before` and the maximum observed ingestion delay of that collection, and refuses a query whose `queried_at` is before `not_before` (input failure `query_before_not_before`).
    - Waiting, the poll loop, the poll count and the investigation's completeness record belong to Task 9B.2, which decides after each collection whether a drifted resource still lacks a capable operation.
  - Completeness-dependent statements say "among events available at `<queried_at>`".
  - The deletion rule's "settled" check is `queried_at ≥ run.finished_at + M` (G5).
  - These values replace Task 7.1's 20-minute `settled_until` margin and Task 7.2's ±5-minute detection skew / P5 rule (not R7's ±5-minute overlap window, G5). M, C and the skew were accepted as recommended (2026-10-04); changing them needs user approval.
- **G9 — Last-in-sync anchor (resolves Task 7.2 blocker B1)**:
  - **Definition**: the latest earlier valid drift report of the same workflow and environment, within artifact retention (≤ 30 days, ≤ 50 runs examined), in which the address was `in_sync`.
  - **Trust checks**:
    - the run belongs to this repository's `drift-detection.yml`, on head branch `main`, with event `schedule` or `workflow_dispatch`;
    - the report validates as `DriftReport` with `outcome: succeeded` (amended 2026-10-05, Task 9B.4A: as the **public** drift report contract, since candidates are public artifacts; older internal-format artifacts are `report_invalid`);
    - `run.run_id` is bound to that run id and attempt;
    - the environment is equal;
    - its `run.finished_at` is before this run's `run.started_at`.
    - **Added (2026-10-04, Task 9B.2 design review, issue 5)**:
      - its workflow run id differs from the current run's, which excludes every attempt of the current run;
      - its repository equals the current repository;
      - its plan timestamp is earlier than the current plan timestamp;
      - at most **50** candidates are examined (any beyond are rejected as `candidate_limit`);
      - every rejected candidate is recorded with a fixed reason code.

      These checks can only make the anchor older, which only adds candidates; they never make `sole` more likely.
    - **Candidate input (user-approved 2026-10-04, rule detail 6)**: a directory (written by Task 9B.5's fetch script) whose candidates are the immediate subdirectories containing a `run.json`.
      - `run.json` is a strict object `{id, run_attempt, repository, workflow_path, head_branch, event}`. The candidate's `drift_report.json` sits beside it.
      - Any other entry (a file, or a subdirectory without `run.json`) is not a candidate: it is recorded as `not_a_candidate`, does not count toward the limit and is never read as a report.
      - Candidates are examined in ascending directory-name order (deterministic). The first 50 are examined; the rest are rejected as `candidate_limit`.
    - **Anchor fetch (user-approved 2026-10-05, Task 9B.5 design review)**: `scripts/fetch_prior_drift_reports.py` writes that directory.
      - **When**: only when `drift_detected == 'true'`. A no-drift run has no drifted address to anchor; the fetch is skipped and `investigate` runs without `--anchors`.
      - **Which runs**: `GET /repos/{repo}/actions/workflows/drift-detection.yml/runs?branch=main&status=completed&per_page=100` (one page). Kept: `event` ∈ {`schedule`, `workflow_dispatch`}, `head_branch == main`, not the current run id, created within the last 30 days (artifact retention). At most the newest **50**, equal to G9's limit, so `candidate_limit` never arises from the fetch.
      - **Downloads**: only the non-expired artifact named exactly `drift-report-<id>`; zip ≤ 10 MB; only `drift_report.json` is extracted, as a single regular file (no paths, no symlinks), ≤ 10 MB; 30 s per request; up to 3 retries on 5xx/429.
      - **Layout**: each candidate is written to `<dir>/run-<id>-<attempt>/` as `run.json` (`{id, run_attempt, repository, workflow_path, head_branch, event}` from the API; attempt = the run's latest) plus `drift_report.json`.
      - **Failures (decision 2)**: a listing failure (authentication, permission, 5xx after retries, invalid JSON, timeout) → exit ≠ 0 → investigation failure `anchor_fetch_failed`. Fail closed: `investigate` is **not** run without the required fetch, and nothing is uploaded.
        - A single candidate whose artifact is missing, expired, oversized, corrupt or fails to download still gets its `run.json`, without a report. `investigate` records it as `report_invalid` (visible in the public anchor counts); losing a candidate only makes verdicts more conservative.
      - **Output**: counts and fixed skip reasons only.
  - **Deletion anchor (amended 2026-10-04, issue 6)**: for a deletion, the same anchor is accepted as existence anchor B (`prior_detection_run`, G5).
  - **Window**: from anchor `run.started_at − 60 s` (conservative: it can only add candidates) to the observation start.
  - **No anchor**: lookback window (default 30 days, max 89); `sole_capable_operation` is then impossible.
  - **Per-resource anchors, run-level query window (amended 2026-10-04, Task 9B.1 design review)**:
    - The anchor is chosen **per drifted address**, while the Activity Log is queried once per resource group for the whole run.
    - Task 9B.2 therefore computes one run-level `window_start` = the earliest of every drifted address's window start (its anchor start, or the lookback start for an address without an anchor), never earlier than `queried_at − 89 days`, and passes it to the collector.
    - Task 9B.2 then narrows each address to its own anchor window from that one evidence document.
- **G10 — CI placement and isolation (mirrors Task 10.1 D5)**:
  - **Placement**: new steps in `plan-and-analyze` after `Upload Drift Report` and **before** the cost step (the cost step runs `az logout`). They run only for a valid drift result (`drift_detected` literal `true`/`false`).
  - **Install**: `.[azure]` in a separate venv, exactly pinned through `ci/azure-constraints.txt`.
  - **Status capture**: the step records its status and a fixed failure code as outputs and exits 0, the same documented exception as Task 10.1 D5.
  - **Exact names and boundaries (user-approved 2026-10-05, Task 9B.5 design review)**:
    - `plan-and-analyze` steps in order:
      1. `Generate Plan Evidence` (unchanged);
      2. `Analyze Drift`;
      3. `Upload Drift Report`;
      4. **`Drift Investigation`** (`id: investigation`): one step running `scripts/investigation_analysis.sh` (always exits 0);
      5. **`Upload Drift Investigation`** (`id: investigation_upload`);
      6. `Infracost Cost Estimate` (its `az logout` stays after the investigation);
      7. `Upload Infracost Report`.
    - New `plan-and-analyze` outputs: `investigation_status`, `investigation_failure`, `investigation_detail`, `investigation_publishable`, `investigation_upload_outcome`.
    - `Drift Investigation` env:
      - `GH_TOKEN` (used only by the anchor fetch);
      - `DRIFT_ENGINE_PIPELINE_PRINCIPAL: ${{ secrets.AZURE_CLIENT_ID }}` (compared on the runner, never written; G13);
      - the repository, the run id and the paths.
    - **No step-level `timeout-minutes` on `Drift Investigation`**: a step timeout would fail `plan-and-analyze`, and the issues and cost jobs (whose `if:` adds an implicit `success()`) would be skipped. The script bounds itself instead: `timeout 1500` around `investigate`, `timeout 300` around the anchor fetch.
    - **Runner isolation**: pinned venv `${RUNNER_TEMP}/investigation-venv`; the restricted investigation and evidence live in `${RUNNER_TEMP}/investigation/restricted/` (0700). Only `${RUNNER_TEMP}/investigation/public/drift_investigation.json` is uploaded.
    - **Job `investigation`**: `name: "Drift Investigation (<env>)"`, `needs: [preflight, plan-and-analyze]`, `if: !cancelled() && drift_detected ∈ {'true','false'}`, `permissions: contents: read`, `timeout-minutes: 10`. Steps:
      1. `Download Drift Report`;
      2. `Download Drift Investigation` (if the upload succeeded);
      3. `Verify Drift Investigation` (`investigation-check --public … --report <downloaded public drift report>`);
      4. `Investigation Summary` (counts only);
      5. **`Require Investigation Success`** (last, so the summary still renders): it fails unless `investigation_status == succeeded`, `investigation_upload_outcome == success` and verification passed. **Amended (2026-10-09, G18)**: `investigation_status == incomplete` with a successful upload and verification also passes, with a `::warning::`. On a no-drift run (`drift_detected == 'false'`) an investigation that did not run passes (not required); on a drifted run it fails.
  - **Upload**: `drift-investigation-<run_id>` (public file only, 30 days; `if: investigation_publishable == 'true'`, `if-no-files-found: error`, `overwrite: true`) uses `continue-on-error: true` as a second documented exception. This amends Task 10.1 D5's "no other step may use `continue-on-error`".
  - **Job settings for `plan-and-analyze`**: permissions `id-token: write`, `contents: read`, `actions: read` (anchor lookup); timeout 30 → 45 min.
  - **Public drift report (amended 2026-10-05, P1/P3)**: `Upload Drift Report` uploads only the public drift report (Task 9B.4A) and `detection_run.json`. A failed projection or verification means `analyze` exit 70, UNKNOWN and no upload, never the internal report.
  - **New `investigation` check job**: `contents: read` only, no Azure, no secrets. It downloads `drift-investigation-<run_id>` and `drift-report-<run_id>` and binds the investigation to the downloaded **public** drift report (amended 2026-10-05, Task 9B.5 item 3). It fails the run on any investigation failure, while `drift_detected`, the drift report and artifact, `issues`, `report` and `cost` are unaffected. **Amended (2026-10-09, G18)**: an `incomplete` investigation is a finding, not a failure.
  - **Logs and step summaries**: counts and fixed codes only.
- **G11 — Public privacy profile** (every public artifact, workflow log, step summary and LLM input):
  - **Never**: caller identity in any form (UPN, name, object ID, app ID, hash), subscription/tenant IDs, ARM resource IDs, event/correlation/operation IDs, IP addresses, claims, HTTP request data, raw Activity Log content or free text (`description`, `properties.*`).
    - **Clarified (2026-10-05, user-approved P2)**: "IP addresses" means sensitive Activity Log / caller identity data (e.g. a caller's client IP or claims). IP addresses, CIDRs and URLs that are Terraform configuration values are Terraform evidence and may appear in the public drift report and the AI report (e.g. an NSG rule opened to `0.0.0.0/0`).
    - This does not relax anything else: ARM/resource IDs, subscription/provider paths, GUIDs and UPN/email-like identities stay forbidden in every public artifact, including inside Terraform values, where they are `withheld` (Task 9B.4A).
  - **Allowed**:
    - Terraform address and type;
    - operation name, status, category and event phase;
    - relation (`exact` / `extension`) and resource scope kind;
    - timestamps (event, availability, observation, anchor);
    - caller type (G13), client application (G13) and `pipeline_identity` (G13);
    - verdict, property link and attribution status with reason codes;
    - completeness, and counts.
  - Public operation references are ordinals (`op-<n>`).
  - Raw evidence and the restricted investigation exist only on the runner (0600) and are never uploaded or printed. An allowlist plus a fail-closed leak scan (GUID, `@`, IPv4/IPv6, `/subscriptions/`, `/providers/` path, URL) guard every public investigation file.
  - **Public drift report profile (added 2026-10-05, P1/P2, Task 9B.4A)**: the internal drift report is a restricted runner-only document; anything leaving the runner uses its public projection.
    - Values of the withheld classes (ARM/resource IDs, subscription/provider paths, GUIDs, UPN/email-like identities) become typed `withheld` views.
    - Structural fields are never rewritten: an identifier in an address or other structural field fails the projection (P3).
    - An independent verification and a fail-closed identifier scan guard it. Configured IPs/CIDRs and URL values are allowed (clarification above).
    - **Hash contract**: the only drift report hash in any public artifact is the canonical SHA-256 (sorted keys, compact separators, UTF-8) of the **public** drift report. The internal report and any hash of it are never public.
  - **Public investigation schema (user-approved 2026-10-04, Task 9B.3 design review, decision C)**: strict and allowlist-based; any field not listed is dropped.
    - **Top level**:
      - `public_version`, `rules`, `outcome`, `failure`;
      - `exposure` (`caller_identity`, `resource_id`, `event_id`, `correlation_id` all `withheld`; `who_path: local_only`);
      - `binding` (run id, plan timestamp, **public** drift report SHA-256 (amended 2026-10-05), evidence outcome, observation window);
      - `completeness`;
      - `anchors` (examined count, accepted count, rejected **counts by reason only**).
    - **Per resource**: address, drift action, relevant areas; window (kind, start; for an anchor its GitHub run id, plan timestamp, started/finished and report SHA-256); verdict, reason, `decisive_operation`, property link and reason, `unreadable_events_in_scope`, descendant counts and operation names.
    - **Per operation**: `op_id`, operation name, outcome, relations, start, end, `available_at`, timing, `in_window`, role, capable areas, `caller_status`, `caller_type`, `client_app`, `pipeline_identity`, the number of attached events.
    - **Automated events**: ordinal `auto-<n>`, operation name, category, timestamp, timing, `in_window`, signal.
    - **Deletion rule**: status, reason, rule, claim, anchor kind/time/run id; no caller, and counts instead of event-id lists.
    - **Actor attribution**: status, rule, claim; no caller.
    - **Never public**, even indirectly:
      - `evidence_sha256` or any hash of the restricted evidence or investigation (they hash content that contains callers);
      - any hash of the internal drift report (it can contain ARM IDs; amended 2026-10-05, Task 9B.4A);
      - correlation ids and event ids;
      - anchor candidate directory names and per-candidate rejection detail.
    - The anchor's GitHub run id and report SHA-256 are safe references: they derive from public drift artifacts (public drift reports, from Task 9B.4A on).
    - `op-<n>` / `auto-<n>` are per-resource ordinals in a deterministic order (start, end, then event ids as tie-break) and encode no identifier.
  - **Restricted-data CLI hardening (user-approved 2026-10-04, decision D)**:
    - In GitHub Actions (`GITHUB_ACTIONS=true`), `drift-engine activity-logs`, `attribute` and `investigate` refuse to write their restricted document to standard output (usage error, exit 2); `--output` is required there. Local use is unchanged.
    - For these commands and `who`, an unexpected error prints only the exception type and a fixed message, never `str(exc)` (a validation error on restricted data can echo input values).
- **G12 — Restricted WHO path: local-only**:
  - **Command**: a maintainer runs `drift-engine who` locally (own `az login`, read-only). Its inputs are the downloaded public investigation file and a local `terraform show -json` / plan JSON that maps addresses to ARM IDs.
  - **Matching**: it re-queries a narrow window (each public operation's start/end ± 1 s), re-normalizes, and requires exactly one operation group that matches operation name, timestamps, status, relation, caller type and client application. Then it prints the recorded caller and writes `who_evidence.local.json` (0600) under `.artifacts/`, never committed.
  - **Limit**: Activity Log retention (90 days).
  - **Details (user-approved 2026-10-04, Task 9B.3 design review, decisions A, E, D)**:
    - **Collection**: `activity_logs.collect_window(source, targets, start, end)` is the local historic collection entry point, a plan-independent bounded window over the same scope query, normalization and safeguards. `collect_evidence()` is unchanged.
    - **Matching**: exact equality of the group's start and end (microseconds), operation name, outcome, relations, caller type and client application. The ±1 s is only the query window.
    - **Inputs**: the public file (contract and leak scan), optionally `--report` (must match its binding), and either `terraform show -json` state (`values`, child modules included) or plan JSON (`prior_state.values`) for address → ARM ID.
    - **Errors**: fixed codes `no_match`, `multiple_matches`, `retention_exceeded`, `binding_failed`, `query_failed`; none prints a caller.
      - `binding_failed` covers: the public file fails its contract or leak scan, `--report` does not match its binding, or an address has no ARM ID locally.
    - **Output**: `--output-dir` is required (created 0700 if missing); exactly one file `who_evidence.local.json`, written 0600 and atomically, refusing a symlinked target. The recorded caller is printed to standard output.
    - **Local only, enforced**: `who` refuses to run under `GITHUB_ACTIONS=true`.
    - **Module**: the WHO logic lives in `src/drift_engine/who.py`.
  - **Rejected**: an encrypted restricted artifact. Its weakness is public ciphertext of personal data protected by one long-lived maintainer key that can't be revoked for already-published artifacts; revisit only by user decision (Phase 12).
- **G13 — Caller type, client application, pipeline identity** (derived on the runner; raw claims never stored):
  - **`caller_type`**:
    - `idtyp = user` → `user` (verified);
    - `idtyp = app` → `service_principal`, or `managed_identity` when an `xms_mirid` claim exists (fixture-only, unverified);
    - otherwise `unknown`.
  - **`client_app`**: allowlist of verified first-party applications only, `azure_portal` and `azure_cli` (both verified 2026-10-03/04). Any other app ID → `other_application`; missing → `unknown`. A new entry needs recorded evidence. `azure_cli` also covers Terraform run locally with CLI authentication; the report says so.
  - **`pipeline_identity`**: `true` / `false` when the event's principal can be compared on the runner with the running job's own principal (never written); otherwise `null`.
- **G14 — AI boundary**:
  - **Module boundary (user-approved 2026-10-04, decision F)**: `drift_engine.investigation_public` is the only investigation-related module `ai_engine` may import. An AST test forbids any `ai_engine` import of `investigation`, `who`, `activity_logs` or `attribution`; a subprocess test checks that importing `investigation_public` loads none of them.
  - **LLM input**: only the sanitized deterministic investigation model (G11 fields plus the Terraform evidence already allowed, taken from the **public** drift report from Task 9B.4A on); never raw Activity Log data, identities or IDs.
  - **Module boundary addendum (2026-10-05, Task 9B.4A)**: `ai_engine` may also import the public drift report module (`drift_engine.report_public`); the allowlist test is extended accordingly.
  - **Module boundary addendum (2026-10-11, Task 10.3)**: `ai_engine` may also import `drift_engine.cost` (Task 10.2), which loads no restricted module; the allowlist test is extended accordingly (see Task 10.3).
  - **CI**: the LLM stays disabled (`AI_LLM_PROVIDER=none`, CLI refusal unchanged). Enabling a real LLM is a later, separate user decision and not part of Phase 9B.
  - **Limits on the LLM**: it may explain consistency, impact and risk. It may not change a verdict, property link, attribution, recommendation, severity or option, and may not cite an operation or timestamp absent from the model.
  - **Guards** reject actor naming, identity-like strings and claims stronger than the deterministic verdict (e.g. "X changed tags.owner", "this operation caused the drift").
- **G15 — Deterministic fallback is mandatory**: without an LLM the report fully answers WHAT, WHEN, WHO (as far as G11 allows) and correlation, plus the recommendation, using fixed versioned statement templates. An LLM only adds labelled interpretation.
- **G16 — AI report v2 and recommendation policy v1**: see the outline below. Report v2 replaces v1's constant `attribution.pending`. The policy replaces "options are never ranked or recommended" (Task 6.6) and adds a recommended option or an explicit "human decision required". Approval stays required and nothing executes.
- **G17 — Unchanged**:
  - Terraform configuration and RBAC (Reader covers Activity Log reads);
  - the drift report contract and `drift-engine analyze`. **Amended (2026-10-05, P1)**: this means the **internal** drift report contract and `analyze`'s internal output and Phase 3/4 semantics. `analyze` gains `--public-output`, and the published artifact contract becomes the public drift report (Task 9B.4A);
  - `drift_detected`/`drift_status` semantics;
  - GitHub issues (Phase 8 profile);
  - `security-scan.yml`, `terraform-auth-test.yml`;
  - remediation command catalogue and approval/execution constants;
  - the no-autonomous-apply principle.
- **G18 — CI result policy (user-approved 2026-10-09, Task 9B.5 design review Q1/Q2; deliberately amends decision 1 of 2026-10-05; revised and 🔒 LOCKED 2026-10-09 with the "investigation required" scope below. Changing G18 needs user approval, G1)**:
  - **Principle**: drift detection is a successful finding, not a CI failure. The run's red/green status reflects process validity only. `drift_detected` comes from the classification alone. It is never derived from the run conclusion or from any job other than `plan-and-analyze`.
  - **Terraform plan exit code 2** means *pending changes*, not necessarily drift (spec §4.2): a configuration-only or output-only change also exits 2, and converged drift exits 0. The classification (`drift-engine analyze`) alone decides drift. Exit 2 is never mapped to a failure or to `drift_detected=unknown`.
  - **Result matrix** (`drift-detection.yml`):

    | Case | `drift_detected` | Drift report artifact | Jobs | Run |
    | --- | --- | --- | --- | --- |
    | No drift: valid classification, `has_drift: false` (plan exit 0, or 2 for a config/output-only change) | `false` | uploaded | `plan-and-analyze`, `issues`, `cost`, `investigation`, `report` succeed | **success** |
    | Drift: valid classification, `has_drift: true` (plan exit 2, or 0 for converged drift) | `true` | uploaded; drift visible (`::warning::`, `drift_status=detected`, run summary, issues, public report) | as above; `investigation` passes for `succeeded` or `incomplete` | **success** |
    | Detection/process error: auth, init/validate, plan exit 1 or other, `show`, integrity gate, lock-file change, `analyze` ≠ 0, public projection failure, invalid report | `unknown` (never `false`) | not uploaded | `plan-and-analyze` fails; `issues`, `cost`, `investigation` skipped; `report` shows FAILED | **failure** |
    | Investigation `incomplete` (some drifted resources `not_investigated`), upload and verification succeeded | unchanged | unchanged | `investigation` **succeeds with a `::warning::`** | success (unless another job fails) |
    | No drift, investigation intentionally skipped (it did not run: empty `investigation_status` on a `drift_detected=false` run) | `false` | uploaded | `investigation` **succeeds** ("not required: no drift" in its summary) | success (unless another job fails) |
    | Investigation `failed` (any failure code, including failed-but-bindable uploaded documents, on a drifted or a no-drift run), or it ran and its upload or verification failed (also for `incomplete`) | unchanged | unchanged | `investigation` **fails** | **failure** |
    | Investigation required but never ran (empty `investigation_status` on a `drift_detected=true` run) | `true` (unchanged) | unchanged | `investigation` **fails** | **failure** |
    | Cost failure (Phase 10 D5) or issues failure (Phase 8) | unchanged | unchanged | that job fails | **failure** |

  - **Investigation required (revision 2026-10-09)**:
    - An investigation is **required** only for a drifted run (`drift_detected` is the literal `true`). There it must run; if it never ran, the `investigation` job fails.
    - For a no-drift run (`drift_detected` is the literal `false`), the investigation is **not required**. If it is skipped (did not run), the `investigation` job passes. If it does run, its result is judged by the same rows as on a drifted run (`succeeded` passes; `incomplete` passes with a warning; `failed`, or a failed upload or verification, fails), because a run that was started and failed is a process error.
    - The current 9B.5 design still runs the investigation on no-drift runs (no anchor fetch, no Azure query, a `complete` document is uploaded), and the 9B.5 real CI proof verifies that path. The skip rule therefore covers an intentional skip, now or in a later design, and never needs a skip to happen.
    - Why the skip rule cannot hide a failure in today's workflow: on a `'false'` run, `Drift Investigation` is skipped only when `Upload Drift Report` did not succeed, and that already fails `plan-and-analyze` and the run. A crash of the step script is mapped to `failed` / `script_error`, never to an empty status.
    - `drift_detected=unknown`: the `investigation` job does not run at all; the run has already failed in detection.
    - `Require Investigation Success` may read `drift_detected` **only** to decide whether an investigation was required. Drift (`'true'`) never by itself fails it, or any other job.
  - **Separation**:
    - An investigation outcome never changes `drift_detected`, `drift_status`, the drift report or artifact, `issues`, `cost` or `report`.
    - A failed or missing investigation is never "no drift". The AI report shows `not_investigated` / `investigation_failed` for every drifted resource (D3).
    - `ai-analysis.yml` stays a separate workflow and decides validity from the drift report artifact, not from the source run's conclusion (Task 9A.1 D3/D4).
  - **Unchanged by G18**:
    - `scripts/investigation_analysis.sh` and its status vocabulary: `incomplete` keeps the fixed code `investigation_failure=incomplete`, which no longer fails the job;
    - the uploads and the publishable rule (decision 1's "uploaded unchanged");
    - the drift, issues, cost and report jobs.
  - **Owner**: Task 9B.5 (implementation and tests); real-run proof of the drift row in Task 9B.6.

#### Data flow (target)

1. `plan-and-analyze` (OIDC, Reader): `plan.json` and the manifest → `drift-engine analyze --public-output` (amended 2026-10-05, Task 9B.4A):
   - writes the internal report (runner only);
   - projects, verifies and scans the public report;
   - upload `drift-report-<run_id>` (public report + `detection_run.json`). A projection failure gives UNKNOWN and no upload.
2. `drift-engine investigate`, in the same job (internal report + `plan.json`; binds the public investigation to the **public** report hash):
   1. targets (address → ARM ID, drift action, drifted path families) from `plan.json`;
   2. observation window from the manifest/report;
   3. last-in-sync anchor from earlier public drift reports (G9; fetched only for a drifted run, fail-closed `anchor_fetch_failed`);
   4. Activity Log query and normalization v2 with settle/poll (G8);
   5. correlation v2 → restricted investigation (runner only);
   6. public projection (`investigate --public-output`);
   7. verification (projection ⊂ restricted ⊂ evidence) and leak scan, all before the public file is written.
3. Upload `drift-investigation-<run_id>` (`drift_investigation.json`) when publishable (succeeded, incomplete, or failed but bindable; decision 1). Then the cost step (bound to the public drift report).
4. `investigation` check job: downloads the public investigation and the public drift report, runs `investigation-check` against that report (amended 2026-10-05, Task 9B.5 item 3), and writes a counts-only summary. It passes for `succeeded`, passes with a warning for `incomplete`, passes when no investigation ran on a no-drift run (not required), and fails otherwise (G18). Before this, still in `plan-and-analyze`, `scripts/investigation_analysis.sh` has already checked the same binding against `${RUNNER_TEMP}/drift/drift_report.json` before upload (item 2).
5. `ai-analysis.yml` (`workflow_run`, no Azure):
   - downloads and binds the public drift report and the investigation;
   - runs AI engine v2: deterministic WHAT/WHEN/WHO/correlation, fallback narrative, recommendation policy, and LLM interpretation only when enabled (never in CI in Phase 9B);
   - uploads `ai-analysis-report-<run_id>` (`ai_analysis_report.json` / `.md`, report v2).
6. Maintainer, locally: `drift-engine who` gives the recorded identity, kept local only (G12).

#### Report v2 outline (locked; field names finalised in Task 9B.4)

- **`report_version: "2"`, `provenance`**: run id; **public** drift report (amended 2026-10-05) and investigation canonical SHA-256; versions (report, investigation, capable-operations table, statements, recommendation policy); LLM record (status, provider, `evidence_sent`).
- **`investigation`**: status; window (anchor or lookback); completeness (G8); exposure (`caller_identity: withheld`, `resource_id: withheld`, `event_id: withheld`, `who_path: local_only`).
- **`resources[]`**, per drifted resource:
  - `what` (basis `terraform_evidence`): classification, severity, changes with path, expected, actual. Taken from the **public** drift report (amended 2026-10-05, Task 9B.4A): withheld-class values appear as `withheld` views;
  - `operations[]` (basis `activity_log_evidence`): `op-<n>`, operation name, status, relation, phase, start, end, availability, timing (G7), capable family or `unclassified`, caller type, client app, `pipeline_identity`, `caller_identity: withheld`;
  - `when`: the decisive operation's start/end and availability, last-in-sync observation, observation window, plan timestamp, gap in seconds;
  - `who`:
    - `recorded_caller` {status `recorded` | `not_recorded` | `multiple_operations` | `not_investigated`, type, client app, `pipeline_identity`, identity `withheld`}. It describes the **decisive operation**, which exists only for `sole_capable_operation` / `latest_capable_operation` (or a confirmed deletion). `ambiguous` with several candidate operations is `multiple_operations`, and each operation's caller data stays in `operations[]` *(amended 2026-10-04, Task 9B.2 design review, issue 9)*;
    - **Amended (2026-10-04, Task 9B.4 design review, user-approved D1)**: the status set is `recorded` | `not_recorded` | `multiple_operations` | `no_decisive_operation` | `not_investigated` (plus `not_applicable`, D2).
      - `multiple_operations` is retained for `ambiguous` with two or more candidate operations.
      - `no_decisive_operation` (with a `candidate_operations` count) covers `no_capable_operation_found` and `ambiguous` with fewer than two candidates.
      - `not_recorded` carries a reason: `caller_missing` or `caller_inconsistent` (the decisive operation's public `caller_status`).
    - `actor_attribution` {status `confirmed` | `not_confirmed_by_available_evidence`, rule};
  - `correlation`: verdict (G4), reason, property link (G5), counts (capable, unclassified, child, after-observation), fixed statement text;
  - **Non-drift changed resources (amended 2026-10-04, Task 9B.4 design review, user-approved D2)**: `config_change`, `resource_added` and `resource_removed` resources (no `drift_actions`) stay in `resources[]` with `investigation_scope = not_drift`. Their investigation, `when`, `who` and `correlation` are `not_applicable` (no verdict), and their existing remediation options are preserved. Drifted resources have `investigation_scope = drift`.
  - **Failed investigations (amended 2026-10-04, Task 9B.4 design review, user-approved D3)**: a bindable public investigation with `outcome: failed` gives report-level `investigation.status = failed` (with its failure stage and reason), and every drifted resource `not_investigated` with reason `investigation_failed`. An unbindable one (`report_invalid` / `report_mismatch`: no drift report hash) cannot produce an AI report (exit 1, nothing written); Task 9B.5 must fail such an investigation before upload.
  - **`gap_seconds`**: `observation.started_at − decisive_operation.end`, only when a decisive operation exists; otherwise the fixed wording "not confirmed by available evidence".
  - `analysis`: deterministic narrative (statement templates) plus optional AI interpretation labelled `inference`;
  - `remediation`: options (unchanged catalogue) plus `recommendation` {option or `null`, decision `recommended` | `human_decision_required` | `no_options`, policy rule, rationale code, notes}, approval required, execution not allowed.
- **Run-level**: the five Phase 6 analysis sections (inference); `limitations` (fixed, including "Activity Log records operations, not property values"; "caller identities are withheld in public reports; WHO is available locally via `drift-engine who`"; the `azure_cli` channel caveat; completeness caveats).
- **Markdown order**: Summary → What changed → Recorded Azure operations → When → Who → Correlation → Analysis → Recommendation & options → Limitations → Provenance. Every unprovable fact renders as "not confirmed by available evidence".

#### Recommendation policy v1 (deterministic, versioned; first matching rule wins)

1. **R0**: no options → decision `no_options`.
2. **R1**: any option is `human_decision_required` (ambiguous, `drift_and_config_change`, `undetermined`) → no recommended option; decision `human_decision_required`, rationale `ambiguous_intent`.
3. **R2**: the plan-direction option is destructive or `data_not_restored` → no recommended option; `human_decision_required`, rationale `plan_direction_destructive`.
4. **R3**: classification `converged_drift` → recommend `refresh_state_only`, rationale `record_converged_state`.
5. **R4**: otherwise → recommend the plan-direction option, rationale `terraform_is_source_of_truth`. If `accept_remote_value` exists, add the fixed note: "If the recorded Azure change was intended, choose accept_remote_value instead and update the configuration."

Investigation verdicts and caller data never change the recommendation in v1. Every recommendation keeps `approval.required = true`, `execution.allowed = false`, `automatic_apply = false`.

#### Phase 9B end-to-end acceptance (verified in Task 9B.6)

The user adds a tag to the Terraform-managed `aitdd-dev-main-rg` in the Azure Portal, with a valid in-sync drift report available within retention, then dispatches drift detection. The final public AI report v2 shows:
- **WHAT**: `external_drift` on `tags.<key>`, expected absent, actual value.
- **Operation**: `Microsoft.Resources/tags/write`, Succeeded, relation `exact`/`extension` pair under one group.
- **WHEN**:
  - operation start/end matching the Azure record to the second, with availability;
  - last-in-sync observation;
  - observation window and plan timestamp, labelled separately;
  - timing `before_observation`.
- **WHO**: `recorded_caller` type `user`, client `azure_portal`, `pipeline_identity: false`, identity withheld; actor attribution `not_confirmed_by_available_evidence`.
- **Correlation**: `sole_capable_operation`, property link `inferred_not_provable`, completeness recorded.
- **Analysis**: deterministic narrative (no LLM in CI).
- **Recommendation**: `restore_declared` (R4) with the accept-remote note, approval required.

In addition:
- the drift run concludes **success** with `drift_detected=true` (G18);
- the drift result is unchanged by the investigation;
- the public files pass the leak scan;
- `drift-engine who` locally reproduces the identity Azure recorded.

#### Task 9B.1 — Activity Log Evidence v2 & Collection Timing
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Objective**: Extend the Activity Log collector to evidence v2 with the investigation fields required by G7, G8, G11 and G13, using the verified event shape. Still collection only (no correlation).
- **Dependencies**: Tasks 7.1–7.3 (implementation), Phase 9B locked decisions G1–G17
- **Files/Areas**: `src/drift_engine/activity_logs.py`, `src/drift_engine/cli.py` (`activity-logs` options), `tests/test_activity_logs.py`, new `tests/fixtures/activity_log/` (sanitized fixtures derived from the verified shape: synthetic GUIDs, `user@example.invalid`, no real IPs; test inputs may use only documentation-range addresses `192.0.2.0/24`, `198.51.100.0/24`, `203.0.113.0/24` and `2001:db8::/32` to prove IPs are dropped, and no IP ever appears in an output), `src/drift_engine/__init__.py` (docstring)
- **Amendment (2026-10-09, Task 9B.5 CI Activity Log authentication fix, user-approved)**: the evidence's per-scope `error` gains one optional, runner-only field `auth_reason`. It is present only with `authentication_failed`, has fixed values, and records no exception text. `evidence_version` stays `"2"`; documents without an authentication failure are unchanged. `AzureMonitorSource` requests the Azure Resource Manager audience Azure CLI caches at login (`https://management.core.windows.net//.default`). The `AzureCliCredential`-only rule, the GET allowlist, the limits and the existing fixed codes are unchanged. Owned and specified by Task 9B.5; the record below is historical.
- **Acceptance Criteria**:
  - [x] **Evidence v2 fields**: `evidence_version: "2"` with per event:
    - `event_phase` (`begin` / `end` / `unknown`, from `eventName`);
    - `caller_type` (G13);
    - `client_app` (G13, verified allowlist only);
    - `pipeline_identity` (`true` / `false` / `null`, from an optional comparison principal supplied at collection time and never written);
    - `submission_timestamp` kept.

    Raw claims, `httpRequest`, `authorization`, `properties` and `description` are still never stored; `caller` is kept only in this restricted evidence.
  - [x] **Relations**: `exact`, `extension` (verified extension types only, G6: v1 `<id>/providers/Microsoft.Resources/tags/default`), `descendant` (everything else below a target, including a resource group's contained resources such as `Microsoft.Resources/deployments`). The verified Started row (`…/tags/default`) is `extension` and the Succeeded row (`<rg-id>`) is `exact`, both on the resource-group target.
  - [x] **Window and timing**:
    - The collector accepts an optional run-level `window_start` (G9: the earliest per-resource anchor or lookback start, computed by Task 9B.2), else the lookback start. It also accepts an optional `not_before`.
    - It records `basis` (`lookback` / `explicit`), `queried_at`, `not_before` and the maximum observed ingestion delay (`submissionTimestamp − eventTimestamp`).
    - A collection whose `queried_at` is before `not_before` issues no query and fails with `query_before_not_before`. The collector never sleeps or polls; the poll loop, poll count and completeness record are Task 9B.2's (G8).
    - **`settled_until` (end − 20 min) stays in evidence v2 as a legacy field.** Task 7.2's `attribution.py` (rule P5, binding window, verifier) still reads it. Task 9B.2 removes it when it re-parameterizes `external_deletion_v1` to G7/G8.
  - [x] **Unchanged from Task 7.1**: security behaviour (read-only GET allowlist, `AzureCliCredential` only, limits, fixed error codes, deterministic rendering).
- **Validation**:
  - [x] Unit tests on sanitized real-shape fixtures: the Started/Succeeded pair, the shared correlation ID, extension and exact relations, `idtyp = user`, Portal and CLI app mapping, `other_application`, missing claims; plus synthetic `idtyp = app` with and without `xms_mirid` (marked unverified).
  - [x] Tests that claims, IPs and request data never reach the output (property-based over all string fields), determinism, window and `not_before` edges, and every existing failure code.
  - [x] Task 7.1 tests updated for v2. Optional, user-approved: a local read-only collection on `aitdd-dev-main-rg` reproduces the verified fields (Execution Rule 10). *(The optional live check was not run: it needs separate user approval. The fixture is derived from the 2026-10-04 real read-only query instead.)*
- **Implementation Notes**:
  - Starts with a design review (field names, the `pipeline_identity` comparison input, the poll interface used by Task 9B.2).
  - **Design review (2026-10-04, user-approved fixes)**: the verified-extension allowlist (G6), the run-level `window_start` (G9), the legacy `settled_until`, the poll and completeness ownership moved to Task 9B.2 (G8), and documentation-range IPs in test inputs.
    - `pipeline_identity` compares `claims.appid` with the pipeline client ID, read from the environment variable `DRIFT_ENGINE_PIPELINE_PRINCIPAL` and never written: `true` on equality (case-insensitive), `false` on a difference, `null` when either side is missing.
    - Only the claims `idtyp`, `appid` and the presence of `xms_mirid` are read; no claim value is stored.
- **Completion Notes**:
  - **Files**:
    - changed `src/drift_engine/activity_logs.py` (evidence v2), `src/drift_engine/cli.py` (`activity-logs --window-start/--not-before`, principal from `DRIFT_ENGINE_PIPELINE_PRINCIPAL`), `src/drift_engine/__init__.py` (docstring);
    - new `tests/fixtures/activity_log/rg_tag_writes.json` + `README.md` (six sanitized real-shape records: the Portal pair and two CLI pairs);
    - `tests/test_activity_logs.py` (v1 expectations updated, 35 new tests); `tests/test_attribution.py` (one fixture expectation: the evidence version string in the duplicate-key case).
    - **Unchanged**: `attribution.py` and its rules, the drift report and schema, `ai_engine`, workflows, Terraform, dependencies.
  - **Evidence v2**:
    - `evidence_version: "2"`;
    - per event `event_phase` (`begin`/`end`/`unknown` from eventName), `caller_type` (`user`/`service_principal`/`managed_identity`/`unknown`), `client_app` (`azure_portal`/`azure_cli`/`other_application`/`unknown`), `pipeline_identity` (`true`/`false`/`null`);
    - new anomalies `claims_missing` (absent claims), `claims_rejected` (not an object), `submission_before_event`;
    - only `idtyp`, `appid` and the *presence* of `xms_mirid` are read: the SDK adapter forwards just these (`xms_mirid` as `true`), no claim value is stored, and the caller stays in this restricted evidence only.
  - **Relations**: `exact` / `extension` / `descendant` through `relation_to`, with `VERIFIED_EXTENSIONS = ("/providers/microsoft.resources/tags/default",)`. The verified Started row is `extension` and the Succeeded row `exact` on the resource-group target. `…/providers/Microsoft.Resources/deployments/*`, locks, `tags/other` and anything below a child resource stay `descendant`. The evidence checks recompute the relation.
  - **Window and timing**:
    - `Window` v2 has `basis` (`lookback`, or `explicit` from `window_start`: rounded down to the second, after end − 89 days and before the end; else `invalid_window_start`) and the legacy `settled_until` (end − 20 min, for Task 7.2 until Task 9B.2).
    - New `collection` block: `queried_at` (µs), `not_before`, `max_ingestion_delay_ms` (whole ms, rounded down, over kept events whose submission time is not earlier) and `ingestion_delay_samples`. It is null exactly for input failures and cross-checked against the window end and the events.
    - New input failures `invalid_window_start`, `invalid_not_before`, `invalid_pipeline_principal`, `query_before_not_before`; each fails before any query.
    - The collector never sleeps or polls.
  - **Behaviour change (intended)**: two copies of one eventDataId that differ only in derived claims are now conflicting duplicates (every copy dropped).
  - **Tests** (session-scratchpad venv, Python 3.13.12, azure-mgmt-monitor 7.0.0, azure-identity 1.26.0, azure-core 1.41.0; no Azure, no credentials):
    - `tests/test_activity_logs.py` **157 passed** (122 Task 7.1 + 35 new: real-shape pair, CLI vs Portal mapping, ingestion delay 111 774 ms, allowlist scan of every string field, determinism under shuffling/paging, identity derivation matrix incl. synthetic `idtyp = app` with/without `xms_mirid` (unverified), pipeline identity, event phase, relation matrix, explicit window bounds, `not_before` edges, contract tampering, CLI options and environment principal never written, SDK adapter over a fake transport with the real-shape records);
    - full suite **1995 passed** (1757 subtests); `drift_engine` coverage **99.94%** (gate 85%; `activity_logs.py` 100%);
    - **6/6 ad hoc mutants caught** (namespace-wide extension, unknown app mapped to the Portal, `not_before` ignored, all claims forwarded, unbounded `window_start`, `pipeline_identity` always true);
    - `unittest discover` OK in the venv (the system Python without pytest fails to import the 14 pytest-only modules, unrelated and pre-existing);
    - `./scripts/validate.sh` passed; gitleaks 8.30.1: no leaks in the changed files;
    - a check against the local raw query output found no real identifier in any changed or new file. The only non-synthetic GUIDs in the fixture are the two public first-party app IDs.
  - **Not done / limitations**:
    - (a) the optional live read-only collection was not run (needs user approval);
    - (b) `service_principal`, `managed_identity` and `pipeline_identity = true` are verified on synthetic claims only; no real service-principal write exists (the CI identity is Reader);
    - (c) tag edits on non-resource-group resources are fixture-only (the `extension` rule is generic over the verified suffix);
    - (d) `settled_until` stays until Task 9B.2.

#### Task 9B.2 — Correlation v2 & Last-In-Sync Anchor
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: `investigate` keeps reading the internal drift report and `plan.json`, and still verifies the report against the recomputed classification. Changes:
  - the public investigation's `binding.drift_report_sha256` becomes the canonical SHA-256 of the **public** projection of that report, recomputed deterministically on the runner;
  - the restricted document may keep the internal hash, which never leaves the runner;
  - anchor candidates (G9) are public drift reports, validated against the public contract. Older internal-format artifacts are rejected as `report_invalid`.
  The record below is historical.
- **Objective**: Deterministically relate Terraform drift to Activity Log evidence. This covers the capable-operations table, operation grouping, timing, anchor selection, verdicts, property link and actor attribution (G3–G9), and produces the restricted investigation document.
- **Dependencies**: Task 9B.1
- **Files/Areas**: new `src/drift_engine/investigation.py`; `src/drift_engine/attribution.py` (`external_deletion_v1` re-parameterized to G7/G8, rules version 2, reused by the investigation); `src/drift_engine/cli.py` (`investigate` subcommand: plan, manifest, drift report, anchor-candidates directory, comparison principal, lookback, M/C/skew from the locked defaults); new `tests/test_investigation.py`; `tests/test_attribution.py`, `tests/test_attribution_fallback.py` (updated)
- **Acceptance Criteria**:
  - [x] **Capable operations**: table v1 exactly as G6, versioned. Operation groups by (`correlationId`, operation) across `exact` and `extension` rows of the target. The verified tag pair forms one successful `tags` group. Only Administrative groups are capable or unclassified; Policy/Autoscale events are attached by correlationId or are automated-activity signals (G6).
  - [x] **Property areas (G6)**: relevant areas from the drift report's non-noise drifted paths. `sole` / `latest` only for a group capable for every relevant area, else `partial_capability`.
  - [x] **Unreadable events (G4)**: unreadable target-scope drops turn `sole` / `latest` into `ambiguous` and `none` into `not_investigated`, and block deletion confirmation.
  - [x] **Timing (G7)**: `before_observation` / `during_observation` / `after_observation` against the manifest window with a 60 s skew. `after_observation` groups are listed but never candidates.
  - [x] **Anchor (G9)**: selection over a supplied set of earlier reports plus run metadata, with every trust check, including the added ones (different run id, same repository, earlier plan timestamp, ≤ 50 candidates). A failed check excludes that report, recorded with a fixed code; no anchor → lookback.
  - [x] **Verdicts and links**: exactly the five verdicts (G4) with fixed reason codes, the property link (G5) and actor attribution (G3). Update drift is never `confirmed` (model invariant).
    - Deletion is `confirmed` only through `external_deletion_v1` (rules version 2), with existence anchor A (`write_event`) or B (`prior_detection_run`) and every R1–R7 safeguard, R7 at ±5 min.
    - The decisive operation exists only for `sole` / `latest` (or a confirmed deletion).
  - [x] **Settle/poll (G8)**: the first query at `run.finished_at` + M; re-query every 2 min up to `run.finished_at` + C while any queried drifted resource lacks a capable operation. This task owns the waiting, the poll loop, the poll count and the completeness record (each poll is one Task 9B.1 collection with `not_before`).
  - [x] **Run-level window (G9)**: computes `window_start` from the per-resource anchors and passes it to the collector, then narrows each address to its own anchor window.
  - [x] **Option A invariant (G5)**: `property_link = confirmed` (and confirmed actor attribution) only when the deletion rule confirms **and** the verdict is `sole` / `latest`; otherwise a rule-confirmed deletion is `inferred_not_provable` (`verdict_not_decisive`). It is enforced as a model invariant.
  - [x] **Report binding**: `investigate --report` must equal the drift report recomputed from `--plan` + `--manifest` (same canonical SHA-256 as `ai_engine`'s `drift_report_sha256`, computed without importing `ai_engine`); a mismatch is an input failure and nothing is queried.
  - [x] **No needless wait**: with no drift or no queryable target, there is no wait and no Azure query, and `not_before` is null.
  - [x] **Legacy field removed**: evidence `settled_until` (retained by Task 9B.1) is removed, together with Task 7.2's P5 and binding-window use of it, when `external_deletion_v1` is re-parameterized.
  - [x] **`drift-engine attribute` retained and adapted**: `drift_attribution.json` moves to attribution version 2 / rules version 2 (the G5 timing, the unreadable-events block, anchor A or B). A `prior_detection_run` anchor needs the anchor input, which only the investigation supplies, so `attribute` alone keeps anchor A only. `origin_statement` (Task 7.3) is unchanged.
  - [x] **Restricted output**: `drift_investigation.restricted.json`, a strict frozen model, byte-identical for identical inputs, 0600. It is bound to the drift report (run id, plan timestamp, canonical SHA-256) and the evidence SHA-256. `verify_against_evidence` independently re-checks every operation id, group, time and caller.
- **Validation**:
  - [x] Scenario matrix, real-shape fixtures:
    - the tag pair before observation with an anchor → `sole_capable_operation`;
    - the same without an anchor → `latest_capable_operation`;
    - two tag writes → `ambiguous`;
    - a tag write during observation → `ambiguous`;
    - an unclassified operation on the resource → `ambiguous`;
    - other resources in the resource group → no effect, counted;
    - an after-observation operation → listed only;
    - failed or unresolved groups;
    - none → `no_capable_operation_found`;
    - collection failure / no ID / binding failure → `not_investigated`;
    - deletion confirmed / unknown.
  - [x] Skew and M/C boundaries ±1 s. Anchor trust-check failures (branch, event, workflow, repository, same run id or attempt, run binding, environment, `finished_at` and plan-timestamp ordering, candidate limit, invalid report, address not `in_sync`).
  - [x] Property-area matrix (tags only, other only, tags + other with a tags write only → `partial_capability`, a lifecycle write explaining both), unreadable-event cases for every verdict, and Policy/Autoscale attached vs separate.
  - [x] Overlapping candidates under `latest`; straddling window membership; anchor A vs B ordering and B-overlap `order_ambiguous`; a rule-confirmed deletion under an `ambiguous` verdict stays unconfirmed; candidate-directory handling (`not_a_candidate`, ordering, limit).
  - [x] Determinism under shuffling and paging. Safeguard mutants are all caught: a verdict upgrade, a dropped ambiguity rule, an ignored skew, an anchor trust check removed, update drift confirmed, the unreadable-event rule removed, `partial_capability` ignored, Policy events counted as capable, settling from `started_at`, R7 tied to the 60 s skew, and Option A removed (confirmation under a non-decisive verdict).
  - [x] Task 7.2/7.3 suites updated and passing.
- **Implementation Notes**:
  - Starts with a design review (reason codes, statement template ids, the anchor-candidate input format shared with Task 9B.5).
- **Completion Notes**:
  - **Files**:
    - new `src/drift_engine/investigation.py`, `tests/test_investigation.py`;
    - changed `src/drift_engine/attribution.py` (rules / attribution version 2), `src/drift_engine/activity_logs.py` (legacy `settled_until` and `INGESTION_LAG` removed), `src/drift_engine/cli.py` (`investigate` subcommand), `src/drift_engine/__init__.py` (docstring);
    - tests updated: `tests/test_attribution.py` (v2 timeline T_start 09:59 / T_end 10:06 / settled from 10:15, constants, mutant sources, new scenarios), `tests/test_attribution_fallback.py` (new reason `unreadable_events_in_scope`, settled boundary), `tests/test_activity_logs.py` (window without `settled_until`).
    - **Unchanged**: the drift report and schema, `ai_engine`, workflows, Terraform, dependencies; `origin_statement` (Task 7.3).
    - The evidence version stays `"2"`: the legacy field was part of the v2 transition planned in 9B.1, and no v2 document exists outside tests.
  - **Investigation** (`investigate()`):
    - **Inputs and anchors**: verifies `--report` against the canonical hash of the report `analyze` writes for the plan and manifest, then selects trusted anchor runs (all G9 checks; codes `metadata_invalid`, `wrong_repository`, `wrong_workflow`, `wrong_branch`, `wrong_event`, `same_run`, `report_invalid`, `report_failed`, `run_binding_mismatch`, `environment_mismatch`, `observation_unknown`, `not_earlier`, `plan_not_earlier`, `outside_retention` (an anchor older than 88 days could not fit the collector's 89-day window), `not_a_candidate` (files, directories without `run.json`, symlinks), `candidate_limit`).
    - **Settling**: waits until `finished_at + 10 min` only when a drifted target is queryable. No drift or no usable ID means no wait and no query. Unknown detection time means no query at all.
    - **Polling**: collects with the run-level `window_start` (earliest per-address anchor start, else the lookback), correlates, and re-collects every 2 min up to `finished_at + 20 min` while a queried resource has no capable operation.
    - **Output**: the restricted document (`trust: restricted`) with binding, completeness (`not_before`, `queried_at`, `polls`, `settled`, max ingestion delay), anchor candidates and per-resource results.
  - **Correlation**: table v1, property areas, Administrative-only grouping by (correlationId, operation) over exact + extension rows, Policy/Autoscale attachment by correlationId or automated signal, timing (60 s skew), window membership by group end, the G4 verdict order, Option A, deletion via `attribution.decide` with anchor B.
    - **Model invariants** enforce the rules (e.g. only a deletion can be property-confirmed, a confirmed link needs a `sole` / `latest` verdict and a confirmed rule on the same operation, the decisive operation explains every area, unreadable scopes allow no `sole` / `latest` / `none`).
    - `verify_against_evidence` independently re-checks every operation's rows (existence, relation, category, group key, start/end, outcome, caller, timing, capability per a restated table), attached and automated events and confirmed-deletion rows. The CLI writes nothing (exit 70) if it reports a problem.
  - **Rules version 2** (`attribution.py`): skew 60 s, settled = `queried_at >= finished_at + 10 min`, P6 `unreadable_events_in_scope`, existence anchor B (`prior_detection_run`; the later proof wins; lifecycle overlap with B's observation ±60 s → `order_ambiguous`; deletes must start after B's `finished_at + 60 s`), R7 at ±5 min, binding `{skew_seconds: 60, settle_margin_minutes: 10, automated_overlap_minutes: 5, window: {start, end, queried_at}}`. `drift-engine attribute` has no anchor input, so it uses anchor A only.
  - **Real-shape result**: with the sanitized fixture of the 2026-10-04 portal tag edit and an in-sync anchor run, the investigation gives:
    - `sole_capable_operation` with decisive `Microsoft.Resources/tags/write` (exact + extension, Succeeded, `before_observation`, caller type `user`, client `azure_portal`);
    - `property_link: inferred_not_provable`, actor `not_confirmed`;
    - a 592 s wait to `finished_at + 10 min`, one poll.

    Without the anchor: `latest_capable_operation` over two CLI writes and the portal write.
  - **Tests** (session-scratchpad venv, Python 3.13.12, azure-mgmt-monitor 7.0.0; no Azure, credentials or real clock):
    - `tests/test_investigation.py` **81 passed** (111 subtests), covering:
      - real shape;
      - the verdict matrix (sole, latest, multiple, during, unclassified, children and resource-group contents counted only, after-observation, failed, unresolved, none, irrelevant);
      - property areas incl. `partial_capability`;
      - unreadable events for every verdict, each drop reason and the deletion block;
      - Policy/Autoscale attached vs signal, never capable, outside window / after observation;
      - skew ±1 s, window membership (straddling, exact edge, run-level vs per-resource window);
      - overlapping `latest`; settling from `finished_at` incl. a long observation; polling to a hit and to the cap ±1 s; not settled; no needless wait; unknown detection time;
      - not-investigated paths;
      - deletion: anchor A under `latest`, anchor B under `sole`, later-anchor choice, B overlap, Option A with an unclassified operation and with a distant Policy event, R7 independent of the skew, update drift never confirmed;
      - every anchor trust check and the current report never usable as an anchor; candidate-directory handling (non-candidates, ordering, limit 50);
      - report binding (tampered / invalid / other plan / failed run / canonical hash equal to `ai_engine`'s);
      - contract invariants and tampering; the verifier; determinism under shuffling and paging; the CLI (0600 outputs, counts-only stdout, exit codes 0/1/2/70/73, principal never written).
    - **Safeguard mutants 18/18 caught** in the default suite: verdict upgrade, unclassified / during / unresolved / automated / overlap rules dropped, skew ignored, three anchor trust checks and the candidate limit removed, update drift confirmed, unreadable rule removed, `partial_capability` ignored, Policy counted as capable, settling from `started_at`, Option A removed, window membership by start.
    - **Task 7.2 suite**: three new attribution mutants (settling from start, R7 tied to the skew, unreadable ignored) plus a re-timed boundary scenario, all caught.
    - **Full suite 2076 passed** (1852+ subtests); `drift_engine` coverage **99.61%** (`activity_logs.py` and `attribution.py` 100%, `investigation.py` 99%); `unittest discover` OK; `./scripts/validate.sh` passed; gitleaks: no leaks in changed files; no real identifier from the local raw query in any change.
  - **Not done / limitations**:
    - (a) `drift_attribution.json` (local `attribute` tool) has no G4 verdict, so Option A is not applied there: it can still confirm a deletion that the investigation marks `ambiguous` (e.g. an unclassified operation after the delete). The investigation (used in CI from Task 9B.5) is the authoritative result.
    - (b) Policy/Autoscale, service-principal and managed-identity shapes are fixture-only (unverified in real Azure).
    - (c) Operations before the run-level window are not collected at all (they are counted as `timestamp_outside_window` drops), so out-of-window operations appear only for addresses whose own window is narrower than the run-level one.
    - (d) Two defensive branches (`decisive_operation_mismatch`, a recomputed report failing its contract) are not reachable with valid inputs and stay untested.
    - (e) Anchor candidates are supplied as a directory; fetching them from GitHub is Task 9B.5; no real Azure run (Task 9B.6).

#### Task 9B.3 — Public Investigation Projection, Privacy Profile & Local WHO Path
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: the public investigation's binding and anchor references, `investigation-check --report` and `who --report` all use the **public** drift report and its canonical SHA-256. The public investigation schema and leak scan are unchanged. The record below is historical.
- **Objective**: Produce the public `drift_investigation.json` under the G11 profile, verify it against the restricted document, and provide the local-only WHO path (G12).
- **Dependencies**: Task 9B.2
- **Files/Areas** *(amended 2026-10-04, design review decisions A–F)*:
  - new `src/drift_engine/investigation_public.py` (public model, loader and leak scan; **no import of `activity_logs`, `attribution`, `investigation` or `who`**, so `ai_engine` can import it);
  - new `src/drift_engine/who.py` (local WHO);
  - `src/drift_engine/investigation.py` (`project()`, `verify_projection()`);
  - `src/drift_engine/activity_logs.py` (`collect_window()` only);
  - `src/drift_engine/cli.py` (`investigate --public-output`; `investigation-check` and `who` subcommands; the restricted stdout refusal in GitHub Actions; type-only errors);
  - `src/drift_engine/__init__.py` (docstring);
  - new `tests/test_investigation_public.py`, `tests/test_who.py`;
  - small updates to existing CLI tests in `tests/test_activity_logs.py`, `tests/test_attribution.py`, `tests/test_investigation.py`.
- **Acceptance Criteria**:
  - [x] **Public model**: an allowlist-only, strict, frozen model with exactly the G11 public schema (decision C); `op-<n>` / `auto-<n>` ordinals; exposure block; binding (run id, plan timestamp, drift report canonical SHA-256). No restricted-content hash, correlation id, event id, candidate name or rejection detail. Byte-identical output.
  - [x] **Public output (decision B)**: `investigate --public-output` projects, verifies restricted/public consistency and runs the leak scan before writing; any failure writes no public file (exit 70).
  - [x] **Projection check**: every public field equals its restricted source (an independent re-derivation).
  - [x] **Leak scan**: the fail-closed scan rejects a GUID, `@`, IPv4/IPv6, `/subscriptions/`, `/providers/` path or URL in any string. `investigation-check` validates a downloaded public file (contract, binding, leak scan).
  - [x] **Local WHO**: `drift-engine who` (local, read-only) matches each public operation to exactly one recorded operation group (G12) and prints the recorded caller.
    - It collects through `collect_window()` (decision A).
    - It writes only `who_evidence.local.json` (0600, atomic, no symlink target) under the required `--output-dir` (0700 if created).
    - No match, several matches, retention exceeded, a binding failure or a failed query each give a fixed error and no caller.
    - It refuses to run under `GITHUB_ACTIONS=true`.
  - [x] **Restricted-data CLI hardening (decision D)**: in GitHub Actions, `activity-logs`, `attribute` and `investigate` refuse restricted stdout output (exit 2). Unexpected errors of these commands and `who` print the exception type only, never `str(exc)`.
  - [x] **AI boundary (decision F)**: AST test: no `ai_engine` module imports `investigation`, `who`, `activity_logs` or `attribution`.
- **Validation**:
  - [x] Leak mutants: a planted value in every public string field (UPN, object ID, subscription ID, ARM ID, event ID, IP) is caught.
  - [x] Projection tampering is caught.
  - [x] `who` over a fake source: a unique match; zero/multiple matches; a timestamp off by more than 1 s (and an unequal timestamp inside the window); caller type or client mismatch; retention; binding failures (contract, leak, report mismatch, unknown address); both Terraform JSON input shapes; output permissions and the symlink refusal; the GitHub Actions refusal.
  - [x] Hardening: the stdout refusal for each restricted command under `GITHUB_ACTIONS=true`, and an internal error carrying a planted caller never printing it.
  - [x] Safeguard mutants on the projection, leak scan, `who` matching and the CLI guards are caught.
  - [x] Import boundary: importing `investigation_public` loads no `azure.*`, `activity_logs`, `attribution`, `investigation` or `who` module (subprocess test).
- **Implementation Notes**:
  - Starts with a design review (the exact public field list, the `who` input mapping from `terraform show -json`).
  - **Design review (2026-10-04, decisions A–F user-approved)**: recorded in G11, G12, G14, the data flow and the criteria above.
- **Completion Notes**:
  - **Files**:
    - new `src/drift_engine/investigation_public.py`, `src/drift_engine/who.py`, `tests/test_investigation_public.py`, `tests/test_who.py`;
    - changed `src/drift_engine/investigation.py` (`group_operations()` factored out of the 9B.2 grouping, behaviour unchanged; `project()`, `verify_projection()`, `publish()`; `canonical_sha256` now shared from `investigation_public`), `src/drift_engine/activity_logs.py` (`collect_window()` / `WindowCollection` only), `src/drift_engine/cli.py`, `src/drift_engine/__init__.py` (docstring).
    - The existing 7.x / 9B.1 / 9B.2 test files are unchanged; their CLI tests pass with the hardening.
    - **Unchanged**: `collect_evidence()`, `attribution.py`, the drift report and schema, `ai_engine`, workflows, Terraform, dependencies.
  - **Public document** (`drift_investigation.json`, `public_version: "1"`):
    - exactly the G11 schema (decision C), as strict frozen models with `extra="forbid"` at every level; per-resource ordinals `op-<n>` / `auto-<n>`; the exposure block;
    - binding (run id, plan timestamp, drift report canonical SHA-256, evidence outcome, observation); anchors as counts by reason; the anchor reference by GitHub run id and report SHA-256;
    - public model invariants (numbering, decisive operation, Option A and actor consistency, unreadable scope, descendant sums).
    - **Never present**: callers, resource / event / correlation IDs, `evidence_sha256` or any hash of restricted content, candidate names, per-candidate rejections.
  - **`publish()`** = project → public contract → `verify_projection()` (an independent field-by-field re-derivation) → `leak_findings()`, all before rendering. `investigate --public-output` writes nothing (restricted, evidence or public) and exits 70 when any check fails.
  - **Leak scan**: every string and dict key is checked for GUIDs, `@`, IP addresses (`ipaddress` parsing of candidate tokens, so ISO timestamps never match), `/providers/` and `/subscriptions/` paths and URLs. Findings report a location and kind only; content keys are shown as `<key>`, never echoed.
  - **`investigation-check`**: strict JSON, leak scan, contract and (with `--report`) the binding. It prints a fixed code plus finding counts by kind, never a value.
  - **Local WHO** (`who.py`, `drift-engine who`):
    - Terraform state (`values`, child modules) or plan JSON (`prior_state`) gives address → ARM ID;
    - per public operation, `collect_window()` over [start − 1 s, end + 1 s] (start rounded down, end up), regrouped with the investigation's `group_operations()`;
    - a match needs exact start/end (µs), operation, outcome, relations, caller type and client app;
    - fixed result codes `matched` / `no_match` / `multiple_matches` / `retention_exceeded` / `query_failed`; global `binding_failed` with details `invalid_json` / `leak` / `contract` / `too_large` / `binding_mismatch` / `terraform_invalid` / `address_unknown` / `invalid_resource_id`;
    - refuses under `GITHUB_ACTIONS=true` (in `run_who` and in the CLI); writes only `who_evidence.local.json` (0600, atomic) under `--output-dir` (created 0700), and refuses a symlinked file or directory;
    - prints the recorded caller with the fixed note that it is not proof of who caused the drift.
  - **Hardening (decision D)**:
    - `activity-logs`, `attribute` and `investigate` exit 2 without `--output` under `GITHUB_ACTIONS=true`.
    - For restricted commands (these three, `investigation-check`, `who`) the last-resort handler prints only the exception type and suppresses the debug traceback (which carries the message).
    - `investigate` write errors report the exception type only.
  - **Tests** (session-scratchpad venv; no Azure, credentials or real clock):
    - `tests/test_investigation_public.py` **24 passed** (1,700+ subtests):
      - projection of six scenarios (rich anchored + unanchored with attached/automated/descendant events and rejected candidates, confirmed deletion, failed input, failed evidence, unreadable scope, no drift): clean, byte-identical, loader round-trip;
      - no restricted value in any public text; the exact key sets; unknown fields rejected at every level;
      - leak kinds, no false positives on allowed content, findings never echo values;
      - **a planted UPN / object ID / subscription path / ARM ID / event ID / IPv4 / IPv6 / URL in every one of the 100+ public string fields and keys caught by the scan and the loader**;
      - projection tampering (13 cases); a consistent-but-leaky restricted document refused by the leak scan alone; publish failures;
      - CLI `--public-output` + `investigation-check` (valid, leak, JSON, contract, binding, unreadable);
      - hardening (stdout refusal per command in GitHub Actions; a planted caller in an exception never printed, incl. `--log-level debug`; `analyze` keeps detailed messages);
      - public contract invariants and loader errors; subprocess import boundary (no `azure.*`, `activity_logs`, `attribution`, `investigation`, `who`); **AST boundary over all of `src/ai_engine/`**; constants equal to the restricted modules.
    - `tests/test_who.py` **20 passed**: `collect_window` (bounded window and rounding, bad input, per-scope failure); both Terraform JSON shapes; unique / zero / multiple matches; timestamps off by 2 s and by 0.5 s; caller type, client, operation and outcome mismatches; retention; query failure; every binding failure; resources without operations; the GitHub Actions refusal; CLI output (0700 / 0600, single file, caller printed only on a match, symlink refusals, unreadable inputs, write error).
    - **Safeguard mutants 23/23 caught**, covering:
      - the leak scan (each kind, keys, loader skip, extra fields allowed, binding hash);
      - the projection (attached count, publish without leak scan or consistency check, verifier blind to operations);
      - `who` matching (start, client, multiple, retention, CI refusal, unknown address);
      - the CLI guards (stdout refusal, verbose restricted errors, public check skipped).
    - **Full suite 2118 passed** (3,627 subtests); `drift_engine` coverage **99.65%** (`activity_logs.py`, `attribution.py`, `investigation_public.py`, `who.py` 100%; `investigation.py` 99%; `cli.py` 99%); `unittest discover` OK; `./scripts/validate.sh` passed.
    - gitleaks: no finding in `src/drift_engine` or the new or changed tests; the one finding in `tests/` is the pre-existing synthetic key in `tests/test_infracost.py:45` (Task 10.1, untouched). No real identifier from the local raw query appears in any change.
  - **Not done / limitations**:
    - (a) no real `who` lookup against Azure (Task 9B.6, user-run);
    - (b) public fields such as the drift report's free-form `run_id` are protected only by the leak scan and its length bounds; a value that is sensitive without matching any leak pattern (e.g. a plain personal name in a run id) is not detectable. The CI run id is always `github-<id>-<attempt>`;
    - (c) `who` re-queries one window per operation (more Azure calls for resources with many operations);
    - (d) the public document's GitHub run ids and report hashes are public by design (they reference public drift artifacts).

#### Task 9B.4 — AI Report v2, Deterministic Investigation Narrative & Recommendation Policy
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-04
- **Completed**: 2026-10-05
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: only the input contract changes; 9B.4 is otherwise complete and is not reopened.
  - `ai-analysis` / `run_analysis` accept only the **public** drift report.
  - WHAT renders `withheld` views; a `withheld` view never produces an HCL fragment (gap reason `withheld`).
  - `verify_report` and the provenance hash use the public report.
  - The AI import allowlist gains the public drift report module.
  - These changes are implemented and tested in Task 9B.4A. Open issue (e) below is resolved there.
- **Objective**: Make the AI engine consume the public investigation model and produce report v2 (G16). This covers the WHAT/WHEN/WHO/correlation sections, the mandatory deterministic narrative (G15), recommendation policy v1, the sanitized LLM evidence model and guards (G14), and verification.
- **Dependencies**: Task 9B.3
- **Files/Areas**: `src/ai_engine/cli.py` (`--investigation`), `src/ai_engine/graph.py` (state input), `src/ai_engine/evidence.py` (sanitized investigation evidence for the LLM), `src/ai_engine/nodes/analyze_drift.py` (prompt: explain consistency/impact/risk only), `src/ai_engine/nodes/common.py` (guards), `src/ai_engine/nodes/root_cause.py` (deterministic attribution source replaces the constants), `src/ai_engine/nodes/remediation.py` (recommendation policy v1), `src/ai_engine/nodes/report_generator.py` (report v2, Markdown), `src/ai_engine/verify.py`, `src/ai_engine/config.py` (the disabled reason says "explicitly none" when the provider is set to `none`); tests: `tests/test_ai_report.py`, `tests/test_ai_engine.py`, `tests/test_ai_root_cause.py`, `tests/test_ai_cli.py`, new `tests/test_ai_investigation.py`, `tests/corpora/`, `tests/mutation/mutants.json`
  - **Added (2026-10-04, design review)**:
    - new `src/ai_engine/nodes/investigation_facts.py` (deterministic WHAT/WHEN/WHO/correlation, statement templates, policy v1);
    - `src/ai_engine/__init__.py` (docstring);
    - the tests that depend on report v1 structures: `tests/test_ai_config.py`, `tests/test_ai_cost_config.py`, `tests/test_ai_parse_drift.py`, `tests/test_ai_security.py`, `tests/test_attribution_fallback.py`;
    - `tests/test_investigation_public.py` (the AI boundary test becomes an allowlist).
- **Acceptance Criteria**:
  - [x] **Report v2**: implements the locked outline. Without `--investigation` the report records `investigation.status = not_available` and every drifted resource `not_investigated` (`investigation_not_provided`). An invalid or unbound investigation file → exit 1, nothing written.
  - [x] **D1–D3 (design review)**: the caller statuses of D1, the `not_drift` scope of D2, and the failed-investigation handling of D3, as locked in the report v2 outline.
  - [x] **D4 (design review)**: `ai-analysis` runs `verify_report` v2 on the generated report (against the drift report and the investigation) before writing. Any problem → exit 70, nothing written.
  - [x] **AI boundary**: `drift_engine.investigation_public` is the only investigation module `ai_engine` imports. The AST test is an allowlist (`drift_engine.logs`, `drift_engine.models`, `drift_engine.investigation_public`). A subprocess test checks that importing `ai_engine.cli` / `ai_engine.graph` loads no restricted module.
  - [x] **Deterministic fallback (no LLM)**: answers WHAT/WHEN/WHO/correlation and the recommendation with versioned statement templates. Every unprovable fact renders "not confirmed by available evidence".
  - [x] **Recommendation policy v1**: rules R0–R4 exactly, with approval and execution constants unchanged.
  - [x] **LLM evidence model**: only public-model fields plus allowed Terraform evidence; `evidence_sent` records the investigation keys sent. Guards reject identity-like strings, actor naming, verdict-upgrade wording, and operations or timestamps not in the model. AI cannot change any deterministic field.
  - [x] **`verify_report` v2**: independently checks the investigation sections against the public investigation file and the drift report.
  - [x] LLM stays disabled in CI (unchanged CLI refusal).
- **Validation**:
  - [x] Report v2 on every fixture: the verified tag scenario, the no-anchor, ambiguous, none, not-investigated and deletion-confirmed scenarios, and no drift.
  - [x] Markdown order and escaping.
  - [x] Policy table over all option fixtures.
  - [x] Fake-model tests: a valid explanation accepted; actor naming, identity strings, "caused" / "confirmed" upgrades and an invented time or operation rejected; deterministic state byte-identical with and without the LLM.
  - [x] Guard and injection corpora extended.
  - [x] Mutation harness extended (verdict, policy and guard mutants caught).
  - [x] Network guard active; no real LLM.
- **Implementation Notes**:
  - Starts with a design review (field names, statement templates, guard patterns, prompt changes within the one-logical-call guarantee of Phase 6).
  - **Design review (2026-10-04, user-approved D1–D4)**:
    - D1–D3 are recorded in the report v2 outline above. D4 is the CLI self-verification criterion.
    - Before implementation, the completed Tasks 9B.1–9B.3 were committed as checkpoint `573d5ec`.
  - **Design details (settled inside the locked rules)**:
    - **Authority**: the public investigation is authoritative for verdict, property link, actor attribution, operations and timestamps. The LLM only adds labelled inference and can change no deterministic field.
    - **One logical LLM call**: a sixth section, `investigation_analysis`, in the same reply. Per drifted resource it has:
      - `cited_operations` (`op-<n>` sent for that address);
      - a structured `consistency` (`consistent_with_drift` | `not_consistent_with_drift` | `undetermined`) that is checked against the operations' deterministic roles;
      - an explanation (impact / risk).
    - **LLM investigation evidence**: an allowlisted subset of the public model.
      - Per resource: address, drift action, relevant areas, verdict, reason, property link and reason, actor attribution status, window kind, decisive operation, unreadable flag, operations (no caller status), automated events, descendant count.
      - Run-level: observation and completeness (`queried_at`, `settled`).
      - Excluded: binding hashes, anchor run ids and report hashes, the exposure block.
      - The public leak scan runs again on it before sending. `llm.investigation_sent` records the addresses and refs sent.
    - **Guards** (in addition to the Phase 6 guards):
      - identity-like strings (the public leak-scan kinds);
      - verdict-upgrade wording ("caused", "responsible for", "proves", "confirms/confirmed", "definitely", "conclusively", ...);
      - any timestamp, Azure operation name or `op-<n>` / `auto-<n>` reference not in the evidence sent.
    - **Root-cause findings**: they lose `actor` / `confirmed` / `confirmation_requires`. The deterministic `who.actor_attribution` is the only place attribution appears.
    - **Field-name finalisation**:
      - the LLM record stays the top-level `llm` object and `generated_from` becomes `provenance`;
      - the top-level `remediation.options` list and the `analysis` section map are kept, so the 9A.1 workflow summary keeps working until Task 9B.5;
      - the public schema v1 has no per-row event phase, so `operations[]` shows the group outcome;
      - WHAT keeps Terraform's three views: expected = `desired`, actual = `real`, recorded = `state`.
- **Completion Notes**:
  - **Checkpoint**: Tasks 9B.1–9B.3 committed as `573d5ec` before implementation (clean tree; full suite 2118 passed at that commit).
  - **Files**:
    - new `src/ai_engine/nodes/investigation_facts.py`: load and bind the public investigation; deterministic WHAT/WHEN/WHO/correlation facts; statement templates v1; the LLM `investigation_analysis` section schema and validator;
    - changed `src/ai_engine/`: `cli.py`, `graph.py`, `evidence.py`, `config.py`, `verify.py`, `__init__.py` (docstring), and `nodes/`: `analyze_drift.py`, `common.py`, `remediation.py`, `report_generator.py`, `root_cause.py`, `security_analysis.py`, `cost_analysis.py` (guard references only);
    - new `tests/test_ai_investigation.py`;
    - updated tests: `tests/test_ai_cli.py`, `test_ai_config.py`, `test_ai_cost_config.py`, `test_ai_engine.py`, `test_ai_parse_drift.py`, `test_ai_report.py`, `test_ai_root_cause.py`, `test_ai_security.py`, `test_attribution_fallback.py`, `test_investigation_public.py`;
    - extended `tests/corpora/guards.json`, `tests/corpora/injection.json`, `tests/mutation/mutants.json`.
    - **Unchanged**: `drift_engine` (incl. `investigation_public`), the drift report contract, workflows, scripts, Terraform, dependencies.
  - **Report v2** (`report_version: "2"`):
    - `provenance`: both canonical SHA-256 hashes and every version;
    - run-level `investigation`: status, failure, observation, completeness, anchors, rules, exposure;
    - `resources[]` (every changed resource, in drift report order):
      - `investigation_scope` (`drift` / `not_drift`, D2);
      - `what` (basis `terraform_evidence`; expected = `desired`, actual = `real`, recorded = `state`);
      - `operations[]` / `automated_events[]` (basis `activity_log_evidence`, `caller_identity: withheld`);
      - `when` (incl. `gap_seconds`);
      - `who` (`recorded_caller` per D1, `actor_attribution`);
      - `correlation` (verdict, reason incl. `investigation_not_provided` / `investigation_failed`, property link, deletion rule, counts, descendant operations);
      - `analysis.narrative` (all fixed statements in order);
      - `remediation` {`option_ids`, `recommendation`};
    - top-level `analysis` (six sections: the five Phase 6 sections plus `investigation`), `remediation` (catalogue options, policy version), `cost`, `llm` (+ `investigation_sent`), `limitations`.
    - The top-level `remediation.options`, `analysis` map and `llm.provider/status` keep the Task 9A.1 workflow summary working until Task 9B.5 (its executed-step test now shows "0 of 6" sections).
  - **Statements v1**: 39 fixed templates (`what.*`, `operations.*`, `correlation.*`, `link.*`, `when.*`, `who.*`, `recommendation.*`). Missing slots render "not confirmed by available evidence", as do all unknown event times, callers, attribution and correlation. The verifier matches every statement against its template.
  - **Policy v1**: implemented in `remediation.recommend` (R0–R4, first match). It is stored per resource and restated independently in `verify.py`. Approval and execution constants are unchanged (`approval_required: true`, `execution_allowed: false`, `automatic_apply: false`). `ranking: none` was removed, since policy v1 now recommends.
  - **LLM** (still one logical call):
    - sixth section `investigation_analysis` (cited `op-<n>`, `consistency` checked against the deterministic operation roles and verdict, explanation);
    - evidence: the allowlisted public subset, leak-scanned again before sending; no caller status, binding, anchor run id or report hash;
    - `llm.investigation_sent` records the addresses and refs sent (field name finalised here; `evidence_sent` keeps the Terraform keys);
    - new guards on all sections: `identity_like_string`, `verdict_upgrade`, `unsupported_timestamp` / `unsupported_operation` (references not in the evidence sent);
    - root-cause findings no longer carry `actor` / `confirmed`.
  - **D4**: `ai-analysis` runs `verify_report(report, drift_report, investigation)` before writing. Any problem → exit 70 with a count only, nothing written. An invalid, leaky, contract-breaking, unbound (incl. `report_invalid` / `report_mismatch`) or out-of-scope investigation → exit 1, nothing written. `run_analysis` re-checks the investigation inside the graph.
  - **AI boundary**: AST allowlist test (`drift_engine.logs`, `drift_engine.models`, `drift_engine.investigation_public`). Subprocess test: importing `ai_engine.cli` / `graph` / `verify` loads no `azure.*`, `activity_logs`, `attribution`, `investigation` or `who`.
  - **Config**: `AI_LLM_PROVIDER=none` set explicitly → disabled reason "AI_LLM_PROVIDER is explicitly none (LLM analysis disabled)". The GitHub Actions refusal is unchanged.
  - **Validation** (session-scratchpad venv, Python 3.13, `ci/ai-constraints.txt`; no Azure, network or real LLM; `tests/conftest.py` network guard active):
    - `tests/test_ai_investigation.py`: **53 passed** (86 subtests). Scenarios come from the real 9B.2 investigation and 9B.3 projection over fake Activity Log sources:
      - the verified portal tag edit: sole, op-1 `Microsoft.Resources/tags/write`, event 11:04:56.093597–11:04:58.187357Z, gap 100.812643 s, caller `user` / `azure_portal`, identity withheld, attribution not confirmed, `inferred_not_provable`, R4 `restore_declared` with the accept-remote note;
      - no anchor (latest, azure_cli caveat); ambiguous with 2 candidates (`multiple_operations`) and with 1 (`no_decisive_operation`); none; unreadable scope;
      - caller missing / inconsistent (`not_recorded`); confirmed deletion (R2); deletion not confirmed; rule-confirmed deletion under an ambiguous verdict (stays inferred, Option A);
      - bindable failed investigations (evidence failure; input failure with no resources) → `investigation_failed`; the unbindable one rejected;
      - no drift; a `config_change` next to drift (`not_drift`); no investigation.
      - Also: the Markdown heading order, determinism, the policy table over every option fixture, every load and CLI rejection, the D4 exit 70, 26 investigation tamper cases plus AI-finding and investigation-file tampering, fake-model accept/reject (actor, identity, causal/proof upgrades, invented time/operation/reference, consistency upgrade), deterministic parts identical with and without the LLM, and prompt allowlist / no restricted data.
    - **Full suite 2230 passed** (3,747 subtests); coverage 98.83% (gate 85%); `unittest discover` OK (919); `./scripts/validate.sh` passed.
    - **Mutation**: 188/188 caught (`scripts/run_mutation_checks.py`): 16 Phase 6 mutants retargeted to the v2 code, 34 new (facts/verdict, binding, evidence, guards, the investigation section, policy, report, verifier, CLI).
    - **Scans**: gitleaks over every changed file shows only the pre-existing synthetic `PROJECT_PLAN.md:1651` finding. No identifier from the local raw Activity Log capture appears in any change (41 identifier-like raw values checked). Test identities use `example.com` / `.invalid` and documentation IP ranges only.
  - **Not done / limitations**:
    - (a) no real LLM was run (fake models only; CI keeps `AI_LLM_PROVIDER=none`);
    - (b) CI integration is Task 9B.5: until then `ai-analysis.yml` runs report v2 without `--investigation` (every drifted resource `investigation_not_provided`);
    - (c) guard trade-offs (documented in `guards.json`):
      - negated proof wording ("not confirmed") is rejected;
      - a clock-like number reads as a time;
      - an IP or URL is accepted only when quoted verbatim from the Terraform evidence sent;
      - a plain personal name still cannot be recognised without NER;
    - (d) D4 is fail-closed: a verifier false positive blocks the AI report (exit 70);
    - (e) **resolved by Task 9B.4A (2026-10-05, P1–P4)**; original note: `what` copies the drift report's Terraform views unchanged, as report v1 did. For object-level changes (e.g. a deletion) those views include the resource's ARM ID, so the existing drift report and the AI report then carry `/subscriptions/…` paths. The investigation-derived sections pass the leak scan in every scenario, and the verified tag-edit scenario is leak-free end to end. This conflicts with the broad reading of G11 ("every public artifact") and with Task 9B.6's leak-scan criterion for deletion cases. Resolving it touches the drift report contract (G17) or the G11 / 9B.6 wording.

#### Task 9B.4A — Public Drift Report Projection
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-05
- **Completed**: 2026-10-05
- **Objective**: Everything that leaves the runner uses a deterministic, independently verified **public projection** of the drift report. The internal drift report, its contract and the Phase 3/4 detection, classification and severity semantics stay unchanged. This resolves Task 9B.4's open issue (e): ARM IDs in public deletion reports.
- **Dependencies**: Task 9B.4; the internal drift report contract (Tasks 3.5, 4.3, 4.6; unchanged)
- **Locked decisions (user-approved 2026-10-05)**:
  - **P1 — Internal/public split**:
    - The existing `drift_report.json` (schema `schemas/drift_report.schema.json`, `drift_engine.models.DriftReport`) stays the internal deterministic document: runner-only in CI (or local), never uploaded, never hashed into anything public.
    - A deterministic public projection is the contract consumed by the investigation's public binding and anchors, AI analysis, GitHub issues, the cost binding and every public artifact.
    - Phase 3 detection semantics and its historical acceptance criteria are not modified.
  - **P2 — Public exposure rules**:
    - Withheld: ARM/resource IDs, subscription/provider paths, GUIDs, UPN/email-like identities, and Activity Log / caller IPs (the drift report never carries Activity Log data; the class is listed for completeness).
    - Kept as Terraform configuration evidence: configured IPs/CIDRs and URLs that are Terraform values.
    - G11 is clarified accordingly. Identifiers become deterministic typed `withheld` views; the final AI report is never regex-cleaned.
  - **P3 — Fail closed**: if the projection cannot be produced safely or independently verified:
    - publication fails and nothing is uploaded;
    - `analyze` exits 70 with a fixed code, so the existing Task 5.5 mapping gives UNKNOWN;
    - the internal report is never published in its place.
  - **P4**: this task owns the items below; CI wiring is Task 9B.5.
- **Design (locked; field names finalised in the task's own design review)**:
  - **Public document**: `drift_report.json` in the artifact.
    - It has the internal report's fields, structure, order, classification, severity, counts, addresses, run and plan blocks and notes, plus top-level `public_version: "1"` and the extra view status `withheld`. Nothing else is added or dropped.
    - Strict, frozen models in new `src/drift_engine/report_public.py`, which imports no restricted module.
    - JSON schema: new `schemas/drift_report.public.schema.json`.
  - **Withheld view**: `{"status": "withheld", "kinds": [...], "resource": <Terraform address> | null, "ref": "id-<n>" | null}`.
    - A scalar ARM ID equal to the ID of exactly one managed resource in the same plan names that resource's Terraform address.
    - Any other withheld scalar gets a per-report ordinal `ref`: deterministic order of first occurrence; the same raw value gives the same ref, so S/R/D inequality stays visible; refs encode nothing.
    - A list/map value containing any withheld-class leaf or key is withheld as a whole view (`kinds` lists the classes; no `resource`/`ref`).
    - `withheld` is distinct from Terraform's `redacted`; the `redacted` flag and redaction (§8.3) are unchanged.
  - **Structure**:
    - A withheld-class map key in a change `path` or in `attributes[].name` becomes a positional placeholder, and that change's views are withheld.
    - A withheld-class value in any structural field fails the projection (P3), never a rewrite. Structural fields: address, `module_address`, `index`, `previous_address`, `resource_types[].addresses`, output names, `run`, `plan`, `notes`.
    - `detection_run.json` is scanned the same way before upload.
  - **Address/ID index**: built on the runner from the same `plan.json` (`prior_state`, planned values and change before/after `id`) and never published. An ID matching several addresses gets a `ref`.
  - **Independent verification**: `verify_public_report(public, internal, index)` re-derives the projection field by field.
    - Every non-view field is equal.
    - Every view is either byte-identical (no withheld class inside) or a correct `withheld` view.
    - Refs are consistent.
  - **Fail-closed identifier scan** over the whole public document and `detection_run.json`: GUID, `/subscriptions/` and `/providers/` paths (case-insensitive), UPN/email-like strings. Configured IPs/CIDRs and URLs are not flagged (P2).
  - **Hash contract**: the canonical SHA-256 (sorted keys, compact separators, UTF-8; Task 9A.1 convention) of the public document. It is the only drift report hash in public artifacts (G11).
  - **CLI**: `drift-engine analyze --public-output PATH`.
    - Projection, verification and scan all complete before the public file is written.
    - Any failure: exit 70, a fixed code `public_projection_failed:<code>`, no public file, no value or `str(exc)` printed.
    - Without the flag, `analyze` is unchanged.
    - Fixed codes: `identifier_in_structure`, `index_invalid`, `verification_failed`, `scan_failed`, `write_failed`.
  - **Consumers switched to the public contract (in this task)**:
    - `ai_engine`:
      - `ai-analysis` and `run_analysis` accept only the public model;
      - `withheld` views render in WHAT, never produce HCL fragments (gap `withheld`), and are sent to the LLM as statuses only;
      - `verify_report` and provenance use the public report;
      - the import allowlist adds `drift_engine.report_public`.
    - `scripts/github_automation.py` validates the public model and renders `withheld`.
    - `drift_engine.investigation`: the public binding hash is the public projection's; anchor candidates are validated as public reports.
    - `investigation_public.check_binding`, `investigation-check --report` and `who --report` take the public report.
    - `scripts/sanitize_infracost.py` refuses a report without `public_version` (fail closed) and binds to its hash.
- **Files/Areas**:
  - new `src/drift_engine/report_public.py` and `schemas/drift_report.public.schema.json`;
  - `src/drift_engine/cli.py` (`analyze --public-output`), `src/drift_engine/investigation.py`, `src/drift_engine/investigation_public.py` (binding input only), `src/drift_engine/who.py` (`--report`);
  - `src/ai_engine/` (`cli.py`, `nodes/parse_drift.py`, `nodes/remediation.py`, `nodes/report_generator.py`, `evidence.py`, `verify.py`);
  - `scripts/github_automation.py`, `scripts/sanitize_infracost.py`;
  - `docs/drift-detection-spec.md` §8.3 (CI publication, issue and AI publication paragraphs; the 9A.1 "same exposure profile" sentence), `README.md` (publication wording);
  - tests:
    - new `tests/test_public_report.py`;
    - `tests/test_cli.py`, `tests/test_models.py` (and schema tests);
    - `tests/test_investigation.py`, `tests/test_investigation_public.py`, `tests/test_who.py`;
    - `tests/test_github_automation.py`, `tests/test_github_issue_lifecycle.py`, `tests/test_infracost.py`;
    - the AI tests (report helpers project fixture reports), `tests/test_ai_investigation.py`;
    - `tests/mutation/mutants.json`.
  - **Not here**: workflows (Task 9B.5), Terraform, the internal contract, Phase 3/4 classification.
- **Acceptance Criteria**:
  - [x] Internal report byte-identical to before for every fixture; Phase 3/4 tests unchanged and passing.
  - [x] Public projection deterministic (byte-identical), with exactly the P2 withheld classes. Configured IPs/CIDRs and URL values are unchanged, and only withheld-class content changes.
  - [x] Address mapping, ordinal refs, containers, keys/paths and structural failures as designed; fixed failure codes; nothing written on failure.
  - [x] Independent verification and a fail-closed scan; a planted ARM ID, GUID, subscription/provider path or UPN/email in every value, key and structural position is caught (or withheld, for values).
  - [x] Every public consumer uses the public contract and hash; no public artifact or binding carries an internal report hash.
  - [x] The deletion, removal and replace fixtures and the AI report v2 built from them are leak-free (identifier classes) end to end.
  - [x] 9B.4's AI behaviour is otherwise unchanged (deterministic parts identical apart from `withheld` views and the hash).
- **Validation**:
  - [x] `tests/test_public_report.py`: projection, mapping, refs, containers, keys, structural failures, scan, verification tampering, hash, CLI.
  - [x] Leak mutants in every public string position.
  - [x] Consumer tests: issues, cost guard, investigation binding/anchors, `who`, AI.
  - [x] Full suite, coverage gate, mutation corpus extended (projection, verification and scan mutants caught).
  - [x] gitleaks; no real identifier in fixtures or changes.
- **Implementation Notes**:
  - Starts with its own short design review inside these locked rules (exact field names, placeholder format, fixed codes).
- **Completion Notes**:
  - **Files**:
    - new `src/drift_engine/report_public.py` (models, identifier classes, address/ID index, projection, independent verification, identifier scan, hash, `publish_report`);
    - new `schemas/drift_report.public.schema.json`, generated from the internal schema (differences: `public_version`, the `withheld` view);
    - new `tests/test_public_report.py`;
    - changed:
      - `src/drift_engine/cli.py` (`analyze --public-output`; fixed codes; help texts), `src/drift_engine/investigation.py` (public binding hash; public anchor contract), `src/drift_engine/__init__.py` (docstring);
      - `src/ai_engine/cli.py`, `nodes/parse_drift.py` (public contract only), `nodes/remediation.py` (gap `withheld`), `nodes/report_generator.py` (Markdown for `withheld`);
      - `scripts/github_automation.py` (public model), `scripts/sanitize_infracost.py` (public-only guard), `scripts/run_mutation_checks.py` (copies `scripts/` into mutation sandboxes);
      - `docs/drift-detection-spec.md` §8.3, `README.md`;
      - tests: the consumer tests read public reports (`_public` / `public_report_bytes` helpers); anchors are public; the internal report is kept where the current workflow or `investigate` reads it; `tests/mutation/mutants.json` (+3).
    - **Unchanged**: classifier, comparator, severity, parser, models, formatters, `schemas/drift_report.schema.json`, `scripts/detect_drift.py`, workflows, Terraform.
    - `investigation_public.py`, `who.py`, `ai_engine/evidence.py` and `verify.py` needed no code change: they already take whatever report bytes they are given and hash or verify it, and `evidence.py` sends non-value views as statuses only.
  - **Behaviour**:
    - **Withheld views**: an ARM ID owned by exactly one resource of the same plan names that address; ambiguous or foreign IDs, GUIDs and UPN/email-like identities get `id-<n>` refs (stable per raw value); containers are withheld whole; identifier map keys become `withheld-key-<n>` in `path`, `attribute`, `attributes[].name` and the matching severity-reason prefix (exact match), with that change's views withheld.
    - **Kept**: configured IPs/CIDRs and URLs.
    - **Fail closed**: an identifier in any other field, a failed verification, a failed scan (report and run manifest), an unexpected error or a write failure each give exit 70 `public_projection_failed:<code>`, nothing written, no value echoed.
    - `investigate` binds the public investigation to the public hash; a projection failure there is `report_invalid` with no binding hash.
  - **Validation** (scratchpad venv, Python 3.13, AI constraints):
    - `tests/test_public_report.py`: **29 passed** (172 subtests):
      - internal output byte-identical with and without `--public-output` for all fixtures;
      - every fixture projects deterministically, verifies, validates the public schema and is identifier-free;
      - deletion, removal and replace IDs: their address, or a ref when the synthetic fixture shares one ID between two addresses;
      - classes and kept evidence; key placeholders; structural failures;
      - 28 verification tampering cases; an identifier planted in every value and key position (5 samples × 150+ positions) caught;
      - model and schema exclusion and agreement; the hash contract; CLI success, every failure code, real structural failure and write failures;
      - consumers: issues (internal rejected, `withheld` rendered), cost guard, AI report v2 from identifier drift leak-free with gap `withheld` and the public provenance hash;
      - **in-process safeguard mutants 18/18 caught**.
    - Consumer suites:
      - `test_ai_investigation.py`: the confirmed-deletion AI report is now identifier-free end to end;
      - `test_investigation.py`: internal-format anchor rejected; binding = public hash, never internal; projection failure;
      - `test_who.py` / `test_investigation_public.py`: the internal report never binds.
    - **Full suite 2261 passed** (3,931 subtests); coverage 98.84% (`report_public.py` 99%); `unittest discover` OK; `./scripts/validate.sh` passed.
    - **AI mutation corpus 191/191 caught**: the full run caught 190; `g-table-pipes-unescaped` was caught after its test was strengthened (the fixture value it relied on is now withheld).
    - **Scans**: gitleaks shows only the two pre-existing synthetic findings (`tests/test_infracost.py:45`, the plan's long-standing false positive). None of the 41 identifier-like values of the local raw Activity Log capture appear in any change.
  - **Not done / limitations**:
    - (a) **Transitional CI blocker, owned by Task 9B.5**: the workflows still upload and consume the internal report. Once this code reaches `main` without 9B.5's wiring, `ai-analysis`, the issues job and the cost check refuse that report and fail (fail-closed by design). Do not push 9B.4A to `main` alone; land it together with 9B.5.
    - (b) Withholding is conservative: any email-like string (e.g. an owner tag) and every GUID-valued attribute is withheld, even when harmless.
    - (c) The workflow executed-step tests in `tests/test_ai_cli.py` still model today's gate (internal report) until 9B.5 changes it.
    - (d) `drift-engine analyze` still prints `str(exc)` for an internal-contract violation (pre-existing Phase 4 behaviour, outside this task); projection errors print fixed codes only.

#### Task 9B.5 — CI Integration (Drift Detection & AI Analysis Workflows)
- **Status**: 🟢 COMPLETED (2026-10-09). Every acceptance criterion and validation item is checked.
  - Implementation committed with 9B.4 and 9B.4A in `26aa3a9` (item 8); G18 CI result policy in `4ba7668`; CI Activity Log authentication fix (Option B, then Option A plus a sanitized diagnostic, including review fixes M1/L2/L3/N1) in `62bdf65`.
  - Real CI proofs:
    - no-drift run #28 (`37948472263`) with its artifact checks;
    - drifted run #29 (`37961189506`), with AI run #12 and all artifact-content checks;
    - in-sync verification run #30 (`37963733177`, issue #7 closed).
  - History: kept 🔵 on 2026-10-09 (user decision, Option B) after scheduled runs #24/#25 showed `authentication_failed` on real drifted runs. That defect is fixed and proven by run #29.
- **Started**: 2026-10-05
- **Completed**: 2026-10-09
- **Objective**: Run the investigation in `plan-and-analyze` and publish `drift-investigation-<run_id>` (G10), add the `investigation` check job, and feed the public investigation into `ai-analysis.yml`. Detection, issues, report and cost results stay unchanged.
- **Dependencies**: Task 9B.4A (and 9B.4); Task 10.1 (step order and D5 exception pattern); Task 9A.1 (binding conventions)
- **Files/Areas**: `.github/workflows/drift-detection.yml`, `.github/workflows/ai-analysis.yml`, new `ci/azure-constraints.txt`, new `scripts/investigation_analysis.sh` (orchestrates install check, anchor fetch, `investigate`, projection, check; fixed status codes; counts-only output), new `scripts/fetch_prior_drift_reports.py` (GitHub API, `actions: read`, G9 metadata and download into a runner directory; rules in G9 "Anchor fetch"); runner-only paths `${RUNNER_TEMP}/drift-internal/`, `${RUNNER_TEMP}/investigation/restricted/` (0700) and `${RUNNER_TEMP}/investigation-venv` (G10), new `tests/test_investigation_workflow.py`, `tests/test_infracost.py` (step order and exception list; amended 2026-10-05, item 5), `tests/test_ai_cli.py` (workflow structure; executed-step gate tests move to the public report); `README.md`, `docs/drift-detection-spec.md` (§8.3 and a new investigation section), `docs/architecture.md`
  - **Amended (2026-10-09, CI Activity Log authentication fix)**:
    - `src/drift_engine/activity_logs.py`: credential scope and the authentication diagnostic;
    - `scripts/investigation_analysis.sh`: `investigation_detail` auth codes;
    - `tests/test_activity_logs.py` and `tests/test_investigation_workflow.py`;
    - `docs/drift-detection-spec.md` and `README.md` (diagnostic codes, only where needed).
- **Acceptance Criteria**:
  - [x] **Workflow structure**: steps after `Upload Drift Report` and before the cost step; separate pinned venv with an exact-pin check; outputs `investigation_status` / `investigation_failure` / `investigation_detail` / `investigation_publishable` / `investigation_upload_outcome` (amended 2026-10-05); the documented exit-0 capture; exactly two `continue-on-error` uploads in the workflow; `plan-and-analyze` permissions `id-token: write`, `contents: read`, `actions: read` and timeout 45; the `investigation` job (`contents: read`, no Azure or secrets) with `--check` and a counts-only summary. **Inputs (amended 2026-10-05, item 3)**: it downloads both `drift-investigation-<run_id>` and `drift-report-<run_id>`, and runs `drift-engine investigation-check --public <file> --report <downloaded public drift_report.json>` (binding against the downloaded public report).
  - [x] **Isolation**: for every investigation failure (install, anchor fetch, Azure auth/authorization/throttling/timeout, correlation, projection, leak scan, upload), `drift_detected`, the drift report and artifact, `issues`, `report` and `cost` are identical to the same run with the investigation steps removed (artifact = the public drift report; amended 2026-10-05, item 4), and the `investigation` job fails. (An `incomplete` investigation is not a failure: G18.)
  - [x] **Investigation outcome mapping (user-approved 2026-10-05, decisions 1 and 2)**: `scripts/investigation_analysis.sh` always exits 0 and writes `investigation_status` / `investigation_failure` / `investigation_publishable`.
    - Required input file missing → `failed` / `inputs_missing` / false.
    - pip install fails / installed pins differ → `failed` / `install_failed` / `pin_mismatch` / false.
    - Anchor fetch exit ≠ 0 or timeout → `failed` / `anchor_fetch_failed` / false; `investigate` is not run (decision 2).
    - `investigate` exit 0 and the public check passes → `succeeded` / `none` / true.
    - Exit 1, public `outcome: incomplete`, check passes → `incomplete` / `incomplete` / true (decision 1).
    - Exit 1, public `outcome: failed` at the evidence / binding / input stage, check passes → `failed` / `evidence_failed` / `evidence_binding_failed` / `input_failed` / true (decision 1).
    - Exit 1 with an unbindable document (null binding hash) → `failed` / `public_check_failed` / false (Task 9B.4 D3).
    - Exit 2 / 70 / 73 / other → `failed` / `investigate_usage` / `investigate_internal_error` / `write_failed` / `investigate_internal_error` / false.
    - Killed by `timeout` (124) → `failed` / `timeout` / false.
    - Public check fails (leak, contract, binding) → `failed` / `public_check_failed` / false.
    - **`investigation_detail`**: counts by fixed code only (e.g. `throttled=1`, `authorization_failed=1`), from the runner-only evidence's per-scope query-failure and limit codes. This is how authentication, authorization, throttling and timeouts become distinguishable without exposing values. **Amended (2026-10-09, CI Activity Log authentication fix)**: it also counts the fixed `auth_<reason>` codes from `error.auth_reason`.
    - **Decision 1 (amended 2026-10-09, G18, user-approved)**: an `incomplete` or failed-but-bindable investigation is uploaded unchanged. The public document keeps its own `outcome` and `failure` (stage/reason), so the AI report shows per-resource reasons or `investigation_failed` (D3). The `investigation` job **passes with a warning** for `incomplete` and **fails** for failed-but-bindable. *(Original 2026-10-05 wording: "The `investigation` job still **fails**" for both. Superseded because `incomplete` only occurs when drift exists, so drift alone could turn the run red.)*
  - [x] **`investigation` job result (amended 2026-10-09, G18)**:
    - **passes** when `investigation_upload_outcome == success`, `Verify Drift Investigation` passes, and `investigation_status` is `succeeded`, or is `incomplete`. For `incomplete` it emits a `::warning::` (drift investigated; some facts not confirmed by available evidence);
    - **passes** on a no-drift run (`drift_detected == 'false'`) when the investigation did not run (empty `investigation_status`: not required, intentionally skipped). The step itself writes "not required: no drift" to the step summary. Upload and verification are not checked because they did not run (revision 2026-10-09);
    - **fails** in every other case:
      - `failed` (including decision 1's uploaded failed-but-bindable case), on a drifted or a no-drift run;
      - an empty status (never ran) on a drifted run (`drift_detected == 'true'`: investigation required);
      - an upload failure, or a verification failure (also for `incomplete`).
    - *(Original 2026-10-05 criterion, met and superseded: passes only for `succeeded`.)*
  - [x] **CI result policy (G18, user-approved 2026-10-09)**: `drift-detection.yml` implements the G18 result matrix:
    - no drift → success with `drift_detected=false`;
    - drift → success with `drift_detected=true`, drift visible;
    - detection/process error → failure with `unknown`;
    - investigation `incomplete` → success with a warning; investigation `failed` → the `investigation` job fails;
    - investigation required (drifted run) but never ran → the `investigation` job fails; not required (no-drift run) and skipped → it passes.
    - No job condition or pass/fail step treats `drift_detected == 'true'`, `has_drift: true` or plan exit 2 as a failure.
    - `Require Investigation Success` reads `drift_detected` only to decide whether an investigation was required, through a new `DRIFT_DETECTED` env from `needs.plan-and-analyze.outputs.drift_detected`. A `'true'` value never by itself fails it.
    - The workflow header comments state the policy.
    - Only `Require Investigation Success`, the workflow comments, the tests and the documentation change. The scripts, outputs, uploads and the other jobs stay as they are.
  - [x] **AI workflow drift report gate (decision 6, user-approved 2026-10-05)**: the `ai-analysis.yml` gate validates the public drift report contract.
    - A valid public report with `outcome: failed` → UNKNOWN, no AI analysis, no artifact (job succeeds, as today).
    - A present report that is invalid or not the public contract (e.g. an internal-format report) → the CI job **fails**, with no result artifact (a wiring/privacy violation, not a detection result).
    - A missing artifact → UNKNOWN, no AI (unchanged).
  - [x] **AI workflow** (amended 2026-10-05: no separate investigation gate step; `ai-analysis` validates and binds the investigation itself, exit 1 → job fails with no artifact; `--investigation` is passed only when the file is present): downloads `drift-investigation-<source run id>` by pattern. Missing → report v2 with `not_investigated`. Present → validated and bound, else the job fails with no artifact. An unbindable investigation (`report_invalid` / `report_mismatch`) fails in the drift workflow before upload (Task 9B.4 D3). `AI_LLM_PROVIDER: none` unchanged; counts-only summary.
  - [x] **Hygiene**: no public log or summary carries a G11-forbidden value (scanned in executed-step tests) in any step 9B.5 adds or changes. The pre-existing Phase 5 diagnostic output is a Phase 12 known limitation (amended 2026-10-05). Raw and restricted files are never uploaded.
  - [x] **Public drift report wiring (Task 9B.4A, P1/P3)**:
    - **Runner layout (amended 2026-10-05, item 1)**:
      - the public report stays at today's path `${RUNNER_TEMP}/drift/drift_report.json`, beside `detection_run.json`, so the artifact root is unchanged (`upload-artifact` roots a multi-path artifact at the paths' common ancestor) and the upload paths, the cost step's `DRIFT_REPORT` and the `test_infracost.py` path assertion are unchanged;
      - the internal report is written to a separate runner-only directory (e.g. `${RUNNER_TEMP}/drift-internal/drift_report.json`, created 0700) that no upload lists;
      - `Analyze Drift` runs `drift-engine analyze --output <internal> --public-output <public>` and derives `has_drift` and the classification counts from the public file, which must exist (engine exit 0, public present and valid; else UNKNOWN);
    - **Investigation binding check (amended 2026-10-05, item 2)**: `scripts/investigation_analysis.sh` runs `drift-engine investigation-check --public <public investigation> --report ${RUNNER_TEMP}/drift/drift_report.json` (the public drift report, never the internal one) before any upload. A failure means no upload and the fixed failure code `binding_check_failed`. This also enforces Task 9B.4 D3 in CI: an unbindable investigation (null binding hash) fails here;
    - `drift-report-<run_id>` contains exactly the public `drift_report.json` and `detection_run.json`;
    - `investigate` receives the internal report, while every downstream job (issues, report, cost check, AI) receives the public one;
    - the `ai-analysis.yml` gate step validates the public drift report contract (it currently validates `DriftReport`; Task 9A.1 amendment);
    - the cost step binds to the public report;
    - a projection failure gives `drift_detected=unknown` with no artifact uploaded (executed-step test).
  - **CI Activity Log authentication fix (user-approved 2026-10-09, Option A plus a sanitized diagnostic; 🔒 locked 2026-10-09; revised and re-locked 2026-10-09 with the four audience-validation adjustments, user-approved; design review in Implementation Notes)**:
    - [x] **Credential scope (Option A)** (implemented 2026-10-09; see Completion Notes, "CI Activity Log authentication fix"):
      - `AzureMonitorSource` creates `MonitorManagementClient` with `credential_scopes` exactly `["https://management.core.windows.net//.default"]`. This is the Azure Resource Manager audience Azure CLI caches at `az login`.
      - `AzureCliCredential` therefore runs `az account get-access-token --resource https://management.core.windows.net/`. In CI this is answered from the token cached at login, so the GitHub OIDC assertion (about 5-minute lifetime) is not reused after the G8 settle wait.
      - **Unchanged**:
        - `AzureCliCredential` only (Task 7.1 rule; never `DefaultAzureCredential`, `ClientAssertionCredential` or a secret);
        - the request target (`base_url` `https://management.azure.com`), the GET-only Activity Log path allowlist and the no-redirect setting;
        - limits, retries and the fixed error codes;
        - the workflow, job permissions, secrets, the federated credential, RBAC and every G-decision.
    - [x] **Sanitized authentication diagnostic (minimal)** (implemented 2026-10-09): the restricted, runner-only evidence's per-scope `error` gains one optional field, `auth_reason`.
      - It is present only when `code == "authentication_failed"`. The model rejects it with any other code, and rejects a missing value with that code.
      - Fixed values:
        - `assertion_expired`: `AADSTS700024`;
        - `federation_mismatch`: `AADSTS70021`, `AADSTS700213`;
        - `other_aadsts`: any other AADSTS number;
        - `no_aadsts`: the credential failed without an AADSTS number;
        - `arm_rejected`: Azure Resource Manager answered HTTP 401.
      - Only the number after `AADSTS` is matched (in memory) from the exception text, mapped through this allowlist, then discarded. The exception text, any AADSTS number, trace or correlation IDs, timestamps and tenant or client IDs never reach any document, log, output or summary.
      - **Implementation note (2026-10-09, review M1, user-approved)**: this rule also covers azure-identity's own record of a failed token request (`"<credential>.get_token_info failed: <exception>"`, logged at WARNING and printed on standard error by Python's last-resort handler). A redaction filter on the `azure.identity` loggers keeps the record but reduces each exception argument to its type name and drops any traceback. **Extended (2026-10-09, review N1, user-approved)**: the same filter drops every `azure.identity` record below WARNING, which covers the pre-formatted DEBUG account-details record of a successful token request (client ID, tenant ID, UPN, object ID). No other logger is affected.
      - `evidence_version` stays `"2"` (an additive, runner-only field). An evidence document without an authentication failure renders byte-identically to today.
      - `scripts/investigation_analysis.sh` adds `auth_<reason>=<count>` to `investigation_detail`. These are fixed `[a-z_]` codes, e.g. `authentication_failed=1,auth_assertion_expired=1`.
      - **Unchanged**: the public investigation contract, the public drift report, the AI report, the G11 privacy profile and the status vocabulary of the outcome mapping.
    - [x] **Audience acceptance, checked against the real Activity Log API (fake tests alone are insufficient)** ((a1) ✅, (a2) ✅ and (b) ✅ 2026-10-09):
      - **(a) Local, read-only, user-approved at execution time**, with the user's own `az login` session (real `AzureCliCredential`, real Activity Log API):
        - **(a1) Pre-implementation go/no-go gate (adjustment 1)**: the current, unchanged `AzureMonitorSource` with an in-memory scope-pinning credential wrapper (`check_arm_audience.py`, scratchpad) requesting `https://management.core.windows.net//.default`.
          - The `aud` claim of **the exact token sent with the request** equals `https://management.core.windows.net/`.
          - One bounded GET of one page for `aitdd-dev-main-rg` over the last 60 minutes completes.
          - Any other result (401, another code, a wrong `aud`) means Option A is invalid: stop, and return to the design review before any implementation.
          - **Result (2026-10-09, user-approved run; ✅ go)**:
            - local Azure CLI **2.84.0**; `aud_match=True` (the token actually sent carried `https://management.core.windows.net/`);
            - outcome `complete`, code `none`, HTTP **200**, **one GET**, retry 0, event count **0**. There were no Activity Log events for the group in the last 60 minutes; the token is validated before results are returned, so HTTP 200 shows the audience was accepted.
            - **Proven**: local API compatibility. The Activity Log API on `https://management.azure.com` accepts a `https://management.core.windows.net/`-audience token through the project's request path (user principal, local session).
            - **Not proven by this check**: the CI behaviour. That covers the login-cache hit on the runner's Azure CLI 2.90.0 / MSAL 1.36.0, the pipeline service principal's access, and success after the settle wait. Only check (b), the drifted CI run, proves those.
        - **(a2) Post-implementation repeat**: the same check through the **fixed** `AzureMonitorSource`, without the wrapper, before any push.
          - **Result (2026-10-09, user-approved; ✅)**:
            - script `check_arm_audience_fixed.py` (scratchpad): the fixed source creates its own `AzureCliCredential`. A recording transport reads only the `aud` of the bearer token actually sent.
            - local Azure CLI **2.84.0**; `ARM_CREDENTIAL_SCOPE` is the cached audience: `True`; `aud_match=True`;
            - outcome `complete`, code `none`, HTTP **200**, **one GET**, event count **0**.
            - As with (a1), this proves local API compatibility only. The CI cache hit, the pipeline principal and the post-wait behaviour remain for (b).
        - **Safety rules (adjustment 2)**:
          - The token and its claims stay in memory. Only `aud` is decoded and printed; no other claim, no token, no subscription ID, no event content, no exception text.
          - Output is limited to the Azure CLI version, `aud` match, the fixed outcome or error code, HTTP status and event count.
          - Exactly one GET of one page, through the project's GET-only path allowlist with no redirects: `retry_total=0`, short timeouts, one resource group, a 60-minute window.
          - SDK logging is disabled; the check writes no file and no bytecode.
          - Acknowledged side effect: Azure CLI may cache the token in its own token cache (`~/.azure`), as any `az` ARM command does.
        - **Versions recorded (adjustment 3)**:
          - the local Azure CLI version at each check;
          - the CI runner: image `ubuntu-24.04` 20261004.327 (run #28) ships Azure CLI 2.90.0 with MSAL 1.36.0. The runner image manages it; this project does not pin it.
          - Every real CI proof records the runner image version.
      - **(b) Real CI, decisive for the pipeline service principal**: the drifted run below. This proves Azure Resource Manager accepts the cached-audience token from the pipeline identity after the settle wait, and proves the login-cache hit on the runner's Azure CLI version.
        - **Result (run #29 `37961189506`, 2026-10-09; ✅)**:
          - runner image `ubuntu-24.04` 20261004.327.1 (Azure CLI 2.90.0 per the image's software list);
          - OIDC login 16:43:55–16:44:02 UTC; `Drift Investigation` 16:44:32–16:54:32 (10m00s settle wait), so the Activity Log query ran about 10.5 minutes after login;
          - `investigation_status=succeeded`, `investigation_detail=none` (no `authentication_failed`, `all_queries_failed`, `auth_*`, query-failure or limit code), outcome `complete`.
        - Before the fix, the same timing gave `authentication_failed` on runs #24/#25.
    - [x] **Real drifted CI proof (approval-gated; Azure change by the user only, Execution Rule 10)** (run #29, 2026-10-09; all checks passed):
      - The user adds one test tag to `aitdd-dev-main-rg` in the Azure Portal. The user approves the commit/push of the fix and one `workflow_dispatch` on that commit; run #28 is the in-sync anchor.
      - Required results:
        - the run concludes **success**: plan exit `2`, `drift_detected=true`, `external_drift` on `tags.<key>`;
        - `Drift Investigation` lasts at least the 10-minute settle wait, so the query ran after the wait;
        - `investigation_status` is `succeeded`, or `incomplete` with the G18 warning;
        - `investigation_detail` has **no** query-failure, limit or `auth_*` code (in particular no `authentication_failed` or `all_queries_failed`);
        - the public investigation's `binding.evidence_outcome` is `complete`;
        - the `investigation`, `issues` and `cost` jobs and the triggered AI analysis succeed;
        - every public artifact passes the identifier scan used for run #28;
        - the runner image version (and with it the Azure CLI version) is recorded.
      - **Result (2026-10-09, user-approved; the user added the test tag `owner`, a 4-character value read but never printed; dispatched by Claude through the signed-in in-app browser)**:
        - **Run**: **#29**, id `37961189506`, <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37961189506>.
          - `workflow_dispatch`, `main`, commit `62bdf65`, attempt 1, environment `dev`;
          - 2026-10-09T16:43:40Z, total 11m 19s; runner image `ubuntu-24.04` 20261004.327.1 (Azure CLI 2.90.0). **Conclusion: success.**
        - **Pre-checks (read-only)**:
          - working tree clean; `HEAD` = `origin/main` = `62bdf65`;
          - the only dispatch input is `environment` (choice `dev`); no run in progress;
          - `aitdd-dev-main-rg` tags: the three configured tags unchanged plus `owner`.
        - **Verified from the public run data** ✅:
          - **Jobs**: all success: Preflight 6s, Terraform Plan & Drift Analysis 10m 47s, Drift Investigation 14s, Drift Issues 13s, Cost Estimate 6s, Report & Summary 5s.
          - **Report & Summary**: Result **VALID**, drift status **detected**, `drift_detected` **`true`**, plan exit code **2**, classification `{"external_drift":1,"in_sync":4}`.
          - **Annotation**: "Drift detected in dev (a valid result, not a pipeline failure)". There is no error annotation (Node.js 20 / Ubuntu 26 notices only).
          - **Step timing**: `Drift Investigation` 16:44:32 → 16:54:32 (10m00s, at least the settle wait).
          - **Investigation job**:
            - status `succeeded`, failure `none`, detail **`none`**;
            - upload `success`, verification `success`;
            - outcome `complete`, resources 1, verdicts `sole_capable_operation=1`, anchors examined 28 / accepted 5.
            - The job passed (G18).
          - **Drift Issues**: created 1 (issue **#7**, "Drift detected: module.resource_group.azurerm_resource_group.this["main"] (dev)"), 0 updated or closed. The issue body is structure-only: no GUID, email or `/subscriptions/` path; the live tag value and the three live account identifiers (compared in memory) are absent.
          - **Cost Estimate**: success, 0 USD, run `github-37961189506-1`.
          - **Triggered AI analysis**: run **#12** `37962525812` (<https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37962525812>), success (26s): 1 resource, 2 remediation options, 0 of 6 AI sections, investigation `complete`, LLM `none` / `not_attempted`.
          - **Artifacts** (expire 2026-11-08):

            | Artifact | Size | Digest |
            | --- | --- | --- |
            | `drift-report-37961189506` | 1,749 B | `sha256:387d3fd904d7f104341a9b72684a129b01a050be17cac6bdca3393d89908f37a` |
            | `drift-investigation-37961189506` | 1,287 B | `sha256:94b48974590197648270a4568139d596389339fc40d4c02dc3736404f003aebb` |
            | `infracost-report-37961189506` | 941 B | `sha256:7df03e714688755377535ca6ca834187caf413c56d07f6dcf28d63c23fec5db5` |
            | `ai-analysis-report-37961189506` | 8,436 B | `sha256:4ba0fe08a5b68a3a83037a3cafd4baf365bf3d5485eb7a4938f41e8fecd1d494` |

          - **Time budget (G18 note)**: `plan-and-analyze` 10m 47s against the 45-minute limit; the settle wait dominated.
        - **Artifact verification (2026-10-09)** ✅, on the four original ZIPs the user downloaded into `.artifacts/task-9B.5-drift-proof/`:
          - **Digests**: each ZIP's SHA-256 equals its GitHub digest (`387d3fd9…`, `94b48974…`, `7df03e71…`, `4ba0fe08…`).
          - **Inspection**: listing showed flat regular-file entries only; each ZIP was extracted into its own folder under `extracted/`. Exactly 7 files, no symlinks.
          - **Checks**: scratchpad script `verify_9b5_drift_proof.py` with the project's own validators. **35 of 35 passed**, plus the two CI checkers:
            - **File lists**: `drift_report.json` + `detection_run.json`; `drift_investigation.json`; `cost_run.json` + `infracost.json`; `ai_analysis_report.json` + `.md`.
            - **Public drift report**:
              - validates as `PublicDriftReport` and against `schemas/drift_report.public.schema.json` (0 errors);
              - `public_version: "1"`, `succeeded`, `has_drift: true`, `{"external_drift":1,"in_sync":4}`, `run.run_id` `github-37961189506-1`;
              - the manifest shows plan exit `2` and commit `62bdf65`.
              - No JSON file in any artifact satisfies the internal `DriftReport` contract.
            - **Public investigation**:
              - validates as `PublicInvestigation`: `public_version: "1"`, outcome `complete`, no failure;
              - **`binding.evidence_outcome: "complete"`**;
              - one resource with verdict `sole_capable_operation`;
              - exposure: `caller_identity`, `resource_id`, `event_id` and `correlation_id` `withheld`, `who_path: local_only`;
              - `drift-engine investigation-check` against the downloaded public report: `valid`, exit 0.
            - **AI report**:
              - `report_version: "2"`; `verify_report` (schema and binding to the drift report and investigation) and `verify_markdown`: no problems;
              - 1 resource, `has_drift: true`, investigation `complete`;
              - recorded caller `status: recorded`, `caller_type: user`, `client_app: azure_portal`, `pipeline_identity: false`, **`identity: withheld`**;
              - LLM `none`, not attempted, `evidence_sent: []`, `investigation_sent: []`.
            - **Three-way hash**: the canonical SHA-256 of the downloaded public drift report is **`7ce635b628a15dbbd934db5eda4a2baceeb60bb2ec68bd6acde01cf828efc1b0`**.
              - The `ai_engine`, `sanitize_infracost` and `investigation_public` implementations all compute that value.
              - It equals `cost_run.json` `drift_report_sha256`, the investigation's `binding.drift_report_sha256` and the AI `provenance.drift_report_sha256`.
              - AI `provenance.investigation_sha256` `fc1b9474…b6c9d0` equals the canonical hash of the investigation. Cost and AI run ids are `github-37961189506-1`.
            - **Cost**: `scripts/sanitize_infracost.py --check` against the downloaded drift report and run id: exit 0.
            - **Identifier scan** of all 7 files:
              - the G11 `leak_findings` scanner: no finding;
              - no GUID, no `/subscriptions/`, `/providers/` or `/resourceGroups/` path, no email or UPN, no IPv4 outside the configured `10.10.` CIDRs, no token-like string;
              - the live subscription ID, tenant ID and signed-in user name (read locally, never printed) appear in no file. The signed-in user is the identity Azure recorded for the portal tag change, so WHO stays withheld publicly.
          - **Git**: all 11 files under `.artifacts/task-9B.5-drift-proof/` are ignored (`.gitignore:40`); nothing under `.artifacts` is tracked.
        - **Back in sync (2026-10-09)**: the user removed the `owner` tag (portal). A read-only check showed exactly the three configured tags. The user-requested in-sync verification run:
          - **Run #30**, id `37963733177` (<https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37963733177>), `workflow_dispatch`, `main`, commit `62bdf65`, 2026-10-09T17:05:03Z, 1m 26s. **Conclusion: success**, all 6 jobs success.
          - Report & Summary: Result **VALID**, drift status `none`, `drift_detected` **`false`**, plan exit code `0`, `{"in_sync":5}`.
          - Investigation `succeeded` / `complete`, detail `none`, 0 resources, no anchor fetch.
          - **Drift Issues closed issue #7** (`state_reason: completed`, 2026-10-09T17:06:26Z): Task 8.3 on a real run.
          - Cost 0 USD. Triggered AI analysis run #13 `37963912084`: success.
          - Artifacts:

            | Artifact | Size | Digest |
            | --- | --- | --- |
            | `drift-report-37963733177` | 1,498 B | `sha256:65fedd655bd2eac323696db692638538b8e67800848820561a7b8e1f7c237cf4` |
            | `drift-investigation-37963733177` | 681 B | `sha256:797c74752e2c5e1bca2766057bb31b1adbfdaa80aff0c1337331cd2ee820239e` |
            | `infracost-report-37963733177` | 940 B | `sha256:4b6b5441c80bf2e3d9604c6caa6113239db23a12ab5e1f02a2a063d99dd9aa7c` |

          - **Run #30 is the in-sync anchor for Task 9B.6** (retained until 2026-11-08). *(Note 2026-10-10: per G9, Task 9B.6 uses the latest in-sync report before its primary run, so a later in-sync scheduled run supersedes run #30.)*
      - **Afterwards**:
        - the user removes the test tag;
        - the next no-drift run (scheduled or dispatched) becomes the fresh in-sync anchor for Task 9B.6, and Task 8.3 closes the issue that the drifted run opened;
        - Task 9B.6 does not reuse this run: one task at a time (Execution Rule 8).
- **Validation**:
  - [x] Workflow-structure tests and executed-step tests (runner-realistic, as in Task 10.1).
  - [x] Synthetic gate tests for every failure code and the missing/invalid investigation paths.
  - [x] Executed-step tests (amended 2026-10-05) for:
    - every row of the investigation outcome mapping, incl. decision 1 (uploaded, job fails; amended by G18 for `incomplete`, see the G18 tests below) and decision 2 (no `investigate` after a failed fetch);
    - the anchor-fetch filters, limits, size caps and per-candidate failures (fake GitHub API);
    - the no-drift path skipping the fetch;
    - the `investigation` job's pass/fail condition;
    - the absence of any step-level timeout on `Drift Investigation`.
  - [x] Pin closure test for `ci/azure-constraints.txt`.
  - [x] **G18 tests (2026-10-09)** (results in Completion Notes, "G18 implementation"):
    - `Require Investigation Success` matrix:
      - `incomplete` + upload success + verification success → passes and prints the `::warning::`;
      - `incomplete` with a failed upload, or with a failed verification → fails;
      - `succeeded` → passes; `failed` → fails, with `drift_detected` `'true'` and `'false'` (unchanged rows);
      - an empty status with `drift_detected='true'` → fails (required, never ran);
      - an empty status with `drift_detected='false'` (upload and verification `skipped`) → passes, with "not required: no drift" in the summary;
      - `drift_detected='true'` with `succeeded` and success everywhere → passes, so drift alone never fails the step.
    - Executed-step test of `Generate Plan Evidence`, with a fake `scripts/generate_plan_json.sh` that writes the manifest:
      - plan exit 0 and plan exit 2 with `outcome: succeeded` → the step exits 0 and passes `plan_exit_code` through;
      - script exit 1 with a failed manifest, script exit 64 (stale manifest ignored), an unexpected `plan_exit_code` with script exit 0, or a modified lock file → the step fails, and `Analyze Drift` (when it runs) yields `unknown`.
      - Until now this was covered only by the uncommitted Phase 5 harness.
    - Structural guard:
      - no job `if:` and no pass/fail step treats `drift_detected == 'true'`, `has_drift` true or plan exit 2 as a failure;
      - `Require Investigation Success` uses `drift_detected` only in the required/not-required decision (no failure branch keyed on `'true'` alone);
      - `issues`, `cost` and `investigation` run for both `'true'` and `'false'`.
    - Full suite, `actionlint` + shellcheck and `./scripts/validate.sh` pass.
  - [x] Real CI proof (approval-gated, on the G18 implementation): one no-drift `workflow_dispatch`. Before it, the user removes any leftover test tag from `aitdd-dev-main-rg` (e.g. `owner` from the 2026-10-04 test), so the resource group is in sync; this run later serves as the Task 9B.6 anchor. The investigation step runs with no Azure query, the artifact is present, the `investigation` job passes, and the AI report v2 shows no drifted resources and no investigation claims.
    - **Also verified (amended 2026-10-05, item 7)**:
      - `drift-report-<run_id>` contains only the public `drift_report.json` (with `public_version`) and `detection_run.json`, and no internal report is present in any artifact;
      - the issues and cost jobs pass on the public report;
      - the cost binding hash (`cost_run.json`), the public investigation's `binding.drift_report_sha256` and the AI report's `provenance.drift_report_sha256` all equal the canonical SHA-256 of the downloaded public drift report.
    - **Result (2026-10-09, run #28 `37948472263`; details in Completion Notes)**:
      - **Passed, every part**: the main criterion (including "no Azure query" and "no investigation claims") and all three item-7 checks.
        - The run data was checked on 2026-10-09.
        - The four downloaded artifacts were checked on 2026-10-09 (results in Completion Notes, "Artifact verification").
  - [x] **Activity Log authentication fix tests (2026-10-09)** (results in Completion Notes):
    - **Scope**:
      - a fake credential records the requested scopes: exactly `https://management.core.windows.net//.default`;
      - every request still goes only to `https://management.azure.com` and the Activity Log path (existing allowlist and blocked-request tests unchanged and passing).
    - **Through the real `AzureCliCredential`**: a fake `az` on `PATH` records its arguments: `account get-access-token --output json --resource https://management.core.windows.net/`, and never `https://management.azure.com`.
    - **CI mechanism reproduced**: a fake `az` answers only the login-cached resource and fails every other resource with an `AADSTS700024` message.
      - Before the scope change the collection fails with `authentication_failed` / `auth_reason: assertion_expired`; after it, the scope completes.
      - This is shown on the real `collect_evidence` path, with a fake transport for the HTTP side.
    - **Diagnostic mapping**:
      - each allowlisted AADSTS number maps to its fixed reason;
      - an unlisted number maps to `other_aadsts`, no number to `no_aadsts`, and an Azure Resource Manager 401 to `arm_rejected`;
      - `auth_reason` with any other code, or a missing reason with `authentication_failed`, is rejected by the model;
      - fixtures with a synthetic tenant/client GUID, an email, a trace ID and a timestamp in the exception text: none of them appears in the evidence, the logs, the script output or `investigation_detail`;
      - evidence without an authentication failure is byte-identical to the current rendering.
    - **Script**: `investigation_detail` counts `auth_<reason>` codes; the counts-only output line and the step summary stay within the fixed-code regexes.
    - **Regression**: full suite, `unittest discover`, `actionlint` + shellcheck, `shellcheck scripts/investigation_analysis.sh`, `./scripts/validate.sh`.
  - [x] **Audience acceptance checks (a1), (a2) and (b)** recorded with results and versions, see the acceptance criterion above. (a1), (a2) and (b) (run #29) are recorded.
- **Implementation Notes**:
  - Starts with a design review (step and job names, the exact exit-code mapping, the anchor-fetch limits). Done 2026-10-05 (below).
  - **Pre-implementation review (2026-10-05, items 1–8 and decision 6 user-approved)**: recorded in the criteria above.
    - **Sequencing (item 8)**: Task 9B.4A cannot reach `main` alone (its limitation (a)). Tasks 9B.4, 9B.4A and 9B.5 are committed and pushed together before the approval-gated real CI proof.
    - **Scope**: the existing Phase 5 diagnostic-log exposure (`plan.log` tail, `az account show`) is out of 9B.5's scope and recorded as a Phase 12 known limitation. 9B.5's hygiene criterion covers the steps 9B.5 adds or changes.
    - Unchanged by design: the issues job and `scripts/github_automation.py`, the cost job and the `Infracost Cost Estimate` report path, the `report` job, the AI CLI and the investigation binding code.
  - **Design review (2026-10-05, user-approved: decisions 1 and 2 and the remaining design)**: job/step boundaries and names, runner isolation and time bounds (G10); anchor fetch (G9); the outcome mapping and the `investigation` job result (criteria above); upload sequencing (upload drift report → investigation → upload investigation if publishable → cost, unchanged and independent of the investigation); the AI gate (decision 6); the D5 always-exit-0 pattern with a final `Require Investigation Success` step.
  - **CI result policy review (2026-10-09, user-approved Q1/Q2 → G18)**. The requirement reviewed: "drift detection is a successful finding, not a CI failure".
    - **Already satisfied, no change**:
      - the plan script accepts plan exit `0 | 2`, and the evidence step accepts both;
      - `drift-engine analyze` exits 0 for drift and for no drift;
      - `Analyze Drift` writes `drift_detected=true` with a `::warning::` and exits 0;
      - the drift report is uploaded for drift;
      - `issues`, `cost` and `investigation` run for both `'true'` and `'false'`;
      - process errors give `unknown` and fail the run;
      - the investigation never changes `drift_detected`;
      - a missing or failed investigation gives `not_investigated` / `investigation_failed` in the AI report, never "no drift";
      - `ai-analysis.yml` is gated on the artifact, not the source run's conclusion.
    - **Gap**: `Require Investigation Success` failed on `incomplete`. `incomplete` (some drifted resource `not_investigated`) can only occur when drift exists: a no-drift run has no drifted resources and is always `complete`. So a drift finding alone could turn the run red. Resolved by amending decision 1 (G18).
    - **Kept red by decision (Q2)**: an investigation `failed` outcome, including anchor-fetch and Activity Log query failures. They also occur only on drifted runs, but they are process errors of the investigation concern. They never touch `drift_detected` or the drift artifact.
    - **Revision (2026-10-09, user clarification; G18 locked)**: "never ran" fails the `investigation` job only when the investigation was required, which means a drifted run. A no-drift run with no investigation passes. The current design still runs the investigation on no-drift runs, so this rule only guarantees that an intentional skip can never turn a no-drift run red. `Require Investigation Success` reads `drift_detected` for this decision only.
    - **Test gap**: no committed test executed the `Generate Plan Evidence` step block with plan exit 2 (only the uncommitted Phase 5 harness did). Closed by the G18 tests.
    - **Not changed (residual risk, recorded)**: the time budget stays as approved in G10 (fetch 300 s, `investigate` 1500 s, `plan-and-analyze` 45 min).
      - On a drifted run, the worst case of these bounds plus the other steps comes close to the job limit.
      - A job timeout would fail `plan-and-analyze` itself.
      - The real drift run of Task 9B.6 records the actual durations.
  - **Activity Log authentication design review (2026-10-09, read-only; user-approved Option A plus a sanitized diagnostic; 🔒 locked)**:
    - **Observed** (public run data):
      - Run #25: OIDC login finished 08:04:11. `Drift Investigation` ran 08:04:49 → 08:14:49 (the G8 settle wait). The single Activity Log query ran at about 08:14:48, about 10.6 minutes after login, and failed within a second. Run #24 shows the same pattern.
      - Detail `authentication_failed=1,all_queries_failed=1`.
      - Not `authorization_failed` (403), so Reader permission is not the cause. Not `credential_unavailable`, so the Azure CLI session existed (`azure-identity` 1.26.0 maps a plain "run az login" without `AADSTS` to that code).
      - No-drift runs never request a token, which is why they pass.
    - **Code path** (pinned packages and Azure CLI 2.91 source, read in the scratchpad):
      - `azure-mgmt-monitor` 7.0.0 requests `https://management.azure.com/.default`. `AzureCliCredential` turns that into `az account get-access-token --resource https://management.azure.com`.
      - After the OIDC login, Azure CLI keeps the GitHub OIDC token as a static `client_assertion` for MSAL `ConfidentialClientApplication`.
      - At login it lists subscriptions with the scope `https://management.core.windows.net//.default` (`active_directory_resource_id`), so only that token is cached.
      - MSAL 1.39 answers `acquire_token_for_client` from the cache only on an exact scope match. The later `management.azure.com` request therefore goes to Entra ID with the original assertion.
    - **External**: GitHub's documented example OIDC token has `exp − iat = 300 s`. Azure/login issue #441 reports a 5-minute token and later `AADSTS700024` failures.
    - **Conclusion**:
      - The cache miss re-sends the expired GitHub assertion, which Entra ID rejects. This is the mechanism consistent with all evidence.
      - The exact AADSTS code is not recorded: it was only in a runner-only log that is never uploaded. The only remaining alternative is a Resource Manager 401.
      - The sanitized diagnostic makes any recurrence distinguishable without exposing values.
    - **Options considered**:
      - **A**: use the cached audience (chosen; smallest, no rule change).
      - **B**: pre-warm the token after login (timing-dependent; changes a completed Phase 5 step).
      - **C**: fresh assertion via `ClientAssertionCredential` (would break the "`AzureCliCredential` only" rule and expose the OIDC request credentials to Python).
      - **D**: re-login after the wait (contradicts the locked G10 one-step design).
    - **Trade-offs of A (accepted)**:
      - It depends on Azure CLI caching the ARM-audience token at login. A future Azure CLI or `azure/login` change could reintroduce the failure; the diagnostic and the scheduled runs would show it.
      - The cached token must outlive the investigation. Service-principal tokens default to about 1 hour, versus at most about 27 minutes of use after login (fetch ≤ 300 s, `investigate` ≤ 1500 s).
      - Local `drift-engine` use with a user `az login` requests the same audience; Azure CLI itself calls Resource Manager this way.
    - **Compatibility evidence (adjustment 4; read-only, from the pinned code, 2026-10-09)**:
      - `azure-identity` 1.26.0 `_scopes_to_resource("https://management.core.windows.net//.default")` gives `https://management.core.windows.net/` (trailing slash kept). Azure CLI `resource_to_scopes` turns that back into exactly the login-cached scope. Today's `https://management.azure.com/.default` maps to `https://management.azure.com`, a different scope.
      - Azure CLI's own `az monitor activity-log list` (AAZ `MgmtClient`) calls `/subscriptions/{id}/providers/Microsoft.Insights/eventtypes/management/values` (API 2015-04-01) on `resource_manager` (`https://management.azure.com/`) with `credential_scopes = resource_to_scopes(active_directory_resource_id)`, i.e. this same audience.
      - MSAL (1.36.0 on the runner, 1.39.0 in Azure CLI 2.91.0): `acquire_token_for_client` answers from the cache first. A failed proactive refresh of an aging token falls back to the still-valid cached token; only a fully expired token is re-requested with the assertion.
      - Azure CLI 2.90.0 against 2.91.0: the auth code paths used here are identical (the differences are macOS broker and a removed cloud).
      - Microsoft documentation: the `management.core.windows.net` audience expects the trailing slash (MSAL guidance), and Resource Manager's wrong-audience error lists `https://management.core.windows.net/` as allowed (Microsoft Q&A).
      - No official page lists Resource Manager's accepted audiences, hence the real checks (a1), (a2) and (b).
    - **Plan impact**: no G-decision changes and no locked rule changes.
      - The Task 9B.1 evidence contract gains one optional runner-only field, recorded as an amendment there.
      - Task 9B.5's Files/Areas, criteria and validation are amended above.
- **Completion Notes** (implementation and local validation 2026-10-05; real CI proofs and completion 2026-10-09):
  - **Files**:
    - workflows: `.github/workflows/drift-detection.yml`, `.github/workflows/ai-analysis.yml`;
    - new: `ci/azure-constraints.txt` (23 exact pins, resolved for CPython 3.12 linux x86_64, equal to `ci/ai-constraints.txt` on every shared package), `scripts/investigation_analysis.sh`, `scripts/fetch_prior_drift_reports.py` (stdlib only), `tests/test_investigation_workflow.py`;
    - changed tests: `tests/test_infracost.py` (step order, two `continue-on-error` uploads), `tests/test_ai_cli.py` (public gate, decision 6, investigation download/argument, summary row), `tests/test_github_automation.py` (job list and permission blocks);
    - docs: `README.md` (investigation section, AI workflow, known limitations), `docs/drift-detection-spec.md` (§8.3 CI layout, a drift investigation paragraph, AI gate), `docs/architecture.md` (workflow access table).
  - **As designed**:
    - item 1: runner layout (internal in `drift-internal/` 0700; public at the old path; validity read from the public file);
    - item 2: the in-job public check;
    - item 3: the `investigation` job verifies against the downloaded public report;
    - the G10 names, outputs and permissions (`plan-and-analyze` 45 min, `actions: read`);
    - no step-level timeout (`timeout 1500` / `300` inside the script);
    - the G9 fetch rules (the token is never forwarded across the storage redirect; per-candidate failures → `report_invalid`);
    - decisions 1, 2 and 6.
  - **Implementation details within the design**:
    - the step block maps an unexpected crash of the orchestration script to `investigation_failure=script_error` (still exit 0, file removed);
    - the `investigation` job adds `Checkout Code` / `Setup Python` / `Install drift-engine` (runtime only, as the issues job) before verification;
    - `investigation_detail` also counts the evidence's own failure reason (e.g. `all_queries_failed`);
    - an archive entry is rejected only when it declares a non-regular file type (archivers may record none).
  - **Validation** (scratchpad venv, Python 3.13, AI and Azure constraints installed; no Azure, no real GitHub; loopback fake API; subprocesses without `az` and with an unroutable proxy):
    - `tests/test_investigation_workflow.py` **54 passed**, covering:
      - the workflow structure;
      - the executed `Analyze Drift` step (layout for drift, no drift and deletion; projection failure → UNKNOWN with nothing written; failed evidence);
      - every row of the outcome mapping, run through the real script with a scripted engine on real public documents;
      - the detail codes; the timeout bound (1500); setup failures with no `investigate`; the pinned install command; stale directories;
      - two real `investigate` runs: no drift (succeeded, no fetch, no Azure) and drifted with three fetched candidates (one accepted, two `report_invalid`) and no Azure credential (failed but bindable, uploaded);
      - fetch failure fails closed (no `investigate`); fetch filters, newest 50, archive rules, skips, retries, usage errors; fetched candidates fed to the real G9 trust checks;
      - `Require Investigation Success` matrix; counts-only summary; the step's `script_error` mapping;
      - Azure pins exact, aligned with the AI pins, equal to the installed `drift-engine[azure]` closure.
    - Full suite **2317 passed** (3,931 subtests); coverage 98.84%; `unittest discover` OK; `./scripts/validate.sh` passed.
    - `actionlint` (incl. shellcheck on every `run:` block) clean on both workflows; `shellcheck` clean on `scripts/investigation_analysis.sh`.
    - gitleaks: only the two pre-existing synthetic findings. None of the 41 identifier-like values of the local raw Activity Log capture appears in any change.
  - **Not done / limitations**:
    - (a) **Real CI proof: done** (2026-10-09: no-drift run #28, drifted run #29 and in-sync run #30, with all artifact checks). It needed 9B.4, 9B.4A and 9B.5 committed and pushed together (item 8; done in `26aa3a9`), the G18 change committed and pushed (done in `4ba7668`), then one no-drift `workflow_dispatch` after the user removes any leftover test tag (done: run #28 and its artifact checks, see "Real CI proof" and "Artifact verification" below). The hash equality across cost, investigation and AI is now verified on GitHub-hosted runner output (run #28). Isolation of an investigation failure was observed on real runners in scheduled runs #24 and #25.
    - (b) The Azure pins were resolved for CPython 3.12 linux x86_64 with pip's resolver report; locally they were installed and checked on 3.13. The CI exact-pin check is the 3.12 confirmation.
    - (c) The AI mutation corpus was not re-run (no `ai_engine` source changed in 9B.5).
  - **G18 implementation (2026-10-09; commit `4ba7668`, pushed; push-triggered `Phase 9 - Security Scan` `37944658696` and `Phase 2 - Terraform Azure Auth & Validation` `37944658966` both success)**:
    - **Files**:
      - `.github/workflows/drift-detection.yml`:
        - `Require Investigation Success` gains `DRIFT_DETECTED` env (`needs.plan-and-analyze.outputs.drift_detected`);
        - an empty status passes only when `DRIFT_DETECTED` is the literal `false`. The step then appends "Drift investigation: not required: no drift." to the step summary. Otherwise it fails with `::error::`;
        - `succeeded | incomplete` continue to the existing upload and verification checks;
        - `incomplete` then prints a `::warning::`;
        - every other status fails;
        - the workflow header and the `investigation` job comments state the G18 policy.

        No other step, condition, output, upload, script or job changed.
      - `tests/test_investigation_workflow.py`: 54 → 87 tests.
      - Docs: `README.md` and `docs/drift-detection-spec.md` §8.3 (policy wording, reviewed against the implementation: consistent). `docs/architecture.md` needed no change.
    - **Tests added or changed** (executed workflow `run:` blocks, as in the rest of the file):
      - **`Require Investigation Success` matrix (16 cases)**:
        - `succeeded`: passes with `true` and `false`; fails on an upload or verification failure;
        - `incomplete`: passes with exactly one `::warning::` only when uploaded and verified, else fails;
        - `failed`: fails with `true` and `false`, uploaded or not;
        - never ran: fails with `true`; passes with `false`, and the summary says "not required: no drift";
        - `unknown` or empty `drift_detected`: fails closed;
        - every failure prints `::error::` and "Drift result unaffected.".
      - **Drift independence (8 cases)**: for every status that ran, the result is identical for `drift_detected` `true` and `false`.
      - **`Generate Plan Evidence` executed** (fake `generate_plan_json.sh` in a temporary git repo, real `jq`/`git`), chained into the real `Analyze Drift`. Plan exit 0/2 → step exit 0, `plan_exit_code` passed through, no `::error::`. The classification decides drift:
        - `in_sync` (0) → `false`; `converged_drift` (0) → `true`;
        - `external_drift` (2) and `external_deletion` (2) → `true`, with the drift `::warning::`;
        - `config_change` (2) and `output_only_change` (2) → `false`.
      - **Evidence failures (5 cases)**: plan failed (script 1, failed manifest), unusable `ARTIFACT_DIR` (64, stale manifest ignored: `manifest_present=false`, job output falls back to `unknown`), unexpected `plan_exit_code` 3, provider lock modified, non-dev var file. Each fails the step with "Drift status: UNKNOWN."; where `Analyze Drift` runs afterwards it yields `drift_detected=unknown` and fails.
      - **Structural guard**:
        - every job or step `if:` that reads `drift_detected` accepts both `'true'` and `'false'`. These are exactly `Drift Investigation`, `Infracost Cost Estimate`, `issues`, `cost` and `investigation`;
        - no `if:` reads `has_drift`, `drift_status` or `plan_exit_code`;
        - the steps that read the drift result or plan exit code are exactly six, each executed by a test showing drift alone never fails it: `Generate Plan Evidence`, `Analyze Drift`, `Drift Investigation`, `Manage Drift Issues` (Phase 8 tests), `Require Investigation Success` and `Run Summary`.
      - **`Run Summary` executed**: `drift_detected` `true` and `false` with plan exit 2 → Result **VALID**, exit 0. A failed stage → "FAILED - drift status UNKNOWN", `drift_detected` `unknown`, still exit 0 (reporting only).
    - **Mutation check** (scratch copies of the workflow, restored and byte-compared afterwards). Each mutation was caught by the new tests:
      - `incomplete` fails again: 1 failing test;
      - the no-drift skip removed: 2;
      - `Analyze Drift` exits 1 on drift: 3;
      - plan exit 2 rejected by the evidence step: 4;
      - `issues` gated on `'true'` only: 1;
      - a missing investigation passes on a drifted run: 5.
    - **Validation** (scratchpad venv, Python 3.13, `.[dev,ai,azure]` with both constraint files):
      - `tests/test_investigation_workflow.py`: **87 passed**;
      - full suite: **2350 passed** (3,931 subtests); coverage 98.84% (gate 85%);
      - `unittest discover -s tests`: 950 OK;
      - `actionlint` 1.7.12 with shellcheck 0.11.0: clean on `drift-detection.yml` and `ai-analysis.yml`;
      - `shellcheck` clean on `scripts/investigation_analysis.sh` (unchanged);
      - `check-jsonschema` (GitHub workflow schema) OK;
      - `./scripts/validate.sh` (Terraform 1.14.7) passed.
    - **Not done**:
      - G18 is not yet proven on GitHub-hosted runners;
      - the no-drift path is covered by the Task 9B.5 real CI proof, and the drift path by Task 9B.6;
      - the time-budget residual risk stays open until the 9B.6 drift run records job durations.
  - **Real CI proof, no-drift run (2026-10-09, user-approved; dispatched by Claude through the signed-in in-app browser)**:
    - **Pre-check (read-only, 2026-10-09)**:
      - `aitdd-dev-main-rg` tags equal the configured `common_tags` exactly (`environment=dev`, `project=ai-terraform-drift-detector`, `managed_by=terraform`); no `owner` or other extra key. The VNet and NSG carry the same three tags; the NSG has 0 custom rules.
      - The Activity Log shows user `tags/write` events on the group on 2026-10-04 11:04:58Z (the documented `owner` test) and 2026-10-07 13:54:08Z (most likely its removal; the log does not record values). No Azure change was made.
    - **Run**: **#28**, id `37948472263`, <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37948472263>.
      - `workflow_dispatch`, `main`, commit `4ba7668`, attempt 1, environment `dev`;
      - 2026-10-09T15:00:38Z, total 1m 29s. **Conclusion: success.**
    - **Jobs**: all **success**.
      - Preflight 5s; Terraform Plan & Drift Analysis 58s; Drift Investigation 13s; Drift Issues 14s; Cost Estimate 7s; Report & Summary 3s.
      - Annotations: Node.js 20 deprecation and Ubuntu 26 notices only; no error, no drift warning.
    - **Report & Summary**:
      - Result **VALID**, failed stage none, drift status **none**, `drift_detected` **`false`**;
      - plan exit code `0`, classification `{"in_sync":5}`;
      - backend initialised and validated; artifact `drift-report-37948472263`.
    - **Drift Investigation** job summary:
      - status `succeeded`, failure `none`, detail `none`;
      - upload `success`, verification `success`;
      - outcome `complete`, resources 0, verdicts none, anchors examined 0 / accepted 0 (no fetch on a no-drift run, as designed).
    - **Drift Issues**: outcome ok, 0 created / updated / closed. **Cost Estimate**: 0 USD, run `github-37948472263-1`.
    - **Artifacts** (Actions API, expire 2026-11-08):

      | Artifact | Size | Digest |
      | --- | --- | --- |
      | `drift-report-37948472263` | 1,494 B | `sha256:10c3a82df4ec8d298859f9356983b5350c0c48e08dd1d6e9a625bd775960620f` |
      | `drift-investigation-37948472263` | 680 B | `sha256:22a4c2863cd7719d473b206190b9bafd775d2b7c2581e7a155a524a0e756fb2a` |
      | `infracost-report-37948472263` | 941 B | `sha256:c8b039d913e0f6196823d86dbb548244842ac280d374172671c0c45f98787d30` |

    - **Triggered AI analysis**: run **#11**, id `37948669003` (<https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37948669003>), commit `4ba7668`. **Conclusion: success** (29s).
      - Summary: source run `37948472263` attempt 1; resources 0; remediation options 0; AI sections analysed 0 of 6; investigation `complete`; LLM `none` / `not_attempted`.
      - Artifact `ai-analysis-report-37948472263`: 3,937 B, `sha256:f578f6ff022c9f49cb3c907baa8c2e47bbeaf7fe1a96f4d80b7258b2eb7615c7`.
    - **Artifact verification (2026-10-09, user-approved download)**:
      - **Download**: the user downloaded the four original ZIPs into `.artifacts/task-9B.5-ci-proof/` (gitignored). Their SHA-256 equals the GitHub digests above, and the AI ZIP equals `sha256:f578f6ff…7615c7`.
      - **Extraction**: each ZIP was extracted into its own folder under `extracted/`, after listing confirmed flat regular-file entries only (no directories, paths or symlinks).
      - **Checks**: scratchpad script with the project's own validators, Python 3.13, `.[dev,ai,azure]`. **34 of 34 passed**, plus the two CI checkers:
        - **File lists**:
          - `drift-report`: exactly `detection_run.json` and `drift_report.json`;
          - `drift-investigation`: `drift_investigation.json`;
          - `infracost-report`: `cost_run.json` and `infracost.json`;
          - `ai-analysis-report`: `ai_analysis_report.json` and `.md`;
          - 7 files in total.
        - **Public drift report**:
          - validates as `PublicDriftReport` and against `schemas/drift_report.public.schema.json` (0 errors);
          - `public_version: "1"`, outcome `succeeded`, `has_drift: false`, `{"in_sync": 5}`, `run.run_id` `github-37948472263-1`;
          - the manifest shows succeeded, plan exit 0, commit `4ba7668`.
        - **No internal report**: no JSON file in any artifact validates as the internal `DriftReport` contract.
        - **Public investigation**:
          - validates as `PublicInvestigation`: `public_version: "1"`, outcome `complete`, 0 resources, no failure, run id bound;
          - `drift-engine investigation-check` against the downloaded public report: `valid`, exit 0;
          - **no Azure query**: with no drifted resource there is no target and no scope, so no Activity Log page is requested (`select_targets` → `_scope_plans` → `_run_scope`). `completeness.queried_at` is only the collection timestamp, and anchors examined 0.
        - **AI report**:
          - `report_version: "2"`;
          - `ai_engine.verify.verify_report` (schema and binding to the drift report and investigation) and `verify_markdown`: no problems;
          - 0 resources, no drift, 0 options, investigation `complete` without failure;
          - LLM provider `none`, `not_attempted`, `evidence_sent: []`, `investigation_sent: []`;
          - **no investigation claims**: no verdict, operation name, `recorded_caller`, `decisive_operation` or `pipeline_identity` in `resources` or the Markdown.
        - **Three-way hash**: the canonical SHA-256 of the downloaded public drift report is `3608aa7b213a287ace44cb24bcabb433308adf9f4e2302af941b590424deb464`.
          - The `ai_engine`, `sanitize_infracost` and `investigation_public` implementations all compute that value.
          - It equals `cost_run.json` `drift_report_sha256`, the investigation's `binding.drift_report_sha256` and the AI `provenance.drift_report_sha256`.
          - The AI `provenance.investigation_sha256` (`8b4cfa65…6632000b`) equals the canonical hash of the investigation.
          - The cost and AI run ids are `github-37948472263-1`.
        - **Cost**: `scripts/sanitize_infracost.py --check` against the downloaded drift report, run id `github-37948472263-1`: exit 0.
        - **Identifier scan** of all 7 files: no finding from the G11 `leak_findings` scanner. There is no GUID, `/subscriptions/`, `/providers/` or `/resourceGroups/` path, email or UPN, IPv4 address outside the configured `10.10.` CIDRs, or token-like string. The live subscription ID, tenant ID and signed-in user name (read locally, never printed) appear in no file.
      - **Git**: all 11 files under `.artifacts/task-9B.5-ci-proof/` (4 ZIPs, 7 extracted) are ignored (`.gitignore:40` `.artifacts/`); `git ls-files .artifacts` is empty.
    - **Anchor for Task 9B.6**: this run's public in-sync drift report is retained until 2026-11-08. **Superseded (2026-10-09)** by the no-drift run that follows the 9B.5 drifted proof and the tag removal (see the CI Activity Log authentication fix).
    - **Earlier scheduled runs on `26aa3a9`** (pre-G18 9B.5 code, read from public run data):
      - #26 `37749098619` and #27 `37904551688` (2026-10-08 and 2026-10-09, no drift): all jobs success.
      - #24 `37436291693` and #25 `37591269837` (2026-10-06 and 2026-10-07): real drift, while the `owner` test tag was still present.
        - Detection, issues, cost and report all succeeded, with "Drift detected in dev (a valid result, not a pipeline failure)".
        - Only the Drift Investigation job failed, on both runs: status `failed`, failure `evidence_failed` (from the annotations).
        - #25's job summary also shows detail `all_queries_failed=1,authentication_failed=1`, upload and verification `success`, outcome `failed`, 1 resource `not_investigated`, anchors examined 24 / accepted 1. #24's summary was not read.
        - Plan & Drift Analysis took 11m 3s on #25: the G8 settle wait ran before the Activity Log query.
        - G18 keeps this case red (Q2: `failed` is a process error), and the drift result was unaffected, as designed.
    - **Blocker for Task 9B.6 (open, not diagnosed)**: in CI, the Activity Log query fails authentication on a drifted run.
      - Hypothesis, unverified: after the ~10-minute settle wait, the Azure CLI session from `azure/login` OIDC can no longer obtain a token (the federated client assertion has expired).
      - Until this is resolved, the 9B.6 primary drift run would fail its G18 investigation criterion.
      - Diagnosis and any fix need a design review and user approval; they are not part of this record.

  - **CI Activity Log authentication fix (2026-10-09; committed and pushed to `main` 2026-10-09 (user-approved, in the commit that carries this plan update))**:
    - **Files**:
      - `src/drift_engine/activity_logs.py`:
        - new constants `ARM_CREDENTIAL_SCOPE`, `AUTH_REASONS` and the AADSTS allowlist;
        - `QueryError.auth_reason`, with a validator requiring it exactly with `authentication_failed`, and a serializer that omits it when absent;
        - `SourceError(..., auth_reason)`: defaults to `no_aadsts` for `authentication_failed` and is rejected with any other code;
        - `_auth_reason()`: 401 gives `arm_rejected`; otherwise the AADSTS number is mapped through the allowlist;
        - `pages()` passes the reason; `_run_scope` records it;
        - `MonitorManagementClient(..., credential_scopes=[ARM_CREDENTIAL_SCOPE])`;
        - module docstring updated.
      - `scripts/investigation_analysis.sh`: `detail_codes` adds `auth_<reason>` counts (regex-bounded); header comment updated.
      - `tests/test_activity_logs.py`: two tests in `AzureMonitorSourceTests`, plus the new classes `CachedAudienceCliTests` (2) and `AuthReasonTests` (4).
      - `tests/test_investigation_workflow.py`: `test_detail_codes_count_the_auth_reason`.
      - Docs: `docs/drift-detection-spec.md` (§8.3 status and credential) and `README.md` (investigation status and token).
      - **Unchanged**: workflows, permissions, secrets, credentials, Azure resources and every G-decision.
    - **Tests**:
      - **Scope**: the recorded scope is exactly `https://management.core.windows.net//.default`; the request is still GET to `management.azure.com` on the Activity Log path.
      - **Real `AzureCliCredential`** with a fake `az` on `PATH`: the only call is `account get-access-token --output json --resource https://management.core.windows.net/`.
      - **CI failure reproduced on the real `collect_evidence` path**: the fake `az` serves only the login-cached resource and prints a realistic `AADSTS700024` error with synthetic GUIDs, a UPN, a trace ID and timestamps.
        - With the old SDK scope: `authentication_failed` / `assertion_expired`, no HTTP request sent.
        - With the fix: the scope is `complete`, with one request.
        - None of the synthetic values, `AADSTS` or `700024` appears in the evidence or the logs.
      - **Mapping**: `700024`, `70021`, `700213`, another number, 7 digits, too short, no number, and 401.
      - **Validation rules**: `SourceError` and `QueryError` rules; auth reasons through the SDK source (credential errors and HTTP 401); no reason for 403 or 429.
      - **Rendering**: without an authentication failure, every other query-failure code, a limit code and a complete scope render without `auth_reason`, with error keys exactly `{code, http_status}`. An authentication failure round-trips.
      - **Script**: `investigation_detail` = `all_queries_failed=1,auth_arm_rejected=1,auth_assertion_expired=1,authentication_failed=3`. A non-code reason is ignored, and no secret appears in the output line or outputs.
    - **Mutation check** (scratch copies, restored and byte-compared). Each mutation was caught:
      - scope argument removed: 3 failing tests;
      - reason always `no_aadsts`: 7;
      - absent reason not omitted: 1;
      - no 401 mapping: 2;
      - script ignores the reason: 1.
    - **Byte-identical rendering**: 14 evidence documents without an authentication failure (complete, page limit, and each other query-failure code) rendered with the committed code (temporary `git worktree` of HEAD, removed afterwards) and with the new code: identical SHA-256 for all 14.
    - **Validation** (scratchpad venv, Python 3.13):
      - full suite **2359 passed** (3,950 subtests), coverage 98.84%;
      - `unittest discover -s tests`: 958 OK;
      - `actionlint` 1.7.12: clean on all workflows;
      - `shellcheck scripts/investigation_analysis.sh`: clean. (A wider `shellcheck scripts/*.sh` run reports one informational SC2329 in the unchanged `generate_plan_json.sh`: a false positive, since `on_exit` is invoked via `trap on_exit EXIT`.)
      - `./scripts/validate.sh` passed.
    - **Audience checks**: (a1) and (a2) passed (see the acceptance criterion).
    - **Not done**:
      - check (b), the drifted real CI proof, is pending. It needs a portal test tag (user action) and one approval-gated dispatch.
  - **Diff review fixes (2026-10-09, user-approved: M1, L2, L3 fixed; L1 and I1 documented; committed and pushed to `main` 2026-10-09 (user-approved, in the commit that carries this plan update))**:
    - **M1, credential error text on standard error**:
      - **Finding**: azure-identity's `log_get_token` logs a failed request as `"%s failed: %s"` with the exception at WARNING. With no handler configured, Python's last-resort handler printed Azure CLI's raw error (tenant and client IDs, trace and correlation IDs, a UPN, timestamps) to standard error.
        - In CI this landed only in the runner-only `investigation.log` (0700, never uploaded or printed); locally it reached the terminal.
        - This predates the fix and is not introduced by it.
      - **Fix** (`activity_logs.py`): `_RedactExceptionArguments`, installed idempotently by `_redact_azure_identity_logs()` on every `azure.identity` logger when the source builds its client.
        - The record is kept: each exception argument becomes its type name and the traceback is dropped. Records without an exception argument are unchanged.
        - No other logger is touched (`azure`, `azure.core`, `drift_engine` and application loggers are verified).
        - `drift_engine`'s supported logging configurations (off, and `--log-level` text/json) attach no root handler; their own structured logs are unchanged.
    - **L2**: `SourceError("authentication_failed", 401)` without an explicit reason now defaults to `arm_rejected`, consistent with `_auth_reason`. Only custom sources and fakes use the default.
    - **L3**: `scripts/investigation_analysis.sh` counts `auth_<reason>` only for the five allowlisted reasons, instead of any `[a-z_]` string. A sync test asserts the script's list equals `AUTH_REASONS`.
    - **L1, known compatibility limitation (documented; the strict model and `evidence_version: "2"` are unchanged by decision)**: an evidence file written before this change with an `authentication_failed` scope (no `auth_reason`) no longer satisfies the strict evidence model.
      - `drift-engine attribute --evidence <old file>` treats it as invalid evidence, and post-run verification reports a contract failure.
      - CI is unaffected (evidence is produced and consumed in the same run); only such locally saved files are.
    - **I1, known limitation (documented; no credential redesign)**: a Resource Manager 401 carrying a CAE claims challenge makes the challenge policy request a token with claims. `AzureCliCredential` cannot satisfy that, so the query is reported as `credential_unavailable` without an `auth_reason`. This predates the fix (verified with a fake `az` and a 401 carrying an `insufficient_claims` challenge).
    - **Tests added**:
      - `CredentialErrorLogRedactionTests`:
        - the real `drift-engine activity-logs` CLI in a subprocess, failing on a fake `az` that prints planted GUIDs, a UPN, trace IDs and timestamps, under logging off, `--log-level debug` text, and debug json;
        - none of the planted values reaches stdout, stderr or the evidence;
        - the redacted azure-identity record (`AzureCliCredential.get_token_info failed: ClientAuthenticationError`) is still present, and `drift_engine` debug logs still appear;
        - an unrelated logger and an `azure.core` logger still print their full warning text;
        - filter unit rules: idempotent, only `azure.identity` loggers, argument redaction, traceback dropped, success record unchanged.
      - `test_source_error_rules` (L2).
      - `test_detail_codes_count_the_auth_reason` with an unlisted `none` reason ignored, and `test_script_auth_reason_allowlist_matches_the_engine` (L3).
    - **Mutation check** (restored and byte-compared). Each mutation was caught:
      - filter not installed: 4 failing tests;
      - filter drops records: 4;
      - L2 default reverted: 1;
      - script regex instead of the allowlist: 2.
      - An unreachable branch for non-tuple record arguments was removed (`LogRecord` keeps positional arguments as a tuple); `activity_logs.py` coverage is 100%.
    - **Validation** (scratchpad venv, Python 3.13):
      - targeted tests 18 passed;
      - full suite **2363 passed** (3,953 subtests), coverage 98.84%;
      - `unittest discover -s tests`: 961 OK;
      - `actionlint` clean; `shellcheck scripts/investigation_analysis.sh` clean; `./scripts/validate.sh` passed.
      - **Evidence byte-equivalence** against HEAD (temporary `git worktree`, removed): 14 of 14 documents without an authentication failure identical.
      - The scratchpad leak probe now shows no planted value on standard error.
    - **Final focused review (2026-10-09)**:
      - **Propagation verified**: Python applies the filters of the record's *originating* logger once in `Logger.handle`, before `callHandlers` walks the hierarchy. Every ancestor handler and `lastResort` therefore receives the already-redacted record.
        - Probed in fresh processes: root handler at WARNING and at DEBUG (traceback attached), a DEBUG handler on `azure`, and a handler on the originating `azure.identity._internal.decorators` logger.
        - Result: no planted `az` text, no traceback, and no `azure.identity` logger left without the filter after a token request.
        - New regression test `test_redaction_holds_through_propagation_and_host_handlers` (4 setups). Mutation-checked: keeping the traceback fails the 3 DEBUG setups; not installing the filter fails all 4.
      - **Rechecked**:
        - the five `AUTH_REASONS` equal the model `Literal` and the script allowlist; the AADSTS map values are a subset; the longest detail code is 24 characters;
        - HTTP 401 gives `arm_rejected`, a token-acquisition failure gives the AADSTS mapping, and 403/429 carry no reason (CAE 401: I1);
        - CI routes the investigation's stderr only to the runner-only restricted log;
        - evidence byte-equivalence against HEAD: 14 of 14 identical.
      - **Finding N1 (fixed 2026-10-09, user-approved; see "N1 fix" below)**: when a host application enables DEBUG on `azure`/`azure.identity` (never done by drift-engine's supported logging configurations, whose effective level stays WARNING), azure-identity's *success* path logs a pre-formatted `[Authenticated account] Client ID … Tenant ID … User Principal Name … Object ID` record.
        - It is built from the token's claims, so argument redaction cannot cover it.
        - Probed with a planted JWT: `upn`, `tid`, `oid` and `appid` reached the host handler in all three DEBUG setups.
        - `resolve_tenant`'s INFO records with tenant IDs are similar, but are not on this path (no tenant is passed).
      - **Validation**:
        - targeted tests 19 passed;
        - full suite **2364 passed** (3,957 subtests), coverage 98.84% (`activity_logs.py` 100%);
        - `unittest` 962 OK; `actionlint`, `shellcheck` and `validate.sh` clean.
    - **N1 fix (2026-10-09, user-approved; committed and pushed to `main` 2026-10-09 (user-approved, in the commit that carries this plan update))**:
      - **Change**: `_RedactExceptionArguments.filter` returns `False` for every record below WARNING. WARNING and ERROR records are kept with the existing redaction (exception arguments reduced to type names, traceback dropped).
        - The filter is still installed only on `azure.identity` loggers; unrelated loggers, `azure.core` and `drift_engine` are unchanged.
        - The spec's credential note is updated.
      - **Tests**:
        - `test_debug_account_details_never_reach_host_handlers`:
          - a fake `az` returns a JWT with planted `appid` (client ID), `tid` (tenant ID), `upn` and `oid`;
          - three DEBUG host setups: root DEBUG, a DEBUG handler on `azure`, a handler on the originating logger;
          - none of the four values, no `[Authenticated account]` and no `get_token_info succeeded` reach stdout or stderr;
          - the host's own unrelated DEBUG line and `azure.core` DEBUG/WARNING lines are still emitted, wherever that setup emits them.
        - `test_filter_rules` gains DEBUG/INFO records dropped and an ERROR record redacted.
        - The existing propagation, CLI and unrelated-logger tests still pass: the failure WARNING record is kept, redacted.
      - **Mutation check** (restored and byte-compared). Each mutation was caught:
        - no level drop: 4 failing tests;
        - WARNING dropped too: 8;
        - every record dropped: 8;
        - filter installed on every logger: 1.
      - **Probe** (scratchpad, fresh processes): with root handlers at WARNING and DEBUG, a DEBUG handler on `azure`, and a handler on the originating logger, on both the failure and the success path (planted JWT), no planted value leaks and no `azure.identity` logger is left unfiltered.
      - **Validation**:
        - targeted tests 18 passed;
        - full suite **2365 passed** (3,960 subtests), coverage 98.84% (`activity_logs.py` 100%);
        - `unittest` 963 OK; `actionlint`, `shellcheck scripts/investigation_analysis.sh` and `./scripts/validate.sh` clean.
        - **Evidence byte-equivalence** against HEAD (temporary `git worktree`, removed): 14 of 14 identical.

#### Task 9B.6 — Real Azure End-to-End Acceptance & Phase Closure
- **Status**: 🟢 COMPLETED — every acceptance criterion and validation item met on cycle 2 (D-6); cycle 1 stays as history
- **Started**: 2026-10-10
- **Completed**: 2026-10-11
- **Plan revision (2026-10-10, user-approved decisions; reviewed and locked by the user on 2026-10-10)**:
  - **D-1 (fresh primary run)**: the primary scenario is repeated with a fresh real Azure drift run. Task 9B.5's run #29 is **not** primary evidence; it is cited only as prior evidence that the pipeline works.
  - **D-2 (job-log scope)**: the public job-log privacy check covers only the investigation and AI logs (see "Leak scan"). The Phase 5 diagnostic-log exposure, which includes the `Verify Azure OIDC Authentication` step, stays a documented Phase 12 known limitation.
  - **D-3 (reference run and phase counts)**:
    - The in-sync anchor is defined by G9 (the latest earlier valid in-sync drift report), not by a fixed run number.
    - The phase counts and the README phase status are reconciled at closure.
  - **Code-verified corrections (2026-10-10, user-approved)**: the Local WHO and Determinism criteria were checked against the code (`src/drift_engine/who.py`, `src/ai_engine/cli.py`, `src/ai_engine/nodes/report_generator.py`, `.github/workflows/ai-analysis.yml`) and made precise:
    - Local WHO: evidence roles stated, sensitive handling of the state JSON made executable, and the caller comparison defined with an explicit, identity-free mismatch path.
    - Determinism: exact AI-run commit, required `--investigation`, explicit `AI_LLM_PROVIDER=none`, unchanged inputs and a fresh pinned environment.
  - **D-4 (job-log GUID policy and B fix; user-approved 2026-10-10, after the primary run)**:
    - **Finding**: a complete scan of the job-log archives of primary run #32 (`38023838144`) and its AI run #15 (`38024516418`) found 14 GUIDs in the in-scope logs. All are GitHub platform output; this project's own steps contain none, and none is unclassified:
      - **A = 2**: the GitHub-hosted runner's `Worker ID` (1 per job).
      - **B = 4**: the `actions/checkout` temporary `HOME` path (`Checkout Code` and `Post Checkout Code`, 1 each, in both jobs).
      - **C = 8**: the `actions/download-artifact` redirect URL (2 per line, 2 download steps per job).
    - **A (exception)**: the runner prints the host-supplied `.setup_info` file in "Set up job", before any workflow step (`actions/runner` v2.337.0: `src/Runner.Worker/JobExtension.cs` lines 106–136, `src/Runner.Common/HostContext.cs` lines 510–513). No workflow setting reaches it. A narrow exception is approved (see "Job logs").
    - **B (fixed, no exception)**: `set-safe-directory: false` is added to the `Checkout Code` step of the `investigation` job and of the `ai-analysis` job (see Files/Areas).
      - The pinned `actions/checkout@v4` (`11d5960a`) logs the temporary `HOME` only when safe-directory or submodules are enabled. A local run of that exact code logged 1 + 1 such UUIDs (main + post) with `true` and 0 with `false`.
      - Neither job runs git after checkout, and the safe-directory entry was only ever written to a temporary config that checkout removes itself, so later steps are unaffected.
      - B must be 0 from the fix commit onward; Control A and Control B verify it in both jobs. The primary scenario's pre-fix occurrences are a one-time recorded finding (see "Job logs"); the primary scenario is not re-run to erase them.
    - **C (exception)**: the official `actions/download-artifact` is kept, and no custom downloader is built. It always logs the redirect URL with `core.info`, query string removed (v4 `d3f86a10` and v8 alike), and has no input to turn it off. A narrow exception is approved (see "Job logs").
    - Every other job-log rule is unchanged: any other GUID, and any email or UPN, ARM path, IP address, token-like string or live subscription, tenant or user value, still fails.
  - **D-5 (Local WHO: no current-CLI identity comparison; user-approved 2026-10-10)**:
    - The historical caller comes only from the Azure Activity Log operation that `drift-engine who` re-matches (G12): the event's recorded `caller`, from the operation group that equals the public operation.
    - The account currently signed in to Azure CLI identifies the local session, not who made a past Portal change. So the caller comparison with `az account show` and the user's "same account" confirmation, both added in the 2026-10-10 revision, are removed from Step 4 and Pass.
    - `az account show` stays only as the Step 2 subscription-scope check. G3, G12 and the Phase 9B end-to-end acceptance list are unchanged.
    - Step 4 gains a WHO evidence acceptance criterion: exactly one distinct, non-empty recorded caller in the matched `who` result, and `caller_status: recorded` on the public operation. An empty or multi-caller result fails even if `who` exits 0. The limitation for partially missing or rejected caller rows is documented; no code change.
  - **D-6 (fresh cycle 2 and test fix; user-approved 2026-10-11)**:
    - **Why**: cycle 1 (runs #31–#36) left gaps that its own evidence cannot close. The pre-dispatch anchor re-confirmation for #32 was not recorded. The D-4 B fix (`c3cf8a0`) changed the workflows but not `tests/test_ai_cli.py`, so the full suite has failed since then (found 2026-10-10).
    - **Cycle 2** repeats the scenarios on the commit that contains the test fix:
      1. **R1**: the user removes the test tags; one dispatch gives an in-sync run, which closes issue #8 (Task 8.3) and becomes the fresh anchor (G9);
      2. **R2**: the primary scenario;
      3. **R3**: Control A;
      4. **R4**: Control B.
      Pre-check 0 applies before R2, after R1 has restored the configured tags. Every criterion below is evaluated on cycle 2. Cycle 1 stays recorded as history and is not used for closure.
    - **Anchor timing**: the UTC times of the anchor identification after R1 and of the re-confirmation immediately before R2 are recorded when they happen. Anything not captured is recorded as NOT RECORDED.
    - **Evidence paths**: `.artifacts/task-9B.6-ci-proof/cycle2/{primary,control-a,control-b,who-local}/` (new folders, nothing overwritten). Job-log archives go to a 0700 folder outside the repository, with files at 0600. Local WHO for R2 uses `cycle2/who-local/`, so Step 1's "must not exist beforehand" rule holds.
  - Locked G-decisions (G1–G18), the Phase 9B end-to-end acceptance list and every completed task record are unchanged. Run #29's and run #30's records under Task 9B.5 stay as history.
- **Objective**: Prove the product requirement with real Azure evidence through CI (a fresh primary scenario plus two controls). Then close Phase 9B and return Phases 6 and 7 to 🟢; Phase 10 resumes.
- **Dependencies**:
  - Task 9B.5 (🟢 2026-10-09: G18 in `4ba7668`, the Activity Log authentication fix in `62bdf65`) and Task 9B.4A.
  - **User actions** (Execution Rule 10): the portal tag changes, approval for each dispatch, the 10 artifact downloads (Claude cannot download artifacts), the job-log archive downloads for each scenario's drift run and AI run (D-4), and local WHO steps 1 and 3 (Terraform state JSON and `who`, run with the user's own `az login`).
- **Files/Areas**:
  - `.artifacts/task-9B.6-ci-proof/` (gitignored; downloaded artifacts per scenario, regenerated AI reports, local WHO output);
  - `PROJECT_PLAN.md`;
  - `README.md` (limitations and phase status at closure).
  - `.github/workflows/drift-detection.yml` and `.github/workflows/ai-analysis.yml`: the D-4 B fix only, one added line each (`set-safe-directory: false` on the `Checkout Code` step of the `investigation` job and of the `ai-analysis` job; user-approved 2026-10-10).
  - `tests/test_ai_cli.py`: the D-4 B fix follow-up only, one assertion (`Checkout Code` expects `set-safe-directory: false` as well; D-6, user-approved 2026-10-11).
  - No other implementation file changes are planned. A failing criterion is reported as a blocker, and any fix needs a separate user decision.
- **Execution sequence** (one scenario at a time; Claude only reads Azure; every Azure change is the user's):
  0. **Pre-checks (Claude, read-only)**:
     - the working tree is clean and `main` = `origin/main`;
     - no drift-detection run is in progress;
     - `aitdd-dev-main-rg` has exactly its configured tags;
     - the latest in-sync drift report within retention is identified and recorded as the expected anchor (as of 2026-10-10: run #30 `37963733177`; a later in-sync run, scheduled or dispatched, supersedes it, per G9. For the primary scenario this was the in-sync dispatch run #31 `38023441753`, see the progress record);
     - the time of the next scheduled run (02:00 UTC cron; recently starting around 08:00 UTC) is noted.
  1. **Primary scenario**:
     - The user adds one test tag with a neutral, non-identity value (no email, name or ID) to `aitdd-dev-main-rg` in the Azure Portal.
     - Claude re-confirms the latest in-sync run (the expected anchor). The user approves one `workflow_dispatch` on `main`; Claude verifies the public run data.
     - The user downloads the four artifacts into `.artifacts/task-9B.6-ci-proof/primary/`.
     - Claude runs the artifact checks, the WHEN-to-the-second check and the determinism check.
     - Local WHO: user step 1 (Terraform state JSON), Claude step 2 (verify), user step 3 (`who`), Claude step 4 (verify).
     - An `incomplete` or other non-complete investigation stops the sequence as a recorded failed attempt (see the primary criterion).
  2. **Control A**:
     - With the primary tag still present, the user makes a second tag write on the same resource group (changes the test tag's value or adds a second neutral test tag). There must be no in-sync run in between.
     - Dispatch; then verification, downloads into `control-a/` (three artifacts, see "Leak scan"), and checks.
  3. **Control B**:
     - The user removes all test tags.
     - Dispatch; then verification, downloads into `control-b/` (three artifacts), and checks.
  4. **Record and close**: record everything (Validation), then apply the Closure criterion. Task 10.2 is not started (Execution Rule 8).
  - A scheduled run that fires during steps 1–3 is recorded as incidental evidence: a drifted run while test tags are present, in-sync after Control B. It does not replace a scenario run, and it can only become an anchor when it is in-sync.
- **Acceptance Criteria**:
  - [x] **Primary scenario (fresh run; D-1)**:
    - **Anchor**: the public investigation's and the AI report's last-in-sync reference is the latest in-sync run before the primary dispatch (G9), identified in pre-check 0 and re-confirmed immediately before the dispatch. The drift report shows `external_drift` on `tags.<key>`, unaffected by the investigation.
    - **CI result (G18)**: the run concludes **success**, specifically:
      - `Generate Plan Evidence` records plan exit code `2`;
      - `drift_detected=true` and `drift_status=detected`;
      - `drift-report-<run_id>` is uploaded with `has_drift: true`;
      - `plan-and-analyze`, `issues`, `cost`, `investigation` and `report` (Result VALID) all succeed. The issues job creates a new drift issue for the resource (closed issues are never reopened, Task 8.1);
      - **the investigation must be complete** (revision 2026-10-10, point 1):
        - `investigation_status: succeeded`, public outcome `complete`, `binding.evidence_outcome: complete`;
        - `investigation_detail` has no query-failure, limit or `auth_*` code;
        - the `investigation` job passes with upload and verification successful.
        - G18 still lets CI pass an `incomplete` investigation with a warning, but for this acceptance an `incomplete` (or any other) result is a **recorded failed acceptance attempt**, not a primary proof. The run id, fixed codes and cause are recorded, and the criterion stays unchecked.
        - A new attempt needs the user's decision. It may reuse the same test tag: a drifted run is not in-sync, so it does not move the anchor, and the single tag write stays the only capable operation since the anchor.
      - the triggered `ai-analysis` run succeeds;
      - job durations and the runner image (Azure CLI) version are recorded.
    - **Public AI report v2** meets every item of "Phase 9B end-to-end acceptance", checked on the downloaded `ai_analysis_report.json`:
      - **WHAT**: `external_drift` on `tags.<key>`, desired `absent`, the actual value present;
      - **operation**: `Microsoft.Resources/tags/write`, outcome `successful`, relations `exact` and `extension` under one group;
      - **WHEN**: event start and end, availability, last-in-sync observation, observation window and plan timestamp present and labelled separately; timing `before_observation`;
      - **WHO**: `recorded_caller` `caller_type: user`, `client_app: azure_portal`, `pipeline_identity: false`, `identity: withheld`; `actor_attribution.status: not_confirmed_by_available_evidence`;
      - **correlation**: verdict `sole_capable_operation`, `property_link: inferred_not_provable`, completeness recorded (`settled: true`);
      - **analysis**: deterministic narrative, LLM `none` / `not_attempted`, nothing sent;
      - **recommendation**: `restore_declared` (policy v1, rule R4) with the accept-remote note, `approval_required: true`, `automatic_apply: false`, `execution_allowed: false`.
    - **WHEN to the second, against the Azure record** (Claude, read-only): one Activity Log query for `aitdd-dev-main-rg` over the scenario window.
      - The decisive operation's start (first row) and end (last Succeeded row) equal the Azure event timestamps when truncated to whole seconds.
      - The last row's status is `Succeeded`.
      - Only timestamps, operation names and statuses are compared or printed, never a caller, claim or ID.
  - [x] **Control A**: a second tag write on the same resource group after the primary tag, with no in-sync run in between, then dispatch. Required:
    - the run concludes **success** with `drift_detected=true` and plan exit `2` (G18);
    - the investigation `succeeded` / `complete` with no query-failure, limit or `auth_*` code;
    - the AI report shows verdict **`ambiguous`** (two capable operations since the same anchor);
    - `who.recorded_caller.status: multiple_operations` with `candidate_operations >= 2`, and actor attribution `not_confirmed_by_available_evidence`;
    - the recommendation is unchanged at `restore_declared` (R4), because verdicts never change the recommendation in policy v1;
    - the issues job updates the open drift issue (or leaves it unchanged) and creates no second issue for the resource;
    - the cost job and the AI run succeed;
    - the run uses a `main` commit that includes the D-4 B fix, and its job-log check passes under the D-4 policy with **B = 0** in both the `investigation` and `ai-analysis` jobs.
  - [x] **Control B**: the user removes all test tags, then dispatch. Required:
    - the run concludes **success** with `drift_detected=false`, plan exit `0` and classification `{"in_sync":5}`;
    - the investigation `succeeded` / `complete` with 0 resources and no anchor fetch;
    - the AI report v2 has 0 resources and no investigation claims;
    - the issues job closes the open drift issue (`state_reason: completed`, Task 8.3);
    - the resource group then has exactly its configured tags (read-only check);
    - its job-log check passes under the D-4 policy with **B = 0** in both the `investigation` and `ai-analysis` jobs.
  - [x] **Leak scan (amended 2026-10-05, P2; job-log scope amended 2026-10-10, D-2; job-log GUID policy amended 2026-10-10, D-4)**:
    - **Required downloads (revision 2026-10-10, point 3; necessity per criterion)**:
      - **Every scenario (primary, Control A, Control B)**: `drift-report`, `drift-investigation` and `ai-analysis-report`. Each is consumed by a criterion in every scenario: the WHAT/WHEN/WHO/verdict/0-resource checks, determinism (the drift report and investigation are its inputs, the AI report its expected output), the leak scan, and for the primary scenario local WHO (`--public`, `--report`). None of them can be dropped.
      - **`infracost-report`**: downloaded for the **primary** scenario and checked locally like the others, including the end-to-end three-way `drift_report_sha256` match across cost, investigation and AI, as in Task 9B.5.
        - For Controls A and B it is not downloaded. The required `cost` job success already runs `scripts/sanitize_infracost.py --check` on that exact artifact, fail-closed: allowlisted schema (totals and resource-type counts only), binding to the run attempt and the downloaded drift report, and rejection of email-like, URL, GUID and absolute-path strings.
        - The artifact cannot carry Activity Log or caller data. Its GitHub digest is still recorded for every scenario.
        - This is stricter than the locked P2 baseline (2026-10-05), which listed only the other three artifacts.
      - **Downloads**: primary 4 + Control A 3 + Control B 3 = **10**.
    - **Artifacts**: every downloaded artifact is checked as for Task 9B.5:
      - each ZIP's SHA-256 equals its GitHub digest; flat regular files only;
      - the G11 `leak_findings` scan is clean, and the public investigation passes its full G11 leak scan;
      - no UPN, email or other caller identity; no GUID; no `/subscriptions/`, `/providers/` or `/resourceGroups/` path or other ARM/resource ID; no Activity Log or caller IP address; no token-like string;
      - the live subscription ID, tenant ID and signed-in user (compared in memory, never printed) appear in no file;
      - Terraform-configured IPs/CIDRs, URL values and the test tag value are Terraform evidence and allowed.
    - **Job logs (D-2 scope; GUID policy D-4)**: the public logs of the `Drift Investigation` step (`plan-and-analyze`), the `investigation` job and the `ai-analysis` job show only counts, fixed codes, timestamps, run ids and public artifact names.
      - **Method**: the user downloads the complete job-log archives (job page → log dropdown → "Download log archive") into a 0700 folder outside the repository.
        - Each archive is mapped to its run by the public API `check_suite_id`, its job set, timestamps inside the API job window and the run id in the in-scope content.
        - Only the in-scope jobs are read, and for `plan-and-analyze` only the lines inside the `Drift Investigation` step's API time window.
        - Lines are assigned to steps by the log's step markers, whose count must equal the API step count.
        - Archives are read in memory only. No line, GUID, host or other value is printed; only counts and booleans are recorded.
      - **Always a failure, with no exception**: any email or UPN, ARM path (`/subscriptions/`, `/providers/`, `/resourceGroups/`), IP address, JWT or other token-like string, or the live subscription ID, tenant ID or signed-in user (compared in memory). Allowed and counted: the public repository name and its URLs, public runner-image URLs, and GitHub `***` masks.
      - **GUIDs are a failure, except exactly**:
        - **A (GitHub-hosted runner `Worker ID`)**: at most 1 GUID per job, on the single line that fully matches `Worker ID: {<GUID>}`, inside the `##[group]Runner Image Provisioner` group of "Set up job", before the first step marker.
        - **C (`actions/download-artifact` redirect URL)**: exactly 2 GUIDs per line, on lines that fully match `Redirecting to blob download url: https://<name>.blob.core.windows.net/actions-results/<GUID>/workflow-job-run-<GUID>/artifacts/<64 lowercase hex>.zip` with no query string; at most 1 such line per download step.
      - **B (`actions/checkout` temporary `HOME`) is not exempt**: any occurrence fails from the D-4 B-fix commit onward.
        - **One-time pre-fix finding, limited to exactly two run ids**: primary drift run `38023838144` (#32) and the AI run it triggered, `38024516418` (#15). Both ran before the D-4 B fix.
          - Their 4 B GUIDs are recorded as a finding, not a failure: 2 in run `38023838144`'s `investigation` job and 2 in run `38024516418`'s `ai-analysis` job (`Checkout Code` and `Post Checkout Code`, 1 each).
          - B must be 0 in both in-scope jobs (`investigation` and `ai-analysis`) of every other run this job-log criterion applies to: Control A, Control B and any re-run or new attempt of the primary scenario, all of which must run on a commit that includes the approved B fix. Incidental scheduled runs, including run `38036342826` (#33), and earlier runs are not scenario runs; this criterion does not evaluate or classify them, and running before the B fix does not make them failures.
      - **Anything else fails**: any other GUID, a second A line in a job, a C line with a different shape or a query string, or more GUIDs than these limits. An unclassified hit stops the check for a user decision.
      - **Recorded per run**: the A, B, C and unclassified GUID counts per job and step, the other categories, the `***` mask count and the scan coverage (lines scanned out of total).
    - **Excluded from the job-log check (known limitation, Phase 12)**: the Phase 5 diagnostic output of `Verify Azure OIDC Authentication` (`az account show`, with subscription and tenant IDs masked by GitHub as `***`) and the failure-only `plan.log` tail of `Generate Plan Evidence`. The exclusion is recorded with the results, and the limitation stays open for Phase 12.
    - **Deletion scenario**: its public projection is leak-free as fixture-verified in Task 9B.4A (the deletion path has no safe real producer). That evidence is cited, not re-run.
  - [x] **Local WHO** (G12; the user runs every step that prints an identity; revision 2026-10-10, point 2; corrected 2026-10-10 after code verification):
    - **Evidence roles** (verified against `src/drift_engine/who.py`; G12 unchanged):
      - **Caller source: Azure Activity Log only.** `who` re-queries each public operation's start and end ± 1 s and accepts exactly one operation group equal in operation name, start and end (to the microsecond), outcome, relations, caller type and client application. Only that group's recorded caller is reported. `no_match` and `multiple_matches` never yield a caller.
      - **Terraform state: address → ARM ID only.** It is the current stored state, but it is the same state the CI plan read as the drift entry's `before` (plan runs never write state), and ARM IDs are name-derived.
        - A state change after the primary run (apply, import, `state mv`, rename) fails closed (`address_unknown`, `invalid_resource_id` or `no_match`), never with a wrong caller.
        - Activity Log rows ingested after CI's query could change a group and give `no_match`; the primary criterion's `settled: true` covers this. Beyond 90 days the result is `retention_exceeded`.
      - **`az account show`: subscription-scope check only** (Step 2). It identifies the account signed in to Azure CLI now, not who made a past change, so it is never a caller source and is never compared with the recorded caller (D-5).
    - **Inputs**, all under the gitignored `.artifacts/task-9B.6-ci-proof/` and never committed:
      - the primary run's downloaded, digest-verified `drift_investigation.json` and `drift_report.json` (`primary/extracted/…`), unchanged;
      - a local Terraform state JSON in `who-local/terraform-state.json`.
    - **Terraform state JSON is sensitive, local-only data**: `show -json` writes every managed attribute, including sensitive values in plain text. It stays in the 0700 `who-local/` folder with mode 0600, git-ignored. Its content, the IDs in it and its address map are never printed, copied elsewhere, uploaded, attached to an issue or committed. Claude reads it only for the Step 2 checks.
    - **Where Steps 1 and 3 run**: in the user's own terminal, outside the Claude app.
      - They are never run through Claude's tools or in the app's Terminal panel, which Claude can read. This keeps state content and the printed caller out of the conversation.
      - Claude never asks the user to paste or otherwise share their output. The user reports only each command's exit code.
    - **Step 1 (user, local, read-only): Terraform evidence.** Run from the repository root with the user's own `az login` on the dev subscription and Terraform 1.14.7:
      - `mkdir -p .artifacts/task-9B.6-ci-proof/who-local && chmod 700 .artifacts/task-9B.6-ci-proof/who-local`
      - `ARM_USE_AZUREAD=true terraform -chdir=terraform/environments/dev init -input=false -lockfile=readonly`
      - `(umask 077 && set -C && ARM_USE_AZUREAD=true terraform -chdir=terraform/environments/dev show -json > .artifacts/task-9B.6-ci-proof/who-local/terraform-state.json)`
      - `terraform-state.json` must not exist beforehand, because a redirect into an existing file keeps that file's old mode.
        - `set -C` (noclobber) enforces this: the redirect fails, and nothing is overwritten, if the file already exists.
        - The subshell limits `umask 077` and `set -C` to this one command.
      - **On failure** (any non-zero exit of `init` or `show -json`):
        - the user removes the incomplete local file (`rm -f .artifacts/task-9B.6-ci-proof/who-local/terraform-state.json`) before retrying, because a failed redirect still leaves an empty 0600 file;
        - only the exit code is reported and recorded, never the raw Terraform or Azure CLI error output, which can contain the storage account, the subscription ID or a UPN.
      - `show -json` only reads the current remote state. No `plan`, `apply`, `refresh` or `state` write is run, and `terraform/environments/dev/.terraform.lock.hcl` must stay unchanged (`git diff --quiet`).
    - **Step 2 (Claude, local, prints booleans and counts only): verify the Terraform evidence matches.**
      - the folder is mode 0700; the file is mode 0600 and git-ignored;
      - `terraform_version` is `1.14.7`;
      - every resource address in the downloaded primary `drift_report.json` is present in the state's managed resources (`who.terraform_resource_ids`);
      - the investigated address maps to an ARM ID that `activity_logs.parse_resource_id` accepts, with resource group `aitdd-dev-main-rg`, and whose subscription equals the live `az account show` subscription (compared in memory).
      - No ID, address map or state value is printed.
    - **Step 3 (user, local): WHO.** With the same `az login`, and `drift-engine` installed with the `[azure]` extra in a fresh virtual environment from the primary drift run's commit (`head_sha`), so `who` groups operations with the same code as the CI investigation. No existing environment or the repository's stale `build/` directory is reused:
      - `drift-engine who --public .artifacts/task-9B.6-ci-proof/primary/extracted/drift-investigation-<run_id>/drift_investigation.json --report .artifacts/task-9B.6-ci-proof/primary/extracted/drift-report-<run_id>/drift_report.json --terraform .artifacts/task-9B.6-ci-proof/who-local/terraform-state.json --output-dir .artifacts/task-9B.6-ci-proof/who-local/`
      - `--report` makes it fail (`binding_failed`) unless the public investigation is bound to that drift report.
      - It prints the recorded caller only on the user's own terminal (see "Where Steps 1 and 3 run") and writes only `who_evidence.local.json` (0600). It refuses to run in GitHub Actions.
    - **Step 4 (Claude, prints booleans and counts only): verify the result.** In `who_evidence.local.json`:
      - `failure` is null;
      - the result statuses are all `matched`, with one result per public operation (1 for the primary scenario);
      - `public_binding.drift_report_sha256` equals the canonical SHA-256 of the downloaded primary drift report, and `public_binding.run_id` equals the primary run;
      - **WHO evidence acceptance (D-5)**:
        - For each public operation there is exactly one local `who` result with the same `op_id`, and it has `status: matched` (exactly one matching operation group). Its `callers` list holds exactly one distinct, non-empty caller. `who` lists the distinct named callers of the matched group, so this is one caller value, not one Activity Log row.
        - The corresponding public investigation operation (the same `op_id`) must have `caller_status: recorded`.
        - An empty caller list or multiple distinct callers fails this acceptance criterion, even if `who` exits with code 0.
        - **Documented limitation**: the current local `who_evidence` output cannot distinguish a fully recorded caller from a partially missing or rejected set of caller rows when the remaining rows contain one named caller. The public investigation's `caller_status` reflects the CI query, not the later local re-query, and does not close this gap.
        - This criterion does not claim to prove that the recorded principal was the human actor who caused the drift (G3).
        - Only the caller count and `caller_status` are checked and recorded; the caller itself is never printed.
    - **Pass**:
      - `who` exits 0;
      - all Step 2 checks and the Step 4 `failure`, status, count, binding and WHO evidence acceptance checks are true.
    - **Recorded in the plan**: only the exit code, the status counts, the binding-hash match, the booleans and the date. No caller (or any part of it) and no ID or state content is recorded. The local files stay 0600 under `.artifacts/` (G12).
  - [x] **Determinism** (corrected 2026-10-10 after code verification): for each scenario, the AI report regenerated locally is byte-identical to the downloaded `ai_analysis_report.json` and `ai_analysis_report.md` (equal SHA-256).
    - **Inputs only**: the scenario's extracted, digest-verified `drift_report.json` and `drift_investigation.json`, used unchanged (not reformatted, re-serialized or edited).
      - `ai-analysis` reads no other file. It makes no Azure, Activity Log or network call and reads no clock (verified in `src/ai_engine/cli.py` and `src/ai_engine/nodes/report_generator.py`).
      - `infracost-report` is not an input; the AI report's cost section is fixed.
    - **`--investigation` is required in every scenario**:
      - The AI workflow passes it whenever the source run's investigation artifact exists. That artifact is a required download in all three scenarios; a no-drift run uploads it too, as run #30 did.
      - Omitting it gives `investigation.status: not_available` and different bytes.
      - A scenario whose source run has no investigation artifact has already failed its investigation criterion.
    - **Exact code version: the AI run's `headSha`**:
      - The AI workflow runs on `workflow_run` and checks out without a `ref`. It therefore uses the latest `main` commit when the AI run starts, which is not necessarily the drift run's commit.
      - Claude records each AI run's `headSha` from the public run data and regenerates from exactly that commit: a temporary `git worktree` of `headSha` in the session scratchpad, removed afterwards.
    - **Fresh compatible environment**:
      - A new virtual environment in the session scratchpad, installed from that worktree with `pip install -c ci/ai-constraints.txt ".[ai]"`, must pass the workflow's pin check (extracted verbatim from `.github/workflows/ai-analysis.yml`).
      - Python 3.12 as in the workflow. If 3.12 is not available locally, Python 3.13 is used and recorded: Task 9A.1's clean-environment verification resolved the same 43 pins for 3.13 and for CPython 3.12.
      - No existing virtual environment, previously installed `ai-analysis`, or the repository's stale `build/` directory is reused.
    - **Command** (run with a minimal environment, so no shell `AI_LLM_*`, LLM key or `GITHUB_ACTIONS` variable can leak in):
      - `env -i PATH="<venv>/bin:/usr/bin:/bin" AI_LLM_PROVIDER=none ai-analysis --report <repo>/.artifacts/task-9B.6-ci-proof/<scenario>/extracted/drift-report-<run_id>/drift_report.json --investigation <repo>/.artifacts/task-9B.6-ci-proof/<scenario>/extracted/drift-investigation-<run_id>/drift_investigation.json --output-dir <repo>/.artifacts/task-9B.6-ci-proof/<scenario>/regenerated/`
      - `<scenario>` is `primary`, `control-a` or `control-b`, and the output folder must not exist beforehand.
      - `AI_LLM_PROVIDER=none` must be set explicitly, as in the workflow. On drift runs the report's `llm.reason` and `limitations` carry the "explicitly none" reason, so leaving it unset changes those bytes.
      - The command must exit 0.
    - **Compare**: the SHA-256 of both regenerated files equals that of the downloaded files. A difference is a blocker, reported with the differing JSON key paths only.
    - **Recorded**: per scenario, the AI run id and `headSha`, the Python version, the pin-check result and the four SHA-256 values.
  - [x] **Closure** (only after every criterion above passes):
    - Phase 9B 🟢; Phase 6 and Phase 7 headers back to 🟢, with closure notes referencing this task;
    - Overview "Phases Completed" updated to **9 of 14 (Phases 1–9)** with the Phase 6/7 note;
    - `README.md` phase status reconciled with the plan (it currently states "Phases 1–9 are complete" / "9 of 14" while the plan states 7 of 14), plus README limitations as needed;
    - Phase 10 → 🟡 WORK IN PROGRESS and Task 10.2 → ⬜ NOT STARTED;
    - Current Active Task → Task 10.2 (not started automatically, Execution Rule 8).
- **Validation**:
  - [x] All of the above recorded with run ids, commit, each AI run's `headSha`, runner image, artifact digests and timings, plus any incidental scheduled runs during the window.
  - [x] For every scenario's drift run and AI run, the D-4 job-log scan is recorded:
    - the archive-to-run mapping;
    - the coverage (every API step has log lines; lines scanned out of total);
    - per job: the A, B, C and unclassified GUID counts, the other categories and the `***` mask count.
    - The 4 B GUIDs of runs `38023838144` and `38024516418` are recorded as the one-time pre-fix finding, not a failure; B must be 0 in both in-scope jobs of Control A, Control B and any re-run or new attempt of the primary scenario.
  - [x] `latest_capable_operation` and the deletion-confirmed paths remain fixture-verified (no safe real producer) and are recorded as such, citing their task records (Tasks 9B.2–9B.4A).
- **Implementation Notes**:
  - Every Azure change is made by the user. Claude only reads (Activity Log, artifacts, public job data).
  - Test tag values appear in the public drift and AI reports as Terraform evidence, so they must be neutral (no email, name or ID). An identity-like value would fail the leak scan.
  - Run #29 (Task 9B.5) already showed the expected primary-scenario shape (`sole_capable_operation`, R4 `restore_declared`, WHO withheld). It is cited as prior evidence only (D-1).
- **Progress record (2026-10-10, cycle 1; history, not used for closure (D-6); the closure evidence is in the Completion Notes)**:
  - **Runs** (public GitHub API; all attempt 1):

    | Drift run | Commit | Event, created (UTC) | Conclusion | Role | AI run (commit, conclusion) |
    | --- | --- | --- | --- | --- | --- |
    | #31 `38023441753` | `717a2f0` | dispatch, 04:15:42 | success | In-sync anchor (G9). **Verified**: the primary investigation accepted it as its anchor (`github-38023441753-1`); G9 accepts only a report in which the address is `in_sync`. **Inferred**: `Drift Investigation` took 9 s, consistent with no settling wait (no drifted target). | #14 `38023538926` (`717a2f0`, success) |
    | #32 `38023838144` | `717a2f0` | dispatch, 04:22:31 | success | **Primary scenario.** **Inferred**: drift issue #8 came from this run. It was created at 04:33:52, inside this run's `Drift Issues` job window (04:33:43–04:33:53), and its title names the resource group address. | #15 `38024516418` (`717a2f0`, success) |
    | #33 `38036342826` | `717a2f0` | schedule, 07:59:57 | success | Incidental scheduled run while the primary tag was present. **Verified**: public drift warning annotation, so not in-sync. | #16 `38037006275` (`717a2f0`, success) |
    | #34 `38057933359` | `0e66f50` | dispatch, 14:00:49 | **cancelled** | **Manual cancellation by the user; reason not recorded.** **Verified**: confirmed by the user and by the public run annotation "The run was canceled by" the repository owner's GitHub account. `Drift Investigation` (step 13) ran 14:01:40–14:03:28 and was cancelled 108 s in. Upload, cost, `investigation`, `issues` and `report` did not run. Only `drift-report-38057933359` was uploaded. The public drift warning annotation is present, so the run is not in-sync. **Inferred**: the cancellation fell inside the G8 settling wait. It is not a Control A or Control B result. | #17 `38058113974` (`0e66f50`, success; it ran on the cancelled run, without an investigation artifact) |
    | #35 `38058888141` | `0e66f50` (includes the D-4 B fix) | dispatch, 14:15:26 | success | **Not Control A**: the Activity Log check below shows no second tag write before it. **Verified**: public drift warning annotation (a drifted run), and no second drift issue was created (issue #8 unchanged). With only the primary tag present, it is not a scenario run. | #18 `38059640155` (`0e66f50`, success) |

    - **Verified (as of 15:41Z)**: #33, #34 and #35 each carry the public drift warning annotation, so no in-sync run happened after #31, and the anchor for Control A is still #31. The only tag write since #31 is the primary one, so #33–#35 all observed the primary tag.
    - Every artifact of runs #31–#35 and AI runs #14–#18 expires on 2026-11-09.
  - **Activity Log check (Claude, read-only, 2026-10-10 15:41Z)**:
    - **Method**: `activity_logs.collect_window` and `investigation.group_operations` (the G12 code, commit `717a2f0`; `src/` is unchanged at `0e66f50`) for `aitdd-dev-main-rg`, from 04:15:26Z (anchor #31 start − 60 s) to 15:41:46Z.
    - **Result**:
      - scope `complete` with 0 dropped events;
      - exactly 2 events forming **1 operation group**: `Microsoft.Resources/tags/write`, 04:21:53.669Z–04:21:56.341Z, `successful`, relations `exact` + `extension`, available 04:23:46Z, caller type `user`, client `azure_portal`, `caller_status: recorded`, one distinct caller (not printed).
      - **No second tag write exists** between the anchor and 15:41Z, so Control A has not been executed.
    - Only timestamps, operation names, statuses and counts were printed.
  - **Primary scenario (run #32 / AI run #15) evidence**:
    - **PASS**:
      - **Artifacts**: the 4 artifact ZIPs equal their GitHub digests. They hold flat regular files only, and the extracted files equal the ZIP members. GitHub digests (SHA-256), equal to the local ZIP SHA-256:
        - `drift-report-38023838144`: `be9b4db25336b91e77b168800e234532463c32acf7fe5ef035b6d88acc356dfb`;
        - `drift-investigation-38023838144`: `f4190749d545f20f0cf2965a5e942be41724aa7cafffcecfdfa75caf9079a545`;
        - `infracost-report-38023838144`: `fd13a4fca5d8de5b407a11440d0fb36ec66dfa207c86996ed4815b381e097308`;
        - `ai-analysis-report-38023838144` (AI run #15): `5317ad3a5c3b1800f0030adf3e4214a3329bc6b32ef79add19e96bdb6379b996`.
      - **Anchor (outcome)**: #31 is the latest run before the dispatch, and the investigation and AI report use it as the last-in-sync reference (G9). The pre-check 0 identification and re-confirmation record is listed under NOT VERIFIED.
      - **CI values**:
        - `detection_run.json` records `plan_exit_code: 2`;
        - the drift report has `has_drift: true`, `outcome: succeeded` and `external_drift` on `tags.owner` (desired `absent`, actual value present).
      - **Inferred, not directly verified**: `drift_detected=true` / `drift_status=detected`. The step outputs appear only in the job log. They are deduced from the public "Drift detected in dev" annotation, which `drift-detection.yml` emits only in the branch that writes `drift_detected=${has_drift}` with `has_drift = true`.
      - **Jobs**: all 6 jobs succeeded. `plan-and-analyze` took 655 s, of which `Drift Investigation` took 600 s (G8 `not_before` = `run.finished_at` 04:23:28Z + 10 min). `investigation` took 17 s, `issues` 10 s, `cost` 10 s and `report` 3 s. AI run #15 took 25 s.
      - **Investigation**: `outcome: complete`, `failure: null`, `binding.evidence_outcome: complete`, completeness `settled: true` (1 poll, `queried_at` 04:33:28Z).
      - **AI report v2**:
        - verdict `sole_capable_operation`, `property_link: inferred_not_provable`;
        - one operation `Microsoft.Resources/tags/write`, `successful`, `exact` + `extension`, `before_observation`;
        - `recorded_caller` `recorded`, `user`, `azure_portal`, `pipeline_identity: false`, identity `withheld`; actor attribution `not_confirmed_by_available_evidence`;
        - LLM `provider: none`, `not_attempted`, nothing sent;
        - recommendation `restore_declared` (R4) with the accept-remote note, `approval_required: true`, `automatic_apply: false`, `execution_allowed: false`.
      - **WHEN to the second**: the operation's start (first row) and end (last Succeeded row) equal the Azure record when truncated to whole seconds, and the last row is `Succeeded` (Activity Log check above).
      - **Hash binding**: the canonical public drift report SHA-256 `7095c361c8dddbdbffacc12560811775a31ecc83e9c78411439793a04693e4a0` is the same in the cost, investigation and AI artifacts.
      - **Leak scan**:
        - the investigation passes `load_public` (contract and full G11 leak scan);
        - `leak_findings` returns 0 findings in every JSON file;
        - there are 0 GUIDs, emails/UPNs, ARM paths, IPs or JWTs, and 0 live subscription, tenant or user values (compared in memory);
        - the only token-like strings are the public run commit SHA (`717a2f0…`) and Terraform type names.
      - **Determinism**:
        - regenerated at AI run #15's `headSha` `717a2f0` in a temporary scratchpad worktree, with a fresh Python 3.13.12 venv (3.12 is not available locally);
        - the workflow pin check passed (all 43 pins);
        - the command was the exact `env -i … AI_LLM_PROVIDER=none ai-analysis --report … --investigation …` and exited 0;
        - the regenerated files are byte-identical to the downloaded files: `ai_analysis_report.json` `9ab2fb24fd581e12e421b6d1d85fee7fed6879640660ec245d7a75a252995b2c` and `ai_analysis_report.md` `0c8a5e8e0e82b1a108de20f5cd3e6d5b1f76d837fbbc8c9830340cded0b3c86b` (downloaded = regenerated for each);
        - **Output path deviation**: the output is in `primary/regenerated-717a2f0/`, not the criterion's `primary/regenerated/`. That folder already existed, from an earlier regeneration (same hashes) with no recorded provenance; it is not used as evidence.
      - **Local WHO (Steps 2 and 4 only)**:
        - Step 2: the folder is 0700, the file is 0600 and git-ignored, `terraform_version` is `1.14.7`, every drift report address is in the state, and the ARM ID parses with resource group `aitdd-dev-main-rg` and the live subscription;
        - the lock file is unchanged;
        - Step 4: `failure: null`, 1 result `matched`, exactly 1 distinct non-empty caller, public `caller_status: recorded`, `public_binding` run `github-38023838144-1` and the hash matches;
        - the caller was not printed or recorded.
    - **NOT VERIFIED** (missing evidence; not passed):
      - **Job-log scan record**: D-4 records only the GUID categories for runs #32 and #15 (A = 2, B = 4, C = 8). The archive-to-run mapping, coverage, the other categories and the `***` mask count are not recorded. The archives are outside the repository, and Claude has no access to them (Execution Rule 16).
      - **Values printed only in job logs or step summaries**: `investigation_status` / `investigation_detail`, `drift_detected` / `drift_status` (inferred above), the `report` job's "Result VALID", and the runner image and Azure CLI version.
      - **Local WHO, user steps**: the exit codes of Step 1 (`init`, `show -json`) and Step 3 (`who`; Pass requires exit 0), and whether Step 3 ran in a fresh environment installed from the primary run's commit `717a2f0`. These are not recorded; the existence of `who_evidence.local.json` with `failure: null` does not establish them.
      - **Anchor process**: no record that the anchor was identified in pre-check 0 and re-confirmed immediately before the dispatch.
  - **Control A (as of 15:41Z): not executed** (no second tag write; see above; executed later as run #36, see below). Run #35 does not count. The scenario is still possible: as of 15:41Z the primary tag is present and no in-sync run has happened since anchor #31.
  - **Control B: not executed.** Issue #8 is still open (public API, as of 2026-10-10 16:08Z).
  - **Cycle 1 status when D-6 was decided (2026-10-11; history, not used for closure)**:
    - **Control A** = drift run #36 `38067518562` / AI run #19 `38068293818`, on `be10e62`, after a second tag write (`tags/write` 16:21:54–16:21:56Z, ingested 16:22:58Z).
      - **PASS**: artifact digests and structure, `ambiguous` (`multiple_capable_operations`), `multiple_operations` with `candidate_operations: 2`, R4 `restore_declared`, hash binding, leak scans, determinism, issue #8 updated with no duplicate, and the AI run #19 job log (D-4: A = 1, B = 0, C = 4, 0 unclassified).
      - **NOT VERIFIED**: the drift run #36 job log.
    - **Primary anchor re-confirmation (#32)**: identification found in a session record; the re-confirmation immediately before dispatch is NOT RECORDED.
    - **Local WHO for #32, re-run 2026-10-11**: the user reported `who` exit 0 in a fresh environment at `717a2f0`. Step 2 and Step 4 PASS. The original evidence was kept in `who-local/original-2026-10-10/`.
  - At the D-6 decision, Phase 9B was not closed and Phase 10 was on hold.
- **Completion Notes**:
  - **Completed 2026-10-11 on cycle 2 (D-6).** All four runs are `workflow_dispatch` on `main` / `dev`, commit `4d89c940de59df53c43ea80cbde3a0dc9e2ab1b9` (it contains the D-4 B fix `c3cf8a0` and the D-6 test fix), attempt 1, conclusion **success**, every job **success**. Each triggered AI run has `headSha` `4d89c94` and succeeded. No other drift run (scheduled or dispatched) ran between #36 and #40.

    | Role | Drift run | Created → finished (UTC) | AI run (`headSha`, conclusion, window) |
    | --- | --- | --- | --- |
    | R1 in-sync anchor (G9) | #37 `38104177960` | 02:08:31 → 02:10:11 | #20 `38104270957` (`4d89c94`, success, created 02:10:13) |
    | R2 primary | #38 `38105671846` | 02:35:55 → 02:47:25 | #21 `38106282914` (`4d89c94`, success, 02:47:30–02:47:51) |
    | R3 Control A | #39 `38109121618` | 03:40:06 → 03:51:25 | #22 `38109723662` (`4d89c94`, success, 03:51:29–03:51:57) |
    | R4 Control B | #40 `38111406531` | 04:23:02 → 04:24:25 | #23 `38111478809` (`4d89c94`, success, 04:24:29–04:24:53) |

    - **Azure changes** (all made by the user in the Azure Portal; each one `Microsoft.Resources/tags/write`, successful, caller type `user`, client `azure_portal`, one recorded caller, identity never printed or recorded):
      - before R1, removal of the cycle-1 test tags: 01:58:26–01:58:28Z;
      - before R2, `drift_test` = `primary-r2`: 02:27:00.310062–02:27:03.028847Z, available 02:29:00Z;
      - before R3, `drift_test-2` = `control-a-r3` (key accepted as-is by user decision): 03:34:30.341314–03:34:32.794486Z, available 03:36:07Z;
      - before R4, removal of both test tags in one write: 04:18:02.344–04:18:05.078Z, ingested 04:19:47Z.
      - Each pre-dispatch Activity Log query was complete with 0 dropped events. After R4, `aitdd-dev-main-rg` has exactly the three declared tags (`environment`, `managed_by`, `project`; read-only checks 04:25:37Z and 04:46:23Z).
    - **R1 (anchor)**: no drift annotation; investigation `complete` with 0 resources; issue #8 closed `completed` at 02:10:08Z, inside R1's `Drift Issues` job (02:09:55–02:10:11Z), Task 8.3. R2's and R3's investigations accepted it as anchor `github-38104177960-1`; G9 accepts only a report in which the address is `in_sync`. Artifact digests (not downloaded): `drift-report` `778d030a69345b27495fa81da5f84562ec5dbc0cf5015dec1b5cf8f5176df12b`, `drift-investigation` `39ab3a393087ba80e6e8e3ec29eaf0c1a53a0c07571ce495045d3b7886a47654`, `infracost-report` `07b589c2c2431400f083bcb7b95600743330a4f6f2b9af00e8df25b346f54449`.
    - **Anchor timing (D-6)**: R1 finished 02:10:11Z; anchor identified 02:16:50Z; re-confirmed 02:34:30Z and, immediately before the dispatch, 02:35:41Z; R2 created 02:35:55Z.
  - **Primary scenario (R2)**: PASS.
    - **CI result (G18)**: `detection_run.json` `plan_exit_code: 2`. Job log literals: `DRIFT_DETECTED: true`, `DRIFT_STATUS: detected`, `INVESTIGATION_STATUS: succeeded`, `INVESTIGATION_DETAIL: none`. The `report` job logged "result VALID; drift_detected=true". `drift-report` has `has_drift: true` and `external_drift` on `tags.drift_test` (desired `absent`, real value present). The issues job created issue #9 at 02:47:22Z (inside 02:47:09–02:47:24Z).
    - **Durations**: `plan-and-analyze` 660 s (`Drift Investigation` step 601 s, the G8 settling wait), `investigation` 12 s, `issues` 15 s, `cost` 7 s, `report` 3 s; AI run #21 21 s.
    - **Runner**: image `ubuntu-24.04` `20261004.327.1`, runner `2.337.0` (from the job log). Azure CLI `2.90.0`, from that image's published readme (tag `ubuntu24/20261004.327`), because the job log does not print it.
    - **Investigation**: `outcome: complete`, `failure: null`, `binding.evidence_outcome: complete`, `settled: true` (1 poll at `not_before` 02:46:54Z, max ingestion delay 119.689 s); anchors examined 37, accepted 14, rejected `report_invalid` 23.
    - **AI report v2** (every item of "Phase 9B end-to-end acceptance"):
      - WHAT `external_drift` on `tags.drift_test`, desired `absent`;
      - operation `op-1` `Microsoft.Resources/tags/write`, `successful`, relations `exact` + `extension` in one group;
      - WHEN event start and end, `available_at` 02:29:00Z, last in-sync observation (R1, 02:09:11–02:09:32Z), observation 02:36:35–02:36:54Z and plan timestamp 02:36:45Z, labelled separately; timing `before_observation`;
      - WHO `recorded_caller` `recorded`, `user`, `azure_portal`, `pipeline_identity: false`, identity `withheld`; actor attribution `not_confirmed_by_available_evidence`;
      - correlation `sole_capable_operation`, `property_link: inferred_not_provable` (`no_property_values_in_activity_log`), completeness `settled: true`;
      - LLM `provider: none`, `not_attempted`, nothing sent;
      - recommendation `restore_declared` (policy v1, R4) with the accept-remote note, `approval_required: true`, `automatic_apply: false`, `execution_allowed: false`.
    - **WHEN to the second**: the operation's first-row start and last `Succeeded` row end equal the Azure record (to the microsecond); only timestamps, operation names and statuses were printed.
    - **Hash binding**: the canonical public drift report SHA-256 `db9db841af415434ecd3c1cc3c11ad8365ee54adf6136b6662ac10e7cb9d0b5b` is the same in the cost, investigation and AI artifacts.
  - **Control A (R3)**: PASS.
    - plan exit `2`; log literals `DRIFT_DETECTED: true`, `DRIFT_STATUS: detected`, `INVESTIGATION_STATUS: succeeded`, `INVESTIGATION_DETAIL: none`; "result VALID; drift_detected=true"; `external_drift` on `tags.drift_test` and `tags.drift_test-2`.
    - investigation `complete`, `failure: null`, `settled: true` (queried 03:50:55Z); anchor still `github-38104177960-1` (no in-sync run in between).
    - verdict **`ambiguous`** (`multiple_capable_operations`), no decisive operation; `op-1` is the R2 write (identical public fields) and `op-2` the R3 write, both `capable`, `before_observation`, `user` / `azure_portal`, caller `recorded`, `pipeline_identity: false`.
    - `who.recorded_caller.status: multiple_operations`, `candidate_operations: 2`; actor attribution `not_confirmed_by_available_evidence`.
    - recommendation unchanged at `restore_declared` (R4).
    - issue #9 updated at 03:51:20Z inside R3's issues job (03:51:07–03:51:24Z), 0 comments, no second issue.
    - cost job and AI run #22 succeeded; hash binding `64ba26717406d8633d8d62d4bc94530b27127d9939f4f39acd0e285df9240f72` across the three artifacts.
    - `plan-and-analyze` 647 s (`Drift Investigation` 601 s).
  - **Control B (R4)**: PASS.
    - plan exit `0`, `has_drift: false`, `{"in_sync":5}` (0 of 5 drifted); log literals `DRIFT_DETECTED: false`, `DRIFT_STATUS: none`, `INVESTIGATION_STATUS: succeeded`, `INVESTIGATION_DETAIL: none`; "result VALID; drift_detected=false".
    - investigation `complete` with 0 resources and 0 anchors examined (no anchor fetch; `Drift Investigation` step 8 s); AI report v2 with 0 resources and no investigation claims.
    - issue #9 closed `completed` at 04:24:20Z, inside R4's issues job (04:24:09–04:24:24Z), Task 8.3.
    - resource group back to exactly its three declared tags; hash binding `e85719d37998315ea964e424e4eab4eda59be65086bd05f06dd21faf9d190ea0`.
  - **Artifacts** (each downloaded ZIP's SHA-256 equals its GitHub digest; flat regular files only, valid CRCs, extracted files equal the members; all expire 2026-11-10). `infracost-report` was downloaded for all three scenarios, beyond the primary-only requirement:

    | Scenario | `drift-report` | `drift-investigation` | `ai-analysis-report` | `infracost-report` |
    | --- | --- | --- | --- | --- |
    | R2 | `b8be685c37dc1b3729ebe1f507055d7e54b2e5a2cc0baebaa7282e696e8ff531` | `4c86dab2a840b5cc5d2e6774d0affd860cc2d15f544fc343c7e7aeb7c0855575` | `ae79e115dff3215cd5e07d3e291ffe4d880c0902cd1946ee99f653ce72e852e0` | `82911f392849cc07808e749f312b032d318e37bf0f692f0278036944f11ee402` |
    | R3 | `e39bab51ae3b4268f9125df9eead765e7d12785346f2d508c6abae8567a5d643` | `88bc08eab59907dc57187fb11d17c42b45a43c9f26fb0179af5f6db88c55f736` | `ca454550632d6295aee26df2ab6f038c83caccf7d476d46aeb00617005b6459c` | `1af035b785cc9c54a2a272df8babd141d7017a237d26e89dc79e68976ad3e266` |
    | R4 | `7442edd13c756586d1f491597117f6348101f14f9508f8367fd8bc0457399a45` | `0cdf214af2f5e5c0a043cb15a61ecfb1dc13dc919660c61d16ea0ada858212c8` | `23f36360cddfbe504be44712aa7ce4093c4eb81a5139d5b86b8eece58fe27c05` | `36a2bcd5bdf32f7554ba857ace3d3233fe88c77fbea92878c9dc3afc92034862` |

  - **Leak scan (artifacts)**: PASS for all 12 artifacts (21 files). Every public investigation passes `load_public` (contract and full G11 scan); `leak_findings` returns 0 in every JSON file; 0 GUIDs, emails/UPNs, ARM paths, IPs or JWTs; the live subscription ID, tenant ID and signed-in user (compared in memory) appear in no file. The only token-like strings are hex hashes and commit SHAs, Terraform type names, three snake_case fixed codes and the `-chdir=terraform/environments/dev` flag. The test tag values are neutral.
  - **Job logs (D-4)**: PASS. The user downloaded the six run log archives into a 0700 folder outside the repository (files 0600). They were read in memory, and only counts were printed.
    - Archive-to-run mapping: each archive is named after its run's `check_suite_id`. Its job and step names match the public API, its timestamps fall inside the API job windows, and the drift run id appears 20 times in each drift archive and the source run id 31 times in each AI archive. Archives: `logs_103243558526.zip` (R2), `logs_103245153873.zip` (AI #21), `logs_103252610018.zip` (R3), `logs_103254175046.zip` (AI #22), `logs_103258625360.zip` (R4), `logs_103258815442.zip` (AI #23).

      | Run | In-scope log | Coverage (lines scanned / total) | A | B | C | Unclassified | `***` masks |
      | --- | --- | --- | --- | --- | --- | --- | --- |
      | R2 #38 | `Drift Investigation` step | 39 / 39 | 0 | 0 | 0 | 0 | 2 |
      | R2 #38 | `investigation` job (12/12 steps) | 374 / 374 | 1 | **0** | 4 | 0 | 3 |
      | AI #21 | `ai-analysis` job (15/15 steps) | 596 / 596 | 1 | **0** | 4 | 0 | 5 |
      | R3 #39 | `Drift Investigation` step | 39 / 39 | 0 | 0 | 0 | 0 | 2 |
      | R3 #39 | `investigation` job (12/12 steps) | 374 / 374 | 1 | **0** | 4 | 0 | 3 |
      | AI #22 | `ai-analysis` job (15/15 steps) | 596 / 596 | 1 | **0** | 4 | 0 | 5 |
      | R4 #40 | `Drift Investigation` step | 38 / 38 | 0 | 0 | 0 | 0 | 2 |
      | R4 #40 | `investigation` job (12/12 steps) | 374 / 374 | 1 | **0** | 4 | 0 | 3 |
      | AI #23 | `ai-analysis` job (15/15 steps) | 596 / 596 | 1 | **0** | 4 | 0 | 5 |

    - Other categories in every in-scope log: 0 emails/UPNs, ARM paths, IPs, JWTs or live subscription, tenant or user values; 0 `##[error]` lines emitted.
    - B = 0 in both in-scope jobs of R2, R3 and R4 (D-4 B fix effective). The 4 pre-fix B GUIDs of runs `38023838144` and `38024516418` (cycle 1) stay the one-time recorded finding.
    - The Phase 5 diagnostic outputs (`Verify Azure OIDC Authentication`, the failure-only `plan.log` tail) stay excluded (D-2) and remain a Phase 12 known limitation.
  - **Local WHO (R2)**: PASS.
    - Step 1 (user, own terminal): `terraform init` exit 0, `terraform show -json` exit 0, into `cycle2/who-local/terraform-state.json`.
    - Step 2 (Claude, booleans only): folder 0700, file 0600 and git-ignored; `terraform_version` `1.14.7`; all 5 drift report addresses in the state; the drifted address's ARM ID parses with resource group `aitdd-dev-main-rg` and the live subscription; `.terraform.lock.hcl` unchanged.
    - Step 3 (user, own terminal): `drift-engine who` exit 0, from a fresh detached worktree at `4d89c94` with a fresh Python 3.13 virtual environment installed with the `[azure]` extra and `ci/azure-constraints.txt`.
    - Step 4 (Claude, booleans and counts only): `failure: null`; 1 result `matched` for 1 public operation (`op-1`, operation name, start and end equal the public operation); exactly 1 distinct non-empty caller; public `caller_status: recorded`; `public_binding` run `github-38105671846-1` and drift report hash `db9db841…` match. Evidence file `who_evidence.local.json` SHA-256 `ab8e95602f8526a286ead44a9fc4c048c2ef894581dfd0a59c897a7390df7860`. No caller, ID or state content was printed or recorded. As G3 requires, this does not claim the recorded principal caused the drift.
    - **Supplementary (not an acceptance criterion)**: `who` for R3 (user, exit 0, output `cycle2/who-local/control-a/`) returned 2 results, both `matched`, each with exactly 1 distinct non-empty caller; `op-1`'s caller equals R2's, and `op-2`'s caller is different (compared in memory). This shows the local path separates the two recorded callers per operation. The public attribution stays `not_confirmed_by_available_evidence`. Evidence SHA-256 `82c45d407eeabe0b5d09b4fbddc457bf78fe43312d66efcae1d8a3ba3ee03f95`. The file is unchanged since `who` wrote it (created and last modified 04:16:42Z). A different value quoted in the cycle-2 session's prose summary is not backed by its tool output and is not used.
  - **Determinism**: PASS. For each scenario: AI run `headSha` `4d89c94`, a temporary scratchpad worktree of that commit, a fresh Python 3.13.12 venv (3.12 is not available locally) installed with `pip install -c ci/ai-constraints.txt ".[ai]"`, the workflow pin check (43/43), the exact `env -i … AI_LLM_PROVIDER=none ai-analysis --report … --investigation …` command exiting 0, and inputs used unchanged. Regenerated = downloaded:
    - R2 (AI #21): JSON `4ec740e08bc506bb4acb44315acda27589d4793fe72a34a97b28cbfa0e658008`, Markdown `b48457934d6d4363327268c80ccbced96a0902957fbd3144b2bd3f5bb376f775`;
    - R3 (AI #22): JSON `d6be26a7938aedb61301b23be56219c8846474fab131c70f4b29ad29badf93b2`, Markdown `c22436517ee3ce2f799b73a47d33f6658c9b0d88390a690ac2044233df760a84`;
    - R4 (AI #23): JSON `59455b5b19c07daa9544de7914a607d04b2033cd813ef2e5d9c02cfc848a628e`, Markdown `b65f97a80c1013824d5da8619189bda55fccb8be5c2f3264d748cb83577148cd`.
    - Verified in the cycle-2 session and re-verified independently at closure (new worktree and venv, removed afterwards).
  - **Fixture-verified paths (no safe real producer)**: `latest_capable_operation` and the confirmed-deletion path remain fixture-verified, as recorded in Tasks 9B.2–9B.4A. Their tests are part of the green suite, e.g. `tests/test_investigation.py` (`test_anchor_a_confirmation_under_latest`, `test_overlapping_latest_is_ambiguous`) and `tests/test_ai_investigation.py` (`ScenarioTests.test_without_an_anchor_the_latest_operation_is_decisive`, `test_confirmed_deletion`, `test_deletion_not_confirmed_by_the_rule`, `test_rule_confirmed_deletion_under_an_ambiguous_verdict_stays_inferred`). The deletion scenario's leak-free public projection is the Task 9B.4A fixture evidence.
  - **Tests**: full suite on commit `4d89c94` (clean detached worktree, Python 3.13.12, venv installed with `-c ci/ai-constraints.txt -c ci/azure-constraints.txt -e ".[dev,ai,azure]"`, re-run at closure on 2026-10-11): `pytest --cov=src/drift_engine tests/` **2365 passed**, 3960 subtests, 0 failed, coverage **99.45%** (gate 85%). The same result was recorded before the commit on a working tree byte-identical to `4d89c94`. The two pin-closure tests (`test_constraints_equal_the_complete_ai_closure`, `test_azure_constraints_equal_the_complete_azure_closure`) require the constrained install by design.
  - **Scope of the proof**: it covers a tag addition (sole capable operation), a second tag write (ambiguous) and a return to in-sync on one resource group. It does not show that every Azure drift type is investigated correctly. The Activity Log carries no property values (`property_link: inferred_not_provable`), and a recorded caller is never treated as proof of who caused the drift (G3).
  - **Closure applied**: Phase 9B 🟢; Phase 6 and Phase 7 back to 🟢; Phases Completed 9 of 14 (Phases 1–9); `README.md` phase status and limitations reconciled; Phase 10 🟡 with Task 10.2 ⬜ NOT STARTED as the Current Active Task (not started automatically, Execution Rule 8).

---

### PHASE 10 — FinOps / Cost Analysis
**Status**: 🟢 COMPLETED (2026-10-11) — Task 10.1 🟢 completed 2026-10-04; Task 10.2 🟢 completed 2026-10-11; Task 10.3 🟢 completed 2026-10-11; Task 10.4 🟢 (unmanaged resources, user-requested 2026-10-11) completed 2026-10-11. Tasks 10.3 and 10.4 were verified together by drift-detection run #44 `38140497702` and AI analysis run #27 `38140599354` on commit `8ef89b6` (the on-hold decision of 2026-10-04 ended when Phase 9B completed on 2026-10-11).

Phase 10 integrates Infracost to provide deterministic cost estimates for configuration drift and infrastructure changes. Task 10.4 adds a separate, read-only inventory of Azure resources that Terraform does not manage, with an Azure Retail Prices API list-price estimate that is never drift and never combined with the Infracost amounts.

> **Phase 10 rules (recorded 2026-10-04 per the Task 10.1 design review and pre-lock verification).**
> - **Cost is never drift**: Infracost output never creates, changes or invalidates a drift result, the drift report, `drift_detected`/`drift_status`, the drift artifact or drift issues. A cost failure is a cost failure, never "drift unknown".
> - **Deterministic numbers only**: monetary figures come only from Infracost output; nothing is estimated, interpolated or invented (Task 10.3 inherits this).
>   - **Amendment (2026-10-11, Task 10.4, user decision 1)**: this applies to Terraform-plan amounts. Amounts for Azure resources **outside Terraform** come only from exactly matched Azure Retail Prices API meters (list prices, USD), are labelled as such, and are never added to, compared with or subtracted from Infracost amounts; nothing is interpolated or invented and an unknown price is never zero.
> - **List prices only**: Infracost Cloud Pricing API public list prices, USD, no usage file, no discounts/reservations/actual costs. Prices change over time, so results are tied to `timeGenerated` and the CLI version, not reproducible across dates.
> - **No Infracost Cloud features**: `infracost upload`, `infracost comment`, dashboard and usage API are never used.
> - **Exact pins and checksum-verified binaries**, as in Phase 9.

#### Task 10.1 — Infracost CLI Integration
- **Status**: 🟢 COMPLETED — design locked 2026-10-04 (Task 10.1 design review, pre-lock verification and user decisions D1–D9, implementation interface I1–I5)
- **Started**: 2026-10-04
- **Completed**: 2026-10-04
- **Objective**: Produce a deterministic, sanitised Infracost cost estimate from the **same refreshed `plan.json`** that each valid drift-detection run classifies, and publish it as a separate artifact for Task 10.2, without ever changing the drift result.
- **Dependencies**: Task 5.3 (plan evidence), Task 5.4 (artifact), Task 5.5 (failure reporting/outputs), Task 2.6 (OIDC job context it must de-privilege); Task 9A.1 (same-run binding and canonical report hash conventions).
- **Amendment (2026-10-05, Task 9B.4A (public drift report projection, user-approved P1–P4, 2026-10-05))**: the cost binding's `drift_report_sha256` and the check job's `--drift-report` input are the **public** drift report: it is the only drift report in the artifact, and the internal report's hash is never published.
  - `scripts/sanitize_infracost.py` gains a fail-closed guard that refuses a report without `public_version` (Task 9B.4A).
  - The workflow wiring is Task 9B.5.
  - The cost estimate, its sanitisation and the D1–D9 decisions are unchanged.
  - The real CI proof recorded below predates this and stays historical.
- **Downstream consumers**: Task 10.2 (`src/drift_engine/cost.py` parses the sanitised `infracost.json`), Task 10.3, Task 13.1.
- **Pre-lock verification (2026-10-04, session scratchpad, isolated `HOME`, no API key, no live pricing call)**:
  - v0.10.46 (`infracost/infracost`, 2026-09-25, stable). Linux amd64 SHA-256 matched three ways (release `.sha256` sidecar, GitHub asset digest, local `shasum`). Tarball holds one file, `infracost-linux-amd64`.
  - A separate product, Infracost CLI v2 (`infracost/cli`, v2.17.0), exists; it has no documented `breakdown`/`diff`/plan-JSON support and uses `INFRACOST_CLI_AUTHENTICATION_TOKEN`. **Not used.**
  - Without a key, `breakdown` exits 1 (`INFRACOST_API_KEY is not set but is required`). The key comes from `INFRACOST_API_KEY` or `$HOME/.config/infracost/credentials.yml`. Keys belong to an Infracost organisation (account required).
  - Source (tag v0.10.46): `INFRACOST_SKIP_UPDATE_CHECK` stops the update check (otherwise `api.github.com/repos/infracost/cli` + Homebrew, and `.state.json` with an `installId`); `INFRACOST_ENABLE_CLOUD=false` stops the dashboard settings query and org-level cloud enablement; `INFRACOST_DISABLE_ENVFILE=true` stops `.env` loading from the working directory; `infracost-run`/`infracost-error` usage events have **no supported off switch** (only the internal `INFRACOST_ENV=test` mode).
  - Plan JSON: without `--compare-to`, `pastBreakdown` is built from `prior_state` (refreshed real infrastructure) and `breakdown` from `planned_values`.
  - Output contains `metadata.vcsCommitAuthorName`/`vcsCommitAuthorEmail` (always emitted), `vcsCommitMessage`, `vcsBranch`, `vcsCommitSha`, `vcsRepositoryUrl`, `vcsPipelineRunId`, `projects[].metadata.path`, git-derived project names, resource `tags` and free-form resource `metadata`.
  - All five dev resource types (`azurerm_resource_group`, `azurerm_virtual_network`, `azurerm_subnet`, `azurerm_network_security_group`, `azurerm_subnet_network_security_group_association`) are in v0.10.46's Azure `FreeResources` list; the dev modules declare exactly these types. Expected dev estimate: **$0.00/month**.
- **Locked decisions (2026-10-04)**:
  - **D1 — Version and install**:
    - Infracost **v0.10.46**, classic CLI (`infracost/infracost`). Not v2, never the rolling `preview` prerelease, no Infracost GitHub Action, no image, no install script.
    - CI installs `https://github.com/infracost/infracost/releases/download/v0.10.46/infracost-linux-amd64.tar.gz`, checks SHA-256 **`d0d081cd39b07b2ca5c315830bfc4bcdfb0183b04c19cb18835c154482a2c97b`** (committed in the workflow) with `sha256sum -c` before unpacking, extracts only `infracost-linux-amd64` and installs it as `infracost`, then requires `infracost --version` to equal `Infracost v0.10.46`. The download, checksum check and unpacking run **inside the cost step** (D5), never as a separate step, so an installation failure is a cost failure (`install_failed`, I2) and cannot alter `plan-and-analyze` *(user decision 2026-10-04, Step 3 review)*.
    - Local runs use the darwin-arm64 tarball (SHA-256 `09fa73ecdc762c1b557df70234eb44cc446a9a9e412a4ab326185cac3f39e631`) in the **session scratchpad only** (Rule 16).
  - **D2 — Mode**: exactly `infracost breakdown --path <plan.json> --format json --out-file <raw> --no-color`, on the `plan.json` produced by `scripts/generate_plan_json.sh` in the same job and run that `drift-engine analyze` classified. No HCL/directory mode, no `--terraform-var-file`, no `diff` command, no `--compare-to`, no usage file, no second `terraform plan`, no Terraform plan, init or HCL evaluation by Infracost; the only Terraform invocation is the start-up `terraform -version` described in the D7 amendment (Checkpoint disabled). *(Wording fixed 2026-10-04, user decision, to match the D7 amendment.)*
  - **D3 — Cost-difference definition**: `diffTotalMonthlyCost` = `totalMonthlyCost` (desired, `planned_values`) − `pastTotalMonthlyCost` (actual, refreshed `prior_state`) = cost of *reverting* to the desired configuration. **Drift cost = −`diffTotalMonthlyCost`.** No committed cost baseline. Task 10.2 must use this sign convention.
    - **Amendment (2026-10-11, Task 10.2, user decision)**: the sign convention is unchanged. The run-level −`diffTotalMonthlyCost` combines drift and pending configuration changes, so Task 10.2 publishes it as `infracost_plan_delta`, never as drift cost; drift cost is only the `confirmed_drift` subtotal (see Task 10.2). "Actual" in this decision means the list-price estimate of the refreshed current configuration of Terraform-managed resources, not actual Azure billing.
  - **D4 — Thresholds**: none. No cost increase, decrease or total fails anything; cost is informational. Only failures of the cost process itself (D5) fail.
  - **D5 — Placement and failure isolation (Option A)**:
    - **Amendment (2026-10-05, Phase 9B G10 / Task 9B.5 design review)**: the cost step stops being the *single* exit-0 exception.
      - `Drift Investigation` is a second documented always-exit-0 step with the same status-capture pattern.
      - `Upload Drift Investigation` is a second `continue-on-error` upload.
      - The workflow then has exactly two of each. Placement (after `Upload Drift Report`, before the cost step), the cost step's condition and the `cost` job are unchanged.
      - The record below is historical.
    - **Placement**: new steps at the end of `plan-and-analyze` in `drift-detection.yml`, after `Upload Drift Report`, running only when the drift classification is valid (`steps.analyze.outputs.drift_detected` is the literal `true` or `false`) and the drift artifact uploaded. A detection failure or `unknown` result runs no cost step (the run is already red; cost is "not run", not a cost failure).
    - **Failure capture**: the cost step captures the script's exit code and publishes `cost_status` = `succeeded` / `failed` (plus `cost_failure`, a fixed reason code) as step and job outputs, and **exits 0 itself**. This is the single, documented exception to the "no exit-code remapping" rule (**approved by the user 2026-10-04**). It exists only so a cost failure cannot alter `plan-and-analyze`'s result, the drift outputs, the `issues` job (implicit `success()`) or the `report` job's VALID/UNKNOWN verdict. It never hides the failure: see `cost` job below.
    - **New `cost` job** (`needs: [preflight, plan-and-analyze]`; `if: !cancelled()` and `drift_detected` literal `true`/`false`; permissions exactly `contents: read`; no `id-token`, no Azure, no secrets; `persist-credentials: false`): fails (exit 1) unless `cost_status == succeeded`, `cost_upload_outcome == success`, the `infracost-report-<run_id>` artifact downloads, both files pass the sanitiser's `--check` (allowlist schema, binding to this run attempt, CLI version), and then writes a **totals-only** step summary. A cost failure therefore makes the **overall workflow run red** while `drift_detected`, `drift_status`, the drift report and artifact, issues and the `report` job stay exactly as they would be without Phase 10.
    - **Installation boundary** *(user decision 2026-10-04, Step 3 review)*: the pinned Infracost installation (D1) runs inside the cost step, before `scripts/infracost_analysis.sh`. If it fails, the step itself writes `cost_status=failed` and `cost_failure=install_failed` to `$GITHUB_OUTPUT`, does not run the script, and exits 0 (the D5 exit-code exception); the `cost` job then fails.
    - **Second documented exception — cost-artifact upload** *(approved by the user 2026-10-04, Step 3 review)*: the single `actions/upload-artifact` step for `infracost-report-<run_id>` (in `plan-and-analyze`, the only runner holding the files) has `continue-on-error: true`, so an upload failure cannot alter `plan-and-analyze`, the drift outputs, `issues` or `report`. Its outcome is published as the job output `cost_upload_outcome`, and the `cost` job fails unless it is `success`, so the failure is never hidden. No other step may use `continue-on-error`.
    - `preflight`, `issues`, `report`, triggers, workflow-level permissions, concurrency and the drift outputs are unchanged; `report` keeps `needs: [preflight, plan-and-analyze]` (**report job unchanged: approved by the user 2026-10-04**).
  - **D6 — Secret and privilege reduction**:
    - Repository secret **`INFRACOST_API_KEY`**, created by the user together with the Infracost account/organisation (Rule 10). Referenced **only** in the cost step's `env`. Never printed, never written to disk by the workflow, never passed to another step or job. The workflow triggers stay `schedule`/`workflow_dispatch` on `main` (no fork or PR exposure).
    - Before Infracost runs, the step removes Azure and OIDC capability: `az logout` and `az account clear`; `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` removed from the step's process environment by a clean re-exec of the step shell (amendment below); no `ARM_*`, `AZURE_*` or `GITHUB_TOKEN` in the step. The script **fails closed** (cost failure) if either OIDC request variable is non-empty or `az account show` still succeeds.
    - **Amendment (2026-10-04, user decision after CI run #20) — OIDC request variables**:
      - **Runner behaviour (verified)**: blanking the two variables in the step's `env:` is ineffective. The GitHub runner (`actions/runner`, `src/Runner.Worker/Handlers/HandlerFactory.cs` applies the step `env:` as `handler.Environment`; `src/Runner.Worker/Handlers/ScriptHandler.cs` lines 314–318 then set `ACTIONS_ID_TOKEN_REQUEST_URL` and `ACTIONS_ID_TOKEN_REQUEST_TOKEN` at process launch whenever the job may mint OIDC tokens, i.e. `id-token: write`) re-injects them into every `run:` step after the step environment is applied.
      - **Evidence**: run **#20** (id `37195216717`, `workflow_dispatch`, `main`, commit `15b0910`, attempt 1): the cost step reported `cost_status=failed`, `cost_failure=oidc_token_present` and exited 0; `Upload Infracost Report` was skipped; the `cost` job failed in `Require Cost Success`; `preflight`, `plan-and-analyze` (all drift steps), `issues` and `report` succeeded and the triggered AI analysis run `37195280852` succeeded, so the drift result was unaffected (D5 behaved as designed). The `missing_api_key` check, which runs first, passed (the secret reached the step); Infracost itself never ran (no pricing call, telemetry or key use).
      - **Mechanism**: the step's first command re-executes the step shell without the two variables: `exec env -u ACTIONS_ID_TOKEN_REQUEST_URL -u ACTIONS_ID_TOKEN_REQUEST_TOKEN bash --noprofile --norc -eo pipefail "$0"`, guarded so it only runs while either variable is set (the re-executed shell finds them absent, so it does not loop). `exec env -u …` is used as a clean re-exec/isolation boundary: the whole cost step (Azure logout, installation, script, Infracost) then runs in a process started without the variables. `shopt -s execfail` and `|| true` keep a failed `exec` from failing the step (which would break D5): the step continues and the script fails closed with `oidc_token_present`. The two ineffective `env:` entries are removed. The script and its `oidc_token_present` check are unchanged.
      - **Residual risk (accepted)**: `plan-and-analyze` keeps job-level `id-token: write` (required for the Azure login), so the runner still holds the request credential for the job, as it does for Terraform and its providers in the same job. Full isolation would need a separate job, which spec §8.3 rules out (`plan.json` never leaves this runner).
      - **Tests**: the executed-step tests run the step file the way the runner does (`bash -e <file>`, with the two variables injected non-empty after the step `env:`), and a regression test shows the run #20 mechanism (step-level blanking without the re-exec) still yields `oidc_token_present` under that runner-realistic harness.
    - `HOME` for Infracost is a fresh `$RUNNER_TEMP/infracost-home`, and the working directory is `$RUNNER_TEMP/cost`, never the checkout.
    - A missing or empty key is a cost failure (`cost_failure=missing_api_key`), detected without echoing the value.
  - **D7 — Egress and environment controls**:
    - Always set: `INFRACOST_SKIP_UPDATE_CHECK=true`, `INFRACOST_ENABLE_CLOUD=false`, `INFRACOST_DISABLE_ENVFILE=true`, `INFRACOST_NO_COLOR=true`, `CHECKPOINT_DISABLE=1` (added 2026-10-04, see below). Never set: `INFRACOST_ENV`, `INFRACOST_PRICING_API_ENDPOINT`, `INFRACOST_ENABLE_DASHBOARD`, `INFRACOST_ENABLE_CLOUD_UPLOAD`, `INFRACOST_TLS_INSECURE_SKIP_VERIFY`.
    - Never run `infracost upload`, `comment`, `auth`, `configure` or `generate` in CI.
    - **Accepted egress (2026-10-04, user decision)**: (a) pricing queries to the Infracost Cloud Pricing API carrying cost-relevant attributes (no plan file, credentials or resource names, per Infracost); (b) unavoidable usage telemetry (`infracost-run`/`infracost-error`: counts, command, flags, an ephemeral `installId`, CI platform). Nothing else leaves the runner. Raw Infracost output stays on the runner, like `plan.json`.
    - **Amendment (2026-10-04, user decision after D9 run 1) — Terraform Checkpoint**:
      - **Root cause (verified)**: Infracost v0.10.46 links Infracost's Terragrunt fork (`github.com/infracost/terragrunt@ddd63fe8e40e`, replacing `gruntwork-io/terragrunt v0.52.4`). Its `options/options.go` sets `var DefaultWrappedPath = identifyDefaultWrappedExecutable()` at Go package start-up, which runs **`terraform -version`** whenever a `terraform` binary is on `PATH`, for every Infracost command (including `--version`), before any Infracost logic and with no Infracost/Terragrunt switch. That `terraform` process then makes its own HashiCorp Checkpoint request (`checkpoint-api.hashicorp.com`; anonymous data plus an anonymous signature, per HashiCorp) and writes `$HOME/.terraform.d/checkpoint_cache` and `checkpoint_signature`. Evidence: a fake `terraform` on `PATH` was invoked as `terraform -version` by the Infracost process; a Go stack dump at that moment shows `terragrunt/options.init()` → `identifyDefaultWrappedExecutable()` → `util.IsCommandExecutable` → `os/exec.(*Cmd).Run`; the Infracost binary has no checkpoint client, the Terraform binary has one. Infracost's own source and pricing API are not involved.
      - **Control**: `CHECKPOINT_DISABLE=1` (Terraform's documented switch: any non-empty value disables Checkpoint entirely) is always set for every Infracost invocation (cost step and live check). Verified locally: with the real `terraform` on `PATH` and `CHECKPOINT_DISABLE=1`, no `.terraform.d/` is created. Stripping `terraform` from `PATH` is not relied on (`setup-terraform` puts it on `PATH` in `plan-and-analyze`). The `terraform -version` child process itself remains (local, no network with the control set) and runs with the same de-privileged step environment (D6).
      - **Fail-closed check**: after the Infracost run, `$HOME/.terraform.d` (the isolated D6 `HOME`) must not exist; otherwise `cost_status=failed`, `cost_failure=unexpected_egress`, no upload. The drift result is unaffected (D5).
      - **Out of scope**: the existing Terraform steps in `drift-detection.yml` (init/validate/plan via `scripts/generate_plan_json.sh`) are not changed by Task 10.1, including any Checkpoint behaviour they have; that is noted for Phase 12 hardening.
  - **D8 — Artifact and sanitisation**:
    - Artifact `infracost-report-<run_id>`, exactly two files, 30-day retention, `if-no-files-found: error`, uploaded only when `cost_status == succeeded`:
      - **`infracost.json`**: an **allowlist** projection of the raw output with Infracost's own key names. Root keeps only `version`, `currency`, `timeGenerated`, `totalHourlyCost`, `totalMonthlyCost`, `pastTotalHourlyCost`, `pastTotalMonthlyCost`, `diffTotalHourlyCost`, `diffTotalMonthlyCost`, `totalMonthlyUsageCost`, `pastTotalMonthlyUsageCost`, `diffTotalMonthlyUsageCost`, `summary` (count fields and per-type count maps only). Each project keeps `breakdown`, `pastBreakdown` and `diff`, each with `totalHourlyCost`/`totalMonthlyCost`/`totalMonthlyUsageCost` and `resources[]`. Each resource keeps only `name` (Terraform address), `resourceType`, `hourlyCost`, `monthlyCost`, `monthlyUsageCost` and `costComponents[]` (`name`, `unit`, `hourlyQuantity`, `monthlyQuantity`, `price`, `hourlyCost`, `monthlyCost`, `priceNotFound`), with `subresources[]` under the same rule. Everything else is dropped, including all of `metadata` (every `vcs*` field, paths, config/usage file paths), project `name`/`displayName`/`metadata`/`summary` (the per-project `summary` duplicates the root one), resource `tags`, `defaultTags` and `metadata`, `runId`, `shareUrl` and `cloudUrl`.
      - **`cost_run.json`** (**approved by the user 2026-10-04**): the binding manifest: `run_id` (`github-<run_id>-<run_attempt>`, equal to the drift report's `run.run_id`), `environment`, `drift_report_sha256` (Task 9A.1 canonical hash of this run's `drift_report.json`), `infracost_version` (`v0.10.46`), `mode` (`plan_json_breakdown`), `pricing` (`list_prices_usd_no_usage_file`), `cost_sign_convention` (D3 text), `generated_at`.
    - **Value types (user decision 2026-10-04, verified on v0.10.46 output)**: every money, price and quantity value is a JSON **decimal string** (e.g. `"119.72"`, `"-106.58"`, `"730"`), copied unchanged by the sanitiser and never parsed as a float (the sanitiser, the `cost` job and Task 10.2 parse them as decimals only). A non-string value where a decimal string is expected is a sanitisation failure.
    - Sanitisation fails closed. An unknown key at an allowlisted level is dropped, not copied; the output is re-checked so no `@`-address, absolute path, URL or GUID string can survive. Any failure gives `cost_status=failed` and no upload.
    - **Missing price (user decision 2026-10-04)**: `priceNotFound` is retained, and any cost component with `priceNotFound: true` gives `cost_status=failed`, `cost_failure=price_not_found`, no upload, so the `cost` job and the run go red; the drift result, report and outputs are unaffected (D5).
    - **Exposure profile** (narrower than `drift-report-<run_id>`): resource addresses and types, public list prices and quantities, totals and counts. No attribute values, tags, identities, paths or VCS data.
  - **Implementation interface (locked 2026-10-04, user decision before implementation; I1–I5)**:
    - **I1 — Sanitiser contract** (`scripts/sanitize_infracost.py`, stdlib only): write mode `python3 scripts/sanitize_infracost.py --raw <raw.json> --drift-report <drift_report.json> --run-id <github-…> --environment <env> --infracost-version v0.10.46 --output-dir <dir>` writes exactly `infracost.json` and `cost_run.json`; check mode `--check <dir> --run-id <…> --drift-report <…>` (used by the `cost` job). Exit codes: `0` written / check passed, `1` sanitisation failure, `2` `price_not_found`, `64` usage. `scripts/infracost_analysis.sh` may be developed against this contract with a stand-in sanitiser, but **final acceptance must be validated against the actual `scripts/sanitize_infracost.py`**, never a stand-in (user constraint 2026-10-04).
    - **I2 — Reason codes and reporting**: `cost_failure` is exactly one of `none` (success), `usage` (exit 64), `install_failed` (reported by the cost step itself: download, checksum, unpacking or placement of the pinned binary failed; added 2026-10-04, user decision), `missing_api_key`, `oidc_token_present`, `azure_session_present`, `version_mismatch`, `infracost_failed`, `unexpected_egress`, `raw_output_invalid`, `price_not_found`, `sanitize_failed`. The script itself appends `cost_status=succeeded|failed` and `cost_failure=<code>` to `$GITHUB_OUTPUT` when it is set, and always prints exactly one final status line. Script exit codes: `0` succeeded, `1` cost failure, `64` usage. The workflow step only captures the exit code and exits 0 (D5).
    - **I3 — Inputs and paths**: environment variables `PLAN_JSON`, `DRIFT_REPORT`, `RUN_ID`, `DRIFT_ENVIRONMENT`, `COST_DIR` (default `$RUNNER_TEMP/cost`; the Infracost working directory); Infracost `HOME` is `$RUNNER_TEMP/infracost-home` (D6); raw output and logs in `$COST_DIR/raw/` (never uploaded), artifact files in `$COST_DIR/report/`. Every directory must be absolute, outside the repository and new or empty; otherwise exit 64 (`usage`).
    - **I4 — No Azure CLI**: if `az` is not on `PATH`, that counts as no Azure CLI session (passes). In CI `az` is present, so `az account show` is always checked there.
    - **I5 — Infracost output handling**: Infracost stdout/stderr (and sanitiser output) are captured to logs in `$COST_DIR/raw/` (never uploaded); the script prints only its final status line on success, or the last 20 log lines on failure. It never prints the key or dumps the environment.
  - **D9 — Testing and proof**:
    - **Step 1, pre-implementation live check** (needs the user's key; no Azure, no CI). **Key handover option (a), user decision 2026-10-04**: the **user runs** the D2 command with the D7 controls in their own terminal, with `INFRACOST_API_KEY` exported there and an isolated `HOME` and output directory under the gitignored `.artifacts/task-10.1-live-check/` (Rule 15). Claude never requests, receives, stores or handles the API key; it only provides the command and inspects the key-free output files afterwards. Inputs: (a) the committed real-derived `tests/fixtures/plan_evidence/in_sync/plan.sanitized.json` and (b) a new synthetic plan with `prior_state` + `planned_values` for a priced type (D9 fixture: `tests/fixtures/infracost/service_plan_sku_drift/plan.synthetic.json`, generated by `tests/fixtures/infracost/build.py`; Linux `azurerm_service_plan`, real `P1v3` in `prior_state` vs desired `B1` in `planned_values`, so a negative `diffTotalMonthlyCost` is expected). Record: exit codes; the presence and types of the D8 fields; the placement of free resources in `summary`; that `diffTotalMonthlyCost` = `totalMonthlyCost` − `pastTotalMonthlyCost` with the D3 sign; a non-zero price for (b); and the raw key set. Any mismatch with D2/D3/D8 stops the task for a plan change.
      - **Live-check environment (amended 2026-10-04)**: the D7 controls including `CHECKPOINT_DISABLE=1`; synthetic `INFRACOST_VCS_*` values for provider, repository URL, branch, commit SHA, author name, author email and message, **plus a synthetic `INFRACOST_VCS_COMMIT_TIMESTAMP`** (Unix epoch seconds, non-zero, e.g. `946684800`; v0.10.46 ignores zero/unparsable values and falls back to the real git time). Pass requires: version `Infracost v0.10.46`; both exit codes 0; no `.artifacts/task-10.1-live-check/home/.terraform.d`; no `credentials.yml`; the key-leak scan result present in the console log (one invocation only, so the log is not overwritten).
      - **Run 1 (2026-10-04, 12:54 IST) — valid findings preserved, run not passed**. Started in a Terminal-panel tab with the key typed by the user at a silent prompt (Claude never saw it). Evidence preserved as diagnostic evidence in `.artifacts/task-10.1-live-check-run1/` (moved there unchanged, 11 files, before run 2):
        - `version.txt` `Infracost v0.10.46` (binary from the checksum-verified darwin-arm64 tarball); `exit_codes.txt` `in_sync exit=0`, `service_plan_sku_drift exit=0`; stderr logs show plan-JSON autodetection and `Output saved`; stdout empty; no ANSI codes; `.state.json` `latestReleaseCheckedAt` empty (update check skipped); no `runId`/`shareUrl`/`cloudUrl`; no `credentials.yml`; no file matches the Infracost key pattern.
        - **D3 sign (synthetic fixture)**: `pastTotalMonthlyCost` **119.72** (P1v3, 0.164 × 730 h) > `totalMonthlyCost` **13.14** (B1, 0.018 × 730 h); `diffTotalMonthlyCost` **−106.58** = 13.14 − 119.72; drift cost = **+106.58**. Diff component `Instance usage (P1v3 → B1)`, `priceNotFound: false`.
        - **In-sync**: all totals `0`; `resources[]` empty; free resource counted only in `summary.totalNoPriceResources` (1) and `summary.noPriceResourceCounts` (`azurerm_resource_group: 1`). The CI proof's "5 free resources" therefore means `totalNoPriceResources: 5` with empty `resources[]`.
        - **Schema facts (v0.10.46)**: root and breakdown usage-cost fields (`totalMonthlyUsageCost`, `pastTotalMonthlyUsageCost`, `diffTotalMonthlyUsageCost`; resource `monthlyUsageCost` in `diff`) present as `"0"`; each project also has a `summary` duplicating the root one; every money/price/quantity value is a **decimal string** (e.g. `"119.72"`); `metadata` carried the synthetic VCS values, but `vcsCommitTimestamp` was the real HEAD commit time (no override set) and `projects[].metadata.path` an absolute local path, both dropped by D8.
        - **Not passed**: (a) Terraform Checkpoint request observed (`home/.terraform.d/checkpoint_cache`, 12:54:16) → D7 amendment above; (b) the locked key-leak scan line was lost because a second invocation overwrote the console log (it stopped at the existing-directory guard); (c) no synthetic commit timestamp. A re-run with the amended environment is required.
        - The other approved D8 schema corrections (usage-cost fields retained, per-project `summary` dropped, money/price/quantity values as decimal strings never parsed as floats) were recorded in D8 on 2026-10-04 (user decision, before the re-run).
      - **Run 2 (2026-10-04, 13:49 IST) — D9 step 1 PASSED.** Amended script (`CHECKPOINT_DISABLE=1`, synthetic commit timestamp, egress and key-scan results also saved to files), one invocation, started by the user in a Terminal-panel tab with the key typed at a silent prompt (Claude never saw it); console log ends `LIVE-CHECK-DONE rc=0`. Evidence in `.artifacts/task-10.1-live-check/` (12 files):
        - **Binary and runs**: darwin-arm64 tarball `shasum -c` OK; `version.txt` `Infracost v0.10.46`; `exit_codes.txt` `in_sync exit=0`, `service_plan_sku_drift exit=0`; stderr logs show plan-JSON autodetection and `Output saved`; stdout empty.
        - **D7 controls active** (`out/controls.txt`, captured from the running environment): `CHECKPOINT_DISABLE=1`, `INFRACOST_SKIP_UPDATE_CHECK=true`, `INFRACOST_ENABLE_CLOUD=false`, `INFRACOST_DISABLE_ENVFILE=true`, `INFRACOST_NO_COLOR=true`, isolated `HOME`; key recorded only as set. Corroborated: `.state.json` `latestReleaseCheckedAt` empty (no update check), no `runId`/`shareUrl`/`cloudUrl`, no ANSI codes in any file.
        - **No unexpected egress**: `out/egress_check.txt` `EGRESS CHECK: PASS - no $HOME/.terraform.d`; no `.terraform.d` anywhere under the evidence. Only the accepted D7 egress (pricing queries, usage telemetry) remains.
        - **Key handling**: `out/key_scan.txt` and the console: `No credentials.yml written.` and `Key-leak scan: no file under …/task-10.1-live-check contains the API key.` (exact-value scan in the user's shell); independently, no file matches the Infracost key pattern.
        - **Synthetic VCS metadata** in both outputs: branch `synthetic-branch`, SHA `0000…0000`, author `synthetic-author` / `synthetic@example.invalid`, message `synthetic-message`, repository `https://example.invalid/synthetic/repo`, provider `github`, **`vcsCommitTimestamp` `2000-01-01T00:00:00Z`**; no real name, email, account or commit data in any file (absolute local fixture paths remain in `projects[].metadata.path` and stderr logs; D8 drops them).
        - **In-sync**: all totals and usage totals `"0"`; `resources[]` empty in all three breakdowns; `summary.totalNoPriceResources` 1, `noPriceResourceCounts` `{"azurerm_resource_group": 1}`.
        - **D3 sign (synthetic fixture)**: `pastTotalMonthlyCost` **`"119.72"`** (P1v3, price `"0.164"`), `totalMonthlyCost` **`"13.14"`** (B1, price `"0.018"`), `diffTotalMonthlyCost` **`"-106.58"`** (= 13.14 − 119.72, checked with decimal arithmetic); drift cost = **+106.58**; every component `priceNotFound: false`; all values decimal strings; per-project `summary` present (dropped by D8).
        - Results identical to run 1 for pricing, sign and schema; the run-1 Checkpoint finding is resolved by the D7 amendment.
    - **Unit and workflow tests** (no live Infracost or network; the test network guard stays):
      - script tests with a fake `infracost` on `PATH`: exit codes, controls, the D6 fail-closed checks, a missing key, the version check;
      - sanitiser tests on the raw sample (allowlist, VCS/author/path/tags removed, fail-closed cases, `--check`);
      - workflow-structure tests: pin, `sha256sum -c`, step order and conditions, secret only in the cost step, D7 environment, never `upload`/`comment`, the `cost` job's permissions, `needs` and `if`, artifact name and retention, drift outputs, `issues`/`report` unchanged;
      - mutation checks on the gate and sanitiser;
      - `test_github_automation.py`: the job-list assertion includes `cost`, and the `permissions:` block count changes 2 → 3 (the `cost` job's own `contents: read`; approved by the user 2026-10-04); nothing else in it changes.
    - **Real CI proof (approval-gated)**: the user creates the secret → push to `main` → manual `drift-detection` dispatch (read-only Azure plan). Expect plan-and-analyze, issues, report and cost all **success**; `drift_detected` and the drift artifact as before; `infracost-report-<run_id>` downloaded to `.artifacts/` with SHA-256 equal to the GitHub digest, `cost_run.json` bound to the run attempt and drift report hash, **`totalMonthlyCost` 0 with 5 free resources**, no VCS/author/path/tag data; the triggered `ai-analysis` run still succeeds. **Negative proof**: the cost-failure path (`cost_status=failed` → `cost` job red, run red, drift outputs and `report` VALID) is proven by tests, not by breaking the real secret, unless the user approves a one-off dispatch with the secret temporarily removed.
- **Files/Areas**:
  - new `scripts/infracost_analysis.sh`: install check, D6 de-privilege checks, D7 environment, D2 invocation, sanitiser call, `cost_status`. Exit codes: `0` sanitised artifact written, `1` cost failure, `64` usage/unusable output directory.
  - new `scripts/sanitize_infracost.py` (**approved by the user 2026-10-04**): stdlib-only D8 allowlist projection, `cost_run.json`, `--check` mode.
  - `.github/workflows/drift-detection.yml`: cost steps at the end of `plan-and-analyze`, new `cost_status`/`cost_failure` outputs, new `cost` job, header comment.
  - new `tests/test_infracost.py`; new `tests/fixtures/infracost/` (**approved by the user 2026-10-04**: synthetic priced plan with `prior_state` + `planned_values` and its generator; a raw Infracost sample from D9 step 1 with synthetic VCS values injected, never real author data).
  - `tests/test_github_automation.py`: the job-list and `permissions:`-count assertions only (approved 2026-10-04).
  - `README.md`; `docs/drift-detection-spec.md` §8.3 ("Cost publication"); `.gitignore` (`infracost*.json` outside fixtures, `cost_run.json`).
  - **Unchanged**: `scripts/generate_plan_json.sh`, `src/drift_engine/`, `src/ai_engine/`, `scripts/github_automation.py`, `ai-analysis.yml`, `security-scan.yml`, `terraform-auth-test.yml`, `terraform/`, `schemas/`, `ci/ai-constraints.txt`.
- **Acceptance Criteria**:
  - [x] **Pin (D1)** *(CI run #21; the `sha256sum -c` line is inferred, see Step 5 evidence)*: v0.10.46 Linux tarball installed only after `sha256sum -c` against the committed hash; version asserted; no action, image, install script or `preview`.
  - [x] **Mode (D2)** *(CI run #21)*: Infracost evaluates the same run's `plan.json` with the exact D2 command, producing a machine-readable `infracost.json` (sanitised).
  - [x] **Sign (D3)** recorded in `cost_run.json` and the README; verified in D9 step 1. *(`cost_run.json` in CI run #21; README "Cost Estimate" section and spec §8.3; D9 step 1: 119.72 → 13.14, diff −106.58.)*
  - [x] **No thresholds (D4)** *(no cost-value gate exists; CI run #21)*.
  - [x] **Isolation (D5)** *(failure path observed in CI run #20, success path in run #21)*: a cost failure makes the `cost` job and the run red; `drift_detected`, `drift_status`, the drift report and artifact, issues and the `report` verdict are identical to a run without Phase 10; no cost step runs for an invalid/`unknown` detection.
  - [x] **Secret and privilege (D6)** *(fail-closed in run #20; OIDC re-exec effective in run #21)*: `INFRACOST_API_KEY` only in the cost step; Azure logged out and OIDC request variables empty before Infracost, fail-closed otherwise; isolated `HOME` and working directory.
  - [x] **Egress (D7)** *(CI run #21: no `unexpected_egress` with `setup-terraform`'s `terraform` on `PATH`)*: the five controls set (incl. `CHECKPOINT_DISABLE=1`); forbidden variables and commands absent; `$HOME/.terraform.d` present after the run → `cost_failure=unexpected_egress`.
  - [x] **Artifact (D8)** *(CI run #21, artifact verified locally)*: `infracost-report-<run_id>` with exactly the two files, 30 days, allowlist only, bound to the run attempt and drift report hash; no VCS, author, path, tag, URL or identity data; any `priceNotFound: true` → `cost_failure=price_not_found`.
  - [x] **Documentation**: README section, spec §8.3, accepted egress/telemetry and exposure profile stated. *(README "💰 Cost Estimate (Task 10.1)", status, structure, security principles, roadmap and limitations; spec §8.3 "Cost publication"; `.gitignore`.)*
- **Validation**:
  - [x] D9 step 1 recorded **before** implementation (PASSED on run 2, 2026-10-04; run 1 kept as diagnostic evidence).
  - [x] Unit, workflow-structure and mutation tests (D9); full suite green; the `drift_engine` coverage gate held (2026-10-04: 81 new tests, full suite 1262 passed, coverage 96.05%).
  - [x] Real CI proof (D9), user-approved, artifacts in `.artifacts/` (run #21, `.artifacts/task-10.1-ci-proof/`).
- **Implementation Notes**:
  - The real dev estimate is **$0.00/month** (all five resource types are free in Infracost); non-zero pricing is shown only with the synthetic fixture and never presented as dev metrics.
  - Scheduled runs make one Infracost call per day plus telemetry; free-tier limits are not documented and are watched in CI.
  - The Phase 9 rule "existing workflows unchanged" was Phase 9-scoped; this task deliberately changes `drift-detection.yml` under D5.
  - Checkpoint behaviour of the existing Terraform steps (outside the cost step) is out of scope for Task 10.1 (D7 amendment); candidate for Phase 12 hardening.
- **Completion Notes**:
  - **Completed 2026-10-04**: all six steps done; every acceptance criterion and validation item met (the three log-only items of the CI proof are recorded as inferred, see Step 5). Commits: `0de9bed` (design lock + D9 live check + fixture), `15b0910` (implementation steps 1–4), `b8aa799` (D6 amendment), plus the Step 5/6 checkpoint.
  - **Implementation record**: implementation steps 1–4 of 6 committed in `15b0910` (pushed; security scan run `37194981184` green); Step 5 CI proof attempt 1 (run #20) stopped on `oidc_token_present` → D6 amendment committed in `b8aa799` (pushed; security scan run `37195940044` green: TFLint, Trivy, TruffleHog success); **Step 5 real CI proof PASSED on run #21** (evidence below). Steps 1–5 done; Step 6 (documentation) remains.
    - `scripts/infracost_analysis.sh` (I2–I5, D1 version check, D2, D6, D7 incl. `CHECKPOINT_DISABLE=1` and the `unexpected_egress` override): `bash -n` and ShellCheck 0.10.0 clean; scratchpad matrix with fake `infracost`/`az` 29/29 (every reason code, exit 0/1/64, exact `$GITHUB_OUTPUT`, D2 argv, allowlisted Infracost environment, sentinel key never printed or written).
    - `scripts/sanitize_infracost.py` (I1, D8; stdlib only): write mode drops unknown keys, check mode rejects them; decimal strings only (float, null or non-decimal → exit 1); `priceNotFound: true` → exit 2; USD only; binding requires `--run-id`/`--environment` to equal the drift report's `run.run_id`/`run.environment`; `drift_report_sha256` equals the Task 9A.1 function (verified by import); fail-closed string re-check (email-like, URL, GUID, absolute path); both files written together or none; usage → 64.
    - End-to-end `infracost_analysis.sh` → **real** sanitiser (no stand-in), driven by the real D9 run-2 raw outputs: 35/35 (both real outputs succeed with totals 119.72 / 13.14 / −106.58 and in-sync 0 preserved as decimal strings, all `vcs*`/paths/tags/project metadata dropped; 13 failure variants; `--check` passes on both outputs under Python 3.9 and 3.14 and fails on 9 tampered copies; 6 usage cases). Live Infracost + real sanitiser together remain for the CI proof.
    - `.github/workflows/drift-detection.yml` (Step 3): `Infracost Cost Estimate` step (D1 pinned install + `sha256sum -c` inside the step → `install_failed`; D6 env: only `INFRACOST_API_KEY`, both OIDC variables blanked, `az logout`/`az account clear`; always exits 0) and `Upload Infracost Report` (`continue-on-error: true`, the approved exception) after `Upload Drift Report`; job outputs `cost_status`, `cost_failure`, `cost_upload_outcome`; new `cost` job (`needs: [preflight, plan-and-analyze]`, `!cancelled()` + literal `true`/`false`, `contents: read` only, fails unless `cost_status == succeeded` and `cost_upload_outcome == success`, same-run downloads, `sanitize_infracost.py --check`, totals-only summary with `Decimal`). Validation: YAML parses; actionlint 1.7.7 with ShellCheck 0.10.0 clean; `preflight`, `issues`, `report`, triggers, permissions, concurrency, env and all existing `plan-and-analyze` steps/outputs identical to `HEAD`; the only secret reference added is `INFRACOST_API_KEY` (cost step only) and the only `continue-on-error` is the cost upload; extracted `run:` blocks executed with shims (fake `curl` tarball, `shasum` for `sha256sum`, logged-out `az`) through the real scripts and sanitiser: 17/17 (success outputs and 2-file report, pinned URL, `az` calls, key never printed, checksum mismatch / download failure → `install_failed` with exit 0, missing key → `missing_api_key` with exit 0, `cost` job gate for failed / not-run / upload-failure, `--check` pass/fail, totals-only summary).
    - Expected until the tests step: `tests/test_github_automation.py` fails exactly two assertions (job list now includes `cost`; `permissions:` block count 3 instead of 2, because D5 requires the `cost` job's own `contents: read`). The rest of the suite passes (1179 passed). Both assertion updates were approved by the user on 2026-10-04 (Step 4).
    - **Step 4 — tests** (no live Infracost, no key, no network; always the real sanitiser):
      - New `tests/fixtures/infracost/raw/{service_plan_sku_drift,in_sync}.raw.json`: the unmodified D9 run-2 Infracost v0.10.46 outputs (synthetic VCS values injected at run time), except the one real local absolute path in `projects[].metadata.path`, replaced by the synthetic absolute `/home/runner/work/_temp/drift/plan.json`; scanned clean (no real identity, key pattern, GUID or local path).
      - New `tests/test_infracost.py`, 81 tests: sanitiser on both real samples (allowlist only, values copied as decimal strings with no JSON floats, D3 values 119.72 / 13.14 / −106.58, in-sync 0, VCS/paths/tags/project metadata dropped, `cost_run.json` hash equal to Task 9A.1 `drift_report_sha256`); 14 write-mode failures (exit 1, or 2 for `price_not_found`, output left empty); binding mismatches; unknown keys dropped in write mode and rejected by `--check`; 8 `--check` tamper cases; CLI usage exits 64; the script with a fake `infracost` on `PATH` for every I2 reason code (23 cases incl. egress overriding a version mismatch, `$GITHUB_OUTPUT` exact, key never printed or written, D2 argv, allowlisted Infracost environment with the five D7 controls, `COST_DIR` inside the repository and a missing sanitiser on a copied tree); workflow structure (step order and `if`s, pin and `sha256sum -c` before unpacking, secret confined to the cost step, the only `continue-on-error`, artifact, `cost` job permissions/needs/steps, `issues`/`report` untouched); the extracted `run:` blocks executed (success, three `install_failed` variants with exit 0, script failure with exit 0, `cost` job gate for 5 states, `--check`, totals-only summary); safeguard mutants on in-process/temporary copies, the repository never changed: 10 sanitiser and 10 script mutants all caught, both no-op controls not caught. Not listed as single mutants (equivalent, defence in depth): the check-mode strict unknown-key check and the exact-projection comparison each reject an unknown key alone.
      - `tests/test_github_automation.py`: only the two approved assertions (job list incl. `cost`; `permissions:` count 3).
      - Results: `tests/test_infracost.py` 81 passed; related workflow/scanner/AI-CLI tests 227 passed; full suite **1262 passed**, 696 skipped (the opt-in `ai`/`azure` extras), 0 failed; `drift_engine` coverage gate held at 96.05% (≥ 85%); `git diff --check` clean.
    - **Step 5 — real CI proof (user-approved, 2026-10-04)**: the user created the `INFRACOST_API_KEY` secret and dispatched the runs; Claude pushed `15b0910` and `b8aa799` after the Step 0 pre-push checks (full suite, actionlint/ShellCheck, TruffleHog 3.97.9 full-history scan of the exact tree: no findings) and verified everything through the public Actions API and the downloaded artifacts.
      - **Attempt 1 — run #20** (`37195216717`, `workflow_dispatch`, `main`, `15b0910`): stopped on the D6 fail-closed check `oidc_token_present` (D6 amendment above). Real evidence for the D5 failure path: cost step exit 0, `Upload Infracost Report` skipped, `cost` job red, while `preflight`, `plan-and-analyze`, `issues`, `report` and AI analysis run `37195280852` succeeded.
      - **Run #21 — PASSED** (id `37196101446`, `workflow_dispatch`, `main`, commit `b8aa79921fb8`, attempt 1, 10:40:07Z → 10:41:24Z, conclusion success). <https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/37196101446>
      - **Directly verified (public Actions API)**: jobs `preflight`, `plan-and-analyze` (all steps incl. `Infracost Cost Estimate` and `Upload Infracost Report`), `cost` (`Require Cost Success`, both downloads, `Verify Infracost Report` = the real sanitiser `--check` on the runner, `Cost Summary`), `issues` and `report` all **success**; triggered AI analysis run `37196175120` (same commit) **success**; only the standard Node.js 20 / `ubuntu-latest` annotations, no errors. D6/D7 on the real runner: no `oidc_token_present`, `azure_session_present` or `unexpected_egress` (any of them fails the `cost` job), so the OIDC re-exec is effective and `CHECKPOINT_DISABLE=1` held with `setup-terraform`'s `terraform` on `PATH`.
      - **Artifacts (directly verified; downloaded by the user to `.artifacts/task-10.1-ci-proof/`, gitignored)**: `infracost-report-37196101446.zip` SHA-256 `33758dda12bddcd908725f8e02a94e6aa5f579e3e5643a80c437f12842df7759` = GitHub digest, 940 B, expires 2026-11-03T10:41:05Z (30 days), exactly `infracost.json` + `cost_run.json`; `drift-report-37196101446.zip` SHA-256 `9a1f2f30662ca3bbabcc5889347e571a486f12f23e2c708067771d37eb1d7803` = GitHub digest, 1490 B, expires 2026-11-03T10:41:01Z, exactly `drift_report.json` + `detection_run.json` (the drift artifact is unchanged in shape).
      - **Sanitiser and binding (directly verified)**: `scripts/sanitize_infracost.py --check` on the downloaded files with run id `github-37196101446-1` and the downloaded drift report: exit 0 (and correctly rejects attempt `-2`). `cost_run.json`: `run_id` `github-37196101446-1` = the drift report's `run.run_id`; `environment` `dev` = `run.environment`; `drift_report_sha256` `8e099db530ec1ab070d1821ce06f0f99ecbc4aab4cc78d254fa9956e20b9763f` = the Task 9A.1 canonical hash of the downloaded `drift_report.json`; `infracost_version` `v0.10.46`, `mode` `plan_json_breakdown`, `pricing` `list_prices_usd_no_usage_file`, sign convention present, `generated_at` `2026-10-04T10:41:05Z`.
      - **Values (directly verified)**: USD; every total, past total, diff and usage total `"0"` (decimal strings, no JSON floats); `resources[]` empty in `breakdown`, `pastBreakdown` and `diff`; `summary` `totalDetectedResources` 5, `totalNoPriceResources` 5, supported/unsupported 0, `noPriceResourceCounts` exactly the five resource types of the drift report (resource group, virtual network, subnet, NSG, subnet–NSG association: the expected all-free $0 dev result). D8 allowlist only: no `metadata`, `vcs*`, `path`, tags, `runId`/`shareUrl`/`cloudUrl`, emails, URLs, GUIDs, absolute paths, real identity or key-shaped strings in either file.
      - **Drift result (directly verified)**: downloaded `drift_report.json` `outcome: succeeded`, `has_drift: false` (boolean), `{"in_sync": 5}`, 5 resources, run `github-37196101446-1`, environment `dev`; manifest plan exit 0, Terraform 1.14.7.
      - **Inferred, not directly observed** (the run's log archive was not available through the GitHub UI; no log line is claimed as seen):
        - `cost_status=succeeded` / `cost_failure=none`: inferred from the successful `Upload Infracost Report` (it runs only when `cost_status == 'succeeded'`) and the successful `Require Cost Success` (fails unless `cost_status == succeeded` and the upload succeeded).
        - `sha256sum -c` OK: inferred from the successful installation path (a checksum failure yields `install_failed`) and the subsequent exact `Infracost v0.10.46` execution (otherwise `version_mismatch`); the literal log line was not observed.
        - `drift_detected=false`: supported directly by the downloaded `drift_report.json` (`has_drift: false`) and the successful `report` job; the exact workflow output line was not available.
    - **Step 6 — documentation (2026-10-04)**: README: new section "💰 Cost Estimate (Task 10.1)" (workflow placement, cost step and `cost` job, pinned v0.10.46 + SHA-256, `INFRACOST_API_KEY`, reason codes and failure semantics, D7 controls and accepted egress incl. the start-up `terraform -version`, drift-cost sign rule with the verified example, artifact allowlist/binding/decimal strings/exposure, current dev $0, local `--check`), plus current status, "What works today", planned items, repository structure, security principles, roadmap and known limitations. `docs/drift-detection-spec.md` §8.3: new "Cost publication (Task 10.1)" (eligibility, raw output stays on the runner, allowlist, binding and canonical hash, sign rule, string re-check, `cost` job `--check`, failure isolation, accepted egress). `.gitignore`: `infracost*.json` and `cost_run.json` ignored outside `tests/fixtures/` (verified with `git check-ignore`; no tracked file affected). No code, workflow or test change.
  - **Limitations and Phase 12 hardening candidates**:
    - TruffleHog 3.97.9 has **no Infracost detector** (a realistic fake `ico-` key was not flagged; a fake GitHub token was): the Task 9.3 secret scan would not catch a leaked Infracost key. Protection relies on D6 (never an argument, printed or written), the key-leak checks in tests and the live check, and GitHub secret masking. Candidate: a custom TruffleHog detector or equivalent check.
    - Residual OIDC exposure: `plan-and-analyze` keeps job-level `id-token: write` (Azure login), so the runner holds the request credential for the job; the cost step removes it only from its own process tree (D6 amendment).
    - Infracost v0.10.46 usage telemetry cannot be disabled (accepted egress); Infracost CLI v2 is a separate product; the classic v0.10 line's maintenance horizon is unknown.
    - D8 treats `null` as a failure, so a usage-based resource without usage data would fail sanitisation (`sanitize_failed`); the current dev resources are all free.
    - Non-zero CI pricing has not been observed (dev is $0); the sign rule and non-zero pricing were verified with the live D9 check on the synthetic fixture.
    - The `execfail` fallback of the OIDC re-exec (only reachable if `env` or `bash` were missing) is not exercised by a test.
    - The existing Terraform steps' own Checkpoint behaviour, the Node.js 20 action deprecation and the `ubuntu-latest` migration notices remain Phase 12 items.

#### Task 10.2 — Terraform Plan Cost Delta Calculation
- **Status**: 🟢 COMPLETED
- **Started**: 2026-10-11
- **Completed**: 2026-10-11
- **Objective**: Extract cost differences (`monthly_cost_delta`) between current state and drifted state.
- **Dependencies**: Task 10.1; Phase 9B (🟢 2026-10-11, Task 9B.6)
- **Files/Areas**: `src/drift_engine/cost.py`; plus (approved design) `tests/test_cost.py`, `README.md`, `docs/drift-detection-spec.md` §8.3 ("Cost delta").
  - **Unchanged**: workflows, `scripts/sanitize_infracost.py`, `src/ai_engine/` and the AI report schema (Task 10.3), `schemas/`, `ci/*-constraints.txt`, `terraform/`, the Task 10.1 fixtures, dependencies.
- **Design (locked 2026-10-11, user-approved after two design reviews)**:
  - **Interface**: library only, `drift_engine.cost.cost_delta(public_report, infracost, cost_run)` returning the `cost_delta_version` 1 document (the Task 10.2 output contract, a strict Pydantic model). No CLI command, workflow step or new dependency; no I/O, clock, network or Azure. Inputs and the drift result are never changed. It loads only `investigation_public`, `models` and `report_public` from `drift_engine`, so `ai_engine` may import it (G14).
  - **Binding (fail closed, `CostDeltaError` codes)**: `not_public_report`, `invalid_structure` (public report schema or a D8-required key), `binding_mismatch` (run id, environment, canonical hash), `unsupported_source` (Infracost version, mode, pricing, sign-convention text), `currency_not_usd`, `invalid_decimal`. Messages name a location, never a value.
  - **Numbers**: decimal strings only, parsed with `Decimal` (at most 40 characters) and computed in an exact context that traps rounding. A float, int, bool, null, exponent or malformed amount fails; an absent optional amount stays `null`. A zero is never invented.
  - **Sign (D3 unchanged)**: `monthly_cost_delta` = −(Infracost diff `monthlyCost`) = list-price estimate of the refreshed current configuration (`prior_state`) − list-price estimate of the declared configuration (`planned_values`).
  - **Scope of the amounts (honesty fix, user-approved 2026-10-11)**: every amount is an Infracost list-price estimate for Terraform-managed resources only, never actual Azure billing. Resources outside Terraform are invisible (spec §6.3) and usage-based charges are not priced. `past_monthly_cost` is the list-price estimate of the refreshed current configuration, not actual Azure cost. Every document carries the fixed `limitations` codes `list_prices_usd_no_usage_file`, `exact_address_match`, `absent_from_diff_is_not_zero`, `subresources_not_attributed`, `mixed_not_split`, `terraform_managed_resources_only` and `estimate_not_billing` (the contract requires exactly these seven, each once: a missing, repeated or unknown code fails; the generated order is fixed, but the contract does not impose an order), and its `sign_convention` text states the same. No calculation or attribution changed.
  - **Contract versioning (user-approved 2026-10-11)**: any change to the v1 output contract that breaks compatibility requires a `cost_delta_version` bump. That includes changing the `sign_convention` or `infracost_plan_delta` label text, the limitation codes, the attribution, attribution-reason, cost-status, group or reason values, the pinned `source` values, or adding, removing or renaming a field. A compatible internal refactoring that leaves every published document byte-identical does not by itself require a bump.
  - **D3 label clarification (user decision 2026-10-11)**: the run-level −`diffTotalMonthlyCost` mixes drift and pending configuration changes, so it is published as `infracost_plan_delta`, labelled "drift and pending configuration changes combined; not a drift cost". Only `confirmed_drift` is drift cost.
  - **Attribution** (from the public report's `classification`, `drift_actions` and `ambiguous` only): `drift` (external drift, external deletion or converged drift, with `drift_actions`, not ambiguous); `configuration` (config change, resource added or removed, without `drift_actions`); `mixed` (`drift_and_config_change`, never split); `ambiguous` (`undetermined_classification`, `classifier_ambiguous`, `inconsistent_drift_evidence`, `duplicate_cost_line`).
  - **Cost status** (exact-address match): `cost_line`, `duplicate_cost_lines`, `no_cost_change_listed`, `no_price_resource_type`, `unsupported_resource_type`, `not_in_cost_output`. Only a diff line gives a delta.
  - **Comparability**: `past_monthly_cost` (`pastBreakdown`, the list-price estimate of the refreshed `prior_state`) and `desired_monthly_cost` (`breakdown`, the list-price estimate of `planned_values`) come from the same Infracost run and pricing call (Task 10.1 pre-lock verification). They are shown only for the same name, once, in the same project, and are never subtracted.
  - **Unmatched lines**: a diff line with no report address (`no_report_address`) or an in-sync address (`in_sync_in_report`) is listed with its amount in `unmatched`; duplicate-name lines are listed in `ambiguous`. Nothing is dropped or attributed to drift.
  - **Subtotals**: `confirmed_drift`, `configuration`, `mixed`, `ambiguous`, `unmatched`, each with `with_cost`, `without_cost` and `complete`; `null` when no member has an amount.
  - **Reconciliation (reported, not enforced)**: Infracost v0.10.46 computes `diff.totalMonthlyCost` as the sum of the non-skipped, non-nil line amounts and the root total as the sum of the projects (source read 2026-10-11: `internal/output/output.go` `calculateTotalCosts`, `internal/schema/diff.go` `CalculateDiff`, which lists only resources whose cost components or subresources changed). Neither the D8 contract nor a documented schema guarantees this, so per project and at the root (vs the projects and vs `totalMonthlyCost − pastTotalMonthlyCost`) the residual is reported and published as `unreconciled`. The groups plus `unreconciled` always equal `infracost_plan_delta`.
  - **Display**: `+$106.58/month` / `-$13.14/month` / `$0.00/month`, half-up to cents for display only; the exact decimal is always kept.
- **Acceptance Criteria**:
  - [x] Parses `infracost.json` and correlates cost changes with specific resource drifts. *(`cost_delta`: binding, per-resource attribution and cost status, unmatched lines, subtotals and reconciliation; verified on both real samples, the in-memory variants and the real cycle-2 artifacts.)*
  - [x] Formats currency delta outputs. *(`format_monthly_usd`, the `display` fields.)*
- **Validation**:
  - [x] Test parsing against sample Infracost output. *(`tests/test_cost.py`, 74 tests, on the real Infracost v0.10.46 samples sanitised by the real `scripts/sanitize_infracost.py` and checked with `--check`.)*
- **Implementation Notes**:
  - Accurate cost metrics provided to AI engine. *(Provided as a library for Task 10.3; 10.2 does not change `ai_engine`, by user decision.)*
  - Input is the sanitised `infracost.json` + `cost_run.json` from `infracost-report-<run_id>` (Task 10.1 D8), correlated to the drift report by `run_id` and `drift_report_sha256` (the **public** drift report's canonical hash; amended 2026-10-05, Task 9B.4A); the D3 sign convention is used (label clarified above).
- **Completion Notes**:
  - **Completed 2026-10-11.** New `src/drift_engine/cost.py` and `tests/test_cost.py`; README ("Cost delta (Task 10.2)", module table, structure, status, roadmap, limitations) and spec §8.3 updated.
  - **Tests**:
    - `tests/test_cost.py`: 74 passed, 100% line and branch coverage of `cost.py`. Covers the priced sample (`azurerm_service_plan.this` `external_drift`, delta `106.58`, past `119.72`, desired `13.14`, `+$106.58/month`, reconciled); the in-sync sample (null, never zero); every attribution and cost-status rule; non-drift groups never reaching `confirmed_drift`; absent optional amounts; type-count reasons; negative zero; unmatched and in-sync lines; exact module/`for_each` address matching (no loose matching); duplicate names across and within projects; multiple projects; residuals; a project without `diff`; every binding and decimal failure; formatting; inputs unchanged and deterministic output; the import boundary; the limitation codes and the estimate-not-billing wording in every document, and the contract requiring exactly the seven codes (missing, repeated and unknown codes rejected; order not imposed).
    - Full suite (`pytest --cov=src/drift_engine tests/`, Python 3.13.12, pinned venv): **2439 passed**, 3960 subtests, 0 failed, coverage 99.49% (gate 85%). `unittest` discovery 963 OK.
    - Safeguard mutation check (scratchpad only, not committed; throwaway copies): 14 of 14 mutants caught (sign not negated, mixed counted as drift, drift without `drift_actions`, absent amount as zero, residual hidden, duplicates ignored, unmatched lines dropped, hash binding skipped, float accepted, completeness always true, past/desired swapped, half-even display rounding, all amounts counted as drift, the exact-limitations check disabled).
    - A formatting test found and fixed a rounding defect during implementation: `abs()` on a large `Decimal` rounded to 28 digits; `copy_abs()` is used instead.
  - **Real data (read-only, local cycle-2 artifacts)**: R2 and R3 bind to their public drift reports; the tag drift on `aitdd-dev-main-rg` is `drift`, `no_price_resource_type`, delta `null`; plan delta `0`, reconciled, no unmatched lines. R4 (in sync) has no resources.
  - **Limitations**: library only, not called by a workflow; the priced path is verified only with the synthetic fixture (dev is all free); Infracost's `name` format for module and `for_each` addresses has not been seen in real output (a differing format is reported as `unmatched`, never as drift); subresources are not attributed separately; `mixed` amounts are never split.

#### Task 10.3 — AI Cost Impact Explanation Engine
- **Status**: 🟢 COMPLETED (real CI verification by run #44 / AI run #27, 2026-10-11)
- **Started**: 2026-10-11
- **Completed**: 2026-10-11
- **Objective**: Pass Infracost cost delta data into LangGraph node `analyze_cost` to generate human-readable financial explanations.
- **Dependencies**: Task 10.2, Task 6.4, Task 9A.1, Task 9B.4 (AI report v2 contract; v3 adds cost, Task 10.3)
- **Files/Areas**: `src/ai_engine/nodes/cost_analysis.py`; plus (approved design) `src/ai_engine/cli.py`, `graph.py`, `evidence.py`, `nodes/analyze_drift.py`, `nodes/report_generator.py`, `verify.py`, `.github/workflows/ai-analysis.yml`, `tests/test_ai_cost_impact.py` (new), the AI tests pinning report v2, `tests/test_investigation_public.py` (G14 allowlist), `tests/mutation/mutants.json`, `README.md`, `docs/drift-detection-spec.md`.
  - **Unchanged**: `src/drift_engine/` (including `cost.py`), `drift-detection.yml`, the sanitiser, `schemas/`, `ci/*-constraints.txt` (no new dependency), `terraform/`, recommendation policy v1.
- **Design (locked 2026-10-11; user decisions 1-5 and the three follow-up decisions)**:
  - **Report v3** (decision 1): `report_version` / `versions.report` "3". It differs from v2 only in cost: `versions.cost_delta`, `provenance.cost_input_sha256`, the `cost` block, `resources[].cost`, the cost findings' `estimate_direction` / `estimate` / `monetary_impact` / `pricing_source`, `llm.evidence_sent[].estimate_direction`, and the status-dependent cost limitations. The `ai-analysis.yml` summary reads only unchanged fields (plus a status-only `Cost` row), so it stays compatible. Reading v2 artifacts is left to Task 13.1.
  - **Single source of amounts** (decision 5): `ai-analysis --cost DIR` reads exactly `infracost.json` and `cost_run.json` (strict JSON, 10 MiB cap each) and calls only `drift_engine.cost.cost_delta`; the full validated `cost_delta` v1 document is embedded in the report.
  - **Statuses** (decision 2): `complete`; `not_available` (`cost_input_not_provided`: no `--cost`, e.g. the cost job failed); `rejected` with a fixed code (the six `cost_delta` codes plus `cost_input_unreadable` / `cost_input_incomplete`). `rejected` still writes the report (exit 0); stderr prints only `cost rejected (<code>)`. Only `complete` carries amounts: the other two have `cost_delta: null`, `monetary_impact: not_determinable_from_evidence`, `pricing_source: null`, `resources[].cost: null`, exactly one amount-free status statement, and the v2 "No pricing data" limitation. A cost input inconsistent with its status, or bound to another drift report, is an internal error (exit 70), never a result.
  - **Hashes**: `provenance.cost_input_sha256` = `{infracost, cost_run}` canonical SHA-256 (Task 10.2 canonicalization: sorted keys, compact separators, UTF-8) of the parsed documents; set once both parsed (also when rejected by a `cost_delta` code), `null` otherwise.
  - **Deterministic statements** (decision 3): `derive_cost_impact` (before the LLM) produces fixed `cost.*.v1` statements from `cost_delta` fields only: status, per-resource estimate or "not determinable" with its reason, one per non-empty subtotal (only `confirmed_drift` is drift cost) or `cost.no_drift_cost.v1`, the plan total labelled "not a drift cost", and a reconciliation statement when Infracost's totals do not reconcile. Per-resource statements live in `resources[].cost.statements`; the Phase 9B narrative is unchanged.
  - **LLM** (follow-up decisions 1-3): the opt-in LLM receives only each cost resource's deterministic `estimate_direction` (increase / decrease / no_change / not_determinable) through the evidence gateway, recorded per cost key in `llm.evidence_sent`, never an amount; the amount guard is unchanged. A cost finding that contradicts it is rejected (`direction_conflicts_with_estimate`, counted, explanation never published). The cost section's free-text summary is withheld when cost is `complete`. In CI there is no LLM.
  - **Verifier**: recomputes `cost_delta` from the same input with drift_engine.cost and requires the embedded document to equal it; checks status, reason, `monetary_impact`, `pricing_source`, hashes, versions and binding; every statement against its fixed template, filled independently; each resource's cost entry; the cost limitations; each finding's estimate, direction and the absence of contradiction; the withheld summary; the direction per cost key in `evidence_sent`; and, unless `complete`, no amount or currency in the deterministic cost output.
  - **Workflow** (decision 4): `ai-analysis.yml` downloads `infracost-report-<run id>` by pattern (missing is no failure), passes `--cost` only when the directory exists, and adds a status-only `Cost` summary row. Permissions (`contents: read`, `actions: read`) and secrets (none) are unchanged. No CI dispatch yet. Under D-4 this adds one `actions/download-artifact` redirect line per AI job (allowed: one per download step).
  - **G14 module boundary addendum (2026-10-11, Task 10.3)**: `ai_engine` may also import `drift_engine.cost` (required by decision 5). It loads only `investigation_public`, `models` and `report_public` (pinned by `tests/test_cost.py`), never a restricted module; the allowlist test is extended accordingly.
- **Acceptance Criteria**:
  - [x] AI output explains exact monthly cost increase/decrease using Infracost numbers. *(Deterministic `cost.*.v1` statements and `resources[].cost` with the exact `cost_delta` amounts, e.g. "+$106.58/month (106.58 USD per month; current configuration 119.72 USD per month, declared configuration 13.14 USD per month); attribution drift; Infracost list-price estimate, not actual Azure billing"; in CI there is no LLM, so the deterministic statements are the explanation, as in Phase 9B.)*
  - [x] AI does not invent or estimate unverified prices. *(The LLM never receives or writes an amount (direction only; amount guard unchanged); a missing price stays "not determinable", never zero; `not_available` / `rejected` publish no amount; the verifier recomputes every amount.)*
- **Validation**:
  - [x] Verify AI cost report matches Infracost JSON numbers. *(`tests/test_ai_cost_impact.py`: the embedded document equals `cost_delta` recomputed from the real sanitised Infracost v0.10.46 samples, every statement is checked against its template, and the verifier recomputes on every run.)*
  - [x] Real CI verification (user decision 2026-10-11): one user-approved drift-detection dispatch whose triggered `ai-analysis.yml` run downloads the cost report, records the cost status in the report and the summary (no amount in the summary) and succeeds. Task 10.3 and Phase 10 stay 🟡 until then. *(Done 2026-10-11 by the Task 10.4 dispatch #44 `38140497702` and its AI run #27 `38140599354`; see Completion Notes, "Real CI verification".)*
- **Implementation Notes**:
  - Strict financial accuracy without LLM pricing hallucinations.
  - Per-resource cost statements are in `resources[].cost.statements`, not in `analysis.narrative` (the Phase 9B narrative and its verifier check are unchanged).
- **Completion Notes**:
  - **Implementation complete 2026-10-11; pending real CI verification** at that point (passed later the same day, see "Real CI verification" below) (design locked with user decisions 1–5 and three follow-up decisions; implementation approved the same day; the user accepted the G14 addendum, `resources[].cost.statements` and no stderr line for `not_available`).
  - **Tests**:
    - `tests/test_ai_cost_impact.py`: 41 passed; `cost_analysis.py` 100% line and branch coverage. Covers exact amounts (complete), null never zero (unpriced), `not_available` and every rejection code with no amount, isolation (drift, investigation and recommendation identical with and without cost), direction-only LLM input, published consistent finding, rejected conflicting findings (`likely_decrease`, `likely_neutral`), kept summary without cost, the amount guard, verifier tampering (amounts, embedded totals, statements, attribution, limitations, hashes, version, direction, estimate, summary, binding), contract guards, determinism, the Markdown cost section, the internal-error paths, the no-drift-cost and reconciliation statements, oversize input and the CLI.
    - Existing AI tests updated only for report v3, the new graph node and state fields, the workflow steps and summary row, and the validated cost finding shape; `tests/test_investigation_public.py` allowlist extended by `drift_engine.cost` (G14 addendum).
    - Full suite (`pytest --cov=src/drift_engine tests/`, Python 3.13.12, pinned venv): **2480 passed**, 3971 subtests, 0 failed, coverage 99.49% (gate 85%); `unittest` discovery 963 OK.
    - AI safeguard mutation corpus (`scripts/run_mutation_checks.py`): 11 new cost mutants added; 202 of 202 caught. Two existing mutants targeted code that this task changed (`new-origin-not-sent`, `g-cost-not-constant`) and were retargeted to the same safeguard in the new code; both are caught.
    - A test exposed a misleading reconciliation wording (a residual of $0.00 described as "differ by"); the `cost.reconciliation.v1` template now states the number of differing checks and missing amounts, then the unattributed amount.
  - **Workflow**: YAML parses; every `run:` block passes `bash -n`; the changed check and summary steps are executed by the workflow tests; permissions and secrets unchanged. actionlint and ShellCheck were not run (not installed; no download without approval).
  - **Real data (local, read-only)**: `ai-analysis --cost` on the cycle-2 R2 artifacts (`.artifacts/task-9B.6-ci-proof/cycle2/primary/`) exits 0 with the verifier passing: cost `complete`, the tag-drifted resource group `no_price_resource_type` with no amount, plan total `0` as Infracost wrote it, investigation `complete` and verdict `sole_capable_operation` unchanged.
  - **Pending (by user decision)**: a real `ai-analysis.yml` run with the cost download needs a separate, user-approved drift-detection dispatch. Dev is all free, so it can only prove the unpriced path. *(Resolved 2026-10-11, below.)*
  - **Real CI verification (2026-10-11; closes the task, user decision 2026-10-11)**: done by the user-approved Task 10.4 dispatch, as its notes anticipated. The code under test was commit `8ef89b6` (report v4 = v3 plus the separate unmanaged section; the Task 10.3 cost fields are unchanged in v4).
    - **Directly verified (public Actions API)**: drift-detection run #44 `38140497702` (`workflow_dispatch`, `main`, `8ef89b6`) succeeded with every job green, including `Cost Estimate (dev)` (`Require Cost Success`, both downloads, `Verify Infracost Report`, `Cost Summary`). The triggered AI analysis run #27 `38140599354` (`workflow_run`, same commit) succeeded, with `Download source cost report`, `Validate and bind the drift report`, `Run AI analysis (no LLM)`, `Summary (counts only)` and `Upload AI analysis report` all green, and the `ai-analysis-report-38140497702` artifact was uploaded. The verifier runs inside `Run AI analysis`, so the cost section passed its recomputation on the runner.
    - **User-confirmed (artifact and summary inspected by the user, 2026-10-11)**: the AI report records the cost status, and the run summary's `Cost` row shows the status only, with no amount.
    - Claude did not download the artifacts in this session (they need authentication), so the cost status value and the report body are not quoted here.
  - **Limitations**: the priced path is fixture-verified only (the real run is the unpriced dev path: every Terraform-managed dev resource type is free); amounts are list-price estimates for Terraform-managed resources, never actual Azure billing; resources outside Terraform and usage-based charges are not covered; a consistent finding's free-text explanation is inference whose wording cannot be proven semantically (its direction field is verified).

#### Task 10.4 — Unmanaged Resource Detection & Cost Estimation
- **Status**: 🟢 COMPLETED (real Azure and CI verification by run #44 / AI run #27, 2026-10-11)
- **Started**: 2026-10-11
- **Completed**: 2026-10-11
- **Objective**: Detect Azure resources that exist in a Terraform-managed resource group but are not managed by the current Terraform state (e.g. a VM created in the Azure Portal inside `aitdd-dev-main-rg`), and estimate their monthly list-price cost, separately from Terraform drift and from the Infracost plan estimate.
- **Dependencies**: Task 10.1 (workflow placement, D5 pattern), Task 10.3 (AI report v3 → v4), Task 9B.4A (public drift report, binding), Task 9B.5 (pinned `[azure]` venv pattern, Reader session in `plan-and-analyze`), Task 2.7 (RBAC: subscription Reader).
- **Files/Areas**: `src/drift_engine/inventory.py`, `unmanaged_public.py`, `unmanaged_cost.py` (new), `src/drift_engine/cli.py` (`inventory`, `unmanaged-cost`, `unmanaged-check`), `src/drift_engine/__init__.py`; `src/ai_engine/nodes/unmanaged_resources.py` (new), `graph.py`, `nodes/report_generator.py` (report v4), `verify.py`, `cli.py` (`--unmanaged`); `scripts/inventory_analysis.sh` (new); `.github/workflows/drift-detection.yml`, `.github/workflows/ai-analysis.yml`; tests `tests/test_inventory.py`, `test_unmanaged_cost.py`, `test_unmanaged_ai.py`, `test_unmanaged_workflow.py`, `unmanaged_fixtures.py`, `tests/fixtures/retail_prices/` (new), and the existing tests pinning report v3, the graph, the workflow structure and the G14 allowlist; `tests/mutation/mutants.json` (one retargeted mutant); `README.md`, `docs/drift-detection-spec.md` (§6.3, §8.3), `docs/architecture.md`.
  - **Unchanged**: drift classification and the drift report contract (`schemas/`), `drift_detected`/G18 for drift, issues, the Infracost steps and sanitiser, `drift_engine.cost`, the investigation, `ci/*-constraints.txt` (no new dependency), `terraform/`, Azure RBAC.
- **Decisions (user-approved 2026-10-11)**:
  1. **Pricing source**: the public Azure Retail Prices API (`prices.azure.com/api/retail/prices`, api-version `2023-01-01-preview`, USD, Consumption list prices). Infracost is not used for unmanaged resources (they are not in the plan). **Phase 10 rule amendment**: "monetary figures come only from Infracost output" now applies to Terraform-plan amounts; unmanaged-resource amounts come only from matched Retail Prices API meters, are labelled as such and are never added to, compared with or subtracted from Infracost amounts.
  2. **CI behaviour**: unmanaged resources (findings) never fail the pipeline (warning); inventory and API failures are explicit: a failed or incomplete inventory, a Retail Prices API failure, or a failed verification/upload fails the new `unmanaged` job. `drift_detected` never changes.
  3. **Public reporting**: resource type, name, estimated cost, pricing assumptions and status are published; full Azure resource IDs (and subscription IDs, tags, IP addresses, other properties) are never published. A name that looks like an identifier (GUID, e-mail or `@`, URL, IP address, ARM or subscription path) is withheld; a generated hexadecimal suffix such as a portal OS disk's `<vm>_OsDisk_1_<32 hex>` is published (review fix 2026-10-11). No GitHub issue is created.
  4. **AI report**: a separate unmanaged-resource section (report v4, `ai-analysis --unmanaged`); nothing of it reaches the LLM; drift, cost, investigation and recommendation are unchanged.
- **Design (implemented)**:
  - **Scope and comparison**: every resource group whose ARM ID is a managed resource's ID in the run's `plan.json`; `GET .../resources` (api-version 2021-04-01, all pages) and, for unmanaged VMs (with `instanceView`), disks, public IPs and NICs only, one `GET <id>`. ARM IDs are case-folded and compared with every managed ID of the plan (`report_public.build_index`). A disk whose `managedBy` is a managed VM is `attached_to_managed` (possible inline OS disk; reported, never unmanaged or priced). Parent (child resource, e.g. VM extension) and attachment (disk → VM, NIC → VM, public IP → NIC) links are refs. Duplicate listing entries are counted once.
  - **Safety**: GET only, `management.azure.com` resource-group paths only (blocked before a token is requested), no redirects, bounded retries / `Retry-After` / pages (50) / resources (5000) / detail reads (500) / time (240 s; CI hard bound 300 s, setup bounded too); `AzureCliCredential` with the cached ARM audience (Task 9B.5). Nothing is imported, modified, deleted or applied.
  - **Outcome**: `complete` / `incomplete` / `failed` with fixed codes; a failed collection is never clean; an incomplete inventory is not priced (`not_run`).
  - **Contracts**: `unmanaged_inventory_version` 1 (`unmanaged_public.py`) and `unmanaged_cost_version` 1 (`unmanaged_cost.py`), strict, with invariants (counts, refs, arithmetic: component = unit price × quantity, resource = components, total = exact sum) and the public leak scan in validation. The cost document is bound to the inventory (canonical hash), the inventory to the public drift report (hash, run id, environment, plan timestamp).
  - **Pricing rules**: exactly one matching meter per resource, else `price_not_found` / `ambiguous_price` (`unavailable`, no amount). VM: `armSkuName` + region + OS product (Windows unless Azure Hybrid Benefit), Spot/Low Priority excluded, compute only, 730 h. Managed disk: billed tier from `diskSizeGB` (P/E 1–80; Standard HDD from S4) and LRS/ZRS, `<tier> <red> Disk` meter, 1/month; Ultra / Premium v2 / shared / performance-tier mismatch → `unavailable`. Public IP: Standard IPv4 regional only. Fixed no-direct-charge types (NIC, NSG, VNet, route table, ASG, VM extension, SSH key, auto-shutdown schedule) → `0`. Paid Linux images / marketplace plans → `partial`. Assumption and exclusion codes per resource.
  - **G14 addendum (Task 10.4)**: `ai_engine` may also import `drift_engine.unmanaged_cost` and `drift_engine.unmanaged_public`; they load no restricted module or Azure SDK (pinned by `tests/test_unmanaged_ai.py`). `unmanaged_public.QUERY_FAILURE_CODES` is a pinned copy of the Activity Log codes.
  - **Workflow**: `Unmanaged Resource Inventory` (third documented always-exit-0 step) and `Upload Unmanaged Inventory` (third documented `continue-on-error` upload) in `plan-and-analyze` after `Upload Drift Report`; new `unmanaged` job (`contents: read`; prices, verifies, uploads `unmanaged-resources-<run_id>`, writes the summary, requires success). `ai-analysis.yml` downloads it by pattern and passes `--unmanaged`; summary row status + count only.
- **Acceptance Criteria**:
  - [x] Unmanaged resources in Terraform-managed resource groups are detected by case-insensitive ARM ID comparison, including VMs, NICs, public IPs, disks and VM extensions, without classifying Terraform-managed resources as unmanaged. *(tests: portal VM set, case variants, managed child, attached-to-managed disk, duplicates)*
  - [x] Monthly cost is estimated from the Azure Retail Prices API with exact arithmetic; unknown or unsupported is `unavailable`/`partial`, never `$0`; no double counting. *(tests on real Central India samples: B1s 8.1760, P4 5.2795, Standard IP 3.650, total 17.1055)*
  - [x] Separate from drift and Infracost; report/summary/AI section with counts, types, statuses, estimate, assumptions; privacy rules followed.
  - [x] Azure/API failures, throttling and incomplete inventory are explicit; never a clean result.
  - [x] Real verification: a user-approved drift-detection dispatch against the user's manually created VM in `aitdd-dev-main-rg`. *(Run #44 `38140497702` and AI run #27 `38140599354`, 2026-10-11; see Completion Notes, "Real Azure and CI verification".)*
- **Validation**:
  - [x] New tests: `tests/test_inventory.py`, `test_unmanaged_cost.py`, `test_unmanaged_ai.py`, `test_unmanaged_workflow.py` (see Completion Notes for counts).
  - [x] Full suite and Terraform validation (see Completion Notes).
  - [x] Real Azure + CI run (user-approved; run #44 / AI run #27, 2026-10-11).
- **Completion Notes**:
  - **Implementation complete 2026-10-11; pending real verification** at that point (no workflow dispatched, no Azure resource touched, nothing committed). Committed afterwards as `8ef89b6` (pushed to `origin/main`; the message carries `[skip ci]`, so no push-triggered `security-scan.yml` or `terraform-auth-test.yml` run exists for that commit).
  - Verified Retail Prices API shapes (2026-10-11, Central India, public read): Linux/Windows VM products, Spot/Low Priority meters under the same `armSkuName`, `P10 LRS Disk` also under "Premium Page Blob" and "Disk Mount" meters (both excluded by the rule), S4 the smallest Standard HDD tier, ZRS disk meters, `Standard IPv4 Static Public IP` hourly.
  - **Tests** (Python 3.13.12, scratchpad venv with the pinned constraints):
    - New: `tests/test_inventory.py` 83, `tests/test_unmanaged_cost.py` 102, `tests/test_unmanaged_ai.py` 28, `tests/test_unmanaged_workflow.py` 42 (255 tests). Coverage: `unmanaged_public.py` 100%, `unmanaged_cost.py` 97%, `inventory.py` 95% (uncovered: the missing-SDK path and real `AzureCliCredential` creation).
    - Full suite (`pytest --cov=src/drift_engine tests/`): **2735 passed**, 3971 subtests, 0 failed, coverage 98.82% (gate 85%). `unittest` discovery in the venv: 963 OK.
    - Existing tests updated only for report v4, the new graph node and state fields, the workflow step lists/outputs/exceptions (third always-exit-0 step and continue-on-error upload, new job, AI download step and summary row), the Markdown section order and the G14 allowlist; one corpus mutant (`cost-limitations-dropped`) retargeted to the changed line (`tests/test_mutation_corpus.py` passes).
    - Safeguard mutation check (scratchpad only, throwaway copies, not committed): 20 of 20 mutants caught (case-sensitive comparison, managed resources not excluded, attached-to-managed disk treated as unmanaged, failed listing reported clean, failed detail read ignored, duplicates counted twice, identifier-like names published, URL guard opened, unknown type priced 0, Spot not excluded, Windows rate ignored, ambiguous price picks first, 720 hours, API failure not failed, incomplete inventory priced, binding not checked, disk tier off by one, verifier skipping the section, unmanaged limitation lines dropped, require step ignoring a pricing failure).
    - Terraform: `scripts/validate.sh` (fmt -check, bootstrap and dev validate, no Azure auth) passes; lock files unchanged. Every workflow `run:` block and every script passes `bash -n`; both workflows parse as YAML. actionlint and ShellCheck were not run (not installed; no download without approval).
  - A test exposed a duplicated unit in the resource statement ("$8.18/month per month"); the template was fixed before completion.
  - **Review fixes (user-approved 2026-10-11)**: (1) names with a generated 32-hex suffix (portal OS disks) are published; GUID, e-mail/`@`, URL, IP and ARM/subscription-path names stay withheld. (2) `scripts/inventory_analysis.sh` bounds every blocking operation (venv 60 s, pip 180 s, pin check 30 s, `drift-engine inventory` 300 s, public check 45 s; worst case about 615 s, a hit is `timeout`) and the inventory's Azure deadline is 240 s, keeping `plan-and-analyze` well inside its 45-minute limit. (3) `drift-engine inventory` reads `--plan` up to the plan parser's 50 MiB limit (was 10 MiB). (4) A stale test comment was moved. (5) Final-review wording fix: an incomplete unmanaged total (any unavailable or partial estimate) is shown as "At least $X/month — incomplete estimate" in the job summary, the AI report's Markdown summary line and the CLI line, and stated with the new fixed template `unmanaged.total_incomplete.v1` (`unmanaged.total.v1` is used only for a complete total); per-resource statuses, the JSON documents and verification are unchanged.
  - **Real Azure and CI verification (2026-10-11; user-approved dispatch; closes the task)**: the user created a VM in the Azure Portal inside `aitdd-dev-main-rg` (outside Terraform) and dispatched `drift-detection.yml` on commit `8ef89b6`.
    - **Directly verified (public Actions API, read-only)**: run #44 `38140497702` (`workflow_dispatch`, `main`, attempt 1, 12:45:40Z) concluded `success`; every job succeeded: `Preflight`, `Terraform Plan & Drift Analysis` (incl. `Unmanaged Resource Inventory` and `Upload Unmanaged Inventory`), `Cost Estimate`, `Drift Investigation`, `Drift Issues`, `Report & Summary` and `Unmanaged Resources` (`Price Unmanaged Resources`, `Verify Unmanaged Documents`, `Upload Unmanaged Resources Report`, `Unmanaged Summary`, `Require Unmanaged Inventory`). The `Unmanaged Resources` job raised exactly the designed warning annotation: "5 Azure resource(s) not managed by Terraform found in its resource groups (a finding, not drift and not a failure; see the summary)". Artifacts `unmanaged-inventory-38140497702` and `unmanaged-resources-38140497702` were uploaded next to the drift report, investigation and Infracost artifacts. The triggered AI analysis run #27 `38140599354` succeeded, including `Download source unmanaged resources report`, and uploaded `ai-analysis-report-38140497702`. Annotations otherwise show only the standard Node.js 20 / `ubuntu-latest` notices.
    - **Inferred from the job gates (decision 2)**: the inventory was `complete` and the Retail Prices API pricing did not fail, because `Require Unmanaged Inventory` fails the job on a failed or incomplete inventory, a pricing failure, or a failed verification or upload. The detection result was valid (the AI run analyses only a valid result and uploaded a report). The unmanaged finding did not turn the run red (decision 2).
    - **User-reported (summary and artifacts inspected by the user, 2026-10-11)**: inventory completed; 5 unmanaged resources; total estimated monthly cost **$44.85** (Azure Retail Prices API list price, USD; not billing, never added to the Infracost estimate); AI report v4 contains the "Unmanaged resources (outside Terraform)" section. Claude did not download these artifacts (they need authentication), so the per-type breakdown, per-resource statuses and whether the total was complete or "at least" are not recorded here.
    - **Cleanup (user-reported)**: the user deleted the test VM after the run. Claude has no Azure access in this session and did not verify it. Whether the VM's associated resources (disk, network interface, public IP, NSG) were deleted with it was not confirmed. The next scheduled inventory, which runs daily, will show any that remain.
  - **Limitations**: Terraform-managed resource groups only; ARM resource list only (no data-plane objects); Terraform `id` must equal the ARM ID; snapshot taken after the plan refresh; only VMs, managed disks and Standard IPv4 public IPs are priced; list prices, 730 h, no usage charges, not billing. Real Azure verification covers one manually created VM scenario in `aitdd-dev-main-rg` (run #44). The other priced and unpriced paths (Windows / Azure Hybrid Benefit, ZRS and Standard HDD disks, Spot, unsupported types, `incomplete` and `failed` inventories, Retail Prices API failures) are verified by tests only.

---

### PHASE 11 — Human-Approved Remediation
**Status**: 🔴 BLOCKED — on hold (user decision 2026-10-13): intentionally deferred while Phase 12 testing and security hardening are prioritized; no Phase 12 task depends on Phase 11. Task 11.1 stays 🟡 (specification revision 9 under user review, 2026-10-12; progress and recorded decisions unchanged); Tasks 11.2 and 11.3 ⬜ NOT STARTED. Resumes at Task 11.1 on user instruction.

Phase 11 enforces strict human approval controls before applying any automated infrastructure remediation.

#### Task 11.1 — Safe Remediation Architecture & Controls
- **Status**: 🟡 WORK IN PROGRESS (specification revision 9 drafted; awaiting user review and approval) — paused while Phase 11 is on hold (2026-10-13); progress and recorded decisions unchanged.
- **Started**: 2026-10-11
- **Objective**: Architect human-in-the-loop controls prohibiting autonomous destructive apply actions.
- **Dependencies**: Task 8.3
- **Dependency note**: changed 2026-10-03 from the superseded remediation-PR task (Phase 8 design review, option R1); its remediation PR scope moved into this task.
- **Files/Areas**: `docs/remediation-safeguards.md`
- **Acceptance Criteria**:
  - [ ] Specification mandating manual review, environment approval gates, and `terraform plan` verification prior to `apply`.
  - [ ] Direct `terraform apply` blocked in automated background detection workflows.
  - [ ] **Locked remediation requirements (moved from Task 8.2, design review 2026-10-03)**:
    - the remediation direction is a human choice;
    - revert direction = reviewed Terraform apply of `main`;
    - accept direction = human-authored PR;
    - PRs reference drift issues using `Refs #n`;
    - remediation PRs never use a closing keyword (drift issues are closed only by Task 8.3 evidence-based resolution);
    - no auto-merge;
    - no apply triggered merely by a merge;
    - real Azure values are published only through a human-authored change.
- **Validation**:
  - [ ] Document architecture approval.
- **Implementation Notes**:
  - Core safety principle: Zero autonomous destructive changes.
- **Completion Notes**:
  - **In progress (2026-10-11)**: `docs/remediation-safeguards.md` drafted (documentation only; no workflow, GitHub setting, Azure identity, role or Terraform change; not committed).
    - Revision 1 reviewed by the user on 2026-10-11: D1 (single run: plan → approval → fresh plan → fingerprint verification → apply), D3 (create and update only; delete, replace and import refused), D5 (self-approval allowed, risk and future multi-reviewer requirement recorded), D6 (24-hour approval expiry; expiry needs a fresh plan and approval) and D8 (no repository writes) approved; D2 (Azure permissions), D4 (reviewer process and fingerprint) and D7 (concurrency) sent back for refinement.
    - Revision 2 refines D2 (instance-scoped custom roles, one role definition per scope, runtime guards, verification from the unmanaged side), D4 (local reviewer procedure, exact fingerprint inputs and limits, approval comment bound to the fingerprint) and D7 (no shared concurrency group; state lock, one-remediation preflight, bounded wait for detection), and adds acceptance criteria for 11.2 and 11.3. It raised one open decision, D2-C (instance-scoped roles cannot create resources).
    - Revision 2 reviewed by the user on 2026-10-11: **C1** approved (v1 refuses create, delete, replace and import; only explicitly allowed updates of existing managed resources); D2 approved **as a proposal, not as validated Azure permissions** (provider operations, inherited permissions, dependency access and unmanaged isolation to be verified before apply is enabled); D4 sent back (bind the approval to the run, commit, exact plan fingerprint and Terraform/provider inputs; no reliance on a public fingerprint for confidentiality; safe access to the exact proposed change); D7 approved provisionally (explicit pre-apply checks for active detection, stale plans and lock conflicts); D5, D6 and D8 retained.
    - Revision 3 adds the C1 eligibility rule and a proposed update allowlist; marks the role design as a proposal behind an apply enablement gate (E1–E6, with `apply_enabled: false` until then); replaces the public fingerprint with an encrypted review bundle of the exact CI plan, a keyed fingerprint and an approval statement bound to run, commit, plan and toolchain; and defines ordered pre-apply checks P1–P12. Unresolved security decisions U1–U6 (encryption tool, fingerprint-key location, initial allowlist, reviewer key management, auth-test runs in the detection check, E1 evidence source) are listed for the user.
    - Revision 3 reviewed by the user on 2026-10-11: U1 (GnuPG), U4 (reviewer key custody), U5 (auth-test runs in the detection check) and U6 (Activity Log evidence) approved conditionally; U2 (repository-secret HMAC key) and U3 (NSG `security_rule` in the initial allowlist) not approved; the D4 binding sent back to separate the GitHub Environment approval from the statement attestation. `apply_enabled` stays `false`.
    - Revision 4: no repository secret (a per-run fingerprint key, sealed for the reviewer and for the `apply` job, whose private key is a `dev-remediation` environment secret) with a leak threat model; GnuPG on a pinned `ubuntu-24.04` runner with version check, packet format and a tested reviewer procedure; reviewer key custody, recovery, rotation and never-in-GitHub checks; a tags-only initial allowlist validated against the actual planned attribute paths, with a separate security review required before NSG rule changes; two separate approvals (Environment deployment approval and a signed statement attestation) bound to run, attempt, commit, plan fingerprint, toolchain, artifact digests and expiry; auth-test verified (from the workflow files) to plan against `dev.tfstate` without a lock timeout, with races documented; E1 left unverified and enablement blocked without sufficient Activity Log evidence. Remaining decisions R1–R4 and unverified assumptions are listed in §15.
    - Revision 4 reviewed by the user on 2026-10-11: R1 changed (prefer an encrypted offline recovery copy of the apply-job key; document loss consequences and rotation), R2 deferred (hardware token optional), R3 approved (B without A recorded as a security event without sensitive content), R4 approved conditionally (separately approved, narrowly scoped, reversible local tag apply plus provider-source evidence; missing evidence leaves E1 unverified). Five security corrections required: a key/seal threat model derived from the actual cryptographic flow; `apply_enabled` kept false until all gates pass; the confirmed auth-test full-plan logging made an enablement prerequisite with a defined verification; A and B rechecked as independently validated and bound to the same run, attempt, commit, fingerprint, bundle digest and expiry; the tag-only allowlist checked against actual attribute paths without admitting unrelated or apply-time-unknown changes.
    - Revision 5: traced key and seal flow and a compromise analysis (individual and combined): a leaked apply-job key allows guess-testing over every seal an attacker collected, not only retained ones; a leaked reviewer key discloses all values, including sensitive ones, of every collected bundle and allows B; the maintainer's GitHub account alone can bypass B by changing workflow code, so with standing write roles it can apply within the RBAC scope (new decision R5: just-in-time write roles). Independent A/B validation with a value-by-value cross-binding table and the R3 security event. Eligibility now also checks `resource_drift` (state-only drift) in both modes, refuses any apply-time unknown, sensitivity change, data-source read, `action_reason` and reserved tag prefixes, with exact type-aware comparison. Apply-job key recovery copy and rotation procedure (R1). E1 conditions (R4). New gate E6: the auth-test log fix and its verification (structural test, sentinel check on a real run, list of older logs for the user, R7); user approval becomes E7. Remaining decisions R5–R7 and unverified assumptions are listed in §15.
    - Revision 5 reviewed by the user on 2026-10-12: R5 approved conditionally (no standing write roles; just-in-time roles granted by the user, never by the workflow, only after review and both approvals and immediately before apply; apply disabled until implemented and verified); R6 approved conditionally (verify the Environment protection configuration or fail closed); R7 changed (no blind deletion of old logs: determine exposure, preserve evidence, restrict or delete where appropriate, document what cannot be removed).
    - Revision 6: no standing write roles; a just-in-time window (P12) in which the user's local procedure (trusted-code check, binding to run, attempt and `S`, per-run least-privilege set) grants roles, the job verifies its own effective permissions, rechecks and re-plans (P13) and applies (P14), and the user removes the roles (hard limit 45 minutes; leftover detection; manual recovery and containment by deleting the federated credential); a `jit_rehearsal` input, accepted only while apply is disabled, verifies the window without applying; the workflow never changes permissions (invariant 19); residual risk stated. P0 reads the Environment protection configuration (administrator bypass off) and fails closed if it differs or cannot be read. Plan-format hardening (unknown keys, identity fields, `generated_config`, allowed `format_version`); fingerprint covers the full `change` object. Key/seal flow re-traced with the just-in-time steps; compromise table updated (the GitHub account alone can no longer apply; the user's machine and Azure credentials are the root of trust). Existing auth-test logs measured from the public API (67 runs, 63 successful pushes with a printed plan, no artifacts, readable by any signed-in GitHub user, all within 90-day retention, 9 cited as evidence) with a classify, preserve and delete-per-run procedure (§12.1). New gates E7 (just-in-time roles), E8 (Environment configuration); approval becomes E9. Remaining decisions R8–R10. Revision 5 is kept privately in the ignored `.artifacts/task-11.1-spec-revisions/` for an exact revision diff; no exact revision 4-to-5 diff exists (the session scratchpad copy was lost).
    - Revision 6 reviewed by the user on 2026-10-12: R8 approved (the local grant script authenticates with the user's own logins and verifies the Environment settings before any grant; unreadable, different or unmatched settings refuse the grant); R9 approved (15-minute propagation timeout and 45-minute role lifetime as hard limits; failure stops the run before apply); R10 approved (per-run deletion only after local classification confirms exposed values and a private evidence copy is kept; run records preserved). Strengthening required: grant script and trusted inputs in the security boundary; interruption and disconnection never permitting an apply after failed verification; real-plan validation of tag-only eligibility before enabling; verified auth-test fix with audit records; a recheck of the A, B and grant binding; a statement of which checks need real execution.
    - Revision 7: the grant script and its trusted inputs (separate reviewed clone, locally stored trusted digest over code and policy, the user's attestation, private identifiers) are part of the security boundary; eight pre-grant checks (logins, self-check, run binding, trusted digest, A and B re-verified, Environment configuration unchanged since the plan, no unexpected assignments, least privilege, time); a `pending`/`confirmed` assignment handshake that the job requires at P12 and immediately before apply; hard limits enforced (P12 15 minutes, P13 5 minutes, apply step 20 minutes, assignments under 25 minutes old before apply, removal at 45 minutes); a cleanup table for normal end, failed checks, interruption, kill, sleep, disconnection and removal failure, with an emergency procedure (remove from any device, else delete the federated credential or disable the service principal, check the Activity Log). Standard role assignments do not expire, so Azure-enforced expiry is new decision R11 (Privileged Identity Management if licensed). The tag-only allowlist is enabled per address only after real-plan validation (new gate E9): the committed real `external_drift` fixture supports the resource-group rules preliminarily (only `tags.<key>` changes, no unknowns, unchanged sensitivity and identity) but predates the current provider lock; no real evidence exists for the VNet and NSG, so all entries stay disabled. E6 now defines structural, executed-step, audit-retention and real sentinel checks for the auth-test fix. The binding recheck adds a value-by-value table across A, B, the grant script and the job. §15.4 separates documentation-only checks from those needing real GitHub and Azure execution. User approval becomes E10. Revision 6 is kept privately in `.artifacts/task-11.1-spec-revisions/` for an exact diff.
    - Revision 7 reviewed by the user on 2026-10-12: R11 decided (prefer Azure-enforced time-bound PIM assignments; the local 45-minute cleanup is not equivalent to Azure-enforced expiry; document residual risks; define and verify a stronger fallback before apply, otherwise keep apply disabled; effective permissions and exact assignment scopes are the checks, the pending/confirmed description is only a handshake marker); R12 approved (per-run log deletion after classification confirms exposure and a private evidence copy is kept; run records preserved).
    - Revision 8: role expiry control (§10.10): PIM time-bound active assignments (preferred, licence and behaviour to be verified), else an Azure-side cleanup watchdog with a delete-only identity (proposed; new decision R13, needs approval as a new Azure resource), else apply stays disabled; the local script is only the earliest cleanup. In-job security checks are exact assignments by principal, role definition and scope, Azure-side end times (at most 45 minutes after start, at least 21 minutes left before apply) and exact effective permissions; the marker is not a security check. Consistent limits (15-minute grant window, 5-minute recheck, 20-minute apply step, 45-minute maximum; a legitimate apply always ends before it), a ten-phase lifecycle table, cleanup succeeds only on a clean V2 (otherwise non-zero exit, emergency procedure, `cleanup_unconfirmed`), and a residual-risk table (active roles, permanent assignments, disconnection, issued tokens, propagation delay, delayed response). New gate E10 (expiry control verified by rehearsals with the script disconnected); user approval becomes E11. Allowlist entries all stay disabled until E9. Revision 7 is kept privately in `.artifacts/task-11.1-spec-revisions/` for an exact diff.
    - Revision 8 reviewed by the user on 2026-10-12: R13 not approved yet; PIM time-bound assignments stay preferred and the user verifies tenant licensing and configuration first; if PIM is unavailable, the Azure-side watchdog is to be presented as a separate design for review, not implemented or provisioned, and not described as a strict 45-minute expiry.
    - Revision 9: the watchdog is a separate design (§10.11), explicitly best-effort cleanup (up to about 5 minutes after the 45-minute threshold, plus run time, retries and RBAC propagation, unbounded if the watchdog fails), never an expiry; it defines a trusted age record (Azure-set `createdOn`, cross-checked with the Activity Log write event, earlier time counts; never `updatedOn` or client text; missing age treated as overdue), deletion only on an exact match of principal, role definition, scope and age from user-configured values, anomalies alerted but never deleted, a read-and-delete-only identity (broader than the code's restriction, an availability risk documented), failure handling with alerts, overdue, removal, failure and missed-run alerts, cleanup confirmed by re-listing, and a verification plan if approved. PIM end timing is marked as to be measured (E10). The revision 8 status header still read "revision 7"; corrected. Revision 8 is kept privately in `.artifacts/task-11.1-spec-revisions/` for an exact diff.
    - The acceptance criteria above stay open until the user approves the specification (Validation).

#### Task 11.2 — Multi-stage Approval Workflow
- **Status**: ⬜ NOT STARTED
- **Objective**: Configure GitHub Actions environment protection rules requiring manual reviewer sign-off before remediation pipeline execution.
- **Dependencies**: Task 11.1
- **Files/Areas**: `.github/workflows/remediation-apply.yml`
- **Acceptance Criteria**:
  - [ ] Environment `production` / `dev-remediation` requires designated reviewer approval in GitHub Settings.
  - [ ] Pipeline pauses until reviewer approves run.
- **Validation**:
  - [ ] Trigger remediation workflow -> verify execution pauses for manual approval.
- **Implementation Notes**:
  - GitHub Actions environment approvals.
- **Completion Notes**:
  - None.

#### Task 11.3 — Safe Terraform Apply Execution
- **Status**: ⬜ NOT STARTED
- **Objective**: Build remediation apply pipeline executing `terraform apply` safely only after approval and plan confirmation.
- **Dependencies**: Task 11.2
- **Files/Areas**: `.github/workflows/remediation-apply.yml`
- **Acceptance Criteria**:
  - [ ] Workflow checks out the approved revision: `main` for the revert direction, or the merged human-authored PR revision for the accept direction. *(Reworded 2026-10-03: no approved PR branch exists for the revert direction; Task 8.2 superseded by Phase 11.)*
  - [ ] Executes `terraform plan` and requires second confirmation if plan diff changed.
  - [ ] Executes `terraform apply` cleanly upon confirmation.
- **Validation**:
  - [ ] Perform end-to-end safe remediation test on dev environment.
- **Implementation Notes**:
  - Closed-loop remediation under human oversight.
- **Completion Notes**:
  - None.

---

### PHASE 12 — Testing & Security Hardening
**Status**: 🟡 WORK IN PROGRESS — Task 12.1A 🟢 COMPLETED (2026-10-14); Task 12.1 🟢 COMPLETED (2026-10-16); Task 12.2 🟢 COMPLETED (2026-10-16); Task 12.3 🟢 COMPLETED (2026-10-16). All tasks are complete; the deferred scope recorded below is still open.

Phase 12 builds a comprehensive end-to-end test suite and performs security hardening across all platform components.

> **Scope deferred into Phase 12 (recorded 2026-10-04):**
> - **Super-Linter / Docker-based code-quality enforcement** from Task 9.4 (🔴 BLOCKED — deferred). Its locked design (D1–D10) is in Task 9.4 and must be re-validated before use.
> - **GitHub Actions workflow linting (actionlint, zizmor) and pinning actions by commit SHA**, already deferred to Phase 12 by Tasks 9.1–9.4.
>
> - **Known limitation: Phase 5 diagnostic-log exposure (recorded 2026-10-05, user decision during the Task 9B.5 review)**:
>   - on a failed detection, `Generate Plan Evidence` prints the last 50 lines of `plan.log`, and `Verify Azure OIDC Authentication` prints `az account show` on every run;
>   - GitHub masks the secret values (subscription and tenant ID), so they show as `***`, but `/subscriptions/***/…` paths, resource names and other Terraform error text can still reach the public workflow log;
>   - this predates Phase 9B and is outside Task 9B.5's scope (G11's log rule is enforced there only for the steps 9B.5 adds or changes). Phase 12 decides the fix (e.g. a redacted or summarised diagnostic).
>   - **Task 9B.6 (plan revised 2026-10-10, D-2)** limits its job-log privacy check to the `Drift Investigation` step, the `investigation` job and the `ai-analysis` job, and excludes these two diagnostic outputs explicitly. The limitation stays open here.
>   - **Status (2026-10-14)**: fixed for new runs by Task 12.1A (commit `6d1aa86`): the `plan.log` tail is no longer printed and `az account show` is replaced by a silent comparison. Verified by local executed-step tests; the identical auth-check block passed live in auth-test run #68, but no live `drift-detection.yml` run has been inspected (unverified). Logs of earlier runs are unchanged.
>
> - **Known limitation: `terraform-auth-test.yml` prints the full plan to the public log (confirmed 2026-10-11 from the workflow file, Task 11.1 review)**:
>   - its `Validate Dev Environment Configuration` step runs `terraform plan -var-file="dev.tfvars" -input=false -no-color` against `dev.tfstate` on every push to `main`/`master` and on manual dispatch, and prints Terraform's human-readable plan, including the non-sensitive attribute values of every planned change (sensitive values show as `(sensitive value)`), to the public job log; it also sets no `-lock-timeout`;
>   - **prerequisite for Phase 11 apply enablement** (`docs/remediation-safeguards.md`, gate E6): the fix is a separate, user-approved change (here or in a dedicated task), verified by a structural test (plan output written to a runner-local file; only the exit code and change counts printed) and a real sentinel check (a temporary probe-tag value absent from the downloaded log of a push-triggered run);
>   - **existing logs** (measured 2026-10-12 from the public API): 67 runs, 63 successful pushes with a printed plan, no artifacts, readable by any signed-in GitHub user, all within the 90-day retention, 9 cited as evidence in this plan; they are classified locally, evidence is preserved, and logs with values are deleted per run by the user's decision (spec §12.1, R7, R10); copies already made by others cannot be removed.
>   - **Status (2026-10-14)**: fixed for new runs by Task 12.1A (commit `6d1aa86`), verified by the real sentinel check on push-triggered auth-test run #68. The existing logs are **not yet handled** (spec §12.1, R7, R10; open).
>
> How these are scheduled within Phase 12 (for example as their own task) is decided in a Phase 12 design review. No task is added here.
>
> **Scheduling decided (user decisions 2026-10-13, Task 12.1 design review)**: the two log-exposure limitations above become Task 12.1A, an early, separate security-hardening task. Per WF-1, actionlint, zizmor and verified full commit-SHA pinning are required parts of the later approved CI implementation plan. Super-Linter (Task 9.4) stays deferred, still subject to its own re-validation.

#### Task 12.1 — Comprehensive Unit & Integration Test Suite
- **Status**: 🟢 COMPLETED (2026-10-16) — `tests.yml` run #2 passed on commit `cd38ffe`
- **Completed**: 2026-10-16
- **Started**: 2026-10-14
- **Objective**: Implement comprehensive `pytest` suite covering Python parser, drift models, severity rules, GitHub automation, and AI graph nodes.
- **Dependencies**: Tasks 4.7, 6.7, 8.3
- **Files/Areas**: `tests/`
  - Planned for the approved implementation (design review 2026-10-13): `pyproject.toml` (marker registration), `requirements.txt` and a new `ci/dev-constraints.txt` (Decision 3), marker decorators in the mixed test files, a new `.github/workflows/tests.yml` (Decision 5), `README.md`.
- **Acceptance Criteria**:
  - [x] Test suite covers clean, drifted, invalid, and corrupted inputs. *(Assessed 2026-10-14; one gap filled, see Completion Notes.)*
  - [x] Test execution completes in < 60 seconds. *(Amended 2026-10-13, Decision 4: the target applies to the fast CI tier, not to the full suite. The full-suite runtime is a monitored budget, never a reason to skip, drop or weaken tests.)*
  - [x] **Tiers (Decision 4)**: existing tests classified with explicit `integration` and `mutation` markers. The fast tier is the tests with neither marker, and its runtime is measured before pytest-xdist is considered. The full suite still runs every existing test: 0 failed, 0 errors, no test skipped or weakened, and no fewer than the 2,763-test baseline without a recorded plan decision.
  - [x] **Coverage (Decision 2)**: the `fail_under = 85` gate is unchanged. `src/ai_engine` coverage is measured, and per-package thresholds are proposed for review after its baseline.
  - [x] **Reproducibility (Decision 3)**: a fresh virtual environment installs the documented dependencies with all constraint files applied, with no duplicate pins. This is verified on the supported local and CI Python/platform combinations.
- **Validation**:
  - [x] `pytest tests/` passes cleanly with high coverage. *(Amended 2026-10-13, Decision 2: "high coverage" means the unchanged 85% gate plus the measured per-package figures; no additional gate is enforced until thresholds are reviewed.)*
- **Implementation Notes**:
  - Automated quality gate.
- **Design Review (2026-10-13, user decisions 1–5; no implementation yet)**:
  - **Baseline (measured 2026-10-13 on commit `488f42d`; macOS arm64, Python 3.13.12, isolated scratchpad venv; `pytest --cov=src/drift_engine tests/`)**:
    - with the documented setup (`pip install -r requirements.txt`, no constraints): 2,761 passed and 2 failed in 233.8 s. The failures were the two constraint-closure tests (`tests/test_ai_cli.py::test_constraints_equal_the_complete_ai_closure` and `tests/test_investigation_workflow.py::test_azure_constraints_equal_the_complete_azure_closure`); newer resolved packages fell outside the CI pins;
    - with both constraint files also applied (`-c ci/ai-constraints.txt -c ci/azure-constraints.txt`): **2,763 passed**, 0 failed, 0 skipped, 0 errors in 237.8 s (228.7 s on a `--durations=25` run); the two constraint files share 11 packages, all with identical pins;
    - coverage **98.85%** (gate 85%) for `src/drift_engine` only. `src/ai_engine` has never been measured, so this figure does not cover the whole project;
    - the 25 slowest tests take 86.7 s (mutation, fuzz and leak-scan loops; bash workflow harnesses; about 14 s of real retry backoff in subprocess anchor-fetch tests). Wall time is about twice CPU time (about 113 s);
    - no CI workflow runs pytest.
  - **Decision 1 — WF-1 (workflow changes)**:
    - Task 9.4's workflow rule (D5) applies to the Super-Linter work covered by that task; it is not a blanket prohibition on later workflow changes.
    - Phase 12 may propose a new `.github/workflows/tests.yml`.
    - Any modification of an existing workflow requires a separately approved task with a reviewed diff and appropriate validation.
    - actionlint, zizmor and verified full commit-SHA pinning must be part of the later approved CI implementation plan.
    - No other security restriction is relaxed by WF-1.
  - **Decision 2 — Coverage**: `fail_under = 85` unchanged; no separate enforced 95% gate yet; `src/ai_engine` coverage measured in the approved implementation stage, then per-package thresholds proposed for review.
  - **Decision 3 — Dependency reproducibility**:
    - A dedicated `ci/dev-constraints.txt` (test tooling: pytest, pytest-cov, coverage, jsonschema and their closures) is approved in principle, alongside the existing AI and Azure constraints, subject to compatibility validation.
    - Duplicate pins are avoided.
    - The existing constraint files and pins are preserved unless a separately reviewed conflict is found.
    - Not created yet.
  - **Decision 4 — Test tiers**:
    - Staged design: first classify existing tests with explicit markers (`integration` for subprocess, bash-harness, git and loopback-API tests; `mutation` for mutation, fuzz and leak-scan tests), then measure the fast tier.
    - No autouse subprocess-blocking fixture in the first step. Marker enforcement is first assessed through collection checks and targeted tests; a guard is proposed only if necessary, with its scope and potential false positives explained.
    - pytest-xdist only by a separate measured decision with an isolation review.
    - The opt-in `scripts/run_mutation_checks.py` stays outside the default suite.
  - **Decision 5 — CI design (proposal; not created)**:
    - A new `.github/workflows/tests.yml` with `contents: read` only.
    - No Azure login, secrets or OIDC token permission.
    - Actions pinned by verified full commit SHA.
    - Fast and full test jobs, with explicit failure handling and runtime reporting.
    - No caching initially unless later measurements justify it.
    - GitHub settings (e.g. required checks) are unchanged; any change there is a user action.
- **Completion Notes**:
  - **Implementation and local validation (2026-10-14)**:
    - **Tiers (Decision 4)**: markers `integration` and `mutation` registered in `pyproject.toml`; 340 tests marked by decorators (327 `integration`, 15 `mutation`, 2 with both) (unittest-style files import them from the new `tests/tiers.py`, so `python3 -m unittest discover -s tests` loads exactly as before: 755 tests, the same 25 pre-existing import failures). `integration` (327) was measured, not guessed: a probe recorded every test that started a subprocess or bound/connected a socket during a full run; whole classes or files were marked only when every member was flagged. A follow-up search found no `os.system`, `os.exec*`, `pty`, `fork`, `spawn`, asyncio subprocess or multiprocessing use outside child-process shims. `mutation` (15) is the reviewed list: the `SafeguardMutationTests` classes, the parser and model fuzz tests, two exhaustive planted-value scans and the Infracost mutant classes (four harness-control tests sit with their classes; the cheap mutant-corpus check and the seeded-shuffle determinism tests stay in the fast tier). The diff to the test files adds lines only: no test removed, skipped or weakened (in the pre-existing files: 1,498 test functions and 124 skip/xfail tokens before and after). pytest-xdist is not needed.
    - **Input coverage**: clean (`plan_evidence/in_sync` through the classifier, CLI, severity, AI parse and issue lifecycle), drifted (real `plan_evidence` scenarios and the generated security, cost, root-cause and report plans), invalid (parser, identity, manifest, model, AI-contract and issue-report consistency checks) and corrupted input (parser: empty, truncated, two documents, trailing garbage, BOM, non-UTF-8, deep nesting, size limit, fuzz) are covered with asserted fail-closed behaviour. Gap found and filled: non-UTF-8 bytes at the two consumer entry points (the `ai-analysis` CLI's `UnicodeDecodeError` branch was never reached; GitHub automation's `report_invalid` path for undecodable bytes). One case added to each existing test; a mutant check confirms the AI case fails when the handler is removed. Not fixed (test-only helper): `ai_engine.nodes.parse_drift.load_drift_report` raises `UnicodeDecodeError` rather than `DriftReportError` for non-UTF-8 input; the CLI uses its own loader, which handles it.
    - **Reproducibility (Decision 3)**: new `ci/dev-constraints.txt` pins the complete `dev` closure (11 packages; `packaging` and, below Python 3.13, `typing_extensions` stay pinned only in the existing files, so no pin is duplicated). `requirements.txt` now applies all three constraint files, so the documented `pip install -r requirements.txt` installs the pinned set (66 packages). Existing pins unchanged; only the "Local development keeps the pyproject.toml ranges" comment in `ci/ai-` and `ci/azure-constraints.txt` was corrected. Verified: fresh venvs from `pip install -r requirements.txt` on CPython 3.12.15 and 3.13.12 (macOS arm64): exactly the 66 pinned versions, `pip check` clean; a wheel-only resolution for CPython 3.12 on linux x86_64 (the CI platform) returns exactly the 66 pins, no source builds. CPython 3.14: the existing AI pin `tiktoken==0.11.0` has no cp314 wheel (everything else resolves); not changed here.
    - **CI (Decision 5)**: new `.github/workflows/tests.yml` (no existing workflow changed, WF-1): push to `main`, pull requests and manual dispatch; `contents: read` only; no Azure login, secrets, OIDC or environment; `ubuntu-24.04`, Python 3.12, `requirements.txt` install plus `pip check`; job `fast` runs the fast tier with `--strict-markers` and reports its runtime (warning at ≥ 60 s); job `full` runs every test with coverage of both packages, then applies the unchanged gate (`coverage report --include='src/drift_engine/*'`, `fail_under = 85` from `pyproject.toml`) and reports `src/ai_engine` without a gate. Actions pinned by full commit SHA, resolved from the official repositories' release tags and fetched to confirm they are commits: `actions/checkout` v6.1.0 `d23441a48e516b6c34aea4fa41551a30e30af803`, `actions/setup-python` v6.3.0 `ece7cb06caefa5fff74198d8649806c4678c61a1` (both node24); `persist-credentials: false`; no cache. actionlint 1.7.12 with ShellCheck 0.11.0: 0 findings (a deliberately broken copy produced ShellCheck findings, so the integration is active). zizmor 1.30.1 (offline, `auditor` persona): no findings. GitHub settings (required checks) unchanged.
    - **New tests**: `tests/test_tests_workflow.py` (14, fast tier) checks the workflow structure, the SHA pins, the absence of secrets, OIDC, write permissions and caching, the gate command, the dev closure (complete, exact, in range, no duplicate pin), the installed dev versions, `requirements.txt` and the marker registration. Mutation check on scratch copies: 12 of 12 mutants caught (write permission, persisted credentials, tag pin, narrowed tier, disabled gate, cache, duplicate/missing/unneeded/out-of-range pin, dropped constraint file, installed version drift); the unmutated control passes.
    - **Results (fresh CPython 3.12.15 venv, the CI interpreter)**: fast tier 2,542 passed, 340 deselected, 0 failed in 21.6 s; full suite **2,882 passed**, 0 failed, 0 skipped in 239.4 s (2,867 before Task 12.1's additions + 14 new tests + 1 new parametrized case); coverage gate passed: `src/drift_engine` **98.85%**; `src/ai_engine` **97.69%** (report only).
    - **Results (fresh CPython 3.13.12 venv, macOS arm64)**: fast tier 2,542 passed in 24.1 s; full suite 2,882 passed, 0 failed, 0 skipped in 246.8 s; same coverage (98.85% gate passed; 97.69%).
    - **Per-package thresholds (proposal for review, not enforced; Decision 2)**: keep the 85% project gate; add floors of 95% for `src/drift_engine` (98.85%; parser, classifier, comparator, severity and models at 100%), 95% for `src/ai_engine` (97.69%) and 95% for `scripts/github_automation.py` (100% in-process). No gate yet for `scripts/sanitize_infracost.py` (91.35%) or `scripts/fetch_prior_drift_reports.py` (52.80%): both run mostly in child processes, which coverage does not trace, so the figures understate them. `scripts/run_mutation_checks.py` (opt-in tool) excluded. Enforcement would be one `coverage report --include=<package>/* --fail-under=N` per package.
    - **Informational, not changed (WF-1)**: zizmor on the existing workflows reports 42 findings (default persona): 39 `unpinned-uses`, one `dangerous-triggers` (`ai-analysis.yml`, `workflow_run`), one `excessive-permissions` (`drift-detection.yml`), one `artipacked` (`terraform-auth-test.yml`); actionlint reports none. Fixing them is a separate, approved workflow task.
  - **First CI run (2026-10-16; commits `73adad7` and `5ddeb86` pushed on user approval)**: [Tests #1](https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/38912773425) **failed**. Installation from `requirements.txt` succeeded in both jobs on `ubuntu-24.04` / Python 3.12 (17 s and 19 s). Fast tier: 2,539 passed, 3 failed, pytest 43.0 s (step 46 s). Full suite: 2,879 passed, 3 failed in 288.3 s; the coverage step was skipped. The same push's Security Scan #33 and Terraform Auth & Validation #69 succeeded.
    - **Cause**: `activity_logs`/`attribution` `CliTests::test_standard_output` and `investigation` `CliErrorTests::test_stdout_and_write_error` expect standard output, but the runner sets `GITHUB_ACTIONS=true`, which turns on the CLI's deliberate guard (`drift_engine.cli._refuse_restricted_stdout`: restricted documents never go to stdout in GitHub Actions; exit 2). A test-isolation defect, not a product defect: reproduced locally from the pushed `HEAD` with `GITHUB_ACTIONS=true` (the same 3 failures).
    - **Fix (commit `cd38ffe`)**: the three CLI test helpers clear `GITHUB_ACTIONS` unless a test asks for it, so local and CI runs behave alike; one new test per command (`test_standard_output_is_refused_in_github_actions`) sets it and asserts exit 2, empty stdout and the `--output FILE` message. The guard had no test before; disabling it makes the 3 new tests fail. Local results: the four affected classes 32 passed with and without `GITHUB_ACTIONS=true`; the three affected files 337 passed with it; fast tier 2,545 passed (22-23 s) with and without it. `src/` unchanged.
  - **CI verification (2026-10-16)**: commit `cd38ffe` pushed on user approval; [Tests #2](https://github.com/HarshAgarwal1102/ai-terraform-drift-detector/actions/runs/38914708232) **passed** (`ubuntu-24.04`, Python 3.12). Fast tier: all 2,545 selected tests passed (340 deselected), step runtime **48 s** (< 60 s, no warning). Full suite: **2,885 passed**, 0 failed, 0 skipped in 224.0 s; coverage gate passed, `src/drift_engine` **98.85%** (5,807 statements / 54 missed, 2,106 branches / 35 partial, identical to local); `src/ai_engine` 97.69% (report only, identical to local). Installation from `requirements.txt` plus `pip check` succeeded in both jobs (19 s, 13 s), and the in-suite closure checks (`ci/ai-`, `ci/azure-`, `ci/dev-constraints.txt`, installed versions equal to the pins) passed on the runner. The same push's Security Scan #34 and Terraform Auth & Validation #70 succeeded.
  - **Acceptance**: all five criteria and the validation are met: input categories (assessed, gap filled), < 60 s fast CI tier (48 s), tiers, coverage (gate unchanged, `src/ai_engine` measured, thresholds proposed), reproducibility (fresh pinned venvs on CPython 3.12/3.13 macOS arm64 and the CI runner, CPython 3.12 linux x86_64; no duplicate pins).
  - **Open for later (not part of 12.1's criteria)**: the per-package threshold proposal awaits user review; the 42 zizmor findings on the existing workflows need a separate approved workflow task (WF-1); CPython 3.14 is blocked only by the existing AI pin `tiktoken==0.11.0`; `load_drift_report` raises `UnicodeDecodeError` rather than `DriftReportError` (test-only helper); the plain-unittest path still has 25 pre-existing import failures.

#### Task 12.1A — Terraform Plan & Diagnostic Log Exposure Hardening
- **Status**: 🟢 COMPLETED (2026-10-14) — commit `6d1aa86` pushed to `main`; real sentinel check passed on auth-test run #68 (recorded 2026-10-13 as an early, separate security-hardening task; user decision, Task 12.1 design review)
- **Completed**: 2026-10-14
- **Started**: 2026-10-13
- **Objective**: Stop Terraform plan content and diagnostic output from reaching public workflow logs.
- **Dependencies**: none on Task 12.1. It needs its own design review, a separately approved implementation plan and a separately approved remediation plan for existing logs (Execution Rules 10 and 13; WF-1).
- **Scope**: the two known limitations recorded under Phase 12 above:
  - `terraform-auth-test.yml` printing the full plan (also gate E6 of the on-hold Phase 11 specification);
  - the Phase 5 diagnostic output (`plan.log` tail, `az account show`).
- **Files/Areas** (implementation approved as I1, 2026-10-13): `.github/workflows/terraform-auth-test.yml`, `.github/workflows/drift-detection.yml`, new `scripts/auth_test_plan.sh`, `scripts/generate_plan_json.sh`, new `tests/test_auth_test_workflow.py`, new `tests/test_generate_plan_json.py`, `tests/test_investigation_workflow.py`; notes in `README.md` and this plan.
- **Design Review (2026-10-13, user decisions)**:
  - In scope: P1 (auth-test plan output), P2 (auth-test `az account show`), P3 (drift-detection `az account show`), P4 (`plan.log` tail in Generate Plan Evidence), P5 (raw jq text in a `generate_plan_json.sh` failure reason) and P5b (value-free integrity messages, because the reason is printed again by Analyze Drift).
  - `terraform plan` stays in the auth-test; no `-lock-timeout` in this task; P6 (drift-detection `terraform init`/`validate` output) is a recorded residual and unchanged.
  - Fixed failure codes only; never raw Terraform, jq or `az` text. Audit evidence kept: step result, exit code, validated action counts. Plan JSON that cannot be validated or counted fails closed and never reports counts. Plan and diagnostic files stay runner-local; nothing is uploaded.
  - Counts (overlapping by design) and the action allowlist are documented in `scripts/auth_test_plan.sh`. Real Terraform output (the committed `tests/fixtures/plan_evidence` plans) backs `no-op`, `create`, `update`, `delete`, `["delete","create"]`, output `update`/`delete`, refresh-only drift and the exit-code rule; `importing` and `previous_address` are backed by synthetic fixtures only; `["create","delete"]`, `["forget"]`, data `["read"]` and output `create` are assumptions (hand-written plans). Forget-, import- or move-only plans fail closed if real Terraform exits 0 for them (residual).
- **Acceptance Criteria** (revised proposal, 2026-10-13):
  - [x] P1–P5 and P5b implemented as designed; P6 recorded as residual; no `-lock-timeout`, trigger, permission or GitHub setting change.
  - [x] Counts match the 10 committed real plans exactly; unknown action shapes, `errored` ≠ false, `complete` ≠ true, structural violations and exit-code/pending mismatches fail closed with no counts line.
  - [x] Plan exit 0 and 2 succeed with a validated counts line; exit 1 → `plan_failed`; other exits → `plan_unexpected_exit`; show failure → `show_failed`.
  - [x] A random sentinel planted in Terraform output, drift section and errors, `az` errors, jq stderr, malformed plan JSON and an inherited `SHELLOPTS=xtrace` never appears in stdout, stderr, the step summary, `GITHUB_OUTPUT` or the manifest's `failure_reason`.
  - [x] Every mutation check is caught; tests pass on local bash 3.2; the full constrained suite stays green with no existing test removed, skipped or weakened.
  - [x] Only the seven code/test paths are in the code commit (separately approved); the five pre-existing changed files are preserved.
  - [x] The real sentinel check passes (separately approved Azure probe tag, push and log download).
- **Validation** *(checked 2026-10-14 after the commit and the real sentinel check; evidence in the Completion Notes)*:
  - [x] E6 structural test: `terraform-auth-test.yml` writes the plan output to a runner-local file and prints only the exit code and change counts.
  - [x] Real sentinel check: a temporary probe-tag value is absent from the downloaded log of a push-triggered run. This requires a separately approved implementation and an approved, controlled workflow run.
  - [x] Phase 5 diagnostic outputs (`plan.log` tail, `az account show`) verified to no longer expose sensitive or unnecessary account or plan details. *(Verified by local executed-step tests of the committed workflow steps and scripts; the identical auth-check block passed live in auth-test run #68. A live `drift-detection.yml` run has not been inspected; that remains unverified.)*
- **Constraints**:
  - Recording this task changed nothing. The approved local implementation (I1) changes only the seven code/test paths above; no Azure or GitHub permission or setting, and no historical log, is changed. Staging, commit, push, the Azure probe tag and the real sentinel check each need separate approval.
  - Existing logs are handled only through the recorded classification, preservation and per-run deletion procedure (spec §12.1, R7, R10).
- **Completion Notes**:
  - **Local implementation (2026-10-13; later committed as `6d1aa86`)**:
    - `scripts/auth_test_plan.sh` (new, 100755, bash 3.2 compatible): `set +x`, `umask 077`, `TF_LOG*` unset, `TF_CLI_ARGS*` refused, a new `$RUNNER_TEMP/auth-test` directory; init, validate, `plan -detailed-exitcode -out` and `show -json` with all output in runner-local files; one jq pass validates and counts (each count parenthesized); prints only the three fixed lines (also to the step summary) or exactly one `::error::auth-test failed: failure_code=<code>` line; an EXIT trap turns any other termination into `internal_error`.
    - `terraform-auth-test.yml`: `terraform_wrapper: false`; the dev step runs the script; `Verify Azure OIDC Authentication` compares `az account show --query id|tenantId` (captured, stderr discarded) with `EXPECTED_SUBSCRIPTION_ID`/`EXPECTED_TENANT_ID` from the existing secrets and prints a fixed line or `auth_configuration_missing`/`auth_context_unavailable`/`auth_context_mismatch`. Triggers and permissions unchanged.
    - `drift-detection.yml`: the same check in `Verify Azure OIDC Authentication` (name and `id: auth` unchanged); the `plan.log` tail removed from Generate Plan Evidence.
    - `generate_plan_json.sh`: jq gate stderr goes to `plan.log`; the evaluation failure reason is fixed; integrity messages carry no plan values (header values written to `plan.log` only).
    - Tests: `tests/test_auth_test_workflow.py` 92, `tests/test_generate_plan_json.py` 8, `tests/test_investigation_workflow.py` +4 (P4; `FAKE_PLAN_SCRIPT` gained an optional `FIXTURE_PLAN_LOG`, existing assertions unchanged). Against the HEAD versions of the changed workflows and script, 26 of the new tests fail; with the change all pass. The HEAD run also showed the pre-fix leak: the Analyze Drift failure line printed a planted `format_version` value.
    - Mutation check (throwaway scratchpad copies, not committed): 17 of 17 caught (HEAD versions, `plan.log` tail restored, plan redirect removed, `az` output printed, show failure failing open, consistency check removed, raw jq text in the reason, wrapper back on, `set +x` removed in the script and in the auth step, jq precedence bug, allowlist removed, value in an integrity message, `az` stderr not discarded, jq stderr to stdout, counts line on failure, `-lock-timeout` added).
    - Full constrained suite (Python 3.13.12, venv with `-c ci/ai-constraints.txt -c ci/azure-constraints.txt`): **2,867 passed** (2,763 + 104 new), 0 failed, 0 skipped; coverage 98.85% (`src/drift_engine` only, gate 85%); 234.0 s.
    - `bash -n` (local bash 3.2) clean on both scripts and on all 41 workflow `run:` blocks; `git diff --check` clean. actionlint, ShellCheck and zizmor were not run (not installed; no download without approval).
    - Residuals: R1 P6 (drift-detection init/validate output); R2 forget/import/move-only exit codes unverified (fail closed); R3 zizmor findings not assessed; R4 historical logs (spec §12.1, separate); R5 `crash.log` on a Terraform panic stays in the runner checkout; R6 actionlint/zizmor not run; R7 Python parser messages still interpolate header fields, reachable only if the script accepts a plan the engine rejects (an engine run on a failed manifest reports the manifest's fixed reason, verified locally); R8 `azure/login` output not reviewed.
  - **Commit, push and live verification (2026-10-13/14, each step separately approved)**:
    - C1: commit `6d1aa86869348fa61819b51e7071fb1fd175e43a` (`fix: harden Terraform diagnostic log exposure`) with exactly the seven code/test paths (3 added, 4 modified; `scripts/auth_test_plan.sh` mode 100755); the five documentation files stayed uncommitted.
    - R1: probe tag `aitdd_drift_probe=task-3.6` added to `aitdd-dev-main-rg` (`rg_tag_drift_inject.sh --apply`, 2026-10-13 17:30:34Z) after a read-only check that the Azure CLI context was the project subscription.
    - R2: normal push to `origin/main` (fast-forward `488f42d..6d1aa86`, 17:32:48Z). It triggered auth-test run #68 (`38439530159`) and security-scan run #32 (`38439529852`); both succeeded, every auth-test step and all three security-scan jobs (TFLint, TruffleHog, Trivy config).
    - R3: the job log was obtained by a signed-in download outside this session (the anonymous API download was refused, HTTP 403) and inspected locally without printing raw content. All 10 criteria passed: the fixed `Azure OIDC context verified` line; `auth-test: terraform_version=1.14.7`, `auth-test: init=succeeded validate=succeeded` and `auth-test: plan_exit_code=2 add=0 change=1 destroy=0 replace=0 import=0 moved=0 forget=0 output_changes=0`; 0 occurrences of `aitdd_drift_probe`, `task-3.6`, `Refreshing state`, `Terraform will perform`, `/subscriptions/`, account-JSON keys, plan-change markers and Terraform error blocks. Identity: the full commit SHA and the run's time window (17:32:55–17:33:34Z); the archive's numeric name is not the run or job ID (unexplained).
    - R4: probe tag removed (`rg_tag_drift_revert.sh --apply`, 17:35:36Z); its absence and the unchanged managed tags (`environment=dev`, `managed_by=terraform`, `project=ai-terraform-drift-detector`) were verified independently (17:35:44Z).
    - E6 (on-hold Phase 11 spec): items (a) structural test, (b) executed-step test and (d) real sentinel check are met; (e) existing logs is open, so E6 as a whole stays open. `docs/remediation-safeguards.md` is not updated while Phase 11 is on hold.
    - Still open (not fixed by this task): the existing auth-test logs (spec §12.1, H1); no live `drift-detection.yml` run inspected for P3/P4; residuals R1–R8 above; the bootstrap and fmt steps of the auth-test still print Terraform's own output for the committed configuration (offline).

#### Task 12.2 — End-to-End Drift Scenario Test Matrix
- **Status**: 🟢 COMPLETED (2026-10-16) — 135-case matrix passes locally; its first `tests.yml` run follows the push
- **Completed**: 2026-10-16
- **Started**: 2026-10-16
- **Objective**: Implement scenario matrix testing: No Drift, Single Resource Drift, Multi-Resource Drift, Security Drift, Cost Drift, AI Unavailable, Azure API Failure.
- **Dependencies**: Task 12.1
- **Files/Areas**: `tests/integration/`
  - Implemented in `tests/integration/test_scenario_matrix.py` (new); notes in `README.md` and this plan. No product code, workflow, dependency or pin changed.
- **Acceptance Criteria**:
  - [x] Matrix tests verify graceful degradation (e.g., if LLM API is down, system still produces deterministic drift report).
- **Validation**:
  - [x] Run full scenario test matrix. *(2026-10-16: 135 passed in 7.8 s, also with `GITHUB_ACTIONS=true`; full suite 3,020 passed; see Completion Notes.)*
- **Implementation Notes**:
  - Resiliency verification across all failure modes.
- **Completion Notes**:
  - **Design**: every case runs the real stages in-process, chained as the workflows chain them: `drift-engine analyze` (internal + public report) → `investigate` (Azure Activity Log) → `ai-analysis` (deterministic report; optional LLM) → GitHub issue publication (`scripts/github_automation.py`), plus the cost path (real `scripts/sanitize_infracost.py` on the committed Infracost v0.10.46 sample → `ai-analysis --cost`) and the unmanaged path (`inventory` → `unmanaged-cost` → `ai-analysis --unmanaged`). Manifests carry a GitHub run binding (`github-123-1`) as in CI. The test helpers clear `GITHUB_ACTIONS` and every LLM variable, so local and CI runs behave alike. No network: Azure, GitHub and Retail Prices are the existing scripted fakes; `tests/conftest.py` blocks non-loopback connections. Module tier: `integration` (it runs a loopback server), so the `tests.yml` full job runs it and the fast tier is unchanged.
  - **Scenario rows (committed fixtures)**: No Drift `plan_evidence/in_sync` (0 drifted, INFO); Single Resource Drift `plan_evidence/external_drift` (1, LOW); Multi-Resource Drift `cost_config_plans/combined_security_cost_config` (2: NSG and storage account, CRITICAL; the only fixture with more than one drifted resource); Security Drift `security_plans/nsg_open_inbound` (1, CRITICAL, includes the prompt-injection description); Cost Drift `infracost/service_plan_sku_drift` (1, MEDIUM; 106.58 → 119.72, +13.14 USD/month). Healthy assertions: analyze outcome, `has_drift`, drifted count and highest severity; Azure queried only when there is drift; AI report written and verified by the CLI, LLM `not_attempted`, resources equal to the drifted set; exactly one issue per drifted resource (security issue body carries CRITICAL); the whole pipeline byte-deterministic on a second run.
  - **AI Unavailable** (30 cases: 5 rows × 6 outages; real OpenAI client, `AI_LLM_MAX_RETRIES=0`, 1 s timeout): refused connection, HTTP 500, 503, 429, timeout and a reply that is not the JSON envelope. Exit 0; report written and verified; LLM status `failed` (`invalid_output` for the bad reply; `not_attempted` without drift); the deterministic sections (`report_version`, `provenance`, `summary`, `investigation`, `resources`, `remediation`, `cost`, `unmanaged`) identical to the no-LLM report; the LLM-routed `analysis` sections empty with the fixed reason `LLM call failed (<ExceptionType>)`; drift reports byte-identical; neither the API key nor a marker in the provider's error body appears in any output.
  - **Azure API Failure** (87 cases): Activity Log, all 13 `QUERY_FAILURE_CODES` × 5 rows: with drift, `investigate` exits 1 with `INVESTIGATION FAILED [evidence_failed]` / "Drift detection results are unaffected", public investigation `failed`; the AI report still writes with investigation `failed` and identical summary, remediation, cost, analysis and per-resource drift facts; issue publication sends exactly the same requests; without drift Azure is never queried. Resource Manager inventory, all 14 `SCOPE_FAILURE_CODES`: inventory `failed` / `listing_failed` (exit 1), unmanaged cost `inventory_not_complete`, AI report records it, drift sections unchanged. Retail Prices, all 8 `API_FAILURES`: unmanaged cost exits 1 with the same code, AI report records it, drift sections unchanged. Drift reports byte-identical in every case.
  - **Infracost unavailable** (5 cases): no Infracost result → cost `rejected` / `cost_input_incomplete` with an explicit message; summary, remediation, investigation and drift facts unchanged.
  - **Mutation check** (scratch copies, not committed): 7 of 7 injected product defects caught: LLM failure raising instead of degrading; investigation failure exiting 0; the AI CLI rejecting a failed investigation; a missing Infracost result crashing it; provider error text leaking into the report (caught only after the error-body marker and exact-reason checks were added); a stage touching the drift report; collapsed pricing failure codes.
  - **Results (2026-10-16, macOS arm64, CPython 3.13.12, pinned `requirements.txt` venv)**: matrix 135 passed in 7.8 s (8.2 s with `GITHUB_ACTIONS=true`); full suite **3,020 passed** (2,885 + 135), 0 failed, 0 skipped in 252.6 s; coverage gate passed, `src/drift_engine` 98.85%, `src/ai_engine` 97.69% (unchanged: the matrix exercises paths the unit tests already cover); fast tier unchanged (2,545); `--strict-markers` collection 3,020; dummy credentials follow the repository's existing `sk-test-not-real` form (no secret-shaped strings).
  - **Not covered (outside this task)**: a GitHub API outage during issue publication (covered by Task 8.1/8.3 unit tests, not repeated here); the `ai` extra not installed (an explicit usage error by design, not a degradation); live Azure, which the matrix never touches.
  - **CI (2026-10-16, follow-up, not an acceptance criterion)**: commit `dd84aaa` pushed on user approval; `tests.yml` run #4 succeeded (fast tier 45 s; full suite step 364 s and the coverage gate step passed), with Security Scan #36 and Terraform Auth & Validation #72 also successful. The per-test count in the log was not read: logs need a signed-in GitHub session.

#### Task 12.3 — Least Privilege RBAC & Secret Hardening Audit
- **Status**: 🟢 COMPLETED (2026-10-16) — acceptance criteria met; the CI identity verified against the documented least-privilege design
- **Completed**: 2026-10-16
- **Started**: 2026-10-16
- **Objective**: Conduct security audit of Azure Service Principals, GitHub Secrets, OIDC permissions, and API key handling.
- **Dependencies**: Task 12.2, Task 9.3
- **Dependency note**: Task 9.3 added 2026-10-03 (Phase 9 re-evaluation): this task's validation runs TruffleHog, which Task 9.3 integrates.
- **Files/Areas**: `docs/security-audit.md`. The detailed audit report is kept private (owner decision, 2026-10-17) and is not in the repository; this record is the public summary.
- **Acceptance Criteria**:
  - [x] Audit confirms no hardcoded secrets exist in repository. *(TruffleHog: 0 findings on the full history and the working tree; manual checks.)*
  - [x] OIDC claims restricted to specific GitHub repo and branch. *(One federated credential with the exact immutable-ID subject for `refs/heads/main`; default subject template.)*
- **Validation**:
  - [x] Run TruffleHog + manual security checklist. *(2026-10-16; 14-item checklist in the private report.)*
- **Implementation Notes**:
  - Production-grade security audit.
- **Completion Notes**:
  - **Method (2026-10-16, read-only)**:
    - Azure and Entra ID through the existing Azure CLI session: app, service principal, federated credentials, credential metadata, role assignments (`--all --include-inherited`), Graph memberships and grants.
    - GitHub through its anonymous public REST API.
    - Workflows and code statically.
    - Output was redacted; no secret value was read. The audit changed nothing in Azure, Entra ID, GitHub settings, secrets or workflows.
  - **TruffleHog 3.97.9**: the official release, checksum-verified (the release checksum list contains the repository's pinned Linux SHA-256). `scripts/run_trufflehog.sh` on the full history: **0 findings** (78 commits, 4 refs). The working tree: **0 findings**.
  - **Verified end state (2026-10-16, re-checked 2026-10-17)**:
    - **OIDC**: exactly one federated credential (`github-main-branch`, issuer `https://token.actions.githubusercontent.com`, audience `api://AzureADTokenExchange`, subject `repo:HarshAgarwal1102@117922914/ai-terraform-drift-detector@1400148970:ref:refs/heads/main`, no claims expression). It matches the repository's IDs and GitHub's default immutable subject template.
    - **RBAC**: exactly the 2 documented assignments (`Reader` on the subscription; `Storage Blob Data Contributor` on the `tfstate` container). Confirmed by the Azure CLI and the Resource Manager API; no inherited assignments.
    - **Credentials and permissions**: no client secret or certificate on the app or the service principal; no API permissions, grants or memberships.
  - **Passed**: no hardcoded credentials; tenant, client and object IDs absent from the repository; no Terraform state ever committed; no `pull_request_target`; API keys environment-only, scoped and never logged.
  - **Remediated during the task**: the audit found deviations from the documented design on the CI identity: additional role assignments and a client secret, added outside this repository. They were removed in Azure outside this audit, and two read-only re-audits (2026-10-16) verified the removal.
  - **Follow-up**: the remaining hardening recommendations are tracked in the private report. Those that change existing workflows need a separately approved task (WF-1).
---

### PHASE 13 — Professional Dashboard
**Status**: 🟡 WORK IN PROGRESS (started 2026-10-17 on user instruction; Tasks 13.1 and 13.2 🟢 2026-10-17; Task 13.3 🟡 since 2026-10-17; Task 13.4 🟡 since 2026-10-18, added by the design amendment below; Task 13.5 🟡 since 2026-10-18). Tasks 13.1–13.5 are merged to `main` (PRs #10–#14) and released in the Level 1 baseline `level1-v1.0.0` (2026-10-18).

> **Level 1 baseline release (2026-10-18)**: the user tested the current implementation on their own system and confirmed that fetching GitHub artifacts from the dashboard and viewing the local reports work as expected (user-confirmed; not re-run as a logged acceptance test). The Phase 13 work as implemented (Tasks 13.1–13.5) was merged to `main` (PR #13, merge `6ae77f2`; follow-up UI changes in PR #14, merge `daa95f8`) and tagged `level1-v1.0.0` (annotated tag `fe07743` → commit `daa95f8`; CI on `main` passed) as the stable **Level 1** baseline. A more user-friendly Level 2 is developed in a separate repository (see the Master Project Overview); it changes nothing in the Level 1 implementation. Task statuses below are unchanged; closing Tasks 13.3–13.5 is the user's decision.

Phase 13 builds a web-based management dashboard consuming live platform APIs and data to visualize drift status, security risks, cost impacts, and remediation workflows.

> **Required feature: caller recorded by Azure for every detected drift (user, 2026-10-10, finalized the same day)**: this is a required dashboard feature, not an optional enhancement. It was documented only until Phase 13 started (2026-10-17); it is implemented by Tasks 13.1–13.3.
> - **Display**: every detected drift row/card shows a field labelled **`Caller recorded by Azure`**:
>   - **human user**: the recorded caller's available name;
>   - **service principal or managed identity**: the identity's available name or identifier, as Azure recorded it;
>   - **`Unknown`**: only when the caller cannot be determined reliably, the relevant operation cannot be uniquely correlated, the required Activity Log record is unavailable, or the lookup fails.
>
>   The dashboard never fabricates a name, substitutes an unrelated identity, or guesses who performed a change.
> - **Lookup**: the dashboard backend (`src/dashboard_api/`) retrieves the caller on demand from Azure Activity Log. It correlates the record with the drift's identified change using the existing Phase 9B matching logic, reused from `src/drift_engine/who.py` and its supporting modules. It never invokes the local-only `drift-engine who` command.
> - **Exposure**:
>   - The frontend gets caller information only through the backend. Browser code holds no Azure credentials and never queries Azure.
>   - Caller identity is returned only to authenticated and authorized dashboard users.
> - **No persistence**: caller names and identifiers are never stored in the application database, reports, GitHub Actions artifacts or ordinary application logs. Public artifacts and general drift reports stay free of personal caller identity.
> - **Meaning**: the field shows the identity Azure recorded. It does not prove which physical person performed the action. Not storing it in this application does not remove it from Azure, whose Activity Log keeps its own records under its configured retention policy.
> - **Phase 9B unchanged**: these stay exactly as they are:
>   - G8's 10-minute Activity Log settling margin;
>   - G11's `caller_identity: withheld` rule for public artifacts;
>   - G12's local-only `drift-engine who` command.

> **Design amendment: on-demand GitHub fetch from the dashboard (user-approved 2026-10-18; implemented by Task 13.4)**
> - **Why**: the dashboard reads only the local data directory `.artifacts/dashboard`; new GitHub Actions runs (the daily scheduled drift detection and its AI analysis) appear only after `scripts/fetch_dashboard_data.py` runs, which today needs a manual `scripts/run_dashboard.sh --fetch`.
> - **Existing Refresh button: unchanged.** It reloads data from `.artifacts/dashboard` only, never sends a GitHub request and never runs the fetch. The 60-second automatic refresh stays local-only.
> - **New button `Check GitHub for new runs`**, separate from Refresh. On click:
>   1. the frontend calls an authenticated dashboard API endpoint;
>   2. the API launches the existing fetch (`scripts/fetch_dashboard_data.py`) as a background job, so the dashboard stays responsive;
>   3. the existing fetch implementation is reused with its current behavior; no second GitHub-fetch implementation is created;
>   4. the fetch checks the eligible GitHub Actions artifacts, skips artifacts already present locally, downloads new eligible artifacts and updates `github_issues.json`, all as it does today;
>   5. artifacts are saved to the existing `.artifacts/dashboard` directory;
>   6. after completion the dashboard invalidates its data cache and reloads the local reports;
>   7. the dashboard shows an understandable status: running, new artifacts downloaded, no new artifacts, partial success, or failure.
> - **Security and reliability**:
>   - the GitHub token is never exposed to browser JavaScript, command-line arguments, logs or report files;
>   - only authenticated users with a dedicated `data_refresher` role may start a fetch;
>   - one fetch at a time (lock), a cooldown between fetches, and an overall timeout;
>   - the existing API `GET` endpoints stay read-only;
>   - downloaded reports are validated before the dashboard reads them; interrupted downloads and temporary staging folders are handled safely;
>   - when GitHub is unavailable, the dashboard keeps showing the locally saved reports.
> - **Out of scope**: the button never triggers a Terraform plan or apply or a new drift scan, and no periodic GitHub fetching is added.
> - **Amends Task 13.1's approved design**: the dashboard API was read-only and never wrote to the data directory. Its `GET` endpoints stay read-only; the fetch endpoint is the single, separately authorized write path, and it makes the server contact GitHub (only through the existing fetch script). Tasks 13.1–13.3 records stay as they are.

#### Task 13.1 — Dashboard Data API & State Engine
- **Status**: 🟢 COMPLETED (2026-10-17; design approved by the user 2026-10-17)
- **Started**: 2026-10-17
- **Objective**: Build lightweight Python backend API (FastAPI) to serve live drift reports, history, and status metrics, including the on-demand `Caller recorded by Azure` value for every detected drift (Phase 13 required feature).
- **Dependencies**: Tasks 4.6, 8.3, 9A.1, 9B.5 (investigation and AI report v2 artifacts), 9B.6 (real-Azure proof of the Phase 9B WHO correlation the lookup reuses; added 2026-10-10)
- **Files/Areas**: `src/dashboard_api/` (reuses matching logic from `src/drift_engine/who.py`, `activity_logs.py` and `investigation.py`; the `drift-engine who` command keeps its behaviour)
- **Acceptance Criteria**:
  - [x] Endpoints for `/api/summary`, `/api/drifts`, `/api/reports/{id}`, `/api/remediations`.
  - [x] Consumes real `drift_report.json` and AI report artifacts. *(Tested on the unchanged public artifacts of Task 9B.6 runs #38, #39 and #40.)*
  - [x] For every detected drift, the backend returns the `Caller recorded by Azure` value defined in the Phase 13 required feature: the recorded name or identifier, or `Unknown`. It is retrieved on demand from Azure Activity Log and correlated with the drift's identified change. *(Verified with a fake Activity Log source through the shared `who.lookup_operation`; the real-Azure check is Task 13.3's validation.)*
  - [x] Caller identity is returned only to authenticated and authorized users and is never persisted in the database, reports or logs.
- **Validation**:
  - [x] `pytest tests/test_dashboard_api.py` passes. *(Local, 2026-10-17; not yet run in `tests.yml`.)*
- **Implementation Notes**:
  - Data layer for dynamic dashboard UI.
  - **Correlation**:
    - The drift's identified change is its decisive operation in the public investigation / AI report v2.
    - Its record is found as `who.py` finds it: `activity_logs.collect_window` over the operation's start/end ± 1 s, grouping by `investigation.group_operations`, and exactly one group equal in operation name, start, end, outcome, relations, caller type and client application.
    - `Unknown` applies when: there is no decisive operation; there is no match or more than one; the caller is missing or inconsistent; the record is past the 90-day retention; or the query fails.
    - The investigation already applied G8, so the dashboard adds no shorter settling margin.
    - If reuse needs a shared helper extracted from `who.py`, the `drift-engine who` behaviour and its tests stay unchanged.
  - **Logging and caching**: logs carry fixed codes only. Responses carrying caller identity are sent with `Cache-Control: no-store`.
  - **Tests cover**:
    - a human name, and a service principal and a managed identity name or identifier;
    - each `Unknown` case;
    - unauthenticated and unauthorized requests;
    - no caller identity in logs, the database or reports (using a sentinel caller in fixtures).
  - **Design review first**: sign-in, authorization, and the backend's read-only Azure credential. Any new Azure resource, role or GitHub setting needs user approval (Execution Rules 12 and 13).
- **Completion Notes**:
  - **Implementation (2026-10-17, committed on branch `phase-13-dashboard`, not pushed)**: `src/dashboard_api/` (`store.py`, `callers.py`, `auth.py`, `views.py`, `app.py`, `cli.py`); `docs/dashboard.md`; `tests/test_dashboard_api.py`; fixtures `tests/fixtures/dashboard/real_9b6/` (the 9B.6 public artifacts of runs #38, #39 and #40, copied unchanged; 0 findings from the public leak scan and the identifier scan).
    - **Data**: the API indexes downloaded workflow artifacts in any layout (for example `gh run download`) on every request. It attaches the AI report, public investigation and cost run to a drift report only when they are bound to it by run id and canonical SHA-256 (`investigation_public.load_public` and `check_binding` for the investigation). Ambiguous or conflicting artifacts are not used and are reported as fixed codes. It writes nothing and has no database.
    - **Caller**: from the decisive operation of the bound public investigation, via `who.lookup_operation`, which is `who.py`'s former `_lookup` made shared (the only change to `who.py`; `drift-engine who` behaviour and `tests/test_who.py` are unchanged). It returns the recorded value or `Unknown` with a fixed status code. Lookups are refused in GitHub Actions (G12).
    - **Design for review (no new Azure resource, role or GitHub setting)**: one bearer token per user, stored only as a SHA-256 digest in a local users file that neither group nor others can write (otherwise every request fails closed with 503). Roles: `viewer` (all endpoints) and `caller_reader` (`include_caller=true`, otherwise 403). The server binds only to loopback. The caller lookup uses the operator's own read-only `az login` (`AzureCliCredential`, as `drift-engine who` does). All responses are sent with `Cache-Control: no-store`; the OpenAPI docs are disabled; validation errors never echo input.
    - **Dependencies**: new `dashboard` extra (`fastapi`, `uvicorn`) and `dashboard-api` entry point; `ci/dashboard-constraints.txt` pins the six packages not pinned elsewhere; `requirements.txt` applies it, so `tests.yml` installs it with no workflow change. `tests/test_tests_workflow.py` and `tests/test_ai_cli.py` were updated for the new constraints file and entry point. The drift and AI workflows do not install the extra.
  - **Validation (2026-10-17, CPython 3.13, pinned `requirements.txt`)**: `tests/test_dashboard_api.py` 19 passed (47 subtests): human, service principal and managed identity callers; all 12 `Unknown` cases; unauthenticated, unauthorized and unusable users-file requests; sentinel callers absent from logs, files and every non-caller response. Full suite: 3039 passed, 1 failed (`test_entry_points_and_core_dependencies` expected the old entry points; fixed, then the affected files passed: 101 passed). Fast tier after the fix: 2565 passed. Coverage: `src/dashboard_api` 78–100% per module, all measured source 98%. A live `dashboard-api` on `127.0.0.1` over the real fixtures returned 401 without a token, 403 for `include_caller` as a viewer and 200 with `no-store` for the maintainer; `--host 0.0.0.0` was refused. gitleaks 8.30.1: no leaks in the new files (TruffleHog is not installed locally; `security-scan.yml` runs it on push).
  - **Design review (2026-10-17)**: the user approved the design: hashed bearer-token users file, `viewer` and `caller_reader` roles, loopback-only server, the user's own read-only `az login`. No Azure resource, role or GitHub setting was added.
  - **Not part of this task**: the real-Azure caller check (Task 13.3).
  - **CI (2026-10-17, commit `b6aaa4f` on branch `phase-13-dashboard`, both runs manually dispatched on the branch because these workflows only trigger on `main`)**: `tests.yml` run #6 (`38995577278`) succeeded: fast tier 47 s, full suite 3047 passed in 336.92 s with no skips (`tests/test_dashboard_api.py` and all 7 `tests/test_dashboard_ui.py` tests, including the `node --test` component tests, passed on the runner), `src/drift_engine` coverage gate passed. `security-scan.yml` run #38 (`38995607123`) succeeded: TFLint, TruffleHog and Trivy config jobs all passed.

#### Task 13.2 — UI Component Development & Visual Analytics
- **Status**: 🟢 COMPLETED (2026-10-17; committed on branch `phase-13-dashboard`; merged to `main` through PR #10)
- **Started**: 2026-10-17
- **Objective**: Build modern, responsive dashboard UI displaying executive overview metrics, drift breakdown charts, and active risk feeds.
- **Dependencies**: Task 13.1
- **Files/Areas**: `dashboard/`
- **Acceptance Criteria**:
  - [x] Overview Cards: Total Resources, Active Drifts, Security Exposure, Monthly Cost Impact.
  - [x] Interactive tables filtering drifts by severity, resource type, and environment. *(Plus a run filter: latest per environment or any run of the history.)*
  - [x] Detailed modal showing AI analysis, HCL diff, and remediation status. *(The diff is a Terraform-style expected/actual diff built from the drift report's attribute changes.)*
  - [x] Every detected drift row/card shows its resource, changed property, expected and actual value, operation time, and the `Caller recorded by Azure` field (recorded name or identifier, or `Unknown`), obtained only through the backend.
- **Validation**:
  - [x] UI renders cleanly and dynamically updates from API data. *(Built-in browser, 2026-10-17, over the real 9B.6 fixtures.)*
- **Implementation Notes**:
  - Modern web interface with dark mode and visual feedback.
  - Browser code holds no Azure credentials, never calls Azure, and does not write caller data to browser storage.
  - Component tests render a human name, a service principal or managed identity name or identifier, and `Unknown`.
- **Completion Notes**:
  - **Implementation (2026-10-17, committed on branch `phase-13-dashboard`, not pushed)**: `dashboard/` (`index.html`, `styles.css`, `render.js`: pure escaped render functions, `app.js`: sign-in, loading and events, `render.test.js`: component tests); `src/dashboard_api/app.py` serves exactly those four browser files at `/` from the same origin and adds a strict Content-Security-Policy to every response (`default-src 'none'`; same-origin scripts, styles and `connect-src`; no inline code; `frame-ancestors 'none'`); `tests/test_dashboard_ui.py`; `docs/dashboard.md` (UI section). No new dependency, no build step, no CDN.
    - Sign-in with a dashboard token held in memory only. All data comes from `/api/*`; a viewer without `caller_reader` gets the rows without callers and sees "Not available (needs the caller_reader role)". Refresh on demand and every 60 s (can be switched off). Light and dark themes.
  - **Validation (2026-10-17)**:
    - Component tests (`node --test`, Node 20.7): 10 passed, 0 failed: human name, service principal and managed identity identifiers, every `Unknown` reason, the hidden-caller state, the drift row fields, HTML escaping of crafted values, the three filters and the run selector, overview cards (no invented cost) and the detail modal.
    - `tests/test_dashboard_ui.py` 7 passed: no browser storage, cookies or external hosts (Azure included) in the browser code; no inline script, style or handler; one `fetch`, to `/api/*` only; the UI served with the CSP, unknown paths 404 and `/api/*` still 401 without a token.
    - Built-in browser on a loopback `dashboard-api` over the real fixtures with a session test token: the overview cards, severity breakdown and run history rendered; selecting run `github-38105671846-1` loaded its drift row (`tags.drift_test`, `(absent)` → `"primary-r2"`, operation time 2026-10-11 02:27:00 UTC, `Microsoft.Resources/tags/write`, caller `Unknown`: no local Terraform state configured); the modal showed the diff, the AI narrative and both remediation options (`pending`, not allowed, `manual_after_approval`). No console errors (so no CSP violations); browser storage and cookies empty; light theme and a 375 px viewport without horizontal page scroll; the server log shows only same-origin requests and no token. The session test token, users file and launch configuration were removed afterwards.
    - Full suite: 3047 passed (4018 subtests); fast tier: 2571 passed. gitleaks 8.30.1: no leaks in `dashboard/`, `src/dashboard_api/` or the new tests.
  - **Not verified**: a real caller name in the browser (needs the user's `az login` and a local Terraform state: Task 13.3).
  - **CI (2026-10-17, commit `b6aaa4f` on branch `phase-13-dashboard`, both runs manually dispatched on the branch because these workflows only trigger on `main`)**: `tests.yml` run #6 (`38995577278`) succeeded: fast tier 47 s, full suite 3047 passed in 336.92 s with no skips (`tests/test_dashboard_api.py` and all 7 `tests/test_dashboard_ui.py` tests, including the `node --test` component tests, passed on the runner), `src/drift_engine` coverage gate passed. `security-scan.yml` run #38 (`38995607123`) succeeded: TFLint, TruffleHog and Trivy config jobs all passed.

#### Task 13.3 — Live Data Integration & Real-Time Status Monitoring
- **Status**: 🟡 WORK IN PROGRESS (🔵 STARTED 2026-10-17)
- **Started**: 2026-10-17
- **Objective**: Connect web dashboard frontend to backend API to ensure 100% real project data (zero mock data in final build).
- **Dependencies**: Task 13.2
- **Files/Areas**: `dashboard/`, `docs/dashboard.md`
- **Acceptance Criteria**:
  - [ ] Dashboard displays live drift reports generated from actual Azure scan runs.
  - [ ] Visual indicators reflect active PR and resolution states.
  - [ ] For a real detected drift, the dashboard shows the identity Azure recorded, matching what `drift-engine who` shows locally for the same operation. Public artifacts and general drift reports still contain no caller identity (`caller_identity: withheld`).
  - [ ] `docs/dashboard.md` explains the `Caller recorded by Azure` field: it is Azure's recorded caller, not proof of which physical person acted; what `Unknown` means; and that the application does not store it.
- **Validation**:
  - [ ] End-to-end user navigation test on active data, including the real-data caller check.
- **Implementation Notes**:
  - Real-time visibility into infrastructure health.
  - Real-data caller check:
    - an authorized user sees the recorded identity;
    - unauthenticated and unauthorized requests are refused;
    - the backend's logs and database contain no caller identity.

    The real Azure change and any login are user actions (Execution Rule 10).
- **Completion Notes**:
  - **Gap analysis (2026-10-17)** against the acceptance criteria, before this task's changes:
    - Live drift reports: the API indexed any artifact directory, but nothing fetched real artifacts into it (`gh` is not installed locally; artifact downloads need an authenticated GitHub API call).
    - PR and resolution states: not shown. Drift issues exist (Tasks 8.1 and 8.3: label `drift-detected`, first-line marker with fp(environment, address), closed with `state_reason: completed` when resolved). **Remediation PRs do not exist**: Task 8.2 is 🔴 BLOCKED, superseded by Phase 11, which is on hold.
    - Real caller check: implemented in Task 13.1 but never run against a real drift (needs a live Azure change and the user's `az login`).
    - `docs/dashboard.md` already explained the `Caller recorded by Azure` field (Task 13.1).
  - **Implemented (2026-10-17, local, not committed)**:
    - `scripts/fetch_dashboard_data.py` (new; standard library; reuses `fetch_prior_drift_reports.GitHub` and the `github_automation` marker and label): downloads the non-expired `drift-report`, `drift-investigation`, `ai-analysis-report` and `infracost-report` artifacts of `main` runs from the last `--days` into the data directory (expected JSON file only, atomic 0600 writes, never refetched), and writes a `github_issues.json` snapshot of the drift issues (number, URL, state, close reason, timestamps, marker fields; no title, body or user). `GH_TOKEN` is read-only, sent only to the API and never printed; `--every` repeats the fetch.
    - `src/dashboard_api/issues.py` (new): strict snapshot loader; fp(environment, address) equal to `github_automation.fingerprint` (tested); each drift row gets `issue` (its open issue, else its latest closed one, else `none_found`; `no_snapshot` without a snapshot) and `remediation_pr: not_enabled` with the Task 8.2/Phase 11 reason. `/api/summary` lists every drift issue with its resource.
    - UI: a GitHub issue column, issue and remediation-PR state in the detail modal, and a "GitHub drift issues" panel with the snapshot time. Only `https://github.com/<owner>/<repo>/issues/<n>` URLs become links.
    - `docs/dashboard.md`: live-data section.
  - **Validation so far (2026-10-17, local)**: `tests/test_dashboard_live.py` 14 passed (artifact filtering: expired, non-`main`, too old, too large, foreign URL, nested file; immutability; snapshot fields; token never printed; fingerprint equality; snapshot validation; open-then-latest-closed selection; API rows). Component tests 13 passed. Full suite 3061 passed; fast tier 2585 passed. gitleaks: no leaks in the new files.
  - **Unmanaged resources (2026-10-17, user request, local, not committed)**: the dashboard now shows the Task 10.4 data, which it did not before.
    - `scripts/fetch_dashboard_data.py` also fetches `unmanaged-inventory-<id>/unmanaged_inventory.json`.
    - `src/dashboard_api/store.py` binds an inventory to its run (`binding.run_id`, `binding.drift_report_sha256` = canonical SHA-256 of the public report), validated with `unmanaged_public.load_inventory` (strict model and public leak scan); invalid ones are skipped (`unmanaged_inventory_invalid`).
    - `src/dashboard_api/views.py` and the new `/api/unmanaged` endpoint (also in `/api/reports/{id}` and per environment in `/api/summary`): listing from the bound artifact, else from a complete AI report v4 `unmanaged` section bound to the run; amounts only from that AI section, validated with `unmanaged_cost.UnmanagedCost`, and only when its inventory is identical to the listing (canonical SHA-256 and the cost's `inventory_sha256`); otherwise a status (`no_ai_report`, `not_in_ai_report`, `not_available`, `rejected`, `inventory_mismatch`, `ai_section_invalid`) and no amount.
    - UI: an "Unmanaged resources" panel (inventory outcome, counts, failed scopes, resources, per-resource estimate and total, "not drift").
    - **Bug fixed in passing (Task 13.1 code)**: the Monthly Cost Impact card read `cost_impact`, but AI report v3/v4 publish the validated estimate under `cost` (`status`, `cost_delta`); a complete estimate would have shown "Not available". It now reads `cost` (report v2's `cost` has no `status` and still shows no amount). Not caught earlier because the real fixtures are report v2.
    - Validation: `tests/test_dashboard_unmanaged.py` 7 passed, with documents built by the real Task 10.4 pipeline (inventory over scripted ARM responses, cost over the real Retail Prices samples, AI report v4 from the analysis graph without an LLM): listing and amounts equal to the AI report's (total 17.1055 USD), inventory without AI report, AI report alone, a different inventory (no amounts), unbound and leaking inventories, the cost-key fix, the fetch name. Component tests 15 passed. Full suite 3072 passed; fast tier 2595 passed; gitleaks: no leaks. Built-in browser on the real 9B.6 fixtures (which predate Task 10.4): the panel shows "No unmanaged-resource inventory for this run"; no console errors besides the expected pre-sign-in 401.
    - Not yet verified on a real Task 10.4 run: it needs the fetched artifacts (same user action as below).
  - **Review and real-data validation (2026-10-17, second pass)**:
    - **Diff review fixes**: (1) the Monthly Cost Impact card read the drift cost from any AI report and without validation; it now reads it only from report v3/v4, validates the embedded `cost_delta` with `drift_engine.cost.CostDelta` and requires its binding to name this run and drift report (`cost_delta_invalid`, `cost_delta_mismatch`); report v2 and unknown versions never show an amount (`not_available`, `unsupported_report_version`). (2) Unmanaged amounts come only from report v4, and the unmanaged cost's own binding must also name this run and drift report (in addition to the identical inventory SHA-256). (3) A drift's GitHub issue was "open, else latest closed" for its fingerprint, which showed a later episode's issue for older runs; it is now the earliest issue with that fingerprint still open when the run finished (the issues job creates it after the run; a later in-sync run closes it). Unmanaged data never enters the managed drift counts (tested: 6 unmanaged resources, `active_drifts` 0).
    - **Login error (`Could not load data (http_404)`)**: re-verified with real requests. `dashboard-api` returns 200 with a valid token and 401 `unauthenticated` with a wrong one for `/api/summary`, `/api/unmanaged` and `/api/drifts?include_caller=true`; a missing data directory returns 503 `data_unavailable` (not a route error); a static file server of `dashboard/` returns an HTML 404 for any token, which the UI now reports as `api_not_found` before sign-in (fixed and regression-tested earlier on 2026-10-17). Root cause: the page was not served by `dashboard-api`.
    - **Real artifacts available (GitHub public API, artifact metadata only, 2026-10-17)**: 141 non-expired artifacts on `main`. Six runs carry a real `unmanaged-inventory` artifact with a matching drift report, investigation, Infracost report and AI report: `38140497702` (the user-approved Task 10.3/10.4 dispatch #44, 1247 bytes) and the scheduled runs `38223728098`, `38372176795`, `38525717476`, `38695031801`, `38862516764` (about 630 bytes each). Downloading them needs an authenticated token; none is available in this session (no `gh`).
    - **Real GitHub issue states (public issues API, parsed by `fetch_dashboard_data.issue_entry`)**: 6 drift issues (#1, #5–#9), all `closed`/`completed`, all for `module.resource_group.azurerm_resource_group.this["main"]`. With the real 9B.6 artifacts in `.artifacts/task-13.3-validation/` (ignored), the dashboard shows run `github-38105671846-1` (R2) and `github-38109121618-1` (R3) with issue #9 (created 2026-10-11T02:47:22Z by R2's issues job, closed `completed` at 04:24:20Z after the in-sync run R4 finished at 04:23:49Z), the summary 0 open and 6 closed with every resource resolved, `remediation_pr: not_enabled`, and no data problems. The authenticated `fetch_issues` HTTP path itself has not run against GitHub yet.
    - **Caller check without a new Azure change**: the 9B.6 R2 drift is a real operation (`Microsoft.Resources/tags/write`, 2026-10-11T02:27:00Z) inside the 90-day Activity Log retention, and the 9B.6 local Terraform state maps its address; so the dashboard caller can be compared with `drift-engine who` for the same operation with only the user's read-only `az login`.
    - **Tests (2026-10-17)**: dashboard and `who` tests 72 passed; component tests 15 passed; full suite 3074 passed; fast tier 2597 passed; gitleaks: no leaks in the changed files.
  - **Live validation (2026-10-17, after the user's `az login` and `fetch_dashboard_data.py` run)**:
    - **Fetched data**: `.artifacts/dashboard` (ignored, 0700) holds 77 artifact directories from GitHub: 19 drift reports, 17 investigations, 17 AI reports, 18 Infracost reports and 6 unmanaged inventories (runs from 2026-10-10 to 2026-10-16); every file 0600; no data problems when indexed. `github_issues.json` is missing: the issue step failed after the artifacts were written (most likely the token lacks "Issues: read"; the script's output then said only `reason=listing_failed`). The script now names the step and HTTP status (`dashboard_fetch=partial step=issues reason=listing_failed detail=http_403 …`), tested.
    - **Issue snapshot now present (evidence recorded 2026-10-18)**: user-confirmed dashboard fetch around 12:25 IST on 2026-10-18 (the user clicked **Check GitHub for new runs**; see Task 13.4) plus the observed local file `.artifacts/dashboard/github_issues.json`, written at about 12:25:02 IST (`fetched_at` 2026-10-18T06:54:56Z) and holding 6 issues. The issue states in it were not independently checked against GitHub, and neither its completeness nor its freshness has been confirmed.
    - **Caller recorded by Azure (real Activity Log, user's read-only `az login`, 9B.6 local Terraform state)**: for run `github-38105671846-1` (R2, `op-1` `Microsoft.Resources/tags/write`, 2026-10-11T02:27:00.310062Z) a fresh `drift-engine who` matched one caller, and the dashboard (`/api/drifts` and `/api/reports/{id}` with `include_caller=true`) returned the same value (`matched`, `user`); compared in code, never printed. The other real drifts agree too: `38023838144`, `38036342826`, `38058888141` match `who`; `38057933359` is `Unknown` (`no_investigation`: no investigation artifact) and `38067518562`, `38109121618` are `Unknown` (`no_decisive_operation`: verdict `ambiguous`).
    - **Security on real data**: viewer `include_caller` 403 `caller_access_denied`; no or wrong token 401 `unauthenticated` with `WWW-Authenticate: Bearer`; without `include_caller` no caller field; the caller is absent from `/api/summary`, `/api/unmanaged`, `/api/remediations` and `/api/reports/{id}`, from every log record (34 captured in-process; server log has request lines only, no `@`), from the data directory (unchanged by the lookups) and from the R2 public artifacts; `Cache-Control: no-store`, the CSP and `X-Frame-Options: DENY` on the live server. The local `who` evidence files, test tokens and users files were deleted afterwards.
    - **Unmanaged inventories (all 6 real runs)**: each artifact bound to its run and drift report; every AI report v4 `unmanaged.status: complete` and priced exactly that inventory. The dashboard's counts, scopes, resources (ref, type, name, resource group, location, category), per-resource estimates and totals equal the files for every run. Run `38140497702` (Task 10.4 dispatch #44): 5 resources not managed by Terraform (a portal VM `FrontEndVM`, its OS disk, NIC, public IP and health extension), estimated 44.8455 USD/month (`$44.85/month`; 3 estimated, 2 no direct charge), inventory complete, one complete scope, no data-quality warnings. The five scheduled runs: 0 unmanaged resources, `$0.00/month`, complete.
    - **Fixed from real data**: (1) the unmanaged panel appended `/month` to displays that already end in `/month` (`unmanaged_cost.format_usd`), showing `$44.85/month/month`; (2) the Monthly Cost Impact card said "Not available — no validated cost estimate" for the real v3/v4 in-sync runs, whose validated estimate states "Confirmed drift has no cost line"; it now shows "No drift cost" (never `$0`), from `confirmed_drift.with_cost == 0` of the validated `cost_delta`. Real drift cost card per run: v2 runs `not_available`, v3/v4 runs `complete` with no confirmed-drift line.
    - **Browser (built-in, `dashboard-api` on loopback over `.artifacts/dashboard`)**: 19 runs; latest run `github-38862516764-1` in sync, cards 5 resources, 0 drifts, 0 exposure, "No drift cost"; run `github-38140497702-1` unmanaged panel as above, no doubled `/month`, 0 drifts for that run; run R2 row with `tags.drift_test`, operation time 2026-10-11 02:27:00 UTC and a caller whose SHA-256 equals `who`'s (checked in the page; no screenshot of it); viewer sign-in shows "Not available (needs the caller_reader role)"; browser storage and cookies empty; issue cells show "No issue data" (no snapshot).
    - **Tests (2026-10-17)**: dashboard and `who` tests 74 passed; component tests 15 passed; full suite 3076 passed; fast tier 2599 passed; gitleaks: no leaks in the changed files.
  - **Run history usability (2026-10-17, user request, local, not committed)**: the run history now scrolls inside a fixed-height box (320 px, sticky header, one line per run) instead of growing with the number of runs, and a search box filters it by run id or GitHub run number, finish date, environment or highest severity (every word must match; "N of M run(s)"). On wide screens the history gets two thirds of its row. No pagination: the API already caps the history at 100 runs. Validation: component tests 16 passed (new search test: run number, full id, date, multiple words, no match, escaping); `tests/test_dashboard_ui.py` 11 passed; built-in browser on the 19 fetched real runs: 318 px box with 726 px of rows scrolls; searching `38105671846` shows `1 of 19 run(s)` with the full row `2026-10-11 02:36:54 UTC dev github-38105671846-1 1 LOW` and no clipped column.
  - **Previous runs in Active drifts (2026-10-17, user report, local, not committed)**: "clicking previous run data displays no result". Root cause (reproduced on the 19 fetched real runs): the API returned the right rows for every run (drift rows = each run's `drifted_resources`), but (1) run-history rows had no click handler, so clicking a run did nothing; (2) the 10 runs after 2026-10-11 03:40Z are in sync, and the empty table said "No drift matches the filters", which read as a filter or loading problem; (3) the unmanaged-cost run `github-38140497702-1` (0 drifts, 5 unmanaged resources, `$44.85/month`) was reachable only through the Run dropdown. Fixed: history rows open their run on click or Enter (Run filter, drifts, remediations and unmanaged panel follow; the row is highlighted); a "Showing run … (time, environment)" line; context-specific empty messages ("Run … found no drift: all N managed resource(s) were in sync" vs "No drift matches the filters (N hidden)"); an Unmanaged column in the history (count and cost, "—" without an inventory; `/api/summary` history entries now carry `resources_total` and an `unmanaged` summary); a viewer's refused caller request is not repeated for the rest of the session. Validation: component tests 18 passed; `tests/test_dashboard_ui.py` 11 passed; built-in browser on the real runs: clicking `github-38105671846-1` shows its drift (`tags.drift_test`, (absent) → "primary-r2"), Enter on `github-38140497702-1` shows "found no drift: all 5 managed resource(s) were in sync" and its 5 unmanaged resources with `$44.85/month`, clicking `github-38067518562-1` shows its drift; after a reload one 401 (pre-sign-in check) and one 403 (first caller request of a viewer), none after.
  - **One-command launcher (2026-10-17, user request, local, not committed)**: `scripts/run_dashboard.sh` (and `scripts/Start Dashboard.command` for a double-click in Finder) prepares and starts the dashboard: uses `.venv` (created with Python 3.13/3.12/3.11 if missing) and installs `.[azure,dashboard]` with the pinned constraints only when the imports are missing (the user's existing `.venv`, Python 3.14, had the `dashboard-api` command but no FastAPI, so `dashboard-api` alone would fail); creates `.artifacts/dashboard-local/users.json` (0700 directory, 0600 file, SHA-256 digest only, roles `viewer` and `caller_reader`) and prints the sign-in token once (`--new-token` rotates and revokes it); with `--fetch` or an empty data directory asks for a read-only GitHub token with hidden input, passes it only to `fetch_dashboard_data.py` and unsets it; enables the caller lookup with `--terraform-json` (or a saved state file); refuses a busy port; starts `dashboard-api` on 127.0.0.1 and opens the browser. Validation: `tests/test_run_dashboard.py` 6 passed (syntax and executable bits, digest-only users file and token shown once, rotation revokes the old token, caller-lookup option, bad options, help); the pinned install works on Python 3.14; a launch from a Python 3.14 venv without FastAPI installed the dependencies, and a real start on the 19 fetched runs served the UI (200), refused an unauthenticated request (401), returned all 19 runs with the token, and refused a second launch on the same port.
  - **Caller identity completion (2026-10-17, user request)**:
    - **Gaps found and fixed** (`src/dashboard_api/callers.py`; `who.py` unchanged): (1) a missing or rejected `az login` and a missing Activity Log read permission were all reported as the generic `query_failed`; the lookup now passes through a recording wrapper that keeps only the fixed `SourceError` codes and reports `azure_sign_in_unavailable` (`credential_unavailable`, `authentication_failed`) or `azure_access_denied` (`authorization_failed`); (2) the dashboard did not itself require the investigation's evidence to have passed the G8 settling margin; it now returns `activity_log_not_settled` without any query when `completeness.settled` is not true or the resource's reason is `evidence_not_settled`. UI reasons added; the row's caller carries the "identity Azure recorded, not proof of which person" note as a tooltip (the details panel already stated it). Tests: `tests/test_dashboard_api.py` new cases (credential unavailable, 401, 403, unsettled evidence with no query).
    - **Local prerequisite**: the user's launcher folder `.artifacts/dashboard-local/` had no Terraform state, so the user's dashboard showed `Unknown (no local Terraform state configured)`; the verified 9B.6 local state (`terraform show -json`, maps every managed address) was copied there (0600, ignored) so `scripts/run_dashboard.sh` enables the lookup automatically.
    - **Real end-to-end (user's `az login`, real Activity Log, fetched real artifacts)**: `caller_reader` result equals a fresh `drift-engine who` for all four real drifts with a single identified change (`github-38105671846-1` R2, `github-38023838144-1`, `github-38036342826-1`, `github-38058888141-1`; compared in code; no caller printed); `no-store` on every response. Real `Unknown` cases: empty `AZURE_CONFIG_DIR` with the real `az` CLI → `azure_sign_in_unavailable`; no Terraform JSON → `resource_ids_unavailable`; address not in the state → `address_unknown`; clock +120 days → `retention_exceeded`; ambiguous real verdict (`github-38109121618-1`) → `no_decisive_operation`; run without an investigation artifact (`github-38057933359-1`) → `no_investigation`; `GITHUB_ACTIONS=true` → `local_only`.
    - **Role isolation and privacy (real data)**: viewer `include_caller` 403 `caller_access_denied`; no or wrong token 401; without `include_caller` no caller field; no caller in `/api/summary`, `/api/unmanaged`, `/api/remediations`, `/api/reports/{id}`, in any of 71 captured log records, in the server log, in the data directory or the launcher folder (unchanged), in any fetched public artifact (drift reports, investigations with `caller_identity: withheld`, AI reports, inventories), or in the titles, bodies and comments of the 6 real GitHub drift issues. The temporary `who` evidence, tokens and users files were deleted afterwards.
    - **Browser (started through `scripts/run_dashboard.sh`, which reported "Caller lookup enabled")**: as `caller_reader`, R2's row and details panel show status `matched`, type User, a caller whose SHA-256 equals `who`'s (checked in the page, no screenshot), the tooltip and the disclaimer; Control A shows `Unknown — no single identified change`, run `38057933359` `Unknown — no bound investigation`; as viewer the field reads "Not available (needs the caller_reader role)"; browser storage and cookies empty.
    - **Tests**: dashboard, launcher and `who` tests 82 passed; component tests 18 passed; full suite 3084 passed; fast tier 2601 passed; gitleaks: no leaks in the changed files.
  - **Caller missing for `github-38109121618-1` (2026-10-17, user report, local, not committed)**: "`drift-engine who` shows the caller, the dashboard does not".
    - **Traced (same inputs on both paths)**: the dashboard's investigation for the run is byte-identical to the fixture and to the 13.3 validation copy (binding `run_id` `github-38109121618-1`, drift report SHA-256 `64ba2671…`); the launcher's `.artifacts/dashboard-local/terraform-state.json` is byte-identical to the 9B.6 `who` state; the launcher's user has `caller_reader`; the UI requests `include_caller=true`; the investigation is `settled` (`not_before` 03:50:55Z) and the operations (2026-10-11) are inside the 90-day retention. No exception or Azure error was involved.
    - **Root cause**: the run's verdict is `ambiguous` (`multiple_capable_operations`: `op-1` R2's tag write at 02:27:00.310062Z, `op-2` R3's at 03:34:30.341314Z; no decisive operation). `drift-engine who` looks up every operation and matched one caller for each (two different callers, compared by SHA-256 only). `callers.recorded_caller` looked up only the decisive operation and returned `Unknown` (`no_decisive_operation`) before any lookup, so the dashboard never asked Azure. It was not a settling, retention, mapping, role, state-file, swallowed-error or rendering problem.
    - **Fix** (`src/dashboard_api/callers.py`, `dashboard/render.js`, `dashboard/styles.css`; `who.py` unchanged): without a decisive operation the drift keeps `value: Unknown` / `no_decisive_operation` (it has no single caller, G3), and the field adds `operations`: each of the resource's public operations with its own `value`, `caller_type` and `status`, found by the same `who.lookup_operation` with the same checks (G12 local-only, Terraform state, address, ARM ID, `caller_status`, sign-in/access codes). The Active drifts row and the details panel show "No single identified change; caller recorded for each operation" with one line per operation (`op-N`, start time, caller and type, or `Unknown` and its reason). Decisive-verdict drifts are unchanged.
    - **Real validation (user's `az login`, real Activity Log, real `dashboard-api` on 127.0.0.1 with the launcher's data and state)**: a fresh `drift-engine who --public --report --terraform` for `github-38109121618-1` matched `op-1` and `op-2` (same caller hashes as the 2026-10-11 evidence); `/api/reports/{id}` and `/api/drifts?report_id=` with `include_caller=true` return both operations `matched` with the same caller as `who` for each (SHA-256 compared, no caller printed). The other ambiguous run, `github-38067518562-1`, also matches a fresh `who` per operation. The decisive drifts (`github-38105671846-1`, `github-38023838144-1`, `github-38036342826-1`, `github-38058888141-1`) still return `matched` with unchanged values; `github-38057933359-1` stays `no_investigation`. Viewer: 403 `caller_access_denied`, no caller field without `include_caller`. Neither of R3's two recorded callers appears in the three server logs; no real caller appears in any of the 23 modified or untracked working-tree files.
    - **Browser (built-in browser, `caller_reader`, run `github-38109121618-1` selected)**: the Active drifts row and the details panel each list `op-1 · 2026-10-11 02:27:00 UTC` and `op-2 · 2026-10-11 03:34:30 UTC`, both `matched`, type User, with caller hashes equal to `who`'s (checked in the page, no screenshot); the disclaimer is present; storage and cookies empty. As viewer: "Not available (needs the caller_reader role)", no operations.
    - **Tests**: `tests/test_dashboard_api.py` 24 passed (new `AmbiguousVerdictCallerTests` on the real R3 artifacts with Activity Log rows reproducing both operations to the microsecond: per-operation callers equal `who.run_who` on the same inputs; `no_match`, `retention_exceeded`, `resource_ids_unavailable`, `address_unknown`, `azure_sign_in_unavailable` and `local_only` stay `Unknown` per operation, with no Azure query for `local_only`; viewer refused with no query); against the pre-fix behaviour the new tests fail (7 errors). Component tests 19 passed (new: per-operation rendering in the row and the details panel, escaping, an unavailable operation keeps its reason). Full suite (fresh CPython 3.13 venv, pinned `requirements.txt`) **3087 passed**, 0 failed, 0 skipped; `src/drift_engine` coverage 98.85%. gitleaks 8.30.1: no findings in the 23 modified or untracked files; the 2 history findings are older false positives (a sentinel test key in `tests/test_infracost.py`, prose in `PROJECT_PLAN.md` since `17eff5f`). TruffleHog is not installed locally.
  - **Open before 🟢**: ~~the GitHub issue snapshot of the user's authenticated fetch~~ (now present: user-confirmed dashboard fetch around 12:25 IST on 2026-10-18 (the user clicked **Check GitHub for new runs**; see Task 13.4) plus the observed local file `.artifacts/dashboard/github_issues.json`, written at about 12:25:02 IST (`fetched_at` 2026-10-18T06:54:56Z) and holding 6 issues. The issue states in it were not independently checked against GitHub, and neither its completeness nor its freshness has been confirmed), and the browser check of the issue column and panel on it (**still open**). Real issue states were already validated through the public API on the 9B.6 artifacts (issue #9 for R2 and R3, 6 closed `completed`), but not yet from the fetched data in the browser. Needed then: the user re-runs the fetch with a token that has "Issues: read"; the 12:25 IST dashboard fetch has since produced the snapshot. Still needed: the browser check of the issue column and the "GitHub drift issues" panel on this snapshot. Remediation PR state stays `not_enabled` (Task 8.2 blocked), as documented.
#### Task 13.4 — On-Demand GitHub Fetch from the Dashboard
- **Status**: 🟡 WORK IN PROGRESS (🔵 STARTED 2026-10-18 on the user's instruction "Start implementation")
- **Started**: 2026-10-18
- **Objective**: Add a `Check GitHub for new runs` button that, for an authorized user, runs the existing GitHub artifact fetch as a secure background job and then reloads the dashboard, without changing the existing Refresh behavior (Phase 13 design amendment, 2026-10-18).
- **Dependencies**: Tasks 13.1 and 13.2 (🟢); the fetch script and data path of Task 13.3 (`scripts/fetch_dashboard_data.py`, `.artifacts/dashboard`, `scripts/run_dashboard.sh`).
- **Files/Areas**: `src/dashboard_api/` (`app.py`, `auth.py`, `cli.py`, `store.py`, a new fetch-job module), `scripts/fetch_dashboard_data.py` (minimal changes only: token input and staging cleanup), `scripts/run_dashboard.sh`, `dashboard/` (`index.html`, `app.js`, `render.js`, `styles.css`), tests (`tests/test_dashboard_api.py`, `tests/test_dashboard_ui.py`, `tests/test_dashboard_live.py`, `tests/test_run_dashboard.py`, a new `tests/test_dashboard_fetch.py`, `dashboard/*.test.js`), `docs/dashboard.md`.
- **Acceptance Criteria**:
  - [x] **Refresh unchanged**: the existing Refresh button and the 60-second automatic refresh reload only `.artifacts/dashboard`, send no GitHub request and never start the fetch (tested).
  - [x] **Button and endpoint**: a separate `Check GitHub for new runs` button calls an authenticated write endpoint (`POST`), which starts the fetch as a background job and returns at once; a read-only status endpoint reports the job's state. All existing `GET` endpoints stay read-only.
  - [x] **Reuse**: the job runs the existing `scripts/fetch_dashboard_data.py`; no second GitHub-fetch implementation exists. Its current behavior is preserved: only eligible artifacts, artifacts already present skipped, new eligible artifacts downloaded into `.artifacts/dashboard`, `github_issues.json` updated as today.
  - [x] **Authorization**: only authenticated users with the dedicated `data_refresher` role can start a fetch (401 without sign-in, 403 without the role); the existing `viewer` and `caller_reader` boundaries are unchanged.
  - [x] **One at a time, cooldown, timeout**: a second start while a fetch runs is refused; a start within the cooldown is refused; a fetch exceeding the overall timeout is stopped and reported as failed.
  - [x] **Token protection**: the GitHub token never reaches browser JavaScript, any command-line argument, any log, any response or any report or artifact file (tested with a sentinel token). The server holds it in memory only, received from the launcher without an environment variable or file.
  - [x] **Safe execution**: the subprocess uses a fixed argument list (no shell), a fixed script path and repository, and a minimal environment (no `GITHUB_API_URL`); no request input reaches the command; only the script's fixed result line is parsed, and its stderr is never returned or logged.
  - [x] **Status shown**: the UI shows running, new artifacts downloaded (with counts), no new artifacts, partial success (e.g. issue state not updated) or failure, in plain words; after completion the data cache is invalidated and the local reports reload.
  - [x] **Validation and interrupted downloads**: downloaded reports are validated before the dashboard reads them; temporary staging folders from an interrupted fetch are never read as data and are cleaned up; a partial fetch keeps only complete artifacts.
  - [x] **Offline behavior**: when GitHub is unavailable or the token is missing, the button reports the failure and the dashboard keeps showing the locally saved reports.
  - [x] **Out of scope respected**: no Terraform plan or apply, no new drift scan and no periodic GitHub fetching is triggered.
  - [x] `docs/dashboard.md` documents the button, the role, the token handling, the limits and the statuses.
- **Validation**:
  - [x] New and updated tests pass with a fake fetch script and no network (authorization, lock, cooldown, timeout, status parsing, token sentinel, minimal environment, Refresh never fetching, staging cleanup, store ignoring staging folders), plus the full suite, the fast tier and the secret scan.
  - [x] Browser check on a loopback `dashboard-api`: Refresh stays local; the button shows each status; data reloads after a successful fetch.
  - [x] One real fetch against GitHub from the button, only with the user's explicit approval and the user's read-only token. **Satisfied by user-confirmed historical real fetches (2026-10-18): the user personally clicked **Check GitHub for new runs** in the dashboard around 11:50 and 12:25 IST; both worked and GitHub artifact data (runs such as `39105665374`) was downloaded into the local dashboard data directory. Recorded from the user's statement, not as a logged acceptance test: no status response, screenshot, token-verification result or download count was captured, and the token's permissions were not recorded.
- **Implementation Notes**:
  - Planned token path: the launcher asks for the read-only token (hidden input) and hands it to `dashboard-api` over a pipe file descriptor; the server passes it to the fetch script on standard input. Never `os.environ` (the caller lookup starts the `az` CLI, which would inherit it), never an argument, never a file.
  - Planned status endpoint: readable by any `viewer`; it carries fixed codes, counts and timestamps only.
  - Store hardening: skip hidden folders (`.fetch-*` staging) when indexing; the fetch script removes stale `.fetch-*` and `.issues-*` leftovers at start; validate drift reports with the existing public report model, not just their shape.
  - The browser request cache (`dashboard/loader.js`) is invalidated after a successful fetch.
  - **Decisions (2026-10-18)**: the user said "Start implementation" without choosing among the open options, so the recommended defaults apply: a 2-minute cooldown and a 10-minute overall timeout; `scripts/run_dashboard.sh` asks for the GitHub token only with an opt-in flag (`--enable-github-fetch`); the launcher's `local-admin` user receives `data_refresher`.
- **Completion Notes**:
  - **Implementation (2026-10-18, local, not committed)**:
    - `src/dashboard_api/github_fetch.py` (new): `GitHubFetcher` runs the existing `scripts/fetch_dashboard_data.py` as one background thread + subprocess: fixed argument list (`--token-stdin --repository <fixed> --data-dir <absolute>`), no shell, the server's own Python, minimal environment (`PATH`, `LANG`, `PYTHONDONTWRITEBYTECODE`; no `GITHUB_API_URL`, no `GH_TOKEN`), token only on standard input, stderr discarded, new session killed as a group on timeout; a lock (`fetch_in_progress` 409), a 120 s cooldown (`fetch_cooldown` 429 + `Retry-After`), a 600 s timeout (`failed`/`timeout`); refused in GitHub Actions (`local_only`) and without a token (`fetch_unavailable` 503). Only the fixed result line is parsed (`ok` → `new_artifacts` / `no_new_artifacts`, `partial` with `issues_*` code, `failed` with `artifacts_*` code; anything else `unexpected_output`, exit 2 `usage`). Logs: fixed `dashboard_fetch_started` / `dashboard_fetch_finished` events with status, code and counts.
    - `src/dashboard_api/app.py`: `POST /api/fetch` (needs `data_refresher`; 403 `fetch_access_denied`; accepts no parameters) and read-only `GET /api/fetch/status` (any `viewer`; adds `allowed`); every other `GET` unchanged. `auth.py`: role `data_refresher`. `cli.py`: `--github-token-fd N` (N ≥ 3) reads the token once from a pipe and closes it; never an argument or environment variable.
    - `src/dashboard_api/store.py`: hidden folders (`.fetch-*` staging) are never indexed; drift reports must validate as `report_public.PublicDriftReport` (all 22 real reports, fetched and fixtures, pass; 19 live runs index in about 50 ms).
    - `scripts/fetch_dashboard_data.py`: `--token-stdin` (single printable line, at most 1024 characters, else usage error); removes `.fetch-*` / `.issues-*` leftovers older than one hour at the start of every fetch (links removed, never followed) and reports `stale_staging_removed`. Existing fetch behavior otherwise unchanged.
    - `scripts/run_dashboard.sh`: opt-in `--enable-github-fetch` asks once for the token (hidden, kept in an unexported shell variable), gives `local-admin` the `data_refresher` role (new or existing users file, same token digest), and starts `dashboard-api --github-token-fd 3 3< <(printf …)` (builtin `printf`: the token is in no process's arguments); `GH_TOKEN`/`GITHUB_TOKEN` are unset before the server starts. The one-off `--fetch` now also passes the token on standard input instead of an environment variable.
    - UI (`dashboard/index.html`, `app.js`, `render.js`, `styles.css`): `Check GitHub for new runs` keycap next to Refresh, shown only when `/api/fetch/status` says `allowed` (disabled with "not enabled" when the server has no token); click → `POST /api/fetch`, uncached status polling every 2 s, then `load(true)` (request cache invalidated, every panel reloaded); plain-language status line (running, downloaded N, no new runs, partial, failed with reason, cooldown with seconds). Refresh and auto-refresh code paths untouched.
    - `docs/dashboard.md`: Quick start pointer, a "Check GitHub for new runs" section, the two endpoints and the role.
  - **Validation (2026-10-18)**:
    - New `tests/test_dashboard_fetch.py` 23 passed (fake fetch script, no network): 401/403/202 by role; status endpoint per role; arguments fixed and unaffected by query parameters and a JSON body; token arrived on stdin (SHA-256 match) and is absent from arguments, environment, responses, logs, `repr` and every data file, with `GITHUB_API_URL` and `GH_TOKEN` set in the server environment and not passed on; 409 while running, 429 with `Retry-After` during the cooldown; a 60 s fake fetch killed after the 1 s test timeout (process gone); stderr containing a fake trace and token never returned or logged; 503 without a token and `local_only` in GitHub Actions; `GET` endpoints never start a fetch or write; a failed fetch keeps the saved reports served; 12 result-line cases including injected text; token descriptor read once, closed and validated; CLI refuses descriptors below 3 and empty tokens.
    - `tests/test_dashboard_live.py` +3 (token on stdin wins over `GH_TOKEN` and is validated; stale staging removed, fresh kept, a link removed without following; the fetch reports `stale_staging_removed`), `tests/test_dashboard_api.py` +2 (hidden staging folders never indexed; non-public or extra-field drift reports rejected as `report_invalid`), `tests/test_run_dashboard.py` +4 (real launcher start with a stand-in `dashboard-api`: arguments `--port N --github-token-fd 3`, token received on descriptor 3, absent from the server environment even with `GH_TOKEN`/`GITHUB_TOKEN` set beforehand, absent from output and files; no token without the flag; an existing users file gains `data_refresher` with the same sign-in token; empty token refused), `tests/test_dashboard_ui.py` updated (uncached requests and the single `POST`), `dashboard/app.test.js` +4 and `render.test.js` +1 (button hidden without the role; Refresh never fetches; start, poll, reload with the summary requested again; refusals explained; not-enabled state; sign-out stops polling).
    - Full suite 3122 passed (4026 subtests); fast tier 2612 passed; component and controller tests 36 passed; coverage of `github_fetch.py` 96%. gitleaks: no leaks in the changed files (two test sentinels first shaped like GitHub tokens were replaced by plainly fake values so secret scanners stay quiet).
    - Built-in browser on a loopback `dashboard-api` over the 19 fetched runs with a fake fetch script (no GitHub access): the button appears for `data_refresher` and is hidden for a viewer; a click shows "Checking GitHub for new runs…" with the button disabled and busy, then "No new runs on GitHub (…)" and a reload of all panels; a second click "Checked recently: try again in 23 s."; Refresh sent no `/api/fetch` request (server log); the fake token never appears in the server log; browser storage empty.
  - **Final review and robustness fixes (2026-10-18, user-approved, local, not committed)**: a read-only review found no critical defect; the user approved these fixes (no design change):
    1. **Worker never stuck `running`** (`github_fetch.py`): `_run` wraps the job in a catch-all; any unexpected error ends it as `failed`/`internal_error` (the process is stopped, the exception text is not logged), and the final state is always written in `finally`.
    2. **Shutdown and timeout** (`github_fetch.py`, `app.py`, `scripts/fetch_dashboard_data.py`): the app's lifespan calls `GitHubFetcher.shutdown()` when the dashboard stops (refuses new jobs: `unavailable_reason: shutting_down`; stops a running fetch; state `failed`/`shutdown`). Stopping is SIGTERM to the fetch's process group, then SIGKILL after 5 s (also used for the 10-minute timeout, before only SIGKILL). The script handles SIGTERM by raising `SystemExit(143)`, and its artifact and issue-snapshot writers now remove their own staging on any exception (before only on `OSError`). Limitation: if the dashboard itself is SIGKILLed, a running fetch is not stopped (it ends by itself; writes stay atomic; stale staging is removed after an hour).
    3. **Proxy and certificates**: the fetch's minimal environment now also passes `HTTPS_PROXY`/`https_proxy`, `NO_PROXY`/`no_proxy`, `SSL_CERT_FILE`, `SSL_CERT_DIR` when the server has them (single-line values only); `HTTP_PROXY`, `ALL_PROXY`, `GITHUB_API_URL`, `GH_TOKEN` and everything else stay excluded; the token still goes only to the fixed API URL.
    4. **Unavailable causes**: `/api/fetch/status` adds `unavailable_reason` (`not_enabled`, `local_only`, `no_data_dir`, `fetch_script_missing`, `shutting_down`; fixed codes, never a path); the UI shows a specific message for each (only `not_enabled` points at `--enable-github-fetch`); a 503 refusal re-reads the status to show the reason.
    5. **Bounded polling and terminal states** (`dashboard/app.js`, `render.js`): polls every 2 s; after a failed poll the delay doubles (4, 8, 16, capped at 30 s); after 5 consecutive failures it stops with "Lost contact with the dashboard server…"; it stops watching after 11 minutes ("still running after 11 minutes; stopped watching"); a successful poll resets the backoff; the cooldown message clears itself when `Retry-After` ends; new failure texts for `shutdown` and `internal_error`.
    6. **Manual `--token-stdin`**: when standard input is a terminal the script reads the token with `getpass` (no echo); piped input (dashboard, launcher) is unchanged.
    - **Tests (2026-10-18, after the fixes)**: `node --test dashboard/` → tests 39, pass 39, fail 0 (new: backoff sequence 4000/8000/16000/30000 then stop; backoff reset and the 11-minute watch limit; self-clearing cooldown with `Retry-After: 37`; reason message after a 503; every unavailable reason and the new failure and notice texts). `python -m pytest -p no:cacheprovider --strict-markers -q tests/test_dashboard_fetch.py tests/test_dashboard_live.py tests/test_dashboard_api.py tests/test_dashboard_ui.py tests/test_dashboard_unmanaged.py tests/test_run_dashboard.py tests/test_who.py` → 128 passed, 73 subtests passed (new: worker error → `internal_error`, never `running`, exception text not logged; dashboard shutdown sends SIGTERM, the fake fetch records it, the process is gone, new starts refused; a fetch ignoring SIGTERM is killed after a 0.5 s grace; the timeout sends SIGTERM first; only the six network variables pass through; every unavailable reason as a fixed code without paths; an interrupted artifact write and issue snapshot leave no staging; `main` installs the SIGTERM handler and the handler exits 143; terminal input read with `getpass`). Full suite `python -m pytest -p no:cacheprovider --strict-markers -q --cov=src/drift_engine --cov=src/ai_engine --cov=src/dashboard_api --cov-report=term --cov-fail-under=0 tests/` → exit 0, 3132 passed, 4026 subtests passed (`github_fetch.py` coverage 90%). Fast tier `python -m pytest -p no:cacheprovider --strict-markers -q -m "not integration and not mutation" tests/` → 2616 passed. `gitleaks dir <path> --no-banner --redact` on every changed path → no leaks found. No real GitHub fetch, token, Terraform or Azure command was used.
  - **Real fetch (user-confirmed, 2026-10-18)**: user-confirmed historical real fetches (2026-10-18): the user personally clicked **Check GitHub for new runs** in the dashboard around 11:50 and 12:25 IST; both worked and GitHub artifact data (runs such as `39105665374`) was downloaded into the local dashboard data directory. Recorded from the user's statement, not as a logged acceptance test: no status response, screenshot, token-verification result or download count was captured. The local evidence matches: artifact directories written 11:50–11:52 and 12:25:00–12:25:01 IST, and `github_issues.json` written at 12:25:02 IST (`fetched_at` 06:54:56Z, 6 issues), with no staging left behind (see Task 13.5, acceptance review).
  - **Open before 🟢**: none of the listed criteria remain open. The status stays 🟡 until the user decides to close Task 13.4.

#### Task 13.5 — Dashboard-Native GitHub Authentication and Fetch Status Window
- **Status**: 🟡 WORK IN PROGRESS (🔵 STARTED 2026-10-18 on the user's instruction; implemented and tested; merged to `main` in PR #13 (`d340763`) with follow-up UI changes in PR #14 (`e6dbfc4`); open items below)
- **Started**: 2026-10-18
- **Objective**: Let the user connect, verify and replace a GitHub personal access token from the dashboard itself (no startup flag), explain token and permission failures precisely, and show GitHub fetch progress and results in a separate, dismissible status window, without changing the local-first design or Task 13.4's protections.
- **Dependencies**: Task 13.4 (🟡; its fetch job, endpoints and protections are reused).
- **Files/Areas**: `src/dashboard_api/github_fetch.py`, `app.py`, `cli.py`; `scripts/fetch_dashboard_data.py`; `scripts/run_dashboard.sh`; `dashboard/index.html`, `app.js`, `render.js`, `styles.css`; tests `tests/test_dashboard_fetch.py`, `tests/test_dashboard_live.py`, `tests/test_dashboard_ui.py`, `tests/test_run_dashboard.py`, `dashboard/app.test.js`, `dashboard/render.test.js`; `docs/dashboard.md`.
- **Acceptance Criteria**:
  - [x] **Normal startup**: `scripts/run_dashboard.sh` with no flag starts a fully usable dashboard without any GitHub token; the launcher always gives `local-admin` the `data_refresher` role (an older users file is migrated, sign-in token unchanged). Tested (`test_plain_startup_*`).
  - [x] **Connection action**: without a token the toolbar shows **Connect GitHub** and the status line says GitHub is not connected; **Check GitHub for new runs** then opens the connection dialog. Tested (`app.test.js`).
  - [x] **Two credentials kept apart**: the dialog states that the GitHub personal access token is not the dashboard sign-in token; the sign-in token is only ever sent as the dashboard's bearer header, the GitHub token only in the connect body. Tested.
  - [x] **Verification before use**: `POST /api/github/connect` runs the existing script with `--verify-only` (three read-only GETs: repository, `actions/artifacts?per_page=1`, `issues?...&per_page=1`); only an accepted token is kept; a rejected one is discarded and an earlier working one stays. Tested with a fake script and with the real script against a loopback fake GitHub.
  - [x] **Precise errors**: `invalid_token` (401), `insufficient_permissions` (403, with `need=actions|issues`), `repository_not_accessible` (404), `rate_limited` (429, or 403 with `X-RateLimit-Remaining: 0` / `Retry-After`), `network_error`, `api_error` (other status, kept). A permission or repository problem is never called an invalid token. The same categories and HTTP status are kept in the fetch status (`category`, `http_status`, `need`). Tested.
  - [x] **Token security**: never in browser storage, cookies, URLs, arguments, environment variables, responses, logs, exception text or files (sentinel tests over responses, captured logs, recorded subprocess arguments and environments, `repr`); held in server memory only; sent only to the fixed GitHub API through the script's stdin; the browser field is emptied before the request and on sign-out. Not persisted (decision below).
  - [x] **Replacement without restart**: a corrected token after a failed verification, and after a fetch that GitHub refused (`connection.last_error`), works without restarting. Tested.
  - [x] **Endpoint protection**: the connect/disconnect endpoints need authentication and `data_refresher`; all three state-changing endpoints refuse a cross-origin `Origin`; connect accepts only `application/json`; one verification at a time (409) and at least 2 s between verifications (429 + `Retry-After`); no token change while a fetch runs (409). Tested.
  - [x] **Status window**: **Check GitHub for new runs** opens a non-modal **GitHub fetch status** window with connection state, status (Idle/Running/Completed/Completed with a warning/Failed), start time, elapsed time, new and skipped counts, truthful stages (`connecting`, then the script's `dashboard_stage=listing|downloading|issues` markers, then the client's "Refreshing dashboard data"; no percentage), sanitized errors with category and HTTP status, **Retry** and **Replace GitHub token**. Tested (`app.test.js`, `render.test.js`, stage test with the server).
  - [x] **Dismiss and reopen**: hiding the window only hides it (no cancel request, polling continues, the dashboard stays usable); **Fetch status** reopens it while running and after completion or failure. Tested.
  - [x] **Local-first preserved**: Refresh and auto-refresh unchanged (Task 13.4 tests still pass); success reloads the local index; failure leaves every report in place (tested with the real script and a 401: the data folder is unchanged); no Terraform, scan or workflow run is triggered; one fetch at a time, the 2-minute cooldown and 10-minute timeout unchanged.
  - [x] **`--enable-github-fetch` decision documented**: kept as a deprecated alias (prints a deprecation note; preloads the token over a pipe as before, shown as "not verified yet").
  - [x] `docs/dashboard.md` documents startup, connecting and replacing a token, permissions, session-only storage, the status window, troubleshooting, offline behavior and Refresh versus GitHub.
- **Validation**:
  - [x] Automated tests (no network, no real token), 2026-10-18: `node --test dashboard/` → 49 pass, 0 fail. `python -m pytest -p no:cacheprovider --strict-markers -q tests/test_dashboard_fetch.py tests/test_dashboard_live.py tests/test_dashboard_api.py tests/test_dashboard_ui.py tests/test_dashboard_unmanaged.py tests/test_run_dashboard.py tests/test_who.py` → 178 passed, 10 skipped (the `ai` extra is not installed in the local `.venv`; unrelated), 73 subtests passed. `github_fetch.py` coverage 92%. `gitleaks dir --redact` on every changed path → no leaks found.
  - [x] Built-in browser on a loopback `dashboard-api` with a loopback fake GitHub (no GitHub access): Connect GitHub with a wrong token shows "GitHub did not accept the token (HTTP 401): it is invalid, expired or revoked." and clears the field; the corrected token connects; a check opens the status window with every stage done and "Completed"; after a reload and sign-in, **Fetch status** reopens it. A stacking bug (the run-history table header painted over the window) was found and fixed (`z-index`).
  - [x] Full suite and fast tier, 2026-10-18, in a scratch Python 3.13.12 venv outside the repo with every extra installed under `ci/{dev,ai,azure,dashboard}-constraints.txt` and `src/` on the path through a `.pth` file (the local `.venv` runs Python 3.14, for which the pinned `tiktoken` has no wheel, so it lacks the `ai` extra and skips 980 tests). Full: `python -m pytest -p no:cacheprovider --strict-markers -q --cov=src/drift_engine --cov=src/ai_engine --cov=src/dashboard_api --cov-report=term --cov-fail-under=0 tests/` → exit 0, 3192 passed, 4026 subtests passed, 0 skipped, total coverage 98% (`github_fetch.py` 92%). Fast tier: `python -m pytest -p no:cacheprovider --strict-markers -q -m "not integration and not mutation" tests/` → exit 0, 2632 passed, 560 deselected, 2213 subtests passed. `node --test dashboard/` → 49 pass, 0 fail. (A first scratch run without the `.pth` file and the pinned `pluggy` had 23 environment-only failures in workflow and pin tests; those tests passed in the `.venv` run and after the environment fix.)
  - [ ] One real verification and fetch against GitHub from the dashboard, only with the user's explicit approval and the user's own read-only token. **Partial evidence**: user-confirmed historical real fetches (2026-10-18): the user personally clicked **Check GitHub for new runs** in the dashboard around 11:50 and 12:25 IST; both worked and GitHub artifact data (runs such as `39105665374`) was downloaded into the local dashboard data directory. Recorded from the user's statement, not as a logged acceptance test: no status response, screenshot, token-verification result or download count was captured. Still open for this task: no verification outcome was recorded, and both fetches came before the 2026-10-18 acceptance-review fixes (verification and partial-result semantics, the token field, the launcher). The current implementation has not yet been validated against real GitHub.
- **Implementation Notes**:
  - **Persistence decision**: tokens are session-only (server memory). Saving one would add a plaintext secret at rest and the project has no OS keychain layer; an opt-in saved token would need one (for example macOS Keychain) and its own review. Python cannot reliably wipe strings from memory; references are dropped after verification, replacement and each fetch.
  - CSRF: authentication is a bearer header kept in page memory (no cookies), so a cross-site request cannot authenticate; the `Origin` check and JSON-only body are defence in depth. DNS-rebinding is limited by the loopback bind and the required bearer token.
  - Fetch-script changes are minimal: one JSON getter that keeps the HTTP status (`http_NNN`, `rate_limited`, `network`, `invalid_json`) for both listings, stage markers, and `--verify-only`. Download, eligibility and write rules are unchanged.
  - `unavailable_reason` `not_enabled` is renamed `not_connected`.
- **Acceptance review and fixes (2026-10-18, user-requested, local, not committed)**:
  - **Unexpected artifacts (read-only investigation)**: `.artifacts/dashboard/` gained 60 artifact directories at 11:50–11:52 and, at 12:24:56–12:25:02, `drift-report-39105665374`, `unmanaged-inventory-39105665374` and `github_issues.json` (`fetched_at` 06:54:56Z). Both bursts were written by the fetch script (atomic, no staging left). Not caused by Claude's session: the run ids are real GitHub ids absent from fixtures and scratch data, no GitHub token exists in Claude's shell, and the tests isolate data and local folders. Shell history (last written 11:48) ends with plain `scripts/run_dashboard.sh` runs and no `--fetch`; the data folder was not empty, so a plain start would not fetch by itself. At the time the evidence was **inconclusive** (a manual script run in another terminal could not be excluded). **Resolved 2026-10-18 by the user's confirmation**: the user started both fetches from the dashboard (**Check GitHub for new runs**, around 11:50 and 12:25 IST), and both succeeded. They count as user-confirmed historical real-fetch evidence (Task 13.4 validation), not as a logged acceptance test of the current implementation.
  - **Finding 1 (medium, browser password managers)**: the GitHub token field is no longer a password field in a submitted `<form>`: a CSS-masked text field (`-webkit-text-security: disc`; falls back to `type="password"` where unsupported) outside any form, with `autocomplete="off"`, spell checking off and `data-1p-ignore` / `data-lpignore` / `data-bwignore` / `data-form-type="other"`; Enter (not during IME composition) and the button submit; double submits are ignored. The sign-in field is unchanged on purpose (the launcher recommends saving the sign-in token in a password manager). Not a guarantee for every browser or extension; **real-Chrome check outstanding**.
  - **Finding 2 (medium, Issues 403)**: an Issues-only refusal is a warning, not a token problem: verification accepts a token whose repository and Actions checks pass but whose issue listing gets 403 (`dashboard_verify=ok warning=insufficient_permissions http=403 need=issues`); a `partial` fetch with an Issues 403 keeps the token verified and sets `connection.warning`; only `invalid_token`, a refused Actions access, `repository_not_accessible` or `sso_required` set `last_error` and mark it unverified; rate limits, network and write failures leave the token state alone. Chip and window texts follow the category ("lacks Issues: Read", "rejected the token (invalid, expired or revoked)", "lacks Actions: Read", "cannot access the repository", "needs SSO authorization").
  - **Finding 3 (medium, launcher and `users.json`)**: the role migration never stops the launcher: invalid JSON, invalid UTF-8, an unexpected shape, an unreadable file, a write failure, a symbolic link or a non-regular file give one warning, the file is left byte-for-byte unchanged (never regenerated), and the server still refuses every sign-in on it (503). Opt-out: `--no-github` or `DASHBOARD_NO_GITHUB=1` skips the grant (a removed `data_refresher` stays removed), starts `dashboard-api --no-github` (connect and fetch refused with `disabled`; a startup token is ignored) and downloads nothing at startup; it refuses to combine with `--fetch` or `--enable-github-fetch`. The deprecated alias still works.
  - **Low findings**: SSO-required 403s (`X-GitHub-SSO` header) → `sso_required`; secondary rate limits (a "rate limit" `message` in at most 4 KB of a 403 body, never shown or logged) → `rate_limited`; `--verify-only` makes one attempt per request (no retry burst on 429); `POST /api/github/*` bodies must declare a length of at most 4 KB, checked before any parsing or authentication (411/413), and the token field is bounded; Escape now hides the non-modal status window (docs corrected); comments no longer imply that rebinding a variable wipes a token.
  - **Tests added**: launcher (6 unusable-file cases, symlink, server still 503, opt-out by flag and environment, server started with `--no-github`, conflicts, deprecated alias); fetcher (Issues-only warning on connect and on a partial fetch, warning cleared by a full success, five refused-token/required-access cases, four neutral failures, GitHub turned off, CLI flag, real-script 429 single request and SSO, body bounds); script (Issues-only warning, SSO, secondary rate limit, plain 403, retries off); UI (masked field and fallback, button and Enter submit, IME Enter ignored, no `<form>`/submit in the dialog, warning chip, partial window text, Escape hides). In-app browser (Chromium, loopback fake GitHub, fake token): field `type="text"` with `-webkit-text-security: disc`, not in a form, Enter connects, field emptied, browser storage and cookies empty. This is not a real-Chrome password-manager check.
  - **Follow-up review (2026-10-18)**: fixed four gaps it found: the status window's **Replace GitHub token** now also appears for `sso_required` (same list as the backend's `AUTH_CATEGORIES`; tested for five categories); `docs/dashboard.md` now lists every category that marks a token unverified, says the launcher never rewrites `users.json` content (a regular file still gets mode 0600 as before), and names the masked text field's trade-offs (a screen reader may speak the typed characters; the text can be copied); the real-script Issues-403 case asserts the warning; a launcher test makes `users.json` truly unreadable (mode 000 + `chflags uchg`; skipped where `chflags` is missing or as root) and checks the warning and the unchanged file.
  - **Validation of the fixes (2026-10-18, scratch Python 3.13.12 venv with every extra pinned by `ci/*-constraints.txt`)**: full suite `python -m pytest -p no:cacheprovider --strict-markers -q -rs --cov=src/drift_engine --cov=src/ai_engine --cov=src/dashboard_api --cov-report=term --cov-fail-under=0 tests/` → exit 0, **3228 passed, 0 failed, 0 skipped**, 4026 subtests passed, total coverage 98% (`github_fetch.py` 93%, `app.py` 98%, `cli.py` 92%). Fast tier `-m "not integration and not mutation"` → exit 0, **2638 passed, 590 deselected**, 2213 subtests passed. `node --test dashboard/` → 55 pass, 0 fail. `gitleaks dir --redact` on every changed path → no leaks found. `.artifacts/dashboard/` (143 entries, last change 12:25:02) and `.artifacts/dashboard-local/` (`users.json` 11:36:10, `terraform-state.json` 2026-10-17) unchanged by this work. No real GitHub request, token, Terraform or Azure command was used.
- **Completion Notes**:
  - **Follow-up UI changes (2026-10-18, PR #14, commit `e6dbfc4`, merge `daa95f8`)**: **Check GitHub for new runs** while GitHub is not connected opens a "Connect GitHub first" popup instead of the token dialog; the token field is locked and masked while verification runs; the status window's Hide button is gone (the – button minimises); **Disconnect GitHub** closes the status window and removes the **Fetch status** button until GitHub is connected again. `dashboard/app.test.js` and `docs/dashboard.md` were updated. CI passed on `e6dbfc4` (Tests, Security Scan, Terraform Auth & Validation) and on `main` at `daa95f8`.
  - **Open before 🟢**: (1) a real-Chrome check that no password-save prompt appears for the GitHub token (the in-app Chromium check confirmed only the masking, the absence of a form, Enter submission and empty storage); (2) validation of the **current** implementation against real GitHub, with the user's approval and read-only token, recording the status window and `/api/fetch/status`: a good token, a wrong or revoked token (`invalid_token`), and ideally a token without Issues: Read (verified with a warning, partial fetch). The user-confirmed fetches of 11:50 and 12:25 IST show that a real fetch from the dashboard works, but they came before the review fixes and recorded no verification outcome. Real responses that the mocks cannot prove still need checking: fine-grained 403 versus 404, rate-limit and SSO headers. (Task 13.4's real-fetch item is now satisfied by the user's confirmation.) a review of the remaining risks (a token is in memory as long as the server runs; any local process running as the user can read it).

### PHASE 14 — Final Documentation, Demo & Portfolio Assets
**Status**: ⬜ NOT STARTED

Phase 14 finalizes documentation, builds an end-to-end automated demo walkthrough, and creates portfolio materials.

#### Task 14.1 — Final Documentation & Architecture Specifications
- **Status**: ⬜ NOT STARTED
- **Objective**: Update all project documentation, setup guides, API references, and architecture diagrams.
- **Dependencies**: Tasks 12.3, 13.3
- **Files/Areas**: `README.md`, `docs/`
- **Acceptance Criteria**:
  - [ ] Complete setup guide from zero to live detection platform.
  - [ ] Updated Mermaid diagrams illustrating full pipeline architecture.
- **Validation**:
  - [ ] Review documentation end-to-end.
- **Implementation Notes**:
  - Polish all project docs.
- **Completion Notes**:
  - None.

#### Task 14.2 — Comprehensive End-to-End Demo Script & Recording
- **Status**: ⬜ NOT STARTED
- **Objective**: Prepare reproducible end-to-end demo script covering drift creation -> detection -> AI analysis -> GitHub issue -> PR -> human approval -> remediation -> dashboard update.
- **Dependencies**: Task 14.1
- **Files/Areas**: `docs/demo-script.md`
- **Acceptance Criteria**:
  - [ ] Step-by-step walkthrough script for live presentation or video recording.
  - [ ] Verified demo execution flow with zero manual errors.
- **Validation**:
  - [ ] Dry run execution of full demo sequence.
- **Implementation Notes**:
  - Portfolio showcase piece.
- **Completion Notes**:
  - None.

#### Task 14.3 — Resume Bullet Points & Project Portfolio Presentation
- **Status**: ⬜ NOT STARTED
- **Objective**: Create professional summary document with high-impact resume bullet points, architectural highlights, and engineering achievements.
- **Dependencies**: Task 14.2
- **Files/Areas**: `docs/portfolio-summary.md`
- **Acceptance Criteria**:
  - [ ] Document containing metric-driven resume bullet points detailing Terraform, Azure, Python, LangGraph, DevSecOps, and FinOps achievements.
- **Validation**:
  - [ ] Review portfolio summary for clarity and impact.
- **Implementation Notes**:
  - Final portfolio artifact.
- **Completion Notes**:
  - None.

---
