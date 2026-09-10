"""Test di scripts/panoptes/_mappa_lib.py, stile CASI (vedi test_filtri_email.py).
Lancio: python3 tests/test_panoptes_lib.py
"""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts" / "panoptes"))

import _mappa_lib as lib  # noqa: E402

CASI = []


def caso(descrizione, atteso, ottenuto):
    CASI.append((descrizione, atteso, ottenuto))


TABELLE_NOTE = {"contacts", "identities", "events", "messages", "approvals", "jobs", "alert_inviati", "soppressioni"}

# --- parse_codice_entry ---
caso("path nudo", ("worker/loop.py", None, None), lib.parse_codice_entry("worker/loop.py"))
caso("path con riga singola", ("worker/loop.py", 1230, 1230), lib.parse_codice_entry("worker/loop.py:1230"))
caso("path con range", ("worker/loop.py", 151, 216), lib.parse_codice_entry("worker/loop.py:151-216"))

# --- bilancia_parentesi ---
caso("parentesi semplice", 16, lib.bilancia_parentesi("cur.execute(x, y)", 11))
testo_annidato = "f(VALUES (%s, %s), 3)"
caso("parentesi annidate", len(testo_annidato) - 1, lib.bilancia_parentesi(testo_annidato, 1))
caso("parentesi sbilanciata", -1, lib.bilancia_parentesi("f(x, y", 1))

# --- estrai_blocchi_execute (multi-riga, con JOIN su riga diversa dal SELECT) ---
blocco_multiriga = (
    "prima riga di contesto\n"
    "cur.execute(\n"
    '    """\n'
    "    SELECT m.thread_id, m.canale\n"
    "    FROM messages m JOIN events e ON m.thread_id = e.id::text\n"
    "    WHERE m.id = %s\n"
    '    """,\n'
    "    (approval_id,),\n"
    ")\n"
)
blocchi = lib.estrai_blocchi_execute(blocco_multiriga)
caso("un solo blocco execute trovato", 1, len(blocchi))
caso("riga del blocco execute (riga 2, dopo il contesto)", 2, blocchi[0][0] if blocchi else None)
caso(
    "blob concatenato contiene sia SELECT che il JOIN su riga diversa",
    True,
    ("SELECT" in blocchi[0][1] and "JOIN events e" in blocchi[0][1]) if blocchi else False,
)

# --- estrai_verbo_e_tabella ---
caso(
    "INSERT INTO riconosciuto",
    ("INSERT", "messages", False),
    (lambda r: (r[0][0], r[0][1], r[0][2]))(lib.estrai_verbo_e_tabella("INSERT INTO messages (x) VALUES (%s)", TABELLE_NOTE)),
)
caso(
    "UPDATE riconosciuto",
    ("UPDATE", "approvals", False),
    (lambda r: (r[0][0], r[0][1], r[0][2]))(lib.estrai_verbo_e_tabella("UPDATE approvals SET stato = %s WHERE id = %s", TABELLE_NOTE)),
)
caso(
    "DELETE FROM riconosciuto",
    ("DELETE", "jobs", False),
    (lambda r: (r[0][0], r[0][1], r[0][2]))(lib.estrai_verbo_e_tabella("DELETE FROM jobs WHERE id = %s", TABELLE_NOTE)),
)
caso(
    "SELECT con JOIN produce due tabelle",
    {"messages", "events"},
    {t[1] for t in lib.estrai_verbo_e_tabella("SELECT * FROM messages m JOIN events e ON m.thread_id = e.id::text", TABELLE_NOTE)},
)
caso(
    "tabella non nota è indecidibile, non una divergenza",
    True,
    lib.estrai_verbo_e_tabella("INSERT INTO tabella_fantasma (x) VALUES (%s)", TABELLE_NOTE)[0][2],
)
caso(
    "SELECT senza FROM riconoscibile (f-string dinamica) è indecidibile",
    True,
    lib.estrai_verbo_e_tabella("SELECT * FROM {tabella} WHERE x = %s", TABELLE_NOTE)[0][2],
)
caso("query irrilevante (nessun verbo) non produce risultati", [], lib.estrai_verbo_e_tabella("SET timezone = 'UTC'", TABELLE_NOTE))
caso(
    "SELECT senza FROM (funzione, es. setseed) non è indecidibile: nessuna tabella coinvolta",
    [],
    lib.estrai_verbo_e_tabella("SELECT setseed(%s)", TABELLE_NOTE),
)
caso(
    "query costruita in una variabile (cur.execute(query)) è indecidibile esplicito, non un buco silenzioso",
    True,
    lib.estrai_verbo_e_tabella("query, params", TABELLE_NOTE)[0][2],
)
caso(
    "query costruita in una variabile senza parametri (cur.execute(query))",
    True,
    lib.estrai_verbo_e_tabella("query", TABELLE_NOTE)[0][2],
)

