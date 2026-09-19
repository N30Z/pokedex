const API_BASE_URL = window.API_BASE_URL || "";
const PAGE_SIZE = 40;

const TYPE_NAMES_DE = {
  normal: "Normal",
  fighting: "Kampf",
  flying: "Flug",
  poison: "Gift",
  ground: "Boden",
  rock: "Gestein",
  bug: "Käfer",
  ghost: "Geist",
  steel: "Stahl",
  fire: "Feuer",
  water: "Wasser",
  grass: "Pflanze",
  electric: "Elektro",
  psychic: "Psycho",
  ice: "Eis",
  dragon: "Drache",
  dark: "Unlicht",
  fairy: "Fee",
  stellar: "Stellar",
  unknown: "Unbekannt",
};

function typeNameDe(type) {
  return TYPE_NAMES_DE[type.name] || type.name;
}

function typeNameDeBySlug(slug) {
  return TYPE_NAMES_DE[slug] || slug;
}

function formatSlug(name) {
  return name
    .split("-")
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

function genderRatioText(genderRate) {
  if (genderRate == null) return "Unbekannt";
  if (genderRate === -1) return "Geschlechtslos";

  const female = (genderRate / 8) * 100;
  const male = 100 - female;

  return `${male}% ♂ / ${female}% ♀`;
}

const EFFECTIVENESS_BUCKETS = [
  { multiplier: 4, label: "Sehr schwach gegen (4×)" },
  { multiplier: 2, label: "Schwach gegen (2×)" },
  { multiplier: 0.5, label: "Resistent gegen (0,5×)" },
  { multiplier: 0.25, label: "Sehr resistent gegen (0,25×)" },
  { multiplier: 0, label: "Immun gegen" },
];

function computeTypeEffectiveness(types) {
  const multiplier = {};

  Object.keys(TYPE_NAMES_DE).forEach((t) => {
    multiplier[t] = 1;
  });

  (types || []).forEach((t) => {
    (t.double_damage_from || []).forEach((opp) => {
      multiplier[opp] = (multiplier[opp] ?? 1) * 2;
    });
    (t.half_damage_from || []).forEach((opp) => {
      multiplier[opp] = (multiplier[opp] ?? 1) * 0.5;
    });
    (t.no_damage_from || []).forEach((opp) => {
      multiplier[opp] = 0;
    });
  });

  return multiplier;
}

function renderEffectivenessChart(types) {
  const multiplier = computeTypeEffectiveness(types);

  const sections = EFFECTIVENESS_BUCKETS.map(({ multiplier: m, label }) => {
    const matches = Object.entries(multiplier)
      .filter(([, value]) => value === m)
      .map(([type]) => `<span class="type-badge">${typeNameDeBySlug(type)}</span>`)
      .join("");

    if (!matches) return "";

    return `<div class="effectiveness-row"><span class="effectiveness-label">${label}</span><div class="type-badges">${matches}</div></div>`;
  }).join("");

  if (!sections) return "";

  return `<div class="detail-section"><h3>Typ-Effektivität</h3>${sections}</div>`;
}

function renderStatsChart(stats) {
  if (!stats || !stats.length) return "";

  const maxStat = 200;

  const rows = stats
    .map((s) => {
      const width = Math.min(100, ((s.value ?? 0) / maxStat) * 100);
      return `
        <div class="stat-bar-row">
          <span class="stat-bar-label">${s.name_de || formatSlug(s.name)}</span>
          <div class="stat-bar-track"><div class="stat-bar-fill" style="width:${width}%"></div></div>
          <span class="stat-bar-value">${s.value ?? "–"}</span>
        </div>
      `;
    })
    .join("");

  return `<div class="detail-section"><h3>Basiswerte</h3>${rows}</div>`;
}

function evolutionConditionText(edge) {
  const parts = [];

  if (edge.min_level) parts.push(`ab Level ${edge.min_level}`);
  if (edge.item) parts.push(formatSlug(edge.item));
  if (edge.min_happiness) parts.push(`Freundschaft ≥ ${edge.min_happiness}`);
  if (edge.trigger === "trade" && !edge.item) parts.push("durch Tausch");

  if (!parts.length && edge.trigger) parts.push(formatSlug(edge.trigger));

  return parts.join(", ");
}

function renderEvolutionEntry(edge) {
  const sprite = mediaUrl(edge.sprite);
  const clickable = edge.pokemon_id != null;

  return `
    <div class="evolution-entry${clickable ? " clickable" : ""}" ${clickable ? `data-pokemon-id="${edge.pokemon_id}"` : ""}>
      <img src="${sprite || ""}" alt="${edge.name || ""}" />
      <p class="evolution-name">${edge.german_name || edge.name || "?"}</p>
      <p class="evolution-condition">${evolutionConditionText(edge)}</p>
    </div>
  `;
}

function renderEvolutionSection(p) {
  const from = p.evolves_from || [];
  const to = p.evolves_to || [];

  if (!from.length && !to.length) return "";

  const fromHtml = from.map(renderEvolutionEntry).join("");
  const toHtml = to.map(renderEvolutionEntry).join("");

  return `
    <div class="detail-section">
      <h3>Entwicklung</h3>
      <div class="evolution-row">
        ${fromHtml}
        ${from.length && to.length ? '<span class="evolution-arrow">→</span>' : ""}
        ${toHtml}
      </div>
    </div>
  `;
}

const grid = document.getElementById("grid");
const statusEl = document.getElementById("status");
const searchInput = document.getElementById("search");
const loadMoreBtn = document.getElementById("load-more");
const modal = document.getElementById("modal");
const modalContent = document.getElementById("modal-content");
const modalClose = document.getElementById("modal-close");
const lightbox = document.getElementById("lightbox");
const lightboxImg = document.getElementById("lightbox-img");
const lightboxClose = document.getElementById("lightbox-close");
const typeFiltersEl = document.getElementById("type-filters");
const favoritesToggleBtn = document.getElementById("favorites-toggle");
const recentSection = document.getElementById("recent-section");
const recentRow = document.getElementById("recent-row");
const compareBar = document.getElementById("compare-bar");
const compareCount = document.getElementById("compare-count");
const compareOpenBtn = document.getElementById("compare-open");
const compareClearBtn = document.getElementById("compare-clear");
const compareModal = document.getElementById("compare-modal");
const compareContent = document.getElementById("compare-content");
const compareCloseBtn = document.getElementById("compare-close");

let currentSearch = "";
let currentOffset = 0;
let total = 0;
let requestToken = 0;
let activeTypes = new Set();
let favoritesOnly = false;
let compareIds = [];

// ---------------------------------------------------------
// Favorites (localStorage)
// ---------------------------------------------------------

const FAVORITES_KEY = "pokedex.favorites";
const RECENT_KEY = "pokedex.recent";
const RECENT_LIMIT = 12;

function loadFavorites() {
  try {
    const raw = localStorage.getItem(FAVORITES_KEY);
    return new Set(raw ? JSON.parse(raw) : []);
  } catch {
    return new Set();
  }
}

function saveFavorites() {
  try {
    localStorage.setItem(FAVORITES_KEY, JSON.stringify([...favorites]));
  } catch {}
}

const favorites = loadFavorites();

function isFavorite(id) {
  return favorites.has(Number(id));
}

function toggleFavorite(id) {
  id = Number(id);
  if (favorites.has(id)) favorites.delete(id);
  else favorites.add(id);
  saveFavorites();

  const active = favorites.has(id);
  document.querySelectorAll(`[data-favorite-id="${id}"]`).forEach((btn) => {
    btn.classList.toggle("active", active);
  });

  if (favoritesOnly) loadPage({ reset: true });
}

// ---------------------------------------------------------
// Recently viewed (localStorage)
// ---------------------------------------------------------

function loadRecent() {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveRecent(list) {
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(list));
  } catch {}
}

