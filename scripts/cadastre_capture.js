/**
 * Wrapper pour appeler l'API locale /api/capture et enregistrer le PNG.
 * Laisse le serveur Express tourner (npm run dev), puis lance :
 *   ADDRESS="14 rue Emile Nicol, Dozulé" OUTPUT="cadastre.png" node scripts/cadastre_capture.js
 * Option : API_URL pour cibler un autre hôte (ex: déploiement).
 */

const fs = require("fs");
const path = require("path");

const ADDRESS = process.env.ADDRESS || "14 rue Emile Nicol, Dozulé";
const OUTPUT = path.resolve(process.env.OUTPUT || "cadastre.png");
const API_URL = process.env.API_URL || "http://localhost:3000/api/capture";

async function main() {
  const resp = await fetch(API_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ address: ADDRESS }),
  });
  if (!resp.ok) {
    const txt = await resp.text();
    throw new Error(`Capture API error (${resp.status}): ${txt}`);
  }
  const arrayBuffer = await resp.arrayBuffer();
  fs.writeFileSync(OUTPUT, Buffer.from(arrayBuffer));
  console.log(`Capture sauvegardée -> ${OUTPUT}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
