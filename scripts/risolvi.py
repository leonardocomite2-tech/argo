"""Risolve le schede Places raccolte in contacts/identities. Non è un job
del worker: si lancia a mano dentro il container.
  docker compose exec worker python -m scripts.risolvi --citta NOME [--dry-run] \
      [--fonte-dettaglio NOME] [cartella_o_file]
"""
import argparse
import glob
import json
import logging
import os
import sys

import psycopg

from connectors.normalizza import (
    dominio, candidato_dominio, telefono_e164, nome_chiave, indirizzo_chiave,
    ammesso, DOMINIO_MAX_STRUTTURE_CONDIVISE,
)
from connectors.telegram import notifica

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.risolvi")

CARTELLA_DEFAULT = "/app/dati/places"


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def leggi_schede(percorso):
    """percorso può essere una cartella (scansiona *.jsonl) o un singolo
    file/pattern glob. Ritorna (scheda, nome_file_senza_estensione) — il
    nome file è il ripiego finale per fonte_dettaglio."""
    if os.path.isdir(percorso):
        file_paths = sorted(glob.glob(os.path.join(percorso, "*.jsonl")))
    else:
        file_paths = sorted(glob.glob(percorso)) or [percorso]
    for file_path in file_paths:
        nome_file = os.path.splitext(os.path.basename(file_path))[0]
        with open(file_path) as f:
            for riga in f:
                riga = riga.strip()
                if riga:
                    yield json.loads(riga), nome_file


def stampa_domini_da_valutare(conteggio_domini):
    """Top 10 domini per numero di strutture TRA quelli rimasti sotto
    DOMINIO_MAX_STRUTTURE_CONDIVISE (quindi ancora sito_proprio=True): sono i
    candidati più probabili a essere la prossima piattaforma di booking non
    ancora riconosciuta — qui si vedono da soli, senza doverli cercare a
    mano dopo ogni raccolta."""
    sotto_soglia = sorted(
        ((n, chiave) for chiave, n in conteggio_domini.items()
         if n <= DOMINIO_MAX_STRUTTURE_CONDIVISE),
        reverse=True,
    )
    print("\nDomini da valutare (più strutture, ancora sotto soglia):")
    for n, chiave in sotto_soglia[:10]:
        print(f"  {n:3d}  {chiave}")


def conta_domini(cartella_dati):
    """Prima passata, prima di qualunque risoluzione: quanti place_id
    distinti condividono ogni candidato dominio. SEMPRE sull'intera cartella
    dati (non sul solo file passato per la risoluzione in questo run) — così
    la soglia di dominio() è coerente indipendentemente dall'ordine in cui i
    file vengono lanciati, uno alla volta."""
    per_chiave = {}
    for scheda, _ in leggi_schede(cartella_dati):
        if not ammesso(scheda):
            continue
        chiave, proprio = candidato_dominio(scheda.get("websiteUri"))
        if proprio:
            per_chiave.setdefault(chiave, set()).add(scheda["id"])
    return {chiave: len(ids) for chiave, ids in per_chiave.items()}


def contatti_matchati(cur, chiavi):
    ids = set()
    for canale, valore in chiavi:
        cur.execute(
            "SELECT contact_id FROM identities WHERE canale=%s AND external_id=%s",
            (canale, valore),
        )
        row = cur.fetchone()
        if row:
            ids.add(row[0])
    return ids


def aggancia_identita(cur, contact_id, chiavi):
    """ON CONFLICT DO NOTHING + RETURNING: idempotente, un rilancio non
    ricrea nulla e non lo riconta come 'nuovo'."""
    nuove = 0
    for canale, valore in chiavi:
        cur.execute(
            """
            INSERT INTO identities (contact_id, canale, external_id)
            VALUES (%s, %s, %s)
            ON CONFLICT (canale, external_id) DO NOTHING
            RETURNING id
            """,
            (contact_id, canale, valore),
        )
        if cur.fetchone():
            nuove += 1
    return nuove


