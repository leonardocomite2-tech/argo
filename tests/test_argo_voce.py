"""Test di argo/voce.py, stile CASI (vedi tests/test_argo_stato.py).
Zero chiamate di rete: il collaudo del testo vero generato dall'LLM è a
mano, con scripts/argo/orienta.py (criterio di chiusura della sessione).
Lancio: python3 tests/test_argo_voce.py
"""
import copy
import json
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


# ============================================================
# Modo "brief" (cantiere Argo — il ponte, passo 1)
# ============================================================

# --- ISTRUZIONI_BRIEF copre i punti del brief: JSON forzato, anti-invenzione
# rinforzata, markdown ammesso (a differenza degli altri modi), niente
# duplicazione dello skeleton fisso ---
_istruzioni_brief_normalizzate = re.sub(r"\s+", " ", voce.ISTRUZIONI_BRIEF)
for frammento in (
    "Markdown ammesso",
    "SOLO con un oggetto JSON",
    "contesto",
    "obiettivo",
    "criterio_di_chiusura",
    "Anti- invenzione più forte",
    "Da precisare con Leonardo",
    "Non scrivere tu le sezioni",
):
    caso(
        f"ISTRUZIONI_BRIEF copre: {frammento!r}",
        True,
        frammento in _istruzioni_brief_normalizzate,
    )

# --- VINCOLI_STANDARD_BRIEF: testo fisso, mai chiesto al modello ---
for frammento in ("guardrail-review", "Niente git push", "suite di test", "verifica_mappa.py", "STATO.md"):
    caso(
        f"VINCOLI_STANDARD_BRIEF cita: {frammento!r}",
        True,
        frammento in voce.VINCOLI_STANDARD_BRIEF,
    )

caso(
    "RIGA_REPO_HA_RAGIONE dice esplicitamente che il repo ha ragione in caso di conflitto",
    True,
    "ha ragione il repo" in voce.RIGA_REPO_HA_RAGIONE,
)

# --- _risolvi_cantiere: match tollerante per sottostringa, case-insensitive ---
CANTIERI_FINTI = [
    {"nome": "Cantiere 2 — email"},
    {"nome": "Designer (bonifica yourservice-it)"},
    {"nome": "Argo — la voce"},
    {"nome": "Argo — il ponte"},
]

caso(
    "_risolvi_cantiere: match esatto case-insensitive",
    ["Designer (bonifica yourservice-it)"],
    [c["nome"] for c in voce._risolvi_cantiere("DESIGNER", CANTIERI_FINTI)],
)
caso(
    "_risolvi_cantiere: match per sottostringa parziale",
    ["Cantiere 2 — email"],
    [c["nome"] for c in voce._risolvi_cantiere("email", CANTIERI_FINTI)],
)
caso(
    "_risolvi_cantiere: nessun match -> lista vuota",
    [],
    voce._risolvi_cantiere("regista sonora", CANTIERI_FINTI),
)
caso(
    "_risolvi_cantiere: 'argo' è ambiguo tra 'la voce' e 'il ponte'",
    ["Argo — la voce", "Argo — il ponte"],
    [c["nome"] for c in voce._risolvi_cantiere("argo", CANTIERI_FINTI)],
)
caso("_risolvi_cantiere: nome vuoto -> lista vuota, non tutti i cantieri", [], voce._risolvi_cantiere("", CANTIERI_FINTI))
caso(
    "_risolvi_cantiere: nome None -> lista vuota",
    [],
    voce._risolvi_cantiere(None, CANTIERI_FINTI),
)

# --- _documento_cantiere: mappa statica, solo se il file esiste davvero ---
_nome_doc, _testo_doc = voce._documento_cantiere("Designer (bonifica yourservice-it)")
caso("_documento_cantiere: 'Designer' trova CANTIERE_Designer.md", "CANTIERE_Designer.md", _nome_doc)
caso("_documento_cantiere: il testo non è vuoto", True, bool(_testo_doc))

_nome_doc_argo, _ = voce._documento_cantiere("Argo — la voce")
caso("_documento_cantiere: 'Argo — la voce' trova IDENTITY.md", "IDENTITY.md", _nome_doc_argo)

_nome_doc_ponte, _ = voce._documento_cantiere("Argo — il ponte")
caso("_documento_cantiere: 'Argo — il ponte' trova anch'esso IDENTITY.md (stessa parola chiave 'argo')", "IDENTITY.md", _nome_doc_ponte)

_nome_doc_assente, _testo_doc_assente = voce._documento_cantiere("Panoptes — Mappa")
caso("_documento_cantiere: 'Panoptes — Mappa' non è mappato -> (None, None)", (None, None), (_nome_doc_assente, _testo_doc_assente))

# --- _componi_brief: pura, nessuna chiamata LLM — valida il JSON e compone lo skeleton fisso ---
CANTIERE_FINTO = {"nome": "Cantiere di prova"}

_json_valido = (
    '{"contesto": "- leggi x.py", "obiettivo": "fare x", '
    '"criterio_di_chiusura": "x funziona"}'
)
_testo_composto = voce._componi_brief(CANTIERE_FINTO, _json_valido)
caso("_componi_brief: il titolo è il nome esatto del cantiere", True, _testo_composto.startswith("Cantiere di prova\n"))
caso('_componi_brief: contiene "Plan mode obbligatorio."', True, "Plan mode obbligatorio." in _testo_composto)
caso("_componi_brief: contiene ## Contesto", True, "## Contesto" in _testo_composto)
caso("_componi_brief: contiene il testo del modello per contesto", True, "leggi x.py" in _testo_composto)
caso("_componi_brief: contiene la riga fissa sul repo che ha ragione", True, voce.RIGA_REPO_HA_RAGIONE in _testo_composto)
caso("_componi_brief: contiene ## Obiettivo", True, "## Obiettivo" in _testo_composto)
caso("_componi_brief: contiene ## Vincoli con il testo fisso", True, voce.VINCOLI_STANDARD_BRIEF in _testo_composto)
caso("_componi_brief: contiene ## Criterio di chiusura", True, "## Criterio di chiusura" in _testo_composto)
caso(
    "_componi_brief: l'ordine delle sezioni è Contesto, Obiettivo, Vincoli, Criterio di chiusura",
    True,
    (
        _testo_composto.index("## Contesto")
        < _testo_composto.index("## Obiettivo")
        < _testo_composto.index("## Vincoli")
        < _testo_composto.index("## Criterio di chiusura")
    ),
)

