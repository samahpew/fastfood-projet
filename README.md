# FastFood.ma — Pipeline temps réel avec Spark et Kafka

Projet Écosystème Big Data 2 (5ème année EMSI) — réalisé en binôme.

```
producer.py → Kafka (topic orders, 3 partitions) → Spark Structured Streaming → MinIO (Bronze → Silver → Gold)
```

## Versions

| Composant | Image Docker | Version |
|---|---|---|
| Apache Spark (Master + 2 Workers) | `quay.io/jupyter/pyspark-notebook:spark-3.5.3` | Spark 3.5.3, Scala 2.12, Hadoop 3.3.4 |
| Jupyter + PySpark (Driver) | même image | Python 3.11, PySpark 3.5.3 |
| Apache Kafka (mode KRaft) | `apache/kafka:3.9.1` | 3.9.1 |
| MinIO (S3) | `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z` | RELEASE.2025-09-07 |
| Client MinIO (`mc`) | même image que MinIO | RELEASE.2025-08-13 |
| Connecteur S3A (téléchargé par Spark) | `org.apache.hadoop:hadoop-aws:3.3.4`, `com.amazonaws:aws-java-sdk-bundle:1.12.262` | — |

Master, Workers et Jupyter partagent **la même image** : Driver et Executors ont exactement
la même version de Python (sinon les RDD Python échouent).

## Prérequis

- Docker Desktop (WSL2), ~8 Go de RAM alloués à Docker
- Ports libres : 4040-4042, 7077, 8081, 8082, 8090, 8888, 9000, 9001, 9094

## Démarrage rapide (Windows / PowerShell)

```powershell
cd $HOME\Desktop\ProjetFastFood
.\demarrer.ps1
```

Le script : démarre les conteneurs, crée le bucket `lake` et le topic `orders` (3 partitions),
génère `data/orders_history.jsonl` (50 000 événements) et `data/restaurants.json` (200 restaurants),
puis les copie dans `lake/bronze/history/` et `lake/bronze/reference/`.

Ensuite ouvrir http://localhost:8888 → dossier `notebooks/` :

1. `partie1_cluster.ipynb` — SparkSession sur `spark://spark-master:7077`, version, master, appName, `defaultParallelism`
2. `partie2_rdd.ipynb` — SparkCore / RDD : CA et panier moyen par ville, top 5 restaurants, lineage
3. `partie3_sql.ipynb` — Spark SQL / DataFrames : schéma explicite, jointure, UDF vs `when`, Parquet Silver, `explain(True)`

Menu **Run → Run All Cells** pour exécuter un notebook, ou en ligne de commande (les sorties sont
enregistrées dans le notebook et les tableaux dans `results/`) :

```powershell
docker compose exec -w /home/jovyan/work/notebooks -e PYTHONPATH=/usr/local/spark/python:/usr/local/spark/python/lib/py4j-0.10.9.7-src.zip jupyter `
    jupyter nbconvert --to notebook --inplace --execute --ExecutePreprocessor.timeout=1800 partie2_rdd.ipynb
```

(`PYTHONPATH` n'est défini automatiquement que pour le serveur Jupyter, pas pour `docker compose exec`.)

## Commandes utiles

```powershell
docker compose ps                                     # état des services
docker compose logs -f spark-master                   # logs d'un service
docker compose exec mc mc ls --recursive local/lake/  # contenu du Data Lake (capture demandée)
docker compose exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic orders
docker compose down                                   # arrêter (données conservées)
docker compose down -v                                # arrêter ET effacer MinIO/Kafka
```

Démarrage manuel (équivalent du script) :

```powershell
docker compose up -d
docker compose exec jupyter python /home/jovyan/work/producer/producer.py --mode file --n 50000 --out /home/jovyan/work/data/orders_history.jsonl
docker compose exec mc mc cp /data/orders_history.jsonl local/lake/bronze/history/orders_history.jsonl
docker compose exec mc mc cp /data/restaurants.json local/lake/bronze/reference/restaurants.json
```

## Interfaces web

| Interface | URL |
|---|---|
| Jupyter | http://localhost:8888 |
| Spark Master UI (2 Workers) | http://localhost:8090 |
| Spark UI de l'application (DAG, stages) | http://localhost:4040 |
| Spark History Server (DAG après `spark.stop()`) | http://localhost:18080 |
| Console MinIO (`minioadmin` / `minioadmin`) | http://localhost:9001 |

## Organisation du dépôt

```
docker-compose.yml        Kafka, Spark Master + 2 Workers, MinIO, mc, Jupyter
demarrer.ps1              démarrage + préparation des données
producer/producer.py      générateur de commandes (mode file / kafka)
notebooks/spark_session.py  SparkSession commune (cluster + MinIO S3A)
notebooks/partie*.ipynb   un notebook par partie
data/                     données générées localement (restaurants.json, orders_history.jsonl)
results/                  tableaux et mesures exportés par les notebooks
rapport/                  rapport Jalon 1 (.docx / .pdf), figures, captures et scripts qui les génèrent
```

## Rapport (Jalon 1)

```powershell
pip install matplotlib pandas playwright
python rapport\figures.py      # graphiques à partir de results/
python rapport\captures.py     # captures Spark UI / MinIO / History Server (Chrome headless)
python rapport\build_rapport.py "$HOME\Desktop\TP-1 ML Samah El Azzab.docx"   # modèle de mise en page
```

## Organisation du bucket `lake`

```
lake/
  bronze/history/        orders_history.jsonl (Partie 2)
  bronze/reference/      restaurants.json
  bronze/orders_raw/     JSON bruts lus dans Kafka (Partie 4)
  silver/orders_history/ Parquet nettoyé de l'historique, partitionné par city (Partie 3)
  silver/orders_clean/   Parquet nettoyé et enrichi (Partie 5)
  gold/kpi_city_10min/   Delta Lake : indicateurs agrégés (Partie 5)
  checkpoints/           checkpoints Structured Streaming
```

## Générateur `producer.py`

```
python producer.py --mode file  --n 50000 --out data/orders_history.jsonl   # historique (seed fixe = données reproductibles)
python producer.py --mode kafka --rate 20 --bootstrap kafka:9092            # flux temps réel (Partie 4)
```

Un événement par changement d'état (`CREATED`, `PICKED_UP`, `DELIVERED`, `CANCELLED`),
~5 % d'événements en retard (jusqu'à 15 min) et ~2 % de doublons (même `order_id` + `status`).
