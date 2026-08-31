"""Cantiere B (email prospect): scarica home e, se la trova, una pagina
contatti per i prospect con sito proprio, ed estrae le email con una regex
deterministica — zero LLM, zero Firecrawl.
  docker compose exec worker python -m scripts.estrai_email \
      [--campione N] [--seme S] [--tutti --offset M] [--scrivi]

Senza --scrivi: solo lettura e stampa (comportamento originale, campione
casuale con --campione/--seme). Con --scrivi: salva l'email scelta su
contacts.email (solo se vuoto), registra l'identità 'email' e aggiorna
attributi.email_altre/email_personale. Con --tutti la selezione non è più
casuale ma paginata per id (--offset), per coprire tutti i prospect senza
buchi né doppioni tra un lotto e l'altro.

Il riepilogo finale, in particolare la ripartizione dei fallimenti per
motivo, serve a decidere se e per quanti siti servirà aprire Firecrawl.
"""
import argparse
import json
import os
import sys

import psycopg

from connectors.fetch import scarica, con_schema, host_di, trova_link_contatti
from connectors.normalizza import estrai_email, preferenza_email

MOTIVI = ("timeout", "dns", "403", "404", "500", "altro")


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def elabora_sito(sito, fallimenti_per_motivo):
    """Ritorna (email_trovate, host_sito, esito) dove esito è "ok" o
    "errore:<motivo>". Al massimo due pagine scaricate (home + contatti)."""
    url_home = con_schema(sito)
    host_sito = host_di(url_home)

    testo_home, motivo = scarica(url_home)
    if testo_home is None:
        fallimenti_per_motivo[motivo] = fallimenti_per_motivo.get(motivo, 0) + 1
        return [], host_sito, f"errore:{motivo}"

    email = estrai_email(testo_home)

    link_contatti = trova_link_contatti(testo_home, url_home, host_sito)
    if link_contatti:
        testo_contatti, motivo2 = scarica(link_contatti)
        if testo_contatti is None:
            fallimenti_per_motivo[motivo2] = fallimenti_per_motivo.get(motivo2, 0) + 1
        else:
            for indirizzo in estrai_email(testo_contatti):
                if indirizzo not in email:
                    email.append(indirizzo)

    return email, host_sito, "ok"


def dominio_di_email(indirizzo):
    dom = indirizzo.partition("@")[2]
    if dom.startswith("www."):
        dom = dom[4:]
    return dom


def salva_email_contatto(cur, contact_id, scelta, altre, personale):
    """Le tre scritture di --scrivi. contacts.email solo se vuoto (mai
    sovrascritto); identities ed email_altre/email_personale sempre
    aggiornati, indipendentemente da cosa c'era prima — descrivono cosa ha
    trovato questo run, non un valore storico da proteggere.
    Ritorna (email_scritta, identita_nuova)."""
    cur.execute(
        """
        UPDATE contacts SET email = %s
        WHERE id = %s AND (email IS NULL OR email = '')
        RETURNING id
        """,
        (scelta, contact_id),
    )
    email_scritta = cur.fetchone() is not None

    cur.execute(
        """
        UPDATE contacts
        SET attributi = jsonb_set(
            jsonb_set(COALESCE(attributi, '{}'::jsonb), '{email_altre}', %s::jsonb),
            '{email_personale}', %s::jsonb
        )
        WHERE id = %s
        """,
        (json.dumps(altre), json.dumps(personale), contact_id),
    )

    cur.execute(
        """
        INSERT INTO identities (contact_id, canale, external_id)
        VALUES (%s, 'email', %s)
        ON CONFLICT (canale, external_id) DO NOTHING
        RETURNING id
        """,
        (contact_id, scelta),
    )
    identita_nuova = cur.fetchone() is not None

    return email_scritta, identita_nuova


