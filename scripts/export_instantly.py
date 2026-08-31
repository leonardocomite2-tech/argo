"""Export ripetibile per le ondate della campagna Instantly. Sola lettura
dal database (+ soppressioni), nessuna scrittura.
  docker compose exec worker python -m scripts.export_instantly \
      [--limite N] [--escludi file.csv ...] [--includi-personali] [--ondata N]

codice_host/zona/chiusura sono copy di campagna, non dati del contatto:
tre rotazioni stabili via hash dell'id su tre pool costanti (POOL_CODICI/
POOL_ZONE/POOL_CHIUSURE) — stesso contatto, stesso valore in ogni export
futuro, finché i pool non cambiano ordine/contenuto.
"""
import argparse
import csv
import hashlib
import os
import sys
from pathlib import Path

import psycopg

from scripts.export_prospect import calcola_punteggio

CARTELLA_EXPORT = "/app/dati/export"

POOL_CODICI = [
    "ROMA60", "OSPITE60", "GUIDA60", "BORGO60", "TEVERE60", "FORO60",
    "ARCO60", "PONTE60", "VICOLO60", "PIAZZA60", "DOMUS60", "CASA60",
    "SUITE60", "NIDO60", "ULIVO60", "ALBA60", "TRAM60", "LUPA60", "MURA60",
    "CUPOLA60",
]

POOL_ZONE = [
    "Centro Storico", "Campo Marzio", "Regola", "Ludovisi", "Monti",
    "Celio", "Esquilino", "Trastevere", "Testaccio", "Aventino", "Borgo",
    "Prati", "San Giovanni", "San Lorenzo", "Salario", "Nomentano",
    "Trieste", "Parioli", "Flaminio", "Ostiense", "Garbatella", "Balduina",
    "Tuscolano", "Appio",
]

POOL_CHIUSURE = [
    "Dai un'occhiata al sito e capisci meglio: riceverai anche un tuo depliant digitale personalizzabile.",
    "Guarda come funziona sul sito: ti spetta anche un depliant digitale personalizzabile.",
    "Trovi tutti i dettagli sul sito, insieme al tuo depliant digitale personalizzabile.",
    "Se vuoi capire meglio, sul sito trovi tutto — e un tuo depliant digitale personalizzabile.",
    "Sul sito trovi la spiegazione completa e il tuo depliant digitale personalizzabile.",
    "Ti lascio il sito: lì c'è tutto, compreso un depliant digitale personalizzabile.",
    "Il sito spiega ogni passaggio, e ti mette a disposizione un depliant digitale personalizzabile.",
    "Passa dal sito quando hai due minuti: c'è anche un depliant digitale personalizzabile per te.",
    "Sul sito capisci in un minuto come funziona, e prendi il tuo depliant digitale personalizzabile.",
    "Ti basta il sito per farti un'idea: dentro trovi anche un depliant digitale personalizzabile.",
    "Guarda il sito con calma: c'è la spiegazione e un depliant digitale personalizzabile.",
    "Sul sito c'è tutto quello che serve, incluso un depliant digitale personalizzabile.",
    "Fai un salto sul sito: ti chiarisce i dubbi e ti lascia un depliant digitale personalizzabile.",
    "Il resto lo trovi sul sito, insieme a un depliant digitale personalizzabile.",
    "Se ti va, guarda il sito: spiega tutto e include un depliant digitale personalizzabile.",
    "Trovi ogni dettaglio sul sito, e in più un depliant digitale personalizzabile.",
    "Il sito ti mostra come funziona davvero, e ti dà un depliant digitale personalizzabile.",
    "Basta un'occhiata al sito per capire, e ti porti via un depliant digitale personalizzabile.",
    "Sul sito trovi la versione completa, più un depliant digitale personalizzabile.",
    "Ti invito a guardare il sito: c'è la spiegazione e un depliant digitale personalizzabile.",
    "Sul sito è spiegato tutto per bene, e c'è un depliant digitale personalizzabile.",
    "Vai sul sito quando puoi: capisci meglio e ricevi un depliant digitale personalizzabile.",
    "Il sito risponde a tutte le domande, e ti lascia un depliant digitale personalizzabile.",
    "Dal sito capisci il funzionamento e ottieni un depliant digitale personalizzabile.",
    "Ti conviene guardare il sito: spiega ogni cosa e include un depliant digitale personalizzabile.",
    "Sul sito trovi tutti i passaggi, e anche un depliant digitale personalizzabile.",
    "Un'occhiata al sito ti chiarisce tutto, e ti dà un depliant digitale personalizzabile.",
    "Se vuoi approfondire, il sito spiega tutto e offre un depliant digitale personalizzabile.",
    "Il sito ti fa vedere come funziona, e ti mette a disposizione un depliant digitale personalizzabile.",
    "Tutto quello che ti serve è sul sito, insieme a un depliant digitale personalizzabile.",
]


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def _scegli(pool, contact_id, salt):
    """Rotazione stabile: stesso contact_id -> stesso elemento, per sempre,
    finché pool non cambia ordine/contenuto. hashlib invece di hash() di
    Python: quest'ultimo è salato per processo sulle stringhe, non stabile
    tra run diversi."""
    h = int(hashlib.sha256(f"{salt}:{contact_id}".encode()).hexdigest(), 16)
    return pool[h % len(pool)]


