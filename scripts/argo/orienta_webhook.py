#!/usr/bin/env python3
"""python3 scripts/argo/orienta_webhook.py

Consumer host-side dei job 'genera_orienta', 'genera_instrada', (passo 8)
'genera_avviso', (cantiere Argo — il ponte, passo 1) 'genera_brief' e (passo
2) 'genera_impatto' — nome file invariato apposta: il crontab di Leonardo
lancia già questo script (ogni 15 secondi dal passo 11 della voce: quattro righe
sfalsate con sleep), rinominarlo lo romperebbe in silenzio.
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

Passo 4 del ponte, 'genera_conversazione' (messaggio libero al bot Argo,
accodato da backend/main.py:_accoda_conversazione): PRIMA dell'invio scrive
l'eventuale mandato di CONSULTAZIONE (_registra_mandato_conversazione, mai
di esecuzione) e la risposta di Argo nella finestra conversazione_argo
(_registra_risposta_conversazione). Il tetto LLM non arriva qui come
eccezione: argo/voce.py:genera_conversazione lo trasforma in un testo che lo
dice, mandato come qualunque risposta.

Passo 9 della voce: un genera_conversazione passa prima dal classificatore
(_instrada_messaggio_libero). Se il modo è orienta/instrada/brief/impatto,
`tipo` e `payload` diventano quelli del comando corrispondente e il ramo
esistente lo esegue identico (per impatto il mandato è registrato qui prima,
come fa backend/main.py per /impatto); se manca un parametro o il modo non è
chiaro, la risposta è una riga fissa senza altre chiamate LLM. In ogni caso
la risposta entra nella finestra conversazione_argo.

Passo 14 della voce, USER.md che si popola (logica in argo/impara.py, senza
LLM): (1) PRIMA del classificatore, se la riga subito precedente il
messaggio è una proposta (ruolo 'argo_proposta') e il messaggio è
esattamente "sì" o "no", la risposta è decisa qui: col sì la riga proposta
entra in USER.md (_scrivi_user_md, l'unico punto che scrive quel file), col
no resta fuori; ogni altro messaggio lascia decadere la proposta e va al
classificatore come sempre. (2) Dopo la risposta a un messaggio libero,
_forse_proponi può mandare una proposta (al massimo una al giorno), scritta
in conversazione_argo PRIMA dell'invio. (3) Un messaggio libero classificato
come instrada lascia minuti e contesto nel payload del suo job
(_registra_finestra): è il dato da cui si calcolano le finestre.
"""

import json
import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env, usa_contatore_persistente  # noqa: E402
from connectors.psql_host import incrementa_chiamate_llm  # noqa: E402

carica_env()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.orienta_webhook")

CONTAINER_DB = "argo-db-1"
TIPI_JOB = (
    "genera_orienta", "genera_instrada", "genera_avviso", "genera_brief", "genera_impatto",
    "genera_conversazione",
)


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
    """Claim atomico: prima trova il pending più vecchio tra i tipi di
    TIPI_JOB il cui run_after è già passato (FIFO) — senza quella condizione
    (mancava fino al 18/9/2026) il genera_avviso programmato per le 22:15
    veniva reclamato un minuto dopo la sua creazione, ~1.400 volte al giorno,
    e il digest serale non partiva mai davvero alle 22:15. I job accodati da
    backend/main.py hanno run_after = now() (default di jobs), quindi per i
    comandi e la conversazione non cambia nulla. Poi lo reclama con una
    UPDATE guardata su stato='pending' — se nel frattempo
    un altro lancio di questo stesso script lo ha già preso, la UPDATE non tocca
    righe e questo lancio esce a mani vuote (nessun doppio invio). Ritorna
    (job_id, tipo, payload) o None."""
    tipi_sql = ",".join(f"'{t}'" for t in TIPI_JOB)
    riga = _psql(
        "SELECT json_agg(t) FROM (SELECT id, tipo, payload FROM jobs "
        f"WHERE tipo IN ({tipi_sql}) AND stato='pending' AND run_after <= now() "
        "ORDER BY id LIMIT 1) t"
    )
    if not riga or riga == "null":
        return None
    job = json.loads(riga)[0]
    job_id = job["id"]
    claimato = _psql(
        f"UPDATE jobs SET stato='running', tentativi=tentativi+1 "
        f"WHERE id={job_id} AND stato='pending' RETURNING id"
    )
    # psql -t -A stampa anche il tag del comando: 0 righe = "UPDATE 0", non
    # stringa vuota. Fino al 18/9/2026 il controllo era `if not claimato`,
    # sempre falso: due lanci sovrapposti avrebbero elaborato lo stesso job.
    # Il claim vale solo se la prima riga è l'id restituito da RETURNING.
    if claimato.splitlines()[:1] != [str(job_id)]:
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


