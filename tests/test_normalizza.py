"""python3 tests/test_normalizza.py"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.normalizza import (  # noqa: E402
    dominio, telefono_e164, nome_chiave, indirizzo_chiave,
    DOMINIO_MAX_STRUTTURE_CONDIVISE,
)

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- dominio() ---
caso("www e slash finale", ("hotelroma.it", True), dominio("https://www.hotelroma.it/"))
caso("maiuscole", ("hotelroma.it", True), dominio("HTTPS://WWW.HotelRoma.IT"))
caso("query e frammento", ("hotelroma.it", True), dominio("https://hotelroma.it/pagina?ref=fb#top"))
caso("porta e path", ("hotelroma.it", True), dominio("https://hotelroma.it:8080/it/camere"))
caso("booking.com", (None, False), dominio("https://www.booking.com/hotel/it/xyz.html"))
caso("sottodominio booking.com", (None, False), dominio("https://secure.booking.com/reservation"))
caso("airbnb", (None, False), dominio("https://www.airbnb.it/rooms/12345"))
caso("facebook", (None, False), dominio("https://www.facebook.com/hotelroma"))
caso("instagram", (None, False), dominio("https://www.instagram.com/hotelroma"))
caso("tripadvisor", (None, False), dominio("https://www.tripadvisor.it/Hotel_Review-xyz"))
caso("link maps google.com", (None, False), dominio("https://www.google.com/maps/place/Hotel"))
caso("link maps goo.gl", (None, False), dominio("https://goo.gl/maps/abc123"))
caso("sottodominio wixsite.com", ("miostruttura.wixsite.com", True), dominio("https://miostruttura.wixsite.com"))
caso("sites.google.com con path", ("sites.google.com/view", True), dominio("https://sites.google.com/view/bebroma/home"))
caso("sites.google.com senza path (host nudo, nessuna identità)", (None, False), dominio("https://sites.google.com/"))
caso("stringa vuota", (None, False), dominio(""))
caso("None", (None, False), dominio(None))
caso("stringa senza punto", (None, False), dominio("nonèunurl"))
caso("mailto", (None, False), dominio("mailto:info@hotelroma.it"))
caso("tel", (None, False), dominio("tel:+390658333413"))

# Soglia di condivisione (30/08): una blocklist statica di aggregatori non
# basta da sola — i booking engine/OTA nuovi spuntano di continuo (nel primo
# batch reale su Roma ne sono emersi 8 mai visti prima: krossbooking,
# spacest, vio, freecancellations, snaptrip, bluepillow, voyabay, trip.com,
# scoperti solo perché centinaia di strutture diverse ci finivano incollate
# sopra come fosse un solo "gestore"). Un dominio condiviso da troppe
# strutture nello stesso batch non è il sito di nessuno in particolare,
# anche se non è (ancora) in AGGREGATORI — per questo dominio() accetta un
# conteggio_domini opzionale e applica la soglia lì, non nella blocklist.
caso(
    "dominio condiviso sopra soglia diventa piattaforma",
    (None, False),
    dominio(
        "https://www.bookingenginesconosciuto.com/struttura-1",
        conteggio_domini={"bookingenginesconosciuto.com": DOMINIO_MAX_STRUTTURE_CONDIVISE + 1},
    ),
)
caso(
    "dominio condiviso esattamente alla soglia resta sito proprio",
    ("bookingenginesconosciuto.com", True),
    dominio(
        "https://www.bookingenginesconosciuto.com/struttura-1",
        conteggio_domini={"bookingenginesconosciuto.com": DOMINIO_MAX_STRUTTURE_CONDIVISE},
    ),
)
caso(
    "senza conteggio_domini la soglia non si applica",
    ("bookingenginesconosciuto.com", True),
    dominio("https://www.bookingenginesconosciuto.com/struttura-1"),
)

# --- telefono_e164() ---
caso("internazionale con spazi (Germania)", "+4930123456", telefono_e164("+49 30 123456"))
caso("fisso italiano con zero", "+390658333413", telefono_e164("06 5833 3413"))
caso("separatori misti", "+390658333413", telefono_e164("06.5833-3413"))
caso("cellulare italiano", "+393331234567", telefono_e164("333 1234567"))
caso("prefisso 00", "+390658333413", telefono_e164("0039 06 5833 3413"))
caso("parentesi", "+390658333413", telefono_e164("(06) 5833-3413"))
caso("estero non italiano (UK)", "+442079460958", telefono_e164("+44 20 7946 0958"))
caso("primo valore utile tra più argomenti", "+393331234567", telefono_e164(None, "", "333 1234567"))
caso("due numeri separati da virgola", "+390658333413", telefono_e164("06 5833 3413, 06 5833 3420"))
caso("due numeri separati da slash", "+390658333413", telefono_e164("06 5833 3413/3420"))
caso("testo senza cifre", None, telefono_e164("chiamare in reception"))
caso("numero troppo corto", None, telefono_e164("123"))
caso("tutti gli argomenti vuoti", None, telefono_e164(None, "", "   "))

# --- nome_chiave() ---
caso("nome con articolo", "giardino", nome_chiave("Il Giardino"))
caso("nome con &", "bb roma vaticano", nome_chiave("B&B Roma & Vaticano"))
caso("nome con accenti", "citta eterna", nome_chiave("Città Eterna"))
caso("forma societaria puntata", "rossi", nome_chiave("Rossi S.r.l."))

# --- indirizzo_chiave() ---
caso("civico dopo virgola", ("Via dei Fori Imperiali", "34"), indirizzo_chiave("Via dei Fori Imperiali, 34, 00186 Roma"))
caso("civico attaccato alla via", ("Via dei Fori Imperiali", "34"), indirizzo_chiave("Via dei Fori Imperiali 34, Roma"))
caso("civico con lettera", ("Via dei Fori Imperiali", "34A"), indirizzo_chiave("Via dei Fori Imperiali, 34/A, Roma"))
caso("P.zza abbreviata", ("Piazza Navona", "1"), indirizzo_chiave("P.zza Navona, 1"))
caso("V.le abbreviata", ("Viale Trastevere", "45"), indirizzo_chiave("V.le Trastevere, 45"))
caso("C.so abbreviata", ("Corso Vittorio Emanuele II", None), indirizzo_chiave("C.so Vittorio Emanuele II, Roma"))
caso("V. abbreviata", ("Via Nazionale", "10"), indirizzo_chiave("V. Nazionale, 10"))
caso("indirizzo senza civico", ("Via dei Fori Imperiali", None), indirizzo_chiave("Via dei Fori Imperiali, Roma"))
caso("indirizzo vuoto", (None, None), indirizzo_chiave(""))
caso("indirizzo None", (None, None), indirizzo_chiave(None))


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
