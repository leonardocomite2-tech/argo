"""Test di argo/impara.py e del ramo USER.md del consumer (passo 14 della
voce), stile CASI. Zero rete, zero DB: lettori, psql e file sono finti.
Lancio: python3 tests/test_argo_impara.py
"""
import re
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import argo.impara as impara  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


def _t(giorno, ora_roma):
    """Istante UTC per il giorno di settembre e l'ora di Roma (CEST, +2)."""
    return datetime(2026, 9, giorno, ora_roma, 0, tzinfo=impara.FUSO_ROMA).astimezone(timezone.utc)


OGGI = date(2026, 9, 19)

# --- guardrail statici ---
_src = (REPO_ROOT / "argo" / "impara.py").read_text(encoding="utf-8")
caso("impara.py: nessuna chiamata LLM", [], re.findall(r"\bchiama\(|connectors\.llm|anthropic|openrouter", _src))
caso("impara.py: nessun verbo di scrittura SQL", [], re.findall(r"\b(INSERT|UPDATE|DELETE)\b", _src))
caso("impara.py: nessuna scrittura su file", [], re.findall(r"write_text|\.write\(|os\.replace|open\(", _src))

_src_consumer = (REPO_ROOT / "scripts/argo/orienta_webhook.py").read_text(encoding="utf-8")
_funzioni = re.split(r"\ndef ", _src_consumer)
_scrivono = [f.split("(", 1)[0] for f in _funzioni if re.search(r"os\.replace|write_text|\.write\(", f)]
caso("consumer: solo _scrivi_user_md scrive un file", ["_scrivi_user_md"], _scrivono)
_chiamanti = [f.split("(", 1)[0] for f in _funzioni[1:] if "_scrivi_user_md(" in f and not f.startswith("_scrivi_user_md(")]
caso("consumer: _scrivi_user_md chiamata solo dal ramo del sì", ["_risposta_a_proposta"], _chiamanti)
_corpo_risposta = _src_consumer.split("def _risposta_a_proposta", 1)[1].split("\ndef ", 1)[0]
caso("ramo del sì: e_si controllato prima di scrivere", True,
     _corpo_risposta.index("impara.e_si(") < _corpo_risposta.index("_scrivi_user_md("))
caso("ramo del sì: nessun LLM", [], re.findall(r"\bchiama\b|classifica_modo", _corpo_risposta))

# --- fasce ---
caso("fascia: 10 di Roma = mattina", "mattina", impara.fascia_di(_t(18, 10)))
caso("fascia: 01 di Roma = notte", "notte", impara.fascia_di(_t(12, 1)))
caso("fascia: 12 di Roma = pomeriggio", "pomeriggio", impara.fascia_di(_t(12, 12)))
caso("fascia: 21 di Roma = sera", "sera", impara.fascia_di(_t(18, 21)))
caso("fascia: 23:30 UTC = notte a Roma (fuso)", "notte",
     impara.fascia_di(datetime(2026, 9, 18, 23, 30, tzinfo=timezone.utc)))

# I dati veri del 19/9: 19 richieste in 5 giorni.
_ORE_VERE = [(12, 1), (18, 10), (18, 10), (19, 10), (18, 10), (13, 11), (18, 11), (18, 11), (18, 11),
             (11, 12), (12, 12), (12, 13), (12, 13), (11, 14), (18, 14), (18, 14), (11, 15), (11, 15), (18, 21)]
_VERE = [_t(g, h) for g, h in _ORE_VERE]
caso("fascia: sotto soglia -> nessun fatto", [], impara.calcola_fatti(_VERE, []))
_forzati = impara.calcola_fatti(_VERE, [], forza=True)
caso("fascia forzata: conteggi e campione dichiarati",
     "- 19/09 — Richieste ad Argo per fascia oraria: pomeriggio 9, mattina 8, notte 1, sera 1 su 19 "
     "(11/09–19/09, 5 giorni) [fascia_oraria:nessuna_prevalente]",
     impara.riga_per(_forzati[0], OGGI))

