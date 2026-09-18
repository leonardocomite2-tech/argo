"""Test di tests/_llm_eval.py: un'eval non raggiunge mai il contatore di
produzione (llm_chiamate_giorno), in nessuno dei due modi. Zero rete e zero
DB: OpenRouter finto, HTTP Anthropic finto su urllib, contatore persistente
finto al posto di connectors/psql_host.incrementa_chiamate_llm. Stile CASI.
Lancio: python3 tests/test_llm_eval.py
"""
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import connectors.llm as llm  # noqa: E402
import connectors.openrouter as openrouter  # noqa: E402
import connectors.psql_host as psql_host  # noqa: E402
from tests import _llm_eval  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


os.environ["LLM_TETTO_GIORNALIERO"] = "100"
os.environ.setdefault("ANTHROPIC_API_KEY", "chiave-finta-dei-test")

registro = {"produzione": 0, "http_anthropic": 0, "openrouter": []}


def _produzione_finta(giorno):
    registro["produzione"] += 1
    return registro["produzione"]


psql_host.incrementa_chiamate_llm = _produzione_finta


class _RispostaFinta:
    def __init__(self):
        self._corpo = json.dumps({"content": [{"type": "text", "text": "ok"}], "stop_reason": "end_turn"}).encode()

    def read(self):
        return self._corpo

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def _urlopen_finto(req, timeout=None):
    registro["http_anthropic"] += 1
    return _RispostaFinta()


urllib.request.urlopen = _urlopen_finto


def _openrouter_finto(system, prompt, modello, max_tokens=500, temperature=0.0, marcatore_se_troncato=None):
    registro["openrouter"].append({"system": system, "prompt": prompt, "modello": modello, "max_tokens": max_tokens})
    return "ok"


openrouter.chiama = _openrouter_finto

# --- modo di default: OpenRouter ---
resto = _llm_eval.prepara_eval(["3", "--modello", "prova/modello:free"])
import argo.voce as voce  # noqa: E402
import brain.classifier as classifier  # noqa: E402
import brain.drafter as drafter  # noqa: E402

caso("default: gli argomenti non dell'helper restano", ["3"], resto)
caso("default: chiama sostituito in voce, classifier, drafter", [True, True, True],
     [m.chiama is _llm_eval.chiama_eval for m in (voce, classifier, drafter)])
voce.chiama("sistema di a@b.it", "scrive mario.rossi@esempio.com", max_tokens=50)
caso("default: la chiamata va a OpenRouter con il modello scelto", "prova/modello:free",
     registro["openrouter"][-1]["modello"])
caso("default: margine di ragionamento aggiunto a max_tokens solo qui", 50 + _llm_eval.MARGINE_RAGIONAMENTO_EVAL,
     registro["openrouter"][-1]["max_tokens"])
# 429: due nuovi tentativi al massimo, poi l'errore risale
_llm_eval.time.sleep = lambda s: None
_esiti = [openrouter.ErroreOpenRouter("openrouter status=429 body=x", retry_after=5)] * 2 + ["ok"]


def _openrouter_429(system, prompt, modello, max_tokens=500, temperature=0.0, marcatore_se_troncato=None):
    esito = _esiti.pop(0)
    if isinstance(esito, Exception):
        raise esito
    return esito


openrouter.chiama = _openrouter_429
caso("429: riprova dopo retry_after, al terzo tentativo risponde", "ok", voce.chiama("s", "p"))
_esiti[:] = [openrouter.ErroreOpenRouter("openrouter status=429 body=x")] * 3
try:
    voce.chiama("s", "p")
    _risalito = False
except openrouter.ErroreOpenRouter:
    _risalito = True
caso("429: dopo due nuovi tentativi l'errore risale", (True, 0), (_risalito, len(_esiti)))
_esiti[:] = [openrouter.TettoOpenRouterRaggiunto("quota"), "ok"]
try:
    voce.chiama("s", "p")
    _risalito = False
except openrouter.TettoOpenRouterRaggiunto:
    _risalito = True
caso("quota esaurita: nessun nuovo tentativo", (True, 1), (_risalito, len(_esiti)))
openrouter.chiama = _openrouter_finto

