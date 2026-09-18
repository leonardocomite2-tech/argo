"""Ramo gratuito del gateway LLM: OpenRouter (API compatibile OpenAI).

Raggiunto SOLO da connectors/llm.py:chiama(..., sensibile=False, modello=...)
e importato solo in quel caso: chi non lo usa (classificatore, drafter, Argo,
hook memoria, worker) non carica mai questo modulo né legge le sue env.
Serve a girare eval e prove di prompt senza pensare alla spesa, non a
risparmiare in produzione. Mai dati di terzi: contratto CD07 della mappa.

Tre garanzie, tutte qui dentro e non configurabili dal chiamante:
- VINCOLO_DATA_POLICY su OGNI richiesta: solo provider che non raccolgono i
  dati e solo endpoint a zero retention. Sintassi dalla documentazione
  ufficiale (openrouter.ai/docs/features/provider-routing e /features/zdr,
  18/9/2026): `data_collection: "deny"` = "use only providers which do not
  collect user data" (il default "allow" include chi "may train on it");
  `zdr: true` = "only routed to endpoints that have a Zero Data Retention
  policy". Nel codice e non solo nell'impostazione di account: una casella
  si può spuntare al contrario, il codice no (il campo per richiesta vale in
  OR con quella di account).
- Quota gratuita contata PRIMA della richiesta, in una tabella sua
  (openrouter_chiamate_giorno): le richieste fallite consumano la quota di
  OpenRouter, quindi contano anche qui. Tetto OPENROUTER_TETTO_GIORNALIERO
  (default 40: il limite vero è 50/giorno senza crediti). Separata dalla
  spesa Anthropic (llm_chiamate_giorno) e dall'in-memory del worker: tre
  quote, mai sommate.
- Un solo tentativo per chiamata: ogni tentativo brucia quota. Su 429
  l'errore porta `retry_after` (header Retry-After) e il chiamante non
  riprova prima; il ripiego su Anthropic, se voluto, lo decide
  connectors/llm.py:chiama(fallback=True).

La chiave OPENROUTER_API_KEY è opzionale: se manca, questo ramo rifiuta la
chiamata prima di contarla e il resto del gateway non se ne accorge.
"""
import json
import logging
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

from connectors.llm import FUSO_ROMA, LLMErrore, _applica_marcatore_troncamento

logger = logging.getLogger("argo.llm")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
TETTO_DEFAULT = 40
TIMEOUT_SEC = 60
VINCOLO_DATA_POLICY = {"data_collection": "deny", "zdr": True}


class ErroreOpenRouter(LLMErrore):
    """Chiamata OpenRouter fallita o rifiutata. `retry_after` (secondi) è
    valorizzato su 429 se il server lo indica."""

    def __init__(self, messaggio, retry_after=None):
        super().__init__(messaggio)
        self.retry_after = retry_after


class TettoOpenRouterRaggiunto(ErroreOpenRouter):
    """Quota gratuita del giorno esaurita (OPENROUTER_TETTO_GIORNALIERO).
    Distinta da connectors/llm.py:TettoLLMRaggiunto, che è la spesa
    Anthropic: chi intercetta quella non deve confonderle."""


_contatore = {"incrementa": None}


def _incrementa_default(giorno):
    from connectors.psql_host import incrementa_chiamate_openrouter
    return incrementa_chiamate_openrouter(giorno)


def corpo_richiesta(system, prompt, modello, max_tokens, temperature):
    """Pura. Il vincolo di data policy c'è sempre: non è un parametro."""
    return {
        "model": modello,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "provider": dict(VINCOLO_DATA_POLICY),
    }


def _retry_after(headers):
    try:
        valore = (headers or {}).get("Retry-After")
        return int(float(valore)) if valore is not None else None
    except (TypeError, ValueError):
        return None


def _messaggio_errore(grezzo):
    """Dal corpo d'errore di OpenRouter tiene solo error.message: il corpo
    completo porta anche lo user_id dell'account, che non serve a nessuno."""
    try:
        errore = json.loads(grezzo).get("error") or {}
        if isinstance(errore, dict) and errore.get("message"):
            return f"{errore['message']} (code={errore.get('code')})"
    except (ValueError, AttributeError):
        pass
    return grezzo


