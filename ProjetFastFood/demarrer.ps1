# Demarre l'environnement FastFood.ma et prepare les donnees des Parties 1 et 2.
# Utilisation (PowerShell, dans le dossier du projet) :   .\demarrer.ps1
# "Continue" : docker ecrit sa progression sur stderr, ce que PowerShell 5.1 prendrait pour une erreur
$ErrorActionPreference = "Continue"
Set-Location $PSScriptRoot

Write-Host "`n[1/4] Demarrage des conteneurs (Kafka, Spark Master + 2 Workers, MinIO, Jupyter)..." -ForegroundColor Cyan
docker compose up -d
if ($LASTEXITCODE -ne 0) { throw "docker compose up a echoue (Docker Desktop est-il lance ?)" }

Write-Host "`n[2/4] Attente de Jupyter et du bucket MinIO..." -ForegroundColor Cyan
for ($i = 0; $i -lt 60; $i++) {
    docker compose exec -T mc mc ls local/lake *> $null
    if ($LASTEXITCODE -eq 0) { break }
    Start-Sleep 3
}

Write-Host "`n[3/4] Generation de l'historique (producer.py --mode file --n 50000)..." -ForegroundColor Cyan
docker compose exec -T jupyter python /home/jovyan/work/producer/producer.py --mode file --n 50000 --out /home/jovyan/work/data/orders_history.jsonl

Write-Host "`n[4/4] Copie dans le Data Lake : lake/bronze/history/ et lake/bronze/reference/" -ForegroundColor Cyan
docker compose exec -T mc mc cp /data/orders_history.jsonl local/lake/bronze/history/orders_history.jsonl
docker compose exec -T mc mc cp /data/restaurants.json local/lake/bronze/reference/restaurants.json
docker compose exec -T mc mc ls --recursive local/lake/

Write-Host "`nTopic Kafka :" -ForegroundColor Cyan
docker compose exec -T kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic orders

Write-Host @"

Pret !
  Jupyter            : http://localhost:8888   (ouvrir notebooks/)
  Spark Master UI    : http://localhost:8090   (2 Workers ALIVE)
  Spark UI (appli)   : http://localhost:4040   (quand un notebook tourne)
  Console MinIO      : http://localhost:9001   (minioadmin / minioadmin)
"@ -ForegroundColor Green
