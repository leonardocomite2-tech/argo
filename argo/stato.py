"""Lettori di stato per Argo — la voce.

Sola lettura: nessuna funzione qui dentro scrive mai su una tabella. Ogni
funzione ritorna un dict con almeno {"copertura": ..., "motivo": ...} —
"completa" | "parziale" | "assente" — così chi legge (Argo, o chi collauda
Argo) sa sempre se sta vedendo lo stato vero o una fetta di esso, invece di
fingere copertura totale. Vedi knowledge/argo/IDENTITY.md.

Le funzioni che leggono il DB passano da `docker exec argo-db-1 psql` (non
psycopg diretto): questo modulo è pensato per girare da host, non dentro un
container, per poter leggere anche STATO.md e git nello stesso comando. È
una deviazione dichiarata dalla convenzione "psycopg diretto" del resto del
repo — vedi il piano di sessione in STATO.md.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
STATO_MD_PATH = REPO_ROOT / "STATO.md"

CONTAINER_DB = "argo-db-1"

SOGLIA_CODA_MINUTI = 10
FINESTRA_ESCALATION_ORE = 24

PREFISSI_ALERT = {
    "appr_bloccata": "approvazione bloccata da più di 6h",
    "poster_mancante": "registrazione senza poster da più di 30 minuti",
    "volume": "volume eventi anomalo (>50/ora)",
    "scadenza_vicina": "approvazione DM in scadenza entro 2h",
    "scaduta_auto": "approvazione chiusa automaticamente per scadenza",
    "scaduta": "invio bloccato, la finestra di risposta era già chiusa",
    "imap_ko": "casella IMAP non raggiungibile",
    "avvisa_appr": "approvazione già segnalata dall'avviso serale di Argo",
    "avvisa_job": "job fallito già segnalato dall'avviso serale di Argo",
}

NON_VISIBILI_DA_ALERT_INVIATI = [
    "tetto giornaliero LLM (connectors/llm.py: contatore in-memory nel worker, azzerato ad ogni riavvio)",
    "notifica di job fallito generico (worker/loop.py:124, mai deduplicata né loggata in tabella)",
    "alert ad-hoc di backend/main.py (errore webhook Telegram, codice invalido malformato)",
]


class ErroreQueryDB(Exception):
    pass


def _query_db(sql, timeout=15):
    """Esegue una SELECT sola lettura via `docker exec argo-db-1 psql`,
    avvolta in json_agg per un parsing robusto (niente delimitatori
    fragili su testo libero). Ritorna una lista di dict, [] se zero righe."""
    query_avvolta = f"SELECT json_agg(t) FROM ({sql}) t"
    try:
        risultato = subprocess.run(
            [
                "docker", "exec", CONTAINER_DB,
                "psql", "-U", "argo", "-d", "argo", "-t", "-A",
                "-c", query_avvolta,
            ],
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError:
        raise ErroreQueryDB("comando 'docker' non trovato sull'host")
    except subprocess.TimeoutExpired:
        raise ErroreQueryDB(f"query DB scaduta dopo {timeout}s (container fermo o bloccato?)")

    if risultato.returncode != 0:
        raise ErroreQueryDB(f"psql fallito: {risultato.stderr.strip()[:300]}")

    grezzo = risultato.stdout.strip()
    if not grezzo:
        return []
    try:
        dati = json.loads(grezzo)
    except json.JSONDecodeError as e:
        raise ErroreQueryDB(f"output psql non è JSON valido: {e}")
    return dati or []


def approvazioni_in_attesa():
    """Da `approvals`: cosa aspetta Leonardo, da quanto. Stessa query/JOIN
    di worker/loop.py:_controllo_approvazioni_bloccate."""
    sql = """
        SELECT a.id, a.stato, a.updated_at,
               e.payload->>'mittente' AS mittente,
               e.payload->>'oggetto' AS oggetto,
               EXTRACT(EPOCH FROM (now() - a.updated_at)) / 3600 AS ore_ferma
        FROM approvals a
        JOIN messages m ON m.id = a.message_id
        JOIN events e ON m.thread_id = e.id::text
        WHERE a.stato IN ('in_attesa', 'in_modifica')
        ORDER BY a.updated_at ASC
    """
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        return {"copertura": "assente", "motivo": str(e), "righe": []}

    return {
        "copertura": "completa",
        "motivo": None,
        "righe": righe,
    }


def job_falliti():
    """Da `jobs`: falliti (aggregati per tipo+errore, non riga per riga —
    lo storico può contenere centinaia di righe identiche), fermi (stato
    'running'), in coda da troppo (pending oltre run_after+soglia)."""
    sql_falliti = """
        SELECT tipo, ultimo_errore, count(*) AS quante,
               max(created_at) AS piu_recente, min(created_at) AS piu_vecchia
        FROM jobs
        WHERE stato = 'failed'
        GROUP BY tipo, ultimo_errore
        ORDER BY piu_recente DESC
    """
    sql_fermi = """
        SELECT id, tipo, tentativi, created_at
        FROM jobs
        WHERE stato = 'running'
        ORDER BY created_at ASC
    """
    sql_in_coda = f"""
        SELECT id, tipo, tentativi, run_after, created_at
        FROM jobs
        WHERE stato = 'pending' AND run_after < now() - interval '{SOGLIA_CODA_MINUTI} minutes'
        ORDER BY run_after ASC
    """

    try:
        falliti = _query_db(sql_falliti)
        fermi = _query_db(sql_fermi)
        in_coda = _query_db(sql_in_coda)
    except ErroreQueryDB as e:
        return {
            "copertura": "assente", "motivo": str(e),
            "falliti": [], "fermi": [], "in_coda_da_troppo": [],
        }

    motivo = (
        "la tabella jobs non ha updated_at/started_at, solo created_at: per i job "
        "'running' l'età mostrata è da quando la riga fu creata, non da quando è "
        "stata presa in carico l'ultima volta — buona approssimazione per i job "
        "perenni (ricreati ad ogni giro), meno per un job con più tentativi."
    )
    return {
        "copertura": "parziale",
        "motivo": motivo,
        "soglia_coda_minuti": SOGLIA_CODA_MINUTI,
        "falliti": falliti,
        "fermi": fermi,
        "in_coda_da_troppo": in_coda,
    }


def categoria_da_chiave_alert(chiave):
    prefisso = chiave.split(":", 1)[0]
    return PREFISSI_ALERT.get(prefisso, f"sconosciuto (prefisso '{prefisso}')")


def escalation_aperte():
    """`escalations` non esiste nello schema (né nel codice, né nel DB —
    vedi knowledge/registro_attriti.md:115). La fonte più vicina è
    `alert_inviati`: un log 'inviato una volta', non un registro di
    escalation aperte/chiuse — non ha severità/contenuto/stato risolto, e
    non tutti gli alert ci passano (vedi NON_VISIBILI_DA_ALERT_INVIATI).
    Uso quindi un proxy dichiarato: alert mandati nella finestra recente."""
    sql = f"""
        SELECT chiave, created_at
        FROM alert_inviati
        WHERE created_at > now() - interval '{FINESTRA_ESCALATION_ORE} hours'
        ORDER BY created_at DESC
    """
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        return {
            "copertura": "assente", "motivo": str(e),
            "righe": [], "non_visibili_da_qui": NON_VISIBILI_DA_ALERT_INVIATI,
        }

    for riga in righe:
        riga["categoria"] = categoria_da_chiave_alert(riga["chiave"])

    motivo = (
        "'escalations' non esiste nello schema (confermato in "
        "knowledge/registro_attriti.md:115): questa funzione legge alert_inviati "
        "come proxy — è un log 'partito una volta', senza stato aperto/risolto, e "
        "alcuni alert reali non ci passano mai (vedi 'non_visibili_da_qui'). "
        "Quello che segue è 'alert mandati nelle ultime "
        f"{FINESTRA_ESCALATION_ORE}h', non 'tutto ciò che richiede attenzione ora'."
    )
    return {
        "copertura": "parziale",
        "motivo": motivo,
        "finestra_ore": FINESTRA_ESCALATION_ORE,
        "righe": righe,
        "non_visibili_da_qui": NON_VISIBILI_DA_ALERT_INVIATI,
    }


def osservazioni_nuove():
    """Da `osservazioni` dove stato='nuova'."""
    sql = """
        SELECT id, created_at, fonte, severita, contratto_toccato, testo
        FROM osservazioni
        WHERE stato = 'nuova'
        ORDER BY created_at ASC
    """
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        return {"copertura": "assente", "motivo": str(e), "righe": []}

    motivo = None
    if not righe:
        motivo = (
            "zero righe: oggi nessuna pipeline scrive ancora in osservazioni "
            "(mappa_sistema.yaml, scheda argo_voce, tabelle.scrive è vuoto — "
            "cantiere Panoptes/Argo ancora in fondamenta). Non è un errore di lettura."
        )

    return {"copertura": "completa", "motivo": motivo, "righe": righe}


def job_falliti_recenti(ore=24):
    """Da `jobs`: falliti nelle ultime `ore`, aggregati per (tipo,
    ultimo_errore) come job_falliti(), ma con finestra temporale — quella
    funzione è volutamente all-time per il contesto di orienta/instrada, e
    infatti mostra anche i 109 fallimenti storici di digest_serale del
    27-29/08 (bug thread_id::int, già risolto). Per il modo "avvisa" serve
    "cosa è successo di recente", non lo storico intero — stessa finestra di
    24h già usata da worker/loop.py:digest_serale. Esclude
    'test_approvazione' come fa quel digest (handler di collaudo manuale,
    non traffico reale)."""
    sql = f"""
        SELECT tipo, ultimo_errore, count(*) AS quante, max(created_at) AS piu_recente
        FROM jobs
        WHERE stato = 'failed' AND tipo != 'test_approvazione'
          AND created_at >= now() - interval '{ore} hours'
        GROUP BY tipo, ultimo_errore
        ORDER BY piu_recente DESC
    """
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        return {"copertura": "assente", "motivo": str(e), "righe": []}
    return {"copertura": "completa", "motivo": None, "righe": righe}


def chiavi_alert_con_prefisso(prefisso):
    """Da `alert_inviati`: chiavi che iniziano con `prefisso:`, nessuna
    finestra temporale — usata dal modo "avvisa" per sapere cosa ha già
    segnalato in passato (l'anti-ripetizione è per sempre, non nelle 24h
    come escalation_aperte())."""
    prefisso_sql = prefisso.replace("'", "''")
    sql = f"SELECT chiave FROM alert_inviati WHERE chiave LIKE '{prefisso_sql}:%'"
    try:
        righe = _query_db(sql)
    except ErroreQueryDB as e:
        return {"copertura": "assente", "motivo": str(e), "chiavi": set()}
    return {"copertura": "completa", "motivo": None, "chiavi": {r["chiave"] for r in righe}}


def _estrai_sezione(testo, titolo):
    """Ritorna il corpo grezzo della sezione '## <titolo>' fino al prossimo
    '## ' (o fine file). None se il titolo non compare."""
    pattern = re.compile(
        r"^## " + re.escape(titolo) + r"\s*$\n(.*?)(?=^## |\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(testo)
    if m is None:
        return None
    return m.group(1).strip()


CANTIERI_INTESTAZIONI_ATTESE = ["nome", "stato", "aperto il", "aspetta", "sessione più recente"]
CANTIERI_STATI_VALIDI = {"aperto", "in attesa", "chiuso", "da confermare"}
CANTIERI_ASPETTA_VALIDI = {"leonardo", "il sistema", "terzi", "calendario", "—", "-", "da confermare"}


def _estrai_cantieri(testo):
    """Parsing della tabella markdown '## CANTIERI'. Ritorna (lista, None)
    se il blocco c'è ed è ben formato, (None, motivo) altrimenti — mai una
    lista parziale silenziosa: o il blocco è affidabile per intero, o non lo
    è e si torna al fallback delle sezioni alla lettera (vedi
    cantieri_aperti())."""
    corpo = _estrai_sezione(testo, "CANTIERI")
    if corpo is None:
        return None, "blocco '## CANTIERI' assente"

    righe = [r for r in corpo.splitlines() if r.strip().startswith("|")]
    if len(righe) < 2:
        return None, "blocco '## CANTIERI' presente ma senza una tabella markdown riconoscibile"

    def celle(riga):
        r = riga.strip()
        if r.startswith("|"):
            r = r[1:]
        if r.endswith("|"):
            r = r[:-1]
        return [c.strip() for c in r.split("|")]

    intestazioni = [c.lower() for c in celle(righe[0])]
    if intestazioni != CANTIERI_INTESTAZIONI_ATTESE:
        return None, (
            f"intestazioni della tabella CANTIERI diverse dall'atteso: attese "
            f"{CANTIERI_INTESTAZIONI_ATTESE}, trovate {intestazioni}"
        )

    corpo_righe = righe[1:]
    separatore = celle(corpo_righe[0])
    if all(re.fullmatch(r"[-: ]*", c) for c in separatore):
        corpo_righe = corpo_righe[1:]

    cantieri = []
    for i, riga in enumerate(corpo_righe, start=1):
        valori = celle(riga)
        if len(valori) != len(CANTIERI_INTESTAZIONI_ATTESE):
            return None, (
                f"riga {i} della tabella CANTIERI ha {len(valori)} celle, "
                f"attese {len(CANTIERI_INTESTAZIONI_ATTESE)}: {riga.strip()!r}"
            )
        nome, stato, aperto_il, aspetta, sessione = valori

        if stato.lower() not in CANTIERI_STATI_VALIDI:
            return None, (
                f"riga {i} ('{nome}'): stato '{stato}' fuori dal vocabolario "
                f"{sorted(CANTIERI_STATI_VALIDI)}"
            )
        aspetta_lower = aspetta.lower()
        # Match sul token canonico più lungo che apre la cella (alcuni sono
        # multi-parola, "il sistema"/"da confermare"): un confronto sulla sola
        # prima parola li spezzerebbe. Consente una nota libera dopo, purché
        # separata da spazio o parentesi (es. "Leonardo (decide se riprendere)").
        match = any(
            aspetta_lower == token
            or aspetta_lower.startswith(token + " ")
            or aspetta_lower.startswith(token + "(")
            for token in CANTIERI_ASPETTA_VALIDI
        )
        if not match:
            return None, (
                f"riga {i} ('{nome}'): aspetta '{aspetta}' fuori dal vocabolario "
                f"{sorted(CANTIERI_ASPETTA_VALIDI)}"
            )

        cantieri.append({
            "nome": nome,
            "stato": stato,
            "aperto_il": aperto_il,
            "aspetta": aspetta,
            "sessione_riferimento": sessione,
        })

    return cantieri, None


def _indice_sessioni(testo, n=15):
    righe = testo.splitlines()
    indice = []
    for i, riga in enumerate(righe, start=1):
        if riga.startswith("## "):
            indice.append({"titolo": riga[3:].strip(), "riga": i})
    return indice[-n:]


def _tutte_le_sezioni(testo):
    """Ogni blocco '## <titolo>' del file, dal titolo al prossimo '## ' (o
    fine file), nell'ordine in cui compaiono. A differenza di
    _estrai_sezione (un titolo esatto alla volta) serve a scorrere TUTTI i
    titoli per trovare quelli che riguardano un cantiere, senza conoscerne
    la stringa esatta in anticipo."""
    pattern = re.compile(r"^## (.+?)\s*$\n(.*?)(?=^## |\Z)", re.MULTILINE | re.DOTALL)
    return [
        {"titolo": m.group(1).strip(), "testo": m.group(2).strip()}
        for m in pattern.finditer(testo)
    ]


def chiave_cantiere(nome):
    """Normalizza il nome di un cantiere per confrontarlo coi titoli delle
    sessioni (usata anche da argo/voce.py per la mappa dei documenti di
    knowledge, quindi non privata): toglie un'eventuale nota tra parentesi
    finale (spesso assente nei titoli, es. 'Designer (bonifica
    yourservice-it)' -> 'Designer'), converte trattini/en-dash in spazi (i
    titoli usano spesso un trattino singolo dove la tabella CANTIERI usa
    l'en-dash — visto su 'Panoptes — Mappa' / 'Cantiere Panoptes-Mappa'),
    minuscolo, spazi singoli. Non taglia al primo trattino: 'Argo — la
    voce' e 'Argo — il ponte' devono restare chiavi diverse."""
    nome = re.sub(r"\s*\([^)]*\)\s*$", "", nome).strip()
    nome = re.sub(r"[-—]+", " ", nome)
    return re.sub(r"\s+", " ", nome).strip().lower()


