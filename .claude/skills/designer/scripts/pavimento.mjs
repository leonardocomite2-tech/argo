#!/usr/bin/env node
// Controlli deterministici (il "pavimento"): contrasto/accessibilità, peso, breakpoint,
// console, gerarchia dei titoli. Un solo Chromium alla volta, mai Lighthouse insieme
// (Lighthouse non è nemmeno installato in questo progetto — vedi modalità).
// Uso: node pavimento.mjs <url-o-file-html> [--domains=...] [--budget-kb=NNN] [--out=cartella]
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import {
  NAV_TIMEOUT_MS,
  DEFAULT_DOMAINS,
  BREAKPOINTS,
  CHROMIUM_ARGS,
  parseArgs,
  assertDomainAllowed,
  resolveTarget,
  slugFor,
  timestamp,
  defaultOutDir,
  MonitorRisorse,
  scriviLogRun,
} from './lib.mjs';

const REPORT_VIEWPORT = { width: 1440, height: 900 };

async function run(input, { allowedDomains, budgetKb }) {
  assertDomainAllowed(input, allowedDomains);
  const target = resolveTarget(input);

  const browser = await chromium.launch({ headless: true, args: CHROMIUM_ARGS });
  const requests = [];
  const consoleErrors = [];
  const pageErrors = [];
  const failedRequests = [];

  try {
    const context = await browser.newContext({ viewport: REPORT_VIEWPORT });
    const page = await context.newPage();
    page.setDefaultNavigationTimeout(NAV_TIMEOUT_MS);
    page.setDefaultTimeout(NAV_TIMEOUT_MS);

    page.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(msg.text());
    });
    page.on('pageerror', (err) => pageErrors.push(err.message));
    page.on('requestfailed', (request) => {
      failedRequests.push({ url: request.url(), failure: request.failure()?.errorText ?? 'sconosciuto' });
    });
    page.on('requestfinished', async (request) => {
      let sizes = null;
      try {
        sizes = await request.sizes();
      } catch {
        sizes = null;
      }
      requests.push({
        url: request.url(),
        resourceType: request.resourceType(),
        bytes: sizes ? sizes.responseBodySize + sizes.responseHeadersSize : 0,
      });
    });

    // 'load' invece di 'networkidle': siti reali con chat widget/tracker mantengono
    // connessioni aperte all'infinito, 'networkidle' andrebbe sempre in timeout.
    await page.goto(target, { waitUntil: 'load', timeout: NAV_TIMEOUT_MS });

    // Contrasto e accessibilità
    const axeResults = await new AxeBuilder({ page }).analyze();
    const violationsBySeverity = { critical: 0, serious: 0, moderate: 0, minor: 0 };
    const violationDetails = [];
    for (const v of axeResults.violations) {
      violationsBySeverity[v.impact ?? 'moderate'] =
        (violationsBySeverity[v.impact ?? 'moderate'] ?? 0) + v.nodes.length;
      violationDetails.push({ id: v.id, impact: v.impact, help: v.help, occorrenze: v.nodes.length });
    }
    const contrastViolations = violationDetails.filter((v) => v.id.includes('color-contrast'));

    // Gerarchia titoli — conta gli h1 ESPOSTI (accessibility tree), non i nodi grezzi
    // del DOM. Un h1 dietro display:none/visibility:hidden/[hidden]/aria-hidden non
    // è visto da uno screen reader e non è un problema di accessibilità o SEO: due
    // h1 nel sorgente HTML sono validi in HTML5 finché uno solo è esposto per volta
    // (caso reale: varianti desktop/mobile con lo stesso ruolo, una sola visibile
    // per viewport). Contare i nodi grezzi era un proxy che misurava la cosa
    // sbagliata — vedi modalita/narratours.md §pavimento per il caso che l'ha
    // scoperto (10/09/2026, yourservice-it).
    const headings = await page.evaluate(() => {
      function esposto(el) {
        if (typeof el.checkVisibility === 'function') {
          if (!el.checkVisibility({ checkVisibilityCSS: true })) return false;
        } else {
          const s = getComputedStyle(el);
          if (s.display === 'none' || s.visibility === 'hidden') return false;
        }
        if (el.closest('[hidden]')) return false;
        if (el.closest('[aria-hidden="true"]')) return false;
        return true;
      }
      return Array.from(document.querySelectorAll('h1,h2,h3,h4,h5,h6')).map((el) => ({
        level: Number(el.tagName[1]),
        testo: el.textContent.trim().slice(0, 80),
        esposto: esposto(el),
      }));
    });
    const headingsEsposti = headings.filter((h) => h.esposto);
    const h1Count = headingsEsposti.filter((h) => h.level === 1).length;
    const h1CountTotaleNelDom = headings.filter((h) => h.level === 1).length;
    let headingLevelSkipped = false;
    let prevLevel = 0;
    for (const h of headingsEsposti) {
      if (prevLevel !== 0 && h.level > prevLevel + 1) headingLevelSkipped = true;
      prevLevel = h.level;
    }

    // Tempo al primo render
    const paint = await page.evaluate(() => {
      const fcp = performance.getEntriesByType('paint').find((e) => e.name === 'first-contentful-paint');
      return { firstContentfulPaintMs: fcp ? Math.round(fcp.startTime) : null };
    });

    // Breakpoint: overflow orizzontale
    const breakpointResults = [];
    for (const width of BREAKPOINTS) {
      await page.setViewportSize({ width, height: REPORT_VIEWPORT.height });
      await page.waitForTimeout(150);
      const { scrollWidth, clientWidth } = await page.evaluate(() => ({
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
      }));
      breakpointResults.push({ width, scrollWidth, clientWidth, overflow: scrollWidth > clientWidth });
    }

    await page.close();
    await context.close();

    // Peso
    const totalBytes = requests.reduce((sum, r) => sum + r.bytes, 0);
    const imageBytes = requests.filter((r) => r.resourceType === 'image').reduce((sum, r) => sum + r.bytes, 0);
    const totalKb = Math.round(totalBytes / 1024);
    const imageKb = Math.round(imageBytes / 1024);
    const weightVerdict = budgetKb ? (totalKb <= budgetKb ? 'PASS' : 'FAIL') : 'N/D (nessun budget impostato)';

    const checks = {
      contrasto: contrastViolations.length === 0,
      breakpoint: breakpointResults.every((b) => !b.overflow),
      console: consoleErrors.length === 0 && pageErrors.length === 0 && failedRequests.length === 0,
      titoli: h1Count === 1 && !headingLevelSkipped,
      peso: budgetKb ? totalKb <= budgetKb : true,
    };
    const overall = Object.values(checks).every(Boolean) ? 'PASS' : 'FAIL';

    return {
      url: target,
      timestamp: new Date().toISOString(),
      verdetto: overall,
      checks,
      dettagli: {
        contrasto: {
          esito: checks.contrasto ? 'PASS' : 'FAIL',
          violazioniPerGravita: violationsBySeverity,
          violazioniContrasto: contrastViolations,
          tutteLeViolazioni: violationDetails,
        },
        peso: {
          esito: weightVerdict,
          byteTotali: totalBytes,
          kbTotali: totalKb,
          numeroRichieste: requests.length,
          byteImmagini: imageBytes,
          kbImmagini: imageKb,
          budgetKb: budgetKb ?? null,
          tempoPrimoRenderMs: paint.firstContentfulPaintMs,
        },
        breakpoint: {
          esito: checks.breakpoint ? 'PASS' : 'FAIL',
          risultati: breakpointResults,
        },
        console: {
          esito: checks.console ? 'PASS' : 'FAIL',
          erroriConsole: consoleErrors,
          erroriPagina: pageErrors,
          risorseFallite: failedRequests,
        },
        titoli: {
          esito: checks.titoli ? 'PASS' : 'FAIL',
          numeroH1: h1Count,
          numeroH1TotaliNelDom: h1CountTotaleNelDom,
          nota:
            h1CountTotaleNelDom > h1Count
              ? `${h1CountTotaleNelDom - h1Count} h1 presenti nel DOM ma non esposti (display:none/visibility:hidden/[hidden]/aria-hidden) — non contano ai fini del pavimento, informativo.`
              : null,
          livelloSaltato: headingLevelSkipped,
          elenco: headings,
        },
      },
    };
  } finally {
    await browser.close();
  }
}

