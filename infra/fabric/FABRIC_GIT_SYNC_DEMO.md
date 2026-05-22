# Fabric Git Sync Deployment Demo Guide

This guide gives you a repeatable demo flow to deploy this repository to a Microsoft Fabric tenant using Git sync.

## What this demo covers

- Creating a GitHub personal access token (PAT)
- Linking Fabric workspaces to this GitHub repository
- Running deployment with Git sync (`--git-sync`)
- Verifying that Bronze, Silver, and Gold artifacts were created

## Repository and branch used in this demo

- Repository: `JakeGarnerPS/GitToFabricDeployment`
- Suggested branch for demo: `road4_example_project`

## Prerequisites

- You have Fabric admin/contributor permissions to create workspaces.
- You can access the target Fabric capacity (if assigning capacity during deployment).
- Azure CLI is installed and you can run `az login`.
- Python 3.8+ is installed.
- Python package `requests` is installed.

Install dependency if needed:

```bash
pip install requests
```

## 1. Create a GitHub PAT for Fabric Git integration

Fabric needs credentials to connect to GitHub.

1. In GitHub, go to **Settings -> Developer settings -> Personal access tokens**.
2. Create either:
   - A fine-grained token scoped to this repository, or
   - A classic token (`repo` scope) if your org policy still uses classic tokens.
3. Set an expiration suitable for your demo window.
4. Copy the token value immediately (GitHub only shows it once).

Recommended minimum permissions for the repo:

- Repository metadata: Read
- Repository contents: Read and write
- Pull requests: Read (optional but useful for team workflows)

## 2. Create or verify a Git connection in Fabric

1. Open the Fabric tenant in browser: `https://app.fabric.microsoft.com`.
2. Open a target workspace.
3. Select **Workspace settings -> Git integration** (wording can vary slightly by UI version).
4. Choose **GitHub** as provider.
5. Authenticate and provide the PAT from Step 1 when prompted.
6. Select:
   - Organization/user: `JakeGarnerPS`
   - Repository: `GitToFabricDeployment`
   - Branch: `road4_example_project` (or your demo branch)

If your tenant requires a centrally managed connection, ask the Fabric admin to pre-create the connection and grant you access.

## 3. Map Fabric workspaces to repo folders

For this repo, each workspace should point to the tier folder that matches it:

- Bronze workspace -> `Bronze/`
- Silver workspace -> `Silver/`
- Gold workspace -> `Gold/`

If you are demoing multiple environments (Dev/Prod/Staging/Feature), keep the same folder mapping per tier.

## 4. Authenticate locally for deployment scripts

From the repo root:

```bash
az login
```

Optional: verify active account/subscription before deployment.

## 5. Deploy with Git sync mode

Run the deployment script in Git mode:

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync
```

Useful variations:

Deploy only one environment across all tiers:

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev
```

Deploy selected tiers only:

```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze,Silver
```

What `--git-sync` does in this repo:

- Creates or reuses target Fabric workspaces
- Connects each workspace to the matching repo folder
- Calls Fabric `updateFromGit` with remote-preferred behavior
- Lets Fabric materialize lakehouses, notebooks, and DataPipelines from source control

## 6. Verify deployment in Fabric

In each workspace, confirm these artifact groups exist:

- Lakehouses from `Lakehouses/`
- Notebooks from `Notebooks/`
- DataPipelines from `DataPipelines/`

Quick checks for this repo:

- Bronze workspace includes `raw_lakehouse` and `bronze_lakehouse`
- Silver workspace includes `silver_lakehouse`
- Gold workspace includes `gold_lakehouse`

## 7. Demo the Git sync loop

1. Make a small change in Git (for example, update a notebook cell or pipeline metadata).
2. Commit and push to the connected branch.
3. In Fabric workspace Git integration, run **Update from Git** (or let your configured sync flow run).
4. Show that the workspace item updates from source control.

## Common issues and fixes

- PAT rejected:
  - Recreate token and confirm scopes/permissions and expiration.
  - Check org policies that may block classic PAT usage.
- Branch/folder not found:
  - Verify exact branch name and workspace folder mapping (`Bronze/`, `Silver/`, `Gold/`).
- Sync conflicts:
  - Resolve in Git first, then run update from Git again.
- Missing artifacts after sync:
  - Confirm the relevant `.platform` and item content files are committed in the tier folder.

## Helpful related docs in this repo

- `infra/FABRIC.md`
- `infra/MEDALLION_WORKSPACE_DEPLOYMENT.md`
- `infra/LAKEHOUSE_DEPLOYMENT.md`
- `infra/NOTEBOOK_DEPLOYMENT_API.md`
