"""Campione di misura per il cantiere B (email prospect): scarica home e,
se la trova, una pagina contatti per un campione casuale di prospect con
sito proprio, ed estrae le email con una regex deterministica — zero LLM,
zero Firecrawl. Non scrive nulla sul database, solo lettura e stampa.
  docker compose exec worker python -m scripts.estrai_email \
      [--campione N] [--seme S]

Il riepilogo finale, in particolare la ripartizione dei fallimenti per
motivo, serve a decidere se e per quanti siti servirà aprire Firecrawl.
"""
import argparse
import os
import re
import sys
from urllib.parse import urljoin, urlsplit

import psycopg

from connectors.fetch import scarica
from connectors.normalizza import estrai_email, preferenza_email

PATTERN_LINK = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
PATTERN_TAG = re.compile(r"<[^>]+>")
PAROLE_CONTATTO = ("contatt", "contact", "prenot", "booking", "reserv", "chi-siamo", "about")

MOTIVI = ("timeout", "dns", "403", "404", "500", "altro")


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def con_schema(url):
    url = url.strip()
    if not url.lower().startswith(("http://", "https://")):
        return "https://" + url
    return url


def host_di(url):
    host = urlsplit(url).netloc.split("@")[-1].split(":")[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def trova_link_contatti(html, url_base, host_sito):
    """Primo link interno (stesso host) il cui href o testo somiglia a una
    pagina contatti. None se non ne trova uno."""
    for href, testo in PATTERN_LINK.findall(html):
        href = href.strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        assoluto = urljoin(url_base, href)
        if host_di(assoluto) != host_sito:
            continue
        testo_pulito = PATTERN_TAG.sub("", testo).lower()
        etichetta = (href + " " + testo_pulito).lower()
        if any(parola in etichetta for parola in PAROLE_CONTATTO):
            return assoluto
    return None


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


def main():
    parser = argparse.ArgumentParser(description="Campione di misura: email dai siti prospect (senza Firecrawl)")
    parser.add_argument("--campione", type=int, default=20)
    parser.add_argument("--seme", type=int, default=None,
                         help="fissa il campione per poterlo ripetere identico")
    args = parser.parse_args()

    conn = db_connect()
    try:
        with conn.cursor() as cur:
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
    finally:
        conn.close()

    fallimenti_per_motivo = {}
    righe = []
    con_email = 0
    senza_email = 0
    errori = 0

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

    intestazione = f"{'nome':<30} {'sito':<35} {'email trovate':<45} {'scelta':<30} {'esito'}"
    print(intestazione)
    print("-" * len(intestazione))
    for nome, sito, email_join, scelta, esito in righe:
        print(f"{nome[:30]:<30} {sito[:35]:<35} {email_join[:45]:<45} {scelta[:30]:<30} {esito}")

    stima_totale = None
    provati = len(campione)
    if provati:
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

    return 0


if __name__ == "__main__":
    sys.exit(main())