_MOLTE = [_t(1 + i % 10, 10) for i in range(15)] + [_t(1 + i, 15) for i in range(6)]
caso("fascia sopra soglia: mattina prevalente", ("fascia_oraria", "mattina"),
     (impara.calcola_fatti(_MOLTE, [])[0]["tipo"], impara.calcola_fatti(_MOLTE, [])[0]["valore"]))
_POCHI_GIORNI = [_t(1 + i % 3, 10) for i in range(25)]
caso("fascia: 25 richieste ma 3 giorni -> niente", [], impara.calcola_fatti(_POCHI_GIORNI, []))
_SENZA_PREV = [_t(1 + i % 10, 10) for i in range(10)] + [_t(1 + i % 10, 15) for i in range(10)] + [_t(5, 21)]
caso("fascia: nessuna fascia al 50% -> niente in produzione", [], impara.calcola_fatti(_SENZA_PREV, []))

# --- finestre ---
_F = [(_t(1 + i, 9), m, "telefono") for i, m in enumerate([10, 15, 20, 15, 10])]
_ff = impara.calcola_fatti([], _F)
caso("finestra telefono sopra soglia: mediana bassa", ("finestra_telefono", "15"), (_ff[0]["tipo"], _ff[0]["valore"]))
caso("finestra: riga", "Finestre dichiarate al telefono: mediana 15 minuti su 5 richieste (da 10 a 20, 01/09–05/09)",
     _ff[0]["testo"])
caso("finestra: 4 dichiarazioni -> niente", [], impara.calcola_fatti([], _F[:4]))
caso("finestra: 5 dichiarazioni in 2 giorni -> niente", [],
     impara.calcola_fatti([], [(_t(1 + i % 2, 9), 10, "telefono") for i in range(5)]))
caso("finestra: il computer non conta per il telefono", [],
     impara.calcola_fatti([], [(t, m, "computer") for t, m, _ in _F[:2]]))
caso("finestra forzata: una richiesta, al singolare", True,
     "su 1 richiesta (" in impara.calcola_fatti([], [(_t(11, 15), 15, "telefono")], forza=True)[0]["testo"])

# --- riga: formato, validazione, chiave ---
_RIGA = "- 19/09 — Finestre dichiarate al telefono: mediana 15 minuti su 5 richieste (da 10 a 20, 01/09–05/09) [finestra_telefono:15]"
caso("analizza_riga: valida", ("finestra_telefono", "15"), impara.analizza_riga(_RIGA))
caso("analizza_riga: tipo fuori dall'insieme chiuso", None, impara.analizza_riga("- 19/09 — Lavora male [umore:basso]"))
caso("analizza_riga: email rifiutata", None, impara.analizza_riga("- 19/09 — scrive a a@b.it [fascia_oraria:sera]"))
caso("analizza_riga: URL rifiutato", None, impara.analizza_riga("- 19/09 — vedi https://x.it [fascia_oraria:sera]"))
caso("analizza_riga: troppo lunga", None, impara.analizza_riga("- 19/09 — " + "x" * 250 + " [fascia_oraria:sera]"))
caso("analizza_riga: senza chiave", None, impara.analizza_riga("- 19/09 — Richieste ad Argo"))
caso("chiave", "finestra_telefono:15", impara.chiave(_RIGA))

_PROP = impara.testo_proposta(_RIGA)
caso("proposta: contiene la riga esatta", True, _RIGA in _PROP)
caso("proposta: dice come rispondere", True, "Rispondi sì" in _PROP)
caso("estrai_riga_proposta: la riga della proposta", _RIGA, impara.estrai_riga_proposta(_PROP))
_VECCHIA = _RIGA.replace("15 minuti", "10 minuti").replace(":15]", ":10]").replace("19/09", "01/09")
caso("estrai_riga_proposta: con 'Al posto di' prende la nuova", _RIGA,
     impara.estrai_riga_proposta(impara.testo_proposta(_RIGA, _VECCHIA)))
caso("estrai_riga_proposta: testo qualunque -> None", None, impara.estrai_riga_proposta("Ciao, tutto bene."))
caso("estrai_riga_proposta: None -> None", None, impara.estrai_riga_proposta(None))

