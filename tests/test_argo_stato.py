"""Test di argo/stato.py, stile CASI (vedi tests/test_panoptes_lib.py).
Lancio: python3 tests/test_argo_stato.py
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import argo.stato as stato  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- guardrail statico: argo/stato.py non scrive mai sul DB ---
sorgente = (REPO_ROOT / "argo" / "stato.py").read_text(encoding="utf-8")
verbi_scrittura = re.findall(r"\b(INSERT|UPDATE|DELETE)\b", sorgente, re.IGNORECASE)
caso("nessun verbo di scrittura SQL nel sorgente di argo/stato.py", [], verbi_scrittura)

# --- categoria_da_chiave_alert ---
caso(
    "prefisso noto",
    "approvazione bloccata da più di 6h",
    stato.categoria_da_chiave_alert("appr_bloccata:11"),
)
caso(
    "prefisso sconosciuto non viene silenziato",
    "sconosciuto (prefisso 'nuovo_tipo')",
    stato.categoria_da_chiave_alert("nuovo_tipo:99"),
)
caso(
    "chiave senza ':' usa la chiave intera come prefisso",
    "sconosciuto (prefisso 'chiavesenzadue punti')",
    stato.categoria_da_chiave_alert("chiavesenzadue punti"),
)

# --- _estrai_sezione / _indice_sessioni su un STATO.md finto ---
STATO_FINTO = """# STATO — finto

## Fatto
- cosa fatta

## In corso
- riga uno
- riga due

## DECISIONI APERTE — bloccano
- decisione bloccante uno
- decisione bloccante due

## Note operative
- nota
"""

caso(
    "estrae 'In corso' fino al prossimo ## ",
    "- riga uno\n- riga due",
    stato._estrai_sezione(STATO_FINTO, "In corso"),
)
caso(
    "estrae 'DECISIONI APERTE — bloccano' fino al prossimo ## ",
    "- decisione bloccante uno\n- decisione bloccante due",
    stato._estrai_sezione(STATO_FINTO, "DECISIONI APERTE — bloccano"),
)
caso(
    "sezione assente ritorna None, non stringa vuota",
    None,
    stato._estrai_sezione(STATO_FINTO, "Sezione che non esiste"),
)
caso(
    "indice sessioni elenca tutti i titoli ## con la riga giusta",
    [
        {"titolo": "Fatto", "riga": 3},
        {"titolo": "In corso", "riga": 6},
        {"titolo": "DECISIONI APERTE — bloccano", "riga": 10},
        {"titolo": "Note operative", "riga": 14},
    ],
    stato._indice_sessioni(STATO_FINTO, n=15),
)


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
