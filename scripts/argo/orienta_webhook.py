#!/usr/bin/env python3
"""python3 scripts/argo/orienta_webhook.py

Consumer host-side dei job 'genera_orienta', 'genera_instrada', (passo 8)
'genera_avviso', (cantiere Argo — il ponte, passo 1) 'genera_brief' e (passo
2) 'genera_impatto' — nome file invariato apposta: il crontab di Leonardo
lancia già questo script ogni minuto, rinominarlo lo romperebbe in silenzio.
Tutti tranne 'genera_avviso' sono accodati da backend/main.py (POST
/webhook/argo) quando Leonardo scrive /orienta, /instrada, /brief o /impatto
al bot Argo da Telegram; 'genera_avviso' è accodato una volta al giorno da
worker/loop.py:garantisci_genera_avviso() (nessuna riga di crontab nuova).
Lanciato da cron, non da Docker: argo/voce.py passa da argo/stato.py, che
deve girare da host (docker exec + STATO.md + git sul filesystem del repo —
vedi il docstring di argo/stato.py). worker/loop.py esclude esplicitamente
i cinque tipi dal proprio claim_job() per questo motivo.

Ad ogni lancio reclama al più un job pending (il più vecchio dei quattro
tipi, FIFO), stesso idiom atomico di worker/loop.py:claim_job (UPDATE ...
WHERE stato='pending' RETURNING id), ma via `docker exec argo-db-1 psql`
invece di psycopg diretto — stessa convenzione di argo/stato.py, dato che
gira da host come quel modulo. Selezione multi-colonna (id, tipo, payload)
avvolta in json_agg, stesso stile robusto di argo/stato.py:_query_db.

Nessun retry automatico su errore (stesso trade-off già scelto per
classificazione/bozza, vedi STATO.md — DECISIONI APERTE): un fallimento è
terminale per quella richiesta, Leonardo la ripete con un altro comando (per
genera_avviso non c'è nulla da ripetere a mano: la schedulazione lo
riaccoderà da sé, vedi worker/loop.py:garantisci_genera_avviso). Mai un
fallimento silenzioso: un errore avvisa comunque su Telegram.

Invio via connectors.telegram.invia_lungo(), non notifica() diretta: un
brief supera spesso i 4096 caratteri di un singolo messaggio Telegram (gli
altri tre modi restano sempre entro un messaggio, quindi per loro il
comportamento non cambia).

Unico punto che scrive, oltre a `jobs`: per genera_avviso, PRIMA dell'invio
(mai dopo — stesso ordine "scritto prima dell'invio" del resto del repo),
marca in `alert_inviati`/`osservazioni.stato` le voci segnalate
(_marca_avviso_inviato) — così l'avviso non si ripete la sera dopo. Per
genera_impatto, stesso ordine: scrive l'esito sul mandato (_scrivi_esito_mandato)
PRIMA dell'invio — il mandato è già stato registrato da backend/main.py alla
ricezione del comando, qui si scrive solo l'esito. Se il job fallisce in modo
imprevisto (eccezione non gestita da argo/voce.py:genera_impatto), l'esito
viene comunque scritto come 'fallito: errore interno': il mandato non deve
mai restare con esito NULL per un job che ha già finito di girare. Per
genera_brief (passo 3 del ponte), il mandato invece NON esiste già: viene
creato qui (_registra_mandato_brief), PRIMA dell'invio, solo se
argo/voce.py:genera_brief segnala che una consultazione di impatti.py è
avvenuta davvero (log non None) — un brief che non cita nessun file reale
non produce nessun mandato, il silenzio è l'esito normale. argo/voce.py
resta sola lettura (vedi il suo guardrail statico), la scrittura vera vive
qui, che già scrive su `jobs` per lo stesso motivo (gira da host).
"""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.orienta_webhook")

CONTAINER_DB = "argo-db-1"
TIPI_JOB = ("genera_orienta", "genera_instrada", "genera_avviso", "genera_brief", "genera_impatto")


