#!/usr/bin/env python3
"""Hook di Claude Code per la memoria di sessione (tabella `sessioni`).

    python3 scripts/memoria/hook_sessione.py inizio   # hook SessionStart
    python3 scripts/memoria/hook_sessione.py fine     # hook SessionEnd

Configurato in .claude/settings.json. Riceve su stdin il JSON dell'hook
(session_id, transcript_path, cwd, reason/source — code.claude.com/docs/en/hooks).
SessionEnd ha un budget di 1,5 s alzato dal `timeout` dell'hook (max 60 s) e
non può bloccare la chiusura: per questo la scrittura è in DUE FASI.

1. Riga deterministica (git, transcript, STATO.md, registro attriti),
   scritta con un UPSERT sulla dedup_key PRIMA di qualunque chiamata LLM:
   la memoria non dipende da un LLM raggiungibile (contratto SE01 della
   mappa). Rilanciare l'hook aggiorna la stessa riga, non ne crea un'altra.
2. UNA chiamata LLM per le due righe su cosa si è deciso, solo se la riga
   non ha ancora un riassunto (o se i commit sono cambiati, es. dopo un
   resume). Fallita o interrotta: la riga resta, con decisioni_stato che
   dice perché manca il riassunto.

Gira da host (come orienta_webhook.py): DB via docker exec psql
(connectors/psql_host.py), tetto LLM sul contatore persistente. Esce sempre
0 e non stampa niente: un errore qui non deve disturbare la chiusura della
sessione — finisce, per categoria, in sessioni_hook.log.
"""
import json
import logging
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import sessione as S  # noqa: E402
from connectors.psql_host import incrementa_chiamate_llm, psql  # noqa: E402

LOG_PATH = REPO_ROOT / "sessioni_hook.log"
MARGINE_INTERVALLO_SEC = 120
MAX_COMMIT_ESAMINATI = 200
LIMITE_RIGHE_STATO_CARATTERI = 4000
LIMITE_TESTO_ASSISTENTE_CARATTERI = 2000
MAX_TOKENS_DECISIONI = 200

logger = logging.getLogger("argo.memoria")

ISTRUZIONI_DECISIONI = """
Riassumi in DUE righe al massimo cosa si è DECISO in questa sessione di
lavoro su un repository (scelte fatte, cosa si è stabilito di fare o di non
fare), a partire dai dati qui sotto: messaggi dei commit, righe aggiunte a
STATO.md, ultimo messaggio dell'assistente.
Regole:
- Solo fatti presenti nei dati, mai ricostruiti. Se i dati non mostrano
  nessuna decisione, scrivi esattamente: "Nessuna decisione registrata."
- MAI riportare valori di variabili d'ambiente, password, token, chiavi o
  segreti di qualunque tipo, nemmeno in parte: i NOMI delle variabili sì, i
  VALORI mai.
- Testo semplice in italiano, niente markdown, niente elenchi.
""".strip()


def _git(*args):
    r = subprocess.run(["git", "-C", str(REPO_ROOT), *args], capture_output=True, text=True, timeout=15)
    if r.returncode != 0:
        raise RuntimeError(f"git {args[0]} fallito")
    return r.stdout


_dollaro = S.letterale_sql


def _riga_esistente(dedup_key):
    grezzo = psql(
        "SELECT json_build_object('inizio_epoch', extract(epoch from inizio), "
        "'head_iniziale', head_iniziale, "
        "'completa', fine IS NOT NULL AND copertura NOT LIKE 'errore raccolta%') "
        "FROM sessioni WHERE dedup_key = "
        f"{_dollaro(dedup_key)}"
    )
    return json.loads(grezzo) if grezzo else {}