def aggiorna_n_strutture(cur, contact_id):
    cur.execute(
        "SELECT COUNT(*) FROM identities WHERE contact_id=%s AND canale='google_places'",
        (contact_id,),
    )
    n = cur.fetchone()[0]
    cur.execute(
        """
        UPDATE contacts
        SET attributi = jsonb_set(COALESCE(attributi, '{}'::jsonb), '{n_strutture}', %s::jsonb)
        WHERE id = %s
        """,
        (json.dumps(n), contact_id),
    )
    return n


def completa_campi_vuoti(cur, contact_id, nome, telefono, sito, indirizzo):
    """Riempie solo i campi NULL/vuoti — non tocca fonte/fonte_dettaglio né
    sovrascrive un valore già presente."""
    cur.execute(
        """
        UPDATE contacts SET
          nome      = COALESCE(NULLIF(nome, ''), %s),
          telefono  = COALESCE(NULLIF(telefono, ''), %s),
          sito      = COALESCE(NULLIF(sito, ''), %s),
          indirizzo = COALESCE(NULLIF(indirizzo, ''), %s)
        WHERE id = %s
        """,
        (nome, telefono, sito, indirizzo, contact_id),
    )


def completa_citta(cur, contact_id, citta):
    """Backfill di attributi.citta sui contatti già esistenti senza —
    creati prima che --citta diventasse obbligatorio. Non sovrascrive un
    valore già presente."""
    cur.execute(
        """
        UPDATE contacts
        SET attributi = jsonb_set(COALESCE(attributi, '{}'::jsonb), '{citta}', to_jsonb(%s::text))
        WHERE id = %s AND attributi->>'citta' IS NULL
        """,
        (citta, contact_id),
    )


def crea_contatto(cur, nome, telefono, sito, indirizzo, fonte_dettaglio, attributi):
    cur.execute(
        """
        INSERT INTO contacts (nome, telefono, sito, indirizzo, stato, fonte, fonte_dettaglio, attributi)
        VALUES (%s, %s, %s, %s, 'prospect', 'google_places', %s, %s::jsonb)
        RETURNING id
        """,
        (nome, telefono, sito, indirizzo, fonte_dettaglio, json.dumps(attributi)),
    )
    return cur.fetchone()[0]


def elabora_scheda(cur, scheda, fonte_dettaglio, citta, indice_debole, contatori, tocchi, conteggio_domini):
    place_id = scheda["id"]

    cur.execute(
        """
        INSERT INTO events (tipo, dedup_key, payload)
        VALUES ('prospect.places', %s, %s::jsonb)
        ON CONFLICT (dedup_key) DO NOTHING
        """,
        (f"places:{place_id}", json.dumps(scheda)),
    )

    nome = (scheda.get("displayName") or {}).get("text")
    indirizzo = scheda.get("formattedAddress")
    sito = scheda.get("websiteUri")
    telefono = telefono_e164(scheda.get("nationalPhoneNumber"), scheda.get("internationalPhoneNumber"))
    dom, proprio = dominio(sito, conteggio_domini)

    chiavi = [("google_places", place_id)]
    if dom and proprio:
        chiavi.append(("dominio", dom))
    if telefono:
        chiavi.append(("telefono", telefono))

    matches = contatti_matchati(cur, chiavi)

    if len(matches) == 1:
        contact_id = next(iter(matches))
        completa_campi_vuoti(cur, contact_id, nome, telefono, sito, indirizzo)
        completa_citta(cur, contact_id, citta)
        contatori["identita_agganciate"] += aggancia_identita(cur, contact_id, chiavi)
        n = aggiorna_n_strutture(cur, contact_id)
        tocchi[contact_id] = n
        return

    if len(matches) >= 2:
        contatori["conflitti"] += 1
        logger.warning("conflitto: place_id=%s chiavi=%s contatti=%s", place_id, chiavi, sorted(matches))
        return

    # Nessun match forte: nuovo contatto. Prima controllo il doppione debole.
    chiave_debole = None
    via, civico = indirizzo_chiave(indirizzo)
    chiave_nome = nome_chiave(nome)
    if chiave_nome and via:
        chiave_debole = (chiave_nome, via, civico)
        esistenti = indice_debole.get(chiave_debole, [])
        if esistenti:
            contatori["possibili_doppioni"] += 1
            logger.warning("possibile doppione: chiave_debole=%s contatti_esistenti=%s", chiave_debole, esistenti)

    attributi = {
        "tipo_primario": scheda.get("primaryType"),
        "rating": scheda.get("rating"),
        "numero_recensioni": scheda.get("userRatingCount"),
        "sito_proprio": proprio,
        "n_strutture": 1,
        "citta": citta,
    }
    contact_id = crea_contatto(cur, nome, telefono, sito, indirizzo, fonte_dettaglio, attributi)
    contatori["identita_agganciate"] += aggancia_identita(cur, contact_id, chiavi)
    contatori["contatti_nuovi"] += 1
    tocchi[contact_id] = 1

    if chiave_debole is not None:
        indice_debole.setdefault(chiave_debole, []).append(contact_id)


