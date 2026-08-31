import logging
import re
import socket
import urllib.error
import urllib.request
from urllib.parse import urljoin, urlsplit

logger = logging.getLogger("argo.fetch")

TIMEOUT_SEC = 10


def scarica(url, timeout=TIMEOUT_SEC):
    """GET con User-Agent Argo/1.0, un solo tentativo, segue i redirect
    (comportamento di default di urllib). Ritorna (testo, None) se riesce,
    (None, motivo) se fallisce — motivo in "timeout", "dns", "403", "404",
    "500", "altro". Nessun retry: qui l'obiettivo è misurare il tasso di
    fallimento reale dei siti prospect, non nasconderlo."""
    req = urllib.request.Request(url, headers={"User-Agent": "Argo/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            corpo = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return corpo.decode(charset, errors="replace"), None
    except urllib.error.HTTPError as e:
        codice = str(e.code)
        motivo = codice if codice in {"403", "404", "500"} else "altro"
        logger.info("scarica: %s -> %s", url, motivo)
        return None, motivo
    except urllib.error.URLError as e:
        if isinstance(e.reason, socket.timeout):
            motivo = "timeout"
        elif isinstance(e.reason, socket.gaierror):
            motivo = "dns"
        else:
            motivo = "altro"
        logger.info("scarica: %s -> %s (%s)", url, motivo, e.reason)
        return None, motivo
    except socket.timeout:
        logger.info("scarica: %s -> timeout", url)
        return None, "timeout"
    except Exception as e:
        # Livello warning apposta: qui possono finire anche bug di
        # programmazione, non solo fallimenti di rete — non vanno persi
        # in mezzo agli "altro" senza lasciare traccia.
        logger.warning("scarica: %s -> altro (%s: %s)", url, type(e).__name__, e)
        return None, "altro"


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


PATTERN_LINK = re.compile(r'<a\b[^>]*href=["\']([^"\']+)["\'][^>]*>(.*?)</a>', re.IGNORECASE | re.DOTALL)
PATTERN_TAG = re.compile(r"<[^>]+>")
PAROLE_CONTATTO = ("contatt", "contact", "prenot", "booking", "reserv", "chi-siamo", "about")


def estrai_link(html, url_base):
    """Tutti gli <a href> di una pagina già scaricata, come (url_assoluto,
    testo_pulito) — i relativi risolti rispetto a url_base. Scarta
    mailto:/tel:/javascript:/#, che non sono mai una pagina da seguire."""
    trovati = []
    for href, testo in PATTERN_LINK.findall(html):
        href = href.strip()
        if not href or href.startswith(("mailto:", "tel:", "javascript:", "#")):
            continue
        assoluto = urljoin(url_base, href)
        testo_pulito = PATTERN_TAG.sub("", testo).lower()
        trovati.append((assoluto, testo_pulito))
    return trovati


def trova_link_contatti(html, url_base, host_sito):
    """Primo link interno (stesso host) il cui href o testo somiglia a una
    pagina contatti. None se non ne trova uno."""
    for url, testo in estrai_link(html, url_base):
        if host_di(url) != host_sito:
            continue
        etichetta = (url + " " + testo).lower()
        if any(parola in etichetta for parola in PAROLE_CONTATTO):
            return url
    return None