def _normalizza_titolo(titolo):
    titolo = re.sub(r"[-—]+", " ", titolo)
    return re.sub(r"\s+", " ", titolo).strip().lower()


def sessioni_cantiere(nome, n=3):
    """Ultime `n` sezioni '## ' di STATO.md che riguardano `nome` (match per
    sottostringa sulla chiave normalizzata, vedi _chiave_cantiere), corpo
    intero incluso. Zero sezioni trovate è un esito valido, non un errore:
    alcuni cantieri (es. Cantiere 1/2/3, Lead-gen host) non hanno mai avuto
    un'intestazione '## ' dedicata, il contenuto vive altrove nel file."""
    if not STATO_MD_PATH.exists():
        return {
            "copertura": "assente",
            "motivo": (
                f"{STATO_MD_PATH} non trovato — questa funzione va eseguita da host, "
                "nel repo: il file non è copiato nell'immagine Docker."
            ),
            "sezioni": [],
        }

    testo = STATO_MD_PATH.read_text(encoding="utf-8")
    chiave = chiave_cantiere(nome)
    trovate = [
        sezione for sezione in _tutte_le_sezioni(testo)
        if chiave in _normalizza_titolo(sezione["titolo"])
    ]
    return {"copertura": "completa", "motivo": None, "sezioni": trovate[-n:]}