# --- sì / no ---
for _t_si in ("sì", "Sì", "si", "SI.", " sì! ", "sí"):
    caso(f"e_si: {_t_si!r}", True, impara.e_si(_t_si))
for _t_non_si in ("sì ma cambia la data", "ok", "va bene", "no", "", None, "sìsì"):
    caso(f"e_si: {_t_non_si!r} non conferma", False, impara.e_si(_t_non_si))
caso("e_no: 'No.'", True, impara.e_no("No."))
caso("e_no: 'no, aspetta'", False, impara.e_no("no, aspetta"))

# --- USER.md ---
# Base dei test: il vero USER.md senza le righe già scritte da Argo (dopo un
# sì il file cambia; i test non devono dipendere da cosa è stato confermato).
_USER_VERO = (REPO_ROOT / "knowledge" / "argo" / "USER.md").read_text(encoding="utf-8")
_USER = "\n".join(r for r in _USER_VERO.split("\n") if not impara.analizza_riga(r))
caso("USER.md vero: al massimo una riga di Argo per tipo", True,
     len([r for r in _USER_VERO.split("\n") if impara.analizza_riga(r)])
     == len({impara.analizza_riga(r)[0] for r in _USER_VERO.split("\n") if impara.analizza_riga(r)}))
caso("USER.md vero: sta nel tetto", True, len(_USER_VERO) <= impara.LIMITE_USER_MD_CARATTERI)
caso("USER.md: il blocco di Argo esiste", True, impara.INTESTAZIONE_BLOCCO in _USER.split("\n"))
caso("USER.md: sta nel tetto", True, len(_USER) <= impara.LIMITE_USER_MD_CARATTERI)
_u1 = impara.applica_riga(_USER, _RIGA)
caso("applica: riga aggiunta subito sotto il blocco", impara.INTESTAZIONE_BLOCCO + "\n" + _RIGA, _u1.split("\n## Cosa lo blocca")[0][-len(impara.INTESTAZIONE_BLOCCO + "\n" + _RIGA) - 1:].strip())
caso("applica: il resto del file invariato", _USER, _u1.replace(_RIGA + "\n", "", 1))
caso("applica: idempotente", _u1, impara.applica_riga(_u1, _RIGA))
_RIGA_FASCIA = impara.riga_per(_forzati[0], OGGI)
_u2 = impara.applica_riga(_u1, _RIGA_FASCIA)
caso("applica: un secondo tipo si aggiunge dopo", [_RIGA, _RIGA_FASCIA],
     [r for r in _u2.split("\n") if impara.analizza_riga(r)])
_NUOVA = _RIGA.replace("mediana 15", "mediana 20").replace(":15]", ":20]")
_u3 = impara.applica_riga(_u2, _NUOVA)
caso("applica: stesso tipo sostituisce, non accumula", [_NUOVA, _RIGA_FASCIA],
     [r for r in _u3.split("\n") if impara.analizza_riga(r)])
caso("riga_esistente: per tipo", _RIGA_FASCIA, impara.riga_esistente(_u3, "fascia_oraria"))
caso("riga_esistente: tipo assente", None, impara.riga_esistente(_USER, "finestra_computer"))


def _errore(funzione, *argomenti):
    try:
        funzione(*argomenti)
    except impara.UserMdErrore as e:
        return str(e)
    return None


caso("applica: blocco mancante -> errore", "blocco delle righe di Argo mancante in USER.md",
     _errore(impara.applica_riga, "# USER\n", _RIGA))
caso("applica: riga non valida -> errore", "riga non valida", _errore(impara.applica_riga, _USER, "- testo libero"))
caso("applica: oltre il tetto -> errore", True,
     "supererebbe" in (_errore(impara.applica_riga, _USER + "x" * impara.LIMITE_USER_MD_CARATTERI, _RIGA) or ""))
caso("applica: le righe fuori dal blocco non contano", _USER.replace(impara.INTESTAZIONE_BLOCCO, impara.INTESTAZIONE_BLOCCO + "\n" + _RIGA),
     impara.applica_riga(_USER, _RIGA))