# JSON avvolto in fence markdown (capita anche con istruzioni esplicite di non farlo,
# vedi connectors/llm.py:estrai_json) — deve essere gestito comunque
_json_con_fence = "```json\n" + _json_valido + "\n```"
caso(
    "_componi_brief: gestisce un JSON avvolto in fence markdown",
    True,
    "leggi x.py" in voce._componi_brief(CANTIERE_FINTO, _json_con_fence),
)

# --- _componi_brief: il modello a volte manda "contesto" come lista JSON invece
# che stringa (osservato nel collaudo reale, 12/9/2026) — mai un repr Python
# (['- riga1', '- riga2']) nel testo finale ---
_json_con_lista = (
    '{"contesto": ["- leggi x.py", "- leggi y.py"], "obiettivo": "fare x", '
    '"criterio_di_chiusura": "x funziona"}'
)
_testo_da_lista = voce._componi_brief(CANTIERE_FINTO, _json_con_lista)
caso("_componi_brief: 'contesto' come lista JSON non produce un repr Python", False, "['" in _testo_da_lista)
caso("_componi_brief: 'contesto' come lista JSON, le righe restano leggibili", True, "- leggi x.py" in _testo_da_lista and "- leggi y.py" in _testo_da_lista)

# --- _testo_campo_brief: normalizza liste in stringa multi-riga, lascia le stringhe invariate ---
caso("_testo_campo_brief: stringa invariata", "già una stringa", voce._testo_campo_brief("già una stringa"))
caso(
    "_testo_campo_brief: lista -> stringa con \\n tra le righe",
    "- uno\n- due",
    voce._testo_campo_brief(["- uno", "- due"]),
)

# --- _componi_brief: errori rumorosi, mai un brief a metà ---
try:
    voce._componi_brief(CANTIERE_FINTO, "questo non è JSON")
    caso("_componi_brief: JSON non valido solleva BriefErrore", "BriefErrore", "nessuna eccezione")
except voce.BriefErrore:
    caso("_componi_brief: JSON non valido solleva BriefErrore", "BriefErrore", "BriefErrore")

_json_incompleto = '{"contesto": "- x", "obiettivo": "y"}'  # manca criterio_di_chiusura
try:
    voce._componi_brief(CANTIERE_FINTO, _json_incompleto)
    caso("_componi_brief: chiave mancante solleva BriefErrore", "BriefErrore", "nessuna eccezione")
except voce.BriefErrore:
    caso("_componi_brief: chiave mancante solleva BriefErrore", "BriefErrore", "BriefErrore")

_json_vuoto = '{"contesto": "", "obiettivo": "y", "criterio_di_chiusura": "z"}'  # contesto vuoto
try:
    voce._componi_brief(CANTIERE_FINTO, _json_vuoto)
    caso("_componi_brief: chiave vuota solleva BriefErrore", "BriefErrore", "nessuna eccezione")
except voce.BriefErrore:
    caso("_componi_brief: chiave vuota solleva BriefErrore", "BriefErrore", "BriefErrore")

# --- _componi_brief: avvertimento_impatti (passo 3 del ponte) va nei Vincoli,
# mai altrove; senza il parametro il comportamento resta quello di sempre ---
_AVVERTIMENTO_FINTO = "Avvertimento impatti — questi file toccano componenti condivisi o contratti:\n- x.py: contratti: RE01"
_testo_con_avvertimento = voce._componi_brief(CANTIERE_FINTO, _json_valido, avvertimento_impatti=_AVVERTIMENTO_FINTO)
caso(
    "_componi_brief: avvertimento_impatti finisce dentro la sezione Vincoli",
    True,
    _AVVERTIMENTO_FINTO in _testo_con_avvertimento.split("## Vincoli", 1)[1],
)
caso(
    "_componi_brief: senza avvertimento_impatti nessuna riga 'Avvertimento impatti'",
    False,
    "Avvertimento impatti" in voce._componi_brief(CANTIERE_FINTO, _json_valido),
)

# --- _estrai_contesto_brief: stessa tolleranza di _componi_brief su
# fence/lista, None se il JSON non è valido (non solleva mai) ---
caso("_estrai_contesto_brief: JSON valido -> testo del campo contesto", "- leggi x.py", voce._estrai_contesto_brief(_json_valido))
caso("_estrai_contesto_brief: JSON in fence markdown -> stesso risultato", "- leggi x.py", voce._estrai_contesto_brief(_json_con_fence))
caso(
    "_estrai_contesto_brief: contesto come lista JSON -> stringa multi-riga",
    "- leggi x.py\n- leggi y.py",
    voce._estrai_contesto_brief(_json_con_lista),
)
caso("_estrai_contesto_brief: JSON non valido -> None, non solleva", None, voce._estrai_contesto_brief("questo non è JSON"))

# ============================================================
# Modo "brief", passo 3 (cantiere Argo — il ponte) — impatti.py sui file
# citati nel contesto. Zero LLM, invocazioni reali di impatti.py (subprocess
# locale e deterministico, stesso principio delle CASI del modo impatto
# sopra — mai rete).
# ============================================================

# --- _file_citati_in_contesto: solo token con estensione che esistono
# davvero nel repo; un nome nudo inventato (limite noto del modello) non
# passa il controllo — nessun errore, semplicemente escluso ---
_contesto_misto = (
    "- leggi argo/voce.py per capire genera_brief\n"
    "- occhio a pavimento.mjs (non esiste in questa cartella)\n"
    "- vedi anche STATO.md\n"
)
caso(
    "_file_citati_in_contesto: solo i file reali, in ordine di comparsa",
    ["argo/voce.py", "STATO.md"],
    voce._file_citati_in_contesto(_contesto_misto),
)
caso("_file_citati_in_contesto: contesto vuoto -> lista vuota", [], voce._file_citati_in_contesto(""))
caso("_file_citati_in_contesto: contesto None -> lista vuota", [], voce._file_citati_in_contesto(None))

