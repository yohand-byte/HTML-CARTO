# HTML-CARTO (cadastre + carte)

Backend FastAPI qui sert l’UI Leaflet et expose les APIs cadastre. L’authentification BASIC a été retirée : aucun BASIC_USER/BASIC_PASS n’est requis.

## Fonctionnalités clés
- Autocomplétion et géocodage via API Adresse (`/api/autocomplete`, `/api/geocode`).
- Parcelles IGN : `/api/cadastre/parcelle` (point) et `/api/cadastre/parcelles-zone` (zone circulaire).
- Orthophoto : génération d’URL WMTS et proxy (`/api/orthophoto`, `/api/orthophoto/proxy`).
- Statut des services : `/api/status`.
- Front Leaflet servi par FastAPI : `/` (UI complète) et `/static` (assets).

## Arborescence utile
```
main.py          # App FastAPI (serveur principal)
static/          # UI Leaflet utilisée en prod (Render)
public/          # Ancien front Express (non utilisé en prod)
scripts/         # Outils de capture / download cadastre (Node)
render.yaml      # Déploiement Render (uvicorn main:app)
```

## Lancement local (FastAPI)
```bash
cd /Users/yohanaboujdid/Downloads/HTML-CARTO
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
# UI : http://localhost:8000/  |  Santé : http://localhost:8000/api/status
```

## Points importants
- Pas d’auth BASIC : aucune variable BASIC_USER/BASIC_PASS n’est lue.
- CORS ouvert (origines *) pour faciliter les tests.
- WMS cadastre : `https://data.geopf.fr/wms-r` couche `CADASTRALPARCELS.PARCELLAIRE_EXPRESS` (publique).

## Déploiement Render
`render.yaml` : build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Pousser `main.py` et `static/index.html` à jour avant de redeployer.