function stampaReport(report) {
  console.log(`\n=== PAVIMENTO: ${report.verdetto} — ${report.url} ===`);
  console.log(`Contrasto:   ${report.dettagli.contrasto.esito}  (violazioni contrasto: ${report.dettagli.contrasto.violazioniContrasto.length}, tutte le gravità: ${JSON.stringify(report.dettagli.contrasto.violazioniPerGravita)})`);
  console.log(`Peso:        ${report.dettagli.peso.esito}  (${report.dettagli.peso.kbTotali} KB totali, ${report.dettagli.peso.numeroRichieste} richieste, ${report.dettagli.peso.kbImmagini} KB immagini, primo render ${report.dettagli.peso.tempoPrimoRenderMs} ms)`);
  console.log(`Breakpoint:  ${report.dettagli.breakpoint.esito}  (${report.dettagli.breakpoint.risultati.filter((b) => b.overflow).length} overflow su ${report.dettagli.breakpoint.risultati.length} larghezze)`);
  console.log(`Console:     ${report.dettagli.console.esito}  (${report.dettagli.console.erroriConsole.length} errori console, ${report.dettagli.console.erroriPagina.length} errori pagina, ${report.dettagli.console.risorseFallite.length} risorse fallite)`);
  const notaTitoli = report.dettagli.titoli.nota ? ` — ${report.dettagli.titoli.nota}` : '';
  console.log(`Titoli:      ${report.dettagli.titoli.esito}  (h1 esposti: ${report.dettagli.titoli.numeroH1}, h1 nel DOM: ${report.dettagli.titoli.numeroH1TotaliNelDom}, livello saltato: ${report.dettagli.titoli.livelloSaltato})${notaTitoli}`);
}