def inizio(dati):
    """SessionStart: registra inizio e HEAD di partenza. ON CONFLICT DO
    NOTHING: un resume non sposta l'inizio della sessione."""
    dedup_key = f"claude-session:{dati['session_id']}"
    head = _git("rev-parse", "HEAD").strip()
    psql(
        "INSERT INTO sessioni (dedup_key, session_id, inizio, head_iniziale) VALUES ("
        f"{_dollaro(dedup_key)}, {_dollaro(dati['session_id'])}, now(), {_dollaro(head)}"
        ") ON CONFLICT (dedup_key) DO NOTHING"
    )


def _epoch(iso):
    return datetime.fromisoformat(iso.replace("Z", "+00:00")).timestamp()


def _commit_intervallo(inizio_epoch):
    """Commit con data >= inizio (meno un margine), dal più vecchio."""
    grezzo = _git("log", "-n", str(MAX_COMMIT_ESAMINATI), "--format=%H%x1f%ct%x1f%s")
    commit = []
    for riga in grezzo.splitlines():
        h, ct, oggetto = riga.split("\x1f", 2)
        if int(ct) >= inizio_epoch - MARGINE_INTERVALLO_SEC:
            commit.append({"hash": h, "oggetto": oggetto})
    return list(reversed(commit))


def _file_del_commit(h):
    return [f for f in _git("show", "--format=", "--name-only", h).splitlines() if f]


def _righe_aggiunte(h, percorso):
    diff = _git("show", "--format=", "--unified=0", h, "--", percorso)
    return [r[1:] for r in diff.splitlines() if r.startswith("+") and not r.startswith("+++")]


def _file_a(h, percorso):
    try:
        return _git("show", f"{h}:{percorso}")
    except RuntimeError:
        return ""


