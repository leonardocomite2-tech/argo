"""Argo — la voce, passo 14: USER.md che si popola.

Argo impara come lavora Leonardo e lo propone per USER.md; la riga entra
nel file solo dopo un sì esplicito (regola 1 di USER.md). Qui vive la parte
deterministica: i fatti si calcolano in Python dai dati (mai chiesti a un
modello), la riga proposta è composta da un template fatto di numeri e
parole fisse — un nome di host o di prospect non ci può entrare per
costruzione —, e la modifica al testo di USER.md è una funzione pura.

Sola lettura: questo modulo non scrive mai né sul DB né sul file. Chi
scrive è scripts/argo/orienta_webhook.py (la riga `argo_proposta` in
conversazione_argo prima dell'invio, USER.md solo nel ramo del sì).

Tre tipi di fatto, insieme chiuso (TIPI_FATTO):
- fascia_oraria: in che fascia di Roma arrivano le richieste di Leonardo
  (messaggi liberi e comandi, mai l'avviso che parte dal sistema);
- finestra_telefono / finestra_computer: i minuti dichiarati per contesto
  (/instrada e, dal passo 14, i messaggi liberi classificati come instrada,
  salvati in jobs.payload dal consumer).

Limite di lunghezza strutturale: le righe di Argo stanno sotto
INTESTAZIONE_BLOCCO, al massimo una per tipo (un valore nuovo sostituisce
il vecchio), e il file non supera LIMITE_USER_MD_CARATTERI.
"""

import re
import statistics
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import argo.stato as stato

REPO_ROOT = Path(__file__).resolve().parent.parent
USER_MD_PATH = REPO_ROOT / "knowledge" / "argo" / "USER.md"
FUSO_ROMA = ZoneInfo("Europe/Rome")

RUOLO_PROPOSTA = "argo_proposta"
TIPI_FATTO = ("fascia_oraria", "finestra_telefono", "finestra_computer")
INTESTAZIONE_BLOCCO = "### Dai dati (ogni riga confermata da Leonardo)"
# Circa due pagine (regola 3 di USER.md). Oltre, Argo non propone più: una
# riga va tolta a mano.
LIMITE_USER_MD_CARATTERI = 6000
LIMITE_RIGA_CARATTERI = 200

FASCE = (("notte", 0, 6), ("mattina", 6, 12), ("pomeriggio", 12, 18), ("sera", 18, 24))
# Soglie di produzione: sotto, Argo tace. Il collaudo (forza=True) le salta,
# ma la riga dichiara sempre il campione.
SOGLIA_FASCIA_RICHIESTE = 20
SOGLIA_FASCIA_GIORNI = 7
SOGLIA_FASCIA_QUOTA = 0.5
SOGLIA_FINESTRA_RICHIESTE = 5
SOGLIA_FINESTRA_GIORNI = 3
NESSUNA_PREVALENTE = "nessuna_prevalente"

# Comandi di Leonardo che nascono come job (backend/main.py). I messaggi
# liberi si contano da conversazione_argo, non dai loro job
# genera_conversazione: sarebbe lo stesso messaggio due volte.
TIPI_JOB_COMANDO = ("genera_orienta", "genera_instrada", "genera_brief", "genera_impatto")

_RIGA_RE = re.compile(
    r"^- (\d{2}/\d{2}) — (.+) \[(" + "|".join(TIPI_FATTO) + r"):([a-z0-9_]+)\]$",
    re.MULTILINE,
)
_VIETATO_IN_RIGA_RE = re.compile(r"@|https?:|www\.|://")

_SI = {"sì", "si", "sí"}
_NO = {"no"}

TESTO_SCRITTA = "Scritta in USER.md. Non è committata: resta nel working tree."
TESTO_GIA_PRESENTE = "La riga era già in USER.md: niente da cambiare."
TESTO_LASCIATA = "Lasciata fuori. Non te la ripropongo."
TESTO_NON_SCRITTA = "Non l'ho scritta: {motivo}."


class UserMdErrore(Exception):
    """Modifica a USER.md non applicabile. Motivo categorico, mai il testo."""


# --- lettori (sola lettura, via argo/stato.py) ---

def richieste_leonardo():
    """Istanti delle richieste di Leonardo: messaggi liberi (anche quelli
    arrivati mentre Argo rispondeva) più i comandi. ErroreQueryDB passa."""
    tipi_sql = ",".join(f"'{t}'" for t in TIPI_JOB_COMANDO)
    righe = stato._query_db(
        "SELECT created_at FROM conversazione_argo WHERE ruolo LIKE 'leonardo%' "
        f"UNION ALL SELECT created_at FROM jobs WHERE tipo IN ({tipi_sql})"
    )
    return [_istante(r["created_at"]) for r in righe]


