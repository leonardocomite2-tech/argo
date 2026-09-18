"""python3 tests/eval_classificatore_argo.py

Chiama l'API Anthropic per davvero (non è un mock): misura il prompt vero
del classificatore dei messaggi liberi di Argo (argo/voce.py:
SISTEMA_CLASSIFICATORE). Va rilanciato dopo ogni modifica a quel prompt.
Nessuna scrittura su DB: la finestra di conversazione è finta, passata caso
per caso. Il confronto è sul risultato di risolvi_modo, cioè su quello che
Argo farebbe davvero: modo più parametri, oppure la riga che chiede."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

import argo.voce as voce  # noqa: E402

CASI = [
    # --- le tre frasi del criterio di chiusura ---
    {"testo": "come sta andando?", "attesa": ("conversazione", {})},
    {"testo": "ho mezz'ora al computer", "attesa": ("instrada", {"minuti": 30, "contesto": "computer"})},
    {"testo": "cosa rischio se tocco mailer", "attesa": ("impatto", {"componente": "mailer"})},
    # --- gli altri esempi del brief ---
    {"testo": "ho venti minuti in metro", "attesa": ("instrada", {"minuti": 20, "contesto": "telefono"})},
    {"testo": "è passato il digest ieri sera?", "attesa": ("conversazione", {})},
    # --- orienta ---
    {"testo": "sono perso, dove ero rimasto?", "attesa": ("orienta", {})},
    # --- brief ---
    {"testo": "preparami il brief per il designer", "attesa": ("brief", {"nome": "designer"})},
    {"testo": "mi serve un brief per Claude Code", "attesa": ("chiedi", voce.TESTO_CHIEDI_CANTIERE)},
    # --- impatto su una tabella e senza oggetto ---
    {"testo": "cosa si rompe se cambio la tabella approvals?", "attesa": ("impatto", {"componente": "approvals"})},
    {"testo": "cosa rischio se lo tocco?", "attesa": ("chiedi", voce.TESTO_CHIEDI_OGGETTO_IMPATTO)},
    # --- instrada con un parametro mancante: chiede, non indovina ---
    {"testo": "ho dieci minuti, cosa faccio?", "attesa": ("chiedi", "Sei al telefono o al computer?")},
    {"testo": "sono al computer, cosa chiudo?", "attesa": ("chiedi", "Quanti minuti hai?")},
    # --- seguito con finestra: risponde alla domanda di Argo ---
    {
        "testo": "telefono",
        "storico": [
            {"ruolo": "leonardo", "testo": "ho dieci minuti, cosa faccio?"},
            {"ruolo": "argo", "testo": "Sei al telefono o al computer?"},
        ],
        "attesa": ("instrada", {"minuti": 10, "contesto": "telefono"}),
    },
    {
        "testo": "e perché proprio quella?",
        "storico": [
            {"ruolo": "leonardo", "testo": "come stiamo messi?"},
            {"ruolo": "argo", "testo": "La cosa che aspetta te è l'approvazione ferma dal 2026-09-03."},
        ],
        "attesa": ("conversazione", {}),
    },
    # --- passo 11: domande sul collaudo instradate su brief (collaudo passo 10) ---
    {"testo": "come collauderesti al meglio Argo voce", "attesa": ("conversazione", {})},
    {"testo": "cosa manca per chiudere il designer?", "attesa": ("conversazione", {})},
    {"testo": "Sto cercando di fare collaudo cantiere comunicatore, ti torna?", "attesa": ("conversazione", {})},
    {
        "testo": "Come mi diresti di fare il collaudo al meglio?",
        "storico": [
            {"ruolo": "leonardo", "testo": "Sto cercando di fare collaudo cantiere comunicatore, ti torna?"},
            {"ruolo": "argo", "testo": "Collaudo reale del ponte Argo: verifica che l'avviso parta alle 22:15 e che il ramo conversazionale funzioni da Telegram."},
        ],
        "attesa": ("conversazione", {}),
    },
    {
        "testo": "Sarebbe argo la voce che serve a comunicare, procedi quindi capendo per il collaudo",
        "storico": [
            {"ruolo": "leonardo", "testo": "Sto cercando di fare collaudo cantiere comunicatore, ti torna?"},
            {"ruolo": "argo", "testo": "Collaudo reale del ponte Argo: verifica che l'avviso parta alle 22:15 e che il ramo conversazionale funzioni da Telegram."},
            {"ruolo": "leonardo", "testo": "Come mi diresti di fare il collaudo al meglio?"},
            {"ruolo": "argo", "testo": 'Nessun cantiere corrisponde a "comunicatore". Cantieri validi: ...'},
        ],
        "attesa": ("conversazione", {}),
    },
    {"testo": "fammi il brief per argo voce", "attesa": ("brief", {"nome": "argo voce"})},
    # --- non chiaro ---
    {"testo": "boh", "attesa": ("chiedi", voce.TESTO_NON_CHIARO)},
]


def main():
    falliti = 0
    originale = voce.stato.conversazione_recente
    for caso in CASI:
        storico = caso.get("storico", [])
        voce.stato.conversazione_recente = lambda prima_di_id, n, s=storico: {
            "copertura": "completa", "motivo": None, "righe": s,
        }
        try:
            decisione = voce.classifica_modo(0, caso["testo"])
            ottenuta = voce.risolvi_modo(decisione)
        except voce.ClassificatoreErrore as e:
            decisione, ottenuta = None, f"ERRORE({e})"
        if ottenuta != caso["attesa"]:
            falliti += 1
            print(f"FALLITO: {caso['testo']!r} — atteso {caso['attesa']!r}, ottenuto {ottenuta!r} (decisione {decisione!r})")
    voce.stato.conversazione_recente = originale

    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
