"""
Cadastre Intelligent - Backend FastAPI
Récupère les données cadastrales françaises via API Carto et Géoplateforme
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
import httpx
import json

app = FastAPI(title="Cadastre Intelligent", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ============================================================
# API ADRESSE - Géocodage et Autocomplete
# ============================================================

@app.get("/api/autocomplete")
async def autocomplete(q: str = Query(..., min_length=3)):
    """Autocomplete d'adresses via API Adresse data.gouv.fr"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api-adresse.data.gouv.fr/search/",
                params={"q": q, "limit": 10, "autocomplete": 1}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"API Adresse error: {str(e)}")


@app.get("/api/geocode")
async def geocode(q: str = Query(..., min_length=3)):
    """Géocodage complet d'une adresse"""
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            resp = await client.get(
                "https://api-adresse.data.gouv.fr/search/",
                params={"q": q, "limit": 1}
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("features"):
                raise HTTPException(status_code=404, detail="Adresse non trouvée")
            
            feature = data["features"][0]
            props = feature["properties"]
            coords = feature["geometry"]["coordinates"]
            
            return {
                "success": True,
                "address": {
                    "label": props.get("label"),
                    "housenumber": props.get("housenumber"),
                    "street": props.get("street"),
                    "postcode": props.get("postcode"),
                    "city": props.get("city"),
                    "context": props.get("context"),
                },
                "location": {
                    "lon": coords[0],
                    "lat": coords[1],
                    "x": props.get("x"),  # Lambert 93
                    "y": props.get("y"),
                },
                "insee": {
                    "code": props.get("citycode"),
                    "city": props.get("city"),
                },
                "score": props.get("score"),
                "type": props.get("type"),
            }
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"API Adresse error: {str(e)}")


# ============================================================
# API CARTO - Cadastre (Parcelles)
# ============================================================

@app.get("/api/cadastre/parcelle")
async def get_parcelle_at_point(lon: float, lat: float):
    """
    Récupère la parcelle cadastrale sous un point GPS
    Utilise API Carto avec paramètre geom=Point
    """
    geom = json.dumps({
        "type": "Point",
        "coordinates": [lon, lat]
    })
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/parcelle",
                params={"geom": geom}
            )
            resp.raise_for_status()
            data = resp.json()
            
            if not data.get("features"):
                return {"success": False, "message": "Aucune parcelle trouvée à ces coordonnées"}
            
            parcelle = data["features"][0]
            props = parcelle["properties"]
            
            return {
                "success": True,
                "parcelle": {
                    "idu": props.get("idu"),
                    "numero": props.get("numero"),
                    "section": props.get("section"),
                    "feuille": props.get("feuille"),
                    "contenance": props.get("contenance"),  # en m²
                    "code_insee": props.get("code_insee"),
                    "nom_commune": props.get("nom_com"),
                    "code_departement": props.get("code_dep"),
                },
                "geometry": parcelle["geometry"],
                "bbox": parcelle.get("bbox"),
                "geojson": data,
            }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"API Carto error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/api/cadastre/parcelles-zone")
async def get_parcelles_around(lon: float, lat: float, radius: float = 100):
    """
    Récupère les parcelles dans un rayon autour d'un point
    Crée un cercle approximatif (polygon) pour la recherche
    """
    import math
    
    # Créer un cercle approximatif (32 points)
    points = []
    for i in range(32):
        angle = (i / 32) * 2 * math.pi
        # Approximation: 1 degré ≈ 111km en latitude, variable en longitude
        dx = (radius / 111000) * math.cos(angle) / math.cos(math.radians(lat))
        dy = (radius / 111000) * math.sin(angle)
        points.append([lon + dx, lat + dy])
    points.append(points[0])  # Fermer le polygone
    
    geom = json.dumps({
        "type": "Polygon",
        "coordinates": [points]
    })
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/parcelle",
                params={"geom": geom}
            )
            resp.raise_for_status()
            data = resp.json()
            
            parcelles = []
            for f in data.get("features", []):
                props = f["properties"]
                parcelles.append({
                    "idu": props.get("idu"),
                    "numero": props.get("numero"),
                    "section": props.get("section"),
                    "contenance": props.get("contenance"),
                    "geometry": f["geometry"],
                })
            
            return {
                "success": True,
                "count": len(parcelles),
                "radius_m": radius,
                "center": [lon, lat],
                "parcelles": parcelles,
                "geojson": data,  # GeoJSON complet pour Leaflet
            }
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"API Carto error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error: {str(e)}")


