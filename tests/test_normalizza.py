"""python3 tests/test_normalizza.py"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.normalizza import (  # noqa: E402
    dominio, telefono_e164, nome_chiave, indirizzo_chiave,
    DOMINIO_MAX_STRUTTURE_CONDIVISE, estrai_email, preferenza_email,
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


# --- estrai_email() ---
caso("email semplice nel testo", ["info@hotelroma.it"], estrai_email("Scrivici a info@hotelroma.it per prenotare"))
caso("maiuscole normalizzate", ["info@hotelroma.it"], estrai_email("INFO@HotelRoma.IT"))
caso("duplicati rimossi", ["info@hotelroma.it"], estrai_email("info@hotelroma.it ... info@hotelroma.it"))
caso("più email distinte, ordine di comparsa", ["info@hotelroma.it", "booking@hotelroma.it"],
     estrai_email("info@hotelroma.it e anche booking@hotelroma.it"))
caso("noreply scartata", [], estrai_email("mittente: noreply@hotelroma.it"))
caso("no-reply scartata", [], estrai_email("no-reply@hotelroma.it"))
caso("postmaster scartata", [], estrai_email("postmaster@hotelroma.it"))
caso("webmaster scartata", [], estrai_email("webmaster@hotelroma.it"))
caso("privacy scartata", [], estrai_email("privacy@hotelroma.it"))
caso("dominio wordpress scartato", [], estrai_email("admin@miosito.wordpress.com"))
caso("dominio sentry scartato (DSN incollato nello script)", [],
     estrai_email("chiave123@o12345.ingest.sentry.io/67890"))
caso("falso positivo retina .png", [], estrai_email("vedi logo@2x.png nell'header"))
caso("falso positivo .jpg", [], estrai_email("sfondo@hero.jpg"))
caso("nessuna email nel testo", [], estrai_email("chiamateci in reception"))
caso("testo vuoto", [], estrai_email(""))
caso("testo None", [], estrai_email(None))

# Placeholder da template/page builder, scoperti nel run reale sui 524 (31/08):
# "example@" e domini demo tipo mail.com/company.co finivano scelti come
# email vera perché non c'era nulla che li distinguesse da un indirizzo reale.
caso("local-part example scartato", [], estrai_email("scrivi a example@sitovero.it"))
caso("dominio mail.com scartato", [], estrai_email("prenota@mail.com"))
caso("dominio company.co scartato", [], estrai_email("info@company.co"))
caso("dominio test.com scartato", [], estrai_email("prova@test.com"))
caso("dominio domain.com scartato", [], estrai_email("contatto@domain.com"))
caso("dominio yourdomain.com scartato (ora via PAROLE_SEGNAPOSTO)", [], estrai_email("info@yourdomain.com"))
caso("gmail.com NON scartato (contiene 'mail.com' come sottostringa)",
     ["mariorossi@gmail.com"], estrai_email("mariorossi@gmail.com"))
caso("hotmail.com NON scartato (contiene 'mail.com' come sottostringa)",
     ["prenota@hotmail.com"], estrai_email("prenota@hotmail.com"))

# Regola generale (1/09): invece di inseguire una lista fissa di domini demo
# scoperti a campione, si scarta chiunque contenga una parola da segnaposto
# — nel dominio O nel local-part, anche come sottostringa di un nome più
# lungo. Scoperto necessario dopo il secondo giro di celle: example.com,
# dominio.com, email.com, esempio.it, mysite.com erano tutti passati
# indenni alla blocklist precedente basata su lista fissa.
caso("dominio example.com scartato", [], estrai_email("your.email@example.com"))
caso("dominio esempio.it scartato", [], estrai_email("contatto@esempio.it"))
caso("dominio mysite.com scartato", [], estrai_email("info@mysite.com"))
caso("dominio dominio.com scartato", [], estrai_email("utente@dominio.com"))
caso("dominio email.com scartato", [], estrai_email("indirizzo@email.com"))
caso("local-part indirizzo scartato", [], estrai_email("indirizzo@hotelroma.it"))
caso("local-part utente scartato", [], estrai_email("utente@hotelroma.it"))
caso("local-part nomeazienda scartato", [], estrai_email("nomeazienda@hotelroma.it"))
caso("parola segnaposto come sottostringa di un dominio più lungo",
     [], estrai_email("info@ilmiosito-esempio.it"))
caso("parola segnaposto come sottostringa di un local-part più lungo",
     [], estrai_email("tuosito.staff@hotelroma.it"))
caso("indirizzo reale con 'utenti' (plurale) NON scartato — non è sottostringa di 'utente'",
     ["utenti@hotelroma.it"], estrai_email("utenti@hotelroma.it"))
caso("amministratore di condominio reale NON scartato — 'dominio' è sottostringa di 'condominio'",
     ["info@condominiorossi.it"], estrai_email("info@condominiorossi.it"))
caso("condominio nel local-part NON scartato",
     ["amministrazione@condominioverdi.it"], estrai_email("amministrazione@condominioverdi.it"))

# --- preferenza_email() ---
# Il dominio del sito viene prima del local-part: un info@ fuori dominio
# (spesso un placeholder da template, tipo info@company.co) non deve battere
# un indirizzo qualunque sul dominio giusto (caso reale, campione 30/08).
caso("info@ sul dominio del sito: il migliore in assoluto", 0, preferenza_email("info@hotelroma.it", "hotelroma.it"))
caso("prenotazioni@ sul dominio del sito", 0, preferenza_email("prenotazioni@hotelroma.it", "hotelroma.it"))
caso("altro indirizzo sul dominio del sito", 1, preferenza_email("amministrazione@hotelroma.it", "hotelroma.it"))
caso("info@ su dominio estraneo NON batte il dominio del sito", 2, preferenza_email("info@company.co", "hotelroma.it"))
caso("booking@ su dominio estraneo", 2, preferenza_email("booking@altrodominio.com", "hotelroma.it"))
caso("dominio diverso, local-part qualunque (gmail)", 3, preferenza_email("mariorossi@gmail.com", "hotelroma.it"))
caso("stesso dominio con www ignorato", 0, preferenza_email("info@www.hotelroma.it", "hotelroma.it"))
caso("dominio del sito batte info@ estraneo nel confronto diretto",
     True,
     preferenza_email("amministrazione@hotelroma.it", "hotelroma.it") < preferenza_email("info@company.co", "hotelroma.it"))


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
