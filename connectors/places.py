import json
import logging
import os
import time
import urllib.error
import urllib.request
from pathlib import Path

logger = logging.getLogger("argo.places")

API_URL = "https://places.googleapis.com/v1/places:searchText"
REPO_ROOT = Path(__file__).resolve().parent.parent

FIELD_MASK = (
    "places.id,places.displayName,places.formattedAddress,places.location,"
    "places.types,places.primaryType,places.nationalPhoneNumber,"
    "places.internationalPhoneNumber,places.websiteUri,places.businessStatus,"
    "places.rating,places.userRatingCount,places.googleMapsUri,nextPageToken"
)
# ATTENZIONE: allargare questa maschera cambia lo SKU fatturato dalla Places
# API (New) Text Search — non aggiungere campi senza aver riverificato la
# tabella prezzi ufficiale.

MAX_TENTATIVI = 3
ATTESA_BASE_SEC = 1  # backoff: 1s dopo il 1° fallimento, 2s dopo il 2°


class PlacesErrore(Exception):
    """Errore non recuperabile: 4xx (escluso 429) o tentativi di retry esauriti."""


def carica_env():
    """Legge PLACES_API_KEY da /root/argo/.env se non già in os.environ.
    Stesso pattern di _carica_env in backup/invia_backup.py: lo script che usa
    questo client gira a mano fuori Docker, dove .env non è auto-caricato."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for riga in env_path.read_text().splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, _, valore = riga.partition("=")
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "'\"":
            valore = valore[1:-1]
        os.environ.setdefault(chiave.strip(), valore)


def _corpo_richiesta(query, rettangolo, tipo, page_token, page_size):
    corpo = {"textQuery": query, "pageSize": page_size}
    if rettangolo is not None:
        corpo["locationRestriction"] = {"rectangle": {
            "low": {"latitude": rettangolo["low"]["lat"], "longitude": rettangolo["low"]["lng"]},
            "high": {"latitude": rettangolo["high"]["lat"], "longitude": rettangolo["high"]["lng"]},
        }}
    if tipo is not None:
        corpo["includedType"] = tipo
    if page_token is not None:
        corpo["pageToken"] = page_token
    return corpo


def cerca_testo(query, rettangolo=None, tipo=None, page_token=None, page_size=20):
    """POST a places:searchText. Ritenta (fino a MAX_TENTATIVI, attesa
    crescente) SOLO su 5xx, 429 o errori di rete/timeout — gli unici casi in
    cui riprovare può cambiare l'esito. Un 4xx diverso da 429 si alza subito.
    Solleva PlacesErrore se tutti i tentativi falliscono."""
    api_key = os.environ["PLACES_API_KEY"]
    corpo = _corpo_richiesta(query, rettangolo, tipo, page_token, page_size)
    data = json.dumps(corpo).encode("utf-8")

    ultimo_errore = None
    for tentativo in range(1, MAX_TENTATIVI + 1):
        req = urllib.request.Request(
            API_URL, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": FIELD_MASK,
                "User-Agent": "Argo/1.0",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                grezzo = resp.read()
        except urllib.error.HTTPError as e:
            corpo_errore = e.read().decode("utf-8", errors="replace").replace(api_key, "***")
            if e.code == 429 or e.code >= 500:
                ultimo_errore = f"status={e.code} body={corpo_errore}"
                logger.warning("cerca_testo: tentativo %d/%d fallito (status=%s), riprovo",
                                tentativo, MAX_TENTATIVI, e.code)
            else:
                logger.error("cerca_testo: errore non recuperabile, status=%s body=%s", e.code, corpo_errore)
                raise PlacesErrore(f"cerca_testo fallita: status={e.code} body={corpo_errore}") from None
        except Exception as e:
            messaggio = str(e).replace(api_key, "***")
            ultimo_errore = f"{type(e).__name__}: {messaggio}"
            logger.warning("cerca_testo: tentativo %d/%d fallito (%s), riprovo",
                            tentativo, MAX_TENTATIVI, type(e).__name__)
        else:
            try:
                return json.loads(grezzo)
            except Exception as e:
                # 2xx ma corpo non JSON valido: non è un problema di rete,
                # ritentare non aiuta — errore immediato, non consuma tentativi.
                raise PlacesErrore(f"cerca_testo: risposta non JSON valida ({type(e).__name__}: {e})") from None

        if tentativo < MAX_TENTATIVI:
            time.sleep(ATTESA_BASE_SEC * (2 ** (tentativo - 1)))

    raise PlacesErrore(f"cerca_testo fallita dopo {MAX_TENTATIVI} tentativi: {ultimo_errore}") from None
