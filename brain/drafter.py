import json
from pathlib import Path

from connectors.llm import chiama, estrai_json, TettoLLMRaggiunto, LLMErrore

REPO_ROOT = Path(__file__).resolve().parent.parent
CONOSCENZA_PATH = REPO_ROOT / "knowledge" / "conoscenza.md"

SYSTEM_PROMPT_TEMPLATE = """Scrivi bozze di risposta email/DM per NarraTours, un
programma di tour audio-guidati per turisti con poster-partner (host: hotel,
B&B, ristoranti...). Rispondi solo usando i fatti nella base di conoscenza
qui sotto: se la domanda richiede un'informazione che NON è in questo testo,
non inventarla e non aggirarla.

--- BASE DI CONOSCENZA ---
{conoscenza}
--- FINE BASE DI CONOSCENZA ---

Tono: ci si rivolge SEMPRE alla singola persona che scrive, con il lei
singolare — mai il tu, mai il voi plurale (anche se chi scrive gestisce un
hotel o un B&B, ci si rivolge alla persona, non alla struttura). Attenzione
soprattutto alle forme implicite, dove l'errore si nasconde più spesso:
- imperativi/congiuntivi: "appenda i poster" — mai "appendi" (tu) né
  "appendete"/"potete appendere" (voi)
- possessivi, su QUALSIASI sostantivo, non solo "ospiti" — "i suoi ospiti",
  "il suo B&B", "il suo hotel", "il suo codice": mai la forma con "tuo/i/a/e"
  né quella con "vostro/i/a/e", anche quando chi scrive gestisce un'attività
  (l'attività non ha un possessivo proprio, è sempre "il suo hotel", mai "il
  vostro hotel")
- pronomi/verbi: "le rispondo", "lei riceverà" — mai "ti rispondo" (tu) né
  "vi rispondo"/"riceverete" (voi)
Cordiale e diretto, mai formalismi da ufficio (sì: "Buongiorno", "in
allegato trova", "risponda pure a questa email"; no: "Gentile Signore", "La
preghiamo di voler cortesemente", "Distinti saluti"). Risposta breve, poche
righe. Firma sempre "NarraTours".

Rispondi SOLO con un oggetto JSON, senza testo attorno, con esattamente
queste chiavi:
{{"puo_rispondere": true/false, "bozza": "...", "motivo_se_no": "..."}}

Se puoi rispondere usando solo la base di conoscenza sopra: "puo_rispondere":
true, "bozza" con il testo della risposta pronta da mandare, "motivo_se_no":
stringa vuota.
Se la domanda esce dal perimetro della base di conoscenza (l'informazione
richiesta non c'è): "puo_rispondere": false, "bozza": stringa vuota,
"motivo_se_no" con una riga breve che spiega cosa manca."""


class DrafterErrore(Exception):
    """Errore rumoroso: JSON non valido. Motivo sempre categorico."""


def redigi_bozza(mittente, oggetto, testo, categoria):
    conoscenza = CONOSCENZA_PATH.read_text(encoding="utf-8")
    system = SYSTEM_PROMPT_TEMPLATE.format(conoscenza=conoscenza)
    prompt = (
        f"Categoria: {categoria}\n"
        f"Mittente: {mittente or '(sconosciuto)'}\n"
        f"Oggetto: {oggetto or '(nessuno)'}\n"
        f"Testo ricevuto:\n{testo or ''}"
    )

    try:
        grezzo = chiama(system, prompt, max_tokens=500, temperature=0.0)
    except TettoLLMRaggiunto:
        raise
    except LLMErrore as e:
        raise DrafterErrore("chiamata LLM fallita") from e

    try:
        risultato = json.loads(estrai_json(grezzo))
    except Exception:
        raise DrafterErrore("JSON non valido") from None

    puo_rispondere = risultato.get("puo_rispondere")
    if not isinstance(puo_rispondere, bool):
        raise DrafterErrore("puo_rispondere non valido")

    if not puo_rispondere:
        motivo = risultato.get("motivo_se_no") or "domanda fuori dal perimetro della base di conoscenza"
        return {"bozza": None, "motivo": motivo}

    bozza = (risultato.get("bozza") or "").strip()
    if not bozza:
        raise DrafterErrore("bozza vuota nonostante puo_rispondere=true")

    return {"bozza": bozza, "motivo": None}
