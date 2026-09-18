"""python3 tests/eval_modi_argo.py [giri]

Chiama l'API Anthropic per davvero (non è un mock): misura le risposte dei
modi di Argo (argo/voce.py) sullo stato vero del sistema, letto in sola
lettura. Nessuna scrittura su DB, nessun Telegram. Va rilanciato dopo ogni
modifica a SOUL.md o alle ISTRUZIONI_* dei modi.

Controlla i tre difetti del collaudo del passo 9 (passo 10 della voce):
- nessun backtick nel testo (garantito da _senza_backtick, qui verificato
  sul testo che partirebbe davvero);
- nessuna azione su cose che girano già (lista nera euristica: avviare o
  lanciare il consumer, il cron, il deploy, git push — non prova che ogni azione
  proposta sia fondata, prova che quella già vista non torna);
- in impatto, nessun totale di contratti scritto dal modello: il totale lo
  aggiunge il codice nell'ultima riga "Contratti in gioco (N)". Il numero di
  pipeline è ammesso: lo dà impatti.py stesso (riga TRASVERSALE).
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

import argo.voce as voce  # noqa: E402

AZIONI_GIA_IN_FUNZIONE = re.compile(
    r"\b(avvia\w*|lancia\w*|attiva\w*|fai partire|metti in cron|configura\w*)\b[^.\n]{0,40}"
    r"\b(consumer|cron\w*|deploy|worker)\b"
    r"|\bdocker compose up\b|\bfai il deploy\b|\bfare il deploy\b"
    r"|\bgit push\b",  # collaudo passo 10: "Poi git push" con il repo già allineato a origin
    re.IGNORECASE,
)
NUMERI = r"(\d+|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)"
TOTALE_DEL_MODELLO = re.compile(
    rf"\b{NUMERI}\s+contratti\b|\bcontratti\b[^.\n]{{0,30}}\bsono\s+{NUMERI}\b|\b(gli )?altri {NUMERI}\b",
    re.IGNORECASE,
)
RIGA_TOTALE = re.compile(r"\n\nContratti in gioco \(\d+\): [^\n]+\.$")

CASI = [
    ("instrada 30/computer", lambda: voce.genera_risposta_instrada(30, "computer"), "proposta"),
    ("instrada 10/telefono", lambda: voce.genera_risposta_instrada(10, "telefono"), "proposta"),
    ("orienta", lambda: voce.genera_risposta(), "proposta"),
    ("impatto mailer", lambda: voce.genera_impatto("mailer")[0], "impatto"),
    ("impatto approvals", lambda: voce.genera_impatto("approvals")[0], "impatto"),
]


def controlla(testo, tipo):
    problemi = []
    if "`" in testo:
        problemi.append("backtick")
    if tipo == "proposta":
        m = AZIONI_GIA_IN_FUNZIONE.search(testo)
        if m:
            problemi.append(f"azione su cosa già in funzione: {m.group(0)!r}")
    if tipo == "impatto":
        corpo = RIGA_TOTALE.split(testo)[0]
        m = TOTALE_DEL_MODELLO.search(corpo)
        if m:
            problemi.append(f"totale scritto dal modello: {m.group(0)!r}")
    return problemi


def main():
    giri = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    falliti, totale = 0, 0
    for giro in range(1, giri + 1):
        for nome, genera, tipo in CASI:
            totale += 1
            testo = genera()
            problemi = controlla(testo, tipo)
            if problemi:
                falliti += 1
                print(f"FALLITO giro {giro}: {nome} — {'; '.join(problemi)}\n{testo}\n")
    print(f"{totale - falliti}/{totale} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
