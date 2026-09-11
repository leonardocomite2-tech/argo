import json
import logging
import os
import urllib.request
from datetime import datetime, timezone

logger = logging.getLogger("argo.telegram")

API_BASE = "https://api.telegram.org"


def notifica(testo, token=None):
    """Manda `testo` come messaggio semplice. `token` opzionale: se assente,
    usa TELEGRAM_TOKEN (bot meccanico) come sempre — passarlo esplicitamente
    permette di riusare questa funzione anche per un bot diverso (stesso
    TELEGRAM_CHAT_ID), senza duplicare la logica di invio."""
    token = token or os.environ.get("TELEGRAM_TOKEN")
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


def normalizza_comando(testo):
    """Primo token di un messaggio Telegram, senza l'eventuale suffisso
    '@NomeBot' che Telegram aggiunge nei gruppi — None se il testo è
    vuoto/assente. Non convalida che sia un comando noto, solo lo estrae."""
    testo = (testo or "").strip()
    if not testo:
        return None
    return testo.split()[0].split("@", 1)[0]


def argomenti_comando(testo):
    """Token successivi al comando (esclude il comando stesso e l'eventuale
    '@NomeBot'). [] se il testo è vuoto/assente o ha solo il comando. Usata da
    /instrada per leggere minuti e contesto senza toccare il testo grezzo altrove."""
    testo = (testo or "").strip()
    if not testo:
        return []
    return testo.split()[1:]


CONTESTI_VALIDI = {"telefono", "computer"}

MESSAGGIO_MINUTI_MANCANTI = "Quanti minuti hai?"
MESSAGGIO_MINUTI_NON_VALIDI = "I minuti vanno scritti come numero intero positivo (es. 20)."
MESSAGGIO_CONTESTO_MANCANTE = "Sei al telefono o al computer?"
MESSAGGIO_CONTESTO_NON_VALIDO = "Contesto non riconosciuto: telefono o computer?"


def interpreta_instrada(argomenti):
    """Interpreta gli argomenti di /instrada (minuti, contesto). Ritorna
    (minuti, contesto, errore): errore è una riga pronta da mandare a Leonardo se
    un parametro manca o non è valido, None se entrambi i valori sono buoni. Non
    indovina mai un valore mancante o fuori dall'enum — coerente con /orienta."""
    minuti_testo = argomenti[0] if len(argomenti) >= 1 else None
    contesto_testo = argomenti[1] if len(argomenti) >= 2 else None

    if minuti_testo is None:
        return None, None, MESSAGGIO_MINUTI_MANCANTI
    if not minuti_testo.isdigit() or int(minuti_testo) <= 0:
        return None, None, MESSAGGIO_MINUTI_NON_VALIDI
    minuti = int(minuti_testo)

    if contesto_testo is None:
        return minuti, None, MESSAGGIO_CONTESTO_MANCANTE
    contesto = contesto_testo.strip().lower()
    if contesto not in CONTESTI_VALIDI:
        return minuti, None, MESSAGGIO_CONTESTO_NON_VALIDO

    return minuti, contesto, None


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
