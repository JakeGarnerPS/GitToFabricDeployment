# Silver Tier

The Silver tier is responsible for data cleaning, transformation, and standardization. This folder contains the Silver notebooks, JSON pipeline definition, Fabric datapipeline item, and the Silver lakehouse asset.

## Folder Structure

- **Notebooks/**: Shared notebooks for the Silver tier
  - `02_clean_sales_data.Notebook` - Data cleaning and transformation notebook

- **Pipelines/**: Silver tier pipeline
  - `silver_transform_pipeline.json` - Data transformation and cleaning pipeline

- **DataPipelines/**: Fabric datapipeline item for the Silver tier
  - `silver_transform_pipeline.DataPipeline` - Deployable Fabric datapipeline artifact

- **Lakehouses/**: Fabric lakehouse item for the Silver tier
  - `silver_lakehouse.Lakehouse` - Silver processing lakehouse asset

## Notebooks

The notebooks in the `Notebooks/` folder are used to clean and transform Bronze data. They can be invoked from the pipeline or run independently.

## Pipeline

The `silver_transform_pipeline.json` orchestrates the data transformation:
- Calls the Silver transformation notebooks
- Reads from Bronze lakehouse
- Writes to Silver lakehouse
- Can be deployed to multiple Fabric workspaces

To customize the pipeline behavior:
- Modify the notebook logic in `Notebooks/`
- Adjust pipeline activities in `Pipelines/silver_transform_pipeline.json`

## Fabric Assets

The Fabric item folders in this tier are kept with the source notebooks and JSON definitions:
- `DataPipelines/silver_transform_pipeline.DataPipeline` stores the Fabric datapipeline definition parts
- `Lakehouses/silver_lakehouse.Lakehouse` stores the silver lakehouse metadata

