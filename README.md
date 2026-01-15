# Fabric Medallion Architecture Sample

This repository contains a complete Bronze → Silver → Gold medallion architecture template for Microsoft Fabric.

## Structure

- **data/** – sample raw CSV
- **bronze/** – ingestion notebook + pipeline
- **silver/** – cleansing notebook + pipeline
- **gold/** – curated notebook + pipeline + semantic model

## Deployment

1. Push this repo to GitHub.
2. In Fabric → Workspace → Git Integration → Connect.
3. Select your repo + branch.
4. Choose "Update workspace from Git".
5. Run pipelines in order:
   - bronze_ingestion_pipeline
   - silver_transform_pipeline
   - gold_curated_pipeline

You now have a fully working medallion architecture.
