# Fabric notebook source

# METADATA ********************

# META {
# META   "kernel_info": {
# META     "name": "synapse_pyspark"
# META   },
# META   "dependencies": {
# META     "lakehouse": {
# META       "default_lakehouse": "22da72ec-b312-4aea-8476-11242d0532b0",
# META       "default_lakehouse_name": "bronze_lakehouse",
# META       "default_lakehouse_workspace_id": "1d9aeb3a-de3d-4124-85d0-999ec07dc670",
# META       "known_lakehouses": [
# META         {
# META           "id": "22da72ec-b312-4aea-8476-11242d0532b0"
# META         }
# META       ]
# META     }
# META   }
# META }

# CELL ********************

#raw_path = "/lakehouse/default/Files/raw/sample_raw_sales.csv"
raw_path = "abfss://1d9aeb3a-de3d-4124-85d0-999ec07dc670@onelake.dfs.fabric.microsoft.com/22da72ec-b312-4aea-8476-11242d0532b0/Files/raw/sample_raw_sales.csv"

df = (
    spark.read.format("csv")
    .option("header", "true")
    .load(raw_path)
)

# Write DataFrame as managed Delta Lakehouse table
df.write.format("delta").mode("overwrite").saveAsTable("raw_sales")

# METADATA ********************

# META {
# META   "language": "python",
# META   "language_group": "synapse_pyspark"
# META }
