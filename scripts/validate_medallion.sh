#!/usr/bin/env bash
set -euo pipefail

error=0

echo "Validating medallion structure..."

ROOT=$(pwd)
REQUIRED_DIRS=("bronze" "silver" "gold")
for d in "${REQUIRED_DIRS[@]}"; do
  if [ ! -d "$d" ]; then
    echo "ERROR: missing directory $d"
    error=1
  fi
done

# Check metadata files
for layer in bronze silver gold; do
  meta="$layer/metadata.json"
  if [ ! -f "$meta" ]; then
    echo "ERROR: missing $meta"
    error=1
  else
    if ! jq -e . "$meta" >/dev/null 2>&1; then
      echo "ERROR: $meta is not valid JSON"
      error=1
    else
      # check required keys
      for key in name description owner; do
        if [ "$(jq -r ".${key} // empty" "$meta")" == "" ]; then
          echo "ERROR: $meta missing required key: $key"
          error=1
        fi
      done
    fi
  fi
done

# Check pipelines exist
declare -A PD=( [bronze]="bronze/pipelines/bronze_ingest_pipeline.json" [silver]="silver/pipelines/silver_transform_pipeline.json" [gold]="gold/pipelines/gold_curated_pipeline.json" )
for layer in "${!PD[@]}"; do
  path=${PD[$layer]}
  if [ ! -f "$path" ]; then
    echo "WARNING: pipeline $path not found (ensure named pipeline exists)"
  else
    if ! jq -e . "$path" >/dev/null 2>&1; then
      echo "ERROR: $path is not valid JSON"
      error=1
    fi
  fi
done

# Check notebooks existence
NOTEBOOK_CHECKS=("bronze/notebooks/01_ingest_raw_sales.ipynb" "silver/notebooks/02_clean_sales_data.ipynb" "gold/notebooks/03_curate_sales_mart.ipynb")
for nb in "${NOTEBOOK_CHECKS[@]}"; do
  if [ ! -f "$nb" ]; then
    echo "WARNING: notebook $nb not found"
  fi
done

if [ $error -ne 0 ]; then
  echo "Validation completed: FAILED"
  exit 2
else
  echo "Validation completed: OK"
  exit 0
fi