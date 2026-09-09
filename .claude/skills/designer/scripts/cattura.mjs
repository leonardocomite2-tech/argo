#!/usr/bin/env node
// Cattura screenshot full-page (mobile + desktop) e snapshot di accessibilità di una pagina.
// Uso: node cattura.mjs <url-o-file-html> [--domains=dominio1,dominio2] [--out=cartella]
import { chromium } from 'playwright';
import { writeFileSync } from 'node:fs';
import path from 'node:path';
import {
  NAV_TIMEOUT_MS,
  DEFAULT_DOMAINS,
  VIEWPORTS,
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

async function main() {
  const { _: positional, domains, out } = parseArgs(process.argv.slice(2));
  const input = positional[0];
  if (!input) {
    console.error('Uso: node cattura.mjs <url-o-file-html> [--domains=dominio1,dominio2] [--out=cartella]');
    process.exit(1);
  }

  const allowedDomains = domains ?? DEFAULT_DOMAINS;
  assertDomainAllowed(input, allowedDomains);

  const outDir = out ?? defaultOutDir();
  const target = resolveTarget(input);
  const slug = slugFor(input);
  const ts = timestamp();
  const produced = [];

  const startTime = Date.now();
  const monitor = new MonitorRisorse();
  let browser;
  try {
    browser = await chromium.launch({ headless: true, args: CHROMIUM_ARGS });
    try {
      for (const viewport of VIEWPORTS) {
        const page = await browser.newPage({ viewport: { width: viewport.width, height: viewport.height } });
        page.setDefaultNavigationTimeout(NAV_TIMEOUT_MS);
        page.setDefaultTimeout(NAV_TIMEOUT_MS);
        try {
          // 'load' invece di 'networkidle': siti reali con chat widget/tracker mantengono
          // connessioni aperte all'infinito, 'networkidle' andrebbe sempre in timeout.
          await page.goto(target, { waitUntil: 'load', timeout: NAV_TIMEOUT_MS });

          const screenshotPath = path.join(outDir, `${slug}_${viewport.name}_${ts}.png`);
          await page.screenshot({ path: screenshotPath, fullPage: true });
          produced.push(screenshotPath);

          if (viewport.name === 'mobile') {
            const ariaSnapshot = await page.locator('body').ariaSnapshot();
            const snapshotPath = path.join(outDir, `${slug}_a11y_${ts}.json`);
            writeFileSync(
              snapshotPath,
              JSON.stringify(
                { url: target, capturedAt: new Date().toISOString(), ariaSnapshot },
                null,
                2,
              ),
            );
            produced.push(snapshotPath);
          }
        } finally {
          await page.close();
        }
      }
    } finally {
      await browser.close();
    }
  } finally {
    const { maxChromiumRssMiB, minAvailableMiB } = monitor.stop();
    const durataS = ((Date.now() - startTime) / 1000).toFixed(1);
    const csvPath = scriviLogRun(outDir, {
      timestamp: new Date().toISOString(),
      script: 'cattura.mjs',
      target: input,
      rssChromiumMaxMib: maxChromiumRssMiB,
      ramAvailableMinMib: minAvailableMiB,
      pesoKb: 'n.d.',
      esitoPavimento: 'n.a.',
      durataS,
    });
    console.log(`Log: ${csvPath}`);
  }

  console.log('File prodotti:');
  for (const f of produced) console.log(' -', f);
}

main().catch((err) => {
  console.error('Errore:', err.message);
  process.exit(1);
});
