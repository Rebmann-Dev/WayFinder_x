const app = {
  config: {
    base: "http://localhost:8000",
    endpoints: {
      echo: "/api/v1/coordinates/echo",
      predict: "/api/v1/predict",
    },
    map: {
      center: [20, 0],
      zoom: 2,
      minZoom: 2,
      maxZoom: 18,
    },
    nominatim: "https://nominatim.openstreetmap.org",
    debugEchoApi: false,
  },

  state: {
    lat: null,
    lon: null,
    place_name: null,
    country: null,
    country_code: null,
    state_region: null,
    county: null,
    city: null,
    postcode: null,
    location_source: null,
    marker: null,
    searchTimeout: null,
  },

  el: {},
  map: null,
  isStreamlitComponent: false,

  init() {
    this.detectStreamlit();
    this.bindStreamlitHelpers();

    this.el = {
      coordsEmpty: document.getElementById("coords-empty"),
      coordsData: document.getElementById("coords-data"),
      actionGroup: document.getElementById("action-group"),
      displayLat: document.getElementById("display-lat"),
      displayLon: document.getElementById("display-lon"),
      displayPlace: document.getElementById("display-place"),
      displayCountry: document.getElementById("display-country"),
      displayCountryCode: document.getElementById("display-country-code"),
      displayState: document.getElementById("display-state"),
      displayCounty: document.getElementById("display-county"),
      displayCity: document.getElementById("display-city"),
      displayPostcode: document.getElementById("display-postcode"),
      displaySource: document.getElementById("display-source"),
      placeRow: document.getElementById("place-row"),
      countryRow: document.getElementById("country-row"),
      countryCodeRow: document.getElementById("country-code-row"),
      stateRow: document.getElementById("state-row"),
      countyRow: document.getElementById("county-row"),
      cityRow: document.getElementById("city-row"),
      postcodeRow: document.getElementById("postcode-row"),
      sourceRow: document.getElementById("source-row"),
      btnConfirm: document.getElementById("btn-confirm"),
      btnClear: document.getElementById("btn-clear"),
      responseSection: document.getElementById("response-section"),
      responseLoading: document.getElementById("response-loading"),
      responsePre: document.getElementById("response-pre"),
      searchInput: document.getElementById("place-search"),
      searchResults: document.getElementById("search-results"),
      mapHint: document.getElementById("map-hint"),
      root: document.getElementById("location-picker-root"),
    };

    this.initMap();
    this.bindEvents();
    this.setStreamlitReady();
    this.setStreamlitFrameHeight();
  },

  detectStreamlit() {
    this.isStreamlitComponent =
      window.parent &&
      window.parent !== window &&
      typeof window.parent.postMessage === "function";

    window.__WAYFINDER_STREAMLIT__ = this.isStreamlitComponent;
  },

  bindStreamlitHelpers() {
    window.setStreamlitFrameHeight = () => this.setStreamlitFrameHeight();
  },

  postStreamlitMessage(type, payload = {}) {
    if (!this.isStreamlitComponent) return;

    window.parent.postMessage(
      {
        isStreamlitMessage: true,
        type,
        ...payload,
      },
      "*"
    );
  },

  setStreamlitReady() {
    this.postStreamlitMessage("streamlit:componentReady", {
      apiVersion: 1,
    });
  },

  setStreamlitFrameHeight(height = null) {
    const nextHeight =
      height ||
      Math.max(
        document.body.scrollHeight,
        document.documentElement.scrollHeight,
        720
      );

    this.postStreamlitMessage("streamlit:setFrameHeight", {
      height: nextHeight,
    });
  },

  sendValueToStreamlit(value) {
    this.postStreamlitMessage("streamlit:setComponentValue", {
      value,
    });
  },

  initMap() {
    this.map = L.map("map", {
      center: this.config.map.center,
      zoom: this.config.map.zoom,
      minZoom: this.config.map.minZoom,
      zoomControl: true,
      worldCopyJump: false,
    });

    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: this.config.map.maxZoom,
      attribution:
        '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a> contributors',
      noWrap: false,
    }).addTo(this.map);

    this.map.on("click", (e) => this.handleMapClick(e.latlng));
    this.map.on("zoomend moveend resize", () => this.setStreamlitFrameHeight());
  },

  normalizeLon(lon) {
    return ((((lon + 180) % 360) + 360) % 360) - 180;
  },

  buildLocationDetails(data = {}, fallbackSource = null) {
    const address = data.address || {};

    const city =
      address.city ||
      address.town ||
      address.village ||
      address.municipality ||
      address.hamlet ||
      address.locality ||
      null;

    return {
      place_name: data.display_name || null,
      country: address.country || null,
      country_code: address.country_code
        ? String(address.country_code).toUpperCase()
        : null,
      state_region: address.state || address.region || address.province || null,
      county: address.county || address.state_district || address.district || null,
      city,
      postcode: address.postcode || null,
      location_source: fallbackSource,
    };
  },

  buildPayload() {
    return {
      lat: this.state.lat,
      lon: this.state.lon,
      place_name: this.state.place_name,
      country: this.state.country,
      country_code: this.state.country_code,
      state_region: this.state.state_region,
      county: this.state.county,
      city: this.state.city,
      postcode: this.state.postcode,
      location_source: this.state.location_source,
    };
  },

  handleMapClick({ lat, lng }) {
    const wrapped = L.latLng(lat, lng).wrap();
    const normalizedLon = this.normalizeLon(wrapped.lng);

    this.updateState({
      lat: wrapped.lat,
      lon: normalizedLon,
      place_name: null,
      country: null,
      country_code: null,
      state_region: null,
      county: null,
      city: null,
      postcode: null,
      location_source: "map_click",
    });

    this.placeMarker(wrapped.lat, normalizedLon);
    this.fadeHint();
  },

  placeMarker(lat, lon) {
    if (this.state.marker) this.state.marker.remove();

    const icon = L.divIcon({
      html: `<svg width="28" height="36" viewBox="0 0 28 36" fill="none" xmlns="http://www.w3.org/2000/svg">
        <path d="M14 0C6.27 0 0 6.27 0 14c0 9.8 14 22 14 22S28 23.8 28 14C28 6.27 21.73 0 14 0z" fill="var(--color-primary)"/>
        <circle cx="14" cy="14" r="5" fill="white" opacity="0.9"/>
      </svg>`,
      className: "",
      iconSize: [28, 36],
      iconAnchor: [14, 36],
      popupAnchor: [0, -36],
    });

    this.state.marker = L.marker([lat, lon], { icon }).addTo(this.map);
    this.state.marker.bindPopup(
      `<b style="font-variant-numeric:tabular-nums">${lat.toFixed(5)}, ${lon.toFixed(5)}</b>`
    ).openPopup();

    this.reverseGeocode(lat, lon);
  },

  updateState(next) {
    this.state.lat = next.lat;
    this.state.lon = this.normalizeLon(next.lon);
    this.state.place_name = next.place_name ?? null;
    this.state.country = next.country ?? null;
    this.state.country_code = next.country_code ?? null;
    this.state.state_region = next.state_region ?? null;
    this.state.county = next.county ?? null;
    this.state.city = next.city ?? null;
    this.state.postcode = next.postcode ?? null;
    this.state.location_source = next.location_source ?? null;

    this.renderCoords();
    this.setStreamlitFrameHeight();
  },

  renderRow(rowEl, valueEl, value) {
    if (!rowEl || !valueEl) return;

    if (value) {
      valueEl.textContent = value;
      rowEl.style.display = "flex";
    } else {
      rowEl.style.display = "none";
    }
  },

  renderCoords() {
    if (this.state.lat === null || this.state.lon === null) return;

    this.el.displayLat.textContent = this.state.lat.toFixed(6);
    this.el.displayLon.textContent = this.state.lon.toFixed(6);
    this.el.coordsEmpty.classList.add("hidden");
    this.el.coordsData.classList.remove("hidden");
    this.el.actionGroup.style.display = "flex";

    this.renderRow(this.el.placeRow, this.el.displayPlace, this.state.place_name);
    this.renderRow(this.el.countryRow, this.el.displayCountry, this.state.country);
    this.renderRow(
      this.el.countryCodeRow,
      this.el.displayCountryCode,
      this.state.country_code
    );
    this.renderRow(this.el.stateRow, this.el.displayState, this.state.state_region);
    this.renderRow(this.el.countyRow, this.el.displayCounty, this.state.county);
    this.renderRow(this.el.cityRow, this.el.displayCity, this.state.city);
    this.renderRow(this.el.postcodeRow, this.el.displayPostcode, this.state.postcode);
    this.renderRow(this.el.sourceRow, this.el.displaySource, this.state.location_source);
  },

  clearState() {
    this.state.lat = null;
    this.state.lon = null;
    this.state.place_name = null;
    this.state.country = null;
    this.state.country_code = null;
    this.state.state_region = null;
    this.state.county = null;
    this.state.city = null;
    this.state.postcode = null;
    this.state.location_source = null;

    if (this.state.marker) {
      this.state.marker.remove();
      this.state.marker = null;
    }

    this.el.coordsEmpty.classList.remove("hidden");
    this.el.coordsData.classList.add("hidden");
    this.el.actionGroup.style.display = "none";
    this.el.responseSection.style.display = "none";
    this.el.responsePre.textContent = "";
    this.el.searchInput.value = "";
    this.el.mapHint.classList.remove("fade-out");
    this.el.mapHint.style.display = "block";
    this.hideSearchResults();

    this.sendValueToStreamlit(null);
    this.setStreamlitFrameHeight();
  },

  bindEvents() {
    this.el.btnConfirm.addEventListener("click", () => this.sendCoordinates());
    this.el.btnClear.addEventListener("click", () => this.clearState());

    this.el.searchInput.addEventListener("input", () => {
      clearTimeout(this.state.searchTimeout);

      const q = this.el.searchInput.value.trim();
      if (q.length < 3) {
        this.hideSearchResults();
        return;
      }

      this.state.searchTimeout = setTimeout(() => this.geocodeSearch(q), 400);
    });

    document.addEventListener("click", (e) => {
      if (
        !this.el.searchInput.contains(e.target) &&
        !this.el.searchResults.contains(e.target)
      ) {
        this.hideSearchResults();
      }
    });

    this.el.searchInput.addEventListener("keydown", (e) => {
      if (e.key === "Escape") this.hideSearchResults();
    });

    window.addEventListener("load", () => this.setStreamlitFrameHeight());
    window.addEventListener("resize", () => this.setStreamlitFrameHeight());
  },

  async geocodeSearch(query) {
    try {
      const url = `${this.config.nominatim}/search?format=json&addressdetails=1&q=${encodeURIComponent(query)}&limit=5`;
      const res = await fetch(url, { headers: { "Accept-Language": "en" } });
      const data = await res.json();
      this.renderSearchResults(data);
    } catch {
      this.hideSearchResults();
    }
  },

  renderSearchResults(results) {
    const ul = this.el.searchResults;
    ul.innerHTML = "";

    if (!results.length) {
      ul.hidden = true;
      return;
    }

    results.forEach((r) => {
      const li = document.createElement("li");
      li.setAttribute("role", "option");

      const name = document.createElement("div");
      name.className = "result-name";
      name.textContent = r.display_name.split(",")[0];

      const sub = document.createElement("div");
      sub.className = "result-sub";
      sub.textContent = r.display_name.split(",").slice(1, 3).join(",").trim();

      li.append(name, sub);

      li.addEventListener("click", () => {
        const lat = parseFloat(r.lat);
        const lon = this.normalizeLon(parseFloat(r.lon));
        const details = this.buildLocationDetails(r, "search");

        this.el.searchInput.value = r.display_name.split(",")[0];
        this.hideSearchResults();

        this.map.setView([lat, lon], 10, { animate: true });

        this.updateState({
          lat,
          lon,
          ...details,
        });

        this.placeMarker(lat, lon);
        this.fadeHint();
      });

      ul.appendChild(li);
    });

    ul.hidden = false;
    this.setStreamlitFrameHeight();
  },

  hideSearchResults() {
    this.el.searchResults.hidden = true;
    this.el.searchResults.innerHTML = "";
    this.setStreamlitFrameHeight();
  },

  async reverseGeocode(lat, lon) {
    try {
      const url = `${this.config.nominatim}/reverse?format=json&addressdetails=1&lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`;
      const res = await fetch(url, { headers: { "Accept-Language": "en" } });
      const data = await res.json();

      if (data && data.display_name) {
        const details = this.buildLocationDetails(
          data,
          this.state.location_source || "map_click"
        );

        this.updateState({
          lat,
          lon,
          ...details,
        });

        if (this.state.marker) {
          const title =
            this.state.city ||
            this.state.place_name?.split(",")[0] ||
            "Selected location";

          this.state.marker.setPopupContent(
            `<b>${title}</b><br><span style="font-variant-numeric:tabular-nums;color:var(--color-text-muted);font-size:0.85em">${lat.toFixed(5)}, ${lon.toFixed(5)}</span>`
          );
        }
      }
    } catch (err) {
      console.warn("Reverse geocode failed:", err);
    }
  },

  async sendCoordinates() {
    const payload = this.buildPayload();

    if (payload.lat === null || payload.lon === null) return;

    this.sendValueToStreamlit(payload);

    if (!this.config.debugEchoApi) return;

    this.el.responseSection.style.display = "block";
    this.el.responseLoading.classList.remove("hidden");
    this.el.responsePre.textContent = "";

    try {
      const res = await fetch(`${this.config.base}${this.config.endpoints.echo}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });

      const data = await res.json();
      this.el.responseLoading.classList.add("hidden");
      this.el.responsePre.textContent = JSON.stringify(data, null, 2);
      this.setStreamlitFrameHeight();
    } catch (err) {
      this.el.responseLoading.classList.add("hidden");
      this.el.responsePre.textContent =
        `Error reaching API:\n${err.message}\n\nMake sure the FastAPI server is running at:\n${this.config.base}`;
      this.setStreamlitFrameHeight();
    }
  },

  fadeHint() {
    this.el.mapHint.classList.add("fade-out");
    setTimeout(() => {
      this.el.mapHint.style.display = "none";
      this.setStreamlitFrameHeight();
    }, 300);
  },
};

document.addEventListener("DOMContentLoaded", () => app.init());