# Connecting this repo to Microsoft Fabric (Git integration)

This repository follows a Bronze → Silver → Gold medallion layout compatible with Microsoft Fabric workspaces.

Quick mapping:
- `bronze/` → raw ingestion notebooks & pipelines
- `silver/` → cleansing/transformation
- `gold/` → curated datasets, models and reporting artifacts

How to connect:
1. In Microsoft Fabric, open your Workspace and select **Git integration** (or **Connect** → **Git**).
2. Choose **GitHub** and connect using your GitHub account or organization.
3. Select this repository (`JakeGarnerPS/GitToFabricDeployment`) and the branch `main` (or pick a dedicated branch).
4. Pick the repository root as the workspace root (Fabric will discover notebooks and pipelines under `bronze/`, `silver/`, `gold/`).

Notes & best practices:
- Keep pipeline definitions and notebooks in Git so Fabric can update the workspace from the repository.
- Use the provided `Medallion Validation` workflow (badge in `README.md`) to ensure your repo layout and metadata are valid before Fabric pulls.
- If you prefer CI-driven imports, we can add a job to call Fabric APIs to import assets automatically (requires Fabric service principal or API token).

Troubleshooting:
- If Fabric cannot find pipelines or notebooks, verify files are present and the branch is correct.
- Ensure file paths are in the expected `*/notebooks/` and `*/pipelines/` folders.

If you'd like, I can add a sample parameter file (`infra/parameters.json`) and a small script to demonstrate importing assets into Fabric programmatically.