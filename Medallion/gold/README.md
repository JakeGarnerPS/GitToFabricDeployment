# Gold (Curated / Reporting) ✅

Purpose: provide curated datasets, semantic models, and artifacts ready for BI and ML consumption.

Contents:

- `notebooks/` — notebooks that assemble curated datasets and models (e.g., `03_curate_sales_mart.ipynb`)
- `pipelines/` — pipeline definition(s) that orchestrate final aggregation and modeling (e.g., `gold_curated_pipeline.json`)
- `models/` — semantic model artifacts (Power BI model files) and model metadata
- `metadata.json` — dataset manifest describing curated tables, measures and consumers

How to use:

1. Build on Silver datasets.
2. Keep models and measures documented in `metadata.json`.
3. Run `gold_curated_pipeline.json` to produce final artifacts.

Notes:
- Gold artifacts should be stable and versioned.