_vecchio_limite = voce.LIMITE_FILE_IMPATTI_BRIEF
try:
    voce.LIMITE_FILE_IMPATTI_BRIEF = 2
    caso(
        "_file_citati_in_contesto: rispetta il cap LIMITE_FILE_IMPATTI_BRIEF",
        ["argo/voce.py", "STATO.md"],
        voce._file_citati_in_contesto(_contesto_misto + "- STATO.md di nuovo\n- backend/main.py\n"),
    )
finally:
    voce.LIMITE_FILE_IMPATTI_BRIEF = _vecchio_limite

# --- _analizza_output_impatti_file / _contratti_in_gioco: parsing a riga
# sull'output reale di impatti.py --file (tre casi veri, verificati a mano) ---
_rc_mailer, _out_mailer, _ = voce._esegui_impatti("--file", "connectors/mailer.py")
caso("collaudo: impatti.py --file connectors/mailer.py esce 0", 0, _rc_mailer)
_condivisi_mailer, _contratti_mailer = voce._analizza_output_impatti_file(_out_mailer)
caso("_analizza_output_impatti_file: mailer.py -> condiviso 'mailer' rilevato", True, "mailer" in _condivisi_mailer)
caso("_analizza_output_impatti_file: mailer.py -> contratto RE04 rilevato", True, "RE04" in _contratti_mailer)

_rc_voce, _out_voce, _ = voce._esegui_impatti("--file", "argo/voce.py")
caso("collaudo: impatti.py --file argo/voce.py esce 0", 0, _rc_voce)
_condivisi_voce, _contratti_voce = voce._analizza_output_impatti_file(_out_voce)
caso("_analizza_output_impatti_file: argo/voce.py -> nessun condiviso (pipeline dedicata)", [], _condivisi_voce)
caso("_analizza_output_impatti_file: argo/voce.py -> nessun contratto ('nessuno' nell'output)", [], _contratti_voce)

_rc_test, _out_test, _ = voce._esegui_impatti("--file", "tests/test_argo_voce.py")
caso("collaudo: impatti.py --file tests/test_argo_voce.py esce 0", 0, _rc_test)
caso(
    "collaudo: tests/test_argo_voce.py non è mappato da nessuna scheda",
    True,
    "non è mappato da nessuna scheda" in _out_test,
)

# --- _verifica_impatti_brief: contesto realistico misto, tre file veri +
# un nome inventato — avvertimento cita solo il file con impatto, il log
# traccia tutti e tre i file reali (la consultazione è avvenuta comunque) ---
_contesto_brief_reale = (
    "- connectors/mailer.py\n"
    "- argo/voce.py\n"
    "- tests/test_argo_voce.py\n"
    "- pavimento.mjs (percorso indovinato male, non esiste qui)\n"
)
_avvertimento, _log = voce._verifica_impatti_brief(_contesto_brief_reale)
caso("_verifica_impatti_brief: avvertimento cita il file con impatto", True, "connectors/mailer.py" in _avvertimento)
caso("_verifica_impatti_brief: avvertimento cita il contratto RE04", True, "RE04" in _avvertimento)
caso(
    "_verifica_impatti_brief: avvertimento NON cita argo/voce.py (nessun impatto condiviso)",
    False,
    "- argo/voce.py:" in _avvertimento,
)
caso(
    "_verifica_impatti_brief: istruzione a lanciare impatti.py presente",
    True,
    "scripts/panoptes/impatti.py" in _avvertimento,
)
caso("_verifica_impatti_brief: log traccia connectors/mailer.py", True, "connectors/mailer.py" in _log)
caso("_verifica_impatti_brief: log traccia argo/voce.py", True, "argo/voce.py" in _log)
caso("_verifica_impatti_brief: log traccia tests/test_argo_voce.py (non mappato)", True, "non mappato" in _log)

# --- _verifica_impatti_brief: nessun file citato esiste davvero -> (None, None),
# nessuna consultazione avvenuta ---
caso(
    "_verifica_impatti_brief: nessun file reale citato -> nessuna consultazione",
    (None, None),
    voce._verifica_impatti_brief("- pavimento.mjs\n- altro/file/inventato.py\n"),
)

# --- genera_brief: risoluzione del nome, su un STATO.md finto (percorso
# ambiguo/non-trovato è deterministico, zero chiamate LLM — testabile senza mock) ---
import argo.stato as _stato_per_test  # noqa: E402

CANTIERI_MD_FINTO = """# STATO — finto

## CANTIERI

| Nome | Stato | Aperto il | Aspetta | Sessione più recente |
|---|---|---|---|---|
| Cantiere 2 — email | aperto | da confermare | il sistema | nota |
| Argo — la voce | in attesa | 10/09/2026 | calendario | nota |
| Argo — il ponte | aperto | 12/09/2026 | Leonardo | nota |

## Fatto
- niente
"""
_percorso_originale_voce = _stato_per_test.STATO_MD_PATH
_stato_voce_path = REPO_ROOT / "tests" / "_stato_finto_genera_brief.md"
_stato_voce_path.write_text(CANTIERI_MD_FINTO, encoding="utf-8")
try:
    _stato_per_test.STATO_MD_PATH = _stato_voce_path

    _esito_non_trovato, _log_non_trovato = voce.genera_brief("regista sonora")
    caso("genera_brief: nome non trovato non chiama l'LLM, elenca i nomi validi", True, "Nessun cantiere" in _esito_non_trovato)
    caso("genera_brief: elenco nomi validi include 'Argo — il ponte'", True, "Argo — il ponte" in _esito_non_trovato)
    caso("genera_brief: nome non trovato non registra nessuna consultazione impatti", None, _log_non_trovato)

    _esito_ambiguo, _log_ambiguo = voce.genera_brief("argo")
    caso("genera_brief: nome ambiguo non chiama l'LLM, lo dichiara", True, "ambiguo" in _esito_ambiguo)
    caso(
        "genera_brief: nome ambiguo elenca entrambi i cantieri coinvolti",
        True,
        "Argo — la voce" in _esito_ambiguo and "Argo — il ponte" in _esito_ambiguo,
    )
    caso("genera_brief: nome ambiguo non registra nessuna consultazione impatti", None, _log_ambiguo)

    _esito_vuoto, _log_vuoto = voce.genera_brief("")
    caso("genera_brief: nome vuoto è trattato come non trovato, non come 'tutti'", True, "Nessun cantiere" in _esito_vuoto)
    caso("genera_brief: nome vuoto non registra nessuna consultazione impatti", None, _log_vuoto)