def _psql(sql, timeout=15):
    """Esegue `sql` via docker exec (stessa convenzione di argo/stato.py, non
    riusabile qui: quel modulo è dichiaratamente sola-lettura e non scrive
    mai). Ritorna stdout grezzo, stripped."""
    risultato = subprocess.run(
        ["docker", "exec", CONTAINER_DB, "psql", "-U", "argo", "-d", "argo", "-t", "-A", "-c", sql],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if risultato.returncode != 0:
        raise RuntimeError(f"psql fallito: {risultato.stderr.strip()[:300]}")
    return risultato.stdout.strip()


def _reclama_job():
    """Claim atomico: prima trova il pending più vecchio tra i tre tipi (FIFO),
    poi lo reclama con una UPDATE guardata su stato='pending' — se nel frattempo
    un altro lancio di questo stesso script lo ha già preso, la UPDATE non tocca
    righe e questo lancio esce a mani vuote (nessun doppio invio). Ritorna
    (job_id, tipo, payload) o None."""
    tipi_sql = ",".join(f"'{t}'" for t in TIPI_JOB)
    riga = _psql(
        "SELECT json_agg(t) FROM (SELECT id, tipo, payload FROM jobs "
        f"WHERE tipo IN ({tipi_sql}) AND stato='pending' ORDER BY id LIMIT 1) t"
    )
    if not riga or riga == "null":
        return None
    job = json.loads(riga)[0]
    job_id = job["id"]
    claimato = _psql(
        f"UPDATE jobs SET stato='running', tentativi=tentativi+1 "
        f"WHERE id={job_id} AND stato='pending' RETURNING id"
    )
    if not claimato:
        return None
    return job_id, job["tipo"], job.get("payload") or {}


def _segna_done(job_id):
    _psql(f"UPDATE jobs SET stato='done' WHERE id={job_id}")


def _segna_failed(job_id, errore):
    errore_sql = errore.replace("'", "''")[:500]
    _psql(f"UPDATE jobs SET stato='failed', ultimo_errore='{errore_sql}' WHERE id={job_id}")


def _scrivi_esito_mandato(mandato_id, esito):
    """Scrive PRIMA dell'invio, mai dopo — stesso ordine di
    _marca_avviso_inviato sotto. mandato_id arriva dal payload del job,
    scritto da backend/main.py all'INSERT del mandato (guardrail AV01, mai
    un mandato senza origine_msg — qui si scrive solo l'esito, non
    l'origine)."""
    esito_sql = esito.replace("'", "''")
    _psql(f"UPDATE mandati SET esito='{esito_sql}' WHERE id={int(mandato_id)}")


def _registra_mandato_brief(origine_msg, oggetto, esito):
    """Passo 3 del ponte: un mandato di consultazione per l'eventuale
    interrogazione di impatti.py dentro /brief. A differenza di
    _scrivi_esito_mandato (usato da genera_impatto, dove backend/main.py ha
    già creato il mandato alla ricezione del comando), qui il mandato non
    esiste finché non sappiamo che la consultazione è avvenuta davvero — un
    brief può citare zero file reali, vedi argo/voce.py:_verifica_impatti_brief
    — quindi lo creiamo solo ora, con esito già valorizzato. Un solo mandato
    per invocazione di /brief (non uno per file citato), per non far
    crescere la tabella a ogni file quando un brief ne cita molti. Scritto
    PRIMA dell'invio Telegram, via docker exec psql come il resto di questo
    file (mai visibile a verifica_mappa.py, stessa deviazione già dichiarata
    per alert_inviati/osservazioni/l'esito di /impatto)."""
    origine_sql = origine_msg.replace("'", "''")
    oggetto_sql = oggetto.replace("'", "''")
    esito_sql = esito.replace("'", "''")
    _psql(
        "INSERT INTO mandati (origine_msg, tipo, oggetto, esito) VALUES "
        f"('{origine_sql}', 'consultazione', '{oggetto_sql}', '{esito_sql}')"
    )


def _marca_avviso_inviato(marcatori):
    """Scrive PRIMA dell'invio, mai dopo — chiamata da main() prima di
    notifica(): stesso ordine "scritto prima dell'invio" usato ovunque nel
    repo per evitare doppi invii — stesso trade-off accettato (STATO.md,
    DECISIONI APERTE): se il processo muore fra questa scrittura e
    notifica(), il fatto risulta segnalato ma il messaggio potrebbe non
    essere arrivato, da gestire a mano se capita."""
    for chiave in marcatori.get("alert_chiavi", []):
        chiave_sql = chiave.replace("'", "''")
        _psql(f"INSERT INTO alert_inviati (chiave) VALUES ('{chiave_sql}') ON CONFLICT DO NOTHING")
    for oss_id in marcatori.get("osservazioni_id", []):
        _psql(f"UPDATE osservazioni SET stato='riferita' WHERE id={int(oss_id)} AND stato='nuova'")


ERRORE_RIPETI = {
    "genera_orienta": "riprova con /orienta",
    "genera_instrada": "riprova con /instrada",
    "genera_avviso": "controllo al prossimo giro",
    "genera_brief": "riprova con /brief <nome cantiere>",
    "genera_impatto": "riprova con /impatto <componente o file>",
}


def main():
    reclamato = _reclama_job()
    if reclamato is None:
        return
    job_id, tipo, payload = reclamato

    from argo.voce import genera_risposta, genera_risposta_instrada, genera_avviso, genera_brief, genera_impatto
    from connectors.telegram import invia_lungo

    esito_mandato = None
    log_impatti_brief = None
    try:
        if tipo == "genera_orienta":
            testo, marcatori = genera_risposta(), None
        elif tipo == "genera_instrada":
            testo, marcatori = genera_risposta_instrada(payload["minuti"], payload["contesto"]), None
        elif tipo == "genera_brief":
            testo, log_impatti_brief = genera_brief(payload["nome"])
            marcatori = None
        elif tipo == "genera_impatto":
            testo, esito_mandato = genera_impatto(payload["componente"])
            marcatori = None
        else:
            testo, marcatori = genera_avviso()
    except Exception as e:
        logger.exception("orienta_webhook: job %s (%s) fallito", job_id, tipo)
        _segna_failed(job_id, f"{type(e).__name__}: {e}")
        if tipo == "genera_impatto":
            _scrivi_esito_mandato(payload["mandato_id"], "fallito: errore interno")
        invia_lungo(
            f"Errore nel generare la risposta — {ERRORE_RIPETI[tipo]}.",
            token=os.environ["ARGO_VOCE_BOT_TOKEN"],
        )
        return

    if not testo:
        # Solo genera_avviso può arrivare qui: niente da segnalare stasera,
        # il silenzio è un esito normale (deciso in argo/voce.py, prima di
        # ogni chiamata LLM) — nessun invio, job comunque riuscito.
        _segna_done(job_id)
        return

    if marcatori:
        _marca_avviso_inviato(marcatori)
    if tipo == "genera_impatto":
        _scrivi_esito_mandato(payload["mandato_id"], esito_mandato)
    if tipo == "genera_brief" and log_impatti_brief:
        _registra_mandato_brief(
            payload["origine_msg"], f"brief: {payload['nome']}", log_impatti_brief
        )

    invia_lungo(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])
    _segna_done(job_id)


if __name__ == "__main__":
    main()
