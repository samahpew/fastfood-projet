"""
Genere le rapport Word du Jalon 1 (Parties 1, 2, 3) dans le theme du compte rendu
« TP-1 ML Samah El Azzab.docx » : page de garde EMSI / Honoris, styles et pied de page
du modele sont repris, le corps est reconstruit a partir des resultats des notebooks.

    python rapport/build_rapport.py "C:/Users/dell/Desktop/TP-1 ML Samah El Azzab.docx"

Sortie : rapport/Rapport_Jalon1_FastFood.docx
"""
import csv
import json
import os
import re
import shutil
import struct
import sys
import tempfile
import zipfile
from xml.sax.saxutils import escape

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
FIG = os.path.join(ROOT, "rapport", "figures")
CAP = os.path.join(ROOT, "rapport", "captures")
NB = os.path.join(ROOT, "notebooks")
OUT = os.path.join(ROOT, "rapport", "Rapport_Jalon1_FastFood.docx")

RED, GREEN, BLUE = "C00000", "005E00", "1F4E79"
FONT = '<w:rFonts w:ascii="Cambria" w:eastAsia="Cambria" w:hAnsi="Cambria" w:cs="Cambria"/>'
MONO = '<w:rFonts w:ascii="Consolas" w:eastAsia="Consolas" w:hAnsi="Consolas" w:cs="Consolas"/>'
BODY_SZ = 22          # 11 pt
CONTENT_W = 11910 - 992 - 1275   # largeur utile de la page du modele (dxa)
BULLET_NUM_ID = 90


# ------------------------------------------------------------------ donnees --
def read_csv(name):
    with open(os.path.join(RES, name), encoding="utf-8") as f:
        return list(csv.reader(f))


def read_json(name):
    with open(os.path.join(RES, name), encoding="utf-8") as f:
        return json.load(f)


def nb_outputs(nb_name):
    """[(source, texte des sorties)] pour chaque cellule de code."""
    with open(os.path.join(NB, nb_name), encoding="utf-8") as f:
        nb = json.load(f)
    cells = []
    for c in nb["cells"]:
        if c["cell_type"] != "code":
            continue
        txt = []
        for o in c.get("outputs", []):
            if o.get("name") == "stderr":
                continue
            t = o.get("text") or o.get("data", {}).get("text/plain", "")
            txt.append("".join(t) if isinstance(t, list) else t)
        cells.append(("".join(c["source"]), "".join(txt)))
    return cells


def output_of(cells, marker):
    for src, out in cells:
        if marker in src:
            return out
    raise KeyError(marker)


def fr(x, dec=2):
    """1079464.82 -> '1 079 464,82' (format francais)."""
    s = f"{float(x):,.{dec}f}".replace(",", " ").replace(".", ",")
    return s


# ---------------------------------------------------------- briques XML ----
def run(text, bold=False, italic=False, color=None, sz=BODY_SZ, mono=False, underline=False):
    rpr = (MONO if mono else FONT)
    if bold:
        rpr += "<w:b/><w:bCs/>"
    if italic:
        rpr += "<w:i/><w:iCs/>"
    if color:
        rpr += f'<w:color w:val="{color}"/>'
    rpr += f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
    if underline:
        rpr += '<w:u w:val="single"/>'
    if mono and not color:
        rpr += '<w:shd w:val="clear" w:color="auto" w:fill="EDEFF2"/>'
    return f'<w:r><w:rPr>{rpr}</w:rPr><w:t xml:space="preserve">{escape(text)}</w:t></w:r>'


def rich(text, sz=BODY_SZ, base_bold=False, color=None):
    """Mini-markdown : **gras**, `code`, *italique*."""
    out = []
    for tok in re.split(r"(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)", text):
        if not tok:
            continue
        if tok.startswith("**"):
            out.append(run(tok[2:-2], bold=True, sz=sz, color=color))
        elif tok.startswith("`"):
            out.append(run(tok[1:-1], mono=True, sz=sz - 3))
        elif tok.startswith("*") and len(tok) > 2:
            out.append(run(tok[1:-1], italic=True, bold=base_bold, sz=sz, color=color))
        else:
            out.append(run(tok, bold=base_bold, sz=sz, color=color))
    return "".join(out)


def para(content, jc="both", before=0, after=120, keep_next=False, extra_ppr="", line=264):
    ppr = f'<w:spacing w:before="{before}" w:after="{after}" w:line="{line}" w:lineRule="auto"/>'
    if keep_next:
        ppr = "<w:keepNext/>" + ppr
    ppr = extra_ppr + ppr + f'<w:jc w:val="{jc}"/>'
    return f"<w:p><w:pPr>{ppr}</w:pPr>{content}</w:p>"


def P(text, **kw):
    return para(rich(text), **kw)


def H1(text, page_break=False):
    pb = '<w:pageBreakBefore/>' if page_break else ""
    return para(run(text, bold=True, italic=True, color=RED, sz=30, underline=True),
                jc="left", before=240, after=120, keep_next=True, extra_ppr=pb)


def H2(text):
    return para(run(text, bold=True, italic=True, color=GREEN, sz=26, underline=True),
                jc="left", before=180, after=80, keep_next=True)


def bullets(items):
    ppr = f'<w:numPr><w:ilvl w:val="0"/><w:numId w:val="{BULLET_NUM_ID}"/></w:numPr>'
    return "".join(para(rich(t), after=60, extra_ppr=ppr) for t in items)


def caption(text):
    return para(run(text, italic=True, sz=20, color="404040"), jc="center", before=40, after=200)


