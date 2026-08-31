"""Cantiere lead-gen (outreach social, 1/09): trova il profilo Instagram e/o
la pagina Facebook di ogni prospect, da due fonti a costo zero:
  1. contatti con sito_proprio falso il cui `sito` grezzo è già un link
     Facebook/Instagram (parsing diretto, nessuna rete)
  2. contatti con sito_proprio vero: home + eventuale pagina contatti
     scaricate con connectors/fetch.py, link social trovati negli <a href>
  docker compose exec worker python -m scripts.estrai_social \
      [--campione N] [--seme S] [--tutti --offset M]

Scrive sempre (nessun flag --scrivi): attributi.instagram/facebook sono
dati derivati sovrascrivibili, non un valore storico da proteggere come
l'email — ma solo quando questo run trova qualcosa, per non cancellare un
valore buono di un run precedente se un fetch fallisce per un motivo
transitorio.
"""
import argparse
import json
import os
import sys

from connectors.fetch import scarica, con_schema, host_di, estrai_link, trova_link_contatti
from connectors.normalizza import normalizza_instagram, normalizza_facebook

import psycopg


def db_connect():
    return psycopg.connect(
        host="db", dbname="argo", user="argo",
        password=os.environ["PG_PASSWORD"],
    )


def social_da_link(url):
    """(instagram, facebook) da un singolo URL già noto — usato sia per la
    fonte 1 (sito grezzo) sia per ogni link trovato negli href della fonte
    2. Al massimo uno dei due è valorizzato, mai entrambi."""
    host = host_di(url)
    if host == "instagram.com" or host.endswith(".instagram.com"):
        return normalizza_instagram(url), None
    if host == "facebook.com" or host.endswith(".facebook.com"):
        return None, normalizza_facebook(url)
    return None, None


def social_da_pagina(html, url_base):
    """Primo profilo Instagram e prima pagina Facebook trovati negli <a
    href> di una pagina già scaricata."""
    instagram = facebook = None
    for url, _testo in estrai_link(html, url_base):
        if instagram and facebook:
            break
        ig, fb = social_da_link(url)
        instagram = instagram or ig
        facebook = facebook or fb
    return instagram, facebook


def elabora_contatto(sito, sito_proprio):
    """Ritorna (instagram, facebook, esito). esito è "diretto" (fonte 1,
    nessuna rete), "ok"/"errore:<motivo>" (fonte 2, dopo il fetch), o
    "nessun social" se sito_proprio falso ma non è un link fb/ig."""
    url = con_schema(sito)

    if not sito_proprio:
        instagram, facebook = social_da_link(url)
        if instagram or facebook:
            return instagram, facebook, "diretto"
        return None, None, "nessun social"

    host_sito = host_di(url)
    testo_home, motivo = scarica(url)
    if testo_home is None:
        return None, None, f"errore:{motivo}"

    instagram, facebook = social_da_pagina(testo_home, url)

    if not (instagram and facebook):
        link_contatti = trova_link_contatti(testo_home, url, host_sito)
        if link_contatti:
            testo_contatti, _ = scarica(link_contatti)
            if testo_contatti is not None:
                ig2, fb2 = social_da_pagina(testo_contatti, link_contatti)
                instagram = instagram or ig2
                facebook = facebook or fb2

    return instagram, facebook, "ok"


def salva_social_contatto(cur, contact_id, instagram, facebook):
    """Scrive solo le chiavi trovate — non tocca quella mancante, per non
    cancellare un valore buono di un run precedente."""
    if instagram:
        cur.execute(
            "UPDATE contacts SET attributi = jsonb_set(COALESCE(attributi, '{}'::jsonb), '{instagram}', %s::jsonb) WHERE id = %s",
            (json.dumps(instagram), contact_id),
        )
    if facebook:
        cur.execute(
            "UPDATE contacts SET attributi = jsonb_set(COALESCE(attributi, '{}'::jsonb), '{facebook}', %s::jsonb) WHERE id = %s",
            (json.dumps(facebook), contact_id),
        )


