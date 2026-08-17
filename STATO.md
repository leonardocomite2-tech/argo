# STATO — aggiornare a fine di ogni step

## Fatto
- VPS Hostinger KVM1, Ubuntu 24.04, Docker + Compose
- 4 container: caddy (HTTPS ok) · api (FastAPI, /health) · worker (poll jobs 5s) · db (Postgres)
- argo.narratour-review.com → certificato Let's Encrypt valido
- Schema DB: contacts, identities, events, messages, approvals, jobs
- Git init + primo commit. Claude Code 2.1.233 + CLAUDE.md + subagent guardrail-review

## In corso
(step 4 chiuso: worker/loop.py, poll ogni 5s con FOR UPDATE SKIP LOCKED, registro
@handler, retry max 2 tentativi poi failed, recovery job orfani all'avvio)
- Step 5: poster.py + coordinate

## Prossimi step (cantiere 1 — poster)
5. poster.py + coordinate
6. invio email                 7. Telegram                8. workflow GHL

## DECISIONI APERTE — bloccano
- **QR e attribuzione**: il QR punta a narra-tours.com/rome-en, uguale per tutti.
  Come si sa da quale host arriva il visitatore? Se serve attribuzione → QR
  generato per host con ?ref=CODICE (libreria qrcode, deterministico).
  Se esistono più pagine per citta/lingua, il QR statico unico non basta.
  → DA DECIDERE PRIMA DELLO STEP 5
- Provider caselle Instantly + casella pulita (serve al cantiere 2)
- Tono delle risposte: tu o lei, quanto sintetico (serve al drafter)

## DATI MANCANTI
- poster_base.png (senza testo codice, QR incluso) — da esportare da Canva
- poster_con_codice.png (stesse dimensioni, con codice esempio)
- nome del font usato nel Canva

## Note operative
- DNS: narratour-review.com → zona su HOSTINGER
        narra-tours.com     → zona su CLOUDFLARE
- Segreti in /root/argo/.env (mai committato)
