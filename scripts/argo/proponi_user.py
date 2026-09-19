#!/usr/bin/env python3
"""python3 scripts/argo/proponi_user.py [--collaudo]

Argo — la voce, passo 14. Da host, come il consumer.

Senza argomenti: stampa cosa Argo proporrebbe oggi per USER.md con le soglie
di produzione (argo/impara.py), e i fatti calcolati anche sotto soglia.
Nessuna scrittura, nessun invio.

--collaudo: calcola sui dati veri saltando le soglie di campione e il tetto
di una proposta al giorno (non la chiave già proposta, non il tetto di
lunghezza), scrive la riga argo_proposta in conversazione_argo e manda la
proposta col bot di Argo. La riga dichiara sempre il campione. La conferma
arriva come in produzione: Leonardo risponde sì o no, il consumer scrive.
"""

import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))

import scripts.argo.orienta_webhook as consumer  # noqa: E402  (carica .env)
from argo import impara  # noqa: E402


def main(argv):
    collaudo = argv == ["--collaudo"]
    if argv and not collaudo:
        print(__doc__)
        return 2
    oggi = datetime.now(impara.FUSO_ROMA).date()
    richieste, finestre = impara.richieste_leonardo(), impara.finestre_dichiarate()
    print(f"Richieste di Leonardo: {len(richieste)}; finestre dichiarate: {len(finestre)}")
    for fatto in impara.calcola_fatti(richieste, finestre, forza=True):
        print(f"  calcolato: {impara.riga_per(fatto, oggi)}")

    proposta, motivo = impara.prepara_proposta(forza=collaudo)
    if proposta is None:
        print(f"Nessuna proposta: {motivo}.")
        return 0
    print("\nProposta:\n" + proposta)
    if collaudo:
        consumer.invia_proposta(proposta)
        print("\nScritta in conversazione_argo e mandata.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