function recordRecentlyViewed(p) {
  let list = loadRecent().filter((item) => item.id !== p.id);
  list.unshift({
    id: p.id,
    name: p.name,
    german_name: p.german_name,
    sprite: p.sprite,
  });
  list = list.slice(0, RECENT_LIMIT);
  saveRecent(list);
  renderRecentRow(list);
}

function renderRecentRow(list) {
  list = list || loadRecent();
  recentSection.hidden = list.length === 0;
  recentRow.innerHTML = list
    .map((p) => {
      const sprite = mediaUrl(p.sprite);
      return `
        <div class="recent-item" data-pokemon-id="${p.id}">
          <img src="${sprite || ""}" alt="${p.name}" loading="lazy" />
          <span>${p.german_name || p.name}</span>
        </div>
      `;
    })
    .join("");
}

recentRow.addEventListener("click", (e) => {
  const item = e.target.closest("[data-pokemon-id]");
  if (item) openDetail(item.dataset.pokemonId);
});

// ---------------------------------------------------------
// Compare (in-memory, up to 2 Pokémon)
// ---------------------------------------------------------

function isCompareSelected(id) {
  return compareIds.includes(Number(id));
}

function toggleCompare(id) {
  id = Number(id);
  const idx = compareIds.indexOf(id);

  if (idx !== -1) {
    compareIds.splice(idx, 1);
  } else {
    if (compareIds.length >= 2) compareIds.shift();
    compareIds.push(id);
  }

  updateCompareUI();
}

