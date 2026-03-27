# Gold Tier

The Gold tier is responsible for creating curated, business-ready data marts. This folder contains the Gold notebooks, JSON pipeline definition, Fabric datapipeline item, and the Gold lakehouse asset.

## Folder Structure

- **Notebooks/**: Shared notebooks for the Gold tier
  - `03_curate_sales_mart.Notebook` - Sales data mart curation notebook

- **Pipelines/**: Gold tier pipeline
  - `gold_curated_pipeline.json` - Data mart curation pipeline

- **DataPipelines/**: Fabric datapipeline item for the Gold tier
  - `gold_curated_pipeline.DataPipeline` - Deployable Fabric datapipeline artifact

- **Lakehouses/**: Fabric lakehouse item for the Gold tier
  - `gold_lakehouse.Lakehouse` - Gold curated lakehouse asset

## Notebooks

The notebooks in the `Notebooks/` folder are used to create curated datasets and data marts. They can be invoked from the pipeline or run independently.

## Pipeline

The `gold_curated_pipeline.json` orchestrates the data curation:
- Calls the Gold curation notebooks
- Reads from Silver lakehouse
- Writes final data marts to Gold lakehouse
- Can be deployed to multiple Fabric workspaces

To customize the pipeline behavior:
- Modify the notebook logic in `Notebooks/`
- Adjust pipeline activities in `Pipelines/gold_curated_pipeline.json`

## Fabric Assets

The Fabric item folders in this tier are kept with the source notebooks and JSON definitions:
- `DataPipelines/gold_curated_pipeline.DataPipeline` stores the Fabric datapipeline definition parts
- `Lakehouses/gold_lakehouse.Lakehouse` stores the gold lakehouse metadata

## Deployment

When you run the deployment script, Gold tier workspaces are created for each environment:
- `Road4_Gold` (Prod)
- `Road4_Gold_Dev` (Dev)
- `Road4_Gold_Staging` (Staging)
- `Road4_Gold_Feature` (Feature)

Each Gold workspace receives everything discovered in the `Gold/` folder:
- `gold_lakehouse` — discovered from `Lakehouses/gold_lakehouse.Lakehouse/`
- `03_curate_sales_mart` notebook — discovered from `Notebooks/03_curate_sales_mart.Notebook/`
- `gold_curated_pipeline` DataPipeline — discovered from `DataPipelines/gold_curated_pipeline.DataPipeline/`

Items are picked up automatically via `.platform` file scanning. Add a new `.Lakehouse`, `.Notebook`, or `.DataPipeline` folder here and it will be included in the next deployment without any config changes.

Default deployment mode for this repository is Git sync (`--git-sync`).

**Deploy only Gold tier** (all environments):
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Gold
```

**Deploy Gold tier, Prod and Staging environments**:
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Gold --environments Prod,Staging
```

**Deploy only Gold Prod** (`Road4_Gold`):
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Gold --workspace Prod
```