def cantieri_aperti():
    """Parsing di STATO.md. La fonte primaria è il blocco strutturato
    '## CANTIERI' (una riga per cantiere, vocabolario fisso per stato/
    aspetta — vedi _estrai_cantieri): quando è presente e ben formato,
    copertura 'completa'. Se manca o è incoerente, copertura 'parziale' e si
    torna al fallback pre-esistente: le due sezioni scritte con intento di
    stato-corrente ('In corso', 'DECISIONI APERTE — bloccano') esposte alla
    lettera, più un indice grezzo delle sessioni — sempre presenti in
    entrambi i casi, non solo come fallback silenzioso."""
    if not STATO_MD_PATH.exists():
        return {
            "copertura": "assente",
            "motivo": (
                f"{STATO_MD_PATH} non trovato — questa funzione va eseguita da host, "
                "nel repo: il file non è copiato nell'immagine Docker."
            ),
            "cantieri": None,
            "in_corso": None,
            "decisioni_aperte_bloccano": None,
            "sessioni_recenti": [],
        }

    testo = STATO_MD_PATH.read_text(encoding="utf-8")
    in_corso = _estrai_sezione(testo, "In corso")
    decisioni_aperte = _estrai_sezione(testo, "DECISIONI APERTE — bloccano")
    cantieri, motivo_cantieri = _estrai_cantieri(testo)

    if cantieri is not None:
        copertura = "completa"
        motivo = None
    else:
        copertura = "parziale"
        motivo = (
            f"{motivo_cantieri} — nessun blocco strutturato affidabile: espongo "
            "come fallback le due sezioni scritte con intento di stato-corrente "
            "('In corso', 'DECISIONI APERTE — bloccano') più l'indice grezzo delle "
            "sessioni recenti, come prima dell'introduzione del blocco CANTIERI."
        )

    return {
        "copertura": copertura,
        "motivo": motivo,
        "cantieri": cantieri,
        "in_corso": in_corso,
        "decisioni_aperte_bloccano": decisioni_aperte,
        "sessioni_recenti": _indice_sessioni(testo),
    }