function clearCompare() {
  compareIds = [];
  updateCompareUI();
}

function updateCompareUI() {
  document.querySelectorAll("[data-compare-id]").forEach((el) => {
    const id = Number(el.dataset.compareId);
    const selected = compareIds.includes(id);
    if (el.matches("input")) el.checked = selected;
    else el.classList.toggle("active", selected);
  });

  document.querySelectorAll(".card").forEach((card) => {
    card.classList.toggle("compare-selected", compareIds.includes(Number(card.dataset.pokemonId)));
  });

  compareBar.hidden = compareIds.length === 0;
  compareCount.textContent = compareIds.length ? `${compareIds.length}/2 ausgewählt` : "";
  compareOpenBtn.disabled = compareIds.length !== 2;
}

function closeCompareModal() {
  compareModal.hidden = true;
  compareContent.innerHTML = "";
}

function statLabel(name, de) {
  return de || formatSlug(name);
}

function renderCompare(a, b) {
  const spriteA = mediaUrl(a.sprite);
  const spriteB = mediaUrl(b.sprite);

  const column = (p, sprite) => `
    <div class="compare-column">
      <img src="${sprite || ""}" alt="${p.name}" />
      <p class="card-name">${p.german_name || p.name}</p>
      <div class="type-badges">${(p.types || []).map((t) => `<span class="type-badge">${typeNameDe(t)}</span>`).join("")}</div>
    </div>
  `;

  const statsA = new Map((a.stats || []).map((s) => [s.name, s]));
  const statsB = new Map((b.stats || []).map((s) => [s.name, s]));
  const statNames = [...new Set([...statsA.keys(), ...statsB.keys()])];

  const statsHtml = statNames
    .map((name) => {
      const sa = statsA.get(name);
      const sb = statsB.get(name);
      const va = sa?.value ?? null;
      const vb = sb?.value ?? null;
      const higherA = va != null && vb != null && va > vb;
      const higherB = va != null && vb != null && vb > va;

      return `
        <div class="compare-stat-row"><span class="compare-stat-label">${statLabel(name, sa?.name_de || sb?.name_de)}</span></div>
        <div class="compare-stat-row">
          <span class="compare-stat-value${higherA ? " higher" : ""}">${va ?? "–"}</span>
          <span></span>
          <span class="compare-stat-value${higherB ? " higher" : ""}">${vb ?? "–"}</span>
        </div>
      `;
    })
    .join("");

  return `
    <div class="compare-columns">${column(a, spriteA)}${column(b, spriteB)}</div>
    <div class="detail-section">
      <div class="compare-stat-row"><span class="compare-stat-label">Größe / Gewicht</span></div>
      <div class="compare-stat-row">
        <span>${a.height_m ?? "–"} m / ${a.weight_kg ?? "–"} kg</span>
        <span></span>
        <span>${b.height_m ?? "–"} m / ${b.weight_kg ?? "–"} kg</span>
      </div>
      ${statsHtml}
    </div>
  `;
}

