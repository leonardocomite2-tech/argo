"""Spedisce l'ultimo dump del DB fuori dalla VPS via email. Gira da cron
sull'host, fuori dai container: nessuna dipendenza oltre alla stdlib."""
import logging
import os
import smtplib
import subprocess
import sys
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.telegram import notifica  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.backup")

LIMITE_BYTE = 15 * 1024 * 1024  # margine sotto i 25 MB di Gmail dopo l'overhead ~1/3 del base64
DUMPS_DIR = REPO_ROOT / "backup" / "dumps"
DB_CONTAINER = "argo-db-1"
TABELLE_PRINCIPALI = ["contacts", "identities", "events", "messages", "approvals", "jobs"]


def _carica_env():
    """Cron non carica .env: lo leggiamo esplicitamente. Non sovrascrive
    variabili già presenti nell'ambiente."""
    env_path = REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for riga in env_path.read_text().splitlines():
        riga = riga.strip()
        if not riga or riga.startswith("#") or "=" not in riga:
            continue
        chiave, _, valore = riga.partition("=")
        valore = valore.strip()
        if len(valore) >= 2 and valore[0] == valore[-1] and valore[0] in "'\"":
            valore = valore[1:-1]
        os.environ.setdefault(chiave.strip(), valore)


def _ultimo_dump():
    candidati = sorted(DUMPS_DIR.glob("argo_*.sql.gz"), key=lambda p: p.stat().st_mtime)
    if not candidati:
        raise FileNotFoundError(f"nessun dump trovato in {DUMPS_DIR}")
    return candidati[-1]


def _conta_righe_tabelle():
    """Il DB non ha porta esposta sull'host: si passa da docker exec,
    stesso pattern già usato da dump.sh per pg_dump."""
    query = " UNION ALL ".join(
        f"SELECT '{tabella}', count(*) FROM {tabella}" for tabella in TABELLE_PRINCIPALI
    )
    risultato = subprocess.run(
        ["docker", "exec", DB_CONTAINER, "psql", "-U", "argo", "-d", "argo",
         "-t", "-A", "-F,", "-c", query],
        capture_output=True, text=True, check=True, timeout=30,
    )
    conteggi = []
    for riga in risultato.stdout.strip().splitlines():
        nome, _, valore = riga.partition(",")
        conteggi.append((nome, int(valore)))
    return conteggi


def _corpo_email(dimensione_byte, conteggi):
    dimensione_mb = dimensione_byte / (1024 * 1024)
    righe = [f"Dimensione: {dimensione_mb:.1f} MB", ""]
    if conteggi is None:
        righe.append("Conteggio righe tabelle: non disponibile")
    else:
        righe.append("Conteggio righe tabelle principali:")
        righe.extend(f"  {nome}: {n}" for nome, n in conteggi)
    return "\n".join(righe)


def _invia(percorso_dump, dimensione_byte, conteggi):
    oggetto = f"Backup Argo — {datetime.now().strftime('%d/%m/%Y')}"

    msg = EmailMessage()
    msg["Subject"] = oggetto
    msg["From"] = f'{os.environ["REPLY_FROM_NAME"]} <{os.environ["REPLY_SMTP_USER"]}>'
    msg["To"] = os.environ["BACKUP_EMAIL_DEST"]
    msg.set_content(_corpo_email(dimensione_byte, conteggi))
    msg.add_attachment(
        percorso_dump.read_bytes(),
        maintype="application",
        subtype="gzip",
        filename=percorso_dump.name,
    )

    with smtplib.SMTP(os.environ["REPLY_SMTP_HOST"], int(os.environ["REPLY_SMTP_PORT"])) as smtp:
        smtp.starttls()
        smtp.login(os.environ["REPLY_SMTP_USER"], os.environ["REPLY_SMTP_PASS"])
        smtp.send_message(msg)


def main():
    _carica_env()

    try:
        percorso_dump = _ultimo_dump()
    except Exception as e:
        logger.error("invia_backup: impossibile trovare l'ultimo dump (%s): %s", type(e).__name__, e)
        notifica(f"ALERT: invio backup fallito, nessun dump trovato ({type(e).__name__}).")
        return 1

    dimensione_byte = percorso_dump.stat().st_size
    if dimensione_byte > LIMITE_BYTE:
        dimensione_mb = dimensione_byte / (1024 * 1024)
        logger.error(
            "invia_backup: dump %s troppo grande per l'email (%.1f MB)",
            percorso_dump.name, dimensione_mb,
        )
        notifica(
            f"ALERT: backup {percorso_dump.name} troppo grande per l'email "
            f"({dimensione_mb:.1f} MB) — serve un'altra strada."
        )
        return 1

    try:
        conteggi = _conta_righe_tabelle()
    except Exception as e:
        # Solo un dettaglio informativo nel corpo dell'email: un suo fallimento
        # non deve mai impedire l'invio del backup.
        logger.warning("invia_backup: conteggio righe fallito (%s): %s", type(e).__name__, e)
        conteggi = None

    try:
        _invia(percorso_dump, dimensione_byte, conteggi)
    except Exception as e:
        logger.error("invia_backup: invio email fallito (%s): %s", type(e).__name__, e)
        notifica(
            f"ALERT: invio backup fallito ({type(e).__name__}) — un backup che non "
            "parte in silenzio è peggio di nessun backup."
        )
        return 1

    logger.info(
        "invia_backup: inviato %s (%.1f MB)",
        percorso_dump.name, dimensione_byte / (1024 * 1024),
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
