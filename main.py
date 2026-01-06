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
from shapely.geometry import shape

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

    def extract_parcelles(features):
        parcelles = []
        for feature in features:
            props = feature.get("properties", {})
            parcelles.append({
                "idu": props.get("idu"),
                "numero": props.get("numero"),
                "section": props.get("section"),
                "feuille": props.get("feuille"),
                "contenance": props.get("contenance"),
                "code_insee": props.get("code_insee"),
                "nom_commune": props.get("nom_com"),
                "code_departement": props.get("code_dep"),
            })
        return parcelles

    def build_parcel_shapes(features):
        shapes = []
        for feature in features:
            try:
                geom = feature.get("geometry")
                if not geom:
                    continue
                poly = shape(geom)
                if poly.is_empty:
                    continue
                shapes.append((feature, poly))
            except Exception:
                continue
        return shapes

    def compute_bounds(parcel_shapes):
        if not parcel_shapes:
            return None
        minx = min(poly.bounds[0] for _, poly in parcel_shapes)
        miny = min(poly.bounds[1] for _, poly in parcel_shapes)
        maxx = max(poly.bounds[2] for _, poly in parcel_shapes)
        maxy = max(poly.bounds[3] for _, poly in parcel_shapes)
        return (miny, minx, maxy, maxx)

    async def fetch_buildings(bbox):
        if not bbox:
            return []
        south, west, north, east = bbox
        query = (
            "[out:json][timeout:25];"
            f"(way['building']({south},{west},{north},{east}););"
            "out body;>;out skel qt;"
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                resp = await client.post(
                    "https://overpass-api.de/api/interpreter",
                    data=query,
                    headers={"Content-Type": "application/x-www-form-urlencoded"}
                )
                resp.raise_for_status()
                data = resp.json()
        except Exception:
            return []

        nodes = {}
        ways = []
        for element in data.get("elements", []):
            if element.get("type") == "node":
                nodes[element["id"]] = (element["lon"], element["lat"])
            elif element.get("type") == "way":
                ways.append(element)

        buildings = []
        for way in ways:
            coords = []
            for node_id in way.get("nodes", []):
                node = nodes.get(node_id)
                if node:
                    coords.append([node[0], node[1]])
            if len(coords) < 4:
                continue
            if coords[0] != coords[-1]:
                coords.append(coords[0])
            feature = {
                "type": "Feature",
                "properties": {
                    "id": way.get("id"),
                    "source": "osm"
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [coords]
                }
            }
            buildings.append(feature)
        return buildings

    def filter_buildings(buildings, parcel_shapes):
        filtered = []
        intersected_parcels = set()
        for building in buildings:
            try:
                poly = shape(building.get("geometry"))
            except Exception:
                continue
            if poly.is_empty:
                continue
            intersects = False
            for feature, parcel_poly in parcel_shapes:
                if poly.intersects(parcel_poly):
                    intersects = True
                    props = feature.get("properties", {})
                    if props.get("idu"):
                        intersected_parcels.add(props["idu"])
            if intersects:
                filtered.append(building)
        return filtered, intersected_parcels

    def select_parcel_id(intersected_parcels, parcel_shapes):
        if len(intersected_parcels) == 1:
            return next(iter(intersected_parcels))
        point = shape({"type": "Point", "coordinates": [lon, lat]})
        candidates = parcel_shapes
        if intersected_parcels:
            candidates = [
                (feature, poly)
                for feature, poly in parcel_shapes
                if feature.get("properties", {}).get("idu") in intersected_parcels
            ]
        if not candidates:
            return None
        closest = min(candidates, key=lambda item: item[1].centroid.distance(point))
        return closest[0].get("properties", {}).get("idu")
    
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
                try:
                    zone_geom = json.dumps(make_circle_polygon(15))
                    zone_resp = await client.get(
                        "https://apicarto.ign.fr/api/cadastre/parcelle",
                        params={"geom": zone_geom}
                    )
                    zone_resp.raise_for_status()
                    zone_data = zone_resp.json()
                    features = zone_data.get("features") or []
                    data = zone_data if features else data
                except httpx.HTTPError:
                    pass
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

            parcel_shapes = build_parcel_shapes(features)
            bounds = compute_bounds(parcel_shapes)
            buildings = await fetch_buildings(bounds)
            buildings, intersected_parcels = filter_buildings(buildings, parcel_shapes)

            parcelles = extract_parcelles(features)
            parcelles_geojson = {"type": "FeatureCollection", "features": features}

            parcel_count = len(features)
            building_count = len(buildings)
            if building_count == 1 and len(intersected_parcels) == 1:
                mode = "SINGLE_CONFIRMED"
            elif parcel_count > 1 or building_count > 1 or len(intersected_parcels) > 1:
                mode = "MULTI_PARCEL"
            else:
                mode = "UNCERTAIN"
            selected_parcel_id = select_parcel_id(intersected_parcels, parcel_shapes) or props.get("idu")
            
            return {
                "success": True,
                "mode": mode,
                "selectedParcelId": selected_parcel_id,
                "parcelles": parcelles,
                "parcellesGeojson": parcelles_geojson,
                "buildings": buildings,
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
