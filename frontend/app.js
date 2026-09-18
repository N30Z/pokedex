const API_BASE_URL = window.API_BASE_URL || "";
const PAGE_SIZE = 40;

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
    .map((t) => `<span class="type-badge">${t.name}</span>`)
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
      .map((t) => `<span class="type-badge">${t.name}</span>`)
      .join("");

    const abilities = (p.abilities || [])
      .map((a) => `<li>${a.name}${a.hidden ? " (versteckt)" : ""}</li>`)
      .join("");

    const flags = [];
    if (p.legendary) flags.push("Legendär");
    if (p.mythical) flags.push("Mystisch");

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
        </div>
      </div>

      ${abilities ? `<div class="detail-section"><h3>Fähigkeiten</h3><ul class="ability-list">${abilities}</ul></div>` : ""}

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
