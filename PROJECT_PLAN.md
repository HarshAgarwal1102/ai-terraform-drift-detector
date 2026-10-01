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

- **Current Active Phase**: Phase 3 — Deterministic Terraform Drift Detection
- **Current Active Task**: Task 3.1 — Drift Detection Strategy & Execution Plan
- **Phases Completed**: 2 of 14

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
**Status**: ⬜ NOT STARTED

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

#### Task 3.1 — Drift Detection Strategy & Execution Plan
- **Status**: ⬜ NOT STARTED
- **Objective**: Define exact CLI strategy for generating, exporting, and parsing machine-readable Terraform plans.
- **Dependencies**: Task 2.8
- **Files/Areas**: `docs/drift-detection-spec.md`
- **Acceptance Criteria**:
  - [ ] Document specifying `terraform plan -detailed-exitcode -out=tfplan` strategy.
  - [ ] Document specifying conversion to JSON via `terraform show -json tfplan`.
- **Validation**:
  - [ ] Specification review.
- **Implementation Notes**:
  - Deterministic engine foundation.
- **Completion Notes**:
  - None.

#### Task 3.2 — Machine-Readable Terraform Plan Generation
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement script to execute non-interactive Terraform plan and convert plan file to JSON format.
- **Dependencies**: Task 3.1
- **Files/Areas**: `scripts/generate_plan_json.sh`
- **Acceptance Criteria**:
  - [ ] Script runs `terraform plan -out=tfplan` cleanly.
  - [ ] Script runs `terraform show -json tfplan > plan.json`.
  - [ ] Valid JSON file produced.
- **Validation**:
  - [ ] `jq . plan.json` executes without errors.
- **Implementation Notes**:
  - Script must handle detailed exit code 0 (no changes), 2 (drift found), and 1 (error).
- **Completion Notes**:
  - None.

#### Task 3.3 — State vs Infrastructure Change Detection
- **Status**: ⬜ NOT STARTED
- **Objective**: Develop core logic to parse `resource_changes` in `plan.json` for `create`, `update`, `delete`, and `no-op` actions.
- **Dependencies**: Task 3.2
- **Files/Areas**: `scripts/detect_drift.py`
- **Acceptance Criteria**:
  - [ ] Evaluates `resource_changes[].change.actions`.
  - [ ] Identifies added, modified, deleted, and replaced resources correctly.
- **Validation**:
  - [ ] Test execution against sample Terraform plan JSON.
- **Implementation Notes**:
  - Pure deterministic evaluation without AI.
- **Completion Notes**:
  - None.

#### Task 3.4 — Resource Identification & Categorization
- **Status**: ⬜ NOT STARTED
- **Objective**: Map detected changes to resource addresses, types, names, and exact attribute diffs.
- **Dependencies**: Task 3.3
- **Files/Areas**: `scripts/detect_drift.py`
- **Acceptance Criteria**:
  - [ ] Captures before and after states for changed attributes.
  - [ ] Group drifts by resource type (initially `azurerm_resource_group`).
- **Validation**:
  - [ ] Verify attribute diff outputs against test drift plans.
- **Implementation Notes**:
  - Extracts `before` and `after` dictionaries from JSON schema.
- **Completion Notes**:
  - None.

#### Task 3.5 — Structured Drift Schema Definition
- **Status**: ⬜ NOT STARTED
- **Objective**: Create standard JSON schema (`drift_report.json`) representing normalized drift findings.
- **Dependencies**: Task 3.4
- **Files/Areas**: `schemas/drift_report.schema.json`
- **Acceptance Criteria**:
  - [ ] Schema defines header (timestamp, environment, target), summary counts, and detailed resource drift list.
  - [ ] Each drift item includes address, type, action, attribute_changes array.
- **Validation**:
  - [ ] Validate sample `drift_report.json` against JSON schema.
- **Implementation Notes**:
  - Contract for Python engine and AI analysis pipeline.
- **Completion Notes**:
  - None.

#### Task 3.6 — Reproducible Drift Scenarios Suite
- **Status**: ⬜ NOT STARTED
- **Objective**: Create reproducible test scenarios, starting with an external change to a verified mutable property of `aitdd-dev-main-rg` (candidate: tags, subject to empirical verification). Scenarios for other resource types are added only if those resources are introduced in a later infrastructure-expansion phase.
- **Dependencies**: Task 3.5
- **Files/Areas**: `tests/scenarios/`
- **Acceptance Criteria**:
  - [ ] Azure CLI / Azure PowerShell scripts to introduce controlled drift into non-production sandbox.
  - [ ] Scripts to revert manual drift.
- **Validation**:
  - [ ] Execute script -> run detection -> confirm expected drift captured.
- **Implementation Notes**:
  - Test suite for validating detection accuracy.
- **Completion Notes**:
  - None.

#### Task 3.7 — Validation Against Real Azure Drift Scenarios
- **Status**: ⬜ NOT STARTED
- **Objective**: Validate deterministic detection engine against live Azure drift scenario in `dev` environment.
- **Dependencies**: Task 3.6
- **Files/Areas**: `scripts/detect_drift.py`
- **Acceptance Criteria**:
  - [ ] Introduce real drift in Azure dev environment (external change to the verified mutable property of `aitdd-dev-main-rg` via Azure CLI).
  - [ ] Run drift detection script.
  - [ ] Confirm `drift_report.json` accurately reflects exact modified attribute.
