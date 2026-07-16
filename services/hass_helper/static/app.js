const toastEl = document.getElementById("toast");
const toastMessageEl = toastEl?.querySelector(".toast-message") ?? null;
const toastCloseEl = toastEl?.querySelector(".toast-close") ?? null;

const state = {
  entities: [],
  selectedEntityId: null,
  chart: null,
};

let toastTimer;

function showToast(message, variant = "info") {
  if (!toastEl || !toastMessageEl) return;
  clearTimeout(toastTimer);
  toastEl.classList.toggle("toast-error", variant === "error");
  toastEl.setAttribute("role", variant === "error" ? "alert" : "status");
  toastEl.setAttribute("aria-live", variant === "error" ? "assertive" : "polite");
  toastMessageEl.textContent = message;
  toastEl.hidden = false;
  if (variant !== "error") {
    toastTimer = setTimeout(() => hideToast(), 5000);
  }
}

function hideToast() {
  if (!toastEl || !toastMessageEl) return;
  clearTimeout(toastTimer);
  toastEl.hidden = true;
  toastMessageEl.textContent = "";
}

toastCloseEl?.addEventListener("click", () => hideToast());

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const payload = await response.json();
      detail = payload?.detail || payload?.message || detail;
    } catch (error) {
      detail = await response.text();
    }
    throw new Error(detail || "Unexpected error");
  }
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return response.json();
  }
  return response.text();
}

function formToPayload(form) {
  const data = new FormData(form);
  const payload = {};
  for (const [key, value] of data.entries()) {
    if (typeof value === "string") {
      const trimmed = value.trim();
      payload[key] = trimmed === "" ? null : trimmed;
    } else {
      payload[key] = value;
    }
  }
  return payload;
}

function populateForm(form, data) {
  if (!form || !data) return;
  const elements = Array.from(form.elements).filter((el) => el.name);
  elements.forEach((element) => {
    const value = data[element.name];
    if (value === undefined || value === null) {
      element.value = "";
      return;
    }
    element.value = value;
  });
}

function setButtonLoading(button, isLoading) {
  if (!(button instanceof HTMLButtonElement)) return;
  if (isLoading) {
    button.disabled = true;
    button.dataset.originalLabel = button.dataset.originalLabel || button.textContent || "";
    button.textContent = "Working…";
  } else {
    button.disabled = false;
    if (button.dataset.originalLabel) {
      button.textContent = button.dataset.originalLabel;
      delete button.dataset.originalLabel;
    }
  }
}

async function loadMqttConfig() {
  try {
    const config = await fetchJson("/api/mqtt/config");
    populateForm(document.getElementById("mqtt-form"), config);
  } catch (error) {
    showToast(error.message, "error");
  }
}

function collectMqttPayload(form) {
  const payload = formToPayload(form);
  if (payload.port !== null && payload.port !== undefined) {
    const port = Number(payload.port);
    payload.port = Number.isFinite(port) ? port : payload.port;
  }
  return payload;
}

