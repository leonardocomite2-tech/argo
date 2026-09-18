#!/usr/bin/env python3
"""Le ultime N sessioni di Claude Code pertinenti a un percorso o a un cantiere.

    python3 scripts/memoria/leggi_sessioni.py --file argo/voce.py [-n 5]
    python3 scripts/memoria/leggi_sessioni.py --file scripts/argo     # anche una cartella
    python3 scripts/memoria/leggi_sessioni.py --cantiere ponte [-n 5]
    python3 scripts/memoria/leggi_sessioni.py --ultime [-n 5]

Sola lettura sulla tabella `sessioni` (via argo/stato.py:_query_db, stessa
deviazione docker exec). Il nome del cantiere si risolve contro '## CANTIERI'
di STATO.md come fa /brief: nessuna corrispondenza o più di una -> l'elenco
dei nomi validi ed exit 2, mai un cantiere indovinato.
Exit: 0 ok (anche con zero righe), 2 argomento non risolvibile, 1 errore DB.
"""
import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from argo.stato import ErroreQueryDB, _query_db, cantieri_aperti  # noqa: E402
from argo.voce import _risolvi_cantiere  # noqa: E402
from sessione import letterale_sql as _letterale  # noqa: E402

COLONNE = """
    session_id, inizio, fine, motivo_fine, copertura, cantieri, file_toccati,
    commit, correzioni_manuali, sospesi_aperti, sospesi_chiusi,
    sessioni_parallele, decisioni, decisioni_stato
"""


def filtro_file(percorso):
    """Il file esatto, o tutto ciò che sta sotto la cartella indicata."""
    p = percorso.strip().rstrip("/")
    return (
        "EXISTS (SELECT 1 FROM unnest(file_toccati) f "
        f"WHERE f = {_letterale(p)} OR f LIKE {_letterale(p + '/%')})"
    )


def _formatta(r):
    righe = [f"— {r['inizio'] or '?'} → {r['fine'] or 'aperta'}  sessione {r['session_id'][:8]}  "
             f"(copertura: {r['copertura'] or '?'}, fine: {r['motivo_fine'] or '?'})"]
    righe.append(f"  cantiere: {', '.join(r['cantieri']) if r['cantieri'] else 'non determinato'}")
    if r["decisioni"]:
        righe.append(f"  deciso: {r['decisioni']}")
    else:
        righe.append(f"  deciso: [nessun riassunto — {r['decisioni_stato'] or 'non ancora scritto'}]")
    for c in r["commit"] or []:
        righe.append(f"  commit {c['hash'][:7]} {c['oggetto']}")
    if r["file_toccati"]:
        righe.append(f"  file: {', '.join(r['file_toccati'])}")
    if r["correzioni_manuali"] is None:
        righe.append("  correzioni manuali: non rilevabili (transcript non leggibile)")
    elif r["correzioni_manuali"]:
        righe.append(f"  correzioni manuali: {', '.join(r['correzioni_manuali'])}")
    for chiave, etichetta in (("sospesi_aperti", "SOSPESO aperto"), ("sospesi_chiusi", "SOSPESO chiuso")):
        for v in r[chiave] or []:
            righe.append(f"  {etichetta} [{v['fonte']}]: {v['testo']}")
    if r["sessioni_parallele"]:
        righe.append(f"  in parallelo con: {', '.join(s[:8] for s in r['sessioni_parallele'])}")
    return "\n".join(righe)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gruppo = parser.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("--file", metavar="PERCORSO")
    gruppo.add_argument("--cantiere", metavar="NOME")
    gruppo.add_argument("--ultime", action="store_true")
    parser.add_argument("-n", type=int, default=5)
    parser.add_argument("--json", action="store_true", help="righe grezze in JSON")
    args = parser.parse_args(argv)

    if args.file:
        where = filtro_file(args.file)
    elif args.cantiere:
        tabella = cantieri_aperti()
        if tabella["copertura"] != "completa":
            print(f"CANTIERI di STATO.md non affidabile: {tabella['motivo']}", file=sys.stderr)
            return 2
        trovati = _risolvi_cantiere(args.cantiere, tabella["cantieri"])
        if len(trovati) != 1:
            esito = "ambiguo" if trovati else "non trovato"
            validi = "\n".join(f"- {c['nome']}" for c in tabella["cantieri"])
            print(f'"{args.cantiere}" {esito}. Cantieri validi:\n{validi}', file=sys.stderr)
            return 2
        where = f"{_letterale(trovati[0]['nome'])} = ANY(cantieri)"
    else:
        where = "TRUE"

    sql = f"SELECT {COLONNE} FROM sessioni WHERE {where} ORDER BY COALESCE(fine, inizio) DESC NULLS LAST LIMIT {max(args.n, 1)}"
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        print(f"lettura di sessioni fallita: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(righe, ensure_ascii=False, indent=2, default=str))
    elif not righe:
        print("nessuna sessione registrata per questa richiesta")
    else:
        print("\n\n".join(_formatta(r) for r in righe))
    return 0


if __name__ == "__main__":
    sys.exit(main())
