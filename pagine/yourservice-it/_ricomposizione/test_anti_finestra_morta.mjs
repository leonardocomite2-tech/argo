// Test anti-finestra-morta per il fix h1 (cantiere Designer, passo 2 Fase B).
// Verifica che a ogni larghezza attorno alla soglia scelta (861px) sia
// visibile ESATTAMENTE una hero (.nt-p1-hero desktop o #ntHero mobile v3):
// mai zero, mai due. Non e' lo strumento pavimento.mjs (quello misura altro
// e usa solo 5 breakpoint fissi) - e' un controllo dedicato, ad-hoc, non
// un tool permanente della skill.
import { chromium } from 'playwright';

const LARGHEZZE = [820, 840, 855, 859, 860, 861, 865, 880, 900];
const FILE = 'file:///root/argo/pagine/yourservice-it/_ricomposizione/ricomposizione.html';

function isVisible(box) {
  return box !== null && box.width > 0 && box.height > 0;
}

const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage();
await page.goto(FILE, { waitUntil: 'load', timeout: 30000 });

let problemi = 0;
console.log('larghezza | .nt-p1-hero (desktop) | #ntHero (mobile v3) | esito');
for (const w of LARGHEZZE) {
  await page.setViewportSize({ width: w, height: 900 });
  await page.waitForTimeout(150);
  const desktopBox = await page.locator('.nt-p1-hero').boundingBox().catch(() => null);
  const mobileBox = await page.locator('#ntHero').boundingBox().catch(() => null);
  const dVis = isVisible(desktopBox);
  const mVis = isVisible(mobileBox);
  const nVisibili = (dVis ? 1 : 0) + (mVis ? 1 : 0);
  const esito = nVisibili === 1 ? 'OK' : (nVisibili === 0 ? 'FINESTRA MORTA (zero hero)' : 'DOPPIA (due hero)');
  if (nVisibili !== 1) problemi++;
  console.log(`${String(w).padStart(9)} | ${String(dVis).padStart(22)} | ${String(mVis).padStart(20)} | ${esito}`);
}

await browser.close();
if (problemi > 0) {
  console.log(`\nFALLITO: ${problemi} larghezze problematiche su ${LARGHEZZE.length}.`);
  process.exit(1);
} else {
  console.log(`\nOK: esattamente una hero visibile a tutte le ${LARGHEZZE.length} larghezze testate.`);
  process.exit(0);
}
