import email
import imaplib
import logging
import os
from email.header import decode_header, make_header
from email.utils import parseaddr, parsedate_to_datetime
from html.parser import HTMLParser

from connectors.telegram import notifica

logger = logging.getLogger("argo.imap")


class _HTMLTextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self._parti = []
        self._salta = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._salta += 1

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._salta > 0:
            self._salta -= 1

    def handle_data(self, data):
        if not self._salta:
            self._parti.append(data)

    def testo(self):
        return " ".join(" ".join(self._parti).split())


def _html_a_testo(html):
    estrattore = _HTMLTextExtractor()
    estrattore.feed(html)
    return estrattore.testo()


def _decodifica_header(valore):
    if not valore:
        return valore
    try:
        return str(make_header(decode_header(valore)))
    except Exception:
        return valore


def _estrai_testo(msg):
    html_fallback = None
    if msg.is_multipart():
        for parte in msg.walk():
            content_type = parte.get_content_type()
            if parte.get_content_disposition() == "attachment":
                continue
            if content_type == "text/plain":
                charset = parte.get_content_charset() or "utf-8"
                return parte.get_payload(decode=True).decode(charset, errors="replace")
            if content_type == "text/html" and html_fallback is None:
                charset = parte.get_content_charset() or "utf-8"
                html_fallback = parte.get_payload(decode=True).decode(charset, errors="replace")
    else:
        content_type = msg.get_content_type()
        charset = msg.get_content_charset() or "utf-8"
        corpo = msg.get_payload(decode=True).decode(charset, errors="replace")
        if content_type == "text/plain":
            return corpo
        if content_type == "text/html":
            html_fallback = corpo

    if html_fallback is not None:
        return _html_a_testo(html_fallback)
    return ""


def _parsa_data(valore):
    if not valore:
        return valore
    try:
        return parsedate_to_datetime(valore).isoformat()
    except Exception:
        logger.warning("imap_reader: header Date non parsabile: %r", valore)
        return valore


def _parse_warmup_tags(valore):
    return [t.strip() for t in (valore or "").split(",") if t.strip()]


WARMUP_TAGS = _parse_warmup_tags(os.environ.get("WARMUP_TAG", ""))
if not WARMUP_TAGS:
    logger.info("imap_reader: WARMUP_TAG non impostata, filtro warmup disattivo")


def _contiene_tag_warmup(msg, tags):
    if not tags:
        return False
    grezzo = msg.as_string().lower()
    return any(tag.lower() in grezzo for tag in tags)


def _e_rimbalzo(msg):
    mittente = (msg.get("From") or "").lower()
    if "mailer-daemon" in mittente or "postmaster@" in mittente:
        return True
    if msg.get_content_type() == "multipart/report":
        report_type = (msg.get_param("report-type", header="Content-Type") or "").lower()
        if report_type == "delivery-status":
            return True
    return False


def _estrai_dettagli_rimbalzo(msg):
    for parte in msg.walk():
        if parte.get_content_type() != "message/delivery-status":
            continue
        payload = parte.get_payload()
        if isinstance(payload, list) and payload:
            blocco = payload[0]
        else:
            testo = parte.get_payload(decode=True)
            if isinstance(testo, bytes):
                testo = testo.decode("utf-8", errors="replace")
            blocco = email.message_from_string(testo or "")
        indirizzo = blocco.get("Final-Recipient") or blocco.get("Original-Recipient")
        if indirizzo and ";" in indirizzo:
            indirizzo = indirizzo.split(";", 1)[1].strip()
        status = blocco.get("Status")
        return indirizzo, status
    return None, None


