FABRIC_API_BASE_URL = "https://api.fabric.microsoft.com/v1"
DEFAULT_TIERS = ["Bronze", "Silver", "Gold"]
DEFAULT_ENVIRONMENTS = ["Dev", "Prod", "Staging", "Feature"]
DEFAULT_PROD_ENVIRONMENT = "Prod"
DEFAULT_TIER_LAKEHOUSES = {
    "bronze": "bronze_lakehouse",
    "silver": "silver_lakehouse",
    "gold": "gold_lakehouse",
}
DEFAULT_TIER_NOTEBOOKS = {
    "bronze": [
        "Bronze/Notebooks/01_ingest_raw_sales_python.Notebook",
        "Bronze/Notebooks/01_ingest_raw_sales.Notebook",
    ],
    "silver": [
        "Silver/Notebooks/02_clean_sales_data.Notebook",
    ],
    "gold": [
        "Gold/Notebooks/03_curate_sales_mart.Notebook",
    ],
}
DEFAULT_TIER_PIPELINES = {
    "bronze": ["Bronze/Pipelines/bronze_ingest_pipeline.json"],
    "silver": ["Silver/Pipelines/silver_transform_pipeline.json"],
    "gold": ["Gold/Pipelines/gold_curated_pipeline.json"],
}
DEFAULT_PARAMS_FILE = "infra/medallion_workspace_params.json"
DEFAULT_WORKSPACE_IDS_OUTPUT = "infra/workspace_ids.json"
PLATFORM_SCHEMA_URL = (
    "https://developer.microsoft.com/json-schemas/"
    "fabric/gitIntegration/platformProperties/2.0.0/schema.json"
)
ITEM_NAME_RETRYABLE_ERROR = "ItemDisplayNameNotAvailableYet"
