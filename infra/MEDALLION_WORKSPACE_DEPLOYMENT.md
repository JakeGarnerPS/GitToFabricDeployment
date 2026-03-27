# Medallion Workspace Deployment Guide

This guide explains how to deploy the environment-based Fabric setup in this repository using the automation scripts.

## Repository Structure

The repository uses a multi-tier architecture with consolidated assets per tier:

```
Bronze/
  Lakehouses/         # Raw and bronze Fabric lakehouse assets
  DataPipelines/      # Bronze Fabric datapipeline asset
  Notebooks/          # Shared ingestion notebooks
  Pipelines/          # Bronze tier JSON pipeline definition

Silver/
  Lakehouses/         # Silver Fabric lakehouse asset
  DataPipelines/      # Silver Fabric datapipeline asset
  Notebooks/          # Shared transformation notebooks
  Pipelines/          # Silver tier JSON pipeline definition

Gold/
  Lakehouses/         # Gold Fabric lakehouse asset
  DataPipelines/      # Gold Fabric datapipeline asset
  Notebooks/          # Shared curation notebooks
  Pipelines/          # Gold tier JSON pipeline definition
```

The deployment creates these Fabric workspaces by default:
- `dev`
- `prod`
- `feature`
- `staging`

Inside each workspace, the deployment creates these medallion lakehouses:
- `raw_lakehouse`
- `bronze_lakehouse`
- `silver_lakehouse`
- `gold_lakehouse`

It deploys the medallion notebooks from the `Bronze/Notebooks/`, `Silver/Notebooks/`, and `Gold/Notebooks/` folders into each workspace.
It also deploys pipeline definitions from `Bronze/Pipelines/`, `Silver/Pipelines/`, and `Gold/Pipelines/`.

The repository also keeps the corresponding Fabric artifact folders under each tier:
- `Bronze/Lakehouses/` and `Bronze/DataPipelines/`
- `Silver/Lakehouses/` and `Silver/DataPipelines/`
- `Gold/Lakehouses/` and `Gold/DataPipelines/`

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
  "prefix": "medallion",
  "environments": "dev,prod,feature,staging",
  "medallion_lakehouses": "raw,bronze,silver,gold",
  "capacity_id": null,
  "workspace_description": "Managed by deploy_medallion_workspaces.py",
  "notebook_dir": ".",
  "lakehouse_suffix": "lakehouse",
  "workspace_ids_output": "infra/workspace_ids.json"
}
```

Key settings:
- `environments` - Fabric workspaces to create/deploy to (e.g., dev, prod, feature, staging)
- `notebook_dir` - Base directory containing the `Bronze/`, `Silver/`, and `Gold/` notebook folders

You can further customize:
- Workspace names under `workspace_names`
- Lakehouse names under `lakehouse_names`
- Notebook files under `notebooks`
- Pipeline files under `pipelines_by_layer`
- Capacity assignment by setting `capacity_id`

## Step 3: Authenticate with Azure

```bash
az login
```

This signs you in and allows the scripts to retrieve a Fabric API token.

## Step 4: Run the Workspace Deployment Script

### Recommended Command

```bash
python scripts/deploy_medallion_workspaces.py --interactive
```

This uses `--workspace all` by default.

This command will:
- Read `infra/medallion_workspace_params.json`
- Create or reuse the `dev`, `prod`, `feature`, and `staging` workspaces
- Create or reuse the medallion lakehouses inside each workspace
- Deploy all pipelines into each workspace
- Update existing notebooks in place (copy latest code/JSON definition without deleting the notebook item)
- Replace existing pipelines when the source artifact has been redeployed
- Deploy notebooks from `Bronze/Notebooks/`, `Silver/Notebooks/`, and `Gold/Notebooks/`
- Write workspace and lakehouse IDs to `infra/workspace_ids.json`

### Run with Explicit Token

```bash
export FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)

python scripts/deploy_medallion_workspaces.py --token "$FABRIC_TOKEN"
```

### Override the Parameters File

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --params-file infra/medallion_workspace_params.json
```

### Deploy to a Specific Workspace

Use the `--workspace` selector to target one environment or all environments.

Deploy only `dev`:

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace dev
```

Deploy only `prod`:

Deploy all configured environments:

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace all
```

Notes:
- `--workspace all` deploys every environment listed in `environments` from the params file (or `--environments` if provided).
- Valid values are `dev`, `prod`, `feature`, `staging`, and `all`.

### Override Capacity at Runtime

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --capacity-id <fabric-capacity-id>
```

### Skip Notebook Re-deployment

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --skip-existing-notebooks
```

### Notebook Update Behavior (Examples)

By default, notebook deployment is **upsert** behavior:
- If the notebook does not exist in the target workspace, it is created.
- If the notebook already exists, its definition is updated in place using Fabric `updateDefinition`.

This means rerunning deployment to `dev` copies the latest notebook code from the tier notebook folders into the existing `dev` notebook item without deleting it.

Deploy to `dev` and update notebook content in place:

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace dev \
  --skip-existing-pipelines
```

Create-only notebook behavior (do not update existing notebooks):

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --workspace dev \
  --skip-existing-notebooks
```

### Skip Pipeline Re-deployment

```bash
python scripts/deploy_medallion_workspaces.py \
  --interactive \
  --skip-existing-pipelines
```

By default, rerunning the deployment script updates notebooks in place and replaces existing pipelines in the target workspace. Use the skip flags when you want create-only behavior.

## What the Deployment Script Does

The script `scripts/deploy_medallion_workspaces.py` performs the following steps:

1. Reads configuration from `infra/medallion_workspace_params.json`
2. Creates or reuses each environment workspace
3. Optionally assigns each workspace to the configured Fabric capacity
4. Creates or reuses the medallion lakehouses in each workspace
5. Creates or replaces the Bronze, Silver, and Gold pipelines in each workspace
6. Uploads notebook files or updates existing notebook definitions in place in each workspace
7. Writes a manifest file at `infra/workspace_ids.json`

## Output File

After deployment, the script writes:

- `infra/workspace_ids.json`

This file contains:
- Workspace environment name
- Workspace display name
- Workspace ID
- Lakehouse names and IDs for that workspace
- Pipeline names and IDs for that workspace

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

For each workspace (`dev`, `prod`, `feature`, `staging`):

1. Open the workspace in Fabric
2. Verify the workspace exists
3. Confirm these lakehouses exist:
   - `raw_lakehouse`
   - `bronze_lakehouse`
   - `silver_lakehouse`
   - `gold_lakehouse`
4. Verify the notebooks appear in the workspace
5. If capacity assignment was enabled, verify the workspace is attached to the expected capacity

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
- Ensure the `.Notebook` folders listed in `notebooks` exist
- Check for invalid notebook JSON or unsupported content
- If an update call fails in your tenant, rerun once after a short delay (newly created items can be briefly unavailable)
- Confirm your identity has permissions to update notebook definitions in the target workspace

### Capacity Assignment Fails

- Confirm the capacity ID is correct
- Verify the authenticated identity has permission to assign workspaces to that capacity
- If one API endpoint is unavailable in your tenant, the scripts automatically try a fallback endpoint

## Typical Workflow

Use this sequence for a normal deployment:

```bash
az login
python scripts/deploy_medallion_workspaces.py --interactive
python scripts/assign_workspaces_to_capacity.py --interactive --capacity-id <fabric-capacity-id>
```

Or, if the capacity should be applied during deployment:

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
