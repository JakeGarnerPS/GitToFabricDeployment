# Medallion Workspace Deployment Guide

This guide explains how to deploy the tier-per-environment Fabric setup in this repository using the automation scripts.

## Deployment Modes

The script supports two deployment modes:

### Mode 1 — Git Integration (`--git-sync`) (default)

Connects each workspace to its tier directory in this Git repo (`Bronze/`, `Silver/`, `Gold/`) using the Fabric Git Integration API, then calls `updateFromGit (PreferRemote)` to create all items from the `.platform` files.

- Items are created with the **correct `logicalId` values** from `.platform` files
- The workspace is **fully Git-connected** after deployment — subsequent Git syncs work without conflicts
- Fabric handles all notebook reference resolution automatically
- Requires a GitHub (or Azure DevOps) connection configured in your Fabric tenant

```
Workspace  →  Git repo directory
────────────────────────────────────────────────────────────
Road4_Bronze_Dev  →  Bronze/   (branch: road4_example_project)
Road4_Silver_Dev  →  Silver/
Road4_Gold_Dev    →  Gold/
```

### Mode 2 — REST API (alternate)

Creates workspaces and deploys each item (lakehouses, notebooks, pipelines) individually via the Fabric REST API. Items receive Fabric-generated GUIDs as their item IDs.

- Suitable for testing and CI pipelines where Git integration is not configured
- `notebookId` values in pipeline definitions are automatically resolved to the correct deployed IDs

## Deployment Model

The deployment creates **one Fabric workspace per tier per environment**:

| Tier | Prod | Dev | Staging | Feature |
|------|------|-----|---------|----------|
| **Bronze** | `Road4_Bronze` | `Road4_Bronze_Dev` | `Road4_Bronze_Staging` | `Road4_Bronze_Feature` |
| **Silver** | `Road4_Silver` | `Road4_Silver_Dev` | `Road4_Silver_Staging` | `Road4_Silver_Feature` |
| **Gold** | `Road4_Gold` | `Road4_Gold_Dev` | `Road4_Gold_Staging` | `Road4_Gold_Feature` |

Each workspace contains:
- All lakehouses discovered in that tier's `Lakehouses/` folder (e.g., both `raw_lakehouse` and `bronze_lakehouse` in Bronze workspaces)
- All notebooks discovered in that tier's `Notebooks/` folder
- All DataPipelines discovered in that tier's `DataPipelines/` folder

Items are discovered automatically by scanning for `.platform` files — **no config changes needed when you add new items** to a tier folder.

## Repository Structure

The repository uses a multi-tier architecture with consolidated assets per tier:

```
Bronze/
  Lakehouses/
    raw_lakehouse.Lakehouse/          # Raw landing lakehouse
    bronze_lakehouse.Lakehouse/       # Bronze processing lakehouse
  DataPipelines/
    bronze_ingestion_pipeline.DataPipeline/   # Fabric datapipeline item
  Notebooks/
    01_ingest_raw_sales.Notebook/     # Raw sales ingestion notebook
    01_ingest_raw_sales_python.Notebook/
  Pipelines/
    bronze_ingest_pipeline.json       # Fallback JSON pipeline definition

Silver/
  Lakehouses/
    silver_lakehouse.Lakehouse/
  DataPipelines/
    silver_transform_pipeline.DataPipeline/
  Notebooks/
    02_clean_sales_data.Notebook/
  Pipelines/
    silver_transform_pipeline.json

Gold/
  Lakehouses/
    gold_lakehouse.Lakehouse/
  DataPipelines/
    gold_curated_pipeline.DataPipeline/
  Notebooks/
    03_curate_sales_mart.Notebook/
  Pipelines/
    gold_curated_pipeline.json
```

### Auto-Discovery

The deployment script **automatically discovers** all Fabric items in each tier folder by scanning for `.platform` files. Every `.Lakehouse`, `.Notebook`, and `.DataPipeline` folder that contains a `.platform` file is picked up and deployed — no configuration changes are needed when you add new items.

| Tier | Discovered lakehouses | Discovered notebooks | Discovered DataPipelines |
|------|----------------------|----------------------|--------------------------|
| **Bronze** | `raw_lakehouse`, `bronze_lakehouse` | `01_ingest_raw_sales_python`, `01_ingest_raw_sales` | `bronze_ingestion_pipeline` |
| **Silver** | `silver_lakehouse` | `02_clean_sales_data` | `silver_transform_pipeline` |
| **Gold** | `gold_lakehouse` | `03_curate_sales_mart` | `gold_curated_pipeline` |

The `tier_lakehouses`, `tier_notebooks`, and `tier_pipelines` settings in the params file act as a **fallback** for any items not in the folder structure. Folder discovery always takes precedence.

## Prerequisites