def table_caption(text):
    return para(run(text, italic=True, sz=20, color="404040"), jc="left", before=120, after=40,
                keep_next=True)


def code(text, sz=15):
    lines = text.rstrip("\n").split("\n")
    out = []
    border = ('<w:pBdr><w:left w:val="single" w:sz="18" w:space="6" w:color="1F4E79"/></w:pBdr>'
              '<w:shd w:val="clear" w:color="auto" w:fill="F2F4F7"/><w:ind w:left="170" w:right="57"/>')
    for i, line in enumerate(lines):
        last = i == len(lines) - 1
        keep = "" if last else "<w:keepNext/><w:keepLines/>"
        out.append(f'<w:p><w:pPr>{keep}{border}<w:spacing w:before="{60 if i == 0 else 0}" '
                   f'w:after="{140 if last else 0}" w:line="240" w:lineRule="auto"/></w:pPr>'
                   f'<w:r><w:rPr>{MONO}<w:color w:val="1A1A1A"/><w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/>'
                   f'</w:rPr><w:t xml:space="preserve">{escape(line)}</w:t></w:r></w:p>')
    return "".join(out)


def table(header, rows, widths, align=None, sz=21):
    """Tableau dans le style du modele : en-tete bleu fonce, lignes alternees."""
    total = sum(widths)
    widths = [round(w * CONTENT_W / total) for w in widths]
    align = align or ["left"] * len(header)
    borders = "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="BFBFBF"/>'
                      for s in ("top", "left", "bottom", "right"))
    mar = ('<w:tcMar><w:top w:w="45" w:type="dxa"/><w:left w:w="90" w:type="dxa"/>'
           '<w:bottom w:w="45" w:type="dxa"/><w:right w:w="90" w:type="dxa"/></w:tcMar>')

    def cell(text, w, fill, jc, head, keep=True):
        r = (run(text, bold=True, color="FFFFFF", sz=sz) if head else rich(text, sz=sz))
        return (f'<w:tc><w:tcPr><w:tcW w:w="{w}" w:type="dxa"/><w:tcBorders>{borders}</w:tcBorders>'
                f'<w:shd w:val="clear" w:color="auto" w:fill="{fill}"/>{mar}<w:vAlign w:val="center"/></w:tcPr>'
                f'<w:p><w:pPr>{"<w:keepNext/>" if keep else ""}<w:spacing w:before="0" w:after="0"/>'
                f'<w:jc w:val="{jc}"/></w:pPr>{r}</w:p></w:tc>')

    xml = (f'<w:tbl><w:tblPr><w:tblW w:w="{CONTENT_W}" w:type="dxa"/><w:jc w:val="center"/>'
           f'<w:tblLayout w:type="fixed"/>'
           '<w:tblCellMar><w:left w:w="10" w:type="dxa"/><w:right w:w="10" w:type="dxa"/></w:tblCellMar>'
           '<w:tblLook w:val="04A0" w:firstRow="1" w:lastRow="0" w:firstColumn="1" w:lastColumn="0" '
           'w:noHBand="0" w:noVBand="1"/></w:tblPr><w:tblGrid>'
           + "".join(f'<w:gridCol w:w="{w}"/>' for w in widths) + "</w:tblGrid>")
    xml += ('<w:tr><w:trPr><w:tblHeader/><w:cantSplit/></w:trPr>'
            + "".join(cell(h, w, BLUE, a if a != "right" else "center", True)
                      for h, w, a in zip(header, widths, align)) + "</w:tr>")
    for i, r in enumerate(rows):
        fill = "FFFFFF" if i % 2 == 0 else "F2F6FA"
        xml += ('<w:tr><w:trPr><w:cantSplit/></w:trPr>'
                + "".join(cell(str(v), w, fill, a, False, keep=i < len(rows) - 1)
                          for v, w, a in zip(r, widths, align)) + "</w:tr>")
    return xml + "</w:tbl>"


class Images:
    """Ajoute les images au paquet (word/media + relations)."""

    def __init__(self):
        self.items = []          # (rId, nom dans media, chemin source)

    def add(self, path):
        rid = f"rIdImg{len(self.items) + 1}"
        name = f"rapport_{len(self.items) + 1}{os.path.splitext(path)[1].lower()}"
        self.items.append((rid, name, path))
        return rid


IMAGES = Images()


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def image(path, width_cm, crop_h=None):
    rid = IMAGES.add(path)
    w_px, h_px = png_size(path)
    cx = int(width_cm * 360000)
    cy = int(cx * h_px / w_px)
    n = len(IMAGES.items) + 100
    drawing = (
        f'<w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
        f'<wp:docPr id="{n}" name="Image {n}"/><wp:cNvGraphicFramePr>'
        '<a:graphicFrameLocks xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" noChangeAspect="1"/>'
        '</wp:cNvGraphicFramePr><a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main">'
        '<a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        '<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">'
        f'<pic:nvPicPr><pic:cNvPr id="{n}" name="{os.path.basename(path)}"/><pic:cNvPicPr/></pic:nvPicPr>'
        f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
        f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm>'
        '<a:prstGeom prst="rect"><a:avLst/></a:prstGeom><a:ln w="6350"><a:solidFill><a:srgbClr val="BFBFBF"/>'
        '</a:solidFill></a:ln></pic:spPr></pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing>')
    return para(f"<w:r>{drawing}</w:r>", jc="center", before=60, after=0, keep_next=True)