def carica_indice_debole(cur):
    cur.execute("SELECT id, nome, indirizzo FROM contacts")
    indice = {}
    for contact_id, nome, indirizzo in cur.fetchall():
        via, civico = indirizzo_chiave(indirizzo)
        chiave_nome = nome_chiave(nome)
        if chiave_nome and via:
            indice.setdefault((chiave_nome, via, civico), []).append(contact_id)
    return indice


def main():
    parser = argparse.ArgumentParser(description="Risolve le schede Places in contacts/identities")
    parser.add_argument("cartella", nargs="?", default=CARTELLA_DEFAULT,
                         help="cartella (scansiona *.jsonl) o singolo file/pattern")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--fonte-dettaglio",
                         help="usato se la scheda non ha _cella; altrimenti ripiego sul nome file")
    parser.add_argument("--citta", required=True,
                         help="es. 'roma' — scritta in attributi.citta su ogni contatto")
    args = parser.parse_args()

    contatori = {
        "lette": 0, "scartate_filtro": 0, "passate": 0,
        "contatti_nuovi": 0, "identita_agganciate": 0,
        "conflitti": 0, "possibili_doppioni": 0,
    }
    tocchi = {}  # contact_id -> n_strutture, per il conteggio finale
    conteggio_domini = conta_domini(CARTELLA_DEFAULT)

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            indice_debole = carica_indice_debole(cur)
            for scheda, nome_file in leggi_schede(args.cartella):
                contatori["lette"] += 1
                if not ammesso(scheda):
                    contatori["scartate_filtro"] += 1
                    continue
                contatori["passate"] += 1
                fonte_dettaglio = scheda.get("_cella") or args.fonte_dettaglio or nome_file
                elabora_scheda(cur, scheda, fonte_dettaglio, args.citta, indice_debole, contatori, tocchi, conteggio_domini)

        contatori["contatti_multi_struttura"] = sum(1 for n in tocchi.values() if n > 1)

        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    testo_report = (
        f"Schede lette: {contatori['lette']}\n"
        f"Scartate dal filtro: {contatori['scartate_filtro']}\n"
        f"Passate al resolver: {contatori['passate']}\n"
        f"Contatti nuovi: {contatori['contatti_nuovi']}\n"
        f"Identità agganciate: {contatori['identita_agganciate']}\n"
        f"Conflitti: {contatori['conflitti']}\n"
        f"Possibili doppioni: {contatori['possibili_doppioni']}\n"
        f"Contatti con più di una struttura: {contatori['contatti_multi_struttura']}"
    )
    print(testo_report)
    stampa_domini_da_valutare(conteggio_domini)

    if args.dry_run:
        print("\n--dry-run: nessuna scrittura mantenuta (rollback).")
    else:
        notifica(f"Risoluzione Places completata.\n{testo_report}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
