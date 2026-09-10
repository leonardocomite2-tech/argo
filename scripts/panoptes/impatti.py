#!/usr/bin/env python3
"""Cosa dipende da un pezzo di codice, secondo knowledge/mappa_sistema.yaml.

La mappa è la fonte, non il codice: questo script non esplora il repo, legge
solo la mappa e (per --diff) `git diff`. Zero LLM.

Uso:
    python3 scripts/panoptes/impatti.py --file worker/loop.py:1230
    python3 scripts/panoptes/impatti.py --file worker/loop.py
    python3 scripts/panoptes/impatti.py --componente approvazione_telegram
    python3 scripts/panoptes/impatti.py --tabella approvals
    python3 scripts/panoptes/impatti.py --diff [--esci-1-se-trasversale]

Exit: 0 sempre (è informativo, non un cancello), salvo:
  - 2 se --componente/--tabella non esiste (vocabolario chiuso, quasi certo refuso)
  - 2 se --file punta a un path inesistente sul filesystem
  - 2 se la mappa non è parsabile/mancante
  - 1 con --esci-1-se-trasversale se il risultato è trasversale (>1 pipeline)
--file su un path esistente ma non mappato da nessuna scheda resta 0: è
un'informazione vera ("la mappa non copre questo file"), non un errore.
"""
import argparse
import re
import subprocess
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mappa_lib as lib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAPPA_PATH = REPO_ROOT / "knowledge" / "mappa_sistema.yaml"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

_HUNK_RE = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", re.MULTILINE)


def ottieni_diff_ranges():
    """git diff HEAD (working tree + staging, non solo unstaged) -> {file: [(start,end), ...]}."""
    nomi = subprocess.run(
        ["git", "diff", "HEAD", "--name-only"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout
    risultato = {}
    for f in (n for n in nomi.splitlines() if n):
        diff_out = subprocess.run(
            ["git", "diff", "HEAD", "--unified=0", "--", f], cwd=REPO_ROOT, capture_output=True, text=True, check=True
        ).stdout
        ranges = []
        for m in _HUNK_RE.finditer(diff_out):
            start = int(m.group(1))
            count = int(m.group(2)) if m.group(2) is not None else 1
            if count == 0:
                # pura cancellazione sul lato nuovo: nessuna riga aggiunta, ma qualcosa
                # è cambiato in quel punto — un punto singolo, non zero, per non perderlo
                ranges.append((max(start, 1), max(start, 1)))
            else:
                ranges.append((start, start + count - 1))
        if ranges:
            risultato[f] = ranges
    return risultato


def risolvi_punti(mappa, punti):
    """punti: list[(file,start,end)] -> (pipeline_finali, condivisi_usati, provenienza).

    pipeline_finali/condivisi_usati: dict nome->scheda. provenienza: dict
    nome_pipeline -> set(nomi condivisi) tramite cui è stata raggiunta.
    """
    pipeline_finali = {}
    condivisi_usati = {}
    provenienza = {}
    for file_path, s, e in punti:
        pm, cm = lib.schede_che_toccano(mappa, file_path, s, e)
        for p in pm:
            pipeline_finali[p["nome"]] = p
        for c in cm:
            condivisi_usati[c["nome"]] = c
            for nome_pl in c.get("usato_da", []) or []:
                pl = lib.trova_pipeline(mappa, nome_pl)
                if pl:
                    pipeline_finali[nome_pl] = pl
                    provenienza.setdefault(nome_pl, set()).add(c["nome"])
    return pipeline_finali, condivisi_usati, provenienza


def contratti_in_gioco(pipeline_finali, condivisi_usati, punti, con_overlap):
    """Unione dei contratti delle schede impattate. Se con_overlap e ci sono
    punti di riga, filtra a solo quelli il cui garantito_da fa overlap con
    almeno un punto — è il segnale principale di questo script."""
    risultati = []
    visti = set()
    for scheda in list(pipeline_finali.values()) + list(condivisi_usati.values()):
        for c in scheda.get("contratti", []) or []:
            if c["id"] in visti:
                continue
            visti.add(c["id"])
            overlap = False
            if con_overlap and punti:
                for rf, rs, re_ in lib.estrai_riferimenti_garantito_da(c.get("garantito_da", "")):
                    if any(rf == pf and lib.intervalli_si_sovrappongono(ps, pe, rs, re_) for pf, ps, pe in punti):
                        overlap = True
                        break
            risultati.append((scheda["nome"], c, overlap))
    if con_overlap and punti:
        risultati = [t for t in risultati if t[2]]
    return risultati


def stampa_intestazione(pipeline_finali):
    n = len(pipeline_finali)
    if n > 1:
        print(f"TRASVERSALE: sì ({n} pipeline)")
    else:
        print("TRASVERSALE: no")
    print()


def stampa_matches(intestazione, condivisi_usati, pipeline_finali, provenienza):
    if intestazione:
        print(intestazione)
    if not condivisi_usati and not pipeline_finali:
        print("  nessuna scheda impattata")
    for nome_c in sorted(condivisi_usati):
        c = condivisi_usati[nome_c]
        usato_da = ", ".join(c.get("usato_da", []) or [])
        print(f"  → {nome_c}  [condiviso, usato_da: {usato_da}]")
    for nome_p in sorted(pipeline_finali):
        via = provenienza.get(nome_p)
        if via:
            print(f"  → {nome_p}  [via componente condiviso {', '.join(sorted(via))}]")
        else:
            print(f"  → {nome_p}")
    print()


def stampa_contratti(contratti):
    print("CONTRATTI IN GIOCO")
    if not contratti:
        print("  nessuno")
        return
    for _owner, c, overlap in contratti:
        marcatore = "   ← la modifica tocca la guardia stessa" if overlap else ""
        print(f"  {c['id']}  {c['enunciato']}")
        print(f"        garantito_da: {c.get('garantito_da')}{marcatore}")


def esito_finale(pipeline_finali, esci_1_se_trasversale):
    if esci_1_se_trasversale and len(pipeline_finali) > 1:
        return 1
    return 0


def modo_file(mappa, valore, esci_1_se_trasversale):
    try:
        file_path, s, e = lib.parse_codice_entry(valore)
    except ValueError as err:
        print(f"ERRORE: {err}", file=sys.stderr)
        return 2

    path_ass = REPO_ROOT / file_path
    if not path_ass.exists():
        print(f"ERRORE: '{file_path}' non esiste nel repo", file=sys.stderr)
        return 2

    if s is None:
        try:
            n_righe = len(path_ass.read_text(encoding="utf-8").splitlines())
        except (UnicodeDecodeError, OSError):
            n_righe = 1
        s, e = 1, max(n_righe, 1)

    punti = [(file_path, s, e)]
    pipeline_finali, condivisi_usati, provenienza = risolvi_punti(mappa, punti)

    if not pipeline_finali and not condivisi_usati:
        print(f"'{file_path}' non è mappato da nessuna scheda — la mappa non lo copre, non significa che sia innocuo.")
        return 0

    stampa_intestazione(pipeline_finali)
    stampa_matches(valore, condivisi_usati, pipeline_finali, provenienza)
    stampa_contratti(contratti_in_gioco(pipeline_finali, condivisi_usati, punti, con_overlap=True))
    return esito_finale(pipeline_finali, esci_1_se_trasversale)


def modo_diff(mappa, esci_1_se_trasversale):
    diff_ranges = ottieni_diff_ranges()
    if not diff_ranges:
        print("Nessuna modifica rilevata (git diff HEAD vuoto).")
        return 0

    punti = [(f, s, e) for f, ranges in diff_ranges.items() for (s, e) in ranges]
    pipeline_finali, condivisi_usati, provenienza = risolvi_punti(mappa, punti)

    stampa_intestazione(pipeline_finali)
    for f, ranges in sorted(diff_ranges.items()):
        etichetta = ", ".join(str(s) if s == e else f"{s}-{e}" for s, e in ranges)
        print(f"{f}:{etichetta}")
    print()
    stampa_matches(None, condivisi_usati, pipeline_finali, provenienza)
    stampa_contratti(contratti_in_gioco(pipeline_finali, condivisi_usati, punti, con_overlap=True))
    return esito_finale(pipeline_finali, esci_1_se_trasversale)


def modo_componente(mappa, nome, esci_1_se_trasversale):
    pipeline_finali = {}
    condivisi_usati = {}
    provenienza = {}

    cond = lib.trova_condiviso(mappa, nome)
    if cond:
        condivisi_usati[cond["nome"]] = cond
        for nome_pl in cond.get("usato_da", []) or []:
            pl = lib.trova_pipeline(mappa, nome_pl)
            if pl:
                pipeline_finali[nome_pl] = pl
                provenienza.setdefault(nome_pl, set()).add(cond["nome"])
    else:
        pl = lib.trova_pipeline(mappa, nome)
        if pl:
            pipeline_finali[pl["nome"]] = pl
        else:
            validi = sorted([c["nome"] for c in mappa.get("condivisi", []) or []] + [p["nome"] for p in mappa.get("pipeline", []) or []])
            print(f"ERRORE: nessun componente condiviso o pipeline chiamato '{nome}'. Validi: {', '.join(validi)}", file=sys.stderr)
            return 2

    stampa_intestazione(pipeline_finali)
    stampa_matches(f"componente: {nome}", condivisi_usati, pipeline_finali, provenienza)
    stampa_contratti(contratti_in_gioco(pipeline_finali, condivisi_usati, [], con_overlap=False))
    return esito_finale(pipeline_finali, esci_1_se_trasversale)


def modo_tabella(mappa, nome, esci_1_se_trasversale):
    tabelle_note = lib.nomi_tabelle_canoniche(SCHEMA_PATH)
    if nome not in tabelle_note:
        print(f"ERRORE: '{nome}' non è una tabella nota. Valide: {', '.join(sorted(tabelle_note))}", file=sys.stderr)
        return 2

    pipeline_finali = {}
    lettori = []
    scrittori = []
    for p in mappa.get("pipeline", []) or []:
        tb = p.get("tabelle") or {}
        legge = nome in (tb.get("legge") or [])
        scrive = nome in (tb.get("scrive") or [])
        if legge or scrive:
            pipeline_finali[p["nome"]] = p
        if legge:
            lettori.append(p["nome"])
        if scrive:
            scrittori.append(p["nome"])

    stampa_intestazione(pipeline_finali)
    print(f"tabella: {nome}")
    if scrittori:
        print(f"  SCRIVONO (rischio per chi legge): {', '.join(sorted(scrittori))}")
    if lettori:
        print(f"  LEGGONO: {', '.join(sorted(lettori))}")
    if not scrittori and not lettori:
        print("  nessuna scheda impattata")
    print()
    stampa_contratti(contratti_in_gioco(pipeline_finali, {}, [], con_overlap=False))
    return esito_finale(pipeline_finali, esci_1_se_trasversale)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    gruppo = parser.add_mutually_exclusive_group(required=True)
    gruppo.add_argument("--file", metavar="PATH[:LINE|:START-END]")
    gruppo.add_argument("--componente", metavar="NOME")
    gruppo.add_argument("--tabella", metavar="NOME")
    gruppo.add_argument("--diff", action="store_true")
    parser.add_argument("--esci-1-se-trasversale", action="store_true")
    args = parser.parse_args()

    try:
        mappa = lib.carica_mappa(MAPPA_PATH)
    except FileNotFoundError:
        print(f"ERRORE: mappa non trovata in {MAPPA_PATH}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERRORE: mappa non parsabile: {e}", file=sys.stderr)
        return 2

    if args.file:
        return modo_file(mappa, args.file, args.esci_1_se_trasversale)
    if args.componente:
        return modo_componente(mappa, args.componente, args.esci_1_se_trasversale)
    if args.tabella:
        return modo_tabella(mappa, args.tabella, args.esci_1_se_trasversale)
    return modo_diff(mappa, args.esci_1_se_trasversale)


if __name__ == "__main__":
    sys.exit(main())