# --- estrai_env_da_blob ---
caso(
    "tre stili di lettura env nella stessa riga",
    {"PG_PASSWORD", "REPLY_SMTP_USER", "WARMUP_TAG"},
    lib.estrai_env_da_blob('os.environ["PG_PASSWORD"] os.environ.get("REPLY_SMTP_USER", "x") os.getenv("WARMUP_TAG")'),
)

# --- filtra_env_infrastruttura ---
caso("PG_* escluso, il resto resta", {"REPLY_SMTP_USER"}, lib.filtra_env_infrastruttura({"PG_PASSWORD", "REPLY_SMTP_USER"}))

# --- intervalli_si_sovrappongono ---
caso("overlap parziale", True, lib.intervalli_si_sovrappongono(1225, 1240, 1228, 1232))
caso("overlap sul confine (toccano)", True, lib.intervalli_si_sovrappongono(1225, 1230, 1230, 1240))
caso("nessun overlap", False, lib.intervalli_si_sovrappongono(1225, 1240, 1311, 1322))

# --- estrai_riferimenti_garantito_da ---
caso(
    "riferimento singolo",
    [("worker/loop.py", 1228, 1232)],
    lib.estrai_riferimenti_garantito_da("worker/loop.py:1228-1232 (guardia stato)"),
)
caso(
    "PH04: lista comma-separata di range sullo stesso file, nessuno perso",
    [("worker/loop.py", 186, 193), ("worker/loop.py", 246, 253), ("worker/loop.py", 294, 301)],
    lib.estrai_riferimenti_garantito_da(
        "indice unico messages_thread_canale_direzione_uniq + guardia ON CONFLICT ... "
        "DO NOTHING RETURNING id in worker/loop.py:186-193,246-253,294-301"
    ),
)
caso(
    "numeri fra parentesi senza file.py: davanti non sono un riferimento",
    [],
    lib.estrai_riferimenti_garantito_da("scrive solo approvals (1088-1099) e chiama chiedi_approvazione (1102)"),
)
caso("garantito_da 'nessuno' non produce riferimenti", [], lib.estrai_riferimenti_garantito_da("nessuno"))

# --- nomi_tabelle_canoniche (integrazione leggera sul vero db/schema.sql) ---
caso(
    "le 8 tabelle note sono tutte in db/schema.sql",
    TABELLE_NOTE,
    lib.nomi_tabelle_canoniche(REPO_ROOT / "db" / "schema.sql"),
)

# --- schede_che_toccano / condivisi_referenziati (su una mappa finta minimale) ---
MAPPA_FINTA = {
    "pipeline": [
        {
            "nome": "pl_a",
            "codice": ["worker/x.py:100-200"],
            "condivisi": ["cond_a", "cond_fantasma"],
        },
        {
            "nome": "pl_b",
            "codice": ["worker/y.py"],  # bare: tutto il file
        },
    ],
    "condivisi": [
        {"nome": "cond_a", "codice": ["worker/z.py:10-20"], "usato_da": ["pl_a"]},
    ],
}

pm, cm = lib.schede_che_toccano(MAPPA_FINTA, "worker/x.py", 150, 160)
caso("range dentro un codice dichiarato: matcha la pipeline", ["pl_a"], [p["nome"] for p in pm])

pm2, cm2 = lib.schede_che_toccano(MAPPA_FINTA, "worker/x.py", 500, 600)
caso("range fuori dal codice dichiarato: nessun match", [], [p["nome"] for p in pm2])

pm3, cm3 = lib.schede_che_toccano(MAPPA_FINTA, "worker/y.py", 9999, 9999)
caso("path bare matcha qualunque riga", ["pl_b"], [p["nome"] for p in pm3])

pm4, cm4 = lib.schede_che_toccano(MAPPA_FINTA, "worker/z.py", 15, 15)
caso("range dentro un condiviso: matcha il condiviso", ["cond_a"], [c["nome"] for c in cm4])

risolti, mancanti = lib.condivisi_referenziati(MAPPA_FINTA["pipeline"][0], MAPPA_FINTA)
caso("condiviso esistente risolto", ["cond_a"], [c["nome"] for c in risolti])
caso("condiviso mancante segnalato, non silenziato", ["cond_fantasma"], mancanti)


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
