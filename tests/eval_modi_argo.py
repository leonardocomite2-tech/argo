"""python3 tests/eval_modi_argo.py [giri]

Chiama l'API Anthropic per davvero (non è un mock): misura le risposte dei
modi di Argo (argo/voce.py) sullo stato vero del sistema, letto in sola
lettura. Nessuna scrittura su DB, nessun Telegram. Va rilanciato dopo ogni
modifica a SOUL.md o alle ISTRUZIONI_* dei modi.

Controlla i tre difetti del collaudo del passo 9 (passo 10 della voce):
- nessun backtick nel testo (garantito da _senza_backtick, qui verificato
  sul testo che partirebbe davvero);
- nessuna azione su cose che girano già (lista nera euristica: avviare o
  lanciare il consumer, il cron, il deploy, git push — non prova che ogni azione
  proposta sia fondata, prova che quella già vista non torna);
- in impatto, nessun totale di contratti scritto dal modello: il totale lo
  aggiunge il codice nell'ultima riga "Contratti in gioco (N)". Il numero di
  pipeline è ammesso: lo dà impatti.py stesso (riga TRASVERSALE).

Passo 11 della voce, dal collaudo del passo 10:
- orienta, instrada e conversazione finiscono con la riga "Fatti" scritta
  dal codice, che nomina ogni approvazione in attesa per #id; nessuna frase
  nega le approvazioni, e con qualcosa in attesa nessun "niente da fare"
  (la conversazione "Come sta andando?" diceva "nessuna approvazione in
  attesa" con la #10 ferma);
- brief: un cantiere non "aperto" dà la riga fissa, mai un brief (la
  voce); su un cantiere aperto (il ponte) l'obiettivo non ripropone un
  passo già committato (euristica: un "passo N" dei commit del cantiere
  nell'obiettivo è ammesso solo se detto già fatto/committato, o se
  l'obiettivo è "Da precisare" — non prova che il lavoro chiuso non sia
  descritto con altre parole).

Passo 12 della voce, dal collaudo del passo 11 ("Come collauderesti argo
voce": quattro paragrafi, "argo/consumer_voce.log o ps aux | grep
consumer"). Su ogni conversazione, nel corpo sopra la riga Fatti:
- al massimo MAX_RIGHE_CONVERSAZIONE righe non vuote e
  MAX_CARATTERI_CONVERSAZIONE caratteri;
- nessuna domanda, salvo quella su un parametro ("Quale...");
- ogni nome di file con estensione esiste nel repo (sul percorso scritto o
  come nome di un file qualunque del repo), niente pipe, niente "ps aux",
  nessun comando Telegram fuori dai COMANDO_* di backend/main.py.
  Controllo indipendente da _togli_riferimenti_inventati: guarda il disco,
  non i dati passati al modello.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

import argo.voce as voce  # noqa: E402

AZIONI_GIA_IN_FUNZIONE = re.compile(
    r"\b(avvia\w*|lancia\w*|attiva\w*|fai partire|metti in cron|configura\w*)\b[^.\n]{0,40}"
    r"\b(consumer|cron\w*|deploy|worker)\b"
    r"|\bdocker compose up\b|\bfai il deploy\b|\bfare il deploy\b"
    r"|\bgit push\b",  # collaudo passo 10: "Poi git push" con il repo già allineato a origin
    re.IGNORECASE,
)
NUMERI = r"(\d+|due|tre|quattro|cinque|sei|sette|otto|nove|dieci|undici|dodici)"
TOTALE_DEL_MODELLO = re.compile(
    rf"\b{NUMERI}\s+contratti\b|\bcontratti\b[^.\n]{{0,30}}\bsono\s+{NUMERI}\b|\b(gli )?altri {NUMERI}\b",
    re.IGNORECASE,
)
RIGA_TOTALE = re.compile(r"\n\nContratti in gioco \(\d+\): [^\n]+\.$")

NEGA_APPROVAZIONI = re.compile(
    r"\b(nessun\w*|zero|non (ci )?sono|niente)\b[^.\n]{0,20}\bapprovazion", re.IGNORECASE
)
NIENTE_DA_FARE = re.compile(r"\b(niente|nulla) da fare\b|\bnon c'è (niente|nulla)\b", re.IGNORECASE)
MAX_RIGHE_CONVERSAZIONE = 3
MAX_CARATTERI_CONVERSAZIONE = 500
NOME_FILE = re.compile(r"[\w./-]*\w\.(py|log|md|yaml|yml|sql|sh|json|txt)\b")
COMANDI_TELEGRAM = set(re.findall(r'^COMANDO_\w+ = "(/\w+)"', (REPO_ROOT / "backend" / "main.py").read_text(encoding="utf-8"), re.MULTILINE))
NOMI_FILE_REPO = {f.name for f in REPO_ROOT.rglob("*") if ".git" not in f.parts}
GIA_CHIUSO = re.compile(r"già (committat|fatt|chius|implementat)\w*|^\s*Da precisare con Leonardo", re.IGNORECASE | re.MULTILINE)


def _conversazione(messaggio):
    voce.stato.conversazione_recente = lambda prima_di_id, n: {"copertura": "completa", "motivo": None, "righe": []}
    return voce.genera_conversazione(0, messaggio)[0]


CASI = [
    ("instrada 30/computer", lambda: voce.genera_risposta_instrada(30, "computer"), "proposta"),
    ("instrada 10/telefono", lambda: voce.genera_risposta_instrada(10, "telefono"), "proposta"),
    ("orienta", lambda: voce.genera_risposta(), "proposta"),
    ("conversazione come sta andando", lambda: _conversazione("Come sta andando?"), "conversazione"),
    ("conversazione come collauderesti", lambda: _conversazione("Come collauderesti argo voce"), "conversazione"),
    ("impatto mailer", lambda: voce.genera_impatto("mailer")[0], "impatto"),
    ("impatto approvals", lambda: voce.genera_impatto("approvals")[0], "impatto"),
    ("brief il ponte", lambda: ("il ponte", voce.genera_brief("il ponte")[0]), "brief"),
    ("brief la voce", lambda: ("la voce", voce.genera_brief("la voce")[0]), "brief"),
]


def _controlla_fatti(testo):
    problemi = []
    righe = testo.rstrip().splitlines()
    if not righe or not righe[-1].startswith("Fatti: "):
        return ["riga Fatti mancante in coda"]
    appr = voce.stato.approvazioni_in_attesa()
    if appr["copertura"] != "assente":
        for r in appr["righe"]:
            if f"#{r['id']}" not in righe[-1]:
                problemi.append(f"approvazione #{r['id']} assente dalla riga Fatti")
    corpo = "\n".join(righe[:-1])
    m = NEGA_APPROVAZIONI.search(corpo)
    if m:
        problemi.append(f"approvazioni negate dal modello: {m.group(0)!r}")
    if appr["righe"]:
        m = NIENTE_DA_FARE.search(corpo)
        if m:
            problemi.append(f"'niente da fare' con approvazioni in attesa: {m.group(0)!r}")
    return problemi


def _controlla_conversazione(testo):
    problemi = []
    corpo = testo.rstrip().rsplit("\n\nFatti: ", 1)[0]
    righe = [r for r in corpo.splitlines() if r.strip()]
    if len(righe) > MAX_RIGHE_CONVERSAZIONE or len(corpo) > MAX_CARATTERI_CONVERSAZIONE:
        problemi.append(f"troppo lunga: {len(righe)} righe, {len(corpo)} caratteri")
    for frase in re.split(r"(?<=[.!?])\s+", corpo):
        if frase.strip().endswith("?") and not re.match(r"\s*(di |su |a |in )?qual", frase, re.IGNORECASE):
            problemi.append(f"domanda: {frase.strip()!r}")
    for m in NOME_FILE.finditer(corpo):
        nome = m.group(0)
        if not (REPO_ROOT / nome.lstrip("/")).exists() and nome.rsplit("/", 1)[-1] not in NOMI_FILE_REPO:
            problemi.append(f"file inesistente: {nome!r}")
    for m in re.finditer(r"(?<![\w/.-])/[a-z_]+\b(?!/)", corpo):
        if m.group(0) not in COMANDI_TELEGRAM:
            problemi.append(f"comando Telegram inesistente: {m.group(0)!r}")
    if "|" in corpo or re.search(r"\bps aux\b", corpo):
        problemi.append("comando di shell")
    return problemi


def _controlla_brief(nome_utente, testo):
    cantiere = voce._risolvi_cantiere(nome_utente, voce.stato.cantieri_aperti()["cantieri"])[0]
    if cantiere["stato"].strip().lower() != "aperto":
        # Cantiere non aperto: riga fissa, mai un brief generato.
        return [] if "Nessun lavoro di codice aperto" in testo and "## Obiettivo" not in testo \
            else [f"brief generato per un cantiere {cantiere['stato']}"]
    parti = testo.split("## Obiettivo", 1)
    if len(parti) < 2:
        return ["brief senza Obiettivo per un cantiere aperto"]
    obiettivo = parti[1].split("## Vincoli", 1)[0]
    nome = cantiere["nome"]
    commit = voce._commit_del_cantiere(nome, voce.stato.attivita_git())["righe"]
    # Un passo che la riga CANTIERI nomina ancora (es. "passo 4 ... resta a
    # Leonardo il collaudo reale") è in gioco, non chiuso: ammesso.
    nella_riga = {m.group(0).lower() for m in re.finditer(r"passo \d+", cantiere["sessione_riferimento"], re.IGNORECASE)}
    passi_chiusi = {m.group(0).lower() for c in commit for m in re.finditer(r"passo \d+", c["oggetto"], re.IGNORECASE)} - nella_riga
    if GIA_CHIUSO.search(obiettivo):
        return []  # lo cita come fatto, non come da fare
    return [f"obiettivo ripropone {p!r}, già committato" for p in sorted(passi_chiusi)
            if re.search(rf"\b{p}\b", obiettivo, re.IGNORECASE)]


def controlla(testo, tipo):
    problemi = []
    if tipo == "brief":
        nome_utente, testo = testo
        return _controlla_brief(nome_utente, testo)
    if "`" in testo:
        problemi.append("backtick")
    if tipo in ("proposta", "conversazione"):
        problemi += _controlla_fatti(testo)
    if tipo == "conversazione":
        problemi += _controlla_conversazione(testo)
    if tipo == "proposta":
        m = AZIONI_GIA_IN_FUNZIONE.search(testo)
        if m:
            problemi.append(f"azione su cosa già in funzione: {m.group(0)!r}")
    if tipo == "impatto":
        corpo = RIGA_TOTALE.split(testo)[0]
        m = TOTALE_DEL_MODELLO.search(corpo)
        if m:
            problemi.append(f"totale scritto dal modello: {m.group(0)!r}")
    return problemi


def main():
    giri = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    falliti, totale = 0, 0
    for giro in range(1, giri + 1):
        for nome, genera, tipo in CASI:
            totale += 1
            testo = genera()
            problemi = controlla(testo, tipo)
            if problemi:
                falliti += 1
                print(f"FALLITO giro {giro}: {nome} — {'; '.join(problemi)}\n{testo}\n")
    print(f"{totale - falliti}/{totale} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
