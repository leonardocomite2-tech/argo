"""python3 tests/test_filtri_email.py"""
import email
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.imap_reader import classifica_messaggio, _parse_warmup_tags  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


def msg_da_testo(testo):
    return email.message_from_string(testo)


WARMUP_TAGS = ["rule-once"]

# --- messaggio normale: nessun filtro ---
NORMALE = """From: Mario Rossi <mario@hotelroma.it>
To: narratours.info@gmail.com
Subject: Info sul depliant
Content-Type: text/plain; charset=utf-8

Buongiorno, vorrei informazioni sul depliant.
"""
caso(
    "email normale passa senza motivo",
    None,
    classifica_messaggio(msg_da_testo(NORMALE), WARMUP_TAGS)["motivo"],
)

# --- warmup nell'oggetto ---
WARMUP_OGGETTO = """From: test@narratours.info
To: qualcuno@landmarkpixel.com
Subject: [rule-once] messaggio di prova
Content-Type: text/plain; charset=utf-8

Contenuto di warmup.
"""
caso(
    "warmup riconosciuto dall'oggetto",
    "warmup",
    classifica_messaggio(msg_da_testo(WARMUP_OGGETTO), WARMUP_TAGS)["motivo"],
)

# --- warmup nel corpo/oggetto del messaggio originale allegato a un rimbalzo vero ---
# Ha anche mittente MAILER-DAEMON e content-type multipart/report: se l'ordine dei
# filtri fosse sbagliato (rimbalzo prima di warmup) questo caso finirebbe come bounce.
RIMBALZO_WARMUP = """From: MAILER-DAEMON@mx.google.com
To: narratours.info@gmail.com
Subject: Delivery Status Notification (Failure)
Content-Type: multipart/report; report-type=delivery-status; boundary="B1"

--B1
Content-Type: text/plain; charset=utf-8

Il messaggio non e' stato recapitato.

--B1
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.google.com
Final-Recipient: rfc822; inesistente@dominio-inesistente.test
Action: failed
Status: 5.1.1
Diagnostic-Code: smtp; 550 5.1.1 User unknown

--B1
Content-Type: message/rfc822

From: narratours.info@gmail.com
To: inesistente@dominio-inesistente.test
Subject: [rule-once] invio di prova warmup
Content-Type: text/plain; charset=utf-8

Messaggio di warmup originale.

--B1--
"""
caso(
    "rimbalzo di un warmup: vince warmup, non bounce",
    "warmup",
    classifica_messaggio(msg_da_testo(RIMBALZO_WARMUP), WARMUP_TAGS)["motivo"],
)

# --- rimbalzo definitivo (5.x.x) ---
RIMBALZO_DEFINITIVO = """From: MAILER-DAEMON@mx.google.com
To: narratours.info@gmail.com
Subject: Delivery Status Notification (Failure)
Content-Type: multipart/report; report-type=delivery-status; boundary="B2"

--B2
Content-Type: text/plain; charset=utf-8

Il messaggio non e' stato recapitato.

--B2
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.google.com
Final-Recipient: rfc822; bounced@dominio-inesistente.test
Action: failed
Status: 5.1.1

--B2--
"""
_ris_def = classifica_messaggio(msg_da_testo(RIMBALZO_DEFINITIVO), WARMUP_TAGS)
caso("rimbalzo definitivo: motivo", "bounce_definitivo", _ris_def["motivo"])
caso("rimbalzo definitivo: indirizzo estratto", "bounced@dominio-inesistente.test", _ris_def["indirizzo_fallito"])
caso("rimbalzo definitivo: codice", "5.1.1", _ris_def["codice_rimbalzo"])

