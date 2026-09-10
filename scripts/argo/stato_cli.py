#!/usr/bin/env python3
"""Harness di collaudo per argo/stato.py — sola lettura, zero LLM, zero bot.

Stampa a terminale l'output delle sei funzioni di lettura, così si vede cosa
Argo vedrebbe oggi senza che esista ancora un bot. Va lanciato da host (non
dentro un container): legge STATO.md e git dal filesystem del repo, e le
fonti DB passano da `docker exec argo-db-1 psql` (vedi argo/stato.py).

Uso:
    python3 scripts/argo/stato_cli.py            # leggibile
    python3 scripts/argo/stato_cli.py --json      # JSON strutturato
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
import argo.stato as stato  # noqa: E402


FONTI = [
    ("approvazioni_in_attesa", stato.approvazioni_in_attesa),
    ("job_falliti", stato.job_falliti),
    ("escalation_aperte", stato.escalation_aperte),
    ("osservazioni_nuove", stato.osservazioni_nuove),
    ("cantieri_aperti", stato.cantieri_aperti),
    ("attivita_git", stato.attivita_git),
]


def _riga(etichetta, valore):
    return f"  {etichetta}: {valore}"


def stampa_leggibile(risultati):
    for nome, dati in risultati.items():
        copertura = dati.get("copertura", "?")
        marcatore = {"completa": "✓", "parziale": "△", "assente": "✗"}.get(copertura, "?")
        print(f"\n== {nome} [{marcatore} copertura: {copertura}] ==")
        if dati.get("motivo"):
            print(f"  motivo: {dati['motivo']}")

        if nome == "approvazioni_in_attesa":
            righe = dati["righe"]
            if not righe:
                print("  nessuna approvazione in attesa.")
            for r in righe:
                print(_riga(
                    f"#{r['id']}",
                    f"{r['stato']} da {r['ore_ferma']:.1f}h — "
                    f"{r.get('mittente') or '(mittente ignoto)'} — "
                    f"\"{r.get('oggetto') or '(senza oggetto)'}\"",
                ))

        elif nome == "job_falliti":
            print(f"  soglia coda: {dati['soglia_coda_minuti']} minuti")
            print("  -- falliti (aggregati per tipo+errore) --")
            if not dati["falliti"]:
                print("    nessuno.")
            for f in dati["falliti"]:
                print(_riga(
                    f['tipo'],
                    f"{f['quante']}x, più recente {f['piu_recente']} — {f['ultimo_errore']}",
                ))
            print("  -- fermi (stato running) --")
            if not dati["fermi"]:
                print("    nessuno.")
            for j in dati["fermi"]:
                print(_riga(f"#{j['id']} {j['tipo']}", f"tentativi={j['tentativi']}, creato {j['created_at']}"))
            print("  -- in coda da troppo --")
            if not dati["in_coda_da_troppo"]:
                print("    nessuno.")
            for j in dati["in_coda_da_troppo"]:
                print(_riga(f"#{j['id']} {j['tipo']}", f"run_after={j['run_after']}"))

        elif nome == "escalation_aperte":
            print(f"  finestra: ultime {dati.get('finestra_ore', '?')}h")
            righe = dati["righe"]
            if not righe:
                print("  nessun alert nella finestra.")
            for r in righe:
                print(_riga(r["chiave"], f"{r['categoria']} — {r['created_at']}"))
            if dati.get("non_visibili_da_qui"):
                print("  non visibili da questa fonte:")
                for voce in dati["non_visibili_da_qui"]:
                    print(f"    - {voce}")

        elif nome == "osservazioni_nuove":
            righe = dati["righe"]
            if not righe:
                print("  nessuna osservazione nuova.")
            for r in righe:
                print(_riga(
                    f"#{r['id']}",
                    f"[{r['severita']}] {r['fonte']} — {r['testo']}",
                ))

        elif nome == "cantieri_aperti":
            print("  -- cantieri (blocco strutturato) --")
            if dati["cantieri"] is None:
                print("    (non disponibile, vedi motivo sopra)")
            else:
                for c in dati["cantieri"]:
                    print(_riga(
                        c["nome"],
                        f"{c['stato']} — aperto il {c['aperto_il']} — aspetta: {c['aspetta']} — "
                        f"{c['sessione_riferimento']}",
                    ))
            print("  -- In corso --")
            print(f"    {dati['in_corso'] or '(sezione assente)'}")
            print("  -- DECISIONI APERTE — bloccano --")
            print(f"    {dati['decisioni_aperte_bloccano'] or '(sezione assente)'}")
            print("  -- ultime sessioni (indice grezzo) --")
            for s in dati["sessioni_recenti"]:
                print(_riga(f"riga {s['riga']}", s["titolo"]))

        elif nome == "attivita_git":
            if dati.get("ultimo_commit_giorni_fa") is not None:
                print(f"  ultimo commit: {dati['ultimo_commit_giorni_fa']:.2f} giorni fa")
            print("  -- commit recenti --")
            for c in dati["commits_recenti"]:
                print(_riga(c["hash"][:8], f"{c['data']} {c['autore']} — {c['oggetto']}"))
            print("  -- modifiche non committate --")
            if not dati["modifiche_non_committate"]:
                print("    nessuna.")
            for m in dati["modifiche_non_committate"]:
                print(_riga(m["stato"], m["path"]))


def main():
    parser = argparse.ArgumentParser(description="Harness di collaudo per argo/stato.py")
    parser.add_argument("--json", action="store_true", help="stampa JSON invece del formato leggibile")
    args = parser.parse_args()

    risultati = {nome: fn() for nome, fn in FONTI}

    if args.json:
        print(json.dumps(risultati, indent=2, default=str, ensure_ascii=False))
    else:
        stampa_leggibile(risultati)


if __name__ == "__main__":
    main()
