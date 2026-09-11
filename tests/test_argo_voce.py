"""Test di argo/voce.py, stile CASI (vedi tests/test_argo_stato.py).
Zero chiamate di rete: il collaudo del testo vero generato dall'LLM è a
mano, con scripts/argo/orienta.py (criterio di chiusura della sessione).
Lancio: python3 tests/test_argo_voce.py
"""
import copy
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import argo.voce as voce  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


# --- guardrail statico: argo/voce.py non scrive mai sul DB ---
sorgente = (REPO_ROOT / "argo" / "voce.py").read_text(encoding="utf-8")
verbi_scrittura = re.findall(r"\b(INSERT|UPDATE|DELETE)\b", sorgente, re.IGNORECASE)
caso("nessun verbo di scrittura SQL nel sorgente di argo/voce.py", [], verbi_scrittura)

# --- i tre file identità esistono e non sono vuoti ---
for nome_file in ("SOUL.md", "IDENTITY.md", "USER.md"):
    contenuto = (voce.KNOWLEDGE_DIR / nome_file).read_text(encoding="utf-8")
    caso(f"{nome_file} non è vuoto", True, len(contenuto.strip()) > 0)

# --- costruisci_system_prompt: contiene davvero identità + istruzioni + stato ---
# istruzioni è ora un parametro (passo 6, condiviso tra orienta e instrada) ---
STATO_FINTO = {
    "cantieri_aperti": {"copertura": "parziale", "motivo": "MARCATORE_TEST_MOTIVO"},
}
_prompt = voce.costruisci_system_prompt(STATO_FINTO, voce.ISTRUZIONI_ORIENTA)

soul, identity, user = voce._leggi_identita()
caso("il system prompt contiene SOUL.md per intero", True, soul in _prompt)
caso("il system prompt contiene IDENTITY.md per intero", True, identity in _prompt)
caso("il system prompt contiene USER.md per intero", True, user in _prompt)
caso("il system prompt contiene le istruzioni del modo orienta", True, voce.ISTRUZIONI_ORIENTA in _prompt)
caso("il system prompt contiene lo stato serializzato passato", True, "MARCATORE_TEST_MOTIVO" in _prompt)

# --- costruisci_system_prompt con ISTRUZIONI_INSTRADA: stesso costruttore, istruzioni diverse ---
_prompt_instrada = voce.costruisci_system_prompt(STATO_FINTO, voce.ISTRUZIONI_INSTRADA)
caso("il system prompt (instrada) contiene SOUL.md per intero", True, soul in _prompt_instrada)
caso(
    "il system prompt (instrada) contiene le istruzioni del modo instrada",
    True,
    voce.ISTRUZIONI_INSTRADA in _prompt_instrada,
)
caso(
    "il system prompt (instrada) NON contiene le istruzioni di orienta",
    False,
    voce.ISTRUZIONI_ORIENTA in _prompt_instrada,
)

# --- le istruzioni esplicite coprono i punti richiesti dal brief ---
_istruzioni_normalizzate = re.sub(r"\s+", " ", voce.ISTRUZIONI_ORIENTA)
for frammento in (
    "Poche righe",
    "Dai del tu",
    "Conclusione prima",
    "UNA SOLA prossima cosa",
    "FERMATI",
    "riportali SOLO se compaiono alla lettera",
    "copertura",
    "silenzio è un esito normale",
    "mai con una domanda",
    "al massimo UN riferimento temporale",
    "senza markdown",
    "niente backtick",
    "Niente incoraggiamenti",
):
    caso(
        f"ISTRUZIONI_ORIENTA copre: {frammento!r}",
        True,
        frammento in _istruzioni_normalizzate,
    )

# --- ISTRUZIONI_INSTRADA copre i punti specifici del brief (chiude-prima-di-apre,
# finestra dichiarata, contesto fisico, una sola proposta, "niente si adatta") ---
_istruzioni_instrada_normalizzate = re.sub(r"\s+", " ", voce.ISTRUZIONI_INSTRADA)
for frammento in (
    "Due o tre righe",
    "Una SOLA proposta",
    "DENTRO la finestra dichiarata",
    "contesto fisico dichiarato",
    "niente Claude Code",
    "CHIUDE qualcosa",
    "APRE",
    "proposta prima",
    "niente si adatta alla finestra",
    "riportali SOLO se compaiono alla lettera",
    "copertura",
    "mai con una domanda",
    "al massimo UN riferimento temporale",
    "senza markdown",
    "niente backtick",
):
    caso(
        f"ISTRUZIONI_INSTRADA copre: {frammento!r}",
        True,
        frammento in _istruzioni_instrada_normalizzate,
    )

# --- _domanda_instrada: pura, deriva solo da minuti/contesto già validati ---
caso(
    "_domanda_instrada(20, 'telefono')",
    "Ho 20 minuti e ho solo il telefono. Cosa chiude qualcosa?",
    voce._domanda_instrada(20, "telefono"),
)
caso(
    "_domanda_instrada(120, 'computer')",
    "Ho 120 minuti e sono al computer. Cosa chiude qualcosa?",
    voce._domanda_instrada(120, "computer"),
)

