import { chromium } from 'playwright';
const URL = process.argv[2];
const OUT = process.argv[3] || '/root/argo/.claude/skills/designer/output';
const CASI = [
  { w: 700, label: 'mobile-ok-700' },
  { w: 767, label: 'mobile-ultimo-ok-767' },
  { w: 768, label: 'DEAD-inizio-768' },
  { w: 820, label: 'DEAD-820' },
  { w: 860, label: 'DEAD-ultimo-860' },
  { w: 861, label: 'desktop-primo-ok-861' },
  { w: 900, label: 'desktop-ok-900' },
];
const browser = await chromium.launch({ headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'] });
const page = await browser.newPage();
await page.goto(URL, { waitUntil: 'load', timeout: 30000 });
for (const c of CASI) {
  await page.setViewportSize({ width: c.w, height: 1000 });
  await page.waitForTimeout(150);
  const path = `${OUT}/finestra-morta_${c.label}.png`;
  await page.screenshot({ path, clip: { x: 0, y: 0, width: c.w, height: 1000 } });
  console.log('Salvato:', path);
}
await browser.close();
