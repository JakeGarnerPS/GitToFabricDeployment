# Lakehouse Deployment Guide

This guide explains how to deploy a lakehouse and sample data to Microsoft Fabric using the automated deployment script.

## Prerequisites

- **Fabric Workspace** — You have a Fabric workspace set up
- **Workspace ID** — You know your Fabric workspace ID (find it in workspace settings or URL)
- **Azure CLI** — Required for authentication, install [Azure CLI](https://docs.microsoft.com/cli/azure/install-azure-cli)
- **Python 3.8+** — Required to run the deployment script
- **Required Python packages** — `requests` (used by the deployment script)

## Step 1: Install Dependencies

```bash
# Install Azure CLI
pip install azure-cli

# Install required Python packages
pip install requests
```

Or if using the dev container:

```bash
pip install -r requirements.txt  # if available
# or
pip install azure-cli requests
```

## Step 2: Get Your Workspace ID

1. Open your Microsoft Fabric workspace
2. Click the **Settings** icon (⚙️) in the top right
3. Copy the **Workspace ID** from the settings panel
4. Or extract it from the workspace URL: `https://app.fabric.microsoft.com/groups/{WORKSPACE_ID}/...`

## Step 3: Authenticate with Azure

```bash
# Log in to Azure
az login
```

A browser window will open for you to sign in with your Microsoft account. After authentication, Azure CLI will cache your credentials automatically.

> **Note:** You only need to run `az login` once. The credentials are cached and reused for subsequent commands.

## Step 4: Run the Deployment Script

### Basic Usage (Recommended - One-Liner)

Run the deployment script with automatic token retrieval:

```bash
python scripts/deploy_lakehouse.py \
  --workspace-id 7eb1a274-c608-4211-9bfc-3127ac351715 \
  --token $(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)
```

Replace `7eb1a274-c608-4211-9bfc-3127ac351715` with your workspace ID from Step 2.

### Alternative: Store Token in Variable

If you prefer, you can store the token in a shell variable first:

```bash
# Get and store token
export FABRIC_TOKEN=$(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv)

# Use it in the script
python scripts/deploy_lakehouse.py \
  --workspace-id 7eb1a274-c608-4211-9bfc-3127ac351715 \
  --token "$FABRIC_TOKEN"
```

### Advanced Options

```bash
python scripts/deploy_lakehouse.py \
  --workspace-id 7eb1a274-c608-4211-9bfc-3127ac351715 \
  --token $(az account get-access-token --resource https://api.fabric.microsoft.com --query accessToken -o tsv) \
  --lakehouse-name my-custom-lakehouse \
  --sample-data-file data/sample_raw_sales.csv
```

**Options:**
- `--workspace-id` (required): Your Fabric workspace ID
- `--token` (required): Access token (use the Azure CLI command above)
- `--lakehouse-name`: Name for the lakehouse (default: `medallion_lakehouse`)
- `--sample-data-file`: Path to sample data CSV (default: `data/sample_raw_sales.csv`)

## Step 5: Verify in Fabric

1. Go to your Fabric workspace
2. You should see a new lakehouse item called **`medallion_lakehouse`** (or your custom name)
3. Inside the lakehouse, navigate to **Files** → **raw** folder
4. You should see **`sample_raw_sales.csv`** uploaded

## What the Script Does

The deployment script:

1. ✅ Checks if a lakehouse with the given name already exists
2. ✅ Creates a new lakehouse if it doesn't exist
3. ✅ Creates a `raw/` folder in the lakehouse
4. ✅ Uploads `data/sample_raw_sales.csv` to `Files/raw/`

## Troubleshooting

### "Access Denied" or "Unauthorized"

- Ensure your Azure account has **admin or contributor** access to the Fabric workspace
- Try logging in again: `az login`
- Check that your token has not expired

### "Workspace not found"

- Verify the workspace ID is correct
- Ensure the workspace exists and you have access to it

### "File not found: data/sample_raw_sales.csv"

- Run the script from the repository root directory
- Verify the sample data file exists at `data/sample_raw_sales.csv`

### Manual Upload Alternative

If the script fails, you can manually upload the data:

1. Navigate to your lakehouse in Fabric
2. Click **Files** section
3. Click **+ New** → **Folder** and create a folder named `raw`
4. Click **Upload** and select `data/sample_raw_sales.csv`

## Next Steps

Once the lakehouse is deployed:

1. Set up **Git integration** in your Fabric workspace to pull notebooks and pipelines
2. Configure the workspace root as `Medallion/` in Git settings
3. Verify that notebooks appear in the workspace
4. Run the notebooks to load data through the medallion architecture (Bronze → Silver → Gold)

See [FABRIC.md](FABRIC.md) for Git integration setup.

## Automating Deployment (GitHub Actions)

You can also automate this deployment via GitHub Actions. A workflow would:

- Run on push to `road4_CI_CD` branch
- Create the lakehouse automatically
- Upload sample data
- Trigger notebook execution

Contact the team if you'd like to set up automated CI/CD deployment.