async function openCompare() {
  if (compareIds.length !== 2) return;

  compareModal.hidden = false;
  compareContent.innerHTML = "<p>Lädt…</p>";

  try {
    const [a, b] = await Promise.all(compareIds.map((id) => fetchPokemonDetail(id)));
    compareContent.innerHTML = renderCompare(a, b);
  } catch (err) {
    compareContent.innerHTML = `<p>Fehler beim Laden: ${err.message}</p>`;
  }
}

compareOpenBtn.addEventListener("click", openCompare);
compareClearBtn.addEventListener("click", clearCompare);
compareCloseBtn.addEventListener("click", closeCompareModal);
compareModal.addEventListener("click", (e) => {
  if (e.target === compareModal) closeCompareModal();
});

// ---------------------------------------------------------
// Type filter chips
// ---------------------------------------------------------

function renderTypeFilters() {
  typeFiltersEl.innerHTML = Object.keys(TYPE_NAMES_DE)
    .filter((slug) => slug !== "unknown")
    .map((slug) => `<button type="button" class="type-chip" data-type="${slug}">${typeNameDeBySlug(slug)}</button>`)
    .join("");
}

typeFiltersEl.addEventListener("click", (e) => {
  const chip = e.target.closest(".type-chip");
  if (!chip) return;

  const slug = chip.dataset.type;
  if (activeTypes.has(slug)) activeTypes.delete(slug);
  else activeTypes.add(slug);

  chip.classList.toggle("active", activeTypes.has(slug));
  currentOffset = 0;
  loadPage({ reset: true });
});

favoritesToggleBtn.addEventListener("click", () => {
  favoritesOnly = !favoritesOnly;
  favoritesToggleBtn.setAttribute("aria-pressed", String(favoritesOnly));
  favoritesToggleBtn.classList.toggle("active", favoritesOnly);
  currentOffset = 0;
  loadPage({ reset: true });
});

async function fetchPokemonList({ search, offset, ids, types }) {
  const url = new URL(`${API_BASE_URL}/api/pokemon`, window.location.href);
  url.searchParams.set("limit", PAGE_SIZE);
  url.searchParams.set("offset", offset);
  if (search) url.searchParams.set("search", search);
  if (ids && ids.length) url.searchParams.set("ids", ids.join(","));
  if (types && types.length) url.searchParams.set("types", types.join(","));

  const response = await fetch(url);
  if (!response.ok) throw new Error(`API-Fehler: ${response.status}`);
  return response.json();
}

async function fetchPokemonDetail(identifier) {
  const response = await fetch(`${API_BASE_URL}/api/pokemon/${identifier}`);
  if (!response.ok) throw new Error(`API-Fehler: ${response.status}`);
  return response.json();
}

function mediaUrl(path) {
  if (!path) return null;
  if (/^https?:\/\//.test(path)) return path;
  const filename = path.split("/").pop();
  const folder = path.includes("/artwork-shiny/")
    ? "artwork-shiny"
    : path.includes("/artwork/")
    ? "artwork"
    : path.includes("/shiny/")
    ? "shiny"
    : path.includes("/cries/")
    ? "cries"
    : "sprites";
  return `${API_BASE_URL}/media/${folder}/${filename}`;
}

function createCard(pokemon) {
  const card = document.createElement("div");
  card.className = "card";
  card.tabIndex = 0;
  card.setAttribute("role", "button");
  card.dataset.pokemonId = pokemon.id;
  if (isCompareSelected(pokemon.id)) card.classList.add("compare-selected");

  const sprite = mediaUrl(pokemon.sprite);
  const typeBadges = (pokemon.types || [])
    .map((t) => `<span class="type-badge">${typeNameDe(t)}</span>`)
    .join("");

  card.innerHTML = `
    <input type="checkbox" class="card-compare" data-compare-id="${pokemon.id}" title="Zum Vergleich auswählen" ${isCompareSelected(pokemon.id) ? "checked" : ""} />
    <button type="button" class="card-favorite${isFavorite(pokemon.id) ? " active" : ""}" data-favorite-id="${pokemon.id}" aria-label="Favorit" title="Favorit">★</button>
    <img src="${sprite || ""}" alt="${pokemon.name}" loading="lazy" />
    <p class="card-id">#${String(pokemon.id).padStart(3, "0")}</p>
    <p class="card-name">${pokemon.german_name || pokemon.name}</p>
    <div class="type-badges">${typeBadges}</div>
  `;

  const open = () => openDetail(pokemon.id);
  card.addEventListener("click", (e) => {
    if (e.target.closest(".card-favorite") || e.target.closest(".card-compare")) return;
    open();
  });
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") open();
  });

  card.querySelector(".card-favorite").addEventListener("click", () => toggleFavorite(pokemon.id));
  card.querySelector(".card-compare").addEventListener("change", () => toggleCompare(pokemon.id));

  return card;
}

