import json
import logging
import os
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("argo.telegram")

API_BASE = "https://api.telegram.org"


def notifica(testo):
    token = os.environ.get("TELEGRAM_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        logger.warning("notifica: TELEGRAM_TOKEN o TELEGRAM_CHAT_ID mancanti, notifica non inviata")
        return

    url = f"{API_BASE}/bot{token}/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": testo}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Argo/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        logger.error("notifica: invio a Telegram fallito (%s): %s", type(e).__name__, messaggio)


def _invia(metodo, corpo):
    """POST verso l'API Telegram. Solleva l'eccezione (redatta) se la chiamata fallisce."""
    token = os.environ["TELEGRAM_TOKEN"]
    url = f"{API_BASE}/bot{token}/{metodo}"
    data = json.dumps(corpo).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Argo/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        raise RuntimeError(f"{metodo} fallita ({type(e).__name__}): {messaggio}") from None


LIMITE_TELEGRAM = 4000  # Telegram rifiuta i messaggi oltre 4096 caratteri, teniamo un margine
AVVISO_TRONCAMENTO = "\n[bozza troncata — testo completo nel database]"
SOGLIA_URGENZA_SCADENZA_SEC = 2 * 3600


def riga_scadenza(scadenza):
    """Riga con il tempo rimanente prima della scadenza, o "" se scadenza è None
    (caso email, nessun vincolo di finestra). Sotto le 2 ore mostra i minuti
    (mai le ore troncate a "1h" quando in realtà sono 95 minuti) e passa a ⚠️;
    troncamento per difetto, mai per eccesso, per non promettere più tempo di
    quanto ne resti davvero."""
    if scadenza is None:
        return ""
    rimane_sec = (scadenza - datetime.now(timezone.utc)).total_seconds()
    if rimane_sec < SOGLIA_URGENZA_SCADENZA_SEC:
        minuti = max(int(rimane_sec // 60), 0)
        return f"⚠️ scade tra {minuti}min"
    ore = int(rimane_sec // 3600)
    return f"⏳ scade tra {ore}h"


def chiedi_approvazione(approval_id, testo_bozza, contesto, scadenza=None):
    """Manda la bozza con i tre bottoni di approvazione. Ritorna il message_id.
    `scadenza` opzionale (TIMESTAMPTZ): se presente, aggiunge in cima una riga
    col tempo rimanente (vedi riga_scadenza). None = nessuna scadenza (email)."""
    mittente = (contesto or {}).get("mittente") or "(mittente sconosciuto)"
    oggetto = (contesto or {}).get("oggetto") or "(senza oggetto)"
    testo_ricevuto = (contesto or {}).get("testo_ricevuto") or "(testo non disponibile)"
    if len(testo_ricevuto) > 500:
        testo_ricevuto = testo_ricevuto[:500] + " [...]"

    def componi(bozza):
        riga = riga_scadenza(scadenza)
        intestazione = f"{riga}\n\n" if riga else ""
        return (
            f"{intestazione}"
            f"📩 Da: {mittente}\n"
            f"Oggetto: {oggetto}\n\n"
            f"{testo_ricevuto}\n\n"
            f"─────────────────\n"
            f"📝 Bozza di risposta\n\n"
            f"{bozza}"
        )

    testo = componi(testo_bozza)
    if len(testo) > LIMITE_TELEGRAM:
        # Tronca la bozza (mai l'email in arrivo, già limitata sopra) così il
        # messaggio di approvazione arriva comunque invece di fallire per
        # superamento del limite di lunghezza dell'API Telegram.
        spazio_bozza = max(
            len(testo_bozza) - (len(testo) - LIMITE_TELEGRAM) - len(AVVISO_TRONCAMENTO), 0
        )
        testo = componi(testo_bozza[:spazio_bozza].rstrip() + AVVISO_TRONCAMENTO)

    reply_markup = {
        "inline_keyboard": [[
            {"text": "✅ Approva", "callback_data": f"appr:{approval_id}"},
            {"text": "✏️ Modifica", "callback_data": f"modif:{approval_id}"},
            {"text": "❌ Rifiuta", "callback_data": f"rifiu:{approval_id}"},
        ]]
    }
    risposta = _invia("sendMessage", {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": testo,
        "reply_markup": reply_markup,
    })
    return risposta["result"]["message_id"]


def chiedi_testo_corretto(testo_prompt):
    """Manda un messaggio con force_reply per raccogliere il testo corretto. Ritorna il message_id."""
    risposta = _invia("sendMessage", {
        "chat_id": os.environ["TELEGRAM_CHAT_ID"],
        "text": testo_prompt,
        "reply_markup": {"force_reply": True},
    })
    return risposta["result"]["message_id"]


def rispondi_callback(callback_query_id, testo):
    token = os.environ.get("TELEGRAM_TOKEN")
    if not token:
        logger.warning("rispondi_callback: TELEGRAM_TOKEN mancante, callback non risposto")
        return

    url = f"{API_BASE}/bot{token}/answerCallbackQuery"
    data = json.dumps({"callback_query_id": callback_query_id, "text": testo}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "Argo/1.0"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        logger.error(
            "rispondi_callback: answerCallbackQuery fallita (%s): %s", type(e).__name__, messaggio
        )