caso("default: ogni indirizzo email esce oscurato (CD07)", [False, False],
     ["@" in registro["openrouter"][-1]["system"], "@" in registro["openrouter"][-1]["prompt"]])
try:
    llm.chiama("s", "p")  # sfuggita allo scambio: ramo Anthropic
    bloccata = False
except llm.LLMErrore:
    bloccata = True
caso("default: una chiamata Anthropic sfuggita è bloccata", True, bloccata)
caso("default: né HTTP Anthropic né contatore di produzione", (0, 0),
     (registro["http_anthropic"], registro["produzione"]))

# quota finita riconosciuta anche avvolta in un errore del modo
try:
    try:
        raise openrouter.TettoOpenRouterRaggiunto("quota")
    except llm.LLMErrore as e:
        raise voce.ConversazioneErrore("chiamata LLM fallita") from e
except voce.ConversazioneErrore as e:
    caso("quota_esaurita: riconosciuta dentro ConversazioneErrore", True, _llm_eval.quota_esaurita(e))
caso("quota_esaurita: altro errore no", False, _llm_eval.quota_esaurita(llm.LLMErrore("x")))

# oscura_stato: mittente, oggetto, ultimo_errore; id e date restano
class _StatoFinto:
    @staticmethod
    def approvazioni_in_attesa():
        return {"righe": [{"id": 10, "updated_at": "2026-09-03", "mittente": "x@y.it", "oggetto": "Info"}]}

    @staticmethod
    def osservazioni_nuove():
        return {"righe": [{"id": 1, "fonte": "panoptes", "testo": "scrive x@y.it: prezzo?"}]}

    @staticmethod
    def osservazioni_recenti(n):
        return {"righe": [{"id": 2, "fonte": "panoptes", "testo": "contenuto ricevuto", "stato": "nuova"}]}

    @staticmethod
    def job_falliti_recenti(ore):
        return {"righe": [{"tipo": "t", "ultimo_errore": "550 x@y.it"}]}

    @staticmethod
    def job_falliti():
        return {"falliti": [{"tipo": "t", "ultimo_errore": "550 x@y.it", "piu_recente": "2026-09-01"}]}


_llm_eval.oscura_stato(_StatoFinto)
caso("oscura_stato: approvazioni", [{"id": 10, "updated_at": "2026-09-03", "mittente": "[oscurato]", "oggetto": "[oscurato]"}],
     _StatoFinto.approvazioni_in_attesa()["righe"])
caso("oscura_stato: testo delle osservazioni nuove e recenti", ["[oscurato]", "[oscurato]", "panoptes"],
     [_StatoFinto.osservazioni_nuove()["righe"][0]["testo"], _StatoFinto.osservazioni_recenti(10)["righe"][0]["testo"],
      _StatoFinto.osservazioni_recenti(10)["righe"][0]["fonte"]])
caso("oscura_stato: job falliti recenti (avvisa)", "[oscurato]", _StatoFinto.job_falliti_recenti(24)["righe"][0]["ultimo_errore"])
caso("oscura_stato: job falliti", "[oscurato]", _StatoFinto.job_falliti()["falliti"][0]["ultimo_errore"])

# --- --anthropic: modello vero, contatore in-memory ---
_llm_eval.prepara_eval(["--anthropic"])
caso("--anthropic: chiama di produzione rimesso nei moduli", [True, True, True],
     [m.chiama is llm.chiama for m in (voce, classifier, drafter)])
caso("--anthropic: risposta dal ramo Anthropic", "ok", voce.chiama("s", "p"))
caso("--anthropic: HTTP Anthropic sì, contatore di produzione mai", (1, 0),
     (registro["http_anthropic"], registro["produzione"]))

# --- guardrail statico: ogni eval passa da prepara_eval prima dei moduli ---
for percorso in sorted((REPO_ROOT / "tests").glob("eval_*.py")):
    testo = percorso.read_text(encoding="utf-8")
    prepara = testo.find("prepara_eval(sys.argv")
    moduli = [m.start() for m in re.finditer(r"^(import argo|from argo|import brain|from brain)", testo, re.MULTILINE)]
    caso(f"{percorso.name}: prepara_eval prima di importare argo/brain", True,
         prepara != -1 and all(prepara < m for m in moduli))


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