def raccogli(dati, esistente):
    """Fase 1, tutta deterministica. Ritorna il dict della riga."""
    segreti = S.valori_segreti((REPO_ROOT / ".env").read_text(encoding="utf-8") if (REPO_ROOT / ".env").exists() else "")

    try:
        righe = S.leggi_transcript(Path(dati.get("transcript_path") or "").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        righe = None
    analisi = S.analizza_transcript(righe, REPO_ROOT) if righe else None

    inizio_epoch = esistente.get("inizio_epoch")
    if inizio_epoch is None and analisi and analisi["primo_timestamp"]:
        inizio_epoch = _epoch(analisi["primo_timestamp"])
    # Fine = ultimo evento del transcript, non l'ora in cui gira l'hook: in
    # uso reale coincidono, ma un hook rilanciato a mano su una sessione
    # vecchia la farebbe sembrare parallela a quelle di oggi (collaudo 18/9).
    # Senza transcript: NULL, e l'SQL usa now().
    fine_epoch = _epoch(analisi["ultimo_timestamp"]) if analisi and analisi["ultimo_timestamp"] else None

    commit_intervallo = _commit_intervallo(inizio_epoch) if inizio_epoch is not None else []
    if analisi:
        copertura = "transcript"
        commit = S.commit_della_sessione(commit_intervallo, analisi["comandi_commit"])
    elif inizio_epoch is not None:
        # Senza transcript l'intervallo è tutto quello che c'è: può includere
        # commit di una sessione parallela, ed è dichiarato così.
        copertura = "intervallo_git"
        commit = commit_intervallo
    else:
        copertura = "nessuna"
        commit = []

    file_diff = sorted({f for c in commit for f in _file_del_commit(c["hash"])})
    if analisi:
        file_toccati = sorted(set(file_diff) | analisi["file_scritti"])
        correzioni = S.correzioni_manuali(file_diff, analisi["file_scritti"], analisi["testi_tool"])
    else:
        file_toccati = file_diff
        correzioni = None  # non rilevabile, non "zero"

    righe_stato, sosp_aperti, sosp_chiusi = [], [], []
    stato_per_commit = []
    for c in commit:
        file_c = _file_del_commit(c["hash"])
        if "STATO.md" in file_c:
            aggiunte = _righe_aggiunte(c["hash"], "STATO.md")
            righe_stato += aggiunte
            stato_per_commit.append("\n".join(aggiunte))
        if S.REGISTRO_ATTRITI in file_c:
            a, ch = S.sospesi_dal_registro(_file_a(f"{c['hash']}^", S.REGISTRO_ATTRITI), _file_a(c["hash"], S.REGISTRO_ATTRITI))
            sosp_aperti += a
            sosp_chiusi += ch
    a, ch = S.sospesi_da_stato_md(righe_stato)
    sosp_aperti += a
    sosp_chiusi += ch

    from argo.stato import cantieri_aperti
    tabella = cantieri_aperti().get("cantieri") or []
    cantieri = S.cantieri_della_sessione(righe_stato, [c["oggetto"] for c in commit], [t["nome"] for t in tabella])

    for c in commit:
        c["messaggio"] = _git("log", "-1", "--format=%B", c["hash"]).strip()

    riga = {
        "dedup_key": f"claude-session:{dati['session_id']}",
        "session_id": dati["session_id"],
        "inizio_epoch": inizio_epoch,
        "fine_epoch": fine_epoch,
        "head_finale": _git("rev-parse", "HEAD").strip(),
        "motivo_fine": dati.get("reason"),
        "copertura": copertura,
        "cantieri": cantieri or None,
        "file_toccati": file_toccati,
        "commit": [{"hash": c["hash"][:12], "oggetto": c["oggetto"]} for c in commit],
        "correzioni_manuali": correzioni,
        "sospesi_aperti": sosp_aperti,
        "sospesi_chiusi": sosp_chiusi,
    }
    materiale = {
        "commit": [c["messaggio"] for c in commit],
        # Budget diviso in parti uguali fra i commit: troncato dall'inizio,
        # il primo commit riempiva tutto e il riassunto ignorava l'ultimo
        # (collaudo 18/9: "questioni aperte" già chiuse dal commit dopo).
        "righe_stato_md": [t[:LIMITE_RIGHE_STATO_CARATTERI // max(len(stato_per_commit), 1)] for t in stato_per_commit],
        "ultimo_messaggio_assistente": (analisi or {}).get("ultimo_testo_assistente", "")[-LIMITE_TESTO_ASSISTENTE_CARATTERI:],
    }
    return S.redigi(riga, segreti), S.redigi(materiale, segreti), segreti


def scrivi_riga(riga):
    """UPSERT sulla dedup_key: un secondo lancio aggiorna, non duplica. Il
    riassunto si azzera solo se l'elenco dei commit è cambiato (resume con
    lavoro nuovo), altrimenti resta quello già scritto. Ritorna True se la
    riga ha bisogno del riassunto."""
    j = _dollaro(json.dumps(riga, ensure_ascii=False))
    sql = f"""
WITH j AS (SELECT {j}::jsonb AS d),
v AS (
  SELECT d->>'dedup_key' AS dedup_key, d->>'session_id' AS session_id,
         CASE WHEN d->'inizio_epoch' = 'null'::jsonb THEN NULL
              ELSE to_timestamp((d->>'inizio_epoch')::double precision) END AS inizio,
         CASE WHEN d->'fine_epoch' = 'null'::jsonb THEN now()
              ELSE to_timestamp((d->>'fine_epoch')::double precision) END AS fine,
         d->>'head_finale' AS head_finale, d->>'motivo_fine' AS motivo_fine,
         d->>'copertura' AS copertura,
         CASE WHEN d->'cantieri' = 'null'::jsonb THEN NULL
              ELSE ARRAY(SELECT jsonb_array_elements_text(d->'cantieri')) END AS cantieri,
         CASE WHEN d->'file_toccati' = 'null'::jsonb THEN NULL
              ELSE ARRAY(SELECT jsonb_array_elements_text(d->'file_toccati')) END AS file_toccati,
         NULLIF(d->'commit', 'null'::jsonb) AS commit,
         CASE WHEN d->'correzioni_manuali' = 'null'::jsonb THEN NULL
              ELSE ARRAY(SELECT jsonb_array_elements_text(d->'correzioni_manuali')) END AS correzioni_manuali,
         NULLIF(d->'sospesi_aperti', 'null'::jsonb) AS sospesi_aperti,
         NULLIF(d->'sospesi_chiusi', 'null'::jsonb) AS sospesi_chiusi
  FROM j
)
INSERT INTO sessioni AS s (dedup_key, session_id, inizio, fine, head_finale, motivo_fine, copertura,
  cantieri, file_toccati, commit, correzioni_manuali, sospesi_aperti, sospesi_chiusi, sessioni_parallele)
SELECT v.dedup_key, v.session_id, v.inizio, v.fine, v.head_finale, v.motivo_fine, v.copertura,
  v.cantieri, v.file_toccati, v.commit, v.correzioni_manuali, v.sospesi_aperti, v.sospesi_chiusi,
  ARRAY(SELECT o.session_id FROM sessioni o
        WHERE o.dedup_key <> v.dedup_key AND o.inizio IS NOT NULL AND v.inizio IS NOT NULL
          AND o.inizio < v.fine AND COALESCE(o.fine, now()) > v.inizio ORDER BY o.inizio)
FROM v
ON CONFLICT (dedup_key) DO UPDATE SET
  inizio = COALESCE(s.inizio, EXCLUDED.inizio),
  fine = EXCLUDED.fine, head_finale = EXCLUDED.head_finale, motivo_fine = EXCLUDED.motivo_fine,
  copertura = EXCLUDED.copertura, cantieri = EXCLUDED.cantieri, file_toccati = EXCLUDED.file_toccati,
  commit = EXCLUDED.commit, correzioni_manuali = EXCLUDED.correzioni_manuali,
  sospesi_aperti = EXCLUDED.sospesi_aperti, sospesi_chiusi = EXCLUDED.sospesi_chiusi,
  sessioni_parallele = EXCLUDED.sessioni_parallele,
  decisioni = CASE WHEN s.commit IS DISTINCT FROM EXCLUDED.commit THEN NULL ELSE s.decisioni END,
  decisioni_stato = CASE WHEN s.commit IS DISTINCT FROM EXCLUDED.commit THEN NULL ELSE s.decisioni_stato END
RETURNING (decisioni IS NULL);

-- La sovrapposizione è simmetrica: una sessione chiusa prima di questa non
-- poteva saperlo. Per ogni altra riga che la nomina o che lei nomina:
-- togli questa sessione e rimettila solo se la sovrapposizione vale ancora.
-- Idempotente.
UPDATE sessioni o SET sessioni_parallele = ARRAY(
    SELECT DISTINCT x FROM unnest(
        array_remove(COALESCE(o.sessioni_parallele, '{{}}'), s.session_id)
        || CASE WHEN o.session_id = ANY(s.sessioni_parallele) THEN ARRAY[s.session_id] ELSE '{{}}'::text[] END
    ) x ORDER BY x)
FROM sessioni s
WHERE s.dedup_key = {_dollaro(riga["dedup_key"])} AND o.dedup_key <> s.dedup_key
  AND (o.session_id = ANY(s.sessioni_parallele) OR s.session_id = ANY(o.sessioni_parallele));
"""
    return psql(sql).splitlines()[0] == "t"


def scrivi_decisioni(dedup_key, materiale, segreti):
    """Fase 2: una sola chiamata LLM. Qualunque fallimento lascia la riga
    com'è, con decisioni_stato che dice perché il riassunto manca."""
    from connectors.llm import LLMErrore, TettoLLMRaggiunto, carica_env, chiama, usa_contatore_persistente

    decisioni, stato = None, None
    if not (materiale["commit"] or materiale["righe_stato_md"] or materiale["ultimo_messaggio_assistente"]):
        stato = "nessun materiale da riassumere"
    else:
        try:
            carica_env()
            usa_contatore_persistente(incrementa_chiamate_llm, "riassunti di sessione sospesi")
            testo = chiama(ISTRUZIONI_DECISIONI, json.dumps(materiale, ensure_ascii=False),
                           max_tokens=MAX_TOKENS_DECISIONI, temperature=0.0)
            decisioni, stato = S.redigi(testo.strip(), segreti) or None, "ok"
        except TettoLLMRaggiunto:
            stato = "llm non disponibile: tetto giornaliero"
        except LLMErrore:
            stato = "llm non disponibile: chiamata fallita"
        except Exception as e:
            stato = f"llm non disponibile: {type(e).__name__}"
    decisioni_sql = "NULL" if decisioni is None else _dollaro(decisioni)
    psql(
        f"UPDATE sessioni SET decisioni = {decisioni_sql}, decisioni_stato = {_dollaro(stato)} "
        f"WHERE dedup_key = {_dollaro(dedup_key)} AND decisioni IS NULL"
    )
    return stato


def _riga_minima(dati, errore):
    """Quando la raccolta deterministica fallisce (git bloccato, STATO.md
    illeggibile, ...) la sessione lascia comunque una riga: chiusa, con la
    categoria dell'errore in `copertura` e ogni campo derivato non
    rilevabile (NULL), mai vuoto — "non rilevabile" non è "zero"."""
    return {
        "dedup_key": f"claude-session:{dati['session_id']}",
        "session_id": dati["session_id"],
        "inizio_epoch": None,
        "fine_epoch": None,
        "head_finale": None,
        "motivo_fine": dati.get("reason"),
        "copertura": f"errore raccolta: {type(errore).__name__}",
        "cantieri": None,
        "file_toccati": None,
        "commit": None,
        "correzioni_manuali": None,
        "sospesi_aperti": None,
        "sospesi_chiusi": None,
    }


def fine(dati):
    dedup_key = f"claude-session:{dati['session_id']}"
    esistente = _riga_esistente(dedup_key)
    try:
        riga, materiale, segreti = raccogli(dati, esistente)
    except Exception as e:
        if esistente.get("completa"):
            # Un lancio precedente ha già scritto la riga completa: non la
            # si sovrascrive con una riga minima peggiore.
            logger.error("sessione %s: raccolta fallita (%s), riga completa già presente, lasciata com'è",
                         dati["session_id"], type(e).__name__)
            return
        logger.error("sessione %s: raccolta fallita (%s), scrivo la riga minima", dati["session_id"], type(e).__name__)
        riga, materiale, segreti = _riga_minima(dati, e), None, []
    if scrivi_riga(riga) and materiale is not None:
        stato = scrivi_decisioni(dedup_key, materiale, segreti)
        logger.info("sessione %s: riga scritta (%s), riassunto: %s", dati["session_id"], riga["copertura"], stato)
    else:
        logger.info("sessione %s: riga scritta o aggiornata (%s), nessuna chiamata LLM", dati["session_id"], riga["copertura"])


def main(argv):
    logging.basicConfig(filename=str(LOG_PATH), level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s %(message)s")
    fase = argv[1] if len(argv) > 1 else ""
    try:
        dati = json.loads(sys.stdin.read() or "{}")
        if not dati.get("session_id"):
            logger.error("hook %s: stdin senza session_id, niente da scrivere", fase)
            return 0
        if fase == "inizio":
            inizio(dati)
        elif fase == "fine":
            fine(dati)
        else:
            logger.error("hook: fase sconosciuta %r (attese: inizio, fine)", fase)
    except Exception as e:
        # Solo la categoria: mai il messaggio grezzo, che potrebbe contenere
        # frammenti di SQL con testo della sessione.
        logger.error("hook %s fallito: %s", fase, type(e).__name__)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
