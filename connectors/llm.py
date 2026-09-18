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
_contatore_persistente = {"incrementa": None, "cosa_si_ferma": None}
_contatore_in_memoria = {"attivo": False}

# Testo della notifica di superamento per il contatore in-memory (worker
# Docker: classificazione e bozze) — invariato.
COSA_SI_FERMA_DEFAULT = "classificazione e bozze sospese"
# Testo per il contatore persistente di default, quando il chiamante non ne
# ha dato uno suo (script lanciati a mano, eval, qualunque processo nuovo).
COSA_SI_FERMA_PERSISTENTE_DEFAULT = "chiamate LLM dei processi host sospese"


def _incrementa_default(giorno):
    """Contatore persistente di default: llm_chiamate_giorno via docker exec
    psql (connectors/psql_host.py). Import tardivo: chi usa il contatore
    in-memory (il worker Docker) non lo carica mai."""
    from connectors.psql_host import incrementa_chiamate_llm
    return incrementa_chiamate_llm(giorno)


def usa_contatore_persistente(incrementa, cosa_si_ferma):
    """Contatore persistente con una funzione e un testo di notifica propri.
    Dal 18/9/2026 il persistente è già il DEFAULT per qualunque chiamante
    (vedi _incrementa_contatore): questa funzione serve solo a personalizzare
    il testo della notifica o a iniettare un contatore finto nei test.
    `incrementa(giorno)` deve incrementare in modo atomico il conteggio di
    `giorno` (date, fuso Europe/Rome) e ritornare il valore dopo
    l'incremento. `incrementa=None` torna al contatore persistente di
    default (llm_chiamate_giorno), non a quello in-memory."""
    _contatore_persistente["incrementa"] = incrementa
    _contatore_persistente["cosa_si_ferma"] = cosa_si_ferma
    _contatore_in_memoria["attivo"] = False


def usa_contatore_in_memoria():
    """Scelta ESPLICITA del contatore in-memory per questo processo: la fa
    solo il worker Docker (worker/loop.py, a livello di modulo), che non ha
    il comando docker per raggiungere llm_chiamate_giorno e che usava già
    questo contatore — comportamento invariato, trade-off in STATO.md
    (azzerato a ogni riavvio del worker). Chiunque altro è coperto dal
    contatore persistente senza dover fare niente: uno script nuovo non
    deve sapere di doverlo agganciare."""
    _contatore_in_memoria["attivo"] = True


def _incrementa_contatore(oggi):
    """Ritorna il conteggio di oggi dopo l'incremento. Persistente per
    default; in-memory solo dopo usa_contatore_in_memoria(). Se il contatore
    persistente non è leggibile solleva LLMErrore: si chiude, non si chiama
    l'API senza sapere a che punto è il tetto."""
    if _contatore_in_memoria["attivo"]:
        if _contatore["giorno"] != oggi:
            _contatore["giorno"] = oggi
            _contatore["chiamate"] = 0
        _contatore["chiamate"] += 1
        return _contatore["chiamate"]

    incrementa = _contatore_persistente["incrementa"] or _incrementa_default
    try:
        return int(incrementa(oggi))
    except Exception as e:
        logger.error("chiama: contatore persistente non leggibile (%s), chiamata bloccata", type(e).__name__)
        raise LLMErrore(f"contatore del tetto non leggibile ({type(e).__name__})") from None


def _testo_cosa_si_ferma():
    if _contatore_in_memoria["attivo"]:
        return COSA_SI_FERMA_DEFAULT
    return _contatore_persistente["cosa_si_ferma"] or COSA_SI_FERMA_PERSISTENTE_DEFAULT