def stampa_totali(cur):
    cur.execute(
        """
        SELECT
          COUNT(*) FILTER (WHERE attributi->>'instagram' IS NOT NULL AND attributi->>'instagram' <> ''),
          COUNT(*) FILTER (WHERE attributi->>'facebook' IS NOT NULL AND attributi->>'facebook' <> ''),
          COUNT(*) FILTER (WHERE (attributi->>'instagram' IS NOT NULL AND attributi->>'instagram' <> '')
                               OR (attributi->>'facebook' IS NOT NULL AND attributi->>'facebook' <> '')),
          COUNT(*) FILTER (WHERE ((attributi->>'instagram' IS NOT NULL AND attributi->>'instagram' <> '')
                                OR (attributi->>'facebook' IS NOT NULL AND attributi->>'facebook' <> ''))
                             AND (email IS NULL OR email = '')
                             AND (telefono IS NULL OR telefono = ''))
        FROM contacts WHERE stato = 'prospect'
        """
    )
    con_ig, con_fb, con_almeno_uno, solo_social = cur.fetchone()
    print("\nTotali cumulativi sui prospect (non solo questo lotto):")
    print(f"  con Instagram: {con_ig}")
    print(f"  con Facebook: {con_fb}")
    print(f"  con almeno uno dei due: {con_almeno_uno}")
    print(f"  di questi, senza email né telefono (raggiungibili solo via social): {solo_social}")


def stampa_social_frequenti(cur, top=15):
    """Un account di default lasciato dal page builder (wix, wordpress, ...)
    si riconosce perché compare su decine di siti scollegati tra loro —
    stessa logica di stampa_domini_email_frequenti in estrai_email.py."""
    cur.execute(
        """
        SELECT attributi->>'instagram', COUNT(*) FROM contacts
        WHERE attributi->>'instagram' IS NOT NULL AND attributi->>'instagram' <> ''
        GROUP BY 1 ORDER BY 2 DESC LIMIT %s
        """,
        (top,),
    )
    ig_righe = cur.fetchall()
    cur.execute(
        """
        SELECT attributi->>'facebook', COUNT(*) FROM contacts
        WHERE attributi->>'facebook' IS NOT NULL AND attributi->>'facebook' <> ''
        GROUP BY 1 ORDER BY 2 DESC LIMIT %s
        """,
        (top,),
    )
    fb_righe = cur.fetchall()
    print(f"\nHandle Instagram più frequenti (top {top}):")
    for handle, n in ig_righe:
        print(f"  {n:3d}  {handle}")
    print(f"\nPagine Facebook più frequenti (top {top}):")
    for pagina, n in fb_righe:
        print(f"  {n:3d}  {pagina}")


def main():
    parser = argparse.ArgumentParser(description="Link social (Instagram/Facebook) dai siti prospect")
    parser.add_argument("--campione", type=int, default=20,
                         help="quante righe processa questa invocazione (campione casuale, o dimensione lotto con --tutti)")
    parser.add_argument("--seme", type=int, default=None,
                         help="fissa il campione casuale per poterlo ripetere identico (ignorato con --tutti)")
    parser.add_argument("--tutti", action="store_true",
                         help="selezione paginata per id invece che casuale, per coprire tutti i prospect a lotti")
    parser.add_argument("--offset", type=int, default=0, help="usato solo con --tutti")
    args = parser.parse_args()

    conn = db_connect()
    try:
        with conn.cursor() as cur:
            if args.tutti:
                cur.execute(
                    """
                    SELECT id, nome, sito, attributi->>'sito_proprio' FROM contacts
                    WHERE stato = 'prospect' AND sito IS NOT NULL AND sito <> ''
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
                    SELECT id, nome, sito, attributi->>'sito_proprio' FROM contacts
                    WHERE stato = 'prospect' AND sito IS NOT NULL AND sito <> ''
                    ORDER BY random()
                    LIMIT %s
                    """,
                    (args.campione,),
                )
            campione = cur.fetchall()

            righe = []
            con_ig = con_fb = errori = 0

            for contact_id, nome, sito, sito_proprio_raw in campione:
                sito_proprio = sito_proprio_raw == "true"
                instagram, facebook, esito = elabora_contatto(sito, sito_proprio)

                if esito.startswith("errore"):
                    errori += 1
                if instagram:
                    con_ig += 1
                if facebook:
                    con_fb += 1

                righe.append((nome or "", sito or "", instagram or "", facebook or "", esito))

                if instagram or facebook:
                    salva_social_contatto(cur, contact_id, instagram, facebook)
                    conn.commit()

            intestazione = f"{'nome':<30} {'sito':<35} {'instagram':<20} {'facebook':<40} {'esito'}"
            print(intestazione)
            print("-" * len(intestazione))
            for nome, sito, instagram, facebook, esito in righe:
                print(f"{nome[:30]:<30} {sito[:35]:<35} {instagram[:20]:<20} {facebook[:40]:<40} {esito}")

            print()
            print(f"Contatti processati: {len(campione)}")
            print(f"Con Instagram trovato in questo lotto: {con_ig}")
            print(f"Con Facebook trovato in questo lotto: {con_fb}")
            print(f"Errori di rete (fonte 2): {errori}")

            stampa_totali(cur)
            stampa_social_frequenti(cur)
    finally:
        conn.close()

    return 0


if __name__ == "__main__":
    sys.exit(main())