# --- scelta e cadenza ---
_fatti = impara.calcola_fatti(_VERE, [(_t(11, 15), 15, "telefono")], forza=True)
caso("scegli: il campione più grande per primo", (_RIGA_FASCIA, None), impara.scegli_proposta(_fatti, set(), _USER, OGGI))
caso("scegli: chiave già proposta salta al fatto dopo", "finestra_telefono:15",
     impara.chiave(impara.scegli_proposta(_fatti, {"fascia_oraria:nessuna_prevalente"}, _USER, OGGI)[0]))
caso("scegli: tutte già proposte -> None", None,
     impara.scegli_proposta(_fatti, {"fascia_oraria:nessuna_prevalente", "finestra_telefono:15"}, _USER, OGGI))
caso("scegli: già nel file con la stessa chiave -> non si ripropone", "finestra_telefono:15",
     impara.chiave(impara.scegli_proposta(_fatti, set(), _u2.replace(_RIGA + "\n", ""), OGGI)[0]))
_vecchia_file = _RIGA.replace("mediana 15", "mediana 10").replace(":15]", ":10]")
_u_vecchia = impara.applica_riga(_USER, _vecchia_file)
caso("scegli: valore nuovo -> propone la sostituzione dichiarandola", _vecchia_file,
     impara.scegli_proposta(_fatti[1:], set(), _u_vecchia, OGGI)[1])
caso("scegli: file pieno -> None", None,
     impara.scegli_proposta(_fatti, set(), _USER + "x" * impara.LIMITE_USER_MD_CARATTERI, OGGI))

_PROPOSTE = [{"id": 30, "created_at": "2026-09-19T08:00:00+00:00", "testo": _PROP}]
caso("chiavi_proposte: dalle righe passate", {"finestra_telefono:15"}, impara.chiavi_proposte(_PROPOSTE))
caso("proposta_oggi: sì", True, impara.proposta_oggi(_PROPOSTE, OGGI))
caso("proposta_oggi: ieri no", False, impara.proposta_oggi(_PROPOSTE, OGGI + timedelta(days=1)))
caso("proposta_oggi: 23:30 UTC del 18 è il 19 a Roma", True,
     impara.proposta_oggi([{"created_at": "2026-09-18T23:30:00+00:00"}], OGGI))


def _prepara(proposte, richieste, finestre, forza=False):
    orig = impara.proposte_passate, impara.richieste_leonardo, impara.finestre_dichiarate, impara.USER_MD_PATH
    impara.USER_MD_PATH = Path(tempfile.mkdtemp()) / "USER.md"
    impara.USER_MD_PATH.write_text(_USER, encoding="utf-8")
    impara.proposte_passate = lambda: proposte
    impara.richieste_leonardo = lambda: richieste
    impara.finestre_dichiarate = lambda: finestre
    try:
        return impara.prepara_proposta(forza=forza, ora=datetime(2026, 9, 19, 12, 0, tzinfo=impara.FUSO_ROMA))
    finally:
        impara.proposte_passate, impara.richieste_leonardo, impara.finestre_dichiarate, impara.USER_MD_PATH = orig


caso("prepara: dati veri sotto soglia -> nessuna proposta", (None, "nessun fatto sopra soglia"), _prepara([], _VERE, []))
caso("prepara: forzata -> proposta della fascia", _RIGA_FASCIA,
     impara.estrai_riga_proposta(_prepara([], _VERE, [], forza=True)[0]))
caso("prepara: già una proposta oggi -> niente", (None, "già una proposta oggi"), _prepara(_PROPOSTE, _MOLTE, []))
caso("prepara: forzata ignora il tetto giornaliero, non la chiave", True,
     _prepara(_PROPOSTE, [], _F, forza=True) == (None, "nessun fatto nuovo da proporre"))

# --- consumer: sì/no prima del classificatore, scrittura del file ---
import argo.stato as stato  # noqa: E402
import scripts.argo.orienta_webhook as consumer  # noqa: E402

