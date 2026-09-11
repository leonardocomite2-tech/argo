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
caso(
    "prefisso avvisa_appr riconosciuto (passo 8)",
    "approvazione già segnalata dall'avviso serale di Argo",
    stato.categoria_da_chiave_alert("avvisa_appr:10"),
)
caso(
    "prefisso avvisa_job riconosciuto (passo 8)",
    "job fallito già segnalato dall'avviso serale di Argo",
    stato.categoria_da_chiave_alert("avvisa_job:digest_serale:abc123"),
)

# --- job_falliti_recenti: stessa forma esplicita nel sorgente di job_falliti,
# ma CON finestra temporale (passo 8: senza, mostrerebbe i 109 fallimenti
# storici di digest_serale del 27-29/08, vedi STATO.md) ed esclude
# 'test_approvazione' come fa worker/loop.py:digest_serale ---
_sorgente_stato = (REPO_ROOT / "argo" / "stato.py").read_text(encoding="utf-8")
_sorgente_job_falliti_recenti = _sorgente_stato[_sorgente_stato.index("def job_falliti_recenti"):]
caso(
    "job_falliti_recenti ha una finestra temporale su created_at",
    True,
    "created_at >= now() - interval" in _sorgente_job_falliti_recenti,
)
caso(
    "job_falliti_recenti esclude test_approvazione",
    True,
    "tipo != 'test_approvazione'" in _sorgente_job_falliti_recenti,
)

# --- chiavi_alert_con_prefisso: nessuna finestra temporale (anti-ripetizione
# per sempre, non nelle 24h come escalation_aperte) ---
_sorgente_chiavi_alert = _sorgente_stato[_sorgente_stato.index("def chiavi_alert_con_prefisso"):]
caso(
    "chiavi_alert_con_prefisso non ha finestra temporale (per sempre)",
    False,
    "interval" in _sorgente_chiavi_alert[:_sorgente_chiavi_alert.index("def ", 1)],
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


# --- _estrai_cantieri su blocchi '## CANTIERI' finti ---
CANTIERI_BEN_FORMATO = """# STATO — finto

## CANTIERI

| Nome | Stato | Aperto il | Aspetta | Sessione più recente |
|---|---|---|---|---|
| Cantiere prova | aperto | 01/01/2026 | Leonardo | Sessione 01/01/2026 |
| Cantiere due | in attesa | da confermare | calendario | Sessione 02/01/2026 |

## Fatto
- niente
"""

caso(
    "_estrai_cantieri: blocco ben formato ritorna la lista, nessun motivo",
    (
        [
            {
                "nome": "Cantiere prova", "stato": "aperto", "aperto_il": "01/01/2026",
                "aspetta": "Leonardo", "sessione_riferimento": "Sessione 01/01/2026",
            },
            {
                "nome": "Cantiere due", "stato": "in attesa", "aperto_il": "da confermare",
                "aspetta": "calendario", "sessione_riferimento": "Sessione 02/01/2026",
            },
        ],
        None,
    ),
    stato._estrai_cantieri(CANTIERI_BEN_FORMATO),
)

CANTIERI_ASSENTE = "# STATO — finto\n\n## Fatto\n- niente\n"
_lista, _motivo = stato._estrai_cantieri(CANTIERI_ASSENTE)
caso("_estrai_cantieri: blocco assente ritorna None", None, _lista)
caso("_estrai_cantieri: blocco assente, motivo esplicito", "blocco '## CANTIERI' assente", _motivo)

CANTIERI_INTESTAZIONI_SBAGLIATE = """# STATO — finto

## CANTIERI

| Cantiere | Stato |
|---|---|
| Prova | aperto |

## Fatto
"""
_lista, _motivo = stato._estrai_cantieri(CANTIERI_INTESTAZIONI_SBAGLIATE)
caso("_estrai_cantieri: intestazioni sbagliate ritorna None", None, _lista)
caso("_estrai_cantieri: intestazioni sbagliate, motivo non None", True, _motivo is not None)

CANTIERI_STATO_FUORI_VOCABOLARIO = """# STATO — finto

## CANTIERI

| Nome | Stato | Aperto il | Aspetta | Sessione più recente |
|---|---|---|---|---|
| Cantiere prova | in_pausa | 01/01/2026 | Leonardo | Sessione 01/01/2026 |

## Fatto
"""
_lista, _motivo = stato._estrai_cantieri(CANTIERI_STATO_FUORI_VOCABOLARIO)
caso("_estrai_cantieri: stato fuori vocabolario ritorna None", None, _lista)
caso("_estrai_cantieri: stato fuori vocabolario, motivo non None", True, _motivo is not None)

# --- cantieri_aperti(): copertura completa vs parziale, su STATO_MD_PATH rediretto ---
_stato_finto_path = REPO_ROOT / "tests" / "_stato_finto_cantieri.md"
_stato_finto_path.write_text(CANTIERI_BEN_FORMATO, encoding="utf-8")
_percorso_originale = stato.STATO_MD_PATH
try:
    stato.STATO_MD_PATH = _stato_finto_path
    _risultato = stato.cantieri_aperti()
    caso("cantieri_aperti: copertura completa con blocco ben formato", "completa", _risultato["copertura"])
    caso("cantieri_aperti: cantieri popolato con blocco ben formato", 2, len(_risultato["cantieri"]))

    _stato_finto_path.write_text(CANTIERI_ASSENTE, encoding="utf-8")
    _risultato = stato.cantieri_aperti()
    caso("cantieri_aperti: copertura parziale senza blocco CANTIERI", "parziale", _risultato["copertura"])
    caso("cantieri_aperti: cantieri None senza blocco CANTIERI", None, _risultato["cantieri"])
finally:
    stato.STATO_MD_PATH = _percorso_originale
    _stato_finto_path.unlink()


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
