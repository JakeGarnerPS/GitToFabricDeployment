# Fabric notebook source


# CELL ********************

from pyspark.sql.functions import col, to_date

bronze_df = spark.read.format("delta").load("/lakehouse/default/bronze/sales")

silver_df = (
    bronze_df
    .dropDuplicates()
    .withColumn("amount", col("amount").cast("double"))
    .withColumn("order_date", to_date("order_date"))
)

silver_df.write.format("delta").mode("overwrite").save("/lakehouse/default/silver/sales")

