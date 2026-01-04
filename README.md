# HTML-CARTO (cadastre + capture)

Petite web-app Node/Express + Leaflet pour afficher le cadastre (fond OSM + WMS cadastre) et déclencher une capture PNG via Playwright. L’ancien backend FastAPI (`main.py`) est conservé, mais l’application web tourne maintenant sur `server.js`.

## Fonctionnalités
- Recherche d’adresse (api-adresse.data.gouv.fr) → géocodage → recentrage de la carte.
- Carte Leaflet avec fond OSM + surcouche WMS cadastre (GeoPlateforme, public).
- Capture Playwright : ouvre la page en headless avec les coords, attend le chargement des tuiles, et renvoie un PNG du rendu carte.
- Endpoints backend :
  - `GET /api/geocode?address=...` → lat/lon/label
  - `POST /api/capture` body `{ address }` → PNG (Content-Type image/png)

## Structure
```
server.js                # serveur Express (static + API + capture Playwright)
public/
  index.html
  app.js                 # logique front (Leaflet, appels API)
  styles.css
scripts/
  cadastre_capture.js    # wrapper : appelle /api/capture et sauvegarde le PNG
main.py                  # backend FastAPI existant (inchangé)
```

## Lancement local (Express + Playwright)
```bash
cd /Users/yohanaboujdid/Downloads/HTML-CARTO
npm install
npx playwright install chromium
npm run dev   # ou npm start
# Ouvre http://localhost:3000
```

## Utilisation front
1. Saisir l’adresse (ex: `14 rue Emile Nicol, Dozulé`).
2. Cliquer sur **Afficher** : la carte se centre, le marqueur est ajouté, la couche cadastre se charge.
3. Cliquer sur **Capturer** : le backend géocode, ouvre la page en headless, attend les tuiles, et renvoie un PNG téléchargé automatiquement.

## Script de capture en ligne de commande
Le script réutilise l’API locale `/api/capture`. Assure-toi que le serveur tourne (npm run dev) puis :
```bash
ADDRESS="14 rue Emile Nicol, Dozulé" OUTPUT="cadastre.png" node scripts/cadastre_capture.js
```
Options :
- `API_URL` pour cibler un autre hôte (ex: déploiement).

## Notes techniques
- WMS cadastre : `https://data.geopf.fr/wms-r` couche `CADASTRALPARCELS.PARCELLAIRE_EXPRESS` (sans clé, public).
- Capture : viewport par défaut 1400x900 (overrides via `CAPTURE_WIDTH/HEIGHT`). URL ouverte : `/?lat=...&lon=...&zoom=19&capture=1`.
- Front : `window.captureReadyDone` passe à `true` quand OSM + WMS + marqueur sont chargés, pour signaler au backend que la capture peut partir.

## Héritage FastAPI
`main.py` et les tests/lint Hardhat existants restent en place. Rien n’est supprimé pour éviter les régressions. Le serveur Express est autonome (port 3000 par défaut).
