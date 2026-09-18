"""Le eval chiamano l'LLM fuori dal tetto di produzione.

Il 18/9/2026 eval_modi_argo ha portato llm_chiamate_giorno a 151/150: è lo
stesso contatore del consumer di Argo, che è rimasto muto fino a mezzanotte.
Da qui ogni tests/eval_*.py chiama prepara_eval() PRIMA di importare
argo.voce o brain.*, e sceglie uno di due modi:

- default, OpenRouter: le chiamate passano da connectors/llm.py:chiama con
  sensibile=False e un modello gratuito (quota openrouter_chiamate_giorno,
  contratto CD07), fallback=False — quota finita = eval ferma, mai un
  ripiego su Anthropic. Il contatore Anthropic è sostituito da uno che
  solleva: una chiamata sfuggita allo scambio si blocca prima dell'HTTP.
- --anthropic, solo esplicito: il modello vero (Haiku), con il contatore
  in-memory del processo — spesa sotto tetto, llm_chiamate_giorno mai
  toccato.

In nessuno dei due modi un'eval raggiunge llm_chiamate_giorno
(test: tests/test_llm_eval.py). Il codice di produzione non cambia: si
sostituisce solo il nome `chiama` nei moduli che lo importano.

Un modello diverso da Haiku misura il prompt, non la produzione: per
chiudere un passo sulla voce serve comunque un giro --anthropic.
"""
import re
import sys
import time

from connectors import llm

# Endpoint ZDR gratuito (elenco pubblico openrouter.ai/api/v1/endpoints/zdr).
# 18/9: deepseek-v4-flash:free ragionava oltre 8200 token senza testo su
# instrada; glm-5.2:free (Decart, contesto 32k) ha risposto con 1475 token
# in 32 s sullo stesso caso. Il listino ruota: --modello per cambiarlo.
MODELLO_EVAL_DEFAULT = "z-ai/glm-5.2:free"
MODULI_CON_CHIAMA = ("argo.voce", "brain.classifier", "brain.drafter")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
OSCURATO = "[oscurato]"
ESITO_QUOTA_ESAURITA = 2
# Un endpoint gratuito risponde spesso 429 (limite al minuto del provider).
# Ogni nuovo tentativo consuma quota: al massimo due.
TENTATIVI_429 = 2
ATTESA_429_DEFAULT_SEC = 20
ATTESA_429_MAX_SEC = 60
# Tutti i modelli di testo gratuiti ZDR (elenco pubblico, 18/9/2026)
# ragionano prima di rispondere: con i max_tokens di produzione (150-200) il
# ragionamento li consuma e il testo arriva vuoto. Margine solo sul ramo
# gratuito dell'eval (scelta di Leonardo, 18/9): gateway e produzione
# invariati. Limite: il troncamento in eval scatta più tardi che in
# produzione, quindi i marcatori di troncamento non si misurano qui.
MARGINE_RAGIONAMENTO_EVAL = 8000  # 18/9: instrada ha usato 6215 token di uscita, 230 s

_config = {"modo": None, "modello": None, "oscura_email": True}


class AnthropicVietatoInEval(Exception):
    """Sollevata dal contatore Anthropic in modo OpenRouter: una chiamata
    arrivata al ramo Anthropic è sfuggita allo scambio di `chiama`."""


def _vietato(giorno):
    raise AnthropicVietatoInEval("chiamata Anthropic in un'eval senza --anthropic")


def oscura_email(testo):
    return _EMAIL_RE.sub("[email oscurata]", testo or "")


def chiama_eval(system, prompt, max_tokens=500, temperature=0.0, marcatore_se_troncato=None):
    """Stessa firma di connectors/llm.py:chiama per i chiamanti di produzione,
    ma sul ramo gratuito. Seconda cintura CD07: ogni indirizzo email esce
    oscurato, anche se è arrivato da un testo libero (es. STATO.md)."""
    from connectors.openrouter import ErroreOpenRouter, TettoOpenRouterRaggiunto
    if _config["oscura_email"]:
        system, prompt = oscura_email(system), oscura_email(prompt)
    for tentativo in range(1, TENTATIVI_429 + 2):
        try:
            return llm.chiama(
                system, prompt, max_tokens=max_tokens + MARGINE_RAGIONAMENTO_EVAL, temperature=temperature,
                marcatore_se_troncato=marcatore_se_troncato,
                sensibile=False, modello=_config["modello"], fallback=False,
            )
        except TettoOpenRouterRaggiunto:
            raise
        except ErroreOpenRouter as e:
            # Il gateway fa un solo tentativo e lascia al chiamante la
            # decisione: qui si riprova solo su 429, dopo retry_after.
            if "status=429" not in str(e) or tentativo > TENTATIVI_429:
                raise
            attesa = min(e.retry_after or ATTESA_429_DEFAULT_SEC, ATTESA_429_MAX_SEC)
            print(f"eval: 429 dal provider gratuito, riprovo fra {attesa}s ({tentativo}/{TENTATIVI_429})")
            time.sleep(attesa)


