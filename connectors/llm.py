import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from connectors.telegram import notifica

logger = logging.getLogger("argo.llm")

API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
MODEL = "claude-haiku-4-5-20251001"
REPO_ROOT = Path(__file__).resolve().parent.parent
FUSO_ROMA = ZoneInfo("Europe/Rome")

MAX_TENTATIVI = 3
ATTESA_BASE_SEC = 1  # backoff: 1s dopo il 1° fallimento, 2s dopo il 2°


class LLMErrore(Exception):
    """Errore non recuperabile: 4xx (diverso da 5xx/rete) o tentativi esauriti."""


class TettoLLMRaggiunto(LLMErrore):
    """Tetto giornaliero di chiamate superato. Già notificato su Telegram
    da questo modulo — chi la intercetta non deve notificare di nuovo."""


def carica_env():
    """Legge ANTHROPIC_API_KEY da /root/argo/.env se non già in os.environ.
    Stesso pattern di places.carica_env(): serve per far girare
    tests/eval_classificatore.py fuori Docker, dove .env non è auto-caricato."""
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


_contatore = {"giorno": None, "chiamate": 0}


def _verifica_tetto():
    """Incrementa il contatore giornaliero (in-memory, azzerato ad ogni
    riavvio del worker — trade-off documentato in STATO.md) e solleva
    TettoLLMRaggiunto PRIMA di qualunque chiamata HTTP se il tetto è
    superato, notificando una sola volta per giorno."""
    oggi = datetime.now(FUSO_ROMA).date()
    if _contatore["giorno"] != oggi:
        _contatore["giorno"] = oggi
        _contatore["chiamate"] = 0

    _contatore["chiamate"] += 1
    tetto = int(os.environ["LLM_TETTO_GIORNALIERO"])

    if _contatore["chiamate"] > tetto:
        if _contatore["chiamate"] == tetto + 1:
            # Notifica una volta sola al superamento, non ad ogni chiamata
            # successiva bloccata nello stesso giorno.
            notifica(
                f"🛑 Tetto giornaliero di chiamate LLM raggiunto ({tetto}/giorno) — "
                "classificazione e bozze sospese fino a domani, verificare il volume."
            )
        logger.warning(
            "chiama: tetto giornaliero superato (%d/%d), chiamata bloccata",
            _contatore["chiamate"], tetto,
        )
        raise TettoLLMRaggiunto(f"tetto giornaliero di {tetto} chiamate superato")


def estrai_json(testo):
    """Rimuove eventuali fence markdown (```json ... ```) attorno al JSON
    prima del parsing — capita anche con istruzioni esplicite di non farlo."""
    testo = testo.strip()
    if testo.startswith("```"):
        testo = testo.split("\n", 1)[1] if "\n" in testo else ""
        if testo.endswith("```"):
            testo = testo[:-3]
        elif "```" in testo:
            testo = testo.rsplit("```", 1)[0]
    return testo.strip()


def _corpo_richiesta(system, prompt, max_tokens, temperature):
    return {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "system": system,
        "messages": [{"role": "user", "content": prompt}],
    }


def chiama(system, prompt, max_tokens=500, temperature=0.0):
    """POST a /v1/messages. Ritenta (fino a MAX_TENTATIVI) SOLO su 5xx o
    errori di rete/timeout — mai su 429 o altri 4xx (richiesta esplicita:
    diverso da connectors/places.py). Logga sempre token in ingresso, in
    uscita e latenza ad ogni chiamata riuscita. Solleva TettoLLMRaggiunto se
    il tetto giornaliero è superato, LLMErrore per ogni altro fallimento
    non recuperabile."""
    _verifica_tetto()

    api_key = os.environ["ANTHROPIC_API_KEY"]
    corpo = _corpo_richiesta(system, prompt, max_tokens, temperature)
    data = json.dumps(corpo).encode("utf-8")

    ultimo_errore = None
    for tentativo in range(1, MAX_TENTATIVI + 1):
        req = urllib.request.Request(
            API_URL, data=data, method="POST",
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": ANTHROPIC_VERSION,
                "User-Agent": "Argo/1.0",
            },
        )
        inizio = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                grezzo = resp.read()
        except urllib.error.HTTPError as e:
            corpo_errore = e.read().decode("utf-8", errors="replace").replace(api_key, "***")
            if e.code >= 500:
                ultimo_errore = f"status={e.code} body={corpo_errore}"
                logger.warning("chiama: tentativo %d/%d fallito (status=%s), riprovo",
                                tentativo, MAX_TENTATIVI, e.code)
            else:
                logger.error("chiama: errore non recuperabile, status=%s body=%s", e.code, corpo_errore)
                raise LLMErrore(f"chiama fallita: status={e.code} body={corpo_errore}") from None
        except Exception as e:
            messaggio = str(e).replace(api_key, "***")
            ultimo_errore = f"{type(e).__name__}: {messaggio}"
            logger.warning("chiama: tentativo %d/%d fallito (%s), riprovo",
                            tentativo, MAX_TENTATIVI, type(e).__name__)
        else:
            latenza_ms = int((time.monotonic() - inizio) * 1000)
            try:
                risposta = json.loads(grezzo)
            except Exception as e:
                raise LLMErrore(f"chiama: risposta non JSON valida ({type(e).__name__}: {e})") from None

            uso = risposta.get("usage") or {}
            logger.info(
                "chiama: modello=%s input_tokens=%s output_tokens=%s latenza_ms=%d",
                MODEL, uso.get("input_tokens"), uso.get("output_tokens"), latenza_ms,
            )

            testo = "".join(
                blocco.get("text", "") for blocco in risposta.get("content", [])
                if blocco.get("type") == "text"
            )
            return testo

        if tentativo < MAX_TENTATIVI:
            time.sleep(ATTESA_BASE_SEC * (2 ** (tentativo - 1)))

    raise LLMErrore(f"chiama fallita dopo {MAX_TENTATIVI} tentativi: {ultimo_errore}") from None
