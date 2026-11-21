"""
Creation d'une SparkSession connectee au cluster standalone et a MinIO (S3A).
Utilise par tous les notebooks du projet :

    from spark_session import get_spark, LAKE
    spark = get_spark("FastFood-Partie2")
"""
import os
from pyspark.sql import SparkSession

SPARK_MASTER = os.getenv("SPARK_MASTER_URL", "spark://spark-master:7077")
MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_USER = os.getenv("MINIO_ROOT_USER", "minioadmin")
MINIO_PASSWORD = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin")

LAKE = "s3a://lake"     # racine du Data Lake (bucket MinIO)

# Connecteur S3A : hadoop-aws doit avoir la meme version que le Hadoop de Spark 3.5 (3.3.4)
BASE_PACKAGES = [
    "org.apache.hadoop:hadoop-aws:3.3.4",
    "com.amazonaws:aws-java-sdk-bundle:1.12.262",
]


def get_spark(app_name, extra_packages=None, extra_conf=None):
    packages = BASE_PACKAGES + list(extra_packages or [])
    builder = (
        SparkSession.builder
        .appName(app_name)
        .master(SPARK_MASTER)
        # le Driver tourne dans le conteneur jupyter : les Executors doivent pouvoir le joindre
        .config("spark.driver.host", "jupyter")
        .config("spark.driver.bindAddress", "0.0.0.0")
        # 2 executors x 2 coeurs x 1 Go -> 4 coeurs par application
        .config("spark.executor.cores", "2")
        .config("spark.executor.memory", "1g")
        .config("spark.cores.max", "4")
        .config("spark.sql.shuffle.partitions", "8")
        # journal d'evenements -> Spark History Server (http://localhost:18080) :
        # les DAG / stages restent consultables apres spark.stop()
        .config("spark.eventLog.enabled", "true")
        .config("spark.eventLog.dir", "file:///home/jovyan/work/spark-events")
        # dependances Maven (cache dans le dossier du projet pour ne telecharger qu'une fois)
        .config("spark.jars.packages", ",".join(packages))
        .config("spark.jars.ivy", "/home/jovyan/work/.ivy2")
        # MinIO via S3A
        .config("spark.hadoop.fs.s3a.endpoint", MINIO_ENDPOINT)
        .config("spark.hadoop.fs.s3a.access.key", MINIO_USER)
        .config("spark.hadoop.fs.s3a.secret.key", MINIO_PASSWORD)
        .config("spark.hadoop.fs.s3a.path.style.access", "true")
        .config("spark.hadoop.fs.s3a.connection.ssl.enabled", "false")
        .config("spark.hadoop.fs.s3a.impl", "org.apache.hadoop.fs.s3a.S3AFileSystem")
        .config("spark.hadoop.fs.s3a.aws.credentials.provider",
                "org.apache.hadoop.fs.s3a.SimpleAWSCredentialsProvider")
    )
    for k, v in (extra_conf or {}).items():
        builder = builder.config(k, v)
    spark = builder.getOrCreate()
    spark.sparkContext.setLogLevel("WARN")
    return spark