def _registra_mandato_conversazione(origine_msg, oggetto, esito):
    """Passo 4 del ponte: un mandato di CONSULTAZIONE per la consultazione
    eseguita dal ramo conversazionale (al più una per messaggio). tipo è
    scritto qui in chiaro, mai preso dal payload o dall'LLM: da una
    conversazione non nasce mai un mandato di esecuzione. origine_msg è il
    messaggio Telegram di Leonardo (backend/main.py lo mette nel payload).
    Scritto PRIMA dell'invio, via docker exec psql come il resto del file."""
    origine_sql = origine_msg.replace("'", "''")
    oggetto_sql = oggetto.replace("'", "''")
    esito_sql = esito.replace("'", "''")
    _psql(
        "INSERT INTO mandati (origine_msg, tipo, oggetto, esito) VALUES "
        f"('{origine_sql}', 'consultazione', '{oggetto_sql}', '{esito_sql}')"
    )


def _registra_mandato_impatto(origine_msg, componente):
    """Passo 9 della voce: /impatto raggiunto da un messaggio libero. Stesso
    mandato che backend/main.py registra per il comando /impatto (tipo
    'consultazione' in chiaro, origine_msg = messaggio di Leonardo), ma qui:
    il componente si conosce solo dopo il classificatore. Registrato PRIMA
    di eseguire impatti.py; l'esito lo scrive poi il ramo genera_impatto
    esistente (_scrivi_esito_mandato). Ritorna l'id del mandato."""
    origine_sql = origine_msg.replace("'", "''")
    oggetto_sql = f"impatto: {componente}".replace("'", "''")
    risultato = _psql(
        "INSERT INTO mandati (origine_msg, tipo, oggetto) VALUES "
        f"('{origine_sql}', 'consultazione', '{oggetto_sql}') RETURNING id"
    )
    return int(risultato.splitlines()[0])


def _instrada_messaggio_libero(payload):
    """Passo 9 della voce: il classificatore sceglie il modo di un messaggio
    libero. Ritorna (tipo, payload, testo_diretto): tipo/payload sono quelli
    del job del modo scelto — il ramo esistente lo esegue identico —, oppure
    testo_diretto è la riga da mandare così com'è (parametro mancante, modo
    non chiaro, tetto LLM) senza altre chiamate. Per conversazione nulla
    cambia: resta genera_conversazione col suo payload."""
    from argo.voce import TESTO_TETTO_CONVERSAZIONE, classifica_modo, risolvi_modo
    from connectors.llm import TettoLLMRaggiunto

    try:
        decisione = classifica_modo(payload["conversazione_id"], payload["testo"])
    except TettoLLMRaggiunto:
        return "genera_conversazione", payload, TESTO_TETTO_CONVERSAZIONE
    logger.info(
        "orienta_webhook: messaggio libero classificato come %s (confidenza %.2f)",
        decisione["modo"], decisione["confidenza"],
    )
    modo, parametri = risolvi_modo(decisione)

    if modo == "chiedi":
        return "genera_conversazione", payload, parametri
    if modo == "orienta":
        return "genera_orienta", {}, None
    if modo == "instrada":
        return "genera_instrada", parametri, None
    if modo == "brief":
        return "genera_brief", {"nome": parametri["nome"], "origine_msg": payload["origine_msg"]}, None
    if modo == "impatto":
        mandato_id = _registra_mandato_impatto(payload["origine_msg"], parametri["componente"])
        return "genera_impatto", {"componente": parametri["componente"], "mandato_id": mandato_id}, None
    return "genera_conversazione", payload, None


