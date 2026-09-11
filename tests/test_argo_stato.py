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


# --- chiave_cantiere: normalizzazione nome cantiere per il match coi titoli ---
caso(
    "chiave_cantiere: toglie la nota tra parentesi finale",
    "designer",
    stato.chiave_cantiere("Designer (bonifica yourservice-it)"),
)
caso(
    "chiave_cantiere: en-dash convertito in spazio, minuscolo",
    "panoptes mappa",
    stato.chiave_cantiere("Panoptes — Mappa"),
)
caso(
    "chiave_cantiere: non taglia al primo trattino, 'la voce' e 'il ponte' restano diversi",
    "argo la voce",
    stato.chiave_cantiere("Argo — la voce"),
)
caso(
    "chiave_cantiere: 'il ponte' non collassa su 'la voce'",
    "argo il ponte",
    stato.chiave_cantiere("Argo — il ponte"),
)
caso(
    "chiave_cantiere: slash e trattino singolo dentro il nome sopravvivono (non normalizzati)",
    "cantiere 3 dm instagram/facebook",
    stato.chiave_cantiere("Cantiere 3 — DM Instagram/Facebook"),
)

# --- sessioni_cantiere: su un STATO.md finto con titoli reali-come, dash misti ---
STATO_SESSIONI_FINTO = """# STATO — finto

## Sessione 1 — Cantiere Panoptes-Mappa, passo 1
corpo passo 1 panoptes

## Sessione 2026-09-10 — Cantiere Argo — la voce, fondamenta
corpo fondamenta la voce

## Sessione 2026-09-11 — Cantiere Argo — la voce, passo 8: il modo "avvisa"
corpo passo 8 la voce

## Sessione 2026-09-12 — Cantiere Argo — il ponte, passo 1
corpo passo 1 il ponte

## Fatto
- niente di specifico a nessun cantiere con intestazione dedicata
"""
_percorso_originale_sessioni = stato.STATO_MD_PATH
_stato_sessioni_path = REPO_ROOT / "tests" / "_stato_finto_sessioni.md"
_stato_sessioni_path.write_text(STATO_SESSIONI_FINTO, encoding="utf-8")
try:
    stato.STATO_MD_PATH = _stato_sessioni_path

    _ris = stato.sessioni_cantiere("Panoptes — Mappa", n=3)
    caso("sessioni_cantiere: copertura completa", "completa", _ris["copertura"])
    caso(
        "sessioni_cantiere: 'Panoptes — Mappa' trova il titolo con trattino singolo",
        1,
        len(_ris["sezioni"]),
    )
    caso(
        "sessioni_cantiere: corpo della sezione trovata",
        "corpo passo 1 panoptes",
        _ris["sezioni"][0]["testo"] if _ris["sezioni"] else None,
    )

    _ris_voce = stato.sessioni_cantiere("Argo — la voce", n=3)
    caso(
        "sessioni_cantiere: 'Argo — la voce' trova le sue due sessioni, non quelle de 'il ponte'",
        2,
        len(_ris_voce["sezioni"]),
    )

    _ris_ponte = stato.sessioni_cantiere("Argo — il ponte", n=3)
    caso(
        "sessioni_cantiere: 'Argo — il ponte' non è ambiguo con 'la voce' (nomi diversi dopo il trattino)",
        1,
        len(_ris_ponte["sezioni"]),
    )

    _ris_n = stato.sessioni_cantiere("Argo — la voce", n=1)
    caso("sessioni_cantiere: n=1 ritorna solo la più recente (ultima nel file)", 1, len(_ris_n["sezioni"]))
    caso(
        "sessioni_cantiere: con n=1, la sessione tenuta è l'ultima trovata nel file",
        "corpo passo 8 la voce",
        _ris_n["sezioni"][0]["testo"] if _ris_n["sezioni"] else None,
    )

    _ris_vuoto = stato.sessioni_cantiere("Cantiere 2 — email", n=3)
    caso(
        "sessioni_cantiere: zero sezioni è un esito valido (copertura completa), non un errore",
        ("completa", []),
        (_ris_vuoto["copertura"], _ris_vuoto["sezioni"]),
    )
finally:
    stato.STATO_MD_PATH = _percorso_originale_sessioni
    _stato_sessioni_path.unlink()


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