async function openDetail(identifier) {
  modal.hidden = false;
  modalContent.innerHTML = "<p>Lädt…</p>";

  try {
    const p = await fetchPokemonDetail(identifier);
    recordRecentlyViewed(p);
    const sprite = mediaUrl(p.sprite);
    const shiny = mediaUrl(p.shiny);
    const cry = mediaUrl(p.cry);
    const artwork = mediaUrl(p.artwork) || sprite;
    const artworkShiny = mediaUrl(p.artwork_shiny) || shiny;

    const typeBadges = (p.types || [])
      .map((t) => `<span class="type-badge">${typeNameDe(t)}</span>`)
      .join("");

    const abilities = (p.abilities || [])
      .map((a) => {
        const label = a.name_de || formatSlug(a.name);
        const effect = a.effect_de ? ` – ${a.effect_de}` : "";
        return `<li><strong>${label}</strong>${a.hidden ? " (versteckt)" : ""}${effect}</li>`;
      })
      .join("");

    const flags = [];
    if (p.legendary) flags.push("Legendär");
    if (p.mythical) flags.push("Mystisch");
    if (p.baby) flags.push("Baby");

    modalContent.innerHTML = `
      <div class="detail-header">
        <img class="zoomable" src="${sprite || ""}" alt="${p.name}" data-full="${artwork || sprite || ""}" />
        <div>
          <p class="detail-id">#${String(p.id).padStart(3, "0")}</p>
          <div class="detail-title-row">
            <h2>${p.german_name || p.name}</h2>
            <button type="button" class="detail-favorite${isFavorite(p.id) ? " active" : ""}" data-favorite-id="${p.id}" aria-label="Favorit" title="Favorit">★</button>
          </div>
          <div class="type-badges">${typeBadges}</div>
          <button type="button" class="chip-toggle detail-compare${isCompareSelected(p.id) ? " active" : ""}" data-compare-id="${p.id}">⚖ Vergleichen</button>
        </div>
      </div>

      ${flags.length ? `<div class="badge-row">${flags.map((f) => `<span class="flag-badge">${f}</span>`).join("")}</div>` : ""}

      ${p.description_de ? `<div class="detail-section"><h3>Beschreibung</h3><p>${p.description_de}</p></div>` : ""}

      <div class="detail-section">
        <h3>Daten</h3>
        <div class="stat-grid">
          <span>Größe</span><span>${p.height_m ?? "–"} m</span>
          <span>Gewicht</span><span>${p.weight_kg ?? "–"} kg</span>
          <span>Kategorie</span><span>${p.category ?? "–"}</span>
          <span>Generation</span><span>${p.generation ?? "–"}</span>
          <span>Fangrate</span><span>${p.capture_rate ?? "–"}</span>
          <span>Basisfreundschaft</span><span>${p.base_happiness ?? "–"}</span>
          <span>Farbe</span><span>${p.color_de || p.color || "–"}</span>
          <span>Form</span><span>${p.shape_de || p.shape || "–"}</span>
          <span>Lebensraum</span><span>${p.habitat_de || p.habitat || "–"}</span>
          <span>Wachstum</span><span>${p.growth_rate_de || p.growth_rate || "–"}</span>
          <span>Geschlecht</span><span>${genderRatioText(p.gender_rate)}</span>
          <span>Ei-Zyklen</span><span>${p.hatch_counter ?? "–"}</span>
        </div>
      </div>

      ${renderStatsChart(p.stats)}

      ${renderEffectivenessChart(p.types)}

      ${abilities ? `<div class="detail-section"><h3>Fähigkeiten</h3><ul class="ability-list">${abilities}</ul></div>` : ""}

      ${renderEvolutionSection(p)}

      ${shiny || cry ? `<div class="detail-section"><h3>Medien</h3>
        ${shiny ? `<img class="zoomable" src="${shiny}" alt="${p.name} shiny" title="Schillernd" width="80" height="80" style="image-rendering:pixelated" data-full="${artworkShiny || shiny}" />` : ""}
        ${cry ? `<audio controls src="${cry}"></audio>` : ""}
      </div>` : ""}
    `;
  } catch (err) {
    modalContent.innerHTML = `<p>Fehler beim Laden: ${err.message}</p>`;
  }
}

