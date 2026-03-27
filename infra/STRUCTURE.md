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
- **Shared Notebooks**: Each tier has a single set of notebooks used to process data
- **Single Pipeline definition per Tier**: Each tier has one JSON pipeline definition that orchestrates the tier's work
- **Clear Separation of Concerns**: Bronze handles ingestion, Silver handles transformation, Gold handles curation
- **Scalable**: Easy to add notebooks, lakehouse assets, or pipeline logic within each tier

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

### Deployment Script Options

The `deploy_medallion_workspaces.py` script deploys all notebooks and pipelines across workspaces:

**Deploy all workspaces:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive
```

**Deploy to specific workspace:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --workspace prod
```

**Deploy with custom parameters:**
```bash
python scripts/deploy_medallion_workspaces.py --interactive --workspace all --capacity-id <id>
```

### Key Command-Line Arguments

- `--workspace` - Filter to specific Fabric workspace (dev/prod/staging/feature/all)
- `--token` - Azure access token for Fabric API
- `--interactive` - Use Azure CLI to get access token
- `--environments` - Comma-separated list of workspaces to deploy to
- `--capacity-id` - Optional Fabric capacity ID for workspace assignment

## Pipeline Configuration

Each tier's pipeline can be customized:
- Modify `[Tier]/Pipelines/*_pipeline.json`
- Changes to notebooks in `[Tier]/Notebooks/` apply across all workspaces
- Use workspace-specific parameters in Fabric for environment-specific behavior

## Fabric Asset Layout

- `Bronze/Lakehouses/` contains `raw_lakehouse.Lakehouse` and `bronze_lakehouse.Lakehouse`
- `Bronze/DataPipelines/` contains `bronze_ingestion_pipeline.DataPipeline`
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
