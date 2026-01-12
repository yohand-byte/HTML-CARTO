"""
Cadastre Intelligent - Backend FastAPI
Récupère les données cadastrales françaises via API Carto et Géoplateforme
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import httpx
import json
import io
import base64
import math

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

    def make_circle_polygon(radius: float):
        import math
        points = []
        for i in range(32):
            angle = (i / 32) * 2 * math.pi
            dx = (radius / 111000) * math.cos(angle) / math.cos(math.radians(lat))
            dy = (radius / 111000) * math.sin(angle)
            points.append([lon + dx, lat + dy])
        points.append(points[0])
        return {"type": "Polygon", "coordinates": [points]}

    def unique_features(features):
        seen = set()
        output = []
        for feature in features:
            props = feature.get("properties", {})
            idu = props.get("idu")
            key = idu or json.dumps(feature.get("geometry", {}), sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            output.append(feature)
        return output
    
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/parcelle",
                params={"geom": geom}
            )
            resp.raise_for_status()
            data = resp.json()
            
            features = data.get("features") or []
            if not features:
                return {"success": False, "message": "Aucune parcelle trouvée à ces coordonnées"}

            # Si une seule parcelle est trouvée, on élargit légèrement la recherche
            # pour capter les parcelles adjacentes quand un bâtiment chevauche 2 lots.
            if len(features) == 1:
                try:
                    zone_geom = json.dumps(make_circle_polygon(6))
                    zone_resp = await client.get(
                        "https://apicarto.ign.fr/api/cadastre/parcelle",
                        params={"geom": zone_geom}
                    )
                    zone_resp.raise_for_status()
                    zone_data = zone_resp.json()
                    zone_features = zone_data.get("features") or []
                    if zone_features:
                        features = unique_features(features + zone_features)
                        data["features"] = features
                except httpx.HTTPError:
                    pass

            parcelle = features[0]
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
# VALIDATION & RENDER - Endpoints pour DP Generator
# ============================================================

class LocationValidationRequest(BaseModel):
    lat: float
    lon: float
    address: Optional[str] = None

class MarkerConfig(BaseModel):
    lat: float
    lon: float
    type: str = "project"  # project, arrow, label

class RenderMapRequest(BaseModel):
    lat: float
    lon: float
    scale: str = "1:1000"  # 1:1000, 1:2000, 1:5000
    width: int = 800
    height: int = 600
    layers: List[str] = ["ortho", "cadastre"]
    parcelles: Optional[List[str]] = None
    markers: Optional[List[MarkerConfig]] = None
    show_scale_bar: bool = True
    show_compass: bool = True

# Scale to zoom level mapping for precise rendering
SCALE_ZOOM_MAP = {
    "1:500": 20,
    "1:1000": 19,
    "1:2000": 18,
    "1:5000": 17,
    "1:10000": 16,
    "1:25000": 15,
}

@app.post("/api/validate-location")
async def validate_location(request: LocationValidationRequest):
    """
    Valide et enrichit une localisation GPS.
    Retourne les coordonnées corrigées, les parcelles cadastrales,
    et les informations d'adresse.
    """
    lon, lat = request.lon, request.lat
    
    result = {
        "success": True,
        "original": {"lat": lat, "lon": lon},
        "validated": {"lat": lat, "lon": lon},
        "parcelles": [],
        "address": None,
        "suggestions": []
    }
    
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Reverse geocoding pour vérifier l'adresse
        try:
            reverse_resp = await client.get(
                "https://api-adresse.data.gouv.fr/reverse/",
                params={"lon": lon, "lat": lat}
            )
            if reverse_resp.status_code == 200:
                reverse_data = reverse_resp.json()
                if reverse_data.get("features"):
                    feature = reverse_data["features"][0]
                    props = feature["properties"]
                    result["address"] = {
                        "label": props.get("label"),
                        "city": props.get("city"),
                        "postcode": props.get("postcode"),
                        "street": props.get("street"),
                        "housenumber": props.get("housenumber"),
                        "score": props.get("score"),
                    }
                    # If original address provided, check distance
                    if request.address:
                        result["suggestions"].append({
                            "type": "address_match",
                            "message": f"Adresse trouvée: {props.get('label')}",
                            "score": props.get("score", 0)
                        })
        except Exception:
            pass
        
        # 2. Récupérer les parcelles cadastrales
        try:
            geom = json.dumps({"type": "Point", "coordinates": [lon, lat]})
            cadastre_resp = await client.get(
                "https://apicarto.ign.fr/api/cadastre/parcelle",
                params={"geom": geom}
            )
            if cadastre_resp.status_code == 200:
                cadastre_data = cadastre_resp.json()
                for f in cadastre_data.get("features", []):
                    props = f["properties"]
                    result["parcelles"].append({
                        "idu": props.get("idu"),
                        "numero": props.get("numero"),
                        "section": props.get("section"),
                        "contenance": props.get("contenance"),
                        "code_insee": props.get("code_insee"),
                        "geometry": f["geometry"]
                    })
                
                # Check for multi-parcelle situation
                if len(result["parcelles"]) > 1:
                    result["suggestions"].append({
                        "type": "multi_parcelle",
                        "message": f"Attention: {len(result['parcelles'])} parcelles détectées sous ce point",
                        "action": "Vérifiez que toutes les parcelles sont sélectionnées"
                    })
                elif len(result["parcelles"]) == 0:
                    result["suggestions"].append({
                        "type": "no_parcelle",
                        "message": "Aucune parcelle trouvée à ces coordonnées",
                        "action": "Déplacez le marqueur sur une parcelle valide"
                    })
        except Exception as e:
            result["suggestions"].append({
                "type": "error",
                "message": f"Erreur cadastre: {str(e)}"
            })
    
    return result


@app.post("/api/render-map")
async def render_map(request: RenderMapRequest):
    """
    Génère une image de carte à une échelle précise en assemblant plusieurs tuiles.
    """
    from PIL import Image
    
    zoom = SCALE_ZOOM_MAP.get(request.scale, 19)
    lat, lon = request.lat, request.lon
    
    # Taille de tuile standard
    TS = 256
    
    # 1. Calculer la position pixel centrale au zoom donné
    n = 2 ** zoom
    world_x = (lon + 180) / 360 * n * TS
    world_y = (1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n * TS
    
    # 2. Déterminer la plage de tuiles à récupérer
    # On veut couvrir width x height
    min_pw_x = world_x - request.width / 2
    max_pw_x = world_x + request.width / 2
    min_pw_y = world_y - request.height / 2
    max_pw_y = world_y + request.height / 2
    
    start_tile_x = int(min_pw_x // TS)
    end_tile_x = int(max_pw_x // TS)
    start_tile_y = int(min_pw_y // TS)
    end_tile_y = int(max_pw_y // TS)
    
    print(f"DEBUG: Rendering scale {request.scale} (zoom {zoom})")
    print(f"DEBUG: Tiles: X={start_tile_x}..{end_tile_x}, Y={start_tile_y}..{end_tile_y}")
    
    # 3. Récupérer les tuiles pour chaque couche
    final_img = Image.new("RGBA", (request.width, request.height), (255, 255, 255, 255))
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        for layer_name in request.layers:
            layer_canvas = Image.new("RGBA", (request.width, request.height), (0, 0, 0, 0))
            layer_found = False
            
            for ty in range(start_tile_y, end_tile_y + 1):
                for tx in range(start_tile_x, end_tile_x + 1):
                    # URL de la tuile
                    if layer_name == "ortho":
                        url = f"https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=ORTHOIMAGERY.ORTHOPHOTOS&STYLE=normal&FORMAT=image/jpeg&TILEMATRIXSET=PM&TILEMATRIX={zoom}&TILEROW={ty}&TILECOL={tx}"
                    elif layer_name == "plan":
                        url = f"https://data.geopf.fr/wmts?SERVICE=WMTS&REQUEST=GetTile&VERSION=1.0.0&LAYER=GEOGRAPHICALGRIDSYSTEMS.PLANIGNV2&STYLE=normal&FORMAT=image/png&TILEMATRIXSET=PM&TILEMATRIX={zoom}&TILEROW={ty}&TILECOL={tx}"
                    elif layer_name == "cadastre":
                        # Pour le cadastre en WMS, on calcule la bbox de la TUIILE précise
                        # Mais c'est plus simple de demander une seule grande image WMS à la fin
                        continue
                    else:
                        continue
                    
                    try:
                        resp = await client.get(url)
                        if resp.status_code == 200:
                            tile = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                            # Position de la tuile dans le canvas final
                            pos_x = int(tx * TS - min_pw_x)
                            pos_y = int(ty * TS - min_pw_y)
                            layer_canvas.paste(tile, (pos_x, pos_y))
                            layer_found = True
                    except Exception as e:
                        print(f"DEBUG: Failed to get tile {tx},{ty} for {layer_name}: {e}")
            
            # Cas spécial Cadastre (WMS sur toute la zone d'un coup)
            if layer_name == "cadastre":
                # Calculer la BBOX du canevas complet
                # Resolution at zoom level
                res = 156543.03392804062 / (2 ** zoom)
                
                # Center in 3857
                center_x = lon * 20037508.34 / 180
                center_y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
                center_y = center_y * 20037508.34 / 180
                
                # BBox based on width/height
                half_w_m = (request.width * res) / 2
                half_h_m = (request.height * res) / 2
                
                bbox = f"{center_x - half_w_m},{center_y - half_h_m},{center_x + half_w_m},{center_y + half_h_m}"
                url = f"https://data.geopf.fr/wms-r?SERVICE=WMS&VERSION=1.3.0&REQUEST=GetMap&LAYERS=CADASTRALPARCELS.PARCELLAIRE_EXPRESS&CRS=EPSG:3857&BBOX={bbox}&WIDTH={request.width}&HEIGHT={request.height}&FORMAT=image/png&TRANSPARENT=true"
                
                try:
                    resp = await client.get(url)
                    if resp.status_code == 200:
                        cad_img = Image.open(io.BytesIO(resp.content)).convert("RGBA")
                        layer_canvas.paste(cad_img, (0, 0))
                        layer_found = True
                except Exception as e:
                    print(f"DEBUG: Failed to get WMS cadastre: {e}")

            if layer_found:
                final_img = Image.alpha_composite(final_img, layer_canvas)

        # 4. Export base64
        buf = io.BytesIO()
        final_img.save(buf, format="PNG")
        b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
        
        return {
            "success": True,
            "image": f"data:image/png;base64,{b64}",
            "metadata": {
                "scale": request.scale,
                "zoom": zoom,
                "width": request.width,
                "height": request.height,
                "lat": lat,
                "lon": lon
            }
        }


def _get_bbox_3857(lat: float, lon: float, zoom: int, tile_size: int = 256) -> str:
    """Calculate bounding box in EPSG:3857 for WMS request"""
    # Convert to Web Mercator
    x = lon * 20037508.34 / 180
    y = math.log(math.tan((90 + lat) * math.pi / 360)) / (math.pi / 180)
    y = y * 20037508.34 / 180
    
    # Calculate tile extent at zoom level
    resolution = 156543.03392804062 / (2 ** zoom)
    half_size = tile_size * resolution / 2
    
    minx = x - half_size
    miny = y - half_size
    maxx = x + half_size
    maxy = y + half_size
    
    return f"{minx},{miny},{maxx},{maxy}"


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