finally:
    _stato_per_test.STATO_MD_PATH = _percorso_originale_voce
    _stato_voce_path.unlink()

# --- genera_brief: blocco CANTIERI non affidabile è un errore rumoroso, non un
# fallback silenzioso (a differenza di cantieri_aperti(), che qui va usato in
# modalità stretta) ---
CANTIERI_MD_ROTTO = "# STATO — finto\n\n## Fatto\n- niente\n"
_stato_rotto_path = REPO_ROOT / "tests" / "_stato_finto_rotto.md"
_stato_rotto_path.write_text(CANTIERI_MD_ROTTO, encoding="utf-8")
try:
    _stato_per_test.STATO_MD_PATH = _stato_rotto_path
    try:
        voce.genera_brief("designer")
        caso("genera_brief: blocco CANTIERI assente solleva RuntimeError", "RuntimeError", "nessuna eccezione")
    except RuntimeError:
        caso("genera_brief: blocco CANTIERI assente solleva RuntimeError", "RuntimeError", "RuntimeError")
finally:
    _stato_per_test.STATO_MD_PATH = _percorso_originale_voce
    _stato_rotto_path.unlink()


# ============================================================
# Modo "impatto" (cantiere Argo — il ponte, passo 2)
# ============================================================

# --- ISTRUZIONI_IMPATTO copre i punti del brief: anti-invenzione, niente
# markdown, niente domanda finale, un solo riferimento temporale, il caso
# "nessuna scheda impattata" dichiarato e non riempito ---
_istruzioni_impatto_normalizzate = re.sub(r"\s+", " ", voce.ISTRUZIONI_IMPATTO)
for frammento in (
    "Poche righe",
    "riportali SOLO se compaiono alla lettera",
    "Mai aggiungere una pipeline",
    "nessuna scheda è impattata",
    "mai con una domanda",
    "Al massimo UN riferimento temporale",
    "senza markdown",
    "niente backtick",
):
    caso(
        f"ISTRUZIONI_IMPATTO copre: {frammento!r}",
        True,
        frammento in _istruzioni_impatto_normalizzate,
    )

# --- _risolvi_flag_impatti: deterministico, un controllo reale sul filesystem
# del repo — non un'euristica sul nome ---
caso("_risolvi_flag_impatti: un file reale del repo -> --file", "--file", voce._risolvi_flag_impatti("argo/voce.py"))
caso(
    "_risolvi_flag_impatti: un file reale con :riga -> --file (la parte prima dei due punti esiste)",
    "--file",
    voce._risolvi_flag_impatti("worker/loop.py:94"),
)
caso(
    "_risolvi_flag_impatti: un nome di componente condiviso (non un file) -> --componente",
    "--componente",
    voce._risolvi_flag_impatti("mailer"),
)
caso(
    "_risolvi_flag_impatti: un percorso inesistente -> --componente (impatti.py deciderà se è valido)",
    "--componente",
    voce._risolvi_flag_impatti("percorso/che/non/esiste.py"),
)

# --- genera_impatto: errore vero di impatti.py (componente inesistente) —
# invocazione reale in sottoprocesso, deterministica, zero rete/LLM ---
_testo_errore, _esito_errore = voce.genera_impatto("componente_inesistente_test_argo")
caso("genera_impatto: componente inesistente -> esito 'fallito: ...'", True, _esito_errore.startswith("fallito:"))
caso(
    "genera_impatto: componente inesistente -> il messaggio è quello di impatti.py, non riscritto",
    True,
    "nessun componente condiviso o pipeline chiamato" in _testo_errore,
)

# --- genera_impatto: file reale ma non mappato da nessuna scheda (STATO.md
# non è coperto dalla mappa) — anche questo è un errore vero (returncode 0,
# ma con messaggio dedicato di impatti.py): verificato che passi comunque
# dall'LLM secondo la decisione presa nel piano (bypass solo su returncode
# != 0), quindi qui controlliamo solo che impatti.py stesso lo segnali così
# nel proprio output, non l'esito di genera_impatto (che richiederebbe rete) ---
_flag_stato_md = voce._risolvi_flag_impatti("STATO.md")
caso("_risolvi_flag_impatti: STATO.md esiste come file -> --file", "--file", _flag_stato_md)


# --- Ramo conversazionale (cantiere Argo — il ponte, passo 4) ---
from connectors.llm import TettoLLMRaggiunto as _Tetto  # noqa: E402

caso(
    "CONSULTAZIONI_PERMESSE: insieme chiuso, esattamente sei tipi di sola lettura",
    ["contratti_pipeline", "impatti_componente", "impatti_file", "impatti_tabella",
     "osservazioni_recenti", "stato_cantiere"],
    sorted(voce.CONSULTAZIONI_PERMESSE),
)

_r, _c = voce._interpreta_prima_risposta('{"consultazione": null, "risposta": "ciao"}')
caso("prima risposta senza consultazione -> (risposta, None)", ("ciao", None), (_r, _c))
_r, _c = voce._interpreta_prima_risposta(
    '```json\n{"consultazione": {"tipo": "impatti_componente", "argomento": " approvazione_telegram "}, "risposta": ""}\n```'
)
caso("prima risposta con consultazione valida (fence tollerato, argomento ripulito)",
     {"tipo": "impatti_componente", "argomento": "approvazione_telegram"}, _c)
_r, _c = voce._interpreta_prima_risposta('{"consultazione": {"tipo": "esegui_comando", "argomento": "rm"}, "risposta": ""}')
caso("tipo fuori dall'insieme chiuso -> mai eseguito, trattato come nessuna consultazione", None, _c)
_r, _c = voce._interpreta_prima_risposta('{"consultazione": {"tipo": "esecuzione", "argomento": "x"}, "risposta": "no"}')
caso("tipo 'esecuzione' -> scartato", ("no", None), (_r, _c))
_r, _c = voce._interpreta_prima_risposta('{"consultazione": "impatti_file", "risposta": "x"}')
caso("consultazione non oggetto -> scartata", None, _c)
try:
    voce._interpreta_prima_risposta("testo libero, non JSON")
    _sollevata = False
