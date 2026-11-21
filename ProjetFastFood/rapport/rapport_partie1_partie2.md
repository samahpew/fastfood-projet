# Rapport — Jalon 1 (Parties 1 et 2)

> Brouillon à reprendre dans le rapport PDF. Les chiffres viennent de l'exécution des notebooks
> (`results/`). Remplacer les emplacements « [capture] » par vos captures d'écran.

---

## Partie 1 — Mise en place du cluster et positionnement

### Déploiement

L'environnement est décrit dans `docker-compose.yml` : Kafka 3.9 en mode KRaft (sans ZooKeeper),
un Spark Master et deux Spark Workers (Spark 3.5.3, mode standalone), MinIO (stockage S3) et un
serveur Jupyter qui héberge le Driver PySpark. Le bucket `lake` et le topic `orders` (3 partitions)
sont créés automatiquement au démarrage.

Sortie de la SparkSession (notebook `partie1_cluster.ipynb`) :

```
{{SORTIE_PARTIE1}}
```

[capture] Spark Master UI (http://localhost:8080) avec les 2 Workers ALIVE
[capture] Console MinIO (http://localhost:9001) avec le bucket `lake`

### Rôle des composants dans notre déploiement

- **Driver** : le processus Python/JVM lancé dans le conteneur `jupyter` quand le notebook crée la
  `SparkSession`. Il contient le code de l'application, construit le DAG des transformations,
  le découpe en *stages* et en *tâches*, les envoie aux Executors puis récupère les résultats des
  actions (`collect`, `count`...). La Spark UI de l'application (port 4040) est servie par le Driver.
- **Cluster Manager** : ici le **Spark Master standalone** (`spark-master:7077`). Il connaît les
  ressources des Workers (2 × 4 cœurs, 2 Go) et alloue à chaque application les Executors demandés
  (`spark.executor.cores=2`, `spark.executor.memory=1g`, `spark.cores.max=4`).
  Il n'exécute aucun calcul lui-même.
- **Workers / Executors** : chaque conteneur `spark-worker-N` lance, à la demande du Master, un
  processus **Executor** (JVM + workers Python) dédié à notre application. Les Executors exécutent
  les tâches (une tâche = une partition), gardent en mémoire les RDD mis en cache et échangent les
  données de shuffle. Ils lisent et écrivent directement dans MinIO via S3A.
- **SparkContext** (`spark.sparkContext`) : point d'entrée créé dans le Driver. Il se connecte au
  Master, demande les Executors, crée les RDD (`sc.textFile`, `sc.parallelize`), les variables
  broadcast, et soumet les jobs au `DAGScheduler`. La `SparkSession` l'encapsule pour l'API SQL.

### Deux limites de MapReduce/Hadoop corrigées par Spark

1. **Écriture sur disque entre chaque étape.** En MapReduce, chaque job relit son entrée sur HDFS et
   écrit son résultat sur disque ; un traitement en plusieurs étapes enchaîne donc les E/S disque.
   Spark garde les résultats intermédiaires en mémoire (`cache`) et enchaîne les étapes dans un seul
   DAG. *Dans le projet :* le RDD des commandes livrées est calculé une fois puis réutilisé pour le CA,
   le panier moyen et le top 5 sans relire MinIO.
2. **Traitement batch uniquement, latence élevée.** MapReduce ne traite qu'un jeu de données fini, avec
   une latence de plusieurs minutes, et il faut d'autres outils pour le temps réel ou le SQL. Spark unifie
   batch (RDD, Spark SQL) et temps réel (Structured Streaming) dans le même moteur. *Dans le projet :*
   la direction veut suivre les retards **en continu** ; les commandes arrivent dans Kafka et le même
   code DataFrame sert pour l'historique (Parties 2-3) et pour le flux (Parties 4-5).

(Autre limite possible : API bas niveau verbeuse — un simple « CA par ville » demande une classe Mapper
et une classe Reducer en Java, contre une ligne `reduceByKey` en Spark.)

---

## Partie 2 — Traitement batch avec SparkCore (RDD)

Données : `orders_history.jsonl` ({{N_EVENTS}} événements) généré par `producer.py --mode file --n 50000`
et copié dans `lake/bronze/history/`.

### Résultats

Commandes `DELIVERED` : {{N_DELIV}} lignes, dont {{N_DUP}} doublons supprimés → {{N_UNIQ}} commandes livrées distinctes.

**Chiffre d'affaires et panier moyen par ville**

{{TABLE_VILLE}}

**Top 5 des restaurants (commandes livrées)**

{{TABLE_TOP5}}

### Lineage, transformations et actions

```
{{LINEAGE}}
```

Les opérations `textFile`, `flatMap`, `filter`, `map`, `values`, `mapValues`, `reduceByKey` et
`aggregateByKey` sont des **transformations** : elles sont *lazy* et ne font qu'ajouter un nœud au
lineage. Les **actions** `count`, `take`, `collect`, `takeOrdered` et `collectAsMap` déclenchent
réellement un job.

### DAG, stages et shuffle

[capture] Spark UI → Jobs → « CA par ville (reduceByKey) » → DAG Visualization

Le job « CA par ville » comporte **2 stages** :
- **Stage 1** (*ShuffleMapStage*) : lecture des partitions de `delivered_unique` en cache, puis `map`
  `(ville, montant)` et **pré-agrégation locale** (*map-side combine*) de `reduceByKey` dans chaque
  partition. Chaque tâche écrit ses sommes partielles dans des fichiers de shuffle, répartis par
  hachage de la clé (`ville`).
- **Stage 2** (*ResultStage*) : chaque tâche lit (*shuffle read*), sur tous les Executors, les sommes
  partielles d'un même groupe de villes, les additionne et renvoie le résultat au Driver.

`reduceByKey` est une transformation **large** (*wide*) : toutes les valeurs d'une même clé doivent se
retrouver dans la même partition, ce qui impose de redistribuer les données sur le réseau (**shuffle**).
C'est la frontière entre deux stages. Grâce au *map-side combine*, seules 4 valeurs par partition
(une par ville) traversent le réseau, et non les ~15 000 commandes.

### Tolérance aux pannes grâce au lineage

Un RDD n'est pas répliqué : Spark mémorise la **suite de transformations** qui permet de le produire à
partir de la source (`textFile` sur MinIO). Si un Executor tombe et qu'une partition en cache ou un
fichier de shuffle est perdu, le Driver **recalcule uniquement les partitions perdues** en rejouant le
lineage depuis la dernière donnée disponible (source ou sortie de shuffle). Les transformations étant
déterministes, le résultat est identique. C'est moins coûteux que la réplication systématique de
MapReduce/HDFS pour les données intermédiaires.

### Temps mesurés (référence pour la Partie 3)

{{TIMINGS}}