# --- genera_risposta_instrada esiste e usa raccogli_stato/costruisci_system_prompt/chiama
# (verificato via source, zero chiamate DB/rete nei test, stesso stile del check su
# raccogli_stato sotto) ---
_sorgente_genera_instrada = sorgente[sorgente.index("def genera_risposta_instrada"):]
caso(
    "genera_risposta_instrada chiama raccogli_stato()",
    True,
    "raccogli_stato()" in _sorgente_genera_instrada,
)
caso(
    "genera_risposta_instrada usa ISTRUZIONI_INSTRADA",
    True,
    "ISTRUZIONI_INSTRADA" in _sorgente_genera_instrada,
)

# --- anti-invenzione anche in SOUL.md (non solo nel prompt operativo) ---
caso(
    "SOUL.md dichiara la regola anti-invenzione",
    True,
    "mai ricostruirlo a memoria" in re.sub(r"\s+", " ", soul),
)

# --- niente rilancio anche in SOUL.md (non solo nel prompt operativo) ---
caso(
    "SOUL.md dichiara la regola anti-rilancio",
    True,
    "finisce con la proposta, mai con una domanda" in re.sub(r"\s+", " ", soul),
)

# --- _data_oggi(): formato ISO, pura, zero DB ---
_oggi = voce._data_oggi()
caso("_data_oggi() ha formato ISO YYYY-MM-DD", True, bool(re.fullmatch(r"\d{4}-\d{2}-\d{2}", _oggi)))

# --- _stato_per_prompt: tronca solo sopra soglia, con nota esplicita ---
_testo_lungo = "X" * (voce.LIMITE_DECISIONI_APERTE_CARATTERI + 500)
_stato_lungo = {"cantieri_aperti": {"decisioni_aperte_bloccano": _testo_lungo}}
_originale_intatto = copy.deepcopy(_stato_lungo)
_risultato = voce._stato_per_prompt(_stato_lungo)
_troncato = _risultato["cantieri_aperti"]["decisioni_aperte_bloccano"]
caso("testo sopra soglia: troncato, resta sotto la soglia + nota", True, len(_troncato) < len(_testo_lungo))
caso("testo sopra soglia: nota di troncamento presente", True, "[TRONCATO" in _troncato)
caso("testo sopra soglia: nota riporta il totale di caratteri originale", True, str(len(_testo_lungo)) in _troncato)
caso("_stato_per_prompt non modifica l'originale (lavora su una copia)", _originale_intatto, _stato_lungo)

_testo_corto = "Y" * 100
_stato_corto = {"cantieri_aperti": {"decisioni_aperte_bloccano": _testo_corto}}
_risultato_corto = voce._stato_per_prompt(_stato_corto)
caso(
    "testo sotto soglia: non toccato",
    _testo_corto,
    _risultato_corto["cantieri_aperti"]["decisioni_aperte_bloccano"],
)

# --- raccogli_stato include il campo "oggi" (verificato via source, zero chiamate DB nei test) ---
sorgente_raccogli = sorgente[sorgente.index("def raccogli_stato"):]
caso('raccogli_stato() include il campo "oggi"', True, '"oggi": _data_oggi()' in sorgente_raccogli)


# ============================================================
# Modo "avvisa" (passo 8)
# ============================================================

# --- ISTRUZIONI_AVVISA copre i punti del brief ---
_istruzioni_avvisa_normalizzate = re.sub(r"\s+", " ", voce.ISTRUZIONI_AVVISA)
for frammento in (
    "Poche righe",
    "Dai del tu",
    "elenco è ammesso",
    "mai con una domanda",
    "senza markdown",
    "niente backtick",
    "riportali SOLO se compaiono alla lettera",
    "mai calcolarlo o ricostruirlo a memoria",
):
    caso(
        f"ISTRUZIONI_AVVISA copre: {frammento!r}",
        True,
        frammento in _istruzioni_avvisa_normalizzate,
    )

# --- costruisci_system_prompt con ISTRUZIONI_AVVISA: stesso costruttore, terze istruzioni ---
_prompt_avvisa = voce.costruisci_system_prompt(STATO_FINTO, voce.ISTRUZIONI_AVVISA)
caso("il system prompt (avvisa) contiene SOUL.md per intero", True, soul in _prompt_avvisa)
caso(
    "il system prompt (avvisa) contiene le istruzioni del modo avvisa",
    True,
    voce.ISTRUZIONI_AVVISA in _prompt_avvisa,
)
caso(
    "il system prompt (avvisa) NON contiene le istruzioni di orienta",
    False,
    voce.ISTRUZIONI_ORIENTA in _prompt_avvisa,
)

