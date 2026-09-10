#!/usr/bin/env python3
"""
Ricompone yourservice-it in locale per il test di fedelta N.1 (cantiere
Designer, passo 2, Fase B).

Metodo: concatenazione LETTERALE degli 8 file di blocco, nell'ordine del
builder, dentro un unico shell HTML. Non si fa estrazione manuale di
head/body dai blocchi che contengono un <!DOCTYPE>/<html>/<head>/<body>
proprio (header, footer, body_mobile_per_host): sono incollati cosi' come
sono, esattamente come li inserisce GHL nella pagina reale. E' il parser
HTML del browser a fondere i tag <html>/<head>/<body> annidati con quelli
del documento reale (regole standard di "tag omission" dell'HTML5) - lo
stesso meccanismo che avviene dal vivo, quindi e' la ricomposizione piu'
fedele possibile senza inventare markup che non abbiamo.

Non include il "CSS globale del sito" (Head/Body tracking code di GHL):
non esiste una copia salvata nel repo, solo i valori misurati in
modalita/baseline_narratours.md. I blocchi dichiarano di essere
autosufficienti (variabili CSS scoped alla sezione, non su :root) - se
questo test NON riproduce i FAIL noti della baseline, l'assunzione e'
sbagliata e va segnalata, non aggirata.

Include anche css_piattaforma_ghl.html (11/09/2026, Fase C): riproduzione
delle tre classi di visibilita' colonna di GHL (.desktop-only/.tablet-hide/
.mobile-only), misurate sulla pagina live intatta, applicate direttamente
alle due hero. Senza questo file il locale mostra sempre ENTRAMBE le hero
contemporaneamente (nessuna classe di piattaforma nel markup dei blocchi) -
non e' una regressione, e' l'assenza nota del CSS di piattaforma. Con
questo file il locale diventa rappresentativo del comportamento reale.
"""
import pathlib

BASE = pathlib.Path(__file__).resolve().parent.parent
QUI = pathlib.Path(__file__).resolve().parent
ORDINE = [
    "blocco_header.html",
    # blocco_gtranslate.html ESCLUSO dal test di fedelta N.1: la sua
    # posizione nel builder non e' confermata (vedi commento nel file
    # stesso) e il suo widget CDN (cdn.gtranslate.net) fa scattare una
    # sfida Cloudflare Turnstile che blocca indefinitamente l'evento
    # 'load' di Playwright in questo ambiente -- non riproducibile in
    # locale, non necessario per i FAIL richiesti (h1, crash React, 404).
    # Vedi nota nel report di bonifica.
    "blocco_01.html",
    "blocco_02.html",
    "blocco_03.html",
    "blocco_hero_mobile_v3.html",
    "blocco_body_mobile_per_host.html",
    "blocco_footer.html",
]

HEAD = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>yourservice-it -- ricomposizione locale (test di fedelta N.1)</title>
</head>
<body>
<!--
  RICOMPOSIZIONE LOCALE PER TEST DI FEDELTA N.1 -- NON E' UN BLOCCO DA
  INCOLLARE IN GHL. Concatenazione letterale, ordine builder dichiarato
  nell'orientamento del cantiere Designer passo 2. Vedi costruisci.py.
-->
"""

TAIL = """
</body>
</html>
"""

def main():
    parti = [HEAD]
    css_piattaforma = (QUI / "css_piattaforma_ghl.html").read_text(encoding="utf-8")
    parti.append(css_piattaforma)
    for nome in ORDINE:
        percorso = BASE / nome
        contenuto = percorso.read_text(encoding="utf-8")
        parti.append(f"\n<!-- ===== INIZIO {nome} ===== -->\n")
        parti.append(contenuto)
        parti.append(f"\n<!-- ===== FINE {nome} ===== -->\n")
    parti.append(TAIL)

    out = pathlib.Path(__file__).resolve().parent / "ricomposizione.html"
    out.write_text("".join(parti), encoding="utf-8")
    print(f"Scritto {out} ({out.stat().st_size} byte)")

if __name__ == "__main__":
    main()