except voce.ConversazioneErrore:
    _sollevata = True
caso("JSON non valido -> ConversazioneErrore", True, _sollevata)

for _arg, _atteso in (("argo/voce.py", True), ("/etc/passwd", False), ("../fuori", False),
                      ("--diff", False), ("", False), ("approvazione_telegram", True)):
    caso(f"_argomento_sicuro({_arg!r})", _atteso, voce._argomento_sicuro(_arg))

try:
    voce._esegui_consultazione("esegui_qualcosa", "x", {})
    _sollevata = False
except ValueError:
    _sollevata = True
caso("_esegui_consultazione: tipo sconosciuto solleva, mai eseguito", True, _sollevata)

_voc = voce._vocabolario_mappa()
caso("vocabolario mappa letto", "completa", _voc["copertura"])
caso("vocabolario mappa: approvazione_telegram tra i condivisi", True, "approvazione_telegram" in _voc["condivisi"])
caso("vocabolario mappa: argo_voce tra le pipeline", True, "argo_voce" in _voc["pipeline"])
caso("vocabolario mappa: conversazione_argo tra le tabelle", True, "conversazione_argo" in _voc["tabelle"])

# Invocazioni reali di impatti.py (locale, zero rete)
_ris, _es = voce._esegui_consultazione("impatti_componente", "approvazione_telegram", _voc)
caso("consultazione impatti_componente reale -> riuscito", "riuscito", _es)
caso("consultazione impatti_componente reale -> RE01 nel risultato", True, "RE01" in _ris)
_ris, _es = voce._esegui_consultazione("impatti_componente", "gate_inesistente", _voc)
caso("componente inesistente -> esito fallito, messaggio di impatti.py", True,
     _es.startswith("fallito:") and "nessun componente condiviso o pipeline" in _ris)
_ris, _es = voce._esegui_consultazione("impatti_file", "--diff", _voc)
caso("impatti_file con argomento-flag -> non eseguita", "non eseguita: argomento non valido", _es)
_ris, _es = voce._esegui_consultazione("contratti_pipeline", "approvazione_telegram", _voc)
caso("contratti_pipeline su un condiviso (non pipeline) -> fallito senza lanciare impatti.py",
     "fallito: pipeline inesistente", _es)
_ris, _es = voce._esegui_consultazione("impatti_tabella", "mandati", _voc)
caso("consultazione impatti_tabella reale su mandati -> riuscito", "riuscito", _es)

# _senza_campi_derivati: toglie i numeri derivati da una copia, non dall'originale
_orig = {
    "approvazioni_in_attesa": {"righe": [{"id": 1, "ore_ferma": 353.8, "updated_at": "2026-09-03"}]},
    "attivita_git": {"ultimo_commit_giorni_fa": 5.2, "commits_recenti": []},
}
_copia = voce._senza_campi_derivati(_orig)
caso("_senza_campi_derivati: ore_ferma tolto dalla copia", False, "ore_ferma" in _copia["approvazioni_in_attesa"]["righe"][0])
caso("_senza_campi_derivati: updated_at resta", "2026-09-03", _copia["approvazioni_in_attesa"]["righe"][0]["updated_at"])
caso("_senza_campi_derivati: ultimo_commit_giorni_fa tolto", False, "ultimo_commit_giorni_fa" in _copia["attivita_git"])
caso("_senza_campi_derivati: originale intatto", 353.8, _orig["approvazioni_in_attesa"]["righe"][0]["ore_ferma"])

# job falliti: solo gli ultimi N giorni, i vecchi contati e dichiarati
_st = voce._senza_campi_derivati({
    "oggi": "2026-09-18",
    "job_falliti": {"falliti": [
        {"tipo": "digest_serale", "piu_recente": "2026-08-29T21:59:51+00:00"},
        {"tipo": "recente", "piu_recente": "2026-09-17T10:00:00+00:00"},
    ]},
})
caso("job falliti: resta solo quello recente", ["recente"], [r["tipo"] for r in _st["job_falliti"]["falliti"]])
caso("job falliti: i vecchi dichiarati, non nascosti", True, _st["job_falliti"]["falliti_piu_vecchi_omessi"].startswith("1 gruppi"))

# cantieri non chiusi raggruppati per "Aspetta", i chiusi esclusi
_st = voce._senza_campi_derivati({"cantieri_aperti": {"cantieri": [
    {"nome": "A", "stato": "aperto", "aspetta": "Leonardo"},
    {"nome": "B", "stato": "in attesa", "aspetta": "calendario"},
    {"nome": "C", "stato": "chiuso", "aspetta": "—"},
    {"nome": "D", "stato": "in attesa", "aspetta": "Leonardo"},
]}})
caso("cantieri per chi aspettano", {"Leonardo": ["A", "D"], "calendario": ["B"]},
     _st["cantieri_aperti"]["cantieri_non_chiusi_per_chi_aspettano"])

# niente rilancio, garantito dal codice
caso("_togli_rilancio: domanda finale tolta", "Fatto uno.\nFatto due.",
     voce._togli_rilancio("Fatto uno.\nFatto due.\n\nCosa specifico vuoi toccare?"))
caso("_togli_rilancio: testo senza domanda invariato", "Solo fatti.", voce._togli_rilancio("Solo fatti."))
caso("_togli_rilancio: domanda nel mezzo resta", "Chi scrive approvals?\nLo scrive il gate.",
     voce._togli_rilancio("Chi scrive approvals?\nLo scrive il gate."))
caso("_togli_rilancio: solo una domanda -> resta (mai messaggio vuoto)", "Quale file?", voce._togli_rilancio("Quale file?"))

_p = voce._prompt_conversazione(
    [{"ruolo": "leonardo", "testo": "come va?", "created_at": "t1"}, {"ruolo": "argo", "testo": "bene", "created_at": "t2"}],
    "e il gate?",
)
caso("_prompt_conversazione: storico in ordine con i ruoli", True, _p.index("Leonardo: come va?") < _p.index("Argo: bene"))
caso("_prompt_conversazione: messaggio attuale in coda", True, _p.rstrip().endswith("e il gate?"))
caso("_prompt_conversazione: messaggio non processato marcato come senza risposta", True,
     "Leonardo (arrivato mentre rispondevi, rimasto senza risposta): e il poster?" in voce._prompt_conversazione(
         [{"ruolo": "leonardo_non_processato", "testo": "e il poster?", "created_at": "t"}], "x"))