# --- rimbalzo temporaneo (4.x.x) ---
RIMBALZO_TEMPORANEO = """From: mailer-daemon@mx.google.com
To: narratours.info@gmail.com
Subject: Delivery Status Notification (Delay)
Content-Type: multipart/report; report-type=delivery-status; boundary="B3"

--B3
Content-Type: text/plain; charset=utf-8

Consegna ritardata.

--B3
Content-Type: message/delivery-status

Reporting-MTA: dns; mx.google.com
Final-Recipient: rfc822; casella-piena@hotelroma.it
Action: delayed
Status: 4.2.2

--B3--
"""
_ris_temp = classifica_messaggio(msg_da_testo(RIMBALZO_TEMPORANEO), WARMUP_TAGS)
caso("rimbalzo temporaneo: motivo", "bounce_temporaneo", _ris_temp["motivo"])
caso("rimbalzo temporaneo: indirizzo estratto", "casella-piena@hotelroma.it", _ris_temp["indirizzo_fallito"])

# --- automatiche ---
AUTO_SUBMITTED = """From: assenza@hotelroma.it
To: narratours.info@gmail.com
Subject: Fuori sede
Auto-Submitted: auto-replied
Content-Type: text/plain; charset=utf-8

Sono fuori sede.
"""
caso(
    "automatica: header Auto-Submitted",
    "automatica",
    classifica_messaggio(msg_da_testo(AUTO_SUBMITTED), WARMUP_TAGS)["motivo"],
)

PRECEDENCE_BULK = """From: newsletter@qualcosa.it
To: narratours.info@gmail.com
Subject: Newsletter
Precedence: bulk
Content-Type: text/plain; charset=utf-8

Contenuto.
"""
caso(
    "automatica: Precedence bulk",
    "automatica",
    classifica_messaggio(msg_da_testo(PRECEDENCE_BULK), WARMUP_TAGS)["motivo"],
)

NOREPLY_GENERICO = """From: no-reply@bookingsystem.it
To: narratours.info@gmail.com
Subject: Conferma prenotazione
Content-Type: text/plain; charset=utf-8

Prenotazione confermata.
"""
caso(
    "automatica: mittente no-reply@ generico",
    "automatica",
    classifica_messaggio(msg_da_testo(NOREPLY_GENERICO), WARMUP_TAGS)["motivo"],
)

# --- amministrazione Google: solo mittente, oggetto ininfluente ---
# Oggetti reali forniti dall'utente dai log — compresi due che non sono affatto
# avvisi di sicurezza, a riprova che il filtro guarda solo il mittente.
GOOGLE_ADMIN_CASI = [
    ("no-reply@google.com", "Google Admin Alert: Bulk upload report for landmarkpixel.com"),
    ("no-reply@accounts.google.com", "Security alert"),
    ("no-reply@google.com", "2-Step Verification turned on"),
    ("noreply@google.com", "Get the official Gmail app"),
    ("no-reply@googlemail.com", "Tips for using your new inbox"),
]
for _mittente, _oggetto in GOOGLE_ADMIN_CASI:
    _raw = (
        f"From: Google <{_mittente}>\n"
        f"To: narratours.info@gmail.com\n"
        f"Subject: {_oggetto}\n"
        "Content-Type: text/plain; charset=utf-8\n\n"
        "Contenuto amministrativo.\n"
    )
    caso(
        f"google_admin: {_mittente} / {_oggetto!r}",
        "google_admin",
        classifica_messaggio(msg_da_testo(_raw), WARMUP_TAGS)["motivo"],
    )

# --- Google admin non deve finire in "automatica" (verifica dell'esclusione dominio) ---
caso(
    "google_admin non finisce mai in automatica",
    "google_admin",
    classifica_messaggio(
        msg_da_testo(
            "From: no-reply@google.com\nTo: x@y.it\nSubject: Security alert\n"
            "Content-Type: text/plain; charset=utf-8\n\nx\n"
        ),
        WARMUP_TAGS,
    )["motivo"],
)

# --- _parse_warmup_tags() ---
caso("_parse_warmup_tags: valore singolo", ["rule-once"], _parse_warmup_tags("rule-once"))
caso(
    "_parse_warmup_tags: valori multipli con spazi",
    ["rule-once", "batch-2"],
    _parse_warmup_tags(" rule-once , batch-2 "),
)
caso("_parse_warmup_tags: valori vuoti scartati", ["x"], _parse_warmup_tags(",, x ,,"))
caso("_parse_warmup_tags: stringa vuota", [], _parse_warmup_tags(""))
caso("_parse_warmup_tags: None", [], _parse_warmup_tags(None))


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
