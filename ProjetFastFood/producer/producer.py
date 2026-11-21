#!/usr/bin/env python3
"""
producer.py - Generateur de commandes FastFood.ma

Simule une plateforme de livraison (Casablanca, Rabat, Marrakech, Tanger).
Chaque commande produit un evenement JSON par changement d'etat :
    CREATED -> PICKED_UP -> DELIVERED      (ou CREATED [-> PICKED_UP] -> CANCELLED)

Cas reels simules volontairement :
  * ~5 % d'evenements en retard (jusqu'a 15 minutes, livreur hors reseau)
  * ~2 % de doublons (meme order_id et meme status)

Modes :
  --mode file   : ecrit un historique JSON Lines (Partie 2 / 3)
      python producer.py --mode file --n 50000 --out data/orders_history.jsonl
  --mode kafka  : publie en continu dans le topic Kafka "orders" (Partie 4 / 5)
      python producer.py --mode kafka --rate 20 --bootstrap kafka:9092

Le referentiel restaurants.json (200 lignes) est (re)genere a cote du fichier
de sortie avec --restaurants (par defaut : meme dossier que --out).
"""
import argparse
import heapq
import json
import math
import os
import random
import sys
import time
from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------
# Referentiel
# --------------------------------------------------------------------------
CITIES = {
    # ville: (poids, prefixe livreur, nb livreurs, centre lat, centre lon)
    "Casablanca": (0.45, "CAS", 40, 33.5731, -7.5898),
    "Rabat":      (0.22, "RAB", 20, 34.0209, -6.8416),
    "Marrakech":  (0.18, "MAR", 18, 31.6295, -7.9811),
    "Tanger":     (0.15, "TAN", 14, 35.7595, -5.8340),
}
CATEGORIES = {
    # categorie: prix unitaire moyen (MAD)
    "pizza": 55, "tacos": 45, "sushi": 85, "marocain": 60,
    "burger": 50, "poulet": 40, "asiatique": 65, "healthy": 70,
}
NAME_PREFIX = ["Chez", "Le", "La", "Dar", "Snack", "Station", "Maison", "Bab"]
NAME_SUFFIX = ["Atlas", "Medina", "Oasis", "Corniche", "Andalous", "Saveurs",
               "Express", "Gourmet", "Riad", "Palmier", "Soleil", "Kasbah"]
N_RESTAURANTS = 200
N_CUSTOMERS = 20000

LATE_RATE = 0.05        # 5 % d'evenements en retard
LATE_MAX_MIN = 15       # jusqu'a 15 minutes
DUP_RATE = 0.02         # 2 % de doublons
CANCEL_RATE = 0.08      # 8 % de commandes annulees


def build_restaurants(rng):
    cities = list(CITIES)
    weights = [CITIES[c][0] for c in cities]
    restaurants = []
    for i in range(1, N_RESTAURANTS + 1):
        city = rng.choices(cities, weights)[0]
        _, _, _, lat, lon = CITIES[city]
        cat = rng.choice(list(CATEGORIES))
        restaurants.append({
            "restaurant_id": f"R-{i:03d}",
            "name": f"{rng.choice(NAME_PREFIX)} {rng.choice(NAME_SUFFIX)} {cat.capitalize()}",
            "city": city,
            "category": cat,
            "latitude": round(lat + rng.uniform(-0.06, 0.06), 6),
            "longitude": round(lon + rng.uniform(-0.06, 0.06), 6),
        })
    return restaurants