caso("_prompt_conversazione: storico vuoto dichiarato", True, "(nessuno)" in voce._prompt_conversazione([], "x"))

# genera_conversazione con chiama/stato finti: flusso a una e due chiamate, tetto
_originali = (voce.chiama, voce.raccogli_stato, voce.stato.conversazione_recente, voce._esegui_consultazione)
voce.raccogli_stato = lambda: {"oggi": "2026-09-18", "MARCATORE_STATO_INTERO": 1}
voce.stato.conversazione_recente = lambda prima_di_id, n: {"copertura": "completa", "motivo": None, "righe": []}
_chiamate = []


def _chiama_finta(risposte):
    def f(system, prompt, **kw):
        _chiamate.append(system)
        r = risposte[len(_chiamate) - 1]
        if isinstance(r, Exception):
            raise r
        return r
    return f


_eseguite = []
voce._esegui_consultazione = lambda t, a, v: (_eseguite.append((t, a)) or ("RISULTATO_FINTO", "riuscito"))

_chiamate.clear(); _eseguite.clear()
voce.chiama = _chiama_finta(['{"consultazione": null, "risposta": "Tutto fermo.\\nVuoi altro?"}'])
caso("conversazione senza consultazione: una sola chiamata", ("Tutto fermo.", None), voce.genera_conversazione(1, "come va?"))
caso("conversazione senza consultazione: nessuna consultazione eseguita", [], list(_eseguite))

_chiamate.clear(); _eseguite.clear()
voce.chiama = _chiama_finta([
    '{"consultazione": {"tipo": "impatti_componente", "argomento": "approvazione_telegram"}, "risposta": ""}',
    '{"consultazione": {"tipo": "impatti_file", "argomento": "worker/loop.py"}, "risposta": ""}',
])
_t, _c = voce.genera_conversazione(1, "cosa rischio?")
caso("una consultazione, poi seconda chiamata: esattamente due chiamate", 2, len(_chiamate))
caso("un solo giro: la seconda risposta non viene mai rieseguita come consultazione", [("impatti_componente", "approvazione_telegram")], list(_eseguite))
caso("consultazione ritornata per il mandato", {"oggetto": "conversazione: impatti_componente approvazione_telegram", "esito": "riuscito"}, _c)
caso("risultato della consultazione passato alla seconda chiamata", True, "RISULTATO_FINTO" in _chiamate[1])
caso("prima chiamata: vede lo stato intero", True, "MARCATORE_STATO_INTERO" in _chiamate[0])
caso("seconda chiamata: contesto stretto, senza lo stato intero", False, "MARCATORE_STATO_INTERO" in _chiamate[1])

_chiamate.clear(); _eseguite.clear()
voce.chiama = _chiama_finta([_Tetto("tetto")])
caso("tetto alla prima chiamata: Argo lo dice, nessuna consultazione", (voce.TESTO_TETTO_CONVERSAZIONE, None), voce.genera_conversazione(1, "x"))

_chiamate.clear(); _eseguite.clear()
voce.chiama = _chiama_finta(['{"consultazione": {"tipo": "osservazioni_recenti", "argomento": ""}, "risposta": ""}', _Tetto("tetto")])
_t, _c = voce.genera_conversazione(1, "x")
caso("tetto alla seconda chiamata: Argo lo dice", voce.TESTO_TETTO_CONVERSAZIONE, _t)
caso("tetto alla seconda chiamata: la consultazione già fatta resta da registrare", "riuscito", (_c or {}).get("esito"))

_chiamate.clear(); _eseguite.clear()
voce.chiama = _chiama_finta(['{"consultazione": {"tipo": "cancella_tutto", "argomento": ""}, "risposta": ""}'])
caso("tipo non permesso e risposta vuota -> 'non lo so' fisso", (voce.TESTO_NON_SO, None), voce.genera_conversazione(1, "x"))
caso("tipo non permesso: niente eseguito", [], list(_eseguite))

# Il tetto vale per ENTRAMBE le chiamate della conversazione: chiama finta
# che passa davvero da connectors/llm.py:_verifica_tetto, contatore
# persistente finto a un passo dal tetto -> la prima passa, la seconda no.
import os  # noqa: E402
import connectors.llm as _llm  # noqa: E402

_notifica_vera = _llm.notifica
_llm.notifica = lambda testo, token=None: None
_env_tetto = os.environ.get("LLM_TETTO_GIORNALIERO")
os.environ["LLM_TETTO_GIORNALIERO"] = "5"
_riga_tetto = {"chiamate": 4}


def _incrementa_finto(giorno):
    _riga_tetto["chiamate"] += 1
    return _riga_tetto["chiamate"]


_llm.usa_contatore_persistente(_incrementa_finto, "risposte di Argo sospese")
_risposte_tetto = [
    '{"consultazione": {"tipo": "impatti_componente", "argomento": "approvazione_telegram"}, "risposta": ""}',
    "mai restituita",
]


def _chiama_col_tetto(system, prompt, **kw):
    _llm._verifica_tetto()
    return _risposte_tetto.pop(0)


_eseguite.clear()
voce.chiama = _chiama_col_tetto
_t, _c = voce.genera_conversazione(1, "cosa rischio se tocco il gate?")
caso("tetto: la prima chiamata della conversazione conta (5/5, passa)", 1, len(_eseguite))
caso("tetto: la seconda chiamata conta anche lei (6/5) -> Argo lo dice", voce.TESTO_TETTO_CONVERSAZIONE, _t)
caso("tetto: il contatore ha visto entrambe le chiamate", 6, _riga_tetto["chiamate"])
_llm._contatore_persistente["incrementa"] = None
_llm._contatore_persistente["cosa_si_ferma"] = None
_llm.notifica = _notifica_vera
if _env_tetto is None:
    del os.environ["LLM_TETTO_GIORNALIERO"]
