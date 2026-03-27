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

