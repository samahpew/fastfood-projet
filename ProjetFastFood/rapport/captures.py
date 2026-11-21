"""
Captures d'ecran du rapport (Spark Master UI, console MinIO, DAG et plan SQL dans le
History Server), prises avec Playwright en pilotant le Chrome installe.

    pip install playwright
    python rapport/captures.py

Prerequis : docker compose up -d, notebooks des Parties 1 a 3 executes.
"""
import json
import os
import urllib.request

from playwright.sync_api import sync_playwright

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "captures")
HISTORY = "http://localhost:18080"
os.makedirs(OUT, exist_ok=True)


def api(path):
    with urllib.request.urlopen(f"{HISTORY}/api/v1/{path}") as r:
        return json.load(r)


def last_app(name):
    apps = [a for a in api("applications") if a["name"] == name]
    return max(apps, key=lambda a: a["attempts"][0]["startTime"])["id"]


def main():
    app2 = last_app("FastFood-Partie2-RDD")
    app3 = last_app("FastFood-Partie3-SQL")
    # job « CA par ville » : premier job du groupe ca_ville
    job = min(j["jobId"] for j in api(f"applications/{app2}/jobs") if j.get("jobGroup") == "ca_ville")
    # requete SQL de la jointure BroadcastHashJoin mesuree (derniere requete contenant ce noeud)
    sql = [q for q in api(f"applications/{app3}/sql?details=true&planDescription=true&length=500")
           if "BroadcastHashJoin" in q.get("planDescription", "")
           and "SortMergeJoin" not in q.get("planDescription", "")
           and "SortAggregate" not in q.get("planDescription", "")]      # pas de dedoublonnage
    sql_id = sql[-1]["id"]          # requete_jointure.collect() (filtre -> jointure -> agregation)
    print("app2", app2, "job", job, "| app3", app3, "sql", sql_id)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1400, "height": 900}, device_scale_factor=1.5)

        page.goto("http://localhost:8090")
        page.screenshot(path=f"{OUT}/p1_spark_master_ui.png", clip={"x": 0, "y": 0, "width": 1400, "height": 690})

        # console MinIO : connexion puis navigation dans le bucket lake
        page.goto("http://localhost:9001/login")
        page.fill("#accessKey", "minioadmin")
        page.fill("#secretKey", "minioadmin")
        page.click("button[type=submit]")
        page.wait_for_url("**/browser**", timeout=20000)
        page.goto("http://localhost:9001/browser/lake")
        page.wait_for_timeout(2500)
        for label in ("Acknowledge", "Accept", "OK", "Close"):   # fenetre de licence AGPL
            btn = page.get_by_role("button", name=label)
            if btn.count():
                btn.first.click()
                break
        else:
            page.keyboard.press("Escape")
        page.wait_for_timeout(1000)
        page.screenshot(path=f"{OUT}/p1_minio_lake.png", clip={"x": 0, "y": 0, "width": 1400, "height": 560})

        # DAG du job « CA par ville » (Partie 2)
        page.goto(f"{HISTORY}/history/{app2}/jobs/job/?id={job}")
        page.get_by_text("DAG Visualization").click()          # le DAG est replie par defaut
        page.wait_for_selector("#dag-viz-graph svg", timeout=20000)
        page.mouse.move(1350, 880)                              # pas d'infobulle sur le DAG
        page.wait_for_timeout(1500)
        top = page.get_by_text("DAG Visualization").bounding_box()["y"] - 10
        bottom = page.locator("span", has_text="Skipped Stages (").last.bounding_box()["y"] - 10
        page.screenshot(path=f"{OUT}/p2_dag_ca_ville.png", full_page=True,
                        clip={"x": 0, "y": top, "width": 1400, "height": bottom - top})

        # Plan SQL de la jointure (Partie 3)
        page.goto(f"{HISTORY}/history/{app3}/SQL/execution/?id={sql_id}")
        page.wait_for_selector("#plan-viz-graph svg", timeout=20000)
        page.wait_for_timeout(1500)
        graph = page.locator("#plan-viz-graph")
        bhj = page.locator("#plan-viz-graph g.node", has_text="BroadcastExchange").first.bounding_box()
        exch = page.locator("#plan-viz-graph g.node", has_text="shuffle records written").first.bounding_box()
        box = graph.bounding_box()
        # de la lecture jusqu'a l'Exchange de l'agregation (inclus), sans la marge vide a droite
        page.screenshot(path=f"{OUT}/p3_sql_dag_jointure.png", full_page=True,
                        clip={"x": box["x"], "y": box["y"],
                              "width": bhj["x"] + bhj["width"] + 30 - box["x"],
                              "height": exch["y"] + 40 - box["y"]})
        browser.close()
    print("captures ecrites dans", OUT)


if __name__ == "__main__":
    main()