async function main() {
  const { _: positional, domains, out, budgetKb } = parseArgs(process.argv.slice(2));
  const input = positional[0];
  if (!input) {
    console.error('Uso: node pavimento.mjs <url-o-file-html> [--domains=...] [--budget-kb=NNN] [--out=cartella]');
    process.exit(1);
  }

  const allowedDomains = domains ?? DEFAULT_DOMAINS;
  const outDir = out ?? defaultOutDir();

  const startTime = Date.now();
  const monitor = new MonitorRisorse();
  let report;
  try {
    report = await run(input, { allowedDomains, budgetKb });
  } finally {
    const { maxChromiumRssMiB, minAvailableMiB } = monitor.stop();
    const durataS = ((Date.now() - startTime) / 1000).toFixed(1);
    const csvPath = scriviLogRun(outDir, {
      timestamp: new Date().toISOString(),
      script: 'pavimento.mjs',
      target: input,
      rssChromiumMaxMib: maxChromiumRssMiB,
      ramAvailableMinMib: minAvailableMiB,
      pesoKb: report?.dettagli?.peso?.kbTotali ?? 'n.d.',
      esitoPavimento: report?.verdetto ?? 'n.a.',
      durataS,
    });
    console.log(`Log: ${csvPath}`);
  }

  stampaReport(report);

  const reportPath = path.join(outDir, `${slugFor(input)}_pavimento_${timestamp()}.json`);
  writeFileSync(reportPath, JSON.stringify(report, null, 2));
  console.log(`\nReport completo: ${reportPath}`);

  process.exit(report.verdetto === 'PASS' ? 0 : 1);
}

main().catch((err) => {
  console.error('Errore:', err.message);
  process.exit(1);
});