def _registra_risposta_conversazione(testo):
    """La risposta di Argo entra nella finestra di conversazione PRIMA
    dell'invio (stesso ordine del resto del repo), così il prossimo messaggio
    la vede anche se questo processo muore subito dopo."""
    testo_sql = testo.replace("'", "''")
    _psql(f"INSERT INTO conversazione_argo (ruolo, testo) VALUES ('argo', '{testo_sql}')")


def _registra_finestra(job_id, parametri):
    """Passo 14: minuti e contesto di un messaggio libero instradato restano
    nel payload del suo job genera_conversazione (chiavi aggiunte al JSONB,
    schema invariato). Sono il dato di argo/impara.py:finestre_dichiarate.
    Valori già validati da interpreta_instrada."""
    aggiunta = json.dumps(
        {"modo": "instrada", "minuti": int(parametri["minuti"]), "contesto": parametri["contesto"]}
    ).replace("'", "''")
    _psql(f"UPDATE jobs SET payload = payload || '{aggiunta}'::jsonb WHERE id={int(job_id)}")


def _scrivi_user_md(riga):
    """L'unico punto che scrive knowledge/argo/USER.md, chiamato solo dal
    ramo del sì (_risposta_a_proposta). File temporaneo nella stessa
    cartella + os.replace: mai un USER.md scritto a metà. Ritorna False se
    la riga c'era già (idempotente: un job rilanciato non la duplica).
    UserMdErrore passa a chi chiama."""
    from argo import impara

    percorso = impara.USER_MD_PATH
    attuale = percorso.read_text(encoding="utf-8")
    nuovo = impara.applica_riga(attuale, riga)
    if nuovo == attuale:
        return False
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=percorso.parent, prefix=".USER.md.", delete=False
    ) as tmp:
        tmp.write(nuovo)
    os.replace(tmp.name, percorso)
    return True


def _risposta_a_proposta(payload):
    """Passo 14: se la riga subito precedente il messaggio è una proposta
    per USER.md e il messaggio è esattamente sì o no, ritorna la risposta
    fissa (dopo aver scritto la riga, se sì). Altrimenti None: la proposta
    decade e il messaggio segue la strada normale. Niente LLM: un sì che
    scrive un file non passa da un modello."""
    import argo.stato as stato
    from argo import impara

    precedente = stato.conversazione_recente(payload["conversazione_id"], 1)
    righe = precedente["righe"]
    if precedente["copertura"] != "completa" or not righe or righe[-1].get("ruolo") != impara.RUOLO_PROPOSTA:
        return None
    if impara.e_no(payload["testo"]):
        logger.info("orienta_webhook: proposta per USER.md rifiutata (riga %s)", righe[-1].get("id"))
        return impara.TESTO_LASCIATA
    if not impara.e_si(payload["testo"]):
        return None
    riga = impara.estrai_riga_proposta(righe[-1].get("testo"))
    if riga is None:
        return impara.TESTO_NON_SCRITTA.format(motivo="la proposta non ha una riga valida")
    try:
        scritta = _scrivi_user_md(riga)
    except impara.UserMdErrore as e:
        return impara.TESTO_NON_SCRITTA.format(motivo=str(e))
    logger.info("orienta_webhook: proposta per USER.md confermata (riga %s)", righe[-1].get("id"))
    return impara.TESTO_SCRITTA if scritta else impara.TESTO_GIA_PRESENTE


def _registra_proposta(testo):
    """La proposta entra in conversazione_argo col suo ruolo PRIMA
    dell'invio: è la riga che il sì successivo conferma."""
    from argo.impara import RUOLO_PROPOSTA

    testo_sql = testo.replace("'", "''")
    _psql(f"INSERT INTO conversazione_argo (ruolo, testo) VALUES ('{RUOLO_PROPOSTA}', '{testo_sql}')")