async function handleMqttSave(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = document.getElementById("save-mqtt");
  setButtonLoading(submitButton, true);
  try {
    const payload = collectMqttPayload(form);
    await fetchJson("/api/mqtt/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    showToast("MQTT settings saved.");
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(submitButton, false);
  }
}

async function handleMqttTest() {
  const form = document.getElementById("mqtt-form");
  if (!(form instanceof HTMLFormElement)) return;
  const button = document.getElementById("test-mqtt");
  setButtonLoading(button, true);
  try {
    const payload = collectMqttPayload(form);
    const result = await fetchJson("/api/mqtt/test", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    const variant = result?.success ? "info" : "error";
    showToast(result?.message || "MQTT test complete.", variant);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(button, false);
  }
}

function renderEntityList() {
  const list = document.getElementById("entity-list");
  if (!list) return;
  list.innerHTML = "";
  if (!state.entities.length) {
    const empty = document.createElement("li");
    empty.className = "muted";
    empty.textContent = "No managed entities yet. Create one to get started.";
    list.appendChild(empty);
    return;
  }
  state.entities.forEach((entity) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "entity-item" + (state.selectedEntityId === entity.entity_id ? " selected" : "");
    button.dataset.entityId = entity.entity_id;

    const name = document.createElement("span");
    name.className = "entity-name";
    name.textContent = entity.name || entity.entity_id;

    const meta = document.createElement("div");
    meta.className = "entity-meta";
    const idSpan = document.createElement("span");
    idSpan.textContent = entity.entity_id;
    const valueSpan = document.createElement("span");
    if (entity.last_value != null) {
      valueSpan.textContent = `${entity.last_value}${entity.unit_of_measurement ? ` ${entity.unit_of_measurement}` : ""}`;
    } else {
      valueSpan.textContent = "No data";
    }
    meta.append(idSpan, valueSpan);

    button.append(name, meta);
    button.addEventListener("click", () => selectEntity(entity.entity_id));
    item.appendChild(button);
    list.appendChild(item);
  });
}

async function loadEntities(selectId = null) {
  try {
    const entities = await fetchJson("/api/managed/entities");
    state.entities = Array.isArray(entities) ? entities : [];
    if (selectId) {
      state.selectedEntityId = selectId;
    } else if (!state.entities.some((item) => item.entity_id === state.selectedEntityId)) {
      state.selectedEntityId = null;
    }
    renderEntityList();
    if (state.selectedEntityId) {
      await loadEntityDetail(state.selectedEntityId);
    }
  } catch (error) {
    showToast(error.message, "error");
  }
}

function updateDetailSubtitle(entity) {
  const subtitle = document.getElementById("entity-detail-subtitle");
  if (!subtitle) return;
  if (!entity?.last_updated) {
    subtitle.textContent = "No data recorded yet.";
    return;
  }
  const date = new Date(entity.last_updated);
  subtitle.textContent = `Last value ${entity.last_value ?? "–"} at ${date.toLocaleString()}`;
}

function toggleDetailCard(visible) {
  const card = document.getElementById("entity-detail-card");
  if (!card) return;
  card.hidden = !visible;
}

function updateHistoryChart(entity) {
  const history = Array.isArray(entity?.history) ? entity.history : [];
  const canvas = document.getElementById("history-chart");
  const emptyLabel = document.getElementById("history-empty");
  if (!canvas) return;

  if (!history.length || !window.Chart) {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    if (emptyLabel) emptyLabel.hidden = false;
    return;
  }

  const labels = history.map((point) => new Date(point.recorded_at).toLocaleString());
  const values = history.map((point) => {
    const number = Number(point.value);
    return Number.isFinite(number) ? number : null;
  });
  const hasValues = values.some((value) => value !== null);

  if (!hasValues) {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
    if (emptyLabel) emptyLabel.hidden = false;
    return;
  }

  if (emptyLabel) emptyLabel.hidden = true;

  const dataset = {
    label: entity.name || entity.entity_id,
    data: values,
    fill: false,
    borderColor: "#2563eb",
    tension: 0.25,
    pointRadius: 3,
    spanGaps: true,
  };

  if (!state.chart) {
    state.chart = new Chart(canvas, {
      type: "line",
      data: { labels, datasets: [dataset] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { beginAtZero: false, ticks: { color: "#475569" } },
          x: { ticks: { color: "#475569" } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label(context) {
                return `${context.parsed.y} ${entity.unit_of_measurement ?? ""}`.trim();
              },
            },
          },
        },
      },
    });
  } else {
    state.chart.data.labels = labels;
    state.chart.data.datasets[0] = dataset;
    state.chart.update();
  }
}

function populateEntityDetail(entity) {
  const form = document.getElementById("entity-edit-form");
  if (!form || !entity) return;
  populateForm(form, {
    name: entity.name ?? "",
    entity_id: entity.entity_id ?? "",
    data_type: entity.data_type ?? "",
    unit_of_measurement: entity.unit_of_measurement ?? "",
    device_class: entity.device_class ?? "",
    state_class: entity.state_class ?? "",
    icon: entity.icon ?? "",
    topic: entity.topic ?? "",
    description: entity.description ?? "",
  });
  const title = document.getElementById("entity-detail-title");
  if (title) {
    title.textContent = entity.name || "Entity details";
  }
  updateDetailSubtitle(entity);
  updateHistoryChart(entity);
}

async function loadEntityDetail(entityId) {
  try {
    const entity = await fetchJson(`/api/managed/entities/${encodeURIComponent(entityId)}`);
    state.selectedEntityId = entity.entity_id;
    populateEntityDetail(entity);
    toggleDetailCard(true);
    renderEntityList();
  } catch (error) {
    showToast(error.message, "error");
  }
}

async function selectEntity(entityId) {
  if (!entityId) return;
  state.selectedEntityId = entityId;
  await loadEntityDetail(entityId);
}

async function handleEntityCreate(event) {
  event.preventDefault();
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit']");
  setButtonLoading(submitButton, true);
  try {
    const payload = formToPayload(form);
    const entity = await fetchJson("/api/managed/entities", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    showToast("Entity created successfully.");
    await loadEntities(entity?.entity_id);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(submitButton, false);
  }
}

async function handleEntityUpdate(event) {
  event.preventDefault();
  if (!state.selectedEntityId) return;
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit']");
  setButtonLoading(submitButton, true);
  try {
    const payload = formToPayload(form);
    const entity = await fetchJson(`/api/managed/entities/${encodeURIComponent(state.selectedEntityId)}`, {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    showToast("Entity updated.");
    state.selectedEntityId = entity?.entity_id ?? state.selectedEntityId;
    populateEntityDetail(entity);
    await loadEntities(state.selectedEntityId);
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(submitButton, false);
  }
}

async function handleEntityDelete() {
  if (!state.selectedEntityId) return;
  const confirmDelete = window.confirm("Delete this entity? This will remove stored history as well.");
  if (!confirmDelete) return;
  const button = document.getElementById("delete-entity");
  setButtonLoading(button, true);
  try {
    await fetchJson(`/api/managed/entities/${encodeURIComponent(state.selectedEntityId)}`, {
      method: "DELETE",
    });
    showToast("Entity removed.");
    state.selectedEntityId = null;
    toggleDetailCard(false);
    await loadEntities();
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(button, false);
  }
}

async function handlePublish(event) {
  event.preventDefault();
  if (!state.selectedEntityId) return;
  const form = event.currentTarget;
  const submitButton = form.querySelector("button[type='submit']");
  setButtonLoading(submitButton, true);
  try {
    const payload = formToPayload(form);
    const point = await fetchJson(`/api/managed/entities/${encodeURIComponent(state.selectedEntityId)}/publish`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
    form.reset();
    showToast("Value sent to MQTT.");
    await loadEntities(state.selectedEntityId);
    if (point) {
      await loadEntityDetail(state.selectedEntityId);
    }
  } catch (error) {
    showToast(error.message, "error");
  } finally {
    setButtonLoading(submitButton, false);
  }
}

function bindEvents() {
  const mqttForm = document.getElementById("mqtt-form");
  mqttForm?.addEventListener("submit", handleMqttSave);
  document.getElementById("test-mqtt")?.addEventListener("click", handleMqttTest);
  document.getElementById("refresh-entities")?.addEventListener("click", () => loadEntities(state.selectedEntityId));
  document.getElementById("entity-create-form")?.addEventListener("submit", handleEntityCreate);
  document.getElementById("entity-edit-form")?.addEventListener("submit", handleEntityUpdate);
  document.getElementById("delete-entity")?.addEventListener("click", handleEntityDelete);
  document.getElementById("entity-data-form")?.addEventListener("submit", handlePublish);
}

async function init() {
  bindEvents();
  await loadMqttConfig();
  await loadEntities();
}

document.addEventListener("DOMContentLoaded", () => {
  init();
});
