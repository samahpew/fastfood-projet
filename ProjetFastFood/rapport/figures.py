"""
Figures du rapport (Jalon 1) a partir des fichiers de results/ produits par les notebooks.

    python rapport/figures.py          -> rapport/figures/*.png
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RES = os.path.join(ROOT, "results")
OUT = os.path.join(ROOT, "rapport", "figures")
os.makedirs(OUT, exist_ok=True)

BLUE, BLUE_L, RED, GREEN, GREY = "#1F4E79", "#9DC3E6", "#C00000", "#005E00", "#595959"
plt.rcParams.update({"font.family": "Cambria", "font.size": 11,
                     "axes.spines.top": False, "axes.spines.right": False})


def box(ax, x, y, w, h, title, sub="", fc="#F2F6FA", ec=BLUE):
    ax.add_patch(FancyBboxPatch((x, y), w, h, boxstyle="round,pad=0.02,rounding_size=0.08",
                                fc=fc, ec=ec, lw=1.4))
    ax.text(x + w / 2, y + h / 2 + (0.13 if sub else 0), title, ha="center", va="center",
            fontsize=11.5, fontweight="bold", color="#1A1A1A")
    if sub:
        ax.text(x + w / 2, y + h / 2 - 0.2, sub, ha="center", va="center", fontsize=9, color=GREY)


def arrow(ax, x1, y1, x2, y2, label="", color=GREY, dy=0.12):
    ax.annotate("", xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=1.5))
    if label:
        ax.text((x1 + x2) / 2, (y1 + y2) / 2 + dy, label, ha="center", fontsize=8.5, color=color)


def architecture():
    fig, ax = plt.subplots(figsize=(10, 4.6))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 4.6)
    ax.axis("off")

    # flux temps reel (Jalon 2)
    box(ax, 0.1, 3.2, 1.7, 0.9, "producer.py", "mode kafka / file")
    box(ax, 2.4, 3.2, 1.9, 0.9, "Kafka (KRaft)", "topic orders · 3 partitions")
    arrow(ax, 1.8, 3.65, 2.4, 3.65)

    # cluster Spark
    ax.add_patch(FancyBboxPatch((4.9, 0.95), 2.6, 3.25, boxstyle="round,pad=0.02,rounding_size=0.1",
                                fc="white", ec=BLUE, lw=1.2, ls="--"))
    ax.text(6.2, 4.0, "Cluster Spark 3.5.3 (standalone)", ha="center", fontsize=9.5,
            color=BLUE, fontweight="bold")
    box(ax, 5.05, 3.0, 2.3, 0.75, "Driver (Jupyter)", "SparkSession · SparkContext", fc="#FDECEC", ec=RED)
    box(ax, 5.05, 2.05, 2.3, 0.7, "Spark Master :7077", "Cluster Manager")
    box(ax, 5.05, 1.05, 1.1, 0.75, "Worker 1", "Executor", fc="#E8F3E8", ec=GREEN)
    box(ax, 6.25, 1.05, 1.1, 0.75, "Worker 2", "Executor", fc="#E8F3E8", ec=GREEN)
    arrow(ax, 6.2, 3.0, 6.2, 2.75)
    arrow(ax, 5.8, 2.05, 5.6, 1.8)
    arrow(ax, 6.6, 2.05, 6.8, 1.8)
    arrow(ax, 4.3, 3.45, 5.05, 3.4)
    ax.text(4.68, 3.62, "J2", ha="center", fontsize=8.5, color=GREY)

    # MinIO
    ax.add_patch(FancyBboxPatch((8.0, 0.45), 1.9, 3.75, boxstyle="round,pad=0.02,rounding_size=0.1",
                                fc="#F7F7F7", ec=GREY, lw=1.2))
    ax.text(8.95, 3.95, "MinIO · bucket lake", ha="center", fontsize=10, fontweight="bold")
    for i, (name, sub, c) in enumerate([("bronze/", "history · reference\norders_raw (J2)", "#C9A66B"),
                                        ("silver/", "orders_history (Parquet)\norders_clean (J2)", "#A6A6A6"),
                                        ("gold/", "kpi_city_10min (Delta, J2)", "#E2B007")]):
        y = 2.85 - i * 1.0
        ax.add_patch(FancyBboxPatch((8.15, y), 1.6, 0.8, boxstyle="round,pad=0.01,rounding_size=0.06",
                                    fc="white", ec=c, lw=2))
        ax.text(8.95, y + 0.55, name, ha="center", fontsize=10.5, fontweight="bold", color="#333333")
        ax.text(8.95, y + 0.22, sub, ha="center", fontsize=7.5, color=GREY, linespacing=1.1)
    arrow(ax, 7.5, 2.45, 8.0, 2.45, color=BLUE)
    arrow(ax, 8.0, 2.25, 7.5, 2.25, color=BLUE)
    ax.text(7.75, 2.6, "S3A", ha="center", fontsize=9, color=BLUE, fontweight="bold")

    # historique (Jalon 1) : copie dans bronze/ par le client mc
    box(ax, 0.1, 1.05, 1.7, 0.9, "orders_history", "50 000 événements")
    box(ax, 2.4, 1.05, 1.9, 0.9, "restaurants.json", "200 restaurants")
    ax.plot([0.95, 0.95, 8.0], [1.05, 0.62, 0.62], color="#8A6D3B", lw=1.3, ls="--")
    ax.plot([3.35, 3.35], [1.05, 0.62], color="#8A6D3B", lw=1.3, ls="--")
    arrow(ax, 7.9, 0.62, 8.05, 0.62, color="#8A6D3B")
    ax.text(5.9, 0.68, "mc cp → lake/bronze/ (Jalon 1)", ha="center", fontsize=9, color="#8A6D3B")
    ax.text(0.1, 0.12, "Jalon 1 : traitement batch (RDD, DataFrame, SQL)   ·   "
                       "J2 : streaming Kafka, Delta Lake, graphes (Parties 4–6)",
            fontsize=8.5, color=GREY, style="italic")
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "architecture.png"), dpi=200)
    plt.close(fig)


def ca_ville():
    df = pd.read_csv(os.path.join(RES, "partie2_ca_panier_par_ville.csv"))
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.4))
    bars = a1.bar(df["ville"], df["CA (MAD)"] / 1000, color=BLUE, width=0.6)
    a1.set_title("Chiffre d'affaires (milliers de MAD)", fontsize=11.5)
    a1.bar_label(bars, labels=[f"{v / 1000:,.0f}".replace(",", " ") for v in df["CA (MAD)"]],
                 padding=2, fontsize=9.5)
    a1.set_ylim(0, df["CA (MAD)"].max() / 1000 * 1.15)
    bars = a2.bar(df["ville"], df["panier moyen (MAD)"], color=GREEN, width=0.6)
    a2.set_title("Panier moyen (MAD)", fontsize=11.5)
    a2.bar_label(bars, labels=[f"{v:.2f}" for v in df["panier moyen (MAD)"]], padding=2, fontsize=9.5)
    a2.set_ylim(0, df["panier moyen (MAD)"].max() * 1.15)
    for a in (a1, a2):
        a.tick_params(axis="y", labelsize=9)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "ca_panier_ville.png"), dpi=200)
    plt.close(fig)


def temps():
    p2 = json.load(open(os.path.join(RES, "partie2_timings.json"), encoding="utf-8"))
    p3 = json.load(open(os.path.join(RES, "partie3_timings.json"), encoding="utf-8"))

    def essais(d, prefixe):
        return [v for k, v in d.items() if k.startswith(prefixe)]

    groupes = [("RDD", essais(p2, "CA par ville RDD sans cache")),
               ("DataFrame", essais(p3, "CA par ville DataFrame sans cache")),
               ("Spark SQL", essais(p3, "CA par ville SQL sans cache")),
               ("UDF Python", essais(p3, "distance_band UDF")),
               ("when/otherwise", essais(p3, "distance_band when"))]
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(10, 3.1), gridspec_kw={"width_ratios": [3, 2]})
    for ax, sub, titre, couleurs in [
            (a1, groupes[:3], "CA par ville, calcul complet sans cache", [RED, BLUE, BLUE_L]),
            (a2, groupes[3:], "Colonne distance_band (données en cache)", [RED, BLUE])]:
        noms = [g[0] for g in sub]
        meilleurs = [min(g[1]) for g in sub]
        moyens = [sum(g[1]) / len(g[1]) for g in sub]
        bars = ax.bar(noms, moyens, color=couleurs, width=0.55)
        ax.bar_label(bars, labels=[f"moy. {m:.2f} s\n(min {b:.2f} s)" for m, b in zip(moyens, meilleurs)],
                     padding=2, fontsize=9)
        ax.set_title(titre, fontsize=11)
        ax.set_ylabel("secondes", fontsize=9.5)
        ax.set_ylim(0, max(moyens) * 1.35)
        ax.tick_params(labelsize=9.5)
    fig.tight_layout()
    fig.savefig(os.path.join(OUT, "temps_api.png"), dpi=200)
    plt.close(fig)


if __name__ == "__main__":
    architecture()
    ca_ville()
    temps()
    print("figures ecrites dans", OUT)