def iso(dt):
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class OrderFactory:
    """Cree une commande complete (liste d'evenements horodates)."""

    def __init__(self, rng, restaurants):
        self.rng = rng
        self.counter = 0
        self.by_city = {}
        for r in restaurants:
            self.by_city.setdefault(r["city"], []).append(r)
        # popularite heterogene des restaurants (loi de Zipf legere)
        self.rest_weights = {
            c: [1.0 / (k + 1) ** 0.6 for k in range(len(rs))]
            for c, rs in self.by_city.items()
        }
        self.cities = list(CITIES)
        self.city_w = [CITIES[c][0] for c in self.cities]

    def new_order(self, t0):
        rng = self.rng
        self.counter += 1
        city = rng.choices(self.cities, self.city_w)[0]
        _, cprefix, ncour, _, _ = CITIES[city]
        resto = rng.choices(self.by_city[city], self.rest_weights[city])[0]
        items = rng.choices([1, 2, 3, 4, 5, 6], [20, 30, 25, 13, 8, 4])[0]
        unit = CATEGORIES[resto["category"]]
        amount = round(sum(rng.uniform(0.7, 1.3) * unit for _ in range(items)) + rng.choice([0, 10, 15]), 2)
        distance = round(min(15.0, max(0.3, rng.lognormvariate(1.1, 0.6))), 1)
        base = {
            "order_id": f"ORD-{self.counter:07d}",
            "restaurant_id": resto["restaurant_id"],
            "customer_id": f"C-{rng.randint(1, N_CUSTOMERS):05d}",
            "city": city,
            "amount_mad": amount,
            "items_count": items,
            "distance_km": distance,
            "courier_id": f"L-{cprefix}-{rng.randint(1, ncour):02d}",
        }
        events = [(t0, "CREATED")]
        t_pick = t0 + timedelta(minutes=rng.uniform(5, 20))
        if rng.random() < CANCEL_RATE:
            if rng.random() < 0.3:          # annulee apres recuperation
                events.append((t_pick, "PICKED_UP"))
                events.append((t_pick + timedelta(minutes=rng.uniform(1, 10)), "CANCELLED"))
            else:                           # annulee avant recuperation
                events.append((t0 + timedelta(minutes=rng.uniform(1, 12)), "CANCELLED"))
        else:
            events.append((t_pick, "PICKED_UP"))
            travel = distance * rng.uniform(2.5, 4.5) + rng.uniform(2, 8)
            events.append((t_pick + timedelta(minutes=travel), "DELIVERED"))
        return [dict(base, status=s, event_time=iso(t)) | {"_t": t} for t, s in events]


def hour_weight(h):
    """Pics au dejeuner et au diner."""
    return 0.15 + math.exp(-((h - 13) ** 2) / 2.0) + 1.3 * math.exp(-((h - 20.5) ** 2) / 3.0)


def clean(ev):
    return {k: v for k, v in ev.items() if k != "_t"}


# --------------------------------------------------------------------------
# Mode file : historique
# --------------------------------------------------------------------------
def run_file(args, rng, factory):
    start = datetime.fromisoformat(args.start.replace("Z", "+00:00"))
    span = args.days * 86400
    events = []
    while len(events) < args.n * 1.02:
        # tirage d'un instant pondere par l'heure (rejection sampling)
        while True:
            t0 = start + timedelta(seconds=rng.uniform(0, span))
            if rng.random() * 2.6 < hour_weight(t0.hour + t0.minute / 60):
                break
        events.extend(factory.new_order(t0))
    events.sort(key=lambda e: e["_t"])

    # numeros de commande chronologiques (ordre de creation)
    renum = {}
    for e in events:
        if e["status"] == "CREATED":
            renum[e["order_id"]] = f"ORD-{len(renum) + 1:07d}"
    for e in events:
        e["order_id"] = renum[e["order_id"]]

    # Arrivee : un evenement en retard apparait plus loin dans le fichier
    arrival = []
    for e in events:
        delay = timedelta(minutes=rng.uniform(1, LATE_MAX_MIN)) if rng.random() < LATE_RATE else timedelta(0)
        arrival.append((e["_t"] + delay, e))
        if rng.random() < DUP_RATE:     # doublon : meme order_id + meme status
            arrival.append((e["_t"] + delay + timedelta(seconds=rng.uniform(1, 30)), e))
    arrival.sort(key=lambda x: x[0])
    arrival = arrival[: args.n]

    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for _, e in arrival:
            f.write(json.dumps(clean(e), ensure_ascii=False) + "\n")
    print(f"[file] {len(arrival)} evenements ecrits dans {args.out}")