def _verifica_quota():
    """Incrementa la quota gratuita del giorno PRIMA della richiesta e
    rifiuta oltre il tetto. Contatore illeggibile -> bloccata, come per
    Anthropic: mai una richiesta senza sapere a che punto è la quota."""
    oggi = datetime.now(FUSO_ROMA).date()
    incrementa = _contatore["incrementa"] or _incrementa_default
    try:
        chiamate = int(incrementa(oggi))
    except Exception as e:
        logger.error("openrouter: contatore della quota non leggibile (%s), chiamata bloccata", type(e).__name__)
        raise ErroreOpenRouter(f"contatore della quota gratuita non leggibile ({type(e).__name__})") from None
    tetto = int(os.environ.get("OPENROUTER_TETTO_GIORNALIERO") or TETTO_DEFAULT)
    if chiamate > tetto:
        logger.warning("openrouter: quota gratuita del giorno superata (%d/%d), chiamata bloccata", chiamate, tetto)
        raise TettoOpenRouterRaggiunto(f"quota gratuita di {tetto} chiamate/giorno superata")
    return chiamate, tetto


def chiama(system, prompt, modello, max_tokens=500, temperature=0.0, marcatore_se_troncato=None):
    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        # Prima del contatore: nessuna richiesta partirà, niente da contare.
        raise ErroreOpenRouter("OPENROUTER_API_KEY non configurata: ramo gratuito non disponibile")

    chiamate, tetto = _verifica_quota()

    data = json.dumps(corpo_richiesta(system, prompt, modello, max_tokens, temperature)).encode("utf-8")
    req = urllib.request.Request(
        API_URL, data=data, method="POST",
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "X-Title": "Argo",
            "User-Agent": "Argo/1.0",
        },
    )
    inizio = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SEC) as resp:
            grezzo = resp.read()
    except urllib.error.HTTPError as e:
        corpo = _messaggio_errore(e.read().decode("utf-8", errors="replace")).replace(api_key, "***")[:300]
        retry_after = _retry_after(e.headers) if e.code == 429 else None
        logger.error("chiama: provider=openrouter modello=%s status=%s retry_after=%s quota=%d/%d",
                     modello, e.code, retry_after, chiamate, tetto)
        raise ErroreOpenRouter(f"openrouter status={e.code} body={corpo}", retry_after=retry_after) from None
    except Exception as e:
        logger.error("chiama: provider=openrouter modello=%s errore di rete (%s) quota=%d/%d",
                     modello, type(e).__name__, chiamate, tetto)
        raise ErroreOpenRouter(f"openrouter non raggiunto ({type(e).__name__})") from None

    latenza_ms = int((time.monotonic() - inizio) * 1000)
    try:
        risposta = json.loads(grezzo)
    except Exception as e:
        raise ErroreOpenRouter(f"openrouter: risposta non JSON valida ({type(e).__name__})") from None
    if risposta.get("error"):
        errore = risposta["error"] if isinstance(risposta["error"], dict) else {"message": str(risposta["error"])}
        logger.error("chiama: provider=openrouter modello=%s errore nel corpo (code=%s) quota=%d/%d",
                     modello, errore.get("code"), chiamate, tetto)
        raise ErroreOpenRouter(f"openrouter errore: {str(errore.get('message'))[:300]}")

    scelta = (risposta.get("choices") or [{}])[0]
    testo = ((scelta.get("message") or {}).get("content")) or ""
    uso = risposta.get("usage") or {}
    logger.info(
        "chiama: provider=openrouter modello=%s fornitore=%s input_tokens=%s output_tokens=%s latenza_ms=%d quota=%d/%d",
        modello, risposta.get("provider"), uso.get("prompt_tokens"), uso.get("completion_tokens"),
        latenza_ms, chiamate, tetto,
    )
    stop = "max_tokens" if scelta.get("finish_reason") == "length" else scelta.get("finish_reason")
    if not testo.strip() and stop == "max_tokens":
        # Modelli che ragionano prima di rispondere: con max_tokens basso il
        # ragionamento consuma tutto e il testo arriva vuoto (prova reale del
        # 18/9, 20 token). Mai un '' silenzioso: in un eval sembrerebbe una
        # risposta vera.
        raise ErroreOpenRouter(f"risposta vuota: max_tokens={max_tokens} esauriti prima del testo (alzarlo)")
    return _applica_marcatore_troncamento(testo, stop, marcatore_se_troncato)
