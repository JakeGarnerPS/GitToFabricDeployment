# Bronze (Raw Ingest) ✅

Purpose: store raw ingested files and notebooks that capture the ingestion logic.

Contents:

- `notebooks/` — ingestion notebooks (e.g., `01_ingest_raw_sales.ipynb`)
- `pipelines/` — pipeline definition(s) that perform the ingest (e.g., `bronze_ingest_pipeline.json`)
- `metadata.json` — dataset manifest describing raw sources and schema

How to use:

1. Place new raw files under `data/` or a cloud storage location referenced by the ingestion pipeline.
2. Confirm `metadata.json` lists the expected source files and sample schema.
3. Run the pipeline `bronze_ingest_pipeline.json` (via Fabric or your orchestration tool) to land data into Bronze.

Notes:
- Bronze data should be immutable and store exactly what was ingested.
- Keep notebooks and pipeline definitions versioned in Git so Fabric can pull them into the workspace.