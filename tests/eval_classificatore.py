"""python3 tests/eval_classificatore.py

Chiama l'API Anthropic per davvero (non è un mock): serve a misurare il
prompt vero, non solo il parsing del JSON. Va rilanciato dopo ogni modifica
al prompt in brain/classifier.py."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from connectors.llm import carica_env  # noqa: E402

carica_env()

from brain.classifier import classifica, ClassificazioneErrore  # noqa: E402

CASI = [
    # --- interessato ---
    {
        "descrizione": "interessato: vuole aderire subito",
        "mittente": "Mario Rossi <mario@hotelroma.it>",
        "oggetto": "Poster ricevuto",
        "testo": "Buongiorno, ho ricevuto il poster e mi interessa molto. Come faccio ad attivare il codice sconto per i miei ospiti?",
        "attesa": "interessato",
    },
    {
        "descrizione": "interessato: chiede il prossimo passo",
        "mittente": "Giulia Bianchi <giulia@bnbfiori.it>",
        "oggetto": None,
        "testo": "Salve, vorrei partecipare al programma. Cosa devo fare adesso?",
        "attesa": "interessato",
    },
    # --- domanda (coperta da conoscenza.md) ---
    {
        "descrizione": "domanda: prezzo di un tour specifico per l'ospite",
        "mittente": "Anna Verdi <anna@hotelcentro.it>",
        "oggetto": "Info prezzi",
        "testo": "Buongiorno, quanto costa il tour Vatican con lo sconto?",
        "attesa": "domanda",
    },
    {
        "descrizione": "domanda: come funziona per l'ospite",
        "mittente": "Luca Neri <luca@residenceroma.it>",
        "oggetto": "Domanda",
        "testo": "Serve scaricare un'app per fare il tour? E quanto dura?",
        "attesa": "domanda",
    },
    {
        "descrizione": "domanda: durata accesso",
        "mittente": "host@example.com",
        "oggetto": None,
        "testo": "L'accesso al tour scade dopo un tot di giorni o resta valido per sempre?",
        "attesa": "domanda",
    },
    # --- obiezione ---
    {
        "descrizione": "obiezione: dubbio sia una truffa",
        "mittente": "Paolo Gialli <paolo@hotelverdi.it>",
        "oggetto": "Perplesso",
        "testo": "Sinceramente mi sembra troppo bello per essere vero, come faccio a fidarmi che non sia una truffa?",
        "attesa": "obiezione",
    },
    {
        "descrizione": "obiezione: non ha tempo/interesse a gestire altro",
        "mittente": "info@bnbtrastevere.it",
        "oggetto": None,
        "testo": "Non so, gestire ancora un'altra cosa in reception mi sembra complicato, non abbiamo tempo per queste iniziative.",
        "attesa": "obiezione",
    },
    # --- prezzo_o_contratto ---
    {
        "descrizione": "prezzo_o_contratto: chiede di negoziare la commissione",
        "mittente": "Mario Rossi <mario@hotelroma.it>",
        "oggetto": "Domande sul codice sconto",
        "testo": "Ho ricevuto il poster ma non ho capito come funziona la commissione per me come host: è calcolata su ogni prenotazione o solo sulla prima? E se voglio una percentuale diversa?",
        "attesa": "prezzo_o_contratto",
    },
    {
        "descrizione": "prezzo_o_contratto: chiede un contratto scritto",
        "mittente": "amministrazione@hotelduemari.it",
        "oggetto": "Contratto",
        "testo": "Prima di aderire vorrei un contratto scritto con le condizioni di pagamento, è possibile averlo?",
        "attesa": "prezzo_o_contratto",
    },
    {
        "descrizione": "confine domanda/prezzo_o_contratto: prezzo guest, non commissione",
        "mittente": "reception@hotelpantheon.it",
        "oggetto": None,
        "testo": "Il bundle Essential quanto costa esattamente con lo sconto ospite?",
        "attesa": "domanda",
    },
    # --- non_interessato ---
    {
        "descrizione": "non_interessato: rifiuto netto",
        "mittente": "Sara Blu <sara@hotelroma2.it>",
        "oggetto": "No grazie",
        "testo": "Grazie ma non siamo interessati a questo tipo di collaborazione.",
        "attesa": "non_interessato",
    },
    {
        "descrizione": "non_interessato: già ha un servizio simile",
        "mittente": "direzione@residencesolare.it",
        "oggetto": None,
        "testo": "Abbiamo già un accordo con un altro operatore di tour, non ci serve altro, grazie.",
        "attesa": "non_interessato",
    },
    # --- disiscrizione ---
    {
        "descrizione": "disiscrizione: chiede di essere rimosso",
        "mittente": "fastidio@hotelxyz.it",
        "oggetto": "Rimuovetemi",
        "testo": "Vi prego di rimuovermi dalla vostra lista, non contattatemi più.",
        "attesa": "disiscrizione",
    },
    {
        "descrizione": "disiscrizione: unsubscribe esplicito",
        "mittente": "info@hotelabc.it",
        "oggetto": None,
        "testo": "STOP, non voglio più ricevere email da voi.",
        "attesa": "disiscrizione",
    },
    {
        "descrizione": "confine obiezione/disiscrizione: dubbio, non chiede di essere rimosso",
        "mittente": "titolare@bnblanterna.it",
        "oggetto": None,
        "testo": "Non sono convinto che funzioni davvero, ho i miei dubbi su questa cosa.",
        "attesa": "obiezione",
    },
    # --- fuori_tema ---
    {
        "descrizione": "fuori_tema: contenuto non pertinente",
        "mittente": "newsletter@qualcosaltro.it",
        "oggetto": "Offerta imperdibile",
        "testo": "Approfitta subito del nostro corso di fotografia con sconto del 30%!",
        "attesa": "fuori_tema",
    },
    {
        "descrizione": "fuori_tema: domanda su altro servizio dell'hotel",
        "mittente": "clienti@hotelmarina.it",
        "oggetto": None,
        "testo": "Volevo sapere se avete camere disponibili per il weekend del 20.",
        "attesa": "fuori_tema",
    },
    # --- ulteriori casi ambigui/di rinforzo ---
    {
        "descrizione": "domanda: bambini/adattabilità (dato mancante in conoscenza.md)",
        "mittente": "famiglia@hotelbimbi.it",
        "oggetto": None,
        "testo": "I tour sono adatti anche ai bambini piccoli?",
        "attesa": "domanda",
    },
    {
        "descrizione": "interessato con richiesta pratica del kit",
        "mittente": "reception@hotelfontana.it",
        "oggetto": "Kit host",
        "testo": "Perfetto, aderiamo! Quando arriva il kit con i poster?",
        "attesa": "interessato",
    },
    {
        "descrizione": "obiezione: teme reazione negativa degli ospiti",
        "mittente": "manager@hotelquattro.it",
        "oggetto": None,
        "testo": "Ho paura che gli ospiti si infastidiscano se propongo loro un altro servizio a pagamento.",
        "attesa": "obiezione",
    },
    {
        "descrizione": "prezzo_o_contratto: chiede quando arriva il pagamento",
        "mittente": "contabilita@hotelsette.it",
        "oggetto": "Pagamento",
        "testo": "A che scadenza viene liquidata la commissione maturata questo mese?",
        "attesa": "prezzo_o_contratto",
    },
]


def main():
    falliti = 0
    for caso in CASI:
        try:
            esito = classifica(caso["mittente"], caso["oggetto"], caso["testo"])
            ottenuta = esito["categoria"]
        except ClassificazioneErrore as e:
            ottenuta = f"ERRORE({e})"

        if ottenuta != caso["attesa"]:
            falliti += 1
            print(f"FALLITO: {caso['descrizione']} — atteso {caso['attesa']!r}, ottenuto {ottenuta!r}")

    passati = len(CASI) - falliti
    print(f"{passati}/{len(CASI)} casi passati")
    return 0 if falliti == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
