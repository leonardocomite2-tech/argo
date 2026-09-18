"""Test del ramo gratuito del gateway (connectors/llm.py + connectors/openrouter.py,
18/9/2026). Zero rete e zero DB: urllib finto, contatori finti (nessun test
tocca llm_chiamate_giorno né openrouter_chiamate_giorno veri). Stile CASI.
tests/test_tetto_llm.py resta la rete del ramo Anthropic ed è invariato.
Lancio: python3 tests/test_openrouter_llm.py
"""
import io
import json
import logging
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.llm as llm  # noqa: E402
import connectors.psql_host as psql_host  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


CHIAVE_FINTA = "sk-or-v1-chiave-finta-di-test-0123456789"
os.environ["LLM_TETTO_GIORNALIERO"] = "100"
os.environ["ANTHROPIC_API_KEY"] = "chiave-anthropic-finta"
os.environ["OPENROUTER_API_KEY"] = CHIAVE_FINTA
os.environ.pop("OPENROUTER_TETTO_GIORNALIERO", None)

quote = {"anthropic": 0, "openrouter": 0, "or_rotto": False}


def _inc_anthropic(g):
    quote["anthropic"] += 1
    return quote["anthropic"]


def _inc_openrouter(g):
    if quote["or_rotto"]:
        raise RuntimeError("psql fallito")
    quote["openrouter"] += 1
    return quote["openrouter"]


psql_host.incrementa_chiamate_llm = _inc_anthropic
psql_host.incrementa_chiamate_openrouter = _inc_openrouter
llm.notifica = lambda testo, token=None: None
llm.time.sleep = lambda s: None

log = io.StringIO()
logging.getLogger("argo.llm").addHandler(logging.StreamHandler(log))
logging.getLogger("argo.llm").setLevel(logging.INFO)

http = {"richieste": [], "coda": []}


class _Risposta:
    def __init__(self, corpo):
        self._c = json.dumps(corpo).encode()

    def read(self):
        return self._c

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _anthropic_ok(testo="da anthropic"):
    return _Risposta({"content": [{"type": "text", "text": testo}], "usage": {}, "stop_reason": "end_turn"})


def _openrouter_ok(testo="da openrouter", finish="stop"):
    return _Risposta({"provider": "FornitoreZDR", "choices": [{"message": {"content": testo}, "finish_reason": finish}],
                      "usage": {"prompt_tokens": 3, "completion_tokens": 2}})


def _http_errore(url, codice, headers=None, corpo=b"errore"):
    return urllib.error.HTTPError(url, codice, "x", headers or {}, io.BytesIO(corpo))


def _urlopen(req, timeout=None):
    http["richieste"].append({"url": req.full_url, "corpo": json.loads(req.data), "headers": dict(req.header_items())})
    esito = http["coda"].pop(0)
    if isinstance(esito, Exception):
        raise esito
    return esito


urllib.request.urlopen = _urlopen


def reset(*coda):
    quote.update({"anthropic": 0, "openrouter": 0, "or_rotto": False})
    http["richieste"].clear()
    http["coda"][:] = list(coda)
    log.seek(0)
    log.truncate()
    llm._contatore_in_memoria["attivo"] = False
    llm._contatore_persistente["incrementa"] = None
    llm._contatore["chiamate"] = 0
    os.environ["OPENROUTER_API_KEY"] = CHIAVE_FINTA
    os.environ.pop("OPENROUTER_TETTO_GIORNALIERO", None)


def urls():
    return ["anthropic" if "anthropic.com" in r["url"] else "openrouter" for r in http["richieste"]]


def solleva(f):
    try:
        f()
        return None
    except Exception as e:
        return e


# 1. Default: chi non dice niente va ad Anthropic, anche con OpenRouter configurato
reset(_anthropic_ok())
sys.modules.pop("connectors.openrouter", None)
caso("default: risposta da Anthropic", "da anthropic", llm.chiama("s", "p"))
caso("default: nessuna richiesta a OpenRouter con la chiave configurata", ["anthropic"], urls())
caso("default: il modulo OpenRouter non viene nemmeno importato", False, "connectors.openrouter" in sys.modules)
caso("default: quota gratuita intatta", 0, quote["openrouter"])
for valore in (True, 0, None, "False", "no"):
    reset(_anthropic_ok())
    llm.chiama("s", "p", sensibile=valore)
    caso(f"sensibile={valore!r} (non il False letterale) -> Anthropic", ["anthropic"], urls())

