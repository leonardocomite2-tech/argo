"""Test della memoria di sessione (scripts/memoria/sessione.py, logica pura),
stile CASI (vedi tests/test_argo_voce.py). Zero DB, zero git, zero rete: il
collaudo con psql/git/LLM veri è a mano (STATO.md, sessione 18/9/2026).
Lancio: python3 tests/test_memoria_sessioni.py
"""
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "memoria"))

import sessione as S  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


RADICE = "/root/argo"


def _assistente(*blocchi, ts="2026-09-18T08:00:00Z"):
    return json.dumps({"type": "assistant", "timestamp": ts, "message": {"content": list(blocchi)}})


def _tool(nome, **ingresso):
    return {"type": "tool_use", "name": nome, "input": ingresso}


TRANSCRIPT = "\n".join([
    json.dumps({"type": "mode", "sessionId": "x"}),
    json.dumps({"type": "user", "timestamp": "2026-09-18T07:00:00Z", "message": {"content": "<bash-input>sed -i s/a/b/ STATO.md</bash-input>"}}),
    _assistente(_tool("Edit", file_path="/root/argo/argo/voce.py")),
    _assistente(_tool("Write", file_path="/root/.claude/plans/piano.md")),
    _assistente(_tool("Bash", command="python3 - <<'EOF'\nPath('backend/main.py').write_text(s)\nEOF")),
    _assistente(_tool("Bash", command='git add -A && git commit -q -m "cantiere Argo — il ponte, passo 4: ramo"')),
    _assistente(_tool("Bash", command="grep -n 'git commit' vecchio.log")),
    _assistente({"type": "text", "text": "Fatto."}, ts="2026-09-18T09:30:00Z"),
    '{"type": "assistant", "message": {"content": [ riga troncata a metà',
])

righe = S.leggi_transcript(TRANSCRIPT)
caso("transcript: la riga troncata a metà è saltata, le altre lette", 8, len(righe))
caso("transcript vuoto -> None (il chiamante ripiega su git)", None, S.leggi_transcript(""))
caso("transcript illeggibile -> None", None, S.leggi_transcript("non json\nneanche questo"))

a = S.analizza_transcript(righe, RADICE)
caso("file scritti via Edit, relativi al repo", {"argo/voce.py"}, a["file_scritti"])
caso("file fuori dal repo (piani) esclusi", False, any("piano.md" in f for f in a["file_scritti"]))
caso("comandi con 'git commit' raccolti (anche il falso positivo del grep)", 2, len(a["comandi_commit"]))
caso("primo e ultimo timestamp", ("2026-09-18T07:00:00Z", "2026-09-18T09:30:00Z"), (a["primo_timestamp"], a["ultimo_timestamp"]))
caso("ultimo testo dell'assistente", "Fatto.", a["ultimo_testo_assistente"])
caso("il comando `!` di Leonardo non è un'azione di Claude", False, any("sed -i" in t for t in a["testi_tool"]))

# Attribuzione dei commit: oggetto presente alla lettera in un git commit della sessione
INTERVALLO = [
    {"hash": "2cb54f7", "oggetto": "cantiere Argo — il ponte, passo 4: ramo"},
    {"hash": "3beb5b3", "oggetto": "cantiere Argo — la voce, passo 9: classificatore"},
]
caso("commit della sessione parallela nello stesso intervallo NON attribuito",
     ["2cb54f7"], [c["hash"] for c in S.commit_della_sessione(INTERVALLO, a["comandi_commit"])])
caso("il grep con 'git commit' non attribuisce commit", [], S.commit_della_sessione(INTERVALLO, ["grep -n 'git commit' x"]))
caso("oggetto vuoto mai attribuito", [], S.commit_della_sessione([{"hash": "a", "oggetto": ""}], ["git commit -m ''"]))

# Correzioni manuali
caso("file scritto via Bash da Claude non è una correzione manuale", True,
     S.scritto_da_claude("backend/main.py", a["file_scritti"], a["testi_tool"]))
