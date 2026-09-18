"""Scrittura/lettura del DB da host via `docker exec argo-db-1 psql`, per gli
script che girano fuori da Docker (psycopg non è installato sull'host).
Estratto al secondo uso (18/9/2026): scripts/argo/orienta_webhook.py e
scripts/memoria/hook_sessione.py. Stessa deviazione dichiarata dalla
convenzione "psycopg diretto" già descritta in argo/stato.py.

`incrementa_chiamate_llm` è il contatore persistente del tetto LLM
(tabella llm_chiamate_giorno) da agganciare con
connectors/llm.py:usa_contatore_persistente in ogni processo host che chiama
l'LLM: un processo per job, quindi il contatore in-memory non basterebbe.
"""
import subprocess

CONTAINER_DB = "argo-db-1"


def psql(sql, timeout=15):
    """Esegue `sql` passandolo su stdin (niente limiti di lunghezza della
    riga di comando, niente quoting della shell). Ritorna stdout grezzo,
    stripped. Solleva RuntimeError se psql fallisce."""
    risultato = subprocess.run(
        ["docker", "exec", "-i", CONTAINER_DB, "psql", "-U", "argo", "-d", "argo",
         "-t", "-A", "-q", "-v", "ON_ERROR_STOP=1"],
        input=sql,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if risultato.returncode != 0:
        raise RuntimeError(f"psql fallito: {risultato.stderr.strip()[:300]}")
    return risultato.stdout.strip()


def incrementa_chiamate_llm(giorno):
    """UPSERT atomico sulla riga del giorno, ritorna il conteggio dopo
    l'incremento. `giorno` è una date, mai testo dall'esterno."""
    risultato = psql(
        "INSERT INTO llm_chiamate_giorno (giorno, chiamate) "
        f"VALUES ('{giorno.isoformat()}', 1) "
        "ON CONFLICT (giorno) DO UPDATE SET chiamate = llm_chiamate_giorno.chiamate + 1 "
        "RETURNING chiamate"
    )
    return int(risultato.splitlines()[0])


def incrementa_chiamate_openrouter(giorno):
    """Quota gratuita OpenRouter del giorno (tabella openrouter_chiamate_giorno),
    stesso UPSERT atomico di incrementa_chiamate_llm ma su una tabella sua:
    spesa Anthropic e quota gratuita non si sommano mai."""
    risultato = psql(
        "INSERT INTO openrouter_chiamate_giorno (giorno, chiamate) "
        f"VALUES ('{giorno.isoformat()}', 1) "
        "ON CONFLICT (giorno) DO UPDATE SET chiamate = openrouter_chiamate_giorno.chiamate + 1 "
        "RETURNING chiamate"
    )
    return int(risultato.splitlines()[0])