e = solleva(lambda: llm.chiama("s", "p", modello="qualche/modello:free"))
caso("modello senza sensibile=False -> errore, mai un provider diverso", "ValueError", type(e).__name__)

# 2. sensibile=False: modello obbligatorio, vincolo di data policy sempre presente
reset()
e = solleva(lambda: llm.chiama("s", "p", sensibile=False))
caso("sensibile=False senza modello -> ValueError", "ValueError", type(e).__name__)
caso("sensibile=False senza modello: nessuna richiesta, nessuna quota", ([], 0), (list(http["richieste"]), quote["openrouter"]))

reset(_openrouter_ok())
caso("sensibile=False + modello -> OpenRouter", "da openrouter", llm.chiama("s", "p", sensibile=False, modello="prova/modello:free"))
r = http["richieste"][0]
caso("richiesta all'endpoint OpenRouter", "https://openrouter.ai/api/v1/chat/completions", r["url"])
caso("modello del chiamante passato com'è", "prova/modello:free", r["corpo"]["model"])
caso("vincolo di data policy su ogni richiesta", {"data_collection": "deny", "zdr": True}, r["corpo"]["provider"])
caso("quota gratuita +1", 1, quote["openrouter"])
caso("spesa Anthropic non toccata", 0, quote["anthropic"])
caso("in-memory del worker non toccato", 0, llm._contatore["chiamate"])
caso("log con provider=openrouter", True, "provider=openrouter modello=prova/modello:free" in log.getvalue())
caso("la chiave non compare nei log", False, CHIAVE_FINTA in log.getvalue())

# 3. Quota consumata anche quando la richiesta fallisce (incremento PRIMA)
url_or = "https://openrouter.ai/api/v1/chat/completions"
reset(_http_errore(url_or, 500, corpo=CHIAVE_FINTA.encode()))
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("errore 500: la quota gratuita sale lo stesso", 1, quote["openrouter"])
caso("errore 500: un solo tentativo (ogni tentativo brucia quota)", 1, len(http["richieste"]))
caso("errore 500 senza fallback: l'errore risale", "ErroreOpenRouter", type(e).__name__)
caso("la chiave non compare nel messaggio d'errore", False, CHIAVE_FINTA in str(e))
caso("la chiave non compare nei log dopo l'errore", False, CHIAVE_FINTA in log.getvalue())

reset(_http_errore(url_or, 429, headers={"Retry-After": "7"}))
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("429: retry_after dal server riportato al chiamante", 7, getattr(e, "retry_after", None))
caso("429: nessun nuovo tentativo automatico", 1, len(http["richieste"]))
caso("429: quota gratuita consumata", 1, quote["openrouter"])
caso("429 senza fallback: nessuna chiamata ad Anthropic", 0, quote["anthropic"])

# 4. fallback=True: su errore passa ad Anthropic e lo logga
reset(_http_errore(url_or, 429, headers={"Retry-After": "3"}), _anthropic_ok("ripiego"))
caso("fallback=True su 429 -> Anthropic", "ripiego", llm.chiama("s", "p", sensibile=False, modello="m:free", fallback=True))
caso("fallback: prima OpenRouter, poi Anthropic", ["openrouter", "anthropic"], urls())
caso("fallback: il cambio di provider è loggato", True, "cambio provider openrouter -> anthropic" in log.getvalue())
caso("fallback: una quota per parte, non sommate", (1, 1), (quote["openrouter"], quote["anthropic"]))