caso("file mai toccato da Claude nel diff = correzione manuale", ["STATO.md", "worker/loop.py"],
     S.correzioni_manuali(["argo/voce.py", "backend/main.py", "worker/loop.py", "STATO.md"], a["file_scritti"], a["testi_tool"]))
caso("nessuna correzione rilevata -> lista vuota (non None)", [],
     S.correzioni_manuali(["argo/voce.py"], a["file_scritti"], a["testi_tool"]))

# SOSPESI dal registro attriti
REGISTRO_PRIMA = """## Attriti registrati
x
## SOSPESI

1. [RISOLTO 07/09] vecchia domanda
2. domanda sul flood
3. domanda sul warmup

---
## Seed
"""
REGISTRO_DOPO = """## Attriti registrati
x
## SOSPESI

1. [RISOLTO 07/09] vecchia domanda
2. [RISOLTO 18/09] domanda sul flood
3. domanda sul warmup
4. nuova domanda sul transcript

---
## Seed
"""
aperti, chiusi = S.sospesi_dal_registro(REGISTRO_PRIMA, REGISTRO_DOPO)
caso("registro: voce nuova -> aperta, con fonte registro",
     [{"testo": "SOSPESO 4: nuova domanda sul transcript", "fonte": "registro"}], aperti)
caso("registro: voce passata a [RISOLTO] -> chiusa",
     [{"testo": "SOSPESO 2: [RISOLTO 18/09] domanda sul flood", "fonte": "registro"}], chiusi)
caso("registro: voce già risolta prima non conta come chiusa ora", 1, len(chiusi))
caso("registro assente -> niente", ([], []), S.sospesi_dal_registro("", ""))

aperti, chiusi = S.sospesi_da_stato_md([
    "SOSPESO 13 — il transcript ha lo stesso session_id dopo un resume?",
    "SOSPESO 12 — [RISOLTO 18/09] fix il giorno del deploy: ricorre",
    "  SOSPESO 14 — con spazi davanti, conta",
    "- DA_VERIFICARE: dedup_key su triggered_at",
    '  ("SOSPESO n —"), non il taglio della fonte.',
    "Le voci SOSPESO 7 ancora aperte non si toccano",
    "SOSPESO 9 - trattino corto, fuori convenzione",
    "SOSPESO — senza numero",
    "- [RISOLTO] il bug di run_after",
    "",
])
caso("STATO.md: solo le righe che cominciano con 'SOSPESO <n> —' sono aperte",
     ["SOSPESO 13 — il transcript ha lo stesso session_id dopo un resume?",
      "SOSPESO 14 — con spazi davanti, conta"], [v["testo"] for v in aperti])
caso("STATO.md: chiusa = stessa apertura + [RISOLTO]",
     ["SOSPESO 12 — [RISOLTO 18/09] fix il giorno del deploy: ricorre"], [v["testo"] for v in chiusi])
caso("STATO.md: la fonte resta dichiarata", {"stato_md_euristica"}, {v["fonte"] for v in aperti + chiusi})
caso("STATO.md: [RISOLTO] senza l'apertura convenzionale non conta", False,
     any("run_after" in v["testo"] for v in chiusi))

# Cantieri
NOMI = ["Argo — la voce", "Argo — il ponte", "Designer (bonifica yourservice-it)"]
caso("cantiere dalla riga CANTIERI modificata", ["Argo — il ponte"],
     S.cantieri_della_sessione(["| Argo — il ponte | aperto | 12/09/2026 | Leonardo | x |"], [], NOMI))
caso("cantiere dall'oggetto del commit (trattini normalizzati)", ["Argo — la voce"],
     S.cantieri_della_sessione([], ["cantiere Argo - la voce, passo 9: classificatore"], NOMI))
caso("nessun cantiere riconoscibile -> lista vuota, mai indovinato", [],
     S.cantieri_della_sessione([], ["fix typo"], NOMI))
caso("stesso cantiere da due fonti -> una volta sola", ["Argo — il ponte"],
     S.cantieri_della_sessione(["| Argo — il ponte | a | b | c | d |"], ["cantiere Argo — il ponte, passo 4"], NOMI))

