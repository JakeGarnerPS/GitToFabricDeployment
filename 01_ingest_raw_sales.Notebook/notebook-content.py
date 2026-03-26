# Fabric notebook source


# CELL ********************

raw_path = "/lakehouse/default/Files/raw/sample_raw_sales.csv"

df = (
    spark.read.format("csv")
    .option("header", "true")
    .load(raw_path)
)

df.write.format("delta").mode("overwrite").save("/lakehouse/default/bronze/sales")