# ------------------------------------------------------------- contenu -----
def build_body():
    p1 = nb_outputs("partie1_cluster.ipynb")
    p2 = nb_outputs("partie2_rdd.ipynb")
    p3 = nb_outputs("partie3_sql.ipynb")
    t2, t3 = read_json("partie2_timings.json"), read_json("partie3_timings.json")

    def essais(d, prefixe):
        v = [t for k, t in d.items() if k.startswith(prefixe)]
        return sum(v) / len(v), min(v)

    session_out = output_of(p1, 'print("Version de Spark   :"').strip()
    executors_out = output_of(p1, "getExecutorInfos()").strip()
    placement_out = output_of(p1, "mapPartitionsWithIndex").strip().splitlines()
    kafka_out = output_of(p1, "KafkaConsumer(").strip().splitlines()[-2:]
    statuts = dict(re.findall(r"\('(\w+)', (\d+)\)", output_of(p2, 'o["status"], 1')))
    m = re.search(r"DELIVERED : (\d+) lignes, (\d+) commandes distinctes -> (\d+)",
                  output_of(p2, "delivered_unique.count()"))
    n_deliv, n_uniq, n_dup = m.groups()
    job_stages = output_of(p2, 'sc.setJobGroup("ca_ville"').strip().splitlines()
    job_stages = [l for l in job_stages if l.startswith("job ")]
    lineage = output_of(p2, "print(ca_ville.toDebugString()").rstrip()
    lineage = re.sub(r"/tmp/ipykernel_\d+/\d+\.py", "<cellule>", lineage)
    lineage = re.sub(r" at NativeMethodAccessorImpl\.java:0", "", lineage)
    lineage = lineage.replace(" []", "")
    clean_out = output_of(p3, "lignes nettoyées")
    n_clean = re.search(r"lignes nettoyées : (\d+)", clean_out).group(1)
    casa = re.search(r"lignes Casablanca : (\d+)", output_of(p3, "partition pruning")).group(1)
    bands = dict(re.findall(r"\|\s*(court|moyen|long)\|\s*(\d+)\|", output_of(p3, "avec_udf.groupBy")))
    parquet_files = [l for l in output_of(p3, "fs.listFiles(").splitlines() if ".parquet" in l]

    ville = read_csv("partie2_ca_panier_par_ville.csv")[1:]
    top5 = read_csv("partie2_top5_restaurants.csv")[1:]
    pivot = read_csv("partie3_pivot_categorie_ville.csv")
    comp = read_csv("partie3_comparaison_rdd_df_sql.csv")[1:]
    total_ca = sum(float(r[1]) for r in ville)
    rdd_m, rdd_b = essais(t2, "CA par ville RDD sans cache")
    df_m, df_b = essais(t3, "CA par ville DataFrame sans cache")
    sql_m, sql_b = essais(t3, "CA par ville SQL sans cache")
    udf_m, udf_b = essais(t3, "distance_band UDF")
    nat_m, nat_b = essais(t3, "distance_band when")
    t_smj = t3["jointure SortMergeJoin (broadcast désactivé)"]
    t_bhj = t3["jointure BroadcastHashJoin"]

    b = []
    # ------------------------------------------------------------ intro
    b.append(H1("1. Introduction et objectif"))
    b.append(P("FastFood.ma est une plateforme fictive de livraison de repas présente à Casablanca, Rabat, "
               "Marrakech et Tanger. La direction veut suivre le volume de commandes, le chiffre d'affaires et les "
               "retards de livraison par ville. Le projet construit un pipeline **Kafka → Spark → MinIO** "
               "(architecture *Bronze / Silver / Gold*)."))
    b.append(P("Ce rapport couvre le **Jalon 1** (traitement batch) : la mise en place du cluster (Partie 1), "
               "l'API bas niveau SparkCore / RDD (Partie 2) et l'API structurée Spark SQL / DataFrames (Partie 3). "
               "Tous les chiffres proviennent de l'exécution des notebooks du dépôt sur le cluster Docker ; "
               "les données sont générées par `producer.py` avec une graine fixe, donc reproductibles."))
    b.append(image(os.path.join(FIG, "architecture.png"), 15.5))
    b.append(caption("Figure 1 – Architecture déployée avec Docker Compose"))

    # ------------------------------------------------------------ partie 1
    b.append(H1("2. Partie 1 – Mise en place du cluster et positionnement"))
    b.append(H2("2.1 Déploiement Docker Compose"))
    b.append(P("Le fichier `docker-compose.yml` démarre neuf services. Le Master, les deux Workers et Jupyter "
               "utilisent la **même image** (`pyspark-notebook:spark-3.5.3`) : le Driver et les Executors ont ainsi "
               "exactement la même version de Python, ce qu'exigent les RDD Python. Le bucket `lake` (MinIO) et le "
               "topic `orders` à 3 partitions (Kafka) sont créés automatiquement par les services `mc` et `kafka-init`."))
    b.append(table_caption("Tableau 1 – Services du cluster"))
    b.append(table(["Service", "Image / version", "Rôle", "Port (hôte)"], [
        ["kafka", "apache/kafka 3.9.1 (KRaft)", "bus de messages, topic orders (3 partitions)", "9094"],
        ["spark-master", "Spark 3.5.3 standalone", "Cluster Manager", "8090 (UI), 7077"],
        ["spark-worker-1 / 2", "Spark 3.5.3", "4 cœurs, 2 Go chacun → Executors", "8081, 8082"],
        ["jupyter", "PySpark 3.5.3, Python 3.11", "Driver (notebooks)", "8888, 4040"],
        ["minio + mc", "MinIO RELEASE.2025-09-07", "Data Lake S3 (bucket lake)", "9000, 9001"],
        ["spark-history", "Spark 3.5.3", "History Server (DAG après spark.stop())", "18080"],
    ], [2.2, 3.2, 4.4, 2.0]))
    b.append(H2("2.2 SparkSession connectée au Master"))
    b.append(P("La session est créée par `notebooks/spark_session.py` (connecteur S3A `hadoop-aws:3.3.4` vers MinIO, "
               "`spark.executor.cores=2`, `spark.cores.max=4`). Sortie du notebook `partie1_cluster.ipynb` :"))
    b.append(code(session_out + "\n\n" + executors_out))
    b.append(P(f"`defaultParallelism = 4` correspond aux 2 Executors × 2 cœurs alloués à l'application. Un job de "
               f"test sur 8 partitions confirme la distribution : les tâches s'exécutent sur `spark-worker-1` et "
               f"`spark-worker-2`, jamais sur le Driver (somme 1..1000 = 500 500). "
               f"Kafka : `{kafka_out[0].strip()}` – `{kafka_out[1].strip()}`."))
    b.append(image(os.path.join(CAP, "p1_spark_master_ui.png"), 13))
    b.append(caption("Figure 2 – Spark Master UI : 2 Workers ALIVE (8 cœurs, 4 Go) et applications du projet"))
    b.append(image(os.path.join(CAP, "p1_minio_lake.png"), 11))
    b.append(caption("Figure 3 – Console MinIO : bucket lake et couches bronze / silver"))

    b.append(H2("2.3 Rôle des composants dans notre déploiement"))
    b.append(bullets([
        "**Driver** : processus lancé dans le conteneur `jupyter` à la création de la `SparkSession`. Il exécute le "
        "code du notebook, construit le DAG des transformations, le découpe en *stages* puis en *tâches* "
        "(une par partition), les envoie aux Executors et récupère le résultat des actions. Il sert la Spark UI (4040).",
        "**Cluster Manager** : le **Spark Master standalone** (`spark-master:7077`). Il connaît les ressources des "
        "Workers (2 × 4 cœurs, 2 Go) et attribue à chaque application les Executors demandés. Il ne calcule rien.",
        "**Workers / Executors** : chaque conteneur `spark-worker-N` lance, à la demande du Master, un Executor (JVM + "
        "processus Python) dédié à l'application. Les Executors exécutent les tâches, gardent les données en cache, "
        "échangent les données de *shuffle* et lisent / écrivent directement dans MinIO via S3A.",
        "**SparkContext** (`spark.sparkContext`) : point d'entrée créé dans le Driver. Il se connecte au Master, "
        "obtient les Executors, crée les RDD (`sc.textFile`), les variables *broadcast*, et soumet les jobs au "
        "`DAGScheduler`. La `SparkSession` l'encapsule pour l'API SQL / DataFrame.",
    ]))
    b.append(H2("2.4 Deux limites de MapReduce / Hadoop corrigées par Spark"))
    b.append(bullets([
        "**Écriture sur disque entre chaque étape.** Un job MapReduce relit son entrée sur HDFS et écrit son résultat "
        "sur disque ; une analyse en plusieurs étapes enchaîne donc des E/S disque. Spark enchaîne les étapes dans un "
        "seul DAG et garde les résultats intermédiaires en mémoire (`cache`). *Dans le projet* : le RDD des "
        f"commandes livrées est calculé une fois puis réutilisé pour le CA, le panier moyen et le top 5 ; le CA par "
        f"ville passe de {fr(rdd_m)} s (relecture complète de MinIO) à {fr(t2['CA par ville (RDD, données en cache)'])} s "
        "sur les données en cache.",
        "**Batch uniquement, latence élevée.** MapReduce ne traite qu'un jeu de données fini, avec une latence de "
        "plusieurs minutes ; le SQL ou le temps réel demandent d'autres outils (Hive, Storm…). Spark unifie batch "
        "(RDD, Spark SQL) et streaming (Structured Streaming) dans un même moteur. *Dans le projet* : la direction veut "
        "suivre les retards **en continu** ; le schéma et le code DataFrame écrits ici pour l'historique "
        "seront réutilisés tels quels sur le flux Kafka (Parties 4–5).",
    ]))

    # ------------------------------------------------------------ partie 2
    b.append(H1("3. Partie 2 – Traitement batch avec SparkCore (RDD)"))
    b.append(H2("3.1 Données et préparation"))
    b.append(P(f"`producer.py --mode file --n 50000` génère `orders_history.jsonl` (50 000 événements), copié dans "
               f"`lake/bronze/history/`. Le fichier est chargé avec `sc.textFile()` (4 partitions) et chaque ligne "
               f"est parsée avec `json.loads` dans un `flatMap` qui ignore les lignes invalides. Répartition : "
               f"CREATED {statuts.get('CREATED')}, PICKED_UP {statuts.get('PICKED_UP')}, "
               f"DELIVERED {statuts.get('DELIVERED')}, CANCELLED {statuts.get('CANCELLED')}."))
    b.append(P(f"Après `filter(status == DELIVERED)` il reste {n_deliv} lignes, mais le générateur injecte ~2 % de "
               f"**doublons** (même `order_id` et même statut). Sans dédoublonnage le CA serait surestimé ; on garde "
               f"une ligne par commande (`map` → `(order_id, o)` puis `reduceByKey(lambda a, b: a)`) : "
               f"**{n_dup} doublons supprimés**, {n_uniq} commandes livrées distinctes."))
    b.append(H2("3.2 Chiffre d'affaires et panier moyen par ville"))
    b.append(P("Le CA utilise `map((ville, montant))` + `reduceByKey(add)`. Le panier moyen calcule somme **et** nombre "
               "en un seul passage avec `aggregateByKey((0.0, 0), seqOp, combOp)` : `seqOp` ajoute une commande à "
               "l'accumulateur dans une partition, `combOp` fusionne les accumulateurs après le shuffle."))
    b.append(table_caption("Tableau 2 – CA et panier moyen par ville (commandes livrées, sans doublons)"))
    rows = [[r[0], fr(r[1]), r[2], fr(r[3]), fr(100 * float(r[1]) / total_ca, 1) + " %"] for r in ville]
    rows.append(["**Total**", "**" + fr(total_ca) + "**", "**" + str(sum(int(r[2]) for r in ville)) + "**", "", "100 %"])
    b.append(table(["Ville", "CA (MAD)", "Commandes livrées", "Panier moyen (MAD)", "Part du CA"], rows,
                   [2.2, 2.4, 2.4, 2.6, 1.8], ["left", "right", "right", "right", "right"]))
    b.append(image(os.path.join(FIG, "ca_panier_ville.png"), 13.5))
    b.append(caption("Figure 4 – CA et panier moyen par ville"))
    b.append(P(f"Casablanca concentre {fr(100 * float(ville[0][1]) / total_ca, 1)} % du CA grâce au volume de "
               f"commandes, mais c'est la ville où le panier moyen est le plus faible ({fr(ville[0][3])} MAD) ; "
               f"Tanger a le panier le plus élevé ({fr(ville[-1][3])} MAD) pour le plus petit volume."))
    b.append(table_caption("Tableau 3 – Top 5 des restaurants par commandes livrées (takeOrdered)"))
    b.append(table(["#", "Restaurant", "Nom", "Ville", "Catégorie", "Livrées"],
                   [[str(i + 1)] + r for i, r in enumerate(top5)],
                   [0.6, 1.6, 4.0, 2.0, 1.6, 1.4], ["center", "left", "left", "left", "left", "right"]))
    b.append(P("Les noms viennent de `restaurants.json`, diffusé une seule fois à chaque Executor par une "
               "**variable broadcast** (`sc.broadcast`) plutôt que par une jointure qui provoquerait un shuffle."))

    b.append(H2("3.3 Lineage : transformations et actions"))
    b.append(P("`toDebugString()` sur le RDD du CA par ville (chaque `+-` marque une frontière de shuffle) :"))
    b.append(code(lineage, sz=14))
    b.append(table_caption("Tableau 4 – Transformations (lazy) et actions utilisées"))
    b.append(table(["Opérations", "Type", "Effet"], [
        ["`textFile`, `flatMap`, `map`, `filter`, `values`, `mapValues`", "Transformation étroite (lazy)",
         "ajoutée au lineage, rien n'est exécuté"],
        ["`reduceByKey`, `aggregateByKey`", "Transformation large (lazy)", "shuffle → nouveau stage"],
        ["`cache`", "Marqueur (lazy)", "RDD gardé en mémoire au 1er calcul"],
        ["`count`, `take`, `collect`, `takeOrdered`, `collectAsMap`", "**Action**",
         "déclenche un job : DAG → stages → tâches"],
    ], [5.0, 2.8, 3.6]))
    b.append(H2("3.4 DAG, stages et shuffle"))
    b.append(image(os.path.join(CAP, "p2_dag_ca_ville.png"), 13))
    b.append(caption("Figure 5 – Spark UI (History Server) : DAG du job « CA par ville (reduceByKey) »"))
    b.append(P(f"Le job « CA par ville » ({job_stages[0] if job_stages else ''}) contient **3 stages, dont 1 "
               "skipped** : le stage qui produisait `delivered_unique` (dédoublonnage) n'est pas rejoué car ce RDD "
               "est en cache. Restent **2 stages exécutés** :"))
    b.append(bullets([
        "**ShuffleMapStage** : lecture des 4 partitions en cache, `map((ville, montant))` et pré-agrégation locale "
        "(*map-side combine*) de `reduceByKey`. Chaque tâche écrit ses sommes partielles dans des fichiers de "
        "shuffle, répartis par hachage de la ville.",
        "**ResultStage** : chaque tâche lit (*shuffle read*) les sommes partielles d'un même groupe de villes "
        "venant de tous les Executors, les additionne et renvoie le résultat au Driver.",
    ]))
    b.append(P("`reduceByKey` est une transformation **large** : toutes les valeurs d'une clé doivent se retrouver dans "
               "la même partition, d'où une redistribution réseau (**shuffle**) qui marque la frontière entre deux "
               "stages. Grâce au *map-side combine*, seules ~4 valeurs par partition (une par ville) traversent le "
               "réseau au lieu des 15 000 commandes."))
    b.append(H2("3.5 Tolérance aux pannes grâce au lineage"))
    b.append(P("Un RDD n'est pas répliqué : Spark mémorise la suite de transformations qui le produit depuis la source "
               "(`textFile` sur MinIO). Si un Executor tombe, le Driver **recalcule uniquement les partitions "
               "perdues** en rejouant le lineage depuis la dernière donnée disponible (source ou sortie de shuffle "
               "encore présente). Les transformations étant déterministes, le résultat est identique. Ce mécanisme "
               "évite d'écrire chaque résultat intermédiaire sur disque répliqué comme le fait MapReduce / HDFS."))

    # ------------------------------------------------------------ partie 3
    b.append(H1("4. Partie 3 – Spark SQL et DataFrames"))
    b.append(H2("4.1 Schéma explicite et CA par ville (DataFrame et SQL)"))
    b.append(P("Les deux fichiers sont lus avec un `StructType` explicite (`event_time` en `TimestampType`, "
               "`amount_mad` en `DoubleType`…) : pas de passe d'inférence sur tout le fichier et des types garantis. "
               "Ce même schéma servira à `from_json` en Partie 4. Le CA par ville est recalculé avec l'API DataFrame "
               "(`filter` → `dropDuplicates([\"order_id\"])` → `groupBy(\"city\").agg(...)`) puis en SQL "
               "(`createOrReplaceTempView` + `spark.sql`, `SELECT DISTINCT` dans une CTE). Les deux versions donnent "
               "**exactement** les valeurs du Tableau 2 (contrôle `Résultats identiques DataFrame / SQL : True`)."))
    b.append(H2("4.2 Jointure avec le référentiel : CA par catégorie et par ville"))
    b.append(P("Jointure `left` sur `restaurant_id` (la colonne `city` du référentiel est renommée pour éviter "
               "l'ambiguïté) ; contrôle qualité : 0 commande sans restaurant connu."))
    b.append(table_caption("Tableau 5 – CA par catégorie et par ville (milliers de MAD)"))
    hdr = pivot[0]
    prow = []
    for r in sorted(pivot[1:], key=lambda r: -float(r[-1])):
        prow.append([r[0]] + [fr(float(v) / 1000, 1) if v else "–" for v in r[1:]])
    b.append(table(["Catégorie"] + hdr[1:-1] + ["Total"], prow,
                   [2.2, 1.9, 1.9, 1.9, 1.9, 1.9], ["left"] + ["right"] * 5, sz=20))
    b.append(P("Chaque ville a son profil : le **tacos** domine à Casablanca, le **healthy** à Rabat, le **sushi** à "
               "Marrakech et à Tanger. Aucune pizzeria n'a de commande livrée à Tanger (« – »)."))

    b.append(H2("4.3 UDF distance_band contre when / otherwise"))
    b.append(P(f"La règle : *court* (< 2 km), *moyen* (2 à 5 km), *long* (> 5 km). Les deux versions donnent les mêmes "
               f"effectifs (court {bands.get('court')}, moyen {bands.get('moyen')}, long {bands.get('long')}), mais "
               f"la version native est plus rapide : **{fr(nat_m)} s contre {fr(udf_m)} s** en moyenne sur 3 essais."))
    b.append(code("avec UDF : +- BatchEvalPython [distance_band_udf(distance_km#6)]\n"
                  "sans UDF : Project [CASE WHEN isnull(distance_km) THEN null WHEN (distance_km < 2.0) THEN court\n"
                  "                    WHEN (distance_km <= 5.0) THEN moyen ELSE long END AS distance_band]"))
    b.append(P("L'UDF Python est une boîte noire pour Catalyst : le plan contient un nœud `BatchEvalPython`, chaque "
               "ligne est sérialisée de la JVM vers un processus Python puis renvoyée. `when/otherwise` devient une "
               "expression `CASE WHEN` native, optimisable par Catalyst et compilée en bytecode JVM par Tungsten "
               "(*whole-stage code generation*), sans aller-retour vers Python."))

    b.append(H2("4.4 Couche Silver : Parquet partitionné par ville"))
    b.append(P(f"Nettoyage : suppression des lignes sans clé, des doublons (`order_id`, `status`), ajout de "
               f"`distance_band`, `event_date`, du nom et de la catégorie du restaurant (jointure broadcast). "
               f"50 000 lignes → **{n_clean}** lignes écrites en Parquet (Snappy) dans `lake/silver/orders_history/` "
               f"avec `partitionBy(\"city\")` : un dossier `city=…` par ville ({len(parquet_files)} fichiers). En "
               f"relecture, `filter(city = 'Casablanca')` ({casa} lignes) ne lit qu'un seul dossier : "
               f"`PartitionFilters: [isnotnull(city), (city = Casablanca)]` (*partition pruning*)."))

    b.append(H2("4.5 explain(True) sur la jointure : plans logique, optimisé et physique"))
    b.append(code(
        "== Optimized Logical Plan ==\n"
        "Aggregate [city, category], [city, category, sum(amount_mad) AS ca_mad]\n"
        "+- Project [city, amount_mad, category]\n"
        "   +- Join Inner, (restaurant_id = restaurant_id)\n"
        "      :- Project [restaurant_id, city, amount_mad]\n"
        "      :  +- Filter ((isnotnull(status) AND (status = DELIVERED)) AND isnotnull(restaurant_id))\n"
        "      +- Project [restaurant_id, category]\n"
        "         +- Filter isnotnull(restaurant_id)\n"
        "== Physical Plan ==\n"
        "HashAggregate(keys=[city, category], functions=[sum(amount_mad)])\n"
        "+- Exchange hashpartitioning(city, category, 8)\n"
        "   +- HashAggregate(keys=[city, category], functions=[partial_sum(amount_mad)])\n"
        "      +- BroadcastHashJoin [restaurant_id], [restaurant_id], Inner, BuildRight\n"
        "         :- Filter (status = DELIVERED ...) +- InMemoryTableScan\n"
        "         +- BroadcastExchange\n"
        "            +- FileScan json [restaurant_id, category] PushedFilters: [IsNotNull(restaurant_id)]", sz=14))
    b.append(bullets([
        "**Plan logique (Parsed / Analyzed)** : la requête telle qu'écrite — `Filter` au-dessus de la lecture, "
        "`Join`, `Aggregate` — puis avec colonnes et types résolus grâce au schéma.",
        "**Plan optimisé par Catalyst** : ajout de `isnotnull(...)` sur les clés, filtre placé **sous** la jointure "
        "(*predicate pushdown*) et *column pruning* : seules `restaurant_id`, `city`, `amount_mad` remontent côté "
        "commandes, et seules `restaurant_id`, `category` sont lues dans le référentiel.",
        "**Stratégie physique : BroadcastHashJoin.** Le référentiel (200 lignes) est sous le seuil "
        "`autoBroadcastJoinThreshold` (10 Mo) : il est diffusé à chaque Executor (`BroadcastExchange`) et la grande "
        "table n'est pas shufflée pour la jointure. Le seul `Exchange` sert à l'agrégation, après un "
        "`partial_sum` local.",
    ]))
    b.append(P(f"En désactivant le broadcast, Spark choisit un `SortMergeJoin` : deux `Exchange hashpartitioning"
               f"(restaurant_id)` et deux `Sort` en plus. Mesuré : **{fr(t_smj)} s** contre **{fr(t_bhj)} s** en "
               f"`BroadcastHashJoin`."))
    b.append(image(os.path.join(CAP, "p3_sql_dag_jointure.png"), 6.2))
    b.append(caption("Figure 6 – Spark UI, onglet SQL / DataFrame : BroadcastExchange et BroadcastHashJoin"))

    b.append(H2("4.6 RDD, DataFrame et Dataset"))
    b.append(image(os.path.join(FIG, "temps_api.png"), 14))
    b.append(caption("Figure 7 – Temps mesurés (3 essais, même calcul complet relu depuis MinIO)"))
    b.append(table_caption("Tableau 6 – Comparaison des trois API"))
    b.append(table(["Critère", "RDD", "DataFrame", "Dataset"], [
        ["Typage", "objets Python / JVM, non structuré", "lignes `Row` + schéma, vérifié à l'exécution",
         "typé à la **compilation** (Scala / Java)"],
        ["Optimisation", "aucune : Spark exécute le code tel quel", "**Catalyst** (pushdown, pruning, choix de "
         "jointure) + **Tungsten**", "Catalyst + Tungsten (encoders)"],
        ["Python", "données sérialisées vers les workers Python", "exécution dans la JVM", "non disponible"],
        ["Mesure (CA par ville)", f"{fr(rdd_m)} s (min {fr(rdd_b)})", f"DF {fr(df_m)} s (min {fr(df_b)}) · "
         f"SQL {fr(sql_m)} s (min {fr(sql_b)})", "–"],
    ], [2.4, 3.2, 3.6, 3.0], sz=20))
    best_api, best_t = min([("DataFrame", df_b), ("Spark SQL", sql_b)], key=lambda x: x[1])
    b.append(P(f"Sur le même calcul, les API structurées sont plus rapides que le RDD : meilleur temps "
               f"{fr(df_b)} s en DataFrame et {fr(sql_b)} s en SQL contre {fr(rdd_b)} s en RDD "
               f"(×{fr(rdd_b / best_t, 1)} pour {best_api}). Le RDD Python paie la désérialisation JSON en "
               f"Python et le transfert de chaque objet entre JVM et Python ; le DataFrame lit le JSON directement "
               f"dans la JVM, ne garde que les colonnes utiles et agrège en format binaire (Tungsten). DataFrame et "
               f"SQL produisent le même plan Catalyst : leur écart vient du bruit de mesure (premier essai à "
               f"froid, petit volume de 12 Mo, cluster partagé sur un seul PC). Le **Dataset** n'existe qu'en "
               f"Scala / Java ; en PySpark, un DataFrame est un `Dataset[Row]`."))

    # ------------------------------------------------------------ conclusion
    b.append(H1("5. Conclusion"))
    b.append(P("Le cluster (Kafka KRaft, Spark Master + 2 Workers, MinIO, Jupyter) est opérationnel et "
               "reproductible avec une seule commande. Le traitement batch confirme l'intérêt de l'API structurée : "
               "mêmes résultats qu'en RDD, avec un code plus court, des plans optimisés automatiquement (pushdown, "
               "broadcast) et de meilleurs temps. La couche Silver Parquet partitionnée et le schéma explicite "
               "constituent la base du Jalon 2 (Structured Streaming depuis Kafka, Delta Lake, GraphFrames)."))
    return "".join(b)


