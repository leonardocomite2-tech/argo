import json
import logging
import os
import urllib.request

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
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
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
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        raise RuntimeError(f"{metodo} fallita ({type(e).__name__}): {messaggio}") from None


def chiedi_approvazione(approval_id, testo_bozza, contesto):
    """Manda la bozza con i tre bottoni di approvazione. Ritorna il message_id."""
    mittente = (contesto or {}).get("mittente") or "(mittente sconosciuto)"
    oggetto = (contesto or {}).get("oggetto") or "(senza oggetto)"
    testo = (
        f"📝 Bozza di risposta\n"
        f"Da: {mittente}\n"
        f"Oggetto: {oggetto}\n\n"
        f"{testo_bozza}"
    )
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
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp.read()
    except Exception as e:
        messaggio = str(e).replace(token, "***")
        logger.error(
            "rispondi_callback: answerCallbackQuery fallita (%s): %s", type(e).__name__, messaggio
        )