# Segreti: nomi sì, valori mai
ENV = "ANTHROPIC_API_KEY=sk-ant-api03-ABCDEFGHIJKLMNOP\nPG_PASSWORD='password-lunga-123'\nLLM_TETTO_GIORNALIERO=150\n# commento\n"
segreti = S.valori_segreti(ENV)
caso("valori abbastanza lunghi presi, quelli corti no (150)", False, "150" in segreti)
riga = {"decisioni": "usata la chiave sk-ant-api03-ABCDEFGHIJKLMNOP e PG_PASSWORD=password-lunga-123",
        "commit": [{"oggetto": "password-lunga-123 nel messaggio"}], "n": 3}
pulita = S.redigi(riga, segreti)
caso("valore .env tolto anche dentro liste e dict annidati", "*** nel messaggio", pulita["commit"][0]["oggetto"])
caso("il NOME della variabile resta, il valore no", "usata la chiave *** e PG_PASSWORD=***", pulita["decisioni"])
caso("formato sk-ant tolto anche senza .env", "chiave ***", S.redigi("chiave sk-ant-api03-XYZXYZXYZXYZ", []))
caso("valori non stringa intatti", 3, pulita["n"])

# Contratto SE01: nell'hook la riga si scrive PRIMA della chiamata LLM
sorgente = (REPO_ROOT / "scripts" / "memoria" / "hook_sessione.py").read_text(encoding="utf-8")
corpo_fine = sorgente.split("def fine(dati):", 1)[1].split("\ndef ", 1)[0]
caso("fine(): scrivi_riga prima di scrivi_decisioni", True,
     0 <= corpo_fine.index("scrivi_riga(") < corpo_fine.index("scrivi_decisioni("))
caso("fine(): la chiamata LLM parte solo dopo l'UPSERT", True, "if scrivi_riga(riga) and materiale is not None:" in corpo_fine)
caso("il prompt del riassunto vieta i valori dei segreti", True, "VALORI mai" in sorgente)


# letterale_sql: nessun testo può far fallire la scrittura (review 18/9)
_ostile = "commit che cita $argo_mem$ e $m$ e ' apici ' e $$"
_lett = S.letterale_sql(_ostile)
_tag = _lett[:_lett.index("$", 1) + 1]
caso("letterale_sql: il tag non compare nel testo", False, _tag in _ostile)
caso("letterale_sql: testo intatto fra i due tag", _ostile, _lett[len(_tag):-len(_tag)])

# fine(): raccolta fallita -> riga minima comunque scritta, niente LLM
import hook_sessione as H  # noqa: E402

_scritte, _llm = [], []
_orig = (H.raccogli, H._riga_esistente, H.scrivi_riga, H.scrivi_decisioni)


def _raccolta_rotta(dati, esistente):
    raise RuntimeError("git bloccato")


H.raccogli = _raccolta_rotta
H.scrivi_riga = lambda riga: (_scritte.append(riga) or True)
H.scrivi_decisioni = lambda *a: _llm.append(a)
H._riga_esistente = lambda k: {}
H.fine({"session_id": "s1", "reason": "other"})
caso("raccolta fallita: la riga minima viene scritta", 1, len(_scritte))
caso("riga minima: copertura dichiara l'errore per categoria", "errore raccolta: RuntimeError", _scritte[0]["copertura"])
caso("riga minima: campi derivati non rilevabili (None), non vuoti", (None, None, None),
     (_scritte[0]["file_toccati"], _scritte[0]["correzioni_manuali"], _scritte[0]["commit"]))
caso("riga minima: nessuna chiamata LLM", [], _llm)

_scritte.clear()
H._riga_esistente = lambda k: {"completa": True}
H.fine({"session_id": "s1", "reason": "other"})
caso("raccolta fallita su riga già completa: non sovrascritta", [], _scritte)
H.raccogli, H._riga_esistente, H.scrivi_riga, H.scrivi_decisioni = _orig


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