# --- genera_avviso: il silenzio è deciso PRIMA di chiamare l'LLM (verificato
# via source — il return anticipato precede la chiamata a chiama()) ---
sorgente_genera_avviso = sorgente[sorgente.index("def genera_avviso"):]
_pos_return_none = sorgente_genera_avviso.index("return None, {}")
_pos_chiama = sorgente_genera_avviso.index("chiama(")
caso(
    "genera_avviso: il return silenzioso precede la chiamata a chiama() (nel sorgente)",
    True,
    _pos_return_none < _pos_chiama,
)

# --- _filtra_candidati_avviso: pura, nessun accesso DB — CASI stile CASI ---

RIGA_APPR = lambda id_, ore_ferma: {"id": id_, "mittente": "x", "oggetto": "y", "ore_ferma": ore_ferma}
RIGA_JOB = lambda tipo, errore: {"tipo": tipo, "ultimo_errore": errore, "quante": 1}
RIGA_OSS = lambda id_, severita: {"id": id_, "fonte": "panoptes", "severita": severita, "testo": "z"}

# Niente qualifica: nessuna chiamata LLM, nessun invio (criterio di chiusura del brief)
caso(
    "_filtra_candidati_avviso: niente qualifica -> (None, {})",
    (None, {}),
    voce._filtra_candidati_avviso([], [], [], set()),
)

# Soglia approvazioni: esattamente 24h NON qualifica (soglia è '>', non '>=')
caso(
    "_filtra_candidati_avviso: approvazione a esattamente 24h non qualifica",
    (None, {}),
    voce._filtra_candidati_avviso([RIGA_APPR(1, 24)], [], [], set()),
)

# Approvazione oltre soglia, non ancora segnalata -> qualifica
_cand, _marc = voce._filtra_candidati_avviso([RIGA_APPR(10, 193.7)], [], [], set())
caso("_filtra_candidati_avviso: approvazione >24h qualifica", 1, len(_cand["approvazioni_da_segnalare"]))
caso(
    "_filtra_candidati_avviso: marcatore approvazione ha la forma avvisa_appr:<id>",
    ["avvisa_appr:10"],
    _marc["alert_chiavi"],
)

# Approvazione oltre soglia ma già segnalata in passato -> esclusa (anti-ripetizione)
caso(
    "_filtra_candidati_avviso: approvazione già avvisata non si ripete",
    (None, {}),
    voce._filtra_candidati_avviso([RIGA_APPR(10, 193.7)], [], [], {"avvisa_appr:10"}),
)

# Job fallito di recente, non ancora segnalato -> qualifica, firma stabile
_cand, _marc = voce._filtra_candidati_avviso([], [RIGA_JOB("invia_risposta", "boom")], [], set())
caso("_filtra_candidati_avviso: job fallito recente qualifica", 1, len(_cand["job_falliti_da_segnalare"]))
caso(
    "_filtra_candidati_avviso: marcatore job ha prefisso avvisa_job:<tipo>:",
    True,
    _marc["alert_chiavi"][0].startswith("avvisa_job:invia_risposta:"),
)

# Stessa (tipo, errore) di un job già segnalato -> esclusa (firma identica)
_chiave_gia_nota = _marc["alert_chiavi"][0]
caso(
    "_filtra_candidati_avviso: job con stessa firma già avvisata non si ripete",
    (None, {}),
    voce._filtra_candidati_avviso([], [RIGA_JOB("invia_risposta", "boom")], [], {_chiave_gia_nota}),
)

# Osservazione grave (case-insensitive) -> qualifica; severità non grave -> esclusa
_cand, _marc = voce._filtra_candidati_avviso([], [], [RIGA_OSS(7, "Grave")], set())
caso("_filtra_candidati_avviso: osservazione 'Grave' qualifica (case-insensitive)", 1, len(_cand["osservazioni_da_segnalare"]))
caso("_filtra_candidati_avviso: marcatore osservazione è l'id, non una chiave alert", [7], _marc["osservazioni_id"])
caso(
    "_filtra_candidati_avviso: osservazione severità 'bassa' non qualifica",
    (None, {}),
    voce._filtra_candidati_avviso([], [], [RIGA_OSS(8, "bassa")], set()),
)

# Cap a LIMITE_VOCI_AVVISO per categoria: l'eccedenza non è nei marcatori
# (riemerge da sola al giro successivo, non è persa)
_sette_approvazioni = [RIGA_APPR(i, 100) for i in range(1, 8)]
_cand, _marc = voce._filtra_candidati_avviso(_sette_approvazioni, [], [], set())
caso(
    "_filtra_candidati_avviso: cap a LIMITE_VOCI_AVVISO voci per categoria",
    voce.LIMITE_VOCI_AVVISO,
    len(_cand["approvazioni_da_segnalare"]),
)
caso(
    "_filtra_candidati_avviso: marcatori tagliati insieme ai candidati",
    voce.LIMITE_VOCI_AVVISO,
    len(_marc["alert_chiavi"]),
)


def main():
    falliti = 0
    for descrizione, atteso, ottenuto in CASI:
        if ottenuto != atteso:
            falliti += 1
            print(f"FALLITO: {descrizione} — atteso {atteso!r}, ottenuto {ottenuto!r}")
    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
