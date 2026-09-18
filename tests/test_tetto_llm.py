"""Test del default del tetto LLM (connectors/llm.py, 18/9/2026): contatore
PERSISTENTE per qualunque chiamante, in-memory solo dove è scelto
esplicitamente (il worker Docker). Un caso per chiamante: script qualsiasi,
worker Docker, classificatore, drafter, Argo (consumer host), hook memoria.
Zero rete e zero DB: HTTP finto su urllib, contatore persistente finto al
posto di connectors/psql_host.incrementa_chiamate_llm (così nessun test
incrementa la tabella vera). Stile CASI.
Lancio: python3 tests/test_tetto_llm.py
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.llm as llm  # noqa: E402
import connectors.psql_host as psql_host  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- ambiente finto ---
os.environ["LLM_TETTO_GIORNALIERO"] = "100"
os.environ.setdefault("ANTHROPIC_API_KEY", "chiave-finta-dei-test")

_persistente = {"chiamate": 0, "rotto": False}


def _incrementa_finto(giorno):
    if _persistente["rotto"]:
        raise RuntimeError("psql fallito")
    _persistente["chiamate"] += 1
    return _persistente["chiamate"]


psql_host.incrementa_chiamate_llm = _incrementa_finto

_notifiche = []
llm.notifica = lambda testo, token=None: _notifiche.append(testo)

_http = {"chiamate": 0, "risposta": "{}"}


class _RispostaFinta:
    def __init__(self, testo):
        self._corpo = json.dumps({
            "content": [{"type": "text", "text": testo}],
            "usage": {"input_tokens": 1, "output_tokens": 1},
            "stop_reason": "end_turn",
        }).encode()

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_finto(req, timeout=None):
    _http["chiamate"] += 1
    return _RispostaFinta(_http["risposta"])


urllib.request.urlopen = _urlopen_finto


def _stato_iniziale():
    """Come un processo appena partito: nessuna scelta fatta."""
    llm._contatore_persistente["incrementa"] = None
    llm._contatore_persistente["cosa_si_ferma"] = None
    llm._contatore_in_memoria["attivo"] = False
    llm._contatore["giorno"] = None
    llm._contatore["chiamate"] = 0
    _persistente["chiamate"] = 0
    _persistente["rotto"] = False
    _http["chiamate"] = 0
    _notifiche.clear()


# 1. Script qualsiasi che chiama il gateway senza dire niente -> persistente
_stato_iniziale()
llm.chiama("s", "p")
llm.chiama("s", "p")
caso("script qualsiasi: ogni chiamata incrementa il contatore persistente", 2, _persistente["chiamate"])
caso("script qualsiasi: il contatore in-memory non viene toccato", 0, llm._contatore["chiamate"])

_stato_iniziale()
_persistente["rotto"] = True
try:
    llm.chiama("s", "p")
    _esito = "partita"
except llm.TettoLLMRaggiunto:
    _esito = "tetto"
except llm.LLMErrore:
    _esito = "bloccata"
caso("script qualsiasi, tabella illeggibile: chiamata bloccata, mai al buio", "bloccata", _esito)
caso("script qualsiasi, tabella illeggibile: nessuna richiesta HTTP partita", 0, _http["chiamate"])

_stato_iniziale()
os.environ["LLM_TETTO_GIORNALIERO"] = "1"
llm.chiama("s", "p")
try:
    llm.chiama("s", "p")
    _esito = "partita"
except llm.TettoLLMRaggiunto:
    _esito = "tetto"
caso("script qualsiasi: il tetto scatta sul contatore persistente", "tetto", _esito)
caso("script qualsiasi: notifica col testo generico dei processi host", True,
     "chiamate LLM dei processi host sospese" in _notifiche[0])
os.environ["LLM_TETTO_GIORNALIERO"] = "100"

# 2. Worker Docker: sceglie esplicitamente l'in-memory, a livello di modulo
_src_worker = (REPO_ROOT / "worker" / "loop.py").read_text(encoding="utf-8")
_righe_modulo = [r for r in _src_worker.splitlines() if not r.startswith((" ", "\t", "#"))]
caso("worker/loop.py chiama usa_contatore_in_memoria() a livello di modulo", True,
     any(r.startswith("usa_contatore_in_memoria()") for r in _righe_modulo))
caso("worker/loop.py: la scelta precede il registro degli handler", True,
     _src_worker.index("usa_contatore_in_memoria()") < _src_worker.index("HANDLERS = {}"))

_stato_iniziale()
llm.usa_contatore_in_memoria()
os.environ["LLM_TETTO_GIORNALIERO"] = "2"
_esiti = []
for _ in range(3):
    try:
        llm.chiama("s", "p")
        _esiti.append("ok")
    except llm.TettoLLMRaggiunto:
        _esiti.append("tetto")
caso("worker (in-memory): stesso comportamento di prima, ok ok tetto", ["ok", "ok", "tetto"], _esiti)
caso("worker (in-memory): il contatore persistente non viene mai toccato", 0, _persistente["chiamate"])
caso("worker (in-memory): notifica col testo di sempre", True, "classificazione e bozze sospese" in _notifiche[0])
os.environ["LLM_TETTO_GIORNALIERO"] = "100"

# 3-4. Classificatore e drafter: girano nel worker -> in-memory, invariati
from brain.classifier import classifica  # noqa: E402
from brain.drafter import redigi_bozza  # noqa: E402

_stato_iniziale()
llm.usa_contatore_in_memoria()
_http["risposta"] = '{"categoria": "domanda", "confidenza": 0.9, "motivo": "chiede orari"}'
caso("classificatore nel worker: risultato invariato", "domanda", classifica("a@b.it", "orari", "a che ora?")["categoria"])
caso("classificatore nel worker: conta sull'in-memory", 1, llm._contatore["chiamate"])
caso("classificatore nel worker: nessun incremento persistente", 0, _persistente["chiamate"])

_http["risposta"] = '{"puo_rispondere": true, "bozza": "Buongiorno, ...", "motivo_se_no": null}'
caso("drafter nel worker: risultato invariato", "Buongiorno, ...", redigi_bozza("a@b.it", "orari", "a che ora?", "domanda")["bozza"])
caso("drafter nel worker: conta sull'in-memory", 2, llm._contatore["chiamate"])
caso("drafter nel worker: nessun incremento persistente", 0, _persistente["chiamate"])

# 5. Argo (consumer host): aggancia il persistente col suo testo -> invariato
_src_consumer = (REPO_ROOT / "scripts" / "argo" / "orienta_webhook.py").read_text(encoding="utf-8")
caso("Argo: il consumer aggancia ancora il persistente col proprio testo", True,
     'usa_contatore_persistente(incrementa_chiamate_llm, "risposte di Argo sospese")' in _src_consumer)
_stato_iniziale()
llm.usa_contatore_persistente(psql_host.incrementa_chiamate_llm, "risposte di Argo sospese")
_http["risposta"] = "ok"
llm.chiama("s", "p")
caso("Argo: la chiamata incrementa il persistente", 1, _persistente["chiamate"])
os.environ["LLM_TETTO_GIORNALIERO"] = "1"
try:
    llm.chiama("s", "p")
except llm.TettoLLMRaggiunto:
    pass
caso("Argo: notifica col testo di Argo", True, "risposte di Argo sospese" in _notifiche[0])
os.environ["LLM_TETTO_GIORNALIERO"] = "100"

# 6. Hook memoria: aggancia il persistente col suo testo -> invariato
_src_hook = (REPO_ROOT / "scripts" / "memoria" / "hook_sessione.py").read_text(encoding="utf-8")
caso("hook memoria: aggancia ancora il persistente col proprio testo", True,
     'usa_contatore_persistente(incrementa_chiamate_llm, "riassunti di sessione sospesi")' in _src_hook)
_stato_iniziale()
llm.usa_contatore_persistente(psql_host.incrementa_chiamate_llm, "riassunti di sessione sospesi")
llm.chiama("s", "p")
caso("hook memoria: la chiamata incrementa il persistente", 1, _persistente["chiamate"])

# Rimettere incrementa=None riporta al persistente di default, non all'in-memory
_stato_iniziale()
llm.usa_contatore_persistente(lambda g: 1, "x")
llm._contatore_persistente["incrementa"] = None
llm.chiama("s", "p")
caso("incrementa=None riporta al persistente di default", 1, _persistente["chiamate"])


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