else:
    os.environ["LLM_TETTO_GIORNALIERO"] = _env_tetto

voce.chiama, voce.raccogli_stato, voce.stato.conversazione_recente, voce._esegui_consultazione = _originali

# Guardrail AV01 sul ramo nuovo: nessun punto del codice scrive un mandato di
# esecuzione — il tipo registrato dalla conversazione è 'consultazione' in chiaro.
for _rel in ("argo/voce.py", "scripts/argo/orienta_webhook.py", "backend/main.py"):
    _src = (REPO_ROOT / _rel).read_text(encoding="utf-8")
    caso(f"{_rel}: nessun letterale SQL 'esecuzione'", False, "'esecuzione'" in _src)
_src_consumer = (REPO_ROOT / "scripts/argo/orienta_webhook.py").read_text(encoding="utf-8")
_corpo = _src_consumer.split("def _registra_mandato_conversazione", 1)[1].split("\ndef ", 1)[0]
caso("_registra_mandato_conversazione scrive tipo 'consultazione' in chiaro", True, "'consultazione'" in _corpo)
caso("_registra_mandato_conversazione scrive origine_msg", True, "origine_msg" in _corpo)


# --- Passo 9 della voce: classificatore dei messaggi liberi ---

def _cls(**campi):
    base = {"modo": "conversazione", "minuti": None, "contesto": None,
            "oggetto": None, "nome_cantiere": None, "confidenza": 0.9}
    base.update(campi)
    return json.dumps(base)


def _errore_classificatore(grezzo):
    try:
        voce._analizza_classificazione(grezzo)
    except voce.ClassificatoreErrore as e:
        return str(e)
    return None


caso("classificatore: JSON rotto -> errore categorico", "JSON non valido", _errore_classificatore("non json"))
caso("classificatore: lista invece di oggetto -> errore", "JSON non è un oggetto", _errore_classificatore("[1]"))
caso("classificatore: modo fuori enum -> errore", "modo fuori dall'insieme chiuso",
     _errore_classificatore(_cls(modo="esegui")))
caso("classificatore: confidenza > 1 -> errore", "confidenza non valida", _errore_classificatore(_cls(confidenza=1.5)))
caso("classificatore: confidenza testo -> errore", "confidenza non valida", _errore_classificatore(_cls(confidenza="alta")))
caso("classificatore: confidenza booleana -> errore", "confidenza non valida", _errore_classificatore(_cls(confidenza=True)))

_d = voce._analizza_classificazione("```json\n" + _cls(modo="instrada", minuti=30, contesto="Computer") + "\n```")
caso("classificatore: fence markdown tollerata, modo instrada", "instrada", _d["modo"])
caso("classificatore: minuti intero", 30, _d["minuti"])
caso("classificatore: contesto normalizzato minuscolo", "computer", _d["contesto"])
caso("classificatore: minuti come stringa di cifre -> intero", 20,
     voce._analizza_classificazione(_cls(modo="instrada", minuti="20"))["minuti"])
caso("classificatore: minuti non numerici -> None, mai dedotti", None,
     voce._analizza_classificazione(_cls(modo="instrada", minuti="venti"))["minuti"])
caso("classificatore: minuti zero -> None", None,
     voce._analizza_classificazione(_cls(modo="instrada", minuti=0))["minuti"])
caso("classificatore: oggetto vuoto -> None", None,
     voce._analizza_classificazione(_cls(modo="impatto", oggetto="  "))["oggetto"])
caso("classificatore: sotto soglia -> non_chiaro", "non_chiaro",
     voce._analizza_classificazione(_cls(modo="orienta", confidenza=0.69))["modo"])
caso("classificatore: alla soglia resta il modo", "orienta",
     voce._analizza_classificazione(_cls(modo="orienta", confidenza=voce.SOGLIA_CONFIDENZA_MODO))["modo"])


def _dec(**campi):
    base = {"modo": "conversazione", "minuti": None, "contesto": None,
            "oggetto": None, "nome_cantiere": None, "confidenza": 0.9}
    base.update(campi)
    return base


caso("risolvi_modo: orienta", ("orienta", {}), voce.risolvi_modo(_dec(modo="orienta")))
caso("risolvi_modo: instrada completo", ("instrada", {"minuti": 20, "contesto": "telefono"}),
     voce.risolvi_modo(_dec(modo="instrada", minuti=20, contesto="telefono")))
caso("risolvi_modo: instrada senza minuti -> stessa domanda di /instrada",
     ("chiedi", "Quanti minuti hai?"), voce.risolvi_modo(_dec(modo="instrada", contesto="computer")))
caso("risolvi_modo: instrada senza contesto -> stessa domanda di /instrada",
     ("chiedi", "Sei al telefono o al computer?"), voce.risolvi_modo(_dec(modo="instrada", minuti=30)))
caso("risolvi_modo: instrada con contesto fuori enum -> chiede, non indovina",
     ("chiedi", "Contesto non riconosciuto: telefono o computer?"),
     voce.risolvi_modo(_dec(modo="instrada", minuti=30, contesto="tablet")))
caso("risolvi_modo: impatto con oggetto", ("impatto", {"componente": "mailer"}),
     voce.risolvi_modo(_dec(modo="impatto", oggetto="mailer")))
caso("risolvi_modo: impatto senza oggetto -> chiede", ("chiedi", "Quale componente o file?"),
     voce.risolvi_modo(_dec(modo="impatto")))
caso("risolvi_modo: brief con nome", ("brief", {"nome": "designer"}),
     voce.risolvi_modo(_dec(modo="brief", nome_cantiere="designer")))
caso("risolvi_modo: brief senza nome -> chiede", ("chiedi", "Quale cantiere?"),
     voce.risolvi_modo(_dec(modo="brief")))
caso("risolvi_modo: conversazione", ("conversazione", {}), voce.risolvi_modo(_dec()))
caso("risolvi_modo: non_chiaro -> riga fissa", ("chiedi", voce.TESTO_NON_CHIARO),
     voce.risolvi_modo(_dec(modo="non_chiaro")))
caso("TESTO_NON_CHIARO è una riga sola", 1, len(voce.TESTO_NON_CHIARO.splitlines()))

