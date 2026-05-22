# Connecting this repo to Microsoft Fabric (Git integration)

This repository follows a Bronze → Silver → Gold medallion layout compatible with Microsoft Fabric workspaces.

Quick mapping:
- `Bronze/` → raw ingestion notebooks, datapipelines, and lakehouses
- `Silver/` → cleansing/transformation notebooks, datapipelines, and lakehouses
- `Gold/` → curated datasets, models, datapipelines, and reporting artifacts

How to connect:
1. In GitHub create a PAT (Personal access token) with read/write permissions
2. In Microsoft Fabric, open your Workspace and select **Git integration** (or **Connect** → **Git**).
3. Choose **GitHub** and connect using your GitHub account or organization.
4. Select this repository (`JakeGarnerPS/GitToFabricDeployment`) and the branch you want to use.
5. Pick the repository root as the workspace root (Fabric will discover notebooks and pipelines under `Bronze/`, `Silver/`, `Gold/`).

Notes & best practices:
- Keep pipeline definitions and notebooks in Git so Fabric can update the workspace from the repository.
- Use the provided `Medallion Validation` workflow (badge in `README.md`) to ensure your repo layout and metadata are valid before Fabric pulls.
- If you prefer CI-driven imports, we can add a job to call Fabric APIs to import assets automatically (requires Fabric service principal or API token).
- Each tier (Bronze, Silver, Gold) has its own `Lakehouses/`, `DataPipelines/`, `Notebooks/`, and `Pipelines/` folders for organization.

Troubleshooting:
- If Fabric cannot find pipelines or notebooks, verify files are present and the branch is correct.
- Ensure file paths are in the expected `Bronze/Lakehouses/`, `Bronze/DataPipelines/`, `Bronze/Notebooks/`, `Bronze/Pipelines/` structure, with the equivalent layout under `Silver/` and `Gold/`.

If you'd like, I can add a sample parameter file (`infra/parameters.json`) and a small script to demonstrate importing assets into Fabric programmatically.