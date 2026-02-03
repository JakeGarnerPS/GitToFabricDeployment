# Silver (Cleaned / Transformed) ✅

Purpose: store transformed and cleansed data suitable for analytics and downstream enrichment.

Contents:

- `notebooks/` — notebooks that clean and standardize Bronze data (e.g., `02_clean_sales_data.ipynb`)
- `pipelines/` — pipeline definition(s) that perform the transform (e.g., `silver_transform_pipeline.json`)
- `metadata.json` — dataset manifest describing the curated tables and schema

How to use:

1. Reference Bronze datasets as inputs.
2. Keep transformations deterministic and idempotent.
3. Run `silver_transform_pipeline.json` to produce clean tables in Silver.

Notes:
- Silver should include parsed datatypes, reasonably cleaned records, and be ready for aggregation.