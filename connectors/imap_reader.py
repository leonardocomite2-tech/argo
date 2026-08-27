import email
import imaplib
import logging
import os
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime
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


WARMUP_TAG = os.environ.get("WARMUP_TAG", "").strip()
if not WARMUP_TAG:
    logger.info("imap_reader: WARMUP_TAG non impostata, filtro warmup disattivo")


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

            risultati.append({
                "message_id": msg.get("Message-ID"),
                "mittente": _decodifica_header(msg.get("From")),
                "destinatario": user,
                "oggetto": _decodifica_header(msg.get("Subject")),
                "testo": _estrai_testo(msg),
                "data": _parsa_data(msg.get("Date")),
                "in_reply_to": msg.get("In-Reply-To"),
                "references": msg.get("References"),
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

    if not WARMUP_TAG:
        return tutti

    risultato = []
    scartati = 0
    for m in tutti:
        oggetto = m.get("oggetto") or ""
        if WARMUP_TAG.lower() in oggetto.lower():
            scartati += 1
        else:
            risultato.append(m)
    logger.info("leggi_nuove: %d messaggi scartati come warmup", scartati)
    return risultato
