# Architecture — AI-Powered Terraform Drift Detection & Remediation Platform

## 1. Project Purpose

This platform detects, analyzes, and remediates **infrastructure drift** — the gap between what Terraform expects and what actually exists in Azure. The final product will combine Terraform, Python, LangGraph/LLM analysis, GitHub automation, and a professional dashboard.

**Current Status: Phase 1 completed (Minimal Foundation in Central India). Phase 2 in progress (infrastructure deployment pending).**

---

## 2. Phases Scope & Status

| Phase | Description | Scope | Status |
|---|---|---|---|
| **1** | **Azure + Terraform Infrastructure** | Minimal Resource Group baseline in `Central India`; reusable modules preserved for Network, Storage, Key Vault | ✅ Complete |
| **2** | **Remote State & Secure Auth** | Dedicated Storage Backend (`Central India`), Bootstrap module, State Migration, GitHub OIDC | 🟡 In Progress (Deployment Pending) |
| 3 | Drift Detection Engine | Scheduled plan analysis, state vs actual state comparison | ⬜ Planned |
| 4 | Python Drift Parser | Structured JSON extraction from plan files | ⬜ Planned |
| 5 | GitHub Actions Automation | CI/CD scheduled workflow for drift runs | ⬜ Planned |
| 6 | LangGraph AI Analysis | Root cause analysis using LLM agents | ⬜ Planned |
| 7 | Azure Activity Log | Identify who/what mutated Azure resources out-of-band | ⬜ Planned |
| 8 | GitHub Issue / PR Remediation | Human-in-the-loop approval workflows | ⬜ Planned |

---

## 3. Remote Terraform State Architecture (Phase 2)

### The Backend Bootstrap Problem

Terraform remote state backends create a chicken-and-egg problem:
* Remote backend configuration requires an Azure Storage Account and Blob Container to already exist.
* If Terraform manages its own backend storage in the same state, initializing state requires resources that haven't been created yet.

### The Bootstrap Solution

To avoid circular dependencies, the project uses a **dedicated bootstrap module** located at [`terraform/bootstrap`](../terraform/bootstrap):

```mermaid
flowchart TD
    subgraph "Local Execution (Bootstrap)"
        DEV_LOCAL["👤 Developer (az login)"]
        BOOTSTRAP_TF["⚙️ Bootstrap Terraform<br/>(Local State)"]
        DEV_LOCAL --> BOOTSTRAP_TF
    end

    subgraph "Azure State Infrastructure"
        TFSTATE_RG["📦 Azure Resource Group<br/>aitdd-tfstate-rg"]
        TFSTATE_SA["💾 Storage Account<br/>aitddtfstatesa001"]
        TFSTATE_CONTAINER["🗂️ Blob Container<br/>tfstate"]

        TFSTATE_RG --> TFSTATE_SA
        TFSTATE_SA --> TFSTATE_CONTAINER
    end

    BOOTSTRAP_TF -->|"Provisions"| TFSTATE_RG

    subgraph "Environments (Remote State)"
        DEV_ENV["⚙️ terraform/environments/dev<br/>(Remote State)"]
        DEV_ENV -->|"Stores State"| TFSTATE_CONTAINER
    end
```

### Remote State Security Controls

| Security Control | Implementation |
|---|---|
| Dedicated Isolation | State storage is entirely isolated from application storage (`aitddtfstatesa001` vs `aitdddevsa001`). |
| Encryption | Encrypted at rest using Azure-managed keys with TLS 1.2 minimum in transit. |
| Access Control | Container access is private (`container_access_type = "private"`). No public blob access. |
| State Versioning | Storage Blob Versioning enabled for recovery from state corruptions. |
| Soft Delete | Container and Blob 7-day soft-delete retention policies active. |
| No Committed Secrets | Local state and credentials are in `.gitignore`. Only `.terraform.lock.hcl` is committed. |

---

## 4. Azure & CI/CD Authentication (Phase 2)

### Local Development Authentication

