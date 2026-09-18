"""Test di connectors/llm.py, stile CASI (vedi tests/test_argo_voce.py).
Zero chiamate di rete: solo la funzione pura _applica_marcatore_troncamento.
Lancio: python3 tests/test_llm.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.llm as llm  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


MARCATORE = "[TRONCATO]"

caso(
    "_applica_marcatore_troncamento: stop_reason max_tokens + marcatore -> accodato",
    "testo parziale\n[TRONCATO]",
    llm._applica_marcatore_troncamento("testo parziale", "max_tokens", MARCATORE),
)
caso(
    "_applica_marcatore_troncamento: stop_reason end_turn -> testo invariato",
    "testo completo",
    llm._applica_marcatore_troncamento("testo completo", "end_turn", MARCATORE),
)
caso(
    "_applica_marcatore_troncamento: marcatore None (default di chiama()) -> invariato anche con max_tokens",
    "testo parziale",
    llm._applica_marcatore_troncamento("testo parziale", "max_tokens", None),
)


# --- tetto giornaliero con contatore persistente (passo 4bis del ponte) ---
import os  # noqa: E402

_notifiche = []
_notifica_vera = llm.notifica
llm.notifica = lambda testo, token=None: _notifiche.append(testo)
os.environ["LLM_TETTO_GIORNALIERO"] = "2"

_riga = {"chiamate": 0}


def _incrementa_finto(giorno):
    _riga["chiamate"] += 1
    return _riga["chiamate"]


llm.usa_contatore_persistente(_incrementa_finto, "risposte di Argo sospese")
_esiti = []
for _ in range(4):
    try:
        llm._verifica_tetto()
        _esiti.append("ok")
    except llm.TettoLLMRaggiunto:
        _esiti.append("tetto")
caso("contatore persistente: tetto 2 -> ok, ok, tetto, tetto", ["ok", "ok", "tetto", "tetto"], _esiti)
caso("contatore persistente: una sola notifica al superamento", 1, len(_notifiche))
caso("notifica dice cosa si ferma per questo processo", True, "risposte di Argo sospese" in _notifiche[0])


def _incrementa_rotto(giorno):
    raise RuntimeError("psql fallito")


llm.usa_contatore_persistente(_incrementa_rotto, "x")
try:
    llm._verifica_tetto()
    _esito = "chiamata permessa"
except llm.TettoLLMRaggiunto:
    _esito = "tetto"
except llm.LLMErrore:
    _esito = "LLMErrore"
caso("contatore persistente illeggibile -> LLMErrore, mai una chiamata alla cieca", "LLMErrore", _esito)

# default invariato per il worker: senza contatore persistente, in-memory
llm._contatore_persistente["incrementa"] = None
llm._contatore_persistente["cosa_si_ferma"] = None
llm._contatore["giorno"] = None
_notifiche.clear()
_esiti = []
for _ in range(3):
    try:
        llm._verifica_tetto()
        _esiti.append("ok")
    except llm.TettoLLMRaggiunto:
        _esiti.append("tetto")
caso("contatore in-memory (worker) invariato", ["ok", "ok", "tetto"], _esiti)
caso("notifica del worker col testo di sempre", True, "classificazione e bozze sospese" in _notifiche[0])
llm.notifica = _notifica_vera


def main():
    falliti = 0
    for descrizione, atteso, ottenuto in CASI:
        if ottenuto != atteso:
            falliti += 1
            print(f"FALLITO: {descrizione} — atteso {atteso!r}, ottenuto {ottenuto!r}")
    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