# --------------------------------------------------------------------------
# Mode kafka : flux temps reel
# --------------------------------------------------------------------------
def run_kafka(args, rng, factory):
    try:
        from kafka import KafkaProducer
    except ImportError:
        sys.exit("Module kafka manquant : pip install 'kafka-python>=2.1'")

    producer = KafkaProducer(
        bootstrap_servers=args.bootstrap,
        key_serializer=lambda k: k.encode("utf-8"),
        value_serializer=lambda v: json.dumps(v, ensure_ascii=False).encode("utf-8"),
        acks="all",
        linger_ms=20,
    )
    scheduled = []   # (temps d'envoi, seq, evenement)  -> etats futurs + retards
    seq = 0
    sent = late = dups = 0
    print(f"[kafka] envoi vers {args.bootstrap} topic={args.topic} rate={args.rate}/s (Ctrl+C pour arreter)")

    def send(ev):
        nonlocal sent, dups
        producer.send(args.topic, key=ev["order_id"], value=clean(ev))
        sent += 1
        if rng.random() < DUP_RATE:
            producer.send(args.topic, key=ev["order_id"], value=clean(ev))
            sent += 1
            dups += 1

    try:
        while True:
            tick = time.time()
            now = datetime.now(timezone.utc)
            emitted = 0
            # 1) etats dus (PICKED_UP, DELIVERED...) et evenements en retard
            while scheduled and scheduled[0][0] <= now and emitted < args.rate:
                _, _, ev = heapq.heappop(scheduled)
                send(ev)
                emitted += 1
            # 2) nouvelles commandes pour completer le debit
            while emitted < args.rate:
                evs = factory.new_order(now)
                for ev in evs:
                    when = ev["_t"]
                    if rng.random() < LATE_RATE:   # livreur hors reseau
                        when = when + timedelta(minutes=rng.uniform(1, LATE_MAX_MIN))
                        late += 1
                    if when <= now:
                        send(ev)
                        emitted += 1
                    else:
                        seq += 1
                        heapq.heappush(scheduled, (when, seq, ev))
            producer.flush()
            if args.max_events and sent >= args.max_events:
                break
            if int(tick) % 10 == 0:
                print(f"[kafka] envoyes={sent} en_attente={len(scheduled)} retards={late} doublons={dups}", flush=True)
            time.sleep(max(0.0, 1.0 - (time.time() - tick)))
    except KeyboardInterrupt:
        pass
    finally:
        producer.flush()
        producer.close()
        print(f"[kafka] termine : {sent} evenements envoyes")


def main():
    p = argparse.ArgumentParser(description="Generateur de commandes FastFood.ma")
    p.add_argument("--mode", choices=["file", "kafka"], required=True)
    p.add_argument("--n", type=int, default=50000, help="[file] nombre d'evenements")
    p.add_argument("--out", default="data/orders_history.jsonl", help="[file] fichier de sortie")
    p.add_argument("--start", default="2026-10-16T00:00:00Z", help="[file] debut de l'historique (UTC)")
    p.add_argument("--days", type=int, default=30, help="[file] duree de l'historique en jours")
    p.add_argument("--restaurants", default=None, help="chemin de restaurants.json")
    p.add_argument("--rate", type=int, default=20, help="[kafka] evenements par seconde")
    p.add_argument("--bootstrap", default=os.getenv("KAFKA_BOOTSTRAP", "kafka:9092"))
    p.add_argument("--topic", default="orders")
    p.add_argument("--max-events", type=int, default=0, help="[kafka] arret apres N evenements (0 = infini)")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    # Le referentiel utilise toujours la meme graine -> memes restaurants partout
    restaurants = build_restaurants(random.Random(2026))
    rpath = args.restaurants or os.path.join(os.path.dirname(os.path.abspath(args.out)), "restaurants.json")
    os.makedirs(os.path.dirname(rpath), exist_ok=True)
    with open(rpath, "w", encoding="utf-8") as f:
        for r in restaurants:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[ref] {len(restaurants)} restaurants ecrits dans {rpath}")

    rng = random.Random(args.seed if args.mode == "file" else None)
    factory = OrderFactory(rng, restaurants)
    if args.mode == "file":
        run_file(args, rng, factory)
    else:
        run_kafka(args, rng, factory)


if __name__ == "__main__":
    main()
