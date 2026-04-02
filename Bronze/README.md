# Bronze Tier

The Bronze tier is responsible for raw data ingestion. This folder contains the Bronze notebooks, JSON pipeline definition, Fabric datapipeline item, and the raw and bronze lakehouse assets.

## Folder Structure

- **Notebooks/**: Shared notebooks for the Bronze tier
  - `01_ingest_raw_sales.Notebook` - Python-based raw sales data ingestion
  - `01_ingest_raw_sales_python.Notebook` - Alternative Python ingestion notebook

- **Pipelines/**: Bronze tier pipeline
  - `bronze_ingest_pipeline.json` - Raw data ingestion pipeline

- **DataPipelines/**: Fabric datapipeline item for the Bronze tier
  - `bronze_ingestion_pipeline.DataPipeline` - Deployable Fabric datapipeline artifact

- **Lakehouses/**: Fabric lakehouse items for the Bronze tier
  - `raw_lakehouse.Lakehouse` - Raw landing lakehouse asset
  - `bronze_lakehouse.Lakehouse` - Bronze processing lakehouse asset

## Notebooks

The notebooks in the `Notebooks/` folder are used to ingest raw data from source systems. They can be invoked from the pipeline or run independently.

## Pipeline

The `bronze_ingest_pipeline.json` orchestrates the data ingestion:
- Calls the Bronze ingestion notebooks
- Loads data into the Bronze lakehouse
- Can be deployed to multiple Fabric workspaces

To customize the pipeline behavior:
- Modify the notebook logic in `Notebooks/`
- Adjust pipeline activities in `Pipelines/bronze_ingest_pipeline.json`

## Fabric Assets

The Fabric item folders in this tier are kept with the source notebooks and JSON definitions:
- `DataPipelines/bronze_ingestion_pipeline.DataPipeline` stores the Fabric datapipeline definition parts
- `Lakehouses/raw_lakehouse.Lakehouse` stores the raw lakehouse metadata
- `Lakehouses/bronze_lakehouse.Lakehouse` stores the bronze lakehouse metadata

## Deployment

When you run the deployment script, Bronze tier workspaces are created for each environment:
- `Road4_Bronze` (Prod)
- `Road4_Bronze_Dev` (Dev)
- `Road4_Bronze_Staging` (Staging)
- `Road4_Bronze_Feature` (Feature)

Each Bronze workspace receives everything discovered in the `Bronze/` folder:
- `raw_lakehouse` — discovered from `Lakehouses/raw_lakehouse.Lakehouse/`
- `bronze_lakehouse` — discovered from `Lakehouses/bronze_lakehouse.Lakehouse/`
- `01_ingest_raw_sales_python` notebook — discovered from `Notebooks/01_ingest_raw_sales_python.Notebook/`
- `01_ingest_raw_sales` notebook — discovered from `Notebooks/01_ingest_raw_sales.Notebook/`
- `bronze_ingestion_pipeline` DataPipeline — discovered from `DataPipelines/bronze_ingestion_pipeline.DataPipeline/`

Items are picked up automatically via `.platform` file scanning. Add a new `.Lakehouse`, `.Notebook`, or `.DataPipeline` folder here and it will be included in the next deployment without any config changes.

Default deployment mode for this repository is Git sync (`--git-sync`).

**Deploy only Bronze tier** (all environments — deploys all items above to all 4 workspaces):
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze
```

**Deploy only Bronze Prod** (`Road4_Bronze`):
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze --workspace Prod
```

**Deploy only Bronze Dev** (`Road4_Bronze_Dev`):
```bash
python scripts/deploy_medallion_workspaces.py --interactive --git-sync --tiers Bronze --workspace Dev
```