# --------------------------------------------------------- assemblage -----
def run_cover(text):
    return (f'<w:r><w:rPr><w:rFonts w:ascii="Cambria" w:hAnsi="Cambria"/><w:sz w:val="28"/></w:rPr>'
            f'<w:t xml:space="preserve">{escape(text)}</w:t></w:r>')


BULLET_ABSTRACT = (
    f'<w:abstractNum w:abstractNumId="{BULLET_NUM_ID}"><w:multiLevelType w:val="hybridMultilevel"/>'
    '<w:lvl w:ilvl="0"><w:start w:val="1"/><w:numFmt w:val="bullet"/><w:lvlText w:val="&#8226;"/>'
    '<w:lvlJc w:val="left"/><w:pPr><w:ind w:left="567" w:hanging="283"/></w:pPr>'
    f'<w:rPr><w:rFonts w:ascii="Cambria" w:hAnsi="Cambria"/><w:color w:val="{BLUE}"/></w:rPr></w:lvl></w:abstractNum>')


def build(template):
    work = tempfile.mkdtemp()
    with zipfile.ZipFile(template) as z:
        z.extractall(work)
    wd = os.path.join(work, "word")
    doc = open(os.path.join(wd, "document.xml"), encoding="utf-8").read()

    # 1) page de garde = tout ce qui precede le titre « 1. Introduction » du modele
    body_start = doc.index("<w:body>") + len("<w:body>")
    first_title = doc.index("1. Introduction et objectif")
    cover_end = doc.rindex("<w:p ", 0, first_title)
    cover = doc[body_start:cover_end]
    sect = doc[doc.rindex("<w:sectPr"):doc.rindex("</w:body>")]
    # la page de garde du modele est une section a part (marges etroites, sans pied de page)
    cover_sect = re.findall(r"<w:sectPr[^>]*>.*?</w:sectPr>", doc, re.S)[0]
    cover_sect = re.sub(r'<w:type w:val="[^"]+"/>', "", cover_sect)
    for old, new in [("COMPTE RENDU", "RAPPORT DE PROJET – JALON 1"),
                     ("TP 1 – Machine Learning", "Écosystème Big Data 2"),
                     ("Prédiction du risque d'incendie", "Pipeline Spark–Kafka : FastFood.ma"),
                     ("Prédiction du risque d&apos;incendie", "Pipeline Spark–Kafka : FastFood.ma")]:
        cover = cover.replace(f">{old}<", f">{escape(new)}<")
    # sous-titre (Parties 1-3) juste apres le titre
    sub = para(run("Parties 1, 2 et 3 : cluster, SparkCore (RDD), Spark SQL / DataFrames",
                   italic=True, color="313D4F", sz=26), jc="center", before=120, after=0)
    marker = "Pipeline Spark–Kafka : FastFood.ma"
    i = cover.index(escape(marker))
    i = cover.index("</w:p>", i) + len("</w:p>")
    cover = cover[:i] + sub + cover[i:]
    # binome : on duplique la ligne « El Azzab Samah » de la liste « Realise par »
    i = cover.index(">Azzab<")
    start, end = cover.rindex("<w:p ", 0, i), cover.index("</w:p>", i) + len("</w:p>")
    ligne = cover[start:end]
    binome = ligne[:ligne.index("</w:pPr>") + len("</w:pPr>")]   # meme puce, meme style
    binome = re.sub(r' w14:(paraId|textId)="[^"]+"', "", binome)       # identifiants uniques
    binome = binome.replace('<w:spacing w:before="306"/>', '<w:spacing w:before="60"/>')
    binome += run_cover("Zriba Sami") + "</w:p>"
    cover = cover[:end] + binome + cover[end:]
    # le sous-titre et le binome ajoutent deux lignes : on retire des paragraphes vides pour rester sur 1 page
    vides = re.findall(r'<w:p [^>]*><w:pPr><w:pStyle w:val="Corpsdetexte"/><w:rPr><w:sz w:val="36"/></w:rPr></w:pPr></w:p>',
                       cover)
    for v in vides[:5]:
        cover = cover.replace(v, "", 1)

    body = build_body()
    cover += f'<w:p><w:pPr><w:spacing w:before="0" w:after="0"/>{cover_sect}</w:pPr></w:p>'
    new_doc = doc[:body_start] + cover + body + sect + "</w:body></w:document>"

    # 2) relations : on garde celles encore referencees + nouvelles images
    rels_p = os.path.join(wd, "_rels", "document.xml.rels")
    rels = open(rels_p, encoding="utf-8").read()
    used = set(re.findall(r'r:(?:embed|id|link)="([^"]+)"', new_doc))
    kept = []
    for r in re.findall(r"<Relationship [^>]+/>", rels):
        rid = re.search(r'Id="([^"]+)"', r).group(1)
        target = re.search(r'Target="([^"]+)"', r).group(1)
        if "relationships/image" in r and rid not in used:
            try:
                os.remove(os.path.join(wd, target))
            except OSError:
                pass
            continue
        kept.append(r)
    os.makedirs(os.path.join(wd, "media"), exist_ok=True)
    for rid, name, src in IMAGES.items:
        shutil.copy(src, os.path.join(wd, "media", name))
        kept.append(f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
                    f'relationships/image" Target="media/{name}"/>')
    rels = rels[:rels.index("<Relationship ")] + "".join(kept) + "</Relationships>"
    open(rels_p, "w", encoding="utf-8").write(rels)

    # 3) puces
    num_p = os.path.join(wd, "numbering.xml")
    num = open(num_p, encoding="utf-8").read()
    k = num.index("<w:num ")
    num = num[:k] + BULLET_ABSTRACT + num[k:]
    num = num.replace("</w:numbering>", f'<w:num w:numId="{BULLET_NUM_ID}"><w:abstractNumId '
                                        f'w:val="{BULLET_NUM_ID}"/></w:num></w:numbering>')
    open(num_p, "w", encoding="utf-8").write(num)

    # 4) metadonnees
    core = os.path.join(work, "docProps", "core.xml")
    if os.path.exists(core):
        c = open(core, encoding="utf-8").read()
        c = re.sub(r"<dc:title>.*?</dc:title>", "<dc:title>Rapport Jalon 1 - FastFood.ma</dc:title>", c)
        open(core, "w", encoding="utf-8").write(c)

    open(os.path.join(wd, "document.xml"), "w", encoding="utf-8").write(new_doc)
    if os.path.exists(OUT):
        os.remove(OUT)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as z:
        for folder, _, files in os.walk(work):
            for f in files:
                full = os.path.join(folder, f)
                z.write(full, os.path.relpath(full, work).replace(os.sep, "/"))
    shutil.rmtree(work)
    print("rapport ecrit :", OUT)


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else
          os.path.join(os.path.expanduser("~"), "Desktop", "TP-1 ML Samah El Azzab.docx"))