def finestre_dichiarate():
    """(istante, minuti, contesto) da /instrada e dai messaggi liberi
    classificati come instrada (chiavi aggiunte al payload dal consumer)."""
    righe = stato._query_db(
        "SELECT created_at, payload->>'minuti' AS minuti, payload->>'contesto' AS contesto "
        "FROM jobs WHERE tipo = 'genera_instrada' "
        "OR (tipo = 'genera_conversazione' AND payload->>'modo' = 'instrada')"
    )
    finestre = []
    for r in righe:
        minuti = r.get("minuti")
        if not (isinstance(minuti, str) and minuti.isdigit()) or r.get("contesto") not in ("telefono", "computer"):
            continue
        finestre.append((_istante(r["created_at"]), int(minuti), r["contesto"]))
    return finestre


def proposte_passate():
    """Le righe argo_proposta, dalla più vecchia: servono per la chiave già
    proposta (non torna mai) e per il tetto di una al giorno."""
    return stato._query_db(
        f"SELECT id, created_at, testo FROM conversazione_argo WHERE ruolo = '{RUOLO_PROPOSTA}' ORDER BY id"
    )


def _istante(valore):
    return datetime.fromisoformat(valore) if isinstance(valore, str) else valore


# --- calcolo dei fatti (puro) ---

def fascia_di(istante):
    ora = istante.astimezone(FUSO_ROMA).hour
    for nome, da, a in FASCE:
        if da <= ora < a:
            return nome
    raise ValueError("ora fuori dalle fasce")


def _periodo(istanti):
    giorni = sorted({i.astimezone(FUSO_ROMA).date() for i in istanti})
    return giorni[0].strftime("%d/%m"), giorni[-1].strftime("%d/%m"), len(giorni)


def _fatto_fascia(richieste, forza):
    if not richieste:
        return None
    conteggi = {nome: 0 for nome, _, _ in FASCE}
    for istante in richieste:
        conteggi[fascia_di(istante)] += 1
    ordine = [nome for nome, _, _ in FASCE]
    presenti = sorted((n for n in ordine if conteggi[n]), key=lambda n: (-conteggi[n], ordine.index(n)))
    totale = len(richieste)
    dal, al, giorni = _periodo(richieste)
    prima = presenti[0]
    quota_ok = conteggi[prima] / totale >= SOGLIA_FASCIA_QUOTA
    if not forza and not (totale >= SOGLIA_FASCIA_RICHIESTE and giorni >= SOGLIA_FASCIA_GIORNI and quota_ok):
        return None
    elenco = ", ".join(f"{n} {conteggi[n]}" for n in presenti)
    return {
        "tipo": "fascia_oraria",
        "valore": prima if quota_ok else NESSUNA_PREVALENTE,
        "campione": totale,
        "testo": f"Richieste ad Argo per fascia oraria: {elenco} su {totale} ({dal}–{al}, {giorni} giorni)",
    }


def _fatto_finestra(finestre, contesto, forza):
    scelte = [(i, m) for i, m, c in finestre if c == contesto]
    if not scelte:
        return None
    istanti = [i for i, _ in scelte]
    minuti = [m for _, m in scelte]
    dal, al, giorni = _periodo(istanti)
    if not forza and not (len(scelte) >= SOGLIA_FINESTRA_RICHIESTE and giorni >= SOGLIA_FINESTRA_GIORNI):
        return None
    mediana = statistics.median_low(minuti)
    richieste = "richiesta" if len(scelte) == 1 else "richieste"
    return {
        "tipo": f"finestra_{contesto}",
        "valore": str(mediana),
        "campione": len(scelte),
        "testo": (
            f"Finestre dichiarate al {contesto}: mediana {mediana} minuti su {len(scelte)} {richieste} "
            f"(da {min(minuti)} a {max(minuti)}, {dal}–{al})"
        ),
    }


def calcola_fatti(richieste, finestre, forza=False):
    """I fatti sopra soglia (tutti, con forza=True), dal campione più grande."""
    fatti = [
        _fatto_fascia(richieste, forza),
        _fatto_finestra(finestre, "telefono", forza),
        _fatto_finestra(finestre, "computer", forza),
    ]
    return sorted((f for f in fatti if f), key=lambda f: -f["campione"])


def riga_per(fatto, oggi):
    return f"- {oggi.strftime('%d/%m')} — {fatto['testo']} [{fatto['tipo']}:{fatto['valore']}]"


# --- proposta e conferma (puro) ---

def testo_proposta(riga, sostituisce=None):
    parti = ["Per USER.md, sotto «Le finestre tipiche», scriverei questa riga:", riga]
    if sostituisce:
        parti += ["Al posto di:", sostituisce]
    parti.append("Rispondi sì per scriverla, no per lasciarla fuori. Qualunque altra risposta la lascia fuori, e non torna.")
    return "\n\n".join(parti)


def analizza_riga(riga):
    """(tipo, valore) se `riga` ha il formato di una riga di Argo ed è
    ammessa, altrimenti None. Rivalidazione prima di ogni scrittura."""
    m = _RIGA_RE.fullmatch(riga.strip())
    if not m or len(riga) > LIMITE_RIGA_CARATTERI or _VIETATO_IN_RIGA_RE.search(riga):
        return None
    return m.group(3), m.group(4)


