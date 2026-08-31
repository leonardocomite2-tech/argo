import logging
import socket
import urllib.error
import urllib.request

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
