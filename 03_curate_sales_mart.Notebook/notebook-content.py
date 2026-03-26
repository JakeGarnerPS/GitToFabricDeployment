# Fabric notebook source


# CELL ********************

from pyspark.sql.functions import sum

silver_df = spark.read.format("delta").load("/lakehouse/default/silver/sales")

gold_df = (
    silver_df
    .groupBy("customer_id")
    .agg(sum("amount").alias("total_sales"))
)

gold_df.write.format("delta").mode("overwrite").save("/lakehouse/default/gold/customer_sales")