def estrai_riga_proposta(testo):
    """La riga da scrivere è la prima riga di formato valido nel testo della
    proposta (l'eventuale "Al posto di" viene dopo). None se non c'è."""
    m = _RIGA_RE.search(testo or "")
    if not m or analizza_riga(m.group(0)) is None:
        return None
    return m.group(0)


def chiave(riga):
    analizzata = analizza_riga(riga)
    return f"{analizzata[0]}:{analizzata[1]}" if analizzata else None


def chiavi_proposte(proposte):
    chiavi = set()
    for p in proposte:
        riga = estrai_riga_proposta(p.get("testo"))
        if riga:
            chiavi.add(chiave(riga))
    return chiavi


def proposta_oggi(proposte, oggi):
    return any(_istante(p["created_at"]).astimezone(FUSO_ROMA).date() == oggi for p in proposte)


def _normalizza_risposta(testo):
    return (testo or "").strip().lower().rstrip(".! ").strip()


def e_si(testo):
    return _normalizza_risposta(testo) in _SI


def e_no(testo):
    return _normalizza_risposta(testo) in _NO


# --- USER.md (puro) ---

def _limiti_blocco(righe):
    try:
        inizio = righe.index(INTESTAZIONE_BLOCCO)
    except ValueError:
        raise UserMdErrore("blocco delle righe di Argo mancante in USER.md") from None
    fine = inizio + 1
    while fine < len(righe) and not righe[fine].startswith("#"):
        fine += 1
    return inizio, fine


def riga_esistente(user_md, tipo):
    """La riga di Argo dello stesso tipo già nel blocco, o None."""
    righe = user_md.split("\n")
    inizio, fine = _limiti_blocco(righe)
    for r in righe[inizio + 1:fine]:
        analizzata = analizza_riga(r)
        if analizzata and analizzata[0] == tipo:
            return r
    return None


def applica_riga(user_md, riga):
    """Nuovo testo di USER.md con `riga` nel blocco di Argo: sostituisce la
    riga dello stesso tipo, altrimenti si aggiunge dopo l'ultima. Stessa
    riga già presente -> testo invariato (idempotente). UserMdErrore se la
    riga non è valida, se manca il blocco o se si supera il tetto."""
    analizzata = analizza_riga(riga)
    if analizzata is None:
        raise UserMdErrore("riga non valida")
    righe = user_md.split("\n")
    inizio, fine = _limiti_blocco(righe)
    if riga in righe[inizio + 1:fine]:
        return user_md
    posizione = None
    for i in range(inizio + 1, fine):
        esistente = analizza_riga(righe[i])
        if esistente and esistente[0] == analizzata[0]:
            righe[i] = riga
            posizione = i
            break
    if posizione is None:
        ultima = inizio
        for i in range(inizio + 1, fine):
            if righe[i].strip():
                ultima = i
        righe.insert(ultima + 1, riga)
    nuovo = "\n".join(righe)
    if len(nuovo) > LIMITE_USER_MD_CARATTERI:
        raise UserMdErrore(f"USER.md supererebbe {LIMITE_USER_MD_CARATTERI} caratteri")
    return nuovo


def scegli_proposta(fatti, chiavi_gia_proposte, user_md, oggi):
    """La prima riga proponibile: chiave mai proposta, non già nel file, e
    che sta nel tetto. Ritorna (riga, riga_sostituita) o None."""
    for fatto in fatti:
        riga = riga_per(fatto, oggi)
        if chiave(riga) is None or chiave(riga) in chiavi_gia_proposte:
            continue
        vecchia = riga_esistente(user_md, fatto["tipo"])
        if vecchia and chiave(vecchia) == chiave(riga):
            continue
        try:
            applica_riga(user_md, riga)
        except UserMdErrore:
            continue
        return riga, vecchia
    return None


def prepara_proposta(forza=False, ora=None):
    """Legge i dati e decide. Ritorna (testo_proposta, None) oppure
    (None, motivo). forza=True (solo il collaudo a mano) salta le soglie di
    campione e il tetto di una al giorno, mai la chiave già proposta né il
    tetto di lunghezza. ErroreQueryDB passa a chi chiama."""
    ora = ora or datetime.now(FUSO_ROMA)
    oggi = ora.astimezone(FUSO_ROMA).date()
    proposte = proposte_passate()
    if not forza and proposta_oggi(proposte, oggi):
        return None, "già una proposta oggi"
    fatti = calcola_fatti(richieste_leonardo(), finestre_dichiarate(), forza=forza)
    if not fatti:
        return None, "nessun fatto sopra soglia"
    user_md = USER_MD_PATH.read_text(encoding="utf-8")
    scelta = scegli_proposta(fatti, chiavi_proposte(proposte), user_md, oggi)
    if scelta is None:
        return None, "nessun fatto nuovo da proporre"
    riga, vecchia = scelta
    return testo_proposta(riga, vecchia), None
