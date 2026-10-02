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

### Core Project Principles
- **Deterministic source of truth**: Terraform/Azure deterministic tooling is the source of truth for drift. AI interprets, classifies, explains, and recommends; AI is NOT the source of truth for detecting drift.
- **Evidence vs inference**: AI must distinguish evidence from inference, and must not hallucinate who changed infrastructure.
- **LLM-independent detection**: Drift detection must work even when the LLM is unavailable.
- **No autonomous apply**: AI must never directly execute destructive `terraform apply`. Remediation requires human approval.
- **Security gates**: Security scan failures should fail the relevant CI/CD pipeline.
- **Drift is a valid result**: "Drift detected" is a valid detection result and does not by itself mean the detection pipeline failed. Detection/process errors should fail appropriately.
- **Real data only**: The final dashboard must use real project data/artifacts; no mock or fake metrics.

---

## 📊 Master Project Overview

- **Current Active Phase**: Phase 4 — Python Drift Engine
- **Current Active Task**: Task 4.7 — Logging, Error Handling & Unit Tests
- **Phases Completed**: 3 of 14

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
**Status**: 🟡 WORK IN PROGRESS

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
- **Status**: ⬜ NOT STARTED
- **Objective**: Add comprehensive logging, exception handling, and test coverage >= 85% for `drift_engine`.
- **Dependencies**: Task 4.6
- **Files/Areas**: `src/drift_engine/`, `tests/`
- **Acceptance Criteria**:
  - [ ] Structured logging using standard library `logging`.
  - [ ] Unit test suite covering all modules, edge cases, and invalid inputs.
- **Validation**:
  - [ ] `pytest --cov=src/drift_engine tests/` achieves >= 85% coverage.
- **Implementation Notes**:
  - Production readiness check for Python package.
- **Completion Notes**:
  - None.

---

### PHASE 5 — Automated Drift Detection Workflow
**Status**: ⬜ NOT STARTED

Phase 5 automates drift scanning in GitHub Actions on a schedule and manual dispatch trigger.

#### Task 5.1 — Scheduled & Manual GitHub Actions Workflows
- **Status**: ⬜ NOT STARTED
- **Objective**: Create `.github/workflows/drift-detection.yml` triggered via `schedule` (cron) and `workflow_dispatch`.
- **Dependencies**: Tasks 2.6, 4.7
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] Workflow contains daily cron trigger (e.g., `0 2 * * *`) and `workflow_dispatch`.
  - [ ] Supports inputs for `environment` selection.
- **Validation**:
  - [ ] Manual trigger test via GitHub Actions UI / CLI.
- **Implementation Notes**:
  - CI pipeline for continuous drift monitoring.
- **Completion Notes**:
  - None.

#### Task 5.2 — OIDC Authentication & Terraform Setup in Pipeline
- **Status**: ⬜ NOT STARTED
- **Objective**: Integrate Azure OIDC login and Terraform CLI setup steps into drift detection workflow.
- **Dependencies**: Task 5.1
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] `azure/login@v2` authenticates via OIDC.
  - [ ] `hashicorp/setup-terraform` installs Terraform.
  - [ ] `terraform init` connects to AzureRM remote backend.
- **Validation**:
  - [ ] Pipeline logs confirm successful backend initialization.
- **Implementation Notes**:
  - Non-interactive Terraform execution.
- **Completion Notes**:
  - None.

#### Task 5.3 — Automated Drift Engine Execution
- **Status**: ⬜ NOT STARTED
- **Objective**: Execute plan generation and Python `drift-engine` inside GitHub Actions step.
- **Dependencies**: Task 5.2
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] Plan output generated and converted to JSON.
  - [ ] Python engine produces `drift_report.json`.
  - [ ] Step captures exit codes accurately.
- **Validation**:
  - [ ] Workflow step succeeds and outputs drift summary in job logs.
- **Implementation Notes**:
  - Pipeline distinguishes between process errors and valid drift findings.
- **Completion Notes**:
  - None.

#### Task 5.4 — Structured Artifact Storage & Pipeline Handling
- **Status**: ⬜ NOT STARTED
- **Objective**: Upload `drift_report.json` and raw plan as workflow artifacts for downstream inspection.
- **Dependencies**: Task 5.3
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] Artifact `drift-report-<run_id>` uploaded using `actions/upload-artifact@v4`.
  - [ ] Retention policy set appropriately (e.g., 30 days).