# Il prompt del classificatore resta corto: niente identità, niente stato.
caso("prompt classificatore: niente SOUL.md", False, soul.strip()[:200] in voce.SISTEMA_CLASSIFICATORE)
caso("prompt classificatore: niente IDENTITY.md", False, identity.strip()[:200] in voce.SISTEMA_CLASSIFICATORE)
caso("prompt classificatore: sotto i 3000 caratteri", True, len(voce.SISTEMA_CLASSIFICATORE) < 3000)
caso("prompt classificatore: elenca tutti i modi", True,
     all(f"- {m}:" in voce.SISTEMA_CLASSIFICATORE for m in voce.MODI_ARGO))

_p = voce._prompt_classificatore(
    [{"ruolo": "argo", "testo": "Sei al telefono o al computer?"}, {"ruolo": "leonardo", "testo": "x" * 1000}],
    "telefono",
)
caso("prompt classificatore: scambio di Argo etichettato", True, "Argo: Sei al telefono o al computer?" in _p)
caso("prompt classificatore: scambio lungo troncato", True, "x" * 1000 not in _p and "[TRONCATO" in _p)
caso("prompt classificatore: messaggio attuale in coda", True, _p.endswith("Messaggio attuale di Leonardo:\ntelefono"))
caso("prompt classificatore: finestra vuota dichiarata", True,
     "(nessuno)" in voce._prompt_classificatore([], "come sta andando?"))

# classifica_modo: chiama() mockata, nessuna rete.
_orig_chiama_cls, _orig_recente_cls = voce.chiama, voce.stato.conversazione_recente
_viste = {}


def _chiama_finta_cls(system, prompt, max_tokens=None, temperature=None, **_):
    _viste.update(system=system, prompt=prompt, max_tokens=max_tokens)
    return _cls(modo="impatto", oggetto="mailer", confidenza=0.95)


voce.chiama = _chiama_finta_cls
voce.stato.conversazione_recente = lambda prima_di_id, n: {"copertura": "assente", "motivo": "x", "righe": []}
_esito_cls = voce.classifica_modo(123, "cosa rischio se tocco mailer")
caso("classifica_modo: decisione dal JSON", ("impatto", "mailer"), (_esito_cls["modo"], _esito_cls["oggetto"]))
caso("classifica_modo: usa il prompt corto", voce.SISTEMA_CLASSIFICATORE, _viste["system"])
caso("classifica_modo: max_tokens del classificatore", voce.MAX_TOKENS_CLASSIFICATORE, _viste["max_tokens"])
caso("classifica_modo: finestra illeggibile non blocca", True, "cosa rischio se tocco mailer" in _viste["prompt"])


def _chiama_rotta(*a, **k):
    raise voce.LLMErrore("status=500")


voce.chiama = _chiama_rotta
try:
    voce.classifica_modo(123, "ciao")
    _err = None
except voce.ClassificatoreErrore as e:
    _err = str(e)
caso("classifica_modo: errore LLM -> ClassificatoreErrore", "chiamata LLM fallita", _err)
voce.chiama, voce.stato.conversazione_recente = _orig_chiama_cls, _orig_recente_cls

# Dispatch nel consumer: classifica_modo mockata, nessun DB (il mandato è mockato).
import scripts.argo.orienta_webhook as consumer  # noqa: E402

_orig_classifica, _orig_mandato = voce.classifica_modo, consumer._registra_mandato_impatto
_mandati_scritti = []
consumer._registra_mandato_impatto = lambda origine, comp: (_mandati_scritti.append((origine, comp)) or 77)
_PAYLOAD = {"conversazione_id": 5, "testo": "t", "origine_msg": "Telegram message_id=9: t"}


def _instrada_con(decisione):
    voce.classifica_modo = lambda cid, testo: decisione
    return consumer._instrada_messaggio_libero(dict(_PAYLOAD))


caso("dispatch: orienta -> genera_orienta", ("genera_orienta", {}, None), _instrada_con(_dec(modo="orienta")))
caso("dispatch: instrada -> genera_instrada coi parametri",
     ("genera_instrada", {"minuti": 30, "contesto": "computer"}, None),
     _instrada_con(_dec(modo="instrada", minuti=30, contesto="computer")))
caso("dispatch: brief -> genera_brief con origine_msg",
     ("genera_brief", {"nome": "designer", "origine_msg": _PAYLOAD["origine_msg"]}, None),
     _instrada_con(_dec(modo="brief", nome_cantiere="designer")))
caso("dispatch: impatto -> mandato registrato prima, poi genera_impatto",
     ("genera_impatto", {"componente": "mailer", "mandato_id": 77}, None),
     _instrada_con(_dec(modo="impatto", oggetto="mailer")))
caso("dispatch: mandato impatto con origine_msg del messaggio", [(_PAYLOAD["origine_msg"], "mailer")], _mandati_scritti)
caso("dispatch: conversazione resta genera_conversazione, payload intatto",
     ("genera_conversazione", _PAYLOAD, None), _instrada_con(_dec()))
caso("dispatch: parametro mancante -> riga diretta, nessun mandato",
     ("genera_conversazione", _PAYLOAD, "Quale componente o file?"), _instrada_con(_dec(modo="impatto")))
caso("dispatch: nessun mandato per la domanda", 1, len(_mandati_scritti))


def _classifica_tetto(cid, testo):
    raise voce.TettoLLMRaggiunto("tetto")


voce.classifica_modo = _classifica_tetto
caso("dispatch: tetto sul classificatore -> testo che lo dice",
     ("genera_conversazione", _PAYLOAD, voce.TESTO_TETTO_CONVERSAZIONE),
     consumer._instrada_messaggio_libero(dict(_PAYLOAD)))
voce.classifica_modo, consumer._registra_mandato_impatto = _orig_classifica, _orig_mandato

_corpo_mandato_impatto = _src_consumer.split("def _registra_mandato_impatto", 1)[1].split("\ndef ", 1)[0]
caso("_registra_mandato_impatto scrive tipo 'consultazione' in chiaro", True, "'consultazione'" in _corpo_mandato_impatto)
caso("main(): un tipo sconosciuto solleva, non cade su genera_avviso", True,
     'raise RuntimeError(f"tipo di job sconosciuto' in _src_consumer)


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