_orig_recente, _orig_path = stato.conversazione_recente, impara.USER_MD_PATH
_tmpdir = Path(tempfile.mkdtemp())
impara.USER_MD_PATH = _tmpdir / "USER.md"


def _risposta(ruolo_prec, testo_prec, messaggio):
    impara.USER_MD_PATH.write_text(_USER, encoding="utf-8")
    stato.conversazione_recente = lambda cid, n: {
        "copertura": "completa", "motivo": None,
        "righe": [{"id": 40, "ruolo": ruolo_prec, "testo": testo_prec}],
    }
    return consumer._risposta_a_proposta({"conversazione_id": 41, "testo": messaggio, "origine_msg": "x"})


caso("consumer: sì dopo una proposta -> scritta", impara.TESTO_SCRITTA, _risposta("argo_proposta", _PROP, "Sì"))
caso("consumer: la riga è nel file", True, _RIGA in impara.USER_MD_PATH.read_text(encoding="utf-8"))
caso("consumer: nessun file temporaneo lasciato", ["USER.md"], sorted(p.name for p in _tmpdir.iterdir()))
caso("consumer: no -> lasciata, file invariato", (impara.TESTO_LASCIATA, _USER),
     (_risposta("argo_proposta", _PROP, "no"), impara.USER_MD_PATH.read_text(encoding="utf-8")))
caso("consumer: 'sì ma...' -> None (va al classificatore), file invariato", (None, _USER),
     (_risposta("argo_proposta", _PROP, "sì ma cambia la data"), impara.USER_MD_PATH.read_text(encoding="utf-8")))
caso("consumer: sì dopo una risposta normale di Argo -> None", (None, _USER),
     (_risposta("argo", _PROP, "sì"), impara.USER_MD_PATH.read_text(encoding="utf-8")))
caso("consumer: proposta senza riga valida -> non scritta", (True, _USER),
     (_risposta("argo_proposta", "Per USER.md: boh", "sì").startswith("Non l'ho scritta"),
      impara.USER_MD_PATH.read_text(encoding="utf-8")))
stato.conversazione_recente = lambda cid, n: {"copertura": "assente", "motivo": "x", "righe": []}
caso("consumer: finestra illeggibile -> None", None,
     consumer._risposta_a_proposta({"conversazione_id": 41, "testo": "sì", "origine_msg": "x"}))
stato.conversazione_recente, impara.USER_MD_PATH = _orig_recente, _orig_path

# _registra_finestra e _registra_proposta: SQL composto, psql finto.
_sql = []
_orig_psql = consumer._psql
consumer._psql = lambda sql, timeout=15: _sql.append(sql) or ""
consumer._registra_finestra(12, {"minuti": 20, "contesto": "telefono"})
consumer._registra_proposta("riga con l'apostrofo")
consumer._psql = _orig_psql
caso("finestra: chiavi aggiunte al payload del job",
     """UPDATE jobs SET payload = payload || '{"modo": "instrada", "minuti": 20, "contesto": "telefono"}'::jsonb WHERE id=12""",
     _sql[0])
caso("proposta: ruolo argo_proposta, apostrofo raddoppiato",
     "INSERT INTO conversazione_argo (ruolo, testo) VALUES ('argo_proposta', 'riga con l''apostrofo')", _sql[1])

# _forse_proponi: quando non prova nemmeno.
_orig_prepara = impara.prepara_proposta
_chiamate = []
impara.prepara_proposta = lambda: _chiamate.append(1) or (None, "x")
consumer._forse_proponi("genera_brief", "testo")
consumer._forse_proponi("genera_conversazione", "Quale cantiere?")
import argo.voce as voce  # noqa: E402
consumer._forse_proponi("genera_conversazione", voce.TESTO_TETTO_CONVERSAZIONE)
caso("forse_proponi: mai dopo brief, domanda o tetto", [], list(_chiamate))
consumer._forse_proponi("genera_instrada", "Chiudi l'approvazione #10.")
caso("forse_proponi: dopo instrada prova", [1], list(_chiamate))
impara.prepara_proposta = _orig_prepara


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
