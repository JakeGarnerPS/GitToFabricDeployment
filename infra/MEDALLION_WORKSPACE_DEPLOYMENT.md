# Medallion Workspace Deployment Guide

This guide explains how to deploy the environment-based Fabric setup in this repository using the automation scripts.

The deployment creates these workspaces by default:
- `dev`
- `prod`
- `feature`
- `staging`

Inside each workspace, the deployment creates these medallion lakehouses:
- `raw_lakehouse`
- `bronze_lakehouse`
- `silver_lakehouse`
- `gold_lakehouse`

It also deploys the medallion notebooks from the `Medallion/` folder into each workspace.

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
  "notebook_dir": "Medallion",
  "lakehouse_suffix": "lakehouse",
  "workspace_ids_output": "infra/workspace_ids.json"
}
```

You can customize:
- Workspace names under `workspace_names`
- Lakehouse names under `lakehouse_names`
- Notebook files under `notebooks`
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

This command will:
- Read `infra/medallion_workspace_params.json`
- Create or reuse the `dev`, `prod`, `feature`, and `staging` workspaces
- Create or reuse the medallion lakehouses inside each workspace
- Deploy notebooks from `Medallion/`
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

## What the Deployment Script Does

The script `scripts/deploy_medallion_workspaces.py` performs the following steps:

1. Reads configuration from `infra/medallion_workspace_params.json`
2. Creates or reuses each environment workspace
3. Optionally assigns each workspace to the configured Fabric capacity
4. Creates or reuses the medallion lakehouses in each workspace
5. Uploads the notebook files to each workspace
6. Writes a manifest file at `infra/workspace_ids.json`

## Output File

After deployment, the script writes:

- `infra/workspace_ids.json`

This file contains:
- Workspace environment name
- Workspace display name
- Workspace ID
- Lakehouse names and IDs for that workspace

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

- Verify the notebook directory exists at `Medallion/`
- Ensure the `.ipynb` files listed in `notebooks` exist
- Check for invalid notebook JSON or unsupported content

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
