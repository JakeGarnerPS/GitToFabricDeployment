# Fabric notebook source


# CELL ********************

from notebookutils import mssparkutils

raw_path = "/lakehouse/default/Files/raw/sample_raw_sales.csv"
table_name = "bronze_sales"

assert mssparkutils.fs.exists(raw_path), f"File not found: {raw_path}"

df = (
    spark.read.format("csv")
    .option("header", "true")
    .option("inferSchema", "true")
    .load(raw_path)
)

(
    df.write
    .format("delta")
    .mode("overwrite")
    .saveAsTable(table_name)
)

print(f"Wrote managed table: {table_name}")
spark.sql(f"SELECT COUNT(*) AS rows FROM {table_name}").show()

