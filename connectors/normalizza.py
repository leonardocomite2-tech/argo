import re
import unicodedata
from urllib.parse import urlsplit


AGGREGATORI = {
    "booking.com", "airbnb.com", "airbnb.it", "facebook.com", "instagram.com",
    "tripadvisor.com", "tripadvisor.it", "expedia.com", "expedia.it",
    "hotels.com", "agoda.com", "trivago.com", "trivago.it",
    "bedandbreakfast.it", "hostelworld.com", "vrbo.com", "wa.me", "t.me",
    "linktr.ee", "goo.gl", "business.site", "lastminute.com", "lastminute.it",
    "google.com",  # per i link maps (google.com/maps) — non è il sito proprio della struttura
}

# Controllate PRIMA degli aggregatori: "google.com" è un aggregatore (per i
# link maps), ma "sites.google.com" è hosting — invertendo l'ordine
# verrebbe scartato come aggregatore prima di arrivare al controllo hosting.
PIATTAFORME_HOSTING = {
    "wixsite.com", "sites.google.com", "altervista.org", "wordpress.com",
    "blogspot.com", "weebly.com", "github.io",
}


def _host_e_path(url):
    """(host_senza_www, path) da un url anche senza schema.
    (None, None) se non è un url http(s) utilizzabile."""
    if not url or not isinstance(url, str):
        return None, None
    testo = url.strip().lower()
    if not testo or testo.startswith("mailto:") or testo.startswith("tel:"):
        return None, None
    lavoro = testo if "://" in testo else "//" + testo.lstrip("/")
    parti = urlsplit(lavoro)
    host = parti.netloc.split("@")[-1].split(":")[0]  # via userinfo/porta
    if host.startswith("www."):
        host = host[4:]
    if not host or "." not in host:
        return None, None
    return host, parti.path


def dominio(url):
    """(chiave, sito_proprio). chiave=None quando l'url non produce
    un'identità di dedup utilizzabile (input non-http, aggregatore noto,
    o piattaforma di hosting senza alcun modo di identificare il sito)."""
    host, path = _host_e_path(url)
    if host is None:
        return None, False

    primo_segmento = path.lstrip("/").split("/")[0] if path else ""

    for piattaforma in PIATTAFORME_HOSTING:
        if host == piattaforma:
            # Host condiviso da tutti (es. sites.google.com): senza un
            # segmento di path non c'è modo di sapere quale sito sia.
            if not primo_segmento:
                return None, False
            return f"{host}/{primo_segmento}", True
        if host.endswith("." + piattaforma):
            # Sottodominio già univoco (es. miostruttura.wixsite.com):
            # basta da solo, il path è un bonus non necessario.
            chiave = host + (f"/{primo_segmento}" if primo_segmento else "")
            return chiave, True

    for aggregatore in AGGREGATORI:
        if host == aggregatore or host.endswith("." + aggregatore):
            return None, False

    return host, True


def telefono_e164(*valori):
    """Primo valore utile tra gli argomenti (skip None/vuoto/non parsabile)."""
    for valore in valori:
        risultato = _prova_numero(valore)
        if risultato is not None:
            return risultato
    return None


def _prova_numero(valore):
    if not valore:
        return None
    testo = str(valore).strip()
    if not testo:
        return None

    for separatore in (",", "/"):
        if separatore in testo:
            testo = testo.split(separatore, 1)[0].strip()
            break

    if testo.startswith("00"):
        testo = "+" + testo[2:]

    ha_piu = testo.startswith("+")
    cifre = re.sub(r"\D", "", testo)
    if not cifre:
        return None

    if ha_piu:
        if cifre.startswith("39"):
            # Trappola italiana: lo 0 iniziale dei fissi fa parte del numero,
            # non va tolto come farebbe una normalizzazione E.164 generica.
            resto = cifre[2:]
            if not (8 <= len(resto) <= 11):
                return None
        elif not (8 <= len(cifre) <= 15):
            return None
        return "+" + cifre

    # Nessun + né 00: assunto italiano (contesto: lead-gen Roma). Mai
    # stripping dello 0 iniziale in nessun ramo di questa funzione.
    if not (6 <= len(cifre) <= 11):
        return None
    return "+39" + cifre


ARTICOLI = {"il", "lo", "la", "i", "gli", "le", "l"}
FORME_SOCIETARIE = {"srl", "snc", "sas"}


def nome_chiave(nome):
    """Chiave debole per segnalare possibili doppioni a un umano — MAI per
    fondere record automaticamente."""
    if not nome:
        return ""
    testo = unicodedata.normalize("NFKD", nome)
    testo = "".join(c for c in testo if not unicodedata.combining(c))
    testo = testo.lower()
    testo = re.sub(r"\bl['’]", "", testo)
    testo = re.sub(r"[^a-z0-9\s]", "", testo)
    token = [t for t in testo.split() if t not in ARTICOLI and t not in FORME_SOCIETARIE]
    return " ".join(token)


ABBREVIAZIONI_VIA = {
    "p.zza": "Piazza",
    "v.le": "Viale",
    "lgt.": "Lungotevere",
    "c.so": "Corso",
    "v.": "Via",
}


def indirizzo_chiave(indirizzo):
    """(via_normalizzata, civico) dal formattedAddress italiano.
    (None, None) se indirizzo è vuoto/None."""
    if not indirizzo or not indirizzo.strip():
        return None, None

    parti = [p.strip() for p in indirizzo.split(",") if p.strip()]
    if not parti:
        return None, None

    via_grezza = parti[0]
    civico = None

    if len(parti) >= 2:
        m = re.match(r"^(\d+)\s*/?\s*([a-zA-Z]{0,3})$", parti[1])
        if m:
            civico = m.group(1) + m.group(2).upper()

    if civico is None:
        m = re.search(r"(\d+)\s*/?\s*([a-zA-Z]{0,3})$", via_grezza)
        if m:
            civico = m.group(1) + m.group(2).upper()
            via_grezza = via_grezza[:m.start()].strip()

    return _espandi_abbreviazione(via_grezza), civico


def _espandi_abbreviazione(via):
    if not via:
        return via
    parti = via.split(" ", 1)
    primo = parti[0].lower()
    resto = parti[1] if len(parti) > 1 else ""
    primo_espanso = ABBREVIAZIONI_VIA.get(primo, parti[0])
    return (primo_espanso + (" " + resto if resto else "")).strip()
