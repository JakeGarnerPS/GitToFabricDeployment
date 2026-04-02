# Repository Structure - Multi-Tier Organization

This repository follows a medallion architecture organized by Bronze, Silver, and Gold tiers.

## Top-Level Organization

```
Bronze/          # Raw data ingestion tier
Silver/          # Data cleaning and transformation tier
Gold/            # Business-ready curated data marts
```

## Tier Structure (Bronze, Silver, Gold)

Each tier follows this structure:

```
[Tier]/
├── Lakehouses/                # Fabric lakehouse items for the tier
│   └── *.Lakehouse
├── DataPipelines/             # Fabric datapipeline items for the tier
│   └── *.DataPipeline
├── Notebooks/                 # Shared notebooks for this tier
│   └── *.Notebook
├── Pipelines/                 # Pipeline definitions for this tier
│   └── *_pipeline.json
└── README.md
```

## Key Features

- **Tiered Fabric assets**: Each tier groups its Fabric lakehouses and datapipelines with the notebooks and JSON definitions that support them
- **Auto-discovery**: The deployment script scans each tier folder for `.platform` files and automatically deploys every `.Lakehouse`, `.Notebook`, and `.DataPipeline` it finds — no config changes needed when adding new items
- **Shared Notebooks**: Each tier has a single set of notebooks used to process data
- **DataPipeline items**: Each tier has a `DataPipelines/` folder containing deployable Fabric datapipeline artifacts
- **Clear Separation of Concerns**: Bronze handles ingestion, Silver handles transformation, Gold handles curation
- **Scalable**: Drop a new `.Notebook`, `.Lakehouse`, or `.DataPipeline` folder (with a `.platform` file) into any tier and it will be deployed automatically

## Tier Responsibilities

### Bronze
- Raw data ingestion from source systems
- Apply minimal transformation (rename, type casting)
- Store in raw format for traceability
- Contains both `raw_lakehouse.Lakehouse` and `bronze_lakehouse.Lakehouse`

### Silver  
- Data cleaning and quality checks
- Standardization and normalization
- Business logic validation

### Gold
- Create aggregated, curated datasets
- Build business-ready data marts
- Performance optimization for analytics/BI

## Deployment

### Workspace Architecture

The deployment creates **one Fabric workspace per tier per environment** (12 total by default):

```
Tier × Environment Matrix:
  Bronze:  Road4_Bronze, Road4_Bronze_Dev, Road4_Bronze_Staging, Road4_Bronze_Feature
  Silver:  Road4_Silver, Road4_Silver_Dev, Road4_Silver_Staging, Road4_Silver_Feature
  Gold:    Road4_Gold,   Road4_Gold_Dev,   Road4_Gold_Staging,   Road4_Gold_Feature
```

Each workspace contains **only that tier's lakehouse, notebooks, and pipelines**—not all four tiers.

### Deployment Script Options

The `deploy_medallion_workspaces.py` script supports two modes. See [MEDALLION_WORKSPACE_DEPLOYMENT.md](MEDALLION_WORKSPACE_DEPLOYMENT.md) for full details.

**Mode 1 — Git Integration (`--git-sync`) (default):** Connect each workspace to its tier directory in the repo and sync all items from Git. Items are created with correct `logicalId` values from `.platform` files, making the workspace fully Git-connected and ready for future syncs without conflicts.

**Mode 2 — REST API (alternate):** Create items via Fabric REST API. Items are discovered automatically from tier folders via `.platform` file scanning. Notebook `logicalId` references in pipeline definitions are resolved to real deployed IDs.

**Deploy all tiers and all environments (default Git sync):**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync
```

**Deploy all tiers and all environments (alternate REST API):**
```bash
python scripts/deploy_medallion_workspaces.py --interactive
```

**Deploy a single environment across all tiers:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Prod
```

**Deploy a single tier across all environments:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze
```

**Deploy a single tier and environment:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze --workspace Dev
```

**Deploy with Git sync for Dev only:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --workspace Dev
```

### Key Command-Line Arguments

- `--tiers` - Medallion tiers to deploy (Bronze,Silver,Gold by default)
- `--environments` - Environments to deploy per tier (Dev,Prod,Staging,Feature by default)
- `--workspace` - Filter to specific environment across all tiers
- `--prod-environment` - Environment that gets no suffix in workspace names (default: Prod)
- `--prefix` - Workspace naming prefix (default: Road4)
- `--token` - Azure access token for Fabric API
- `--interactive` - Use Azure CLI to get access token
- `--capacity-id` - Optional Fabric capacity ID for workspace assignment
- `--workspaces-only` - Create/verify workspaces only; skip all artifacts
- `--skip-existing-notebooks` - Skip notebooks already in the workspace
- `--skip-existing-pipelines` - Skip pipelines already in the workspace
- `--git-sync` - Use Fabric Git Integration API instead of REST API item creation
- `--git-provider` - Git provider: `GitHub` (default) or `AzureDevOps`
- `--git-org` - GitHub owner or Azure DevOps organisation
- `--git-repo` - Repository name
- `--git-branch` - Branch to sync from (default: current git branch)
- `--git-project` - Azure DevOps project name (AzureDevOps only)
- `--git-credential-type` - Fabric git credentials source (`Automatic` or `ConfiguredConnection`)
- `--git-connection-id` - Fabric Git connection ID (required when using `ConfiguredConnection`)

## Pipeline Configuration

Each tier's pipeline can be customized:
- Modify `[Tier]/Pipelines/*_pipeline.json`
- Changes to notebooks in `[Tier]/Notebooks/` apply across all workspaces
- Use workspace-specific parameters in Fabric for environment-specific behavior

## Fabric Asset Layout

| Tier | Lakehouses | Notebooks | DataPipelines |
|------|-----------|-----------|---------------|
| **Bronze** | `raw_lakehouse`, `bronze_lakehouse` | `01_ingest_raw_sales_python`, `01_ingest_raw_sales` | `bronze_ingestion_pipeline` |
| **Silver** | `silver_lakehouse` | `02_clean_sales_data` | `silver_transform_pipeline` |
| **Gold** | `gold_lakehouse` | `03_curate_sales_mart` | `gold_curated_pipeline` |

All items are discovered automatically at deploy time. To add a new item to a tier, create a folder with a `.platform` file — no script or config changes required.
- `Silver/Lakehouses/` contains `silver_lakehouse.Lakehouse`
- `Silver/DataPipelines/` contains `silver_transform_pipeline.DataPipeline`
- `Gold/Lakehouses/` contains `gold_lakehouse.Lakehouse`
- `Gold/DataPipelines/` contains `gold_curated_pipeline.DataPipeline`

## Migration Notes

- Original `/Medallion` folder structure has been reorganized
- Existing notebooks have been redistributed to appropriate tiers
- Pipelines are now consolidated per tier (no environment-specific copies needed)
- Lakehouse and datapipeline artifact folders now live inside their corresponding tier folders
- Deployment scripts automatically support both old and new structures