def prepara_eval(argv, oscura_email=True):
    """Legge --anthropic e --modello <id> da argv e ritorna gli argomenti
    rimasti. Va chiamata prima di importare i moduli in MODULI_CON_CHIAMA.
    `oscura_email=False` solo per eval con casi scritti a mano (nessun dato
    di terzi)."""
    resto, anthropic, modello = [], False, MODELLO_EVAL_DEFAULT
    i = 0
    while i < len(argv):
        if argv[i] == "--anthropic":
            anthropic = True
        elif argv[i] == "--modello" and i + 1 < len(argv):
            modello = argv[i + 1]
            i += 1
        else:
            resto.append(argv[i])
        i += 1

    llm.carica_env()
    if anthropic:
        llm.usa_contatore_in_memoria()
        for nome in MODULI_CON_CHIAMA:
            __import__(nome, fromlist=["chiama"]).chiama = llm.chiama
        _config.update(modo="anthropic", modello=None, oscura_email=oscura_email)
        print("eval: modello vero (Anthropic), contatore in-memory — llm_chiamate_giorno non toccato")
        return resto

    llm.usa_contatore_persistente(_vietato, "eval: Anthropic vietato senza --anthropic")
    _config.update(modo="openrouter", modello=modello, oscura_email=oscura_email)
    for nome in MODULI_CON_CHIAMA:
        modulo = __import__(nome, fromlist=["chiama"])
        modulo.chiama = chiama_eval
    print(f"eval: OpenRouter {modello} (quota gratuita, --anthropic per il modello vero)")
    return resto


def quota_esaurita(errore):
    """Vero se l'errore (o la sua causa, spesso avvolta in ConversazioneErrore
    o ImpattoErrore) è la quota gratuita finita."""
    from connectors.openrouter import TettoOpenRouterRaggiunto
    while errore is not None:
        if isinstance(errore, TettoOpenRouterRaggiunto):
            return True
        errore = errore.__cause__ or errore.__context__
    return False


def esci_se_quota_esaurita(errore):
    if quota_esaurita(errore):
        print("eval fermata: quota gratuita OpenRouter del giorno esaurita (non è un caso fallito)")
        sys.exit(ESITO_QUOTA_ESAURITA)


def oscura_stato(modulo_stato):
    """Prima cintura CD07 per le eval sullo stato vero: mittente e oggetto
    delle approvazioni (email di prospect), ultimo_errore dei job (anche
    job_falliti_recenti, usata da avvisa) e il testo
    libero delle osservazioni (nuove e recenti, quest'ultima letta da una
    consultazione della conversazione) diventano "[oscurato]". Oggi la
    tabella osservazioni è vuota, ma una pipeline che ci scriverà testo di
    prospect non deve arrivare al ramo gratuito. Id e date restano: i
    controlli della riga Fatti li usano. escalation_aperte porta solo chiavi
    di alert di sistema; un indirizzo lì dentro lo toglie chiama_eval."""
    originale_appr = modulo_stato.approvazioni_in_attesa
    originale_job = modulo_stato.job_falliti

    def approvazioni_in_attesa():
        risultato = originale_appr()
        for riga in risultato.get("righe") or []:
            for campo in ("mittente", "oggetto"):
                if campo in riga:
                    riga[campo] = OSCURATO
        return risultato

    def job_falliti():
        risultato = originale_job()
        for riga in risultato.get("falliti") or []:
            if "ultimo_errore" in riga:
                riga["ultimo_errore"] = OSCURATO
        return risultato

    def _oscura_campo(originale, campo):
        def funzione(*args, **kwargs):
            risultato = originale(*args, **kwargs)
            for riga in risultato.get("righe") or []:
                if campo in riga:
                    riga[campo] = OSCURATO
            return risultato
        return funzione

    modulo_stato.approvazioni_in_attesa = approvazioni_in_attesa
    modulo_stato.job_falliti = job_falliti
    modulo_stato.osservazioni_nuove = _oscura_campo(modulo_stato.osservazioni_nuove, "testo")
    modulo_stato.osservazioni_recenti = _oscura_campo(modulo_stato.osservazioni_recenti, "testo")
    # Usata da genera_avviso, oggi non nei CASI: chiusa comunque per costruzione.
    modulo_stato.job_falliti_recenti = _oscura_campo(modulo_stato.job_falliti_recenti, "ultimo_errore")
