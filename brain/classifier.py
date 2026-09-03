import json

from connectors.llm import chiama, estrai_json, TettoLLMRaggiunto, LLMErrore

CATEGORIE = {
    "interessato",
    "domanda",
    "obiezione",
    "prezzo_o_contratto",
    "non_interessato",
    "disiscrizione",
    "fuori_tema",
}

SYSTEM_PROMPT = """Classifichi risposte ricevute da host di NarraTours (programma di
poster con codice sconto per hotel/B&B) o da prospect contattati per lo stesso
programma. Rispondi SOLO con un oggetto JSON, senza testo attorno, con
esattamente queste chiavi:
{"categoria": "...", "confidenza": 0.0, "motivo": "..."}

`categoria` deve essere ESATTAMENTE una di queste sette, mai altro:
- interessato: vuole aderire o partecipare, chiede come iniziare.
- domanda: chiede informazioni pratiche sul programma o sui tour per l'ospite
  (es. come funziona, sconto, prezzi dei tour, lingue, durata) — informazioni
  che potrebbero già stare in una base di conoscenza pubblica.
- obiezione: esprime un dubbio o una resistenza (non si fida, teme sia una
  truffa, non ha tempo, ecc.) senza chiedere esplicitamente di rinegoziare
  prezzo o contratto.
- prezzo_o_contratto: chiede di negoziare o modificare le CONDIZIONI DEL
  PROPRIO CONTRATTO come host (percentuale di commissione, importi, modalità
  o tempi di pagamento) — mai i prezzi dei tour mostrati all'ospite, quelli
  sono "domanda".
- non_interessato: rifiuta esplicitamente, dice di non essere interessato.
- disiscrizione: chiede di essere rimosso dalla lista o di non ricevere più
  contatti.
- fuori_tema: contenuto non pertinente al programma host o a NarraTours.

`confidenza` è un numero tra 0.0 e 1.0. `motivo` è una riga breve in italiano
che spiega la scelta. Nessun altro testo, nessuna spiegazione fuori dal JSON."""


class ClassificazioneErrore(Exception):
    """Errore rumoroso: JSON non valido o categoria fuori dall'insieme chiuso.
    Il motivo è sempre categorico, mai il testo grezzo restituito dal modello."""


def classifica(mittente, oggetto, testo):
    prompt = (
        f"Mittente: {mittente or '(sconosciuto)'}\n"
        f"Oggetto: {oggetto or '(nessuno)'}\n"
        f"Testo:\n{testo or ''}"
    )

    try:
        grezzo = chiama(SYSTEM_PROMPT, prompt, max_tokens=200, temperature=0.0)
    except TettoLLMRaggiunto:
        raise
    except LLMErrore as e:
        raise ClassificazioneErrore("chiamata LLM fallita") from e

    try:
        risultato = json.loads(estrai_json(grezzo))
    except Exception:
        raise ClassificazioneErrore("JSON non valido") from None

    categoria = risultato.get("categoria")
    confidenza = risultato.get("confidenza")
    motivo = risultato.get("motivo") or ""

    if categoria not in CATEGORIE:
        raise ClassificazioneErrore("categoria fuori dall'insieme chiuso")
    if not isinstance(confidenza, (int, float)) or not (0.0 <= confidenza <= 1.0):
        raise ClassificazioneErrore("confidenza non valida")

    return {"categoria": categoria, "confidenza": float(confidenza), "motivo": motivo}
