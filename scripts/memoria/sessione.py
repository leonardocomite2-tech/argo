"""Logica pura della memoria di sessione (tabella `sessioni`): nessun accesso
a DB, git o rete — riceve testi e liste, ritorna valori. L'orchestrazione
(stdin dell'hook, git, psql, LLM) sta in scripts/memoria/hook_sessione.py.

Il transcript di Claude Code è un formato interno, non documentato come
contratto (code.claude.com/docs/en/hooks: "written asynchronously"): lo si
legge in modo tollerante, riga per riga, e chi chiama dichiara la copertura
quando non è leggibile invece di fingere.
"""
import json
import re
import secrets

from argo.stato import _normalizza_titolo, chiave_cantiere

STRUMENTI_SCRITTURA = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
FONTE_REGISTRO = "registro"
FONTE_STATO_MD = "stato_md_euristica"
REGISTRO_ATTRITI = "knowledge/registro_attriti.md"
LUNGHEZZA_MINIMA_SEGRETO = 6
SEGNAPOSTO_SEGRETO = "***"
_SEGRETI_NOTI_RE = [
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{10,}"),
    re.compile(r"(?i)bearer\s+[A-Za-z0-9._\-]{16,}"),
]


def leggi_transcript(testo):
    """Righe JSON del transcript. Le righe non JSON sono saltate (il file è
    scritto in modo asincrono, l'ultima può essere a metà). Ritorna None se
    nessuna riga è leggibile: il chiamante ripiega su git e lo dichiara."""
    righe = []
    for riga in (testo or "").splitlines():
        riga = riga.strip()
        if not riga:
            continue
        try:
            d = json.loads(riga)
        except ValueError:
            continue
        if isinstance(d, dict):
            righe.append(d)
    return righe or None


def _relativo(percorso, repo_root):
    percorso = str(percorso or "")
    radice = str(repo_root).rstrip("/") + "/"
    if percorso.startswith(radice):
        return percorso[len(radice):]
    if percorso.startswith("/"):
        return None  # fuori dal repo (piani, scratchpad, memoria): non è un file del progetto
    return percorso or None


def analizza_transcript(righe, repo_root):
    """Estrae dal transcript solo ciò che serve alla riga di sessione:
    - file_scritti: percorsi (relativi al repo) passati a Edit/Write/...;
    - testi_tool: l'input serializzato di OGNI tool usato da Claude — serve
      a riconoscere i file scritti via Bash (heredoc, sed, script python),
      che non passano da Edit/Write;
    - comandi_commit: i comandi Bash che contengono "git commit";
    - primo_timestamp, ultimo_timestamp, ultimo_testo_assistente.
    Le azioni di Leonardo (comandi `!`, che arrivano come <bash-input> nei
    messaggi utente) NON finiscono in testi_tool: sono azioni manuali."""
    file_scritti, testi_tool, comandi_commit = set(), [], []
    primo_timestamp, ultimo_timestamp, ultimo_testo = None, None, ""
    for d in righe:
        if d.get("timestamp"):
            primo_timestamp = primo_timestamp or d["timestamp"]
            ultimo_timestamp = d["timestamp"]
        if d.get("type") != "assistant":
            continue
        contenuto = (d.get("message") or {}).get("content")
        if not isinstance(contenuto, list):
            continue
        for blocco in contenuto:
            if not isinstance(blocco, dict):
                continue
            if blocco.get("type") == "text" and blocco.get("text"):
                ultimo_testo = blocco["text"]
            if blocco.get("type") != "tool_use":
                continue
            ingresso = blocco.get("input") or {}
            testi_tool.append(json.dumps(ingresso, ensure_ascii=False))
            if blocco.get("name") in STRUMENTI_SCRITTURA:
                rel = _relativo(ingresso.get("file_path") or ingresso.get("notebook_path"), repo_root)
                if rel:
                    file_scritti.add(rel)
            comando = ingresso.get("command") if blocco.get("name") == "Bash" else None
            if isinstance(comando, str) and "git commit" in comando:
                comandi_commit.append(comando)
    return {
        "file_scritti": file_scritti,
        "testi_tool": testi_tool,
        "comandi_commit": comandi_commit,
        "primo_timestamp": primo_timestamp,
        "ultimo_timestamp": ultimo_timestamp,
        "ultimo_testo_assistente": ultimo_testo,
    }


def commit_della_sessione(commit_intervallo, comandi_commit):
    """Un commit dell'intervallo appartiene alla sessione solo se il suo
    oggetto compare alla lettera in un `git commit` lanciato da questa
    sessione. L'intervallo da solo non basta: due sessioni parallele (18/9,
    e423d9b e 3beb5b3 a 13 minuti) si attribuirebbero l'una i commit
    dell'altra. `commit_intervallo`: lista di dict {hash, oggetto}."""
    return [c for c in commit_intervallo if c["oggetto"] and any(c["oggetto"] in cmd for cmd in comandi_commit)]


def scritto_da_claude(percorso, file_scritti, testi_tool):
    return percorso in file_scritti or any(percorso in t for t in testi_tool)


def correzioni_manuali(file_diff, file_scritti, testi_tool):
    """File nel diff della sessione che il transcript non mostra scritti da
    Claude — né via Edit/Write né nominati in un comando: li ha toccati
    Leonardo. Lista vuota = nessuna correzione rilevata (diverso da None =
    non rilevabile, deciso da chi chiama quando il transcript manca)."""
    return sorted(f for f in set(file_diff) if not scritto_da_claude(f, file_scritti, testi_tool))