def invia_proposta(testo):
    """Scrive e manda una proposta. Usata da _forse_proponi e dal collaudo a
    mano (scripts/argo/proponi_user.py --collaudo)."""
    from connectors.telegram import invia_lungo

    _registra_proposta(testo)
    invia_lungo(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])


# Modi dopo cui una proposta può seguire la risposta. Mai dopo un brief
# (lungo, per Claude Code), mai dopo una riga che chiede qualcosa: il
# messaggio seguente di Leonardo risponderebbe a due cose.
TIPI_CON_PROPOSTA = ("genera_orienta", "genera_instrada", "genera_conversazione", "genera_impatto")


def _forse_proponi(tipo, testo):
    """Passo 14: al più una proposta al giorno, solo in coda a una risposta
    a un messaggio libero. Decide argo/impara.py:prepara_proposta; qui solo
    i casi in cui non si prova nemmeno."""
    from argo.impara import prepara_proposta
    from argo.voce import TESTO_TETTO_CONVERSAZIONE

    if tipo not in TIPI_CON_PROPOSTA or "?" in testo or testo == TESTO_TETTO_CONVERSAZIONE:
        return
    proposta, motivo = prepara_proposta()
    if proposta is None:
        logger.info("orienta_webhook: nessuna proposta per USER.md (%s)", motivo)
        return
    invia_proposta(proposta)


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
    "genera_conversazione": "riscrivi il messaggio",
}


def main():
    reclamato = _reclama_job()
    if reclamato is None:
        return
    job_id, tipo, payload = reclamato
    usa_contatore_persistente(incrementa_chiamate_llm, "risposte di Argo sospese")

    from argo.voce import (
        genera_risposta, genera_risposta_instrada, genera_avviso, genera_brief, genera_impatto,
        genera_conversazione,
    )
    from connectors.telegram import invia_lungo

    esito_mandato = None
    log_impatti_brief = None
    consultazione = None
    # Un messaggio libero entra sempre come genera_conversazione; dopo il
    # classificatore `tipo` può diventare quello di un altro modo, ma la
    # risposta va comunque nella finestra di conversazione.
    da_messaggio_libero = tipo == "genera_conversazione"
    testo_diretto = None
    try:
        if da_messaggio_libero:
            testo_diretto = _risposta_a_proposta(payload)
        if da_messaggio_libero and testo_diretto is None:
            tipo, payload, testo_diretto = _instrada_messaggio_libero(payload)
            if tipo == "genera_instrada":
                try:
                    _registra_finestra(job_id, payload)
                except Exception:
                    logger.exception("orienta_webhook: finestra del job %s non registrata", job_id)

        if testo_diretto is not None:
            testo, marcatori = testo_diretto, None
        elif tipo == "genera_orienta":
            testo, marcatori = genera_risposta(), None
        elif tipo == "genera_instrada":
            testo, marcatori = genera_risposta_instrada(payload["minuti"], payload["contesto"]), None
        elif tipo == "genera_brief":
            testo, log_impatti_brief = genera_brief(payload["nome"])
            marcatori = None
        elif tipo == "genera_impatto":
            testo, esito_mandato = genera_impatto(payload["componente"])
            marcatori = None
        elif tipo == "genera_conversazione":
            testo, consultazione = genera_conversazione(payload["conversazione_id"], payload["testo"])
            marcatori = None
        elif tipo == "genera_avviso":
            testo, marcatori = genera_avviso()
        else:
            raise RuntimeError(f"tipo di job sconosciuto: {tipo}")
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
    if consultazione:
        _registra_mandato_conversazione(
            payload["origine_msg"], consultazione["oggetto"], consultazione["esito"]
        )
    if da_messaggio_libero:
        _registra_risposta_conversazione(testo)

    invia_lungo(testo, token=os.environ["ARGO_VOCE_BOT_TOKEN"])
    _segna_done(job_id)

    # La proposta per USER.md è un di più: un suo errore non tocca il job,
    # già riuscito e consegnato.
    if da_messaggio_libero and testo_diretto is None:
        try:
            _forse_proponi(tipo, testo)
        except Exception:
            logger.exception("orienta_webhook: proposta per USER.md non mandata")


if __name__ == "__main__":
    main()
