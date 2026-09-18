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

let currentSearch = "";
let currentOffset = 0;
let total = 0;
let requestToken = 0;

async function fetchPokemonList(search, offset) {
  const url = new URL(`${API_BASE_URL}/api/pokemon`, window.location.href);
  url.searchParams.set("limit", PAGE_SIZE);
  url.searchParams.set("offset", offset);
  if (search) url.searchParams.set("search", search);

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
  const folder = path.includes("/shiny/")
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

  const sprite = mediaUrl(pokemon.sprite);
  const typeBadges = (pokemon.types || [])
    .map((t) => `<span class="type-badge">${typeNameDe(t)}</span>`)
    .join("");

  card.innerHTML = `
    <img src="${sprite || ""}" alt="${pokemon.name}" loading="lazy" />
    <p class="card-id">#${String(pokemon.id).padStart(3, "0")}</p>
    <p class="card-name">${pokemon.german_name || pokemon.name}</p>
    <div class="type-badges">${typeBadges}</div>
  `;

  const open = () => openDetail(pokemon.id);
  card.addEventListener("click", open);
  card.addEventListener("keydown", (e) => {
    if (e.key === "Enter" || e.key === " ") open();
  });

  return card;
}

async function openDetail(identifier) {
  modal.hidden = false;
  modalContent.innerHTML = "<p>Lädt…</p>";

  try {
    const p = await fetchPokemonDetail(identifier);
    const sprite = mediaUrl(p.sprite);
    const shiny = mediaUrl(p.shiny);
    const cry = mediaUrl(p.cry);

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
        <img src="${sprite || ""}" alt="${p.name}" />
        <div>
          <p class="detail-id">#${String(p.id).padStart(3, "0")}</p>
          <h2>${p.german_name || p.name}</h2>
          <div class="type-badges">${typeBadges}</div>
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
        ${shiny ? `<img src="${shiny}" alt="${p.name} shiny" title="Schillernd" width="80" height="80" style="image-rendering:pixelated" />` : ""}
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

modalContent.addEventListener("click", (e) => {
  const entry = e.target.closest("[data-pokemon-id]");
  if (entry) openDetail(entry.dataset.pokemonId);
});

modalClose.addEventListener("click", closeModal);
modal.addEventListener("click", (e) => {
  if (e.target === modal) closeModal();
});
document.addEventListener("keydown", (e) => {
  if (e.key === "Escape" && !modal.hidden) closeModal();
});

async function loadPage({ reset }) {
  const token = ++requestToken;
  statusEl.textContent = "Lädt…";
  loadMoreBtn.hidden = true;

  try {
    const data = await fetchPokemonList(currentSearch, currentOffset);
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

loadPage({ reset: true });
