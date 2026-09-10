"""Funzioni pure condivise da verifica_mappa.py e impatti.py.

Zero LLM, solo stdlib + PyYAML. Nessuna funzione qui tocca il filesystem
oltre a leggere file di testo — l'orchestrazione (scope, stampa, exit code)
resta negli script chiamanti.
"""
import re
from pathlib import Path

import yaml

LIMITE_BILANCIAMENTO = 20000

_CODICE_RE = re.compile(r"^(?P<path>[^:]+)(?::(?P<start>\d+)(?:-(?P<end>\d+))?)?$")
_CHIAMATA_EXECUTE_RE = re.compile(r"\w+\.execute\s*\(")
_ENV_PATTERNS = [
    re.compile(r"""os\.environ\[\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]\s*\]"""),
    re.compile(r"""os\.environ\.get\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""),
    re.compile(r"""os\.getenv\(\s*['"]([A-Za-z_][A-Za-z0-9_]*)['"]"""),
]
_RIF_GARANTITO_DA_RE = re.compile(r"([\w./]+\.py):(\d+(?:-\d+)?(?:,\d+(?:-\d+)?)*)")
_CREATE_TABLE_RE = re.compile(r"CREATE TABLE(?:\s+IF NOT EXISTS)?\s+(\w+)", re.IGNORECASE)
_ARGOMENTO_VARIABILE_RE = re.compile(r"^\s*[A-Za-z_]\w*\s*(,|$)")


def carica_mappa(path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def trova_pipeline(mappa, nome):
    for p in mappa.get("pipeline", []) or []:
        if p.get("nome") == nome:
            return p
    return None


def trova_condiviso(mappa, nome):
    for c in mappa.get("condivisi", []) or []:
        if c.get("nome") == nome:
            return c
    return None


def parse_codice_entry(voce):
    """'path' -> (path,None,None); 'path:N' -> (path,N,N); 'path:A-B' -> (path,A,B)."""
    m = _CODICE_RE.match(voce.strip())
    if not m:
        raise ValueError(f"formato non riconosciuto: {voce!r}")
    path = m.group("path")
    start = m.group("start")
    if start is None:
        return path, None, None
    start = int(start)
    end = int(m.group("end")) if m.group("end") is not None else start
    return path, start, end


def voci_codice(scheda):
    """Lista di (file,start,end), MAI un dict: lo stesso file può ricorrere con range diversi."""
    return [parse_codice_entry(v) for v in (scheda.get("codice") or [])]


def leggi_righe(percorso, start, end):
    """Righe 1-indexed [start,end] incluse, o tutto il file se start è None."""
    righe = Path(percorso).read_text(encoding="utf-8").splitlines()
    if start is None:
        return righe
    return righe[start - 1:end]


def bilancia_parentesi(testo, indice_apertura):
    """Data la posizione di una '(' ritorna l'indice della ')' corrispondente, -1 se sbilanciata."""
    profondita = 0
    limite = min(len(testo), indice_apertura + LIMITE_BILANCIAMENTO)
    for i in range(indice_apertura, limite):
        c = testo[i]
        if c == "(":
            profondita += 1
        elif c == ")":
            profondita -= 1
            if profondita == 0:
                return i
    return -1


def estrai_blocchi_execute(testo):
    """Trova ogni `qualcosa.execute(...)`, ritorna [(riga_1indexed, blob_concatenato)]."""
    risultati = []
    for m in _CHIAMATA_EXECUTE_RE.finditer(testo):
        apertura = m.end() - 1
        chiusura = bilancia_parentesi(testo, apertura)
        if chiusura == -1:
            continue
        blob = testo[apertura + 1:chiusura]
        blob_concatenato = re.sub(r"\s+", " ", blob)
        riga = testo.count("\n", 0, m.start()) + 1
        risultati.append((riga, blob_concatenato))
    return risultati


def estrai_verbo_e_tabella(blob, tabelle_note):
    """Ritorna una lista di (verbo, tabella_o_None, indecidibile, token_grezzo_o_None).

    Una SELECT con più tabelle (FROM + JOIN) produce più elementi. INSERT/UPDATE/
    DELETE ne producono uno solo. Un blob senza nessuno dei quattro verbi (es. SET
    timezone) ritorna lista vuota: non è rilevante per tabelle.legge/scrive. Un
    blob il cui primo argomento è una variabile nuda (query costruita altrove,
    es. `query = "..."` seguito da `cur.execute(query)`) non ha testo SQL da
    leggere qui: indecidibile esplicito, non un falso negativo silenzioso.
    """
    m_variabile = _ARGOMENTO_VARIABILE_RE.match(blob)
    if m_variabile:
        nome_variabile = blob[:m_variabile.end()].split(",")[0].strip()
        return [("?", None, True, nome_variabile)]

    m = re.search(r"\bINSERT\s+INTO\s+(\w+)", blob, re.IGNORECASE)
    if m:
        token = m.group(1)
        tabella = token.lower() if token.lower() in tabelle_note else None
        return [("INSERT", tabella, tabella is None, token)]

    m = re.search(r"\bUPDATE\s+(\w+)\s+SET\b", blob, re.IGNORECASE)
    if m:
        token = m.group(1)
        tabella = token.lower() if token.lower() in tabelle_note else None
        return [("UPDATE", tabella, tabella is None, token)]

    m = re.search(r"\bDELETE\s+FROM\s+(\w+)", blob, re.IGNORECASE)
    if m:
        token = m.group(1)
        tabella = token.lower() if token.lower() in tabelle_note else None
        return [("DELETE", tabella, tabella is None, token)]

    if re.search(r"\bSELECT\b", blob, re.IGNORECASE):
        if not re.search(r"\bFROM\b", blob, re.IGNORECASE):
            return []  # SELECT senza FROM (es. "SELECT setseed(%s)"): nessuna tabella coinvolta, non indecidibile
        token_trovati = set()
        for mm in re.finditer(r"\bFROM\s+(\w+)", blob, re.IGNORECASE):
            token_trovati.add(mm.group(1))
        for mm in re.finditer(r"\bJOIN\s+(\w+)", blob, re.IGNORECASE):
            token_trovati.add(mm.group(1))
        if not token_trovati:
            return [("SELECT", None, True, None)]
        risultati = []
        for token in sorted(token_trovati):
            tabella = token.lower() if token.lower() in tabelle_note else None
            risultati.append(("SELECT", tabella, tabella is None, token))
        return risultati

    return []


def estrai_env_da_blob(testo):
    """os.environ[...] / os.environ.get(...) / os.getenv(...) -> nomi grezzi trovati."""
    trovati = set()
    for pat in _ENV_PATTERNS:
        for m in pat.finditer(testo):
            trovati.add(m.group(1))
    return trovati


def filtra_env_infrastruttura(env):
    """Rimuove i nomi PG_* (per convenzione appartengono a `infrastruttura`, non a una scheda)."""
    return {e for e in env if not e.startswith("PG_")}


def intervalli_si_sovrappongono(a_start, a_end, b_start, b_end):
    return a_start <= b_end and b_start <= a_end


def estrai_riferimenti_garantito_da(testo):
    """Estrae tutte le tuple (file,start,end) da un testo libero di garantito_da.

    Gestisce anche la forma comma-separata "file.py:186-193,246-253,294-301"
    (PH04): senza gestirla esplicitamente un finditer naive cattura solo il
    primo range e perde gli altri.
    """
    risultati = []
    for m in _RIF_GARANTITO_DA_RE.finditer(testo or ""):
        file = m.group(1)
        for pezzo in m.group(2).split(","):
            if "-" in pezzo:
                s, e = pezzo.split("-")
                risultati.append((file, int(s), int(e)))
            else:
                n = int(pezzo)
                risultati.append((file, n, n))
    return risultati


def nomi_tabelle_canoniche(schema_sql_path):
    """Nomi tabella da db/schema.sql (CREATE TABLE [IF NOT EXISTS] nome) — non hardcoded."""
    testo = Path(schema_sql_path).read_text(encoding="utf-8")
    return {m.group(1).lower() for m in _CREATE_TABLE_RE.finditer(testo)}


def condivisi_referenziati(pipeline, mappa):
    """Risolve i nomi in pipeline['condivisi'] nelle voci top-level condivisi:.

    Ritorna (risolti, mancanti): un nome che non esiste in condivisi: è un
    errore di mappa, va segnalato dal chiamante, mai silenziato.
    """
    risolti = []
    mancanti = []
    for nome in pipeline.get("condivisi", []) or []:
        cond = trova_condiviso(mappa, nome)
        if cond is None:
            mancanti.append(nome)
        else:
            risolti.append(cond)
    return risolti, mancanti


def _entry_tocca(scheda, file, start, end):
    for f, s, e in voci_codice(scheda):
        if f != file:
            continue
        if s is None:
            return True
        if start is None:
            return True
        if intervalli_si_sovrappongono(start, end, s, e):
            return True
    return False


def schede_che_toccano(mappa, file, start, end):
    """Voci codice (pipeline dirette + condivisi) che referenziano file[/range].

    start=end=None -> query sull'intero file: matcha qualunque voce per quel
    file, indipendentemente dal suo range dichiarato. Una voce con range
    dichiarato NULLO (bare path) matcha sempre, qualunque sia la query.
    Ritorna (pipeline_match, condiviso_match), entrambe liste di dict.
    """
    pipeline_match = [p for p in mappa.get("pipeline", []) or [] if _entry_tocca(p, file, start, end)]
    condiviso_match = [c for c in mappa.get("condivisi", []) or [] if _entry_tocca(c, file, start, end)]
    return pipeline_match, condiviso_match