- **Microsoft Fabric access** — You can create workspaces and lakehouses in your Fabric tenant
- **Capacity permissions** — Required if you want to assign workspaces to a Fabric capacity
- **Azure CLI** — Install [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- **Python 3.8+** — Required to run the scripts
- **Required Python package** — `requests`

## Step 1: Install Dependencies

```bash
pip install requests
```

If Azure CLI is not already installed in your environment, install it separately.

## Step 2: Review the Parameters File

Open the parameters file:

- `infra/medallion_workspace_params.json`

Default values:

```json
{
  "prefix": "Road4",
  "tiers": "Bronze,Silver,Gold",
  "environments": "Dev,Prod,Staging,Feature",
  "prod_environment": "Prod",
  "capacity_id": "667C93CA-2177-448B-B39B-EA656D994404",
  "workspace_description": "Managed by deploy_medallion_workspaces.py",
  "notebook_dir": ".",
  "workspace_ids_output": "infra/workspace_ids.json",
  "workspace_names": { ... },
  "tier_lakehouses": { ... },
  "tier_notebooks": { ... },
  "tier_pipelines": { ... }
}
```

Key settings:
- `tiers` - Medallion tiers to deploy per environment (Bronze, Silver, Gold)
- `environments` - Environment names to create per tier (Dev, Prod, Staging, Feature)
- `prod_environment` - Which environment gets no suffix in workspace names (default: Prod)
- `notebook_dir` - Base directory containing the `Bronze/`, `Silver/`, and `Gold/` notebook folders

You can further customize:
- Workspace names under `workspace_names` (keyed as `{Tier}_{Environment}`, e.g., `Bronze_Prod`)
- Lakehouse names under `tier_lakehouses` (keyed by tier)
- Notebook files under `tier_notebooks` (keyed by tier)
- Pipeline files under `tier_pipelines` (keyed by tier)
- Capacity assignment by setting `capacity_id`

## Step 3: Authenticate with Azure

```bash
az login
```

This signs you in and allows the scripts to retrieve a Fabric API token.

## Step 4: Run the Workspace Deployment Script

### Default Mode — Git Integration (`--git-sync`)

#### Deploy All Tiers, All Environments

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync
```

#### Deploy a Single Environment Across All Tiers

**Deploy Dev environment only** (Bronze_Dev, Silver_Dev, Gold_Dev):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev
```

**Deploy Prod environment only** (Road4_Bronze, Road4_Silver, Road4_Gold):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Prod
```

### Alternate Mode — REST API

#### Deploy All Tiers, All Environments

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive
```

#### Deploy a Single Environment Across All Tiers

**Deploy Dev environment only** (Bronze_Dev, Silver_Dev, Gold_Dev):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --workspace Dev
```

**Deploy Prod environment only** (Road4_Bronze, Road4_Silver, Road4_Gold):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --workspace Prod
```

**Deploy Staging and Feature environments only**:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --workspace Staging
python scripts/deploy_medallion_workspaces.py --interactive --workspace Feature
```

### Deploy Specific Tiers Only

**Deploy Bronze tier only** (all environments):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --tiers Bronze
```

**Deploy Bronze and Silver tiers** (all environments):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py --interactive --tiers Bronze,Silver
```

### Combine Tier and Environment Filters

**Deploy Bronze tier, Dev environment only** (Road4_Bronze_Dev):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --tiers Bronze \
  --workspace Dev
```

**Deploy Bronze and Silver tiers, Prod environment only** (Road4_Bronze, Road4_Silver):

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --tiers Bronze,Silver \
  --workspace Prod
```

**Deploy all tiers, Dev and Staging only**:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --environments Dev,Staging
```

### Run with Explicit Token

> REST API example (alternate mode):

```bash
export FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)

python scripts/deploy_medallion_workspaces.py --token "$FABRIC_TOKEN"
```

### Override the Parameters File

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --params-file infra/medallion_workspace_params.json
```

### Override Tiers or Environments at Runtime

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --tiers Silver,Gold
```

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --environments Dev,Prod
```

### Override Capacity at Runtime

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --capacity-id <fabric-capacity-id>
```

### Skip Notebook Re-deployment

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --skip-existing-notebooks
```

### Notebook Update Behavior

By default, notebook deployment is **upsert** behavior:
- If the notebook does not exist in the target workspace, it is created.
- If the notebook already exists, its definition is updated in place using Fabric `updateDefinition`.

This means rerunning deployment copies the latest notebook code from the tier notebook folders into the existing tier-specific workspace notebooks without deleting them.

**Deploy Dev environment and update notebook content in place**:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace Dev
```

**Create-only notebook behavior (do not update existing notebooks)**:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace Dev \
  --skip-existing-notebooks
```

### Skip Pipeline Re-deployment

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --skip-existing-pipelines
```

By default, rerunning the deployment script updates notebooks in place and replaces existing pipelines in the target workspace. Use the skip flags when you want create-only behavior.

### Workspaces Only (Skip Lakehouses, Notebooks, and Pipelines)

Use `--workspaces-only` to provision (or verify) workspaces and optionally assign capacity without touching any lakehouses, notebooks, or pipelines:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspaces-only
```

Combine with `--workspace` to target a single environment:

> REST API example (alternate mode):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace dev \
  --workspaces-only
```

This is useful when you want to pre-create workspaces and assign them to a capacity before deploying any artifacts.

---

### Additional Git Integration Examples (`--git-sync`)

`--git-sync` is the default deployment path for this repository because it keeps workspace items aligned to Git `logicalId` values and avoids post-deploy sync conflicts.

Git connection details are read from `infra/medallion_workspace_params.json` (`git_connection` key) or supplied via CLI flags.

#### Git credentials for `--git-sync`

`deploy_medallion_workspaces.py` supports these Fabric `myGitCredentials.source` values:

- `Automatic`
- `ConfiguredConnection`

For GitHub tenants where `Automatic` is not supported, use `ConfiguredConnection` and provide a Fabric connection ID:

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --git-sync \
  --git-credential-type ConfiguredConnection \
  --git-connection-id <fabric-connection-id>
```

#### Sync all tiers and environments from Git

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync
```

#### Sync Dev environments only (Bronze/Silver/Gold Dev)

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev
```

#### Sync a single tier from Git

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze
```

#### Override Git connection at runtime

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --git-sync \
  --git-provider GitHub \
  --git-org JakeGarnerPS \
  --git-repo GitToFabricDeployment \
  --git-branch road4_example_project
```

#### Azure DevOps repo

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --git-sync \
  --git-provider AzureDevOps \
  --git-org MyOrg \
  --git-project MyProject \
  --git-repo MyRepo \
  --git-branch main
```

> **Note:** `--git-sync` requires a GitHub or Azure DevOps connection to be configured in your Fabric tenant settings before running.
>
> **Note:** If you get `GitCredentialsConfigurationNotSupported` with `source=Automatic`, switch to `--git-credential-type ConfiguredConnection` and pass `--git-connection-id`.

## What the Deployment Script Does

### Mode 1 — Git Integration (`--git-sync`) (default)

1. Reads configuration from `infra/medallion_workspace_params.json`
2. For each tier (`Bronze`, `Silver`, `Gold`), scans the tier folder for Fabric items:
   - Walks `Bronze/`, `Silver/`, `Gold/` looking for `.platform` files
   - Auto-discovers all `.Lakehouse`, `.Notebook`, and `.DataPipeline` item folders
   - Captures the `logicalId` from each `.platform` file
3. For each tier and environment combination:
   - Creates or reuses the tier-environment workspace (e.g., `Road4_Bronze_Dev`)
   - Optionally assigns the workspace to the configured Fabric capacity
4. For each tier-environment workspace *(skipped with `--workspaces-only`)*:
   - Uploads or updates **all discovered notebooks**; builds a `logicalId → deployedId` map
   - Creates or reuses **all discovered lakehouses**
   - Deploys **all discovered DataPipeline folders** — `notebookId` values in `pipeline-content.json` are resolved using the `logicalId → deployedId` map so references match the newly deployed notebooks
5. Writes a manifest file at `infra/workspace_ids.json`

### Mode 2 — REST API (alternate)

1. Reads configuration from `infra/medallion_workspace_params.json`
2. For each tier and environment combination:
   - Creates or reuses the tier-environment workspace
   - Optionally assigns the workspace to capacity
   - Connects the workspace to this Git repo at the tier directory (e.g., `Bronze/` for Bronze workspaces)
   - Calls `initializeConnection (PreferRemote)` (first run) or `updateFromGit (PreferRemote)` (subsequent runs)
   - Fabric creates/updates all items from the `.platform` files with correct `logicalId` values
   - Notebook ID references in pipeline definitions are resolved automatically by Fabric
3. Lists all items in each workspace to populate `infra/workspace_ids.json`

**Result:** 12 workspaces (3 tiers × 4 environments) or a subset if filtered by `--tiers` or `--workspace`.

## Output File

After deployment, the script writes:

- `infra/workspace_ids.json`

This file contains:
- Tier and environment for each workspace
- Workspace display name (e.g., `Road4_Bronze_Dev`)
- Workspace ID (GUID)
- Lakehouse names and IDs for that workspace (tier-specific)
- Pipeline names and IDs for that workspace (tier-specific)

You can use this file for follow-up automation, including bulk capacity assignment.

## Step 5: Assign Workspaces to a Capacity Separately

If you did not set `capacity_id` during deployment, you can assign all deployed workspaces later with:

```bash
python scripts/assign_workspaces_to_capacity.py \
  --interactive \
  --capacity-id <fabric-capacity-id>
```

This script reads `infra/workspace_ids.json` and assigns each workspace to the target capacity.

### Dry Run

```bash
python scripts/assign_workspaces_to_capacity.py \
  --interactive \
  --capacity-id <fabric-capacity-id> \
  --dry-run
```

### Custom Input or Output File

```bash
python scripts/assign_workspaces_to_capacity.py \
  --interactive \
  --capacity-id <fabric-capacity-id> \
  --workspace-ids-file infra/workspace_ids.json \
  --results-file infra/workspace_capacity_assignment_results.json
```

## Step 6: Verify in Fabric

After deployment, verify the workspace structure in Fabric:

**For each tier and environment combination**, navigate to the corresponding workspace (e.g., `Road4_Bronze_Dev`, `Road4_Silver_Prod`, etc.):

1. Open the workspace in Fabric
2. Verify the workspace exists and is named correctly
3. Verify **only the tier's lakehouse** exists (e.g., `bronze_lakehouse` in Bronze workspaces)
4. Verify the tier's notebooks appear (e.g., Bronze ingestion notebooks in `Road4_Bronze_Dev`)
5. Verify the tier's pipelines appear (e.g., bronze ingest pipeline in `Road4_Bronze_Dev`)
6. If capacity assignment was enabled, verify the workspace is attached to the expected capacity

**Example verification checklist:**
- `Road4_Bronze` → contains `raw_lakehouse` + `bronze_lakehouse` + Bronze notebooks + `bronze_ingestion_pipeline`
- `Road4_Bronze_Dev` → same contents as `Road4_Bronze` (same tier, different environment)
- `Road4_Silver` → contains `silver_lakehouse` + Silver notebooks + `silver_transform_pipeline`
- `Road4_Gold_Staging` → contains `gold_lakehouse` + Gold notebooks + `gold_curated_pipeline`

## Troubleshooting

### Unauthorized or Access Denied

- Run `az login` again
- Verify your account has permissions to create Fabric workspaces
- Verify your account can create lakehouses in the target tenant
- If assigning capacity, verify you have rights to place workspaces onto that capacity

### Workspace Creation Fails

- Check whether the workspace name already exists in a conflicting form
- Try explicit names in `workspace_names`
- Verify the Fabric API token is valid

### Lakehouse Creation Fails

- Confirm the workspace exists and is visible in Fabric
- Re-run the script after a short delay because workspace creation can be asynchronous

### Notebook Deployment Fails

- Verify the notebook base directory exists and contains `Bronze/Notebooks/`, `Silver/Notebooks/`, and `Gold/Notebooks/`
- Each `.Notebook` folder must contain a `.platform` file (used for auto-discovery) and a `notebook-content.py` file
- Check for invalid notebook content in `notebook-content.py`
- If an update call fails in your tenant, rerun once after a short delay (newly created items can be briefly unavailable)
- Confirm your identity has permissions to update notebook definitions in the target workspace

### Capacity Assignment Fails

- Confirm the capacity ID is correct
- Verify the authenticated identity has permission to assign workspaces to that capacity
- If one API endpoint is unavailable in your tenant, the scripts automatically try a fallback endpoint

## Typical Workflow

Use this sequence for a normal deployment:

```bash
# Step 1: Authenticate
az login

# Step 2: Deploy all tiers and environments (default: Git sync)
python scripts/deploy_medallion_workspaces.py --interactive --git-sync

# Step 3: (Optional) Assign workspaces to capacity if not done during deployment
python scripts/assign_workspaces_to_capacity.py --interactive --capacity-id <fabric-capacity-id>
```

Or, to deploy incrementally:

```bash
# Deploy Prod environment first (all tiers, Git sync)
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Prod

# Deploy Dev environment (all tiers, Git sync)
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev

# Deploy Staging and Feature later
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --environments Staging,Feature
```

Or, to deploy one tier at a time:

```bash
# Deploy Bronze tier first (all environments)
python scripts/deploy_medallion_workspaces.py --interactive --tiers Bronze

# Deploy Silver and Gold tiers later
python scripts/deploy_medallion_workspaces.py --interactive --tiers Silver,Gold
```

```bash
az login
python scripts/deploy_medallion_workspaces.py --interactive --capacity-id <fabric-capacity-id>
```

## Related Files

- `scripts/deploy_medallion_workspaces.py`
- `scripts/assign_workspaces_to_capacity.py`
- `infra/medallion_workspace_params.json`
- `infra/workspace_ids.json`
- `infra/workspace_capacity_assignment_results.json`
