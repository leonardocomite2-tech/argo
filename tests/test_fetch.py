"""python3 tests/test_fetch.py"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.fetch import con_schema, host_di, estrai_link, trova_link_contatti  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- con_schema() ---
caso("aggiunge https se manca lo schema", "https://hotelroma.it", con_schema("hotelroma.it"))
caso("non tocca http esistente", "http://hotelroma.it", con_schema("http://hotelroma.it"))
caso("non tocca https esistente", "https://hotelroma.it", con_schema("https://hotelroma.it"))
caso("spazi ai bordi rimossi", "https://hotelroma.it", con_schema("  hotelroma.it  "))

# --- host_di() ---
caso("www rimosso", "hotelroma.it", host_di("https://www.hotelroma.it/it/camere"))
caso("maiuscole normalizzate", "hotelroma.it", host_di("https://WWW.HotelRoma.IT/"))
caso("porta rimossa", "hotelroma.it", host_di("https://hotelroma.it:8080/it"))
caso("sottodominio diverso da www non toccato", "m.facebook.com", host_di("https://m.facebook.com/hotelroma"))

# --- estrai_link() ---
HTML_SEMPLICE = """
<html><body>
<a href="/it/camere">Camere</a>
<a href="https://www.instagram.com/hotelroma/">Seguici su Instagram</a>
<a href="mailto:info@hotelroma.it">Scrivici</a>
<a href="tel:+390612345">Chiamaci</a>
<a href="#top">Su</a>
<a href="javascript:void(0)">Apri menu</a>
</body></html>
"""
caso(
    "risolve i relativi, scarta mailto/tel/javascript/#",
    [
        ("https://www.hotelroma.it/it/camere", "camere"),
        ("https://www.instagram.com/hotelroma/", "seguici su instagram"),
    ],
    estrai_link(HTML_SEMPLICE, "https://www.hotelroma.it/"),
)

# --- trova_link_contatti() ---
HTML_CON_CONTATTI = """
<html><body>
<a href="/it/camere">Camere</a>
<a href="/it/contatti">Contatti</a>
<a href="https://www.booking.com/hotel/it/xyz.html">Prenota su Booking</a>
</body></html>
"""
caso(
    "trova il link interno alla pagina contatti",
    "https://www.hotelroma.it/it/contatti",
    trova_link_contatti(HTML_CON_CONTATTI, "https://www.hotelroma.it/", "hotelroma.it"),
)
caso(
    "ignora link a un host diverso anche se contiene parole chiave",
    None,
    trova_link_contatti(
        '<a href="https://altrositoconcontatti.it/contact">Contact</a>',
        "https://www.hotelroma.it/", "hotelroma.it",
    ),
)
caso("nessun link contatti trovato", None, trova_link_contatti(
    '<a href="/camere">Camere</a>', "https://www.hotelroma.it/", "hotelroma.it",
))


def main():
    falliti = 0
    for descrizione, atteso, ottenuto in CASI:
        if ottenuto != atteso:
            falliti += 1
            print(f"FALLITO: {descrizione} — atteso {atteso!r}, ottenuto {ottenuto!r}")
    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
