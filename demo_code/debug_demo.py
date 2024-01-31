import os

import pyspark.sql.functions as f
from pyspark.sql import DataFrame, SparkSession
from pyspark.sql.types import StringType

host = os.environ.get("DEBUG_HOST")
port = os.environ.get("DEBUG_PORT")
if host and port:
    print("=== ENABLING DEBUG MODE ===")
    import pydevd_pycharm

    pydevd_pycharm.settrace(host, port=int(port), stdoutToServer=True, stderrToServer=True)


def convert_to_camel_case(location):
    parts = location.split(",", 1)
    return f"{parts[0].title()},{parts[1]}"


def load_data(ss: SparkSession, year: int) -> DataFrame:
    """
    Load data from NOAA GSOD for the specified year.
    """
    return ss.read.csv(f"s3://noaa-gsod-pds/{year}/72793524234.csv", header=True, inferSchema=True)


def run():
    """
    Usage: debug
    Basic script to demonstrate debugging
    """
    spark = SparkSession.builder.appName("RemoteDebug").getOrCreate()  # type: ignore
    udf_camelize = f.udf(lambda x: convert_to_camel_case(x), StringType())
    df = load_data(spark, 2023)
    print(f"{df.count()} records for 2023")
    df = load_data(spark, 2022).withColumn("location_title", udf_camelize("NAME"))
    print(f"{df.count()} records for 2022")
    print(df.select("location_title").head())


if __name__ == "__main__":
    run()
