"""Esporta i contatti prospect in CSV, ordinati per punteggio. Deterministico,
zero LLM. Non è un job del worker: si lancia a mano dentro il container.
  docker compose exec worker python -m scripts.export_prospect [--limite N] [--solo-con-telefono]
"""
import argparse
import csv
import math
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import psycopg

CARTELLA_EXPORT = "/app/dati/export"

PUNTI_FORMA_IMPRESA = 15
TIPI_IMPRESA = {"guest_house", "hostel", "hotel", "inn", "extended_stay_hotel"}

PUNTI_VOLUME_OSPITI_MAX = 25
# Calibrato sui percentili reali del batch Roma (30/08): mediana=41,
# p90≈181, p95≈286, p99≈730, max=4445 — sopra RECENSIONI_CAP il punteggio
# satura a PUNTI_VOLUME_OSPITI_MAX, non serve premiare oltre. Valore rotondo
# scelto per la distribuzione osservata, non un dato — si aggiusta qui se la
# distribuzione cambia (altre città, più celle).
RECENSIONI_CAP = 1000

# Scala, non più un bonus fisso (30/08, ritarato): con un bonus unico i
# gestori con 4-6 strutture finivano sotto ostelli singoli col solo bonus
# forma impresa — il tipo pesava più della promettenza vera. Nessun tetto:
# la soglia di condivisione sui domini (connectors/normalizza.py) ha già
# tolto le piattaforme di booking, quindi n_strutture alto qui è un segnale
# reale di gestore multi-struttura, non rumore da fondere.
PUNTI_N_STRUTTURE = {2: 20, 3: 30, 4: 40}
PUNTI_N_STRUTTURE_5_PIU = 50

PUNTI_SITO_PROPRIO = 10
PUNTI_TELEFONO = 10


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def punteggio_volume_ospiti(numero_recensioni):
    if not numero_recensioni or numero_recensioni <= 0:
        return 0
    n = min(numero_recensioni, RECENSIONI_CAP)
    return round(PUNTI_VOLUME_OSPITI_MAX * math.log1p(n) / math.log1p(RECENSIONI_CAP))


def punteggio_n_strutture(n_strutture):
    n = n_strutture or 0
    if n >= 5:
        return PUNTI_N_STRUTTURE_5_PIU
    return PUNTI_N_STRUTTURE.get(n, 0)


def calcola_punteggio(attributi, telefono):
    attributi = attributi or {}
    punti = 0
    if attributi.get("tipo_primario") in TIPI_IMPRESA:
        punti += PUNTI_FORMA_IMPRESA
    punti += punteggio_volume_ospiti(attributi.get("numero_recensioni"))
    punti += punteggio_n_strutture(attributi.get("n_strutture"))
    if attributi.get("sito_proprio"):
        punti += PUNTI_SITO_PROPRIO
    if telefono:
        punti += PUNTI_TELEFONO
    return punti


def carica_contatti(cur, solo_con_telefono):
    """DISTINCT ON (c.id) + ORDER BY c.id, i.id: un contatto con più
    strutture (n_strutture>1) ha più identità google_places — si prende
    l'evento della prima (id più basso), un solo googleMapsUri per riga."""
    query = (
        "SELECT DISTINCT ON (c.id) "
        "c.id, c.nome, c.telefono, c.sito, c.indirizzo, c.fonte_dettaglio, c.attributi, "
        "e.payload->>'googleMapsUri' AS google_maps_uri "
        "FROM contacts c "
        "LEFT JOIN identities i ON i.contact_id = c.id AND i.canale = 'google_places' "
        "LEFT JOIN events e ON e.dedup_key = 'places:' || i.external_id "
        "WHERE c.stato = 'prospect'"
    )
    if solo_con_telefono:
        query += " AND c.telefono IS NOT NULL"
    query += " ORDER BY c.id, i.id"
    cur.execute(query)
    return cur.fetchall()


def righe_csv(contatti):
    righe = []
    for contact_id, nome, telefono, sito, indirizzo, fonte_dettaglio, attributi, google_maps_uri in contatti:
        attributi = attributi or {}
        righe.append({
            "nome": nome, "telefono": telefono, "sito": sito,
            "instagram": attributi.get("instagram"), "facebook": attributi.get("facebook"),
            "indirizzo": indirizzo,
            "tipo": attributi.get("tipo_primario"),
            "recensioni": attributi.get("numero_recensioni"),
            "n_strutture": attributi.get("n_strutture"),
            "fonte_dettaglio": fonte_dettaglio,
            "punteggio": calcola_punteggio(attributi, telefono),
            "id": contact_id,
            # attributi non ha mai googleMapsUri oggi (non è tra i campi che
            # risolvi.py ci scrive) — controllato comunque per primo, come
            # richiesto: se un giorno finisce lì, ha la precedenza sul JOIN.
            "googleMapsUri": attributi.get("googleMapsUri") or google_maps_uri,
            "esito": "",
        })
    righe.sort(key=lambda r: r["punteggio"], reverse=True)
    return righe


def scrivi_csv(righe, limite):
    Path(CARTELLA_EXPORT).mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    percorso = Path(CARTELLA_EXPORT) / f"prospect_{ts}.csv"
    colonne = ["nome", "telefono", "sito", "instagram", "facebook", "indirizzo",
               "tipo", "recensioni", "n_strutture", "fonte_dettaglio",
               "punteggio", "id", "googleMapsUri", "esito"]
    with percorso.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=colonne)
        writer.writeheader()
        writer.writerows(righe[:limite])
    return percorso


def stampa_top10(righe):
    print("\nTop 10 per punteggio:")
    for r in righe[:10]:
        print(f"  {r['nome']} | {r['telefono'] or '-'} | punteggio {r['punteggio']} | n_strutture {r['n_strutture']}")


def main():
    parser = argparse.ArgumentParser(description="Esporta i contatti prospect in CSV, ordinati per punteggio")
    parser.add_argument("--limite", type=int, default=30)
    parser.add_argument("--solo-con-telefono", action="store_true")
    args = parser.parse_args()

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            contatti = carica_contatti(cur, args.solo_con_telefono)
    finally:
        conn.close()

    righe = righe_csv(contatti)
    percorso = scrivi_csv(righe, args.limite)

    print(f"Contatti prospect trovati: {len(righe)}")
    print(f"Esportati in CSV (limite {args.limite}): {min(args.limite, len(righe))}")
    print(f"File: {percorso}")
    stampa_top10(righe)

    return 0


if __name__ == "__main__":
    sys.exit(main())