_VOCE_SOSPESO_RE = re.compile(r"^(\d+)\.\s+(.*)$")


def _voci_sospesi(testo_registro):
    """{numero: (testo_prima_riga, risolto)} dalla sezione '## SOSPESI' del
    registro attriti. Formato: '<n>. [RISOLTO gg/mm] testo...'."""
    if not testo_registro:
        return {}
    m = re.search(r"^## SOSPESI\s*$\n(.*?)(?=^## |\Z)", testo_registro, re.MULTILINE | re.DOTALL)
    if not m:
        return {}
    voci = {}
    for riga in m.group(1).splitlines():
        v = _VOCE_SOSPESO_RE.match(riga.strip())
        if v:
            voci[int(v.group(1))] = (v.group(2).strip(), "[RISOLTO" in v.group(2))
    return voci


def sospesi_dal_registro(prima, dopo):
    """Confronto deterministico del registro prima/dopo un commit: aperti =
    voci nuove non risolte; chiusi = voci che passano a [RISOLTO]."""
    v_prima, v_dopo = _voci_sospesi(prima), _voci_sospesi(dopo)
    aperti, chiusi = [], []
    for n, (testo, risolto) in sorted(v_dopo.items()):
        if n not in v_prima and not risolto:
            aperti.append({"testo": f"SOSPESO {n}: {testo}", "fonte": FONTE_REGISTRO})
        elif risolto and n in v_prima and not v_prima[n][1]:
            chiusi.append({"testo": f"SOSPESO {n}: {testo}", "fonte": FONTE_REGISTRO})
    return aperti, chiusi


def sospesi_da_stato_md(righe_aggiunte):
    """Euristica testuale su STATO.md, marcata come tale e mai filtrata:
    righe aggiunte che nominano SOSPESO/DA_VERIFICARE -> aperti, che
    nominano RISOLTO -> chiusi. Meglio una riga incerta ma dichiarata che un
    campo vuoto quando il SOSPESO c'era (decisione di Leonardo, 18/9)."""
    aperti, chiusi = [], []
    for riga in righe_aggiunte:
        testo = riga.strip()
        if not testo:
            continue
        voce = {"testo": testo[:300], "fonte": FONTE_STATO_MD}
        if "RISOLTO" in testo:
            chiusi.append(voce)
        elif "SOSPESO" in testo or "DA_VERIFICARE" in testo:
            aperti.append(voce)
    return aperti, chiusi


def cantieri_della_sessione(righe_stato_aggiunte, oggetti_commit, nomi_cantieri):
    """Deterministico. Prima le righe della tabella CANTIERI modificate dai
    commit della sessione (prima cella = nome esatto), poi i nomi che
    compaiono negli oggetti dei commit (stessa normalizzazione dei titoli di
    STATO.md). Ordine di scoperta, senza doppioni; lista vuota se niente
    corrisponde — mai un cantiere indovinato."""
    trovati = []
    for riga in righe_stato_aggiunte:
        if riga.startswith("|"):
            cella = riga.strip().strip("|").split("|")[0].strip()
            if cella in nomi_cantieri and cella not in trovati:
                trovati.append(cella)
    for oggetto in oggetti_commit:
        normalizzato = _normalizza_titolo(oggetto)
        for nome in nomi_cantieri:
            if nome not in trovati and chiave_cantiere(nome) in normalizzato:
                trovati.append(nome)
    return trovati


def valori_segreti(testo_env):
    """Valori (non nomi) delle variabili in .env, abbastanza lunghi da non
    produrre falsi positivi su parole comuni."""
    valori = []
    for riga in (testo_env or "").splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        valore = riga.partition("=")[2].strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "'\"":
            valore = valore[1:-1]
        if len(valore) >= LUNGHEZZA_MINIMA_SEGRETO:
            valori.append(valore)
    return sorted(set(valori), key=len, reverse=True)


def redigi(valore, segreti):
    """Sostituisce ogni valore segreto (e i formati noti di chiave/token)
    con SEGNAPOSTO_SEGRETO, ricorsivamente dentro liste e dict. Garanzia in
    codice, non solo nel prompt: niente valori nella tabella."""
    if isinstance(valore, str):
        for s in segreti:
            valore = valore.replace(s, SEGNAPOSTO_SEGRETO)
        for regex in _SEGRETI_NOTI_RE:
            valore = regex.sub(SEGNAPOSTO_SEGRETO, valore)
        return valore
    if isinstance(valore, list):
        return [redigi(v, segreti) for v in valore]
    if isinstance(valore, dict):
        return {k: redigi(v, segreti) for k, v in valore.items()}
    return valore


def letterale_sql(testo):
    """Letterale SQL in dollar-quoting con un tag casuale, rigenerato finché
    non compare nel testo: nessun escaping da sbagliare e nessun testo (un
    commit che descrive questo stesso codice, per esempio) che possa far
    fallire la scrittura. Prima il tag era fisso e il suo comparire nel
    testo faceva saltare la riga (review 18/9)."""
    testo = str(testo)
    while True:
        tag = f"$m{secrets.token_hex(6)}$"
        if tag not in testo:
            return f"{tag}{testo}{tag}"