def _esegui_git(args, timeout=15):
    return subprocess.run(
        ["git", "-C", str(REPO_ROOT)] + args,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def attivita_git():
    """Cosa si è mosso di recente, cosa è fermo, cosa non è committato."""
    try:
        log = _esegui_git([
            "log", "-n", "20",
            "--date=iso-strict",
            "--format=%H%x1f%ad%x1f%an%x1f%s",
        ])
        status = _esegui_git(["status", "--porcelain"])
    except FileNotFoundError:
        return {
            "copertura": "assente",
            "motivo": "comando 'git' non trovato sull'host",
            "commits_recenti": [], "modifiche_non_committate": [],
            "ultimo_commit_giorni_fa": None,
        }
    except subprocess.TimeoutExpired:
        return {
            "copertura": "assente",
            "motivo": "comando git scaduto per timeout",
            "commits_recenti": [], "modifiche_non_committate": [],
            "ultimo_commit_giorni_fa": None,
        }

    if log.returncode != 0:
        return {
            "copertura": "assente",
            "motivo": f"git log fallito: {log.stderr.strip()[:300]}",
            "commits_recenti": [], "modifiche_non_committate": [],
            "ultimo_commit_giorni_fa": None,
        }

    commits = []
    for riga in log.stdout.strip("\n").split("\n"):
        if not riga:
            continue
        hash_, data, autore, oggetto = riga.split("\x1f", 3)
        commits.append({
            "hash": hash_, "data": data, "autore": autore, "oggetto": oggetto,
        })

    ultimo_commit_giorni_fa = None
    if commits:
        data_ultimo = datetime.fromisoformat(commits[0]["data"])
        ultimo_commit_giorni_fa = (
            datetime.now(timezone.utc) - data_ultimo.astimezone(timezone.utc)
        ).total_seconds() / 86400

    modifiche = []
    if status.returncode == 0:
        for riga in status.stdout.strip("\n").split("\n"):
            if not riga:
                continue
            modifiche.append({"stato": riga[:2].strip(), "path": riga[3:]})

    return {
        "copertura": "completa",
        "motivo": None,
        "commits_recenti": commits,
        "modifiche_non_committate": modifiche,
        "ultimo_commit_giorni_fa": ultimo_commit_giorni_fa,
    }