- **Validation**:
  - [ ] Download and inspect artifact from completed workflow run.
- **Implementation Notes**:
  - Artifacts serve as input for Phase 6 AI analysis.
- **Completion Notes**:
  - None.

#### Task 5.5 — Pipeline Error Handling & Failure Reporting
- **Status**: ⬜ NOT STARTED
- **Objective**: Ensure execution failures (auth failure, terraform syntax errors) fail the job, while detected drift is reported without failing execution unexpectedly.
- **Dependencies**: Task 5.4
- **Files/Areas**: `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] Infra/CLI failures cause job status to fail (red).
  - [ ] "Drift detected" sets pipeline output variable `drift_detected=true` while step completes successfully.
- **Validation**:
  - [ ] Test execution with valid plan, drifted plan, and syntax error.
- **Implementation Notes**:
  - Clear separation of operational failure vs drift finding.
- **Completion Notes**:
  - None.

---

### PHASE 6 — LangGraph AI Analysis Engine
**Status**: ⬜ NOT STARTED

Phase 6 constructs the AI analysis engine using LangGraph, LangChain, and OpenAI-compatible models to analyze detected drift, evaluate security and cost implications, and recommend remediation steps based on strict empirical evidence.

#### Task 6.1 — LangGraph Infrastructure & LLM Configuration
- **Status**: ⬜ NOT STARTED
- **Objective**: Initialize Python LangGraph state graph framework and set up OpenAI / Azure OpenAI client providers with environment configuration.
- **Dependencies**: Tasks 4.3, 5.4
- **Files/Areas**: `src/ai_engine/config.py`, `src/ai_engine/graph.py`
- **Acceptance Criteria**:
  - [ ] `AiState` TypedDict defined for LangGraph state propagation.
  - [ ] Config handles API keys, endpoint URLs, and model deployment names safely.
  - [ ] Graceful fallback when LLM API keys are missing or unreachable.
- **Validation**:
  - [ ] `pytest tests/test_ai_config.py` passes.
- **Implementation Notes**:
  - Robust LLM integration layer.
- **Completion Notes**:
  - None.

#### Task 6.2 — Drift Parsing & Resource Identification Nodes
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement LangGraph node `parse_drift` to read `drift_report.json` and populate graph state with structured resource diffs.
- **Dependencies**: Task 6.1
- **Files/Areas**: `src/ai_engine/nodes/parse_drift.py`
- **Acceptance Criteria**:
  - [ ] Extracts target resource types, addresses, and attribute changes into graph memory.
  - [ ] Generates initial resource summary list.
- **Validation**:
  - [ ] Test node execution with sample `drift_report.json`.
- **Implementation Notes**:
  - Deterministic state preparation node.
- **Completion Notes**:
  - None.

#### Task 6.3 — Classification & Security Analysis Nodes
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement LangGraph nodes `classify_drift` and `analyze_security` to evaluate compliance and security exposure.
- **Dependencies**: Task 6.2
- **Files/Areas**: `src/ai_engine/nodes/security_analysis.py`
- **Acceptance Criteria**:
  - [ ] Analyzes firewall rule removals, open ports, public storage access, or disabled encryption.
  - [ ] Assigns security impact rating backed by specific attribute evidence.
- **Validation**:
  - [ ] Test node with security-drift report.
- **Implementation Notes**:
  - AI must explicitly cite attribute evidence in prompt response.
- **Completion Notes**:
  - None.

#### Task 6.4 — Cost & Configuration Analysis Nodes
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement LangGraph nodes `analyze_cost` and `analyze_configuration` to inspect resource SKU changes, instance counts, or settings.
- **Dependencies**: Task 6.3
- **Files/Areas**: `src/ai_engine/nodes/cost_analysis.py`
- **Acceptance Criteria**:
  - [ ] Evaluates SKU upgrades/downgrades or resource additions/deletions.
  - [ ] Summarizes configuration drift relative to declared Terraform specs.
- **Validation**:
  - [ ] Test node with SKU change drift report.
- **Implementation Notes**:
  - Synthesizes configuration differences into clear explanations.
- **Completion Notes**:
  - None.

#### Task 6.5 — Root Cause & Risk Assessment Nodes
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement LangGraph nodes `analyze_root_cause` and `assess_risk` to hypothesize drift origin based strictly on available evidence.
- **Dependencies**: Task 6.4
- **Files/Areas**: `src/ai_engine/nodes/root_cause.py`
- **Acceptance Criteria**:
  - [ ] Analyzes whether drift stems from manual portal edits, missing HCL variables, or out-of-band updates.
  - [ ] Explicitly labels speculative claims as inferences vs facts.
- **Validation**:
  - [ ] Test prompt outputs against strict Evidence vs Inference criteria.
- **Implementation Notes**:
  - Prompt engineering enforcing zero hallucination of untracked events.
- **Completion Notes**:
  - None.

#### Task 6.6 — Remediation Recommendation & Report Generation Nodes
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement LangGraph nodes `recommend_remediation` and `generate_report` to synthesize full Markdown AI analysis report.
- **Dependencies**: Task 6.5
- **Files/Areas**: `src/ai_engine/nodes/report_generator.py`
- **Acceptance Criteria**:
  - [ ] Generates clean Markdown report containing Summary, Security Impact, Cost Impact, Root Cause, and Recommended HCL Remediation snippet.
  - [ ] Outputs structured JSON alongside Markdown report.
- **Validation**:
  - [ ] Run full LangGraph pipeline end-to-end and inspect `ai_analysis_report.md`.
- **Implementation Notes**:
  - Final graph output node producing user-facing artifacts.
- **Completion Notes**:
  - None.

#### Task 6.7 — Evidence vs Inference Validation & Unit Testing
- **Status**: ⬜ NOT STARTED
- **Objective**: Create automated evaluation test suite to verify that LLM outputs never invent non-existent resource attributes or false attributions.
- **Dependencies**: Task 6.6
- **Files/Areas**: `tests/test_ai_engine.py`
- **Acceptance Criteria**:
  - [ ] Unit tests for all individual nodes.
  - [ ] Assertion tests checking that all cited attributes exist in `drift_report.json`.
- **Validation**:
  - [ ] `pytest tests/test_ai_engine.py` passes.
- **Implementation Notes**:
  - AI reliability guardrails.
- **Completion Notes**:
  - None.

---

### PHASE 7 — Azure Activity Log Investigation
**Status**: ⬜ NOT STARTED

Phase 7 queries Azure Activity Logs to correlate detected drift with actual Azure control plane events (caller identity, timestamp, operation name).

#### Task 7.1 — Azure Activity Log API Integration
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement Python module using `azure-mgmt-log` / Azure REST API to query activity logs for target resource IDs within drift timeframe.
- **Dependencies**: Task 6.6
- **Files/Areas**: `src/drift_engine/activity_logs.py`
- **Acceptance Criteria**:
  - [ ] Queries Azure Activity Logs for resource operations in past N days.
  - [ ] Extracts `caller`, `eventTimestamp`, `operationName`, and `status`.
- **Validation**:
  - [ ] Test query against Azure environment (or mocked log responses).
- **Implementation Notes**:
  - Integrates empirical Azure management plane telemetry.
- **Completion Notes**:
  - None.

#### Task 7.2 — Caller Identity & Action Correlation
- **Status**: ⬜ NOT STARTED
- **Objective**: Correlate detected drift attributes with specific write/delete operations from Activity Logs.
- **Dependencies**: Task 7.1
- **Files/Areas**: `src/drift_engine/activity_logs.py`
- **Acceptance Criteria**:
  - [ ] Matches resource ID and modification timestamp window with log entries.
  - [ ] Populates `caller_identity` field in drift report when exact match is found.
- **Validation**:
  - [ ] Verify caller attribution in test scenario log match.
- **Implementation Notes**:
  - Provides empirical attribution when log evidence exists.
- **Completion Notes**:
  - None.

#### Task 7.3 — Unknown/Missing Log Handling & Fallback Logic
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement fallback behavior when Activity Logs are disabled, expired, or lack relevant events.
- **Dependencies**: Task 7.2
- **Files/Areas**: `src/drift_engine/activity_logs.py`
- **Acceptance Criteria**:
  - [ ] Sets `caller_identity = "Change origin could not be confirmed"` when logs are missing.
  - [ ] Prevents AI layer from inventing or assuming caller identities without log data.
- **Validation**:
  - [ ] Test execution with empty log response.
- **Implementation Notes**:
  - Strict compliance with anti-hallucination rules.
- **Completion Notes**:
  - None.

---

### PHASE 8 — GitHub Issue / PR Automation
**Status**: ⬜ NOT STARTED

Phase 8 automates workflow actions upon drift detection by creating structured GitHub Issues and proposing remediation PRs.

#### Task 8.1 — Automated GitHub Drift Issue Creator
- **Status**: ⬜ NOT STARTED
- **Objective**: Build script using GitHub REST API / PyGithub to automatically create or update structured GitHub Issues when drift is detected.
- **Dependencies**: Tasks 5.5, 6.6
- **Files/Areas**: `scripts/github_automation.py`
- **Acceptance Criteria**:
  - [ ] Creates GitHub Issue formatted with drift summary, AI security analysis, cost impact, and recommended HCL fix.
  - [ ] Deduplicates issues (updates existing open issue for same resource drift instead of creating duplicates).
- **Validation**:
  - [ ] Run issue creator script against test GitHub repository.
- **Implementation Notes**:
  - Automated tracking of active infrastructure drifts.
- **Completion Notes**:
  - None.

#### Task 8.2 — Automated Remediation Branch & PR Generator
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement workflow step to generate a Git remediation branch and PR updating Terraform HCL to match desired/remediated state.
- **Dependencies**: Task 8.1
- **Files/Areas**: `scripts/create_remediation_pr.py`
- **Acceptance Criteria**:
  - [ ] Creates branch `drift-remediation/<resource_name>-<date>`.
  - [ ] Proposes HCL patch or state sync.
  - [ ] Opens GitHub PR referencing original drift issue.
- **Validation**:
  - [ ] Test PR generation in test repository.
- **Implementation Notes**:
  - PR must await human review before apply.
- **Completion Notes**:
  - None.

#### Task 8.3 — Issue/PR Lifecycle & Deduplication
- **Status**: ⬜ NOT STARTED
- **Objective**: Automatically close GitHub Issues and PRs when subsequent drift scans confirm drift has been resolved.
- **Dependencies**: Task 8.2
- **Files/Areas**: `scripts/github_automation.py`
- **Acceptance Criteria**:
  - [ ] Scans open drift issues.
  - [ ] Closes issue with comment when drift report confirms 0 drifts for target resource.
- **Validation**:
  - [ ] Test auto-close flow after applying Terraform fix.
- **Implementation Notes**:
  - Complete issue lifecycle management.
- **Completion Notes**:
  - None.

---

### PHASE 9 — DevSecOps Integration
**Status**: ⬜ NOT STARTED

Phase 9 integrates deterministic security scanners into CI/CD to validate Terraform code security and prevent secret leaks.

#### Task 9.1 — TFLint Integration
- **Status**: ⬜ NOT STARTED
- **Objective**: Integrate TFLint with AzureRM ruleset into local scripts and GitHub Actions workflows.
- **Dependencies**: Task 5.1
- **Files/Areas**: `.tflint.hcl`, `.github/workflows/security-scan.yml`
- **Acceptance Criteria**:
  - [ ] `.tflint.hcl` configures azurerm ruleset plugin.
  - [ ] `tflint --recursive` executes cleanly without errors.
  - [ ] Workflow fails if TFLint finds errors.
- **Validation**:
  - [ ] Run `tflint --init && tflint` locally.
- **Implementation Notes**:
  - Static analysis for Terraform best practices.
- **Completion Notes**:
  - None.

#### Task 9.2 — tfsec Infrastructure Security Scanner
- **Status**: ⬜ NOT STARTED
- **Objective**: Integrate `tfsec` static analysis scanner to check for Azure security misconfigurations.
- **Dependencies**: Task 9.1
- **Files/Areas**: `.github/workflows/security-scan.yml`
- **Acceptance Criteria**:
  - [ ] `tfsec` scans all module directories and environments.
  - [ ] High/Critical security findings fail the pipeline.
- **Validation**:
  - [ ] Run `tfsec terraform/` locally.
- **Implementation Notes**:
  - Security scanning prior to plan/apply.
- **Completion Notes**:
  - None.

#### Task 9.3 — TruffleHog Secret Scanning
- **Status**: ⬜ NOT STARTED
- **Objective**: Configure TruffleHog in GitHub Actions to scan commits and repository history for exposed credentials or keys.
- **Dependencies**: Task 9.2
- **Files/Areas**: `.github/workflows/security-scan.yml`
- **Acceptance Criteria**:
  - [ ] TruffleHog action runs on push and PR.
  - [ ] Pipeline halts if unencrypted secrets/tokens are detected.
- **Validation**:
  - [ ] Test execution in GitHub Actions workflow.
- **Implementation Notes**:
  - Credentials leakage prevention.
- **Completion Notes**:
  - None.

#### Task 9.4 — Super-Linter Code Quality Enforcement
- **Status**: ⬜ NOT STARTED
- **Objective**: Add GitHub Super-Linter to validate Python, YAML, Shell, and Markdown standards across repository.
- **Dependencies**: Task 9.3
- **Files/Areas**: `.github/workflows/super-linter.yml`
- **Acceptance Criteria**:
  - [ ] Super-Linter validates Python (flake8/black), Bash (shellcheck), and YAML.
  - [ ] Enforces unified coding standards.
- **Validation**:
  - [ ] Workflow completes cleanly on main branch.
- **Implementation Notes**:
  - Code hygiene and linting automation.
- **Completion Notes**:
  - None.

---

### PHASE 10 — FinOps / Cost Analysis
**Status**: ⬜ NOT STARTED

Phase 10 integrates Infracost to provide deterministic cost estimates for configuration drift and infrastructure changes.

#### Task 10.1 — Infracost CLI Integration
- **Status**: ⬜ NOT STARTED
- **Objective**: Install and configure Infracost CLI in local environment and GitHub Actions pipeline.
- **Dependencies**: Task 5.3
- **Files/Areas**: `scripts/infracost_analysis.sh`, `.github/workflows/drift-detection.yml`
- **Acceptance Criteria**:
  - [ ] Infracost evaluates `tfplan` or environment directory.
  - [ ] Generates machine-readable `infracost.json`.
- **Validation**:
  - [ ] `infracost breakdown --path terraform/environments/dev` output generated.
- **Implementation Notes**:
  - Real cloud cost estimations.
- **Completion Notes**:
  - None.

#### Task 10.2 — Terraform Plan Cost Delta Calculation
- **Status**: ⬜ NOT STARTED
- **Objective**: Extract cost differences (`monthly_cost_delta`) between current state and drifted state.
- **Dependencies**: Task 10.1
- **Files/Areas**: `src/drift_engine/cost.py`
- **Acceptance Criteria**:
  - [ ] Parses `infracost.json` and correlates cost changes with specific resource drifts.
  - [ ] Formats currency delta outputs.
- **Validation**:
  - [ ] Test parsing against sample Infracost output.
- **Implementation Notes**:
  - Accurate cost metrics provided to AI engine.
- **Completion Notes**:
  - None.

#### Task 10.3 — AI Cost Impact Explanation Engine
- **Status**: ⬜ NOT STARTED
- **Objective**: Pass Infracost cost delta data into LangGraph node `analyze_cost` to generate human-readable financial explanations.
- **Dependencies**: Task 10.2, Task 6.4
- **Files/Areas**: `src/ai_engine/nodes/cost_analysis.py`
- **Acceptance Criteria**:
  - [ ] AI output explains exact monthly cost increase/decrease using Infracost numbers.
  - [ ] AI does not invent or estimate unverified prices.
- **Validation**:
  - [ ] Verify AI cost report matches Infracost JSON numbers.
- **Implementation Notes**:
  - Strict financial accuracy without LLM pricing hallucinations.
- **Completion Notes**:
  - None.

---

### PHASE 11 — Human-Approved Remediation
**Status**: ⬜ NOT STARTED

Phase 11 enforces strict human approval controls before applying any automated infrastructure remediation.

#### Task 11.1 — Safe Remediation Architecture & Controls
- **Status**: ⬜ NOT STARTED
- **Objective**: Architect human-in-the-loop controls prohibiting autonomous destructive apply actions.
- **Dependencies**: Task 8.2
- **Files/Areas**: `docs/remediation-safeguards.md`
- **Acceptance Criteria**:
  - [ ] Specification mandating manual review, environment approval gates, and `terraform plan` verification prior to `apply`.
  - [ ] Direct `terraform apply` blocked in automated background detection workflows.
- **Validation**:
  - [ ] Document architecture approval.
- **Implementation Notes**:
  - Core safety principle: Zero autonomous destructive changes.
- **Completion Notes**:
  - None.

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
  - [ ] Workflow checks out approved PR branch.
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
**Status**: ⬜ NOT STARTED

Phase 12 builds a comprehensive end-to-end test suite and performs security hardening across all platform components.

#### Task 12.1 — Comprehensive Unit & Integration Test Suite
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement comprehensive `pytest` suite covering Python parser, drift models, severity rules, GitHub automation, and AI graph nodes.
- **Dependencies**: Tasks 4.7, 6.7, 8.3
- **Files/Areas**: `tests/`
- **Acceptance Criteria**:
  - [ ] Test suite covers clean, drifted, invalid, and corrupted inputs.
  - [ ] Test execution completes in < 60 seconds.
- **Validation**:
  - [ ] `pytest tests/` passes cleanly with high coverage.
- **Implementation Notes**:
  - Automated quality gate.
- **Completion Notes**:
  - None.

#### Task 12.2 — End-to-End Drift Scenario Test Matrix
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement scenario matrix testing: No Drift, Single Resource Drift, Multi-Resource Drift, Security Drift, Cost Drift, AI Unavailable, Azure API Failure.
- **Dependencies**: Task 12.1
- **Files/Areas**: `tests/integration/`
- **Acceptance Criteria**:
  - [ ] Matrix tests verify graceful degradation (e.g., if LLM API is down, system still produces deterministic drift report).
- **Validation**:
  - [ ] Run full scenario test matrix.
- **Implementation Notes**:
  - Resiliency verification across all failure modes.
- **Completion Notes**:
  - None.

#### Task 12.3 — Least Privilege RBAC & Secret Hardening Audit
- **Status**: ⬜ NOT STARTED
- **Objective**: Conduct security audit of Azure Service Principals, GitHub Secrets, OIDC permissions, and API key handling.
- **Dependencies**: Task 12.2
- **Files/Areas**: `docs/security-audit.md`
- **Acceptance Criteria**:
  - [ ] Audit confirms no hardcoded secrets exist in repository.
  - [ ] OIDC claims restricted to specific GitHub repo and branch.
- **Validation**:
  - [ ] Run TruffleHog + manual security checklist.
- **Implementation Notes**:
  - Production-grade security audit.
- **Completion Notes**:
  - None.

---

### PHASE 13 — Professional Dashboard
**Status**: ⬜ NOT STARTED

Phase 13 builds a web-based management dashboard consuming live platform APIs and data to visualize drift status, security risks, cost impacts, and remediation workflows.

#### Task 13.1 — Dashboard Data API & State Engine
- **Status**: ⬜ NOT STARTED
- **Objective**: Build lightweight Python backend API (FastAPI) to serve live drift reports, history, and status metrics.
- **Dependencies**: Tasks 4.6, 8.3
- **Files/Areas**: `src/dashboard_api/`
- **Acceptance Criteria**:
  - [ ] Endpoints for `/api/summary`, `/api/drifts`, `/api/reports/{id}`, `/api/remediations`.
  - [ ] Consumes real `drift_report.json` and AI report artifacts.
- **Validation**:
  - [ ] `pytest tests/test_dashboard_api.py` passes.
- **Implementation Notes**:
  - Data layer for dynamic dashboard UI.
- **Completion Notes**:
  - None.

#### Task 13.2 — UI Component Development & Visual Analytics
- **Status**: ⬜ NOT STARTED
- **Objective**: Build modern, responsive dashboard UI displaying executive overview metrics, drift breakdown charts, and active risk feeds.
- **Dependencies**: Task 13.1
- **Files/Areas**: `dashboard/`
- **Acceptance Criteria**:
  - [ ] Overview Cards: Total Resources, Active Drifts, Security Exposure, Monthly Cost Impact.
  - [ ] Interactive tables filtering drifts by severity, resource type, and environment.
  - [ ] Detailed modal showing AI analysis, HCL diff, and remediation status.
- **Validation**:
  - [ ] UI renders cleanly and dynamically updates from API data.
- **Implementation Notes**:
  - Modern web interface with dark mode and visual feedback.
- **Completion Notes**:
  - None.

#### Task 13.3 — Live Data Integration & Real-Time Status Monitoring
- **Status**: ⬜ NOT STARTED
- **Objective**: Connect web dashboard frontend to backend API to ensure 100% real project data (zero mock data in final build).
- **Dependencies**: Task 13.2
- **Files/Areas**: `dashboard/`
- **Acceptance Criteria**:
  - [ ] Dashboard displays live drift reports generated from actual Azure scan runs.
  - [ ] Visual indicators reflect active PR and resolution states.
- **Validation**:
  - [ ] End-to-end user navigation test on active data.
- **Implementation Notes**:
  - Real-time visibility into infrastructure health.
- **Completion Notes**:
  - None.

---

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