def _verifica_tetto():
    """Incrementa il contatore giornaliero e solleva TettoLLMRaggiunto PRIMA
    di qualunque chiamata HTTP se il tetto è superato, notificando una sola
    volta per giorno. Contatore persistente (llm_chiamate_giorno) per
    default; in-memory solo se il processo ha chiamato
    usa_contatore_in_memoria() (il worker Docker)."""
    oggi = datetime.now(FUSO_ROMA).date()
    chiamate = _incrementa_contatore(oggi)
    tetto = int(os.environ["LLM_TETTO_GIORNALIERO"])

    if chiamate > tetto:
        if chiamate == tetto + 1:
            # Notifica una volta sola al superamento, non ad ogni chiamata
            # successiva bloccata nello stesso giorno.
            cosa_si_ferma = _testo_cosa_si_ferma()
            notifica(
                f"🛑 Tetto giornaliero di chiamate LLM raggiunto ({tetto}/giorno) — "
                f"{cosa_si_ferma} fino a domani, verificare il volume."
            )
        logger.warning(
            "chiama: tetto giornaliero superato (%d/%d), chiamata bloccata",
            chiamate, tetto,
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


def _applica_marcatore_troncamento(testo, stop_reason, marcatore):
    """Pura: se `marcatore` è valorizzato e la risposta si è fermata per
    max_tokens, lo accoda al testo — mai un taglio silenzioso, stesso
    principio già usato per decisioni_aperte_bloccano (argo/voce.py:_tronca).
    Con marcatore=None (default di chiama()) il comportamento è invariato:
    nessun chiamante esistente (orienta/instrada/avvisa/brief/classificatore/
    drafter) viene toccato da questa aggiunta."""
    if marcatore and stop_reason == "max_tokens":
        return f"{testo}\n{marcatore}"
    return testo


def _chiama_anthropic(system, prompt, max_tokens=500, temperature=0.0, marcatore_se_troncato=None):
    """Il ramo Anthropic, identico al chiama() di prima del 18/9/2026 (solo
    rinominato). POST a /v1/messages. Ritenta (fino a MAX_TENTATIVI) SOLO su 5xx o
    errori di rete/timeout — mai su 429 o altri 4xx (richiesta esplicita:
    diverso da connectors/places.py). Logga sempre token in ingresso, in
    uscita e latenza ad ogni chiamata riuscita. Solleva TettoLLMRaggiunto se
    il tetto giornaliero è superato, LLMErrore per ogni altro fallimento
    non recuperabile. `marcatore_se_troncato` è opt-in (vedi
    _applica_marcatore_troncamento): solo chi lo passa esplicitamente vede
    un marcatore accodato quando stop_reason=='max_tokens'."""
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
            return _applica_marcatore_troncamento(testo, risposta.get("stop_reason"), marcatore_se_troncato)

        if tentativo < MAX_TENTATIVI:
            time.sleep(ATTESA_BASE_SEC * (2 ** (tentativo - 1)))

    raise LLMErrore(f"chiama fallita dopo {MAX_TENTATIVI} tentativi: {ultimo_errore}") from None


def chiama(system, prompt, max_tokens=500, temperature=0.0, marcatore_se_troncato=None,
           *, sensibile=True, modello=None, fallback=False):
    """Gateway LLM. Per default (sensibile=True) è esattamente il ramo
    Anthropic di sempre: classificatore, drafter, Argo e hook memoria non
    passano nessuno dei tre parametri nuovi e non cambiano.

    OpenRouter (connectors/openrouter.py, endpoint gratuiti) si raggiunge
    SOLO con `sensibile is False` — il valore False letterale, passato di
    proposito: 0, None, "no" o un parametro dimenticato restano su
    Anthropic (fail closed, contratto CD07) — e con `modello` esplicito:
    nessun modello cablato qui, il listino gratuito ruota. Solo per compiti
    dichiarati non sensibili (eval, prove di prompt, testi senza dati di
    terzi): mai email di prospect, contatti o contenuti ricevuti.

    `fallback=True`: se OpenRouter fallisce (429, tetto gratuito, chiave
    mancante, errore) la chiamata passa ad Anthropic e il cambio è loggato.
    `fallback=False` (default): l'errore risale — un ripiego silenzioso su
    un batch di eval trasformerebbe un esperimento gratuito in una spesa
    che nessuno ha deciso."""
    if sensibile is not False:
        if modello is not None:
            raise ValueError("modello vale solo con sensibile=False: il ramo Anthropic usa MODEL")
        return _chiama_anthropic(system, prompt, max_tokens, temperature, marcatore_se_troncato)

    if not isinstance(modello, str) or not modello.strip():
        raise ValueError("con sensibile=False il modello è obbligatorio (il listino gratuito ruota)")

    from connectors import openrouter

    try:
        return openrouter.chiama(system, prompt, modello.strip(), max_tokens, temperature, marcatore_se_troncato)
    except LLMErrore as e:
        if not fallback:
            raise
        logger.warning(
            "chiama: cambio provider openrouter -> anthropic (fallback=True), motivo: %s",
            type(e).__name__,
        )
        return _chiama_anthropic(system, prompt, max_tokens, temperature, marcatore_se_troncato)

