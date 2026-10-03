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
- **Drift is a valid result**: "Drift detected" is a valid detection result and does not by itself mean the detection pipeline failed. Detection/process errors should fail appropriately.
- **Real data only**: The final dashboard must use real project data/artifacts; no mock or fake metrics.

---

## 📊 Master Project Overview

- **Current Active Phase**: Phase 6 — LangGraph AI Analysis Engine
- **Current Active Task**: Task 6.6 — Remediation Recommendation & Report Generation Nodes
- **Phases Completed**: 5 of 14

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
**Status**: 🟡 WORK IN PROGRESS

Phase 6 constructs the AI analysis engine using LangGraph, LangChain, and OpenAI-compatible models to analyze detected drift, evaluate security and cost implications, and recommend remediation steps based on strict empirical evidence.

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
  - **Constraint (recorded 2026-10-03, Task 6.5 design review):** Task 6.6 must not introduce an independent additional LLM call; the Phase 6 guarantee of at most one logical LLM call per run stands. The final remediation architecture is decided in Task 6.6.
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