Local developers authenticate using the Azure CLI:
```bash
az login
az account set --subscription "<subscription-id>"
```
Terraform automatically inherits these credentials without needing hardcoded secrets or service principal keys.

### GitHub Actions OIDC Authentication

For CI/CD automation, the project relies on **GitHub Workload Identity / OpenID Connect (OIDC)** federated credentials instead of long-lived service principal client secrets.

```mermaid
flowchart TD
    GHA["🐙 GitHub Actions Workflow"]
    ENTRA["🔐 Microsoft Entra ID<br/>(App Registration / SP)"]
    FED_CRED["📜 Federated Identity Credential<br/>(repo:org/repo:ref)"]
    AZURE_ARM["☁️ Azure Resource Manager"]
    TF_REMOTE["💾 Azure Remote State"]

    GHA -->|"1. Requests OIDC Token"| ENTRA
    ENTRA -->|"2. Validates Claims against"| FED_CRED
    ENTRA -->|"3. Issues short-lived Access Token"| GHA
    GHA -->|"4. Executes Terraform Commands"| AZURE_ARM
    AZURE_ARM -->|"5. Reads/Writes State"| TF_REMOTE
```

### Minimum Azure RBAC Permissions

| Identity Role | Scope | Purpose |
|---|---|---|
| **Storage Blob Data Contributor** | `aitddtfstatesa001` Storage Account | Allows Terraform to read, write, and lock state blobs. |
| **Contributor** | `aitdd-dev-main-rg` Resource Group | Allows Terraform to plan and apply application infrastructure changes. |
| **Key Vault Secrets Officer** | `aitdd-dev-kv-001` Key Vault | Allows secret provisioning in dev Key Vault. |

---

## 5. Modular Infrastructure Architecture (Phase 1)

```mermaid
flowchart LR
    subgraph "terraform/environments/dev (Active Minimal Baseline)"
        TFVARS["dev.tfvars<br/>(Resource Groups)"]
        MAIN["main.tf<br/>(Module Composition)"]
        MOD_RG["modules/resource-group<br/>(Active)"]
        TFVARS -->|"feeds"| MAIN
        MAIN -->|"for_each"| MOD_RG
    end

    subgraph "terraform/modules (Preserved Reusable Modules)"
        MOD_NET["modules/network<br/>(Deferred to Phase 3+)"]
        MOD_ST["modules/storage<br/>(Deferred to Phase 3+)"]
        MOD_KV["modules/key-vault<br/>(Deferred to Phase 3+)"]
    end
```

### Data-Driven Design & Incremental Expansion

1. **Active Minimal Foundation**: Phase 1 activates only the Azure Resource Group (`aitdd-dev-main-rg`) in `Central India`. This provides the cleanest, smallest practical infrastructure baseline for establishing remote state and testing deterministic drift detection.
2. **Preserved Reusable Modules**: Modules for Virtual Networks, Subnets, NSGs, Storage Accounts, and Key Vaults are implemented and preserved under `terraform/modules/`. They will be plugged into `dev/main.tf` in subsequent phases to produce rich multi-resource drift scenarios.
3. **Data-Driven Scalability**: When activating additional resources, configurations are added to the corresponding map in `dev.tfvars` without redesigning core architectures.

---

## 6. Resource Naming Convention

```
<project_name>-<environment>-<resource_name>-<resource_type_suffix>
```

| Example | Breakdown |
|---|---|
| `aitdd-tfstate-rg` | Resource group containing Terraform state storage |
| `aitddtfstatesa001` | Dedicated storage account for state (3-24 lowercase alphanumeric) |
| `aitdd-dev-main-rg` | Application dev resource group |
| `aitdd-dev-main-vnet` | Main dev virtual network (10.10.0.0/16) |
| `aitdd-dev-app-snet` | Application subnet (10.10.1.0/24) |
| `aitdd-dev-app-nsg` | Application Network Security Group |
| `aitdddevsa001` | Application dev storage account |
| `aitdd-dev-kv-001` | Application dev Key Vault |