function closeModal() {
  modal.hidden = true;
  modalContent.innerHTML = "";
}

function openLightbox(src, alt) {
  if (!src) return;
  lightboxImg.src = src;
  lightboxImg.alt = alt || "";
  lightbox.hidden = false;
}

function closeLightbox() {
  lightbox.hidden = true;
  lightboxImg.src = "";
}

modalContent.addEventListener("click", (e) => {
  const zoomable = e.target.closest(".zoomable");
  if (zoomable) {
    openLightbox(zoomable.dataset.full || zoomable.src, zoomable.alt);
    return;
  }

  const favBtn = e.target.closest(".detail-favorite");
  if (favBtn) {
    toggleFavorite(favBtn.dataset.favoriteId);
    return;
  }

  const compareBtn = e.target.closest(".detail-compare");
  if (compareBtn) {
    toggleCompare(compareBtn.dataset.compareId);
    return;
  }

  const entry = e.target.closest("[data-pokemon-id]");
  if (entry) openDetail(entry.dataset.pokemonId);
});

modalClose.addEventListener("click", closeModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeModal();
});

lightboxClose.addEventListener("click", closeLightbox);
lightbox.addEventListener("click", (e) => {
  if (e.target === lightbox) closeLightbox();
});

document.addEventListener("keydown", (e) => {
  if (e.key !== "Escape") return;
  if (!lightbox.hidden) {
    closeLightbox();
  } else if (!compareModal.hidden) {
    closeCompareModal();
  } else if (!modal.hidden) {
    closeModal();
  }
});

async function loadPage({ reset }) {
  const token = ++requestToken;
  statusEl.textContent = "Lädt…";
  loadMoreBtn.hidden = true;

  if (favoritesOnly && favorites.size === 0) {
    if (reset) grid.innerHTML = "";
    total = 0;
    statusEl.textContent = "Keine Favoriten ausgewählt.";
    return;
  }

  try {
    const data = await fetchPokemonList({
      search: currentSearch,
      offset: currentOffset,
      ids: favoritesOnly ? [...favorites] : null,
      types: [...activeTypes],
    });
    if (token !== requestToken) return;

    total = data.total;

    if (reset) grid.innerHTML = "";
    data.items.forEach((p) => grid.appendChild(createCard(p)));

    currentOffset += data.items.length;

    const shown = grid.children.length;
    statusEl.textContent = `${shown} von ${total} Pokémon`;
    loadMoreBtn.hidden = currentOffset >= total;
  } catch (err) {
    if (token !== requestToken) return;
    statusEl.textContent = `Fehler beim Laden: ${err.message}`;
  }
}

function search(term) {
  currentSearch = term.trim();
  currentOffset = 0;
  loadPage({ reset: true });
}

let debounceTimer;
searchInput.addEventListener("input", (e) => {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(() => search(e.target.value), 300);
});

loadMoreBtn.addEventListener("click", () => loadPage({ reset: false }));

renderTypeFilters();
renderRecentRow();
loadPage({ reset: true });

if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register(`${API_BASE_URL}/sw.js`).catch(() => {});
  });
}
