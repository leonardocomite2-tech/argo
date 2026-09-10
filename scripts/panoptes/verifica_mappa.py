#!/usr/bin/env python3
"""Confronta knowledge/mappa_sistema.yaml col codice reale (grep deterministico, zero LLM).

Verifica solo i campi che il codice può sapere: tabelle.legge/scrive, env,
codice (esistenza+range). Il resto della mappa (produce, evidenza, contratti,
stato...) non è verificabile da qui.

Uso:
    python3 scripts/panoptes/verifica_mappa.py
    python3 scripts/panoptes/verifica_mappa.py --solo risposte_email

Exit: 0 nessuna divergenza, 1 almeno una divergenza reale (gli "indecidibile"
non contano), 2 errore dello script stesso (mappa non parsabile/mancante).
"""
import argparse
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _mappa_lib as lib

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MAPPA_PATH = REPO_ROOT / "knowledge" / "mappa_sistema.yaml"
SCHEMA_PATH = REPO_ROOT / "db" / "schema.sql"

_NOME_ENV_PULITO_RE = re.compile(r"^[A-Z_][A-Z0-9_]*$")


def raccogli_range_per_file(voci):
    """voci: list[(file,start,end)] -> dict file -> None (bare, tutto il file) | list[(s,e)]."""
    per_file = {}
    for f, s, e in voci:
        if s is None:
            per_file[f] = None
            continue
        if f not in per_file:
            per_file[f] = []
        if per_file[f] is not None:
            per_file[f].append((s, e))
    return per_file


def riga_in_scope(per_file, file, riga):
    if file not in per_file:
        return False
    rng = per_file[file]
    if rng is None:
        return True
    return any(s <= riga <= e for s, e in rng)


def verifica_codice_esistenza(voci):
    divergenze = []
    for f, s, e in voci:
        path = REPO_ROOT / f
        if not path.exists():
            divergenze.append(f"[codice] {f} — file non esiste nel repo")
            continue
        if s is None:
            continue
        try:
            n_righe = len(path.read_text(encoding="utf-8").splitlines())
        except (UnicodeDecodeError, OSError):
            continue  # binario o illeggibile come testo, range non verificabile da qui
        if s < 1 or s > e or e > n_righe:
            divergenze.append(f"[codice] {f}:{s}-{e} — range non valido (il file ha {n_righe} righe)")
    return divergenze


def grep_tabelle(per_file, tabelle_note):
    trovato_legge = {}
    trovato_scrive = {}
    indecidibili = []
    for f in sorted(per_file):
        if not f.endswith(".py"):
            continue
        path = REPO_ROOT / f
        if not path.exists():
            continue
        testo = path.read_text(encoding="utf-8")
        for riga, blob in lib.estrai_blocchi_execute(testo):
            if not riga_in_scope(per_file, f, riga):
                continue
            for verbo, tabella, indecidibile, token in lib.estrai_verbo_e_tabella(blob, tabelle_note):
                if indecidibile:
                    indecidibili.append(
                        f"[indecidibile] {f}:{riga} — {verbo}: tabella non determinabile a grep"
                        + (f" ({token!r})" if token else "")
                    )
                    continue
                dest = trovato_legge if verbo == "SELECT" else trovato_scrive
                dest.setdefault(tabella, []).append((f, riga))
    return trovato_legge, trovato_scrive, indecidibili


def grep_env(per_file):
    trovato = {}
    for f in sorted(per_file):
        if not f.endswith(".py"):
            continue
        path = REPO_ROOT / f
        if not path.exists():
            continue
        for i, linea in enumerate(lib.leggi_righe(path, None, None), start=1):
            if not riga_in_scope(per_file, f, i):
                continue
            for nome in lib.estrai_env_da_blob(linea):
                if nome.startswith("PG_"):
                    continue
                trovato.setdefault(nome, []).append((f, i))
    return trovato


def estrai_eccezioni(scheda):
    """Legge il campo opzionale `verifica.indecidibile` di una scheda: dichiarazioni
    esplicite di "so che questo è vero, il grep non ci arriva" con motivo. Ritorna
    (per_campo: dict campo->set(valori), motivi: dict (campo,valore)->motivo)."""
    per_campo = {}
    motivi = {}
    for e in ((scheda.get("verifica") or {}).get("indecidibile") or []):
        campo = e.get("campo")
        valore = e.get("valore")
        per_campo.setdefault(campo, set()).add(valore)
        motivi[(campo, valore)] = (e.get("motivo") or "").strip()
    return per_campo, motivi


def applica_eccezioni(mancanti, campo, eccezioni_campo, motivi):
    """Filtra un insieme 'dichiarato ma non trovato' contro le eccezioni dichiarate
    su quella scheda. Un valore coperto da un'eccezione NON è una divergenza, ma
    resta visibile in output come indecidibile atteso — mai sparisce in silenzio."""
    divergenze = []
    attesi = []
    for valore in sorted(mancanti):
        if valore in eccezioni_campo:
            motivo = motivi.get((campo, valore)) or "(nessun motivo dichiarato in verifica.indecidibile)"
            attesi.append(f"[indecidibile atteso, dichiarato] {campo}: {valore} — {motivo}")
        else:
            divergenze.append(f"[{campo}] dichiarato ma non trovato nel codice: {valore}")
    return divergenze, attesi


def confronta_env(dichiarati, trovati, eccezioni_campo=None, motivi=None):
    """Gestisce anche le dichiarazioni a pattern con '{n}' (es. MAILBOX_{n}_USER/PASS):
    non è un nome pulito confrontabile per uguaglianza, quindi si verifica solo che
    ESISTA almeno una variabile trovata con quel prefisso, senza pretendere di
    ricostruire i suffissi esatti dal testo libero. Ritorna (divergenze, indecidibili_attesi)."""
    eccezioni_campo = eccezioni_campo or set()
    motivi = motivi or {}
    divergenze = []
    dich_puliti = set()
    dich_template = []
    for voce in dichiarati:
        if _NOME_ENV_PULITO_RE.match(voce):
            dich_puliti.add(voce)
        elif "{n}" in voce:
            prefisso = voce.split("{n}")[0]
            dich_template.append((prefisso, voce))
        else:
            divergenze.append(f"[env] dichiarazione non in formato nome pulito, non verificabile automaticamente: {voce!r}")

    trovati_nomi = set(trovati.keys())

    coperti_da_template = set()
    for prefisso, originale in dich_template:
        match = [n for n in trovati_nomi if n.startswith(prefisso) and n[len(prefisso):len(prefisso) + 1].isdigit()]
        if not match:
            divergenze.append(f"[env] dichiarato come pattern ma nessuna variabile trovata con prefisso {prefisso!r}: {originale!r}")
        coperti_da_template.update(match)

    div_env, attesi = applica_eccezioni(dich_puliti - trovati_nomi, "env", eccezioni_campo, motivi)
    divergenze += div_env

    extra = trovati_nomi - dich_puliti - coperti_da_template
    for nome in sorted(extra):
        f, i = trovati[nome][0]
        divergenze.append(f"[env] trovato nel codice ma NON dichiarato: {nome} ({f}:{i})")

    return divergenze, attesi


def verifica_pipeline(pipeline, mappa, tabelle_note):
    divergenze = []
    indecidibili = []
    indecidibili_attesi = []

    eccezioni_campo, motivi = estrai_eccezioni(pipeline)

    voci_proprie = lib.voci_codice(pipeline)
    divergenze += verifica_codice_esistenza(voci_proprie)

    condivisi_usati, mancanti = lib.condivisi_referenziati(pipeline, mappa)
    for nome_mancante in mancanti:
        divergenze.append(f"[condivisi] '{nome_mancante}' referenziato ma non esiste nella sezione condivisi")

    # --- tabelle: scope = proprio codice + codice dei condivisi usati (replicato, per scelta già presa) ---
    voci_tabelle = list(dict.fromkeys(voci_proprie + [v for c in condivisi_usati for v in lib.voci_codice(c)]))
    per_file_tabelle = raccogli_range_per_file(voci_tabelle)
    trovato_legge, trovato_scrive, indec_tabelle = grep_tabelle(per_file_tabelle, tabelle_note)
    indecidibili += indec_tabelle

    dich_legge = set((pipeline.get("tabelle") or {}).get("legge") or [])
    dich_scrive = set((pipeline.get("tabelle") or {}).get("scrive") or [])

    div, att = applica_eccezioni(dich_legge - trovato_legge.keys(), "tabelle.legge", eccezioni_campo.get("tabelle.legge", set()), motivi)
    divergenze += div
    indecidibili_attesi += att
    div, att = applica_eccezioni(dich_scrive - trovato_scrive.keys(), "tabelle.scrive", eccezioni_campo.get("tabelle.scrive", set()), motivi)
    divergenze += div
    indecidibili_attesi += att

    for tabella in sorted(trovato_legge.keys() - dich_legge):
        f, riga = trovato_legge[tabella][0]
        divergenze.append(f"[tabelle.legge] trovato nel codice ma NON dichiarato: {tabella} ({f}:{riga})")
    for tabella in sorted(trovato_scrive.keys() - dich_scrive):
        f, riga = trovato_scrive[tabella][0]
        divergenze.append(f"[tabelle.scrive] trovato nel codice ma NON dichiarato: {tabella} ({f}:{riga})")

    # --- env: scope = SOLO proprio codice, escludendo i range duplicati esatti coi condivisi usati (regola A2) ---
    voci_condivisi_flat = {v for c in condivisi_usati for v in lib.voci_codice(c)}
    voci_env = [v for v in voci_proprie if v not in voci_condivisi_flat]
    per_file_env = raccogli_range_per_file(voci_env)
    trovato_env = grep_env(per_file_env)
    div, att = confronta_env(pipeline.get("env") or [], trovato_env, eccezioni_campo.get("env", set()), motivi)
    divergenze += div
    indecidibili_attesi += att

    return divergenze, indecidibili, indecidibili_attesi


def verifica_condiviso(condiviso, mappa):
    divergenze = []
    eccezioni_campo, motivi = estrai_eccezioni(condiviso)
    voci = lib.voci_codice(condiviso)
    divergenze += verifica_codice_esistenza(voci)
    per_file_env = raccogli_range_per_file(voci)
    trovato_env = grep_env(per_file_env)
    div, att = confronta_env(condiviso.get("env") or [], trovato_env, eccezioni_campo.get("env", set()), motivi)
    divergenze += div
    return divergenze, [], att


def stampa_esito(nome, tipo, divergenze, indecidibili, indecidibili_attesi):
    print(f"=== {nome} ({tipo}) ===")
    if not divergenze and not indecidibili and not indecidibili_attesi:
        print("  OK — tabelle, env, codice combaciano con il codice")
    else:
        for d in divergenze:
            print(f"  {d}")
        for i in indecidibili:
            print(f"  {i}")
        for a in indecidibili_attesi:
            print(f"  {a}")
    print()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--solo", metavar="NOME", help="verifica solo una scheda (pipeline o condiviso)")
    args = parser.parse_args()

    try:
        mappa = lib.carica_mappa(MAPPA_PATH)
    except FileNotFoundError:
        print(f"ERRORE: mappa non trovata in {MAPPA_PATH}", file=sys.stderr)
        return 2
    except yaml.YAMLError as e:
        print(f"ERRORE: mappa non parsabile: {e}", file=sys.stderr)
        return 2

    try:
        tabelle_note = lib.nomi_tabelle_canoniche(SCHEMA_PATH)
    except FileNotFoundError:
        print(f"ERRORE: schema DB non trovato in {SCHEMA_PATH}", file=sys.stderr)
        return 2

    pipeline_list = mappa.get("pipeline", []) or []
    condivisi_list = mappa.get("condivisi", []) or []

    if args.solo:
        pipeline_list = [p for p in pipeline_list if p.get("nome") == args.solo]
        condivisi_list = [c for c in condivisi_list if c.get("nome") == args.solo]
        if not pipeline_list and not condivisi_list:
            print(f"ERRORE: nessuna scheda o componente condiviso chiamato '{args.solo}'", file=sys.stderr)
            return 2

    divergenze_totali = 0
    indecidibili_totali = 0
    indecidibili_attesi_totali = 0
    schede_verificate = 0

    for pipeline in pipeline_list:
        nome = pipeline.get("nome", "?")
        if pipeline.get("sede") == "windows":
            print(f"=== {nome} ===\n  saltata, non verificabile da questo repo (sede: windows)\n")
            continue
        schede_verificate += 1
        divergenze, indecidibili, indecidibili_attesi = verifica_pipeline(pipeline, mappa, tabelle_note)
        stampa_esito(nome, "pipeline", divergenze, indecidibili, indecidibili_attesi)
        divergenze_totali += len(divergenze)
        indecidibili_totali += len(indecidibili)
        indecidibili_attesi_totali += len(indecidibili_attesi)

    for condiviso in condivisi_list:
        nome = condiviso.get("nome", "?")
        schede_verificate += 1
        divergenze, indecidibili, indecidibili_attesi = verifica_condiviso(condiviso, mappa)
        stampa_esito(nome, "condiviso", divergenze, indecidibili, indecidibili_attesi)
        divergenze_totali += len(divergenze)
        indecidibili_totali += len(indecidibili)
        indecidibili_attesi_totali += len(indecidibili_attesi)

    if not args.solo:
        for fr in mappa.get("fuori_repo", []) or []:
            print(f"=== {fr.get('nome', '?')} (fuori_repo) ===\n  saltata, non verificabile da questo repo\n")

    print(
        f"RISULTATO: {divergenze_totali} divergenze su {schede_verificate} schede verificate "
        f"({indecidibili_totali} indecidibili, {indecidibili_attesi_totali} indecidibili attesi/dichiarati "
        f"— nessuno dei due conta come divergenza)"
    )

    return 1 if divergenze_totali > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
