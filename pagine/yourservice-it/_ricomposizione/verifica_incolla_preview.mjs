// Verifica mirata: assenza CDN React/ReactDOM/Babel, assenza richiesta tweaks-panel.jsx,
// assenza crash useTweaks. Ad-hoc per la verifica del passo 1 (Fase C), non un tool permanente.
import { chromium } from 'playwright';

const URL = process.argv[2];
if (!URL) { console.error('Uso: node verifica_incolla.mjs <url>'); process.exit(1); }

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage();
const requests = [];
const pageErrors = [];
const consoleErrors = [];
page.on('request', (r) => requests.push(r.url()));
page.on('pageerror', (e) => pageErrors.push(e.message));
page.on('console', (m) => { if (m.type() === 'error') consoleErrors.push(m.text()); });

await page.goto(URL, { waitUntil: 'load', timeout: 30000 });

const cdnReact = requests.filter((u) => /unpkg\.com.*(react|react-dom|babel)/i.test(u));
const tweaksPanel = requests.filter((u) => /tweaks-panel\.jsx/i.test(u));
const useTweaksErr = [...pageErrors, ...consoleErrors].filter((e) => /useTweaks/i.test(e));
const heroRoot = await page.locator('#hero-root').count();
const tweaksRoot = await page.locator('#tweaks-root').count();

console.log('Richieste CDN React/ReactDOM/Babel (unpkg.com):', cdnReact.length);
cdnReact.forEach((u) => console.log('  -', u));
console.log('Richieste tweaks-panel.jsx:', tweaksPanel.length);
tweaksPanel.forEach((u) => console.log('  -', u));
console.log('Errori/console che citano useTweaks:', useTweaksErr.length);
useTweaksErr.forEach((e) => console.log('  -', e));
console.log('#hero-root presente nel DOM:', heroRoot > 0, `(count=${heroRoot})`);
console.log('#tweaks-root presente nel DOM:', tweaksRoot > 0, `(count=${tweaksRoot})`);

const problemi = cdnReact.length + tweaksPanel.length + useTweaksErr.length + heroRoot + tweaksRoot;
console.log(problemi === 0 ? '\nOK: nessun residuo del sistema React morto.' : '\nATTENZIONE: residui trovati, incolla probabilmente parziale.');

await browser.close();
process.exit(problemi === 0 ? 0 : 1);