- **Validation**:
  - [ ] Verify `drift_report.json` matches manual Azure CLI modification.
- **Implementation Notes**:
  - Revert manual change immediately after test.
- **Completion Notes**:
  - None.

---

### PHASE 4 — Python Drift Engine
**Status**: ⬜ NOT STARTED

Phase 4 modularizes the Python drift engine into a production-grade library with structured models, custom CLI entry points, logging, and unit tests.

#### Task 4.1 — Python Project Structure & Environment
- **Status**: ⬜ NOT STARTED
- **Objective**: Set up Python package structure, virtualenv configuration, dependencies, and `pyproject.toml` / `requirements.txt`.
- **Dependencies**: Task 3.5
- **Files/Areas**: `src/drift_engine/`, `pyproject.toml`, `requirements.txt`
- **Acceptance Criteria**:
  - [ ] Standard Python package layout (`src/drift_engine/`).
  - [ ] `pyproject.toml` configured with dependencies (Pydantic, click/argparse, pytest).
- **Validation**:
  - [ ] `pip install -e .` succeeds in clean virtual environment.
- **Implementation Notes**:
  - Clean Python library architecture.
- **Completion Notes**:
  - None.

#### Task 4.2 — Terraform Plan JSON Parser
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement robust Python parser module to read Terraform plan JSON files and extract state changes safely.
- **Dependencies**: Task 4.1
- **Files/Areas**: `src/drift_engine/parser.py`
- **Acceptance Criteria**:
  - [ ] Safely parses `plan.json` files up to 50MB.
  - [ ] Handles missing fields, null states, and unknown values gracefully without throwing unhandled exceptions.
- **Validation**:
  - [ ] `pytest tests/test_parser.py` passes.
- **Implementation Notes**:
  - Defensive parsing for all Terraform resource change fields.
- **Completion Notes**:
  - None.

#### Task 4.3 — Drift Normalization & Pydantic Data Models
- **Status**: ⬜ NOT STARTED
- **Objective**: Define strong Pydantic models for `DriftItem`, `AttributeChange`, `DriftSummary`, and `DriftReport`.
- **Dependencies**: Task 4.2
- **Files/Areas**: `src/drift_engine/models.py`
- **Acceptance Criteria**:
  - [ ] Pydantic models enforce strict types for all drift attributes.
  - [ ] Supports JSON serialization and deserialization seamlessly.
- **Validation**:
  - [ ] `pytest tests/test_models.py` passes.
- **Implementation Notes**:
  - Types used across Python engine and LangGraph pipeline.
- **Completion Notes**:
  - None.

#### Task 4.4 — Resource Difference & Comparison Engine
- **Status**: ⬜ NOT STARTED
- **Objective**: Build comparison module to extract deep attribute diffs between `before` and `after` resource definitions.
- **Dependencies**: Task 4.3
- **Files/Areas**: `src/drift_engine/comparator.py`
- **Acceptance Criteria**:
  - [ ] Filters out noise (e.g., computed IDs, timestamps, read-only metadata).
  - [ ] Isolates user-configured drifts (e.g., IP whitelist changes, tag changes, security setting modifications).
- **Validation**:
  - [ ] `pytest tests/test_comparator.py` passes.
- **Implementation Notes**:
  - Intelligent diffing ignoring non-consequential metadata changes.
- **Completion Notes**:
  - None.

#### Task 4.5 — Drift Severity Classifier Foundation
- **Status**: ⬜ NOT STARTED
- **Objective**: Build deterministic rules-based severity classifier (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`).
- **Dependencies**: Task 4.4
- **Files/Areas**: `src/drift_engine/severity.py`
- **Acceptance Criteria**:
  - [ ] Classifies security-sensitive resources (Key Vault access policy, NSG inbound rules, public storage access) as `CRITICAL`/`HIGH`.
  - [ ] Classifies tag/description changes as `LOW`/`INFO`.
- **Validation**:
  - [ ] `pytest tests/test_severity.py` passes.
- **Implementation Notes**:
  - Rules-based fallback classifier prior to AI enrichment.
- **Completion Notes**:
  - None.

#### Task 4.6 — Structured Output Generator (JSON/YAML)
- **Status**: ⬜ NOT STARTED
- **Objective**: Implement CLI output formatters for console human readability and machine JSON/YAML output.
- **Dependencies**: Task 4.5
- **Files/Areas**: `src/drift_engine/cli.py`, `src/drift_engine/formatters.py`
- **Acceptance Criteria**:
  - [ ] CLI command `drift-engine analyze --plan plan.json --output report.json` produces formatted report.
  - [ ] CLI command supports `--format console` for rich terminal output.
- **Validation**:
  - [ ] Test CLI invocation with sample plan JSON files.
- **Implementation Notes**:
  - Use rich or standard formatting for terminal output.
- **Completion Notes**:
  - None.

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