# 5. Tetto della quota gratuita
reset(_openrouter_ok(), _openrouter_ok())
os.environ["OPENROUTER_TETTO_GIORNALIERO"] = "2"
llm.chiama("s", "p", sensibile=False, modello="m:free")
llm.chiama("s", "p", sensibile=False, modello="m:free")
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("oltre OPENROUTER_TETTO_GIORNALIERO -> bloccata", "TettoOpenRouterRaggiunto", type(e).__name__)
caso("oltre il tetto: nessuna richiesta partita", 2, len(http["richieste"]))
caso("il tetto gratuito non è il tetto Anthropic", False, isinstance(e, llm.TettoLLMRaggiunto))
os.environ.pop("OPENROUTER_TETTO_GIORNALIERO")
import connectors.openrouter as openrouter  # noqa: E402
caso("tetto di default 40", 40, openrouter.TETTO_DEFAULT)

# 6. Contatore gratuito illeggibile -> bloccata, mai al buio
reset()
quote["or_rotto"] = True
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("contatore gratuito illeggibile -> errore", "ErroreOpenRouter", type(e).__name__)
caso("contatore gratuito illeggibile -> nessuna richiesta", 0, len(http["richieste"]))

# 7. Chiave opzionale: se manca il gateway funziona come oggi
reset(_anthropic_ok())
del os.environ["OPENROUTER_API_KEY"]
caso("senza chiave: il ramo Anthropic funziona come sempre", "da anthropic", llm.chiama("s", "p"))
reset()
del os.environ["OPENROUTER_API_KEY"]
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("senza chiave, sensibile=False: errore chiaro", True, "OPENROUTER_API_KEY non configurata" in str(e))
caso("senza chiave: nessuna quota consumata, nessuna richiesta", (0, 0), (quote["openrouter"], len(http["richieste"])))
reset(_anthropic_ok("ripiego"))
del os.environ["OPENROUTER_API_KEY"]
caso("senza chiave, fallback=True -> Anthropic", "ripiego", llm.chiama("s", "p", sensibile=False, modello="m:free", fallback=True))

# 8. Errore nel corpo di una risposta 200 (OpenRouter lo fa) e troncamento
reset(_Risposta({"error": {"code": 404, "message": "No endpoints found matching your data policy"}}))
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("errore nel corpo di una 200 -> ErroreOpenRouter col messaggio", True, "data policy" in str(e))
reset(_openrouter_ok("mezza", finish="length"))
caso("finish_reason=length -> marcatore se richiesto", "mezza\n[TRONC]",
     llm.chiama("s", "p", sensibile=False, modello="m:free", marcatore_se_troncato="[TRONC]"))

reset(_openrouter_ok("", finish="length"))
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free", max_tokens=20))
caso("testo vuoto per max_tokens esauriti -> errore esplicito, mai '' silenzioso", True, "max_tokens=20" in str(e))

reset(_http_errore(url_or, 400, corpo=b'{"error":{"message":"modello non valido","code":400},"user_id":"user_XYZ"}'))
e = solleva(lambda: llm.chiama("s", "p", sensibile=False, modello="m:free"))
caso("errore: solo error.message, niente user_id dell'account", (True, False), ("modello non valido" in str(e), "user_XYZ" in str(e)))

# 9. Worker: sceglie l'in-memory per Anthropic; il ramo gratuito resta separato
reset(_anthropic_ok())
llm.usa_contatore_in_memoria()
llm.chiama("s", "p")
caso("worker: chiamata di default sull'in-memory, zero persistente, zero gratuita",
     (1, 0, 0), (llm._contatore["chiamate"], quote["anthropic"], quote["openrouter"]))

# 10. Classificatore e drafter non passano i parametri nuovi: restano su Anthropic
for modulo in ("brain/classifier.py", "brain/drafter.py", "argo/voce.py", "scripts/memoria/hook_sessione.py"):
    sorgente = (REPO_ROOT / modulo).read_text(encoding="utf-8")
    caso(f"{modulo}: nessun sensibile=False", False, "sensibile=False" in sorgente)


def main():
    falliti = 0
    for descrizione, atteso, ottenuto in CASI:
        if ottenuto != atteso:
            falliti += 1
            print(f"FALLITO: {descrizione} — atteso {atteso!r}, ottenuto {ottenuto!r}")
    print(f"{len(CASI) - falliti}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
