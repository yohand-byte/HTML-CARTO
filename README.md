# 🏠 Cadastre Intelligent

Application web pour afficher les données cadastrales françaises complètes.

## ✅ Fonctionnalités

| Fonctionnalité | Status | API utilisée |
|---------------|--------|--------------|
| Autocomplete adresse | ✅ | api-adresse.data.gouv.fr |
| Géocodage | ✅ | api-adresse.data.gouv.fr |
| Parcelle cadastrale | ✅ | apicarto.ign.fr |
| Parcelles zone | ✅ | apicarto.ign.fr |
| Orthophoto | ✅ | data.geopf.fr (WMTS) |
| Carte Leaflet | ✅ | OSM + IGN |

## 🚀 Installation

```bash
pip install fastapi uvicorn httpx

cd cadastre-app
uvicorn main:app --host 0.0.0.0 --port 8000
```

Ouvrir http://localhost:8000

## 📡 Endpoints API

### Géocodage
```
GET /api/geocode?q=14 rue emile nicol dozule
GET /api/autocomplete?q=14 rue emile
```

### Cadastre
```
GET /api/cadastre/parcelle?lon=-0.045421&lat=49.232138
GET /api/cadastre/parcelles-zone?lon=-0.045421&lat=49.232138&radius=100
GET /api/cadastre/commune?code_insee=14229
```

### Orthophoto
```
GET /api/orthophoto?lon=-0.045421&lat=49.232138&zoom=17
GET /api/orthophoto/proxy?lon=-0.045421&lat=49.232138&zoom=17
```

### Status
```
GET /api/status
```

## 🔍 Exemple de réponse cadastre

Pour l'adresse **14 rue Émile Nicol, 14430 Dozulé**:

```json
{
  "success": true,
  "parcelle": {
    "idu": "14229000AE0061",
    "numero": "0061",
    "section": "AE",
    "contenance": 419,
    "code_insee": "14229",
    "nom_commune": "Dozulé"
  }
}
```

## 🗺️ Couches de carte disponibles

- OpenStreetMap (par défaut)
- Orthophoto IGN (vue aérienne)
- Plan IGN (carte topographique)

## 📦 Structure

```
cadastre-app/
├── main.py          # Backend FastAPI
├── static/
│   └── index.html   # Frontend (HTML/JS/CSS)
└── README.md

## 🚦 Lancement local rapide

```bash
pip install -r requirements.txt
uvicorn main:app --host 0.0.0.0 --port 8000
```

## ☁️ Déploiement gratuit (Render)

1. Pousser ce repo sur GitHub (déjà prêt).
2. Sur Render: «New Web Service» → connecter le repo → branch `main`.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`
5. Choisir le plan **Free**. Le `render.yaml` est fourni pour l’auto-détection.

## 🖼️ Capture du plan cadastral officiel (script Playwright, option manuelle)

Un script d’automatisation est fourni pour capturer un plan directement depuis cadastre.gouv.fr (rend à lancer en local, sans l’exposer en prod) :
```
cd HTML-CARTO
npm install playwright
ADDRESS="14 rue Emile Nicol, Dozulé" OUTPUT="cadastre.png" node scripts/cadastre_capture.js
```
Si le site change de structure, ajustez les sélecteurs dans `scripts/cadastre_capture.js` ou utilisez `npx playwright codegen https://www.cadastre.gouv.fr/scpc/rechercherPlan.do` pour régénérer les clics.
```