def stampa_totali_cumulativi(cur):
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE email IS NOT NULL AND email <> ''),
          COUNT(*) FILTER (WHERE email IS NOT NULL AND email <> ''
                            AND COALESCE(attributi->>'email_personale', 'false') = 'false'),
          COUNT(*) FILTER (WHERE email IS NOT NULL AND email <> ''
                            AND attributi->>'email_personale' = 'true')
        FROM contacts WHERE attributi->>'sito_proprio' = 'true'
        """
    )
    con_email, dominio_proprio, personali = cur.fetchone()
    print("\nTotali cumulativi sui prospect idonei (non solo questo lotto):")
    print(f"  con email: {con_email}")
    print(f"  di cui su dominio proprio: {dominio_proprio}")
    print(f"  di cui personali (dominio diverso dal sito): {personali}")


def stampa_domini_email_frequenti(cur, top=15):
    """Un placeholder da template si riconosce perché compare su decine di
    siti scollegati tra loro — questa lista lo mostra da sola, invece di
    scoprirlo a campione ogni volta che ne spunta uno nuovo."""
    cur.execute(
        """
        SELECT split_part(email, '@', 2) AS dominio, COUNT(*) AS n
        FROM contacts
        WHERE attributi->>'sito_proprio' = 'true' AND email IS NOT NULL AND email <> ''
        GROUP BY dominio
        ORDER BY n DESC
        LIMIT %s
        """,
        (top,),
    )
    righe = cur.fetchall()
    print(f"\nDomini email più frequenti tra le scelte (top {top}):")
    for dominio, n in righe:
        print(f"  {n:3d}  {dominio}")


def main():
    parser = argparse.ArgumentParser(description="Email dai siti prospect (GET diretto, senza Firecrawl)")
    parser.add_argument("--campione", type=int, default=20,
                         help="quante righe processa questa invocazione (campione casuale, o dimensione lotto con --tutti)")
    parser.add_argument("--seme", type=int, default=None,
                         help="fissa il campione casuale per poterlo ripetere identico (ignorato con --tutti)")
    parser.add_argument("--tutti", action="store_true",
                         help="selezione paginata per id invece che casuale, per coprire tutti i prospect a lotti")
    parser.add_argument("--offset", type=int, default=0, help="usato solo con --tutti")
    parser.add_argument("--scrivi", action="store_true",
                         help="salva l'email scelta su contacts/identities; senza, solo lettura e stampa")
    args = parser.parse_args()

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            if args.tutti:
                cur.execute(
                    """
                    SELECT id, nome, sito FROM contacts
                    WHERE attributi->>'sito_proprio' = 'true'
                    ORDER BY id
                    LIMIT %s OFFSET %s
                    """,
                    (args.campione, args.offset),
                )
            else:
                if args.seme is not None:
                    seme_normalizzato = ((args.seme % 2_000_000) / 1_000_000.0) - 1.0
                    cur.execute("SELECT setseed(%s)", (seme_normalizzato,))
                cur.execute(
                    """
                    SELECT id, nome, sito FROM contacts
                    WHERE attributi->>'sito_proprio' = 'true'
                    ORDER BY random()
                    LIMIT %s
                    """,
                    (args.campione,),
                )
            campione = cur.fetchall()

            cur.execute(
                "SELECT COUNT(*) FROM contacts WHERE attributi->>'sito_proprio' = 'true'"
            )
            totale_idonei = cur.fetchone()[0]

            fallimenti_per_motivo = {}
            righe = []
            con_email = 0
            senza_email = 0
            errori = 0
            email_scritte = 0
            identita_nuove = 0

            for contact_id, nome, sito in campione:
                email, host_sito, esito = elabora_sito(sito, fallimenti_per_motivo)
                if esito != "ok":
                    errori += 1
                elif email:
                    con_email += 1
                else:
                    senza_email += 1

                scelta = min(email, key=lambda e: preferenza_email(e, host_sito)) if email else ""
                righe.append((nome or "", sito or "", ", ".join(email), scelta, esito))

                if args.scrivi and scelta:
                    altre = [e for e in email if e != scelta]
                    personale = dominio_di_email(scelta) != host_sito
                    scritta, nuova = salva_email_contatto(cur, contact_id, scelta, altre, personale)
                    conn.commit()
                    if scritta:
                        email_scritte += 1
                    if nuova:
                        identita_nuove += 1

            intestazione = f"{'nome':<30} {'sito':<35} {'email trovate':<45} {'scelta':<30} {'esito'}"
            print(intestazione)
            print("-" * len(intestazione))
            for nome, sito, email_join, scelta, esito in righe:
                print(f"{nome[:30]:<30} {sito[:35]:<35} {email_join[:45]:<45} {scelta[:30]:<30} {esito}")

            stima_totale = None
            provati = len(campione)
            if provati and not args.tutti:
                stima_totale = round((con_email / provati) * totale_idonei)

            print()
            print(f"Siti provati: {provati}")
            print(f"Siti con almeno un'email: {con_email}")
            print(f"Siti senza email (scaricati ma 0 trovate): {senza_email}")
            print(f"Errori (home irraggiungibile): {errori}")
            print("Fallimenti per motivo (home + pagina contatti):")
            for motivo in MOTIVI:
                if fallimenti_per_motivo.get(motivo):
                    print(f"  {motivo}: {fallimenti_per_motivo[motivo]}")
            if not fallimenti_per_motivo:
                print("  nessuno")
            print(f"Prospect idonei totali (sito_proprio=true): {totale_idonei}")
            if stima_totale is not None:
                print(f"Stima siti con email se applicato a tutti: ~{stima_totale}")
            if args.scrivi:
                print(f"Email scritte su contacts.email: {email_scritte}")
                print(f"Identità 'email' nuove: {identita_nuove}")

            stampa_totali_cumulativi(cur)
            stampa_domini_email_frequenti(cur)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
