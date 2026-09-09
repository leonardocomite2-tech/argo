// Utilità condivise tra cattura.mjs e pavimento.mjs (secondo uso reale della stessa logica).
import { mkdirSync, existsSync, appendFileSync, readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

export const NAV_TIMEOUT_MS = 30_000;
// sites.leadconnectorhq.com: URL di anteprima GoHighLevel (/preview/<pageId>) — flusso
// standard di verifica, non un'eccezione da ricordare col flag --domains.
export const DEFAULT_DOMAINS = ['narra-tours.com', 'sites.leadconnectorhq.com'];
export const BREAKPOINTS = [360, 390, 768, 1024, 1440];
export const VIEWPORTS = [
  { name: 'mobile', width: 390, height: 844 },
  { name: 'desktop', width: 1440, height: 900 },
];

export const CHROMIUM_ARGS = ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'];

export function parseArgs(argv) {
  const args = { _: [] };
  for (const a of argv) {
    if (a.startsWith('--domains=')) {
      args.domains = a.slice('--domains='.length).split(',').map((s) => s.trim()).filter(Boolean);
    } else if (a.startsWith('--out=')) {
      args.out = a.slice('--out='.length);
    } else if (a.startsWith('--budget-kb=')) {
      args.budgetKb = Number(a.slice('--budget-kb='.length));
    } else {
      args._.push(a);
    }
  }
  return args;
}

export function isUrl(input) {
  return /^https?:\/\//i.test(input);
}

export function assertDomainAllowed(input, allowedDomains) {
  if (!isUrl(input)) return; // file locale: nessuna restrizione di dominio
  const host = new URL(input).hostname.replace(/^www\./, '');
  const ok = allowedDomains.some((d) => host === d || host.endsWith(`.${d}`));
  if (!ok) {
    throw new Error(
      `Dominio non consentito: ${host}. Domini ammessi: ${allowedDomains.join(', ')}. ` +
        `Passa --domains=dominio1,dominio2 per estendere l'elenco.`,
    );
  }
}

export function resolveTarget(input) {
  return isUrl(input) ? input : `file://${path.resolve(input)}`;
}

export function slugFor(input) {
  if (isUrl(input)) {
    const url = new URL(input);
    return (
      (url.hostname + url.pathname).replace(/[^a-z0-9]+/gi, '-').replace(/^-+|-+$/g, '').toLowerCase() || 'root'
    );
  }
  return path.basename(input).replace(/[^a-z0-9]+/gi, '-').toLowerCase();
}

export function timestamp() {
  return new Date().toISOString().replace(/[:.]/g, '-');
}

export function defaultOutDir() {
  const dir = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'output');
  mkdirSync(dir, { recursive: true });
  return dir;
}

// --- Misura RAM durante l'esecuzione (per il log CSV) ---

export function ramAvailableMiB() {
  try {
    const meminfo = readFileSync('/proc/meminfo', 'utf8');
    const m = meminfo.match(/MemAvailable:\s+(\d+)\s+kB/);
    return m ? Math.round(Number(m[1]) / 1024) : null;
  } catch {
    return null;
  }
}

// Somma la RSS di tutti i processi Chromium/headless-shell attivi (il browser headless
// lancia più processi: main, renderer, gpu, zygote — vanno sommati per avere il consumo
// reale, non solo quello del processo principale).
export function chromiumRssMiB() {
  try {
    const out = execSync('ps -eo rss,args', { encoding: 'utf8' });
    let sumKb = 0;
    for (const line of out.split('\n')) {
      if (/chrome-linux64\/chrome|chrome-headless-shell/.test(line) && !line.includes('grep')) {
        const rss = parseInt(line.trim().split(/\s+/)[0], 10);
        if (!Number.isNaN(rss)) sumKb += rss;
      }
    }
    return Math.round(sumKb / 1024);
  } catch {
    return null;
  }
}

// Campiona RSS Chromium + RAM available a intervalli regolari mentre uno script gira,
// per registrare il picco nel log CSV (§4 della modalità NarraTours).
export class MonitorRisorse {
  constructor(intervalMs = 300) {
    this.maxChromiumRssMiB = null;
    this.minAvailableMiB = null;
    this._timer = setInterval(() => {
      const rss = chromiumRssMiB();
      const avail = ramAvailableMiB();
      if (rss !== null) this.maxChromiumRssMiB = Math.max(this.maxChromiumRssMiB ?? 0, rss);
      if (avail !== null) this.minAvailableMiB = Math.min(this.minAvailableMiB ?? Infinity, avail);
    }, intervalMs);
    this._timer.unref?.();
  }

  stop() {
    clearInterval(this._timer);
    return { maxChromiumRssMiB: this.maxChromiumRssMiB, minAvailableMiB: this.minAvailableMiB };
  }
}

// --- Log CSV (output/log_runs.csv) ---

const LOG_CSV_HEADER =
  'timestamp,script,target,rss_chromium_max_mib,ram_available_min_mib,peso_kb,esito_pavimento,durata_s\n';

function csvCampo(v) {
  const s = v === null || v === undefined ? '' : String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function scriviLogRun(outDir, riga) {
  const csvPath = path.join(outDir, 'log_runs.csv');
  if (!existsSync(csvPath)) appendFileSync(csvPath, LOG_CSV_HEADER);
  const campi = [
    riga.timestamp,
    riga.script,
    riga.target,
    riga.rssChromiumMaxMib,
    riga.ramAvailableMinMib,
    riga.pesoKb,
    riga.esitoPavimento,
    riga.durataS,
  ].map(csvCampo);
  appendFileSync(csvPath, campi.join(',') + '\n');
  return csvPath;
}
