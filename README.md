# Argo

## DNS — attenzione, due pannelli diversi
- narratour-review.com  → zona su HOSTINGER   (argo.* = API, A record, TTL 14400)
- narra-tours.com       → zona su CLOUDFLARE  (sito pubblico, destinazione QR)

Se sposti il VPS: abbassa il TTL a 300 qualche ora prima del cambio.

## Avvio
docker compose up -d --build
