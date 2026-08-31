import re
import unicodedata
from urllib.parse import parse_qs, urlsplit


AGGREGATORI = {
    "booking.com", "airbnb.com", "airbnb.it", "facebook.com", "instagram.com",
    "tripadvisor.com", "tripadvisor.it", "expedia.com", "expedia.it",
    "hotels.com", "agoda.com", "trivago.com", "trivago.it",
    "bedandbreakfast.it", "hostelworld.com", "vrbo.com", "wa.me", "t.me",
    "linktr.ee", "goo.gl", "business.site", "lastminute.com", "lastminute.it",
    "google.com",  # per i link maps (google.com/maps) — non è il sito proprio della struttura
    # Booking engine / OTA scoperti nel batch Roma del 30/08 (STATO.md):
    # condivisi da decine di gestori diversi, non sono il sito di nessuno.
    "krossbooking.com", "spacest.com", "vio.com", "freecancellations.com",
    "snaptrip.com", "bluepillow.com", "voyabay.com", "trip.com",
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


DOMINIO_MAX_STRUTTURE_CONDIVISE = 8


def candidato_dominio(url):
    """(chiave, sito_proprio) — la classificazione host/piattaforma/
    aggregatore di sempre, SENZA la soglia di condivisione (quella vive in
    dominio()). Esposta a parte perché risolvi.py la riusa identica nella
    prima passata di conteggio, prima ancora di sapere quante strutture
    condivideranno ogni chiave."""
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


def dominio(url, conteggio_domini=None):
    """(chiave, sito_proprio). chiave=None quando l'url non produce
    un'identità di dedup utilizzabile (input non-http, aggregatore noto,
    piattaforma di hosting senza alcun modo di identificare il sito, o un
    dominio condiviso da troppe strutture per essere il sito di una sola).

    conteggio_domini, se passato, è un dict chiave -> quanti place_id
    distinti nel batch condividono quella chiave (calcolato a parte, in una
    prima passata su tutte le schede — vedi risolvi.py). Un dominio non
    ancora in AGGREGATORI ma condiviso da più di
    DOMINIO_MAX_STRUTTURE_CONDIVISE strutture è quasi certamente un booking
    engine o un'OTA non ancora scoperta, non il sito di nessuno in
    particolare: (None, False), il link resta comunque nel payload grezzo,
    solo non genera identità di dedup. Senza conteggio_domini (default)
    dominio() si comporta come prima — nessuna soglia applicata."""
    chiave, proprio = candidato_dominio(url)
    if proprio and conteggio_domini is not None:
        if conteggio_domini.get(chiave, 0) > DOMINIO_MAX_STRUTTURE_CONDIVISE:
            return None, False
    return chiave, proprio


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


EMAIL_REGEX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")

# Local-part di caselle di servizio, mai un contatto utile.
PREFISSI_SERVIZIO = {"noreply", "no-reply", "postmaster", "webmaster", "privacy"}
# Domini di servizio: compaiono negli indirizzi solo perché la regex ha preso
# per email qualcos'altro — tipico un DSN Sentry incollato nel <script> della
# pagina ("chiave@o12345.ingest.sentry.io"), o un placeholder di WordPress.
# Controllo per sottostringa: questi non compaiono mai come dominio completo
# di un indirizzo vero.
DOMINI_SERVIZIO = {"wordpress", "sentry"}
# Domini placeholder da demo/template con nomi che non contengono nessuna
# delle PAROLE_SEGNAPOSTO sotto (altrimenti sarebbero già coperti da quella
# regola generale): controllo per uguaglianza esatta, MAI per sottostringa —
# "mail.com" per sottostringa scarterebbe anche gmail.com/hotmail.com, che
# sono domini reali.
DOMINI_PLACEHOLDER = {"mail.com", "company.co", "test.com", "domain.com"}
# Parole che, ovunque compaiano — nel local-part o nel dominio, anche come
# sottostringa di un nome più lungo — segnalano quasi certamente un
# indirizzo demo lasciato in un template mai sostituito, non un contatto
# vero. Scoperte a campione (31/08: company.co, mail.com, ...; poi
# example.com, dominio.com, email.com, esempio.it, mysite.com nel giro
# successivo) prima di passare a questa regola generale, per non dover
# inseguire ogni nuova variante una alla volta.
PAROLE_SEGNAPOSTO = {
    "example", "esempio", "mysite", "dominio", "tuodominio", "yourdomain",
    "tuosito", "email.com", "indirizzo", "utente", "nomeazienda",
}
# Estensioni di file: la regex a volte prende per email nomi tipo
# "logo@2x.png" nei retina asset dentro l'HTML.
ESTENSIONI_FILE = {"png", "jpg", "jpeg", "gif", "svg", "webp", "bmp", "ico"}


def _contiene_segnaposto(campo):
    """"dominio" è sottostringa di "condominio" — un amministratore di
    condominio vero (info@condominiorossi.it) non va scartato come
    placeholder. Unica eccezione nella lista: le altre parole non
    compaiono per caso dentro nomi italiani comuni."""
    for parola in PAROLE_SEGNAPOSTO:
        if parola not in campo:
            continue
        if parola == "dominio" and "condominio" in campo:
            continue
        return True
    return False


def estrai_email(testo):
    """Regex deterministica sul testo HTML grezzo. Ritorna gli indirizzi
    validi (minuscoli, deduplicati, ordine di prima comparsa), scartando le
    caselle di servizio, i placeholder da template e i falsi positivi che la
    regex prende per sbaglio."""
    if not testo:
        return []
    trovate = []
    visti = set()
    for m in EMAIL_REGEX.finditer(testo):
        indirizzo = m.group(0).lower()
        if indirizzo in visti:
            continue
        locale, _, dom = indirizzo.partition("@")
        if locale in PREFISSI_SERVIZIO:
            continue
        if dom in DOMINI_PLACEHOLDER:
            continue
        if any(servizio in dom for servizio in DOMINI_SERVIZIO):
            continue
        if _contiene_segnaposto(locale) or _contiene_segnaposto(dom):
            continue
        estensione = dom.rsplit(".", 1)[-1]
        if estensione in ESTENSIONI_FILE:
            continue
        visti.add(indirizzo)
        trovate.append(indirizzo)
    return trovate


PREFISSI_PREFERITI = {"info", "booking", "prenotazioni"}


def preferenza_email(indirizzo, dominio_sito):
    """Rango di preferenza per scegliere la migliore email tra più trovate
    sullo stesso sito (rango più basso = preferito). Il dominio del sito
    viene prima del local-part: un info@ su un dominio estraneo (spesso un
    placeholder da template, tipo info@company.co) non deve battere un
    indirizzo qualunque sul dominio giusto.
    0 = info@/booking@/prenotazioni@ sul dominio del sito
    1 = altro indirizzo sul dominio del sito
    2 = info@/booking@/prenotazioni@ su un dominio diverso
    3 = altro indirizzo su un dominio diverso (es. gmail)"""
    locale, _, dom = indirizzo.partition("@")
    if dom.startswith("www."):
        dom = dom[4:]
    preferito = locale in PREFISSI_PREFERITI
    stesso_dominio = bool(dominio_sito) and dom == dominio_sito
    if stesso_dominio:
        return 0 if preferito else 1
    return 2 if preferito else 3


IG_RISERVATI = {"p", "reel", "reels", "tv", "stories", "explore", "accounts", "direct"}
# Un handle Instagram vero è solo lettere/cifre/punto/underscore (regole
# reali di Instagram). Scarta gli artefatti di href rotti tipo
# "instagram.com/https://instagram.com/handle" (copia-incolla nel template
# del sito), dove il "primo segmento" diventerebbe "https:".
IG_HANDLE_VALIDO = re.compile(r"^[a-z0-9._]{1,30}$")

# Account social ufficiali di page builder/hosting: compaiono quando il
# sito li lascia come icona social di default, mai configurata dal
# gestore — non sono la struttura. Scoperti a campione (1/09: wix,
# wixstudio, shopify) e ampliati coi builder più comuni tra i siti low-cost
# usati da B&B/hotel italiani.
BUILDER_SOCIAL_DA_SCARTARE = {
    "wix", "wixstudio", "shopify", "squarespace", "webador", "weebly",
    "wordpress", "godaddy", "jimdo", "altervista", "aruba", "ionos",
}


def normalizza_instagram(url):
    """Handle nudo (minuscolo, senza @) da un URL instagram.com, o None se
    non è un profilo — post/reel/storie/pagine di sistema, un href rotto, o
    la home senza handle."""
    segmenti = [s for s in urlsplit(url).path.split("/") if s]
    if not segmenti:
        return None
    handle = segmenti[0].lower()
    if handle in IG_RISERVATI:
        return None
    if not IG_HANDLE_VALIDO.match(handle):
        return None
    if handle in BUILDER_SOCIAL_DA_SCARTARE:
        return None
    return handle


FB_RISERVATI = {
    "sharer", "sharer.php", "share", "share.php", "dialog", "plugins",
    "photo.php", "photos", "permalink.php", "story.php", "video.php",
    "watch", "l.php", "posts", "reel", "reels", "groups", "events",
}
# "pages"/"people" sono schemi URL Facebook veri (facebook.com/pages/Nome/id,
# facebook.com/people/Nome/id), non il nome della pagina — il primo
# segmento da solo perderebbe l'identificativo. Servono i segmenti dopo.
FB_SCHEMI_MULTI_SEGMENTO = {"pages", "people"}


def normalizza_facebook(url):
    """URL profilo normalizzato (https://facebook.com/<pagina>), o None se
    non è un profilo — condivisioni/post/reel/plugin. "profile.php?id=..."
    è l'unica eccezione alla regola "niente query": è l'unico identificatore
    per le pagine senza nome vanity, senza id non ha senso tenerlo."""
    parti = urlsplit(url)
    segmenti = [s for s in parti.path.split("/") if s]
    if not segmenti:
        return None
    primo = segmenti[0].lower()
    if primo in FB_RISERVATI:
        return None
    if primo in BUILDER_SOCIAL_DA_SCARTARE:
        return None
    if primo == "profile.php":
        id_valori = parse_qs(parti.query).get("id")
        if not id_valori:
            return None
        return f"https://facebook.com/profile.php?id={id_valori[0]}"
    if primo in FB_SCHEMI_MULTI_SEGMENTO:
        # Serve anche l'id (terzo segmento): è quello che giustifica di
        # preservare lo schema invece di scartarlo come gli altri — un
        # "pages/nome" senza id non è un link garantito funzionante.
        if len(segmenti) < 3:
            return None
        # "pages/category/..." è la directory categorie di Facebook, non
        # una pagina — trovato reale in un batch (facebook.com/pages/
        # category/hotel). "category" non è mai un nome di pagina vero.
        if segmenti[1].lower() == "category":
            return None
        resto = "/".join(s.lower() for s in segmenti[1:3])
        return f"https://facebook.com/{primo}/{resto}"
    # Un id numerico vero (facebook.com/profile.php?id=... o le prime cifre
    # di pages/people) è sempre lungo (15-17 cifre) — Facebook non assegna
    # username di pagina puramente numerici brevi. Un "facebook.com/<cifre
    # corte>" come slug diretto è quasi certo un placeholder di widget mai
    # configurato (bug reale, 1/09: "facebook.com/1278" identico su 9 siti
    # scollegati, stesso widget "socialHubWrapper" di un booking engine
    # condiviso — non una pagina).
    if primo.isdigit():
        return None
    return f"https://facebook.com/{primo}"


TYPES_AMMESSI = {
    "bed_and_breakfast", "guest_house", "private_guest_room", "hostel",
    "inn", "lodging", "hotel", "extended_stay_hotel", "cottage",
    "farmstay", "resort_hotel", "motel",
}
TYPES_ESCLUSI = {"real_estate_agency", "travel_agency", "tour_agency"}


def ammesso(posto):
    """OPERATIONAL e almeno un type ammesso, nessuno escluso. Stessa regola
    usata sia da cerca_places.py (raccolta) sia da risolvi.py (resolver)."""
    if posto.get("businessStatus") != "OPERATIONAL":
        return False
    types = set(posto.get("types", []))
    if types & TYPES_ESCLUSI:
        return False
    return bool(types & TYPES_AMMESSI)
