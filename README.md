# HTML-CARTO (cadastre + carte)

Backend FastAPI qui sert l’UI Leaflet et expose les APIs cadastre. L’authentification BASIC a été retirée : aucun BASIC_USER/BASIC_PASS n’est requis.

## Fonctionnalités clés
- Autocomplétion et géocodage via API Adresse (`/api/autocomplete`, `/api/geocode`).
- Parcelles IGN : `/api/cadastre/parcelle` (point + ajout parcelles adjacentes si besoin) et `/api/cadastre/parcelles-zone` (zone circulaire).
- Orthophoto : génération d’URL WMTS et proxy (`/api/orthophoto`, `/api/orthophoto/proxy`).
- Statut des services : `/api/status`.
- Front Leaflet servi par FastAPI : `/` (UI complète) et `/static` (assets).
- Boutons d’échelle 1:1000 / 1:2000 / 1:5000 sur Carte et Cadastre avec barre 25 m / 50 m / 100 m.

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
- Patch anti-joints : overlap de tuiles Leaflet activé pour éviter le quadrillage.

## Détails des couches / emprises / échelles (actuel)
### Cadastre (UI principale)
- Fond principal : selon filtre actif (cadastre, planign, ortho).
- Overlays : parcelle sélectionnée (GeoJSON), marqueur, label numéro de parcelle, légende + échelle Leaflet.
- Emprise : centrée sur l’adresse sélectionnée (pas de bounds/rayon explicite).
- Échelle + zoom : 1:1 000 → zoom 19 (25 m), 1:2 000 → zoom 18 (50 m), 1:5 000 → zoom 17 (100 m).

### Carte interactive
- Fond principal : OSM (par défaut), bascule possible vers Orthophoto IGN, Plan IGN, Cadastre.
- Overlays : parcelle (feature group) + marqueur.
- Emprise : centre initial France, zoom 6; sur adresse → zoom 18.

### Orthophoto
- Fond principal : Orthophoto IGN.
- Overlays : marqueur.
- Emprise : centre initial France, zoom 6; sur adresse → zoom 18.

### Ancien front Express (public/)
- Fond principal : OSM.
- Overlay : Cadastre WMS.
- Emprise : centre initial France, zoom 6; sur adresse → zoom 19.

## Déploiement Render
`render.yaml` : build `pip install -r requirements.txt`, start `uvicorn main:app --host 0.0.0.0 --port $PORT`. Pousser `main.py` et `static/index.html` à jour avant de redeployer.
