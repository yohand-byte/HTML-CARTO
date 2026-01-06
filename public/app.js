(() => {
  const qs = new URLSearchParams(window.location.search);
  const captureMode = qs.get("capture") === "1";
  const initialLat = parseFloat(qs.get("lat"));
  const initialLon = parseFloat(qs.get("lon"));
  const initialZoom = parseInt(qs.get("zoom") || "18", 10);
  const initialAddress = qs.get("address") || "";

  if (captureMode) document.body.classList.add("capture-mode");

  const addressInput = document.getElementById("addressInput");
  const btnShow = document.getElementById("btnShow");
  const btnCapture = document.getElementById("btnCapture");
  const logBox = document.getElementById("log");

  if (initialAddress && addressInput) addressInput.value = initialAddress;

  const state = {
    map: null,
    marker: null,
    baseLoaded: false,
    cadLoaded: false,
    currentAddress: initialAddress,
  };

  window.captureReadyDone = false;

  function enableTileOverlap(pixels = 2) {
    if (!window.L || !L.GridLayer) return;
    const proto = L.GridLayer.prototype;
    if (proto._tileOverlapEnabled) return;
    const originalInitTile = proto._initTile;
    proto._initTile = function (tile) {
      originalInitTile.call(this, tile);
      const size = this.getTileSize();
      const overlap = pixels * 2;
      tile.style.width = `${size.x + overlap}px`;
      tile.style.height = `${size.y + overlap}px`;
      tile.style.marginLeft = `-${pixels}px`;
      tile.style.marginTop = `-${pixels}px`;
    };
    proto._tileOverlapEnabled = true;
  }

  function log(msg, type = "info") {
    if (!logBox) return;
    const div = document.createElement("div");
    div.className = `line ${type}`;
    div.textContent = msg;
    logBox.prepend(div);
  }

  function checkReady() {
    if (state.baseLoaded && state.cadLoaded && state.marker) {
      window.captureReadyDone = true;
    }
  }

  function setMarker(lat, lon) {
    if (!state.map) return;
    if (state.marker) state.map.removeLayer(state.marker);
    state.marker = L.marker([lat, lon]).addTo(state.map);
    checkReady();
  }

  function initMap() {
    enableTileOverlap(2);
    state.map = L.map("map").setView([46.6, 1.88], 6);

    const osm = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    });
    osm.on("load", () => {
      state.baseLoaded = true;
      checkReady();
    });
    osm.addTo(state.map);

    const cadastreWms = L.tileLayer.wms("https://data.geopf.fr/wms-r", {
      layers: "CADASTRALPARCELS.PARCELLAIRE_EXPRESS",
      format: "image/png",
      transparent: true,
      version: "1.3.0",
      attribution: "© IGN - Cadastre",
    });
    cadastreWms.on("load", () => {
      state.cadLoaded = true;
      checkReady();
    });
    cadastreWms.on("tileerror", (e) => log("Erreur WMS cadastre (tuile)", "err"));
    cadastreWms.addTo(state.map);

    L.control
      .layers(
        { OpenStreetMap: osm },
        { "Cadastre (WMS)": cadastreWms },
        { position: "topright" }
      )
      .addTo(state.map);

    if (!isNaN(initialLat) && !isNaN(initialLon)) {
      state.map.setView([initialLat, initialLon], initialZoom);
      setMarker(initialLat, initialLon);
      checkReady();
    }
  }

  async function geocode(address) {
    const resp = await fetch(`/api/geocode?address=${encodeURIComponent(address)}`);
    if (!resp.ok) {
      const data = await resp.json().catch(() => ({}));
      throw new Error(data.error || "Erreur géocodage");
    }
    const data = await resp.json();
    return data;
  }

  async function handleShow() {
    const address = (addressInput?.value || "").trim();
    if (!address) return log("Saisis une adresse.", "err");
    log(`Recherche: ${address}`, "info");
    try {
      const data = await geocode(address);
      state.currentAddress = data.label || address;
      state.map.setView([data.lat, data.lon], 19);
      setMarker(data.lat, data.lon);
      log(`Géocodé: ${data.label} (${data.lat.toFixed(5)}, ${data.lon.toFixed(5)})`, "ok");
    } catch (err) {
      log(err.message, "err");
    }
  }

  async function handleCapture() {
    const address = (addressInput?.value || "").trim() || state.currentAddress;
    if (!address) return log("Saisis une adresse avant de capturer.", "err");
    log(`Capture en cours pour ${address}...`, "info");
    btnCapture.disabled = true;
    try {
      const resp = await fetch("/api/capture", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ address }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || "Capture échouée");
      }
      const blob = await resp.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `capture-${Date.now()}.png`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      log("Capture téléchargée.", "ok");
    } catch (err) {
      log(err.message, "err");
    } finally {
      btnCapture.disabled = false;
    }
  }

  initMap();

  btnShow?.addEventListener("click", handleShow);
  btnCapture?.addEventListener("click", handleCapture);

  addressInput?.addEventListener("keyup", (e) => {
    if (e.key === "Enter") handleShow();
  });

  if (!isNaN(initialLat) && !isNaN(initialLon)) {
    log("Carte centrée via paramètres d'URL", "info");
  } else {
    log("Prêt. Saisis une adresse puis “Afficher”.", "info");
  }
})();
