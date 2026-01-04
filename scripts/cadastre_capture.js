/**
 * Capture d'un plan cadastral via cadastre.gouv.fr avec Playwright (ESM).
 * Usage (en local) :
 *   ADDRESS="14 rue Emile Nicol, Dozulé" OUTPUT="cadastre.png" node scripts/cadastre_capture.js
 *
 * Si le site change de structure, ajustez les sélecteurs ou régénérez avec :
 *   npx playwright codegen https://www.cadastre.gouv.fr/scpc/rechercherPlan.do
 */

import { chromium } from "playwright";

const ADDRESS = process.env.ADDRESS || "14 rue Emile Nicol, Dozulé";
const OUTPUT = process.env.OUTPUT || "cadastre.png";
const WAIT_MS = Number(process.env.WAIT_MS || 9000);

async function clickIfVisible(page, selector) {
  const el = await page.$(selector);
  if (el) {
    await el.click({ timeout: 1000 });
    return true;
  }
  return false;
}

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1700, height: 1200 } });

await page.goto("https://www.cadastre.gouv.fr/scpc/rechercherPlan.do", {
  waitUntil: "domcontentloaded",
});

// Consentement/cookies selon le bandeau affiché
await clickIfVisible(page, 'button:has-text("Accepter")');
await clickIfVisible(page, 'button:has-text("Tout accepter")');
await clickIfVisible(page, "text=Accepter");

// Champ de recherche principal (premier input texte)
const searchBox = await page.$('input[type="text"]');
if (!searchBox) {
  console.error("Champ de recherche introuvable, ajustez le sélecteur dans scripts/cadastre_capture.js");
  await browser.close();
  process.exit(1);
}
await searchBox.fill(ADDRESS);
await searchBox.press("Enter");

// Laisser le temps au site de charger la feuille/zoom
await page.waitForTimeout(WAIT_MS);

await page.screenshot({ path: OUTPUT, fullPage: true });
console.log(`Capture enregistrée dans ${OUTPUT}`);

await browser.close();