@app.get("/api/cadastre/commune")
async def get_commune_boundary(code_insee: str):
    """Récupère les limites de la commune"""
    async with httpx.AsyncClient(timeout=15.0) as client:
        try:
            resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/commune",
                params={"code_insee": code_insee}
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"API Carto error: {str(e)}")


# ============================================================
# ORTHOPHOTO - WMTS Géoplateforme
# ============================================================

@app.get("/api/orthophoto")
async def get_orthophoto_url(
    lon: float,
    lat: float,
    zoom: int = 17
):
    """
    Génère l'URL de la tuile WMTS pour l'orthophoto
    Retourne aussi l'URL template pour Leaflet
    """
    import math
    
    # Conversion lat/lon -> tile x,y
    n = 2 ** zoom
    tile_x = int((lon + 180) / 360 * n)
    tile_y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    
    # URL de la tuile spécifique
    tile_url = f"https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={zoom}&TILEROW={tile_y}&TILECOL={tile_x}"
    
    # URL template pour Leaflet
    leaflet_url = "https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={z}&TILEROW={y}&TILECOL={x}"
    
    return {
        "success": True,
        "tile_url": tile_url,
        "leaflet_url": leaflet_url,
        "tile": {"x": tile_x, "y": tile_y, "z": zoom},
        "center": {"lon": lon, "lat": lat},
        "layer": "ORTHOIMAGERY.ORTHOPHOTOS",
    }


@app.get("/api/orthophoto/proxy")
async def proxy_orthophoto(lon: float, lat: float, zoom: int = 17):
    """Proxy pour récupérer la tuile directement (évite CORS)"""
    import math
    
    n = 2 ** zoom
    tile_x = int((lon + 180) / 360 * n)
    tile_y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    
    tile_url = f"https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={zoom}&TILEROW={tile_y}&TILECOL={tile_x}"
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            resp = await client.get(tile_url)
            resp.raise_for_status()
            return Response(
                content=resp.content,
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=86400"}
            )
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"WMTS error: {str(e)}")


# ============================================================
# STATUS - Vérification des APIs
# ============================================================

@app.get("/api/status")
async def check_apis_status():
    """Vérifie la disponibilité de toutes les APIs"""
    results = {}
    
    async with httpx.AsyncClient(timeout=5.0) as client:
        # Test API Adresse
        try:
            resp = await client.get(
                "https://api-adresse.data.gouv.fr/search/",
                params={"q": "paris", "limit": 1}
            )
            results["api_adresse"] = {
                "status": "ok" if resp.status_code == 200 else "error",
                "code": resp.status_code
            }
        except Exception as e:
            results["api_adresse"] = {"status": "error", "message": str(e)}
        
        # Test API Carto
        try:
            resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/commune",
                params={"code_insee": "75056"}
            )
            results["api_carto"] = {
                "status": "ok" if resp.status_code == 200 else "error",
                "code": resp.status_code
            }
        except Exception as e:
            results["api_carto"] = {"status": "error", "message": str(e)}
        
        # Test WMTS Orthophoto
        try:
            resp = await client.get(
                "https://data.geopf.fr/wmts",
                params={
                    "SERVICE": "WMTS",
                    "REQUEST": "GetTile",
                    "VERSION": "1.0.0",
                    "LAYER": "ORTHOIMAGERY.ORTHOPHOTOS",
                    "STYLE": "normal",
                    "FORMAT": "image/jpeg",
                    "TILEMATRIXSET": "PM",
                    "TILEMATRIX": "10",
                    "TILEROW": "384",
                    "TILECOL": "527"
                }
            )
            is_image = resp.headers.get("content-type", "").startswith("image/")
            results["wmts_orthophoto"] = {
                "status": "ok" if is_image else "error",
                "code": resp.status_code,
            }
        except Exception as e:
            results["wmts_orthophoto"] = {"status": "error", "message": str(e)}
    
    all_ok = all(r.get("status") == "ok" for r in results.values())
    
    return {
        "success": all_ok,
        "apis": results,
        "message": "Toutes les APIs sont opérationnelles" if all_ok else "Certaines APIs sont en erreur"
    }


# ============================================================
# FRONTEND - Servir l'interface HTML
# ============================================================

@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Sert l'interface utilisateur"""
    with open("static/index.html", "r", encoding="utf-8") as f:
        return f.read()


# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