def carica_esclusi(percorsi):
    """Unione delle email (minuscole) lette dalla colonna 'email' di uno o
    più CSV di ondate precedenti."""
    esclusi = set()
    for percorso in percorsi or []:
        if not os.path.isfile(percorso):
            raise SystemExit(f"--escludi: file non trovato: {percorso}")
        with open(percorso, newline="") as f:
            for riga in csv.DictReader(f):
                email = (riga.get("email") or "").strip().lower()
                if email:
                    esclusi.add(email)
    return esclusi


def carica_contatti(cur, includi_personali):
    query = """
        SELECT c.id, c.email, c.nome, c.attributi, c.telefono, c.sito
        FROM contacts c
        WHERE c.stato = 'prospect'
          AND c.email IS NOT NULL AND c.email <> ''
    """
    if not includi_personali:
        query += " AND COALESCE(c.attributi->>'email_personale', 'false') = 'false'"
    query += """
          AND NOT EXISTS (
              SELECT 1 FROM soppressioni s WHERE s.tipo = 'email' AND s.valore = c.email
          )
    """
    cur.execute(query)
    return cur.fetchall()


def righe_csv(contatti, esclusi, limite):
    righe = []
    for contact_id, email, nome, attributi, telefono, sito in contatti:
        if email.strip().lower() in esclusi:
            continue
        attributi = attributi or {}
        righe.append({
            "email": email, "struttura": nome,
            "citta": attributi.get("citta"), "tipo": attributi.get("tipo_primario"),
            "n_strutture": attributi.get("n_strutture"), "telefono": telefono, "sito": sito,
            "punteggio": calcola_punteggio(attributi, telefono),
            "Nome Business": nome,
            "codice_host": _scegli(POOL_CODICI, contact_id, "codice"),
            "zona": _scegli(POOL_ZONE, contact_id, "zona"),
            "chiusura": _scegli(POOL_CHIUSURE, contact_id, "chiusura"),
        })
    righe.sort(key=lambda r: r["punteggio"], reverse=True)
    return righe[:limite]


def scrivi_csv(righe, ondata):
    Path(CARTELLA_EXPORT).mkdir(parents=True, exist_ok=True)
    percorso = Path(CARTELLA_EXPORT) / f"instantly_ondata{ondata}.csv"
    colonne = ["email", "struttura", "citta", "tipo", "n_strutture", "telefono",
               "sito", "punteggio", "Nome Business", "codice_host", "zona", "chiusura"]
    with percorso.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=colonne)
        writer.writeheader()
        writer.writerows(righe)
    return percorso


def stampa_distribuzione_zone(righe):
    conteggi = {}
    for r in righe:
        conteggi[r["zona"]] = conteggi.get(r["zona"], 0) + 1
    print("\nDistribuzione per zona (verifica, non un filtro):")
    for zona in POOL_ZONE:
        if conteggi.get(zona):
            print(f"  {conteggi[zona]:3d}  {zona}")


def main():
    parser = argparse.ArgumentParser(description="Export per un'ondata della campagna Instantly")
    parser.add_argument("--limite", type=int, default=50)
    parser.add_argument("--escludi", action="append",
                         help="CSV di un'ondata precedente, colonna 'email' — ripetibile")
    parser.add_argument("--includi-personali", action="store_true",
                         help="senza, esclude le email personali (gmail/outlook/...)")
    parser.add_argument("--ondata", type=int, default=1,
                         help="scrive instantly_ondata<N>.csv, sovrascritto se rilanciato con lo stesso N")
    args = parser.parse_args()

    esclusi = carica_esclusi(args.escludi)

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            contatti = carica_contatti(cur, args.includi_personali)
    finally:
        conn.close()

    righe = righe_csv(contatti, esclusi, args.limite)
    percorso = scrivi_csv(righe, args.ondata)

    idonei = sum(1 for c in contatti if c[1].strip().lower() not in esclusi)
    print(f"Contatti idonei prima del limite: {idonei}")
    print(f"Esportati in CSV (limite {args.limite}): {len(righe)}")
    print(f"File: {percorso}")
    stampa_distribuzione_zone(righe)

    return 0


if __name__ == "__main__":
    sys.exit(main())
