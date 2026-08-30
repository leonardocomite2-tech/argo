"""Matrice di ricerche Places (New) su celle geografiche di Roma. Sola
lettura: nessuna scrittura sul DB. Gira a mano fuori Docker."""
import argparse
import json
import logging
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.places import cerca_testo, carica_env, PlacesErrore  # noqa: E402
from connectors.normalizza import (  # noqa: E402
    dominio, telefono_e164, TYPES_AMMESSI, TYPES_ESCLUSI,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("argo.cerca_places")

MAX_CHIAMATE_RUN = 120
MAX_LIVELLO_BISEZIONE = 2
DIMENSIONE_PAGINA = 20
PAGINE_PER_CELLA = 3

RICERCHE = [
    {"query": "bed and breakfast", "tipo": "bed_and_breakfast"},
    {"query": "affittacamere e guest house", "tipo": "guest_house"},
    {"query": "ostello", "tipo": "hostel"},
    {"query": "casa vacanze", "tipo": None},
]

# Prima passata su base OpenStreetMap/confini di quartiere noti, NON confini
# amministrativi ufficiali. Una cella troppo grande satura e si autodivide in
# quadranti; una troppo piccola/mal piazzata si vede da un conteggio basso nel
# --dry-run e si aggiusta — non serve precisione al primo colpo.
CELLE = {
    "centro_storico":     {"low": {"lat": 41.893, "lng": 12.464}, "high": {"lat": 41.903, "lng": 12.482}},
    "trevi_spagna":       {"low": {"lat": 41.900, "lng": 12.478}, "high": {"lat": 41.910, "lng": 12.492}},
    "monti_colosseo":     {"low": {"lat": 41.885, "lng": 12.484}, "high": {"lat": 41.897, "lng": 12.500}},
    "esquilino_termini":  {"low": {"lat": 41.892, "lng": 12.495}, "high": {"lat": 41.906, "lng": 12.515}},
    "trastevere":         {"low": {"lat": 41.878, "lng": 12.462}, "high": {"lat": 41.895, "lng": 12.480}},
    "testaccio_aventino": {"low": {"lat": 41.868, "lng": 12.466}, "high": {"lat": 41.884, "lng": 12.486}},
    "prati_borgo":        {"low": {"lat": 41.900, "lng": 12.452}, "high": {"lat": 41.915, "lng": 12.475}},
    "san_giovanni":       {"low": {"lat": 41.878, "lng": 12.500}, "high": {"lat": 41.892, "lng": 12.520}},
    "salario_nomentano":  {"low": {"lat": 41.906, "lng": 12.492}, "high": {"lat": 41.925, "lng": 12.515}},
    "flaminio_parioli":   {"low": {"lat": 41.910, "lng": 12.462}, "high": {"lat": 41.930, "lng": 12.492}},
    "san_lorenzo_pigneto": {"low": {"lat": 41.885, "lng": 12.515}, "high": {"lat": 41.900, "lng": 12.545}},
}

CELLE_DRY_RUN = ["trastevere", "centro_storico", "monti_colosseo"]


class ContatoreChiamate:
    """Passato per riferimento attraverso tutta la ricorsione di bisezione:
    un solo tetto per l'intero run."""
    def __init__(self, tetto):
        self.usate = 0
        self.tetto = tetto

    def puo_chiamare(self):
        return self.usate < self.tetto

    def incrementa(self):
        self.usate += 1


def _quadranti(rettangolo):
    lat_lo, lat_hi = rettangolo["low"]["lat"], rettangolo["high"]["lat"]
    lng_lo, lng_hi = rettangolo["low"]["lng"], rettangolo["high"]["lng"]
    lat_mid, lng_mid = (lat_lo + lat_hi) / 2, (lng_lo + lng_hi) / 2
    return [
        {"low": {"lat": lat_lo, "lng": lng_lo}, "high": {"lat": lat_mid, "lng": lng_mid}},
        {"low": {"lat": lat_lo, "lng": lng_mid}, "high": {"lat": lat_mid, "lng": lng_hi}},
        {"low": {"lat": lat_mid, "lng": lng_lo}, "high": {"lat": lat_hi, "lng": lng_mid}},
        {"low": {"lat": lat_mid, "lng": lng_mid}, "high": {"lat": lat_hi, "lng": lng_hi}},
    ]


def cerca_cella(nome_cella, rettangolo, ricerca, contatore, risultati_grezzi,
                 celle_sature, celle_processate, livello=0, cella_radice=None):
    """Fino a PAGINE_PER_CELLA pagine per (cella, ricerca). Se satura (60
    risultati) e livello < MAX_LIVELLO_BISEZIONE, si divide in 4 quadranti e
    ricorre. Ritorna False se il tetto di chiamate viene raggiunto (fermata
    immediata, ciò che è già scaricato resta valido), True altrimenti.
    cella_radice resta il nome pulito della cella originale (senza #qN) per
    tutta la ricorsione — è quello che finisce in _cella su ogni scheda."""
    cella_radice = cella_radice or nome_cella
    celle_processate.append((nome_cella, livello))
    pagina_token = None
    risultati_cella = []

    for _ in range(PAGINE_PER_CELLA):
        if not contatore.puo_chiamare():
            risultati_grezzi.extend(risultati_cella)
            return False
        try:
            risposta = cerca_testo(
                query=ricerca["query"], rettangolo=rettangolo, tipo=ricerca["tipo"],
                page_token=pagina_token, page_size=DIMENSIONE_PAGINA,
            )
        except PlacesErrore as e:
            logger.error("cerca_cella: %s/%s fallita (%s), tengo quanto già raccolto",
                          nome_cella, ricerca["query"], e)
            break
        finally:
            contatore.incrementa()

        nuovi = risposta.get("places", [])
        for posto in nuovi:
            posto["_cella"] = cella_radice
        risultati_cella.extend(nuovi)
        pagina_token = risposta.get("nextPageToken")
        if not pagina_token:
            break

    risultati_grezzi.extend(risultati_cella)
    satura = len(risultati_cella) >= PAGINE_PER_CELLA * DIMENSIONE_PAGINA

    if not satura:
        return True

    if livello >= MAX_LIVELLO_BISEZIONE:
        celle_sature.append((nome_cella, livello))
        logger.warning("cerca_cella: %s ancora satura al livello massimo di bisezione (%d)",
                        nome_cella, livello)
        return True

    for i, quadrante in enumerate(_quadranti(rettangolo)):
        ok = cerca_cella(f"{nome_cella}#q{i}", quadrante, ricerca, contatore,
                          risultati_grezzi, celle_sature, celle_processate,
                          livello + 1, cella_radice=cella_radice)
        if not ok:
            return False
    return True


def esegui_matrice(celle, contatore, risultati_grezzi, celle_sature, celle_processate):
    """Ritorna False se fermato dal tetto di chiamate (risultati parziali ma
    validi, non un'eccezione), True se completato interamente."""
    for nome_cella, rettangolo in celle.items():
        for ricerca in RICERCHE:
            ok = cerca_cella(nome_cella, rettangolo, ricerca, contatore,
                              risultati_grezzi, celle_sature, celle_processate)
            if not ok:
                return False
    return True


def filtra_e_dedup(risultati_grezzi):
    per_id = {}
    for posto in risultati_grezzi:
        pid = posto.get("id")
        if pid and pid not in per_id:
            per_id[pid] = posto

    ammessi = []
    scarti_per_tipo = Counter()
    scarti_non_operativi = 0

    for posto in per_id.values():
        if posto.get("businessStatus") != "OPERATIONAL":
            scarti_non_operativi += 1
            continue
        types = set(posto.get("types", []))
        chiave_scarto = posto.get("primaryType") or (posto.get("types") or ["sconosciuto"])[0]
        if types & TYPES_ESCLUSI or not (types & TYPES_AMMESSI):
            scarti_per_tipo[chiave_scarto] += 1
            continue
        ammessi.append(posto)

    stats = {
        "grezze_totali": len(risultati_grezzi), "uniche": len(per_id),
        "ammesse": len(ammessi), "scarti_non_operativi": scarti_non_operativi,
        "scarti_per_tipo": scarti_per_tipo,
    }
    return ammessi, stats


def arricchisci_stats_contatti(ammessi, stats):
    con_telefono = con_sito_proprio = con_solo_aggregatore = senza_sito = 0
    for posto in ammessi:
        if telefono_e164(posto.get("nationalPhoneNumber"), posto.get("internationalPhoneNumber")):
            con_telefono += 1
        sito = posto.get("websiteUri")
        if not sito:
            senza_sito += 1
        else:
            _, proprio = dominio(sito)
            con_sito_proprio += proprio
            con_solo_aggregatore += not proprio
    stats.update({"con_telefono": con_telefono, "con_sito_proprio": con_sito_proprio,
                   "con_solo_aggregatore": con_solo_aggregatore, "senza_sito": senza_sito})


def stampa_report(contatore, celle_processate, celle_sature, stats):
    print(f"Chiamate API usate: {contatore.usate}/{contatore.tetto}")
    print(f"Celle processate (comprese esplose in quadranti): {len(celle_processate)}")
    print(f"Schede grezze totali: {stats['grezze_totali']}")
    print(f"Uniche dopo dedup per place_id: {stats['uniche']}")
    print(f"Ammesse dopo filtri tipo/stato: {stats['ammesse']}")
    print(f"  con telefono: {stats['con_telefono']}")
    print(f"  con sito proprio: {stats['con_sito_proprio']}")
    print(f"  con solo aggregatore: {stats['con_solo_aggregatore']}")
    print(f"  senza alcun sito: {stats['senza_sito']}")
    print(f"Scartate per stato non operativo: {stats['scarti_non_operativi']}")
    print("Scartate per tipo:")
    for tipo, n in stats["scarti_per_tipo"].most_common():
        print(f"  {tipo}: {n}")
    if celle_sature:
        print("Celle ancora sature dopo bisezione massima (da rivedere a mano):")
        for nome, livello in celle_sature:
            print(f"  {nome} (livello {livello})")


def stampa_top20(ammessi):
    ordinati = sorted(ammessi, key=lambda p: p.get("userRatingCount") or 0, reverse=True)[:20]
    print("\nTop 20 per numero recensioni:")
    for posto in ordinati:
        nome = (posto.get("displayName") or {}).get("text", "(senza nome)")
        telefono = telefono_e164(posto.get("nationalPhoneNumber"), posto.get("internationalPhoneNumber")) or "-"
        print(f"  {nome} | {posto.get('primaryType', '-')} | {telefono} | {posto.get('websiteUri') or '-'}")


def salva_jsonl(risultati_grezzi, cartella_out):
    """cartella_out è una directory (default out/places), MAI un path di
    file: ogni esecuzione scrive un file nuovo places_<timestamp UTC>.jsonl,
    non sovrascrive mai quello di una run precedente."""
    out_dir = Path(cartella_out) if cartella_out else (REPO_ROOT / "out" / "places")
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    percorso = out_dir / f"places_{ts}.jsonl"
    with percorso.open("w") as f:
        for posto in risultati_grezzi:
            f.write(json.dumps(posto) + "\n")
    print(f"\nSalvate {len(risultati_grezzi)} schede grezze in {percorso}")


def main():
    parser = argparse.ArgumentParser(description="Matrice di ricerche Places per lead-gen host")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--celle", default="tutte")
    parser.add_argument("--out", help="cartella di destinazione del JSONL (default out/places); ignorato con --dry-run")
    parser.add_argument("--max-chiamate", type=int, default=MAX_CHIAMATE_RUN)
    args = parser.parse_args()

    carica_env()

    if args.dry_run:
        celle_scelte = {k: CELLE[k] for k in CELLE_DRY_RUN}
    elif args.celle == "tutte":
        celle_scelte = CELLE
    else:
        nomi = [c.strip() for c in args.celle.split(",")]
        non_valide = [c for c in nomi if c not in CELLE]
        if non_valide:
            print(f"Celle non riconosciute: {non_valide}", file=sys.stderr)
            print(f"Celle valide: {sorted(CELLE)}", file=sys.stderr)
            return 2
        celle_scelte = {c: CELLE[c] for c in nomi}

    contatore = ContatoreChiamate(args.max_chiamate)
    risultati_grezzi, celle_sature, celle_processate = [], [], []

    completato = esegui_matrice(celle_scelte, contatore, risultati_grezzi, celle_sature, celle_processate)
    if not completato:
        print(f"\nATTENZIONE: fermato per tetto di chiamate raggiunto ({contatore.tetto}) — risultati parziali ma validi.")

    ammessi, stats = filtra_e_dedup(risultati_grezzi)
    arricchisci_stats_contatti(ammessi, stats)
    stampa_report(contatore, celle_processate, celle_sature, stats)
    stampa_top20(ammessi)

    if not args.dry_run:
        salva_jsonl(risultati_grezzi, args.out)
    else:
        print("\n--dry-run: nessun file scritto.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