def _e_automatica(msg):
    auto_submitted = (msg.get("Auto-Submitted") or "no").strip().lower()
    if auto_submitted not in ("", "no"):
        return True
    precedence = (msg.get("Precedence") or "").strip().lower()
    if precedence in ("bulk", "auto_reply"):
        return True
    _, indirizzo = parseaddr(msg.get("From") or "")
    indirizzo = (indirizzo or "").lower()
    dominio = indirizzo.split("@")[-1] if "@" in indirizzo else ""
    if _e_dominio_google(dominio):
        # I domini Google hanno un controllo dedicato più sotto (_e_google_admin):
        # qui li escludiamo per non far scattare sempre "automatica" per primo.
        return False
    return indirizzo.startswith(("no-reply@", "noreply@", "donotreply@"))


def _e_dominio_google(dominio):
    return (
        dominio in ("google.com", "googlemail.com")
        or dominio.endswith(".google.com")
        or dominio.endswith(".googlemail.com")
    )


def _e_google_admin(msg):
    _, indirizzo = parseaddr(msg.get("From") or "")
    indirizzo = (indirizzo or "").lower()
    if "@" not in indirizzo:
        return False
    locale, dominio = indirizzo.split("@", 1)
    if not _e_dominio_google(dominio):
        return False
    return locale.startswith("no-reply") or locale.startswith("noreply")


def classifica_messaggio(msg, warmup_tags):
    if _contiene_tag_warmup(msg, warmup_tags):
        return {"motivo": "warmup"}

    if _e_rimbalzo(msg):
        indirizzo, status = _estrai_dettagli_rimbalzo(msg)
        definitivo = bool(status) and status.strip().startswith("5.")
        return {
            "motivo": "bounce_definitivo" if definitivo else "bounce_temporaneo",
            "indirizzo_fallito": indirizzo,
            "codice_rimbalzo": status,
        }

    if _e_automatica(msg):
        return {"motivo": "automatica"}

    if _e_google_admin(msg):
        return {"motivo": "google_admin"}

    return {"motivo": None}


def _mailboxes():
    n = 1
    while True:
        user = os.environ.get(f"MAILBOX_{n}_USER")
        password = os.environ.get(f"MAILBOX_{n}_PASS")
        if not user or not password:
            break
        yield user, password
        n += 1


def _leggi_casella(user, password):
    host = os.environ["IMAP_HOST"]
    port = int(os.environ.get("IMAP_PORT", 993))
    risultati = []

    with imaplib.IMAP4_SSL(host, port) as imap:
        imap.login(user, password)
        imap.select("INBOX", readonly=True)
        typ, data = imap.search(None, "UNSEEN")
        if typ != "OK":
            raise imaplib.IMAP4.error(f"search fallita: {typ}")

        for num in data[0].split():
            typ, msg_data = imap.fetch(num, "(BODY.PEEK[])")
            if typ != "OK" or not msg_data or msg_data[0] is None:
                logger.warning("imap_reader: fetch fallita per uid %s in %s", num, user)
                continue

            raw = msg_data[0][1]
            msg = email.message_from_bytes(raw)
            classificazione = classifica_messaggio(msg, WARMUP_TAGS)

            risultati.append({
                "message_id": msg.get("Message-ID"),
                "mittente": _decodifica_header(msg.get("From")),
                "destinatario": user,
                "oggetto": _decodifica_header(msg.get("Subject")),
                "testo": _estrai_testo(msg),
                "data": _parsa_data(msg.get("Date")),
                "in_reply_to": msg.get("In-Reply-To"),
                "references": msg.get("References"),
                "motivo_scarto": classificazione["motivo"],
                "indirizzo_fallito": classificazione.get("indirizzo_fallito"),
                "codice_rimbalzo": classificazione.get("codice_rimbalzo"),
            })

    return risultati


def leggi_nuove():
    tutti = []
    for user, password in _mailboxes():
        try:
            tutti.extend(_leggi_casella(user, password))
        except Exception as e:
            logger.exception("leggi_nuove: casella %s non raggiungibile", user)
            notifica(
                f"ALERT: casella IMAP {user} non raggiungibile (errore={type(e).__name__})"
            )

    return tutti
