const toastEl = document.getElementById("toast");
const toastMessageEl = toastEl?.querySelector(".toast-message") ?? null;
const toastCloseEl = toastEl?.querySelector(".toast-close") ?? null;
let statusTimer;

const state = {
  selectedDomains: [],
  availableDomains: [],
  blacklist: { entities: [], devices: [] },
  whitelist: [],
  entities: [],
  devices: [],
  expandedDevices: new Set(),
};

const UNKNOWN_DEVICE_KEY = "__no_device__";

function setButtonLoading(button, loadingText = "Working…") {
  if (!(button instanceof HTMLButtonElement)) return;
  const loadingStyle = button.dataset.loadingStyle || "text";
  button.setAttribute("aria-busy", "true");
  if (loadingStyle === "icon") {
    button.disabled = true;
    button.classList.add("loading-icon");
    return;
  }
  if (!button.dataset.originalLabel) {
    button.dataset.originalLabel = button.textContent ?? "";
  }
  button.textContent = loadingText;
  button.disabled = true;
  button.classList.add("loading");
}

function clearButtonLoading(button) {
  if (!(button instanceof HTMLButtonElement)) return;
  const loadingStyle = button.dataset.loadingStyle || "text";
  button.disabled = false;
  button.removeAttribute("aria-busy");
  button.classList.remove("loading");
  if (loadingStyle === "icon") {
    button.classList.remove("loading-icon");
    return;
  }
  const originalLabel = button.dataset.originalLabel ?? "";
  button.textContent = originalLabel;
  delete button.dataset.originalLabel;
}

async function withButtonLoading(button, action, loadingText = "Working…") {
  const target = button instanceof HTMLButtonElement ? button : null;
  if (target) {
    setButtonLoading(target, loadingText);
  }
  try {
    return await action();
  } finally {
    if (target) {
      clearButtonLoading(target);
    }
  }
}

function showStatus(message, type = "info", timeout = 5000) {
  if (!toastEl || !toastMessageEl) return;
  clearTimeout(statusTimer);
  toastEl.setAttribute("role", type === "error" ? "alert" : "status");
  toastEl.setAttribute("aria-live", type === "error" ? "assertive" : "polite");
  toastMessageEl.textContent = message;
  toastEl.classList.toggle("toast--error", type === "error");
  toastEl.classList.toggle("toast--info", type !== "error");
  toastEl.hidden = false;
  if (type === "error") {
    timeout = 0;
  }
  if (timeout > 0) {
    statusTimer = setTimeout(() => {
      hideStatus();
    }, timeout);
  }
}

function hideStatus() {
  if (!toastEl || !toastMessageEl) return;
  clearTimeout(statusTimer);
  toastEl.hidden = true;
  toastMessageEl.textContent = "";
  toastEl.classList.remove("toast--error", "toast--info");
  toastEl.setAttribute("role", "status");
  toastEl.setAttribute("aria-live", "polite");
}

toastCloseEl?.addEventListener("click", () => hideStatus());

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    let detail;
    try {
      const payload = await response.json();
      detail = payload?.detail || payload?.message;
    } catch (error) {
      detail = await response.text();
    }
    throw new Error(detail || `${response.status} ${response.statusText}`);
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

function formatMeasurement(entity) {
  if (!entity) return "";
  const attributes = entity.attributes || {};
  const unit =
    entity.unit_of_measurement ??
    entity.unit ??
    attributes.unit_of_measurement ??
    attributes.unit ??
    attributes.measurement ??
    attributes.native_unit_of_measurement ??
    "";
  return unit ?? "";
}

function renderSelectedDomains() {
  const tbody = document.querySelector("#domains-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!state.selectedDomains.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="3" data-label="Message">No domains selected.</td>';
    tbody.appendChild(row);
    return;
  }
  state.selectedDomains.forEach((entry) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="Domain">${entry.domain}</td>
      <td data-label="Display name">${entry.title || entry.domain}</td>
      <td class="actions">
        <button class="danger" data-action="remove-domain" data-id="${entry.domain}">Remove</button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

function renderBlacklist() {
  const entityBody = document.querySelector("#blacklist-entities tbody");
  const deviceBody = document.querySelector("#blacklist-devices tbody");
  if (entityBody) {
    entityBody.innerHTML = "";
    if (!state.blacklist.entities.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="2" data-label="Message">No entities blacklisted.</td>';
      entityBody.appendChild(row);
    } else {
      state.blacklist.entities.forEach((entityId) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td data-label="Entity ID">${entityId}</td>
          <td class="actions">
            <button class="danger" data-action="remove-blacklist" data-type="entity" data-id="${entityId}">Remove</button>
          </td>
        `;
        entityBody.appendChild(row);
      });
    }
  }
  if (deviceBody) {
    deviceBody.innerHTML = "";
    if (!state.blacklist.devices.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="2" data-label="Message">No devices blacklisted.</td>';
      deviceBody.appendChild(row);
    } else {
      state.blacklist.devices.forEach((deviceId) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td data-label="Device ID">${deviceId}</td>
          <td class="actions">
            <button class="danger" data-action="remove-blacklist" data-type="device" data-id="${deviceId}">Remove</button>
          </td>
        `;
        deviceBody.appendChild(row);
      });
    }
  }
}

function renderWhitelist() {
  const tbody = document.querySelector("#whitelist-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!state.whitelist.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="2" data-label="Message">No entities whitelisted.</td>';
    tbody.appendChild(row);
    return;
  }
  state.whitelist.forEach((entityId) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="Entity ID">${entityId}</td>
      <td class="actions">
        <button class="danger" data-action="remove-whitelist" data-id="${entityId}">Remove</button>
      </td>
    `;
    tbody.appendChild(row);
  });
}

function renderEntities() {
  const entityBody = document.querySelector("#entities-table tbody");
  const entityCount = document.getElementById("entity-count");
  const deviceLookup = new Map();
  state.devices.forEach((device) => {
    if (!device) return;
    const key = device.device_id ?? device.id;
    if (!key) return;
    deviceLookup.set(key, device);
  });

  const createBlacklistButton = ({ action, id, label, disabled = false }) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "icon-button";
    button.dataset.action = action;
    button.dataset.loadingStyle = "icon";
    button.setAttribute("aria-label", label);
    button.title = label;
    button.textContent = "+";
    if (id) {
      button.dataset.id = id;
    }
    if (disabled) {
      button.disabled = true;
    }
    return button;
  };

  if (!entityBody) {
    if (entityCount) {
      entityCount.textContent = `${state.entities.length} entities`;
    }
    return;
  }

  entityBody.innerHTML = "";

  if (!state.entities.length) {
    const row = document.createElement("tr");
    const cell = document.createElement("td");
    cell.colSpan = 6;
    cell.dataset.label = "Message";
    cell.textContent = "No entities ingested yet.";
    row.appendChild(cell);
    entityBody.appendChild(row);
    if (entityCount) {
      entityCount.textContent = "0 entities";
    }
    return;
  }

  const deviceOrder = [];
  const groupedEntities = new Map();
  state.entities.forEach((entity) => {
    const deviceId = entity.device_id || UNKNOWN_DEVICE_KEY;
    if (!groupedEntities.has(deviceId)) {
      groupedEntities.set(deviceId, []);
      deviceOrder.push(deviceId);
    }
    groupedEntities.get(deviceId)?.push(entity);
  });

  const validDeviceIds = new Set(deviceOrder);
  Array.from(state.expandedDevices).forEach((deviceId) => {
    if (!validDeviceIds.has(deviceId)) {
      state.expandedDevices.delete(deviceId);
    }
  });

  deviceOrder.forEach((deviceId) => {
    const entities = groupedEntities.get(deviceId) ?? [];
    const device = deviceLookup.get(deviceId) || null;
    const firstEntity = entities[0] || null;
    const integrationLabel =
      device?.integration_id || firstEntity?.integration_id || "";
    const areaLabel =
      device?.area ||
      device?.area_id ||
      firstEntity?.area ||
      firstEntity?.area_id ||
      "";
    const deviceDisplayName =
      device?.name_by_user ||
      device?.name ||
      (deviceId === UNKNOWN_DEVICE_KEY ? "Unassigned entities" : deviceId) ||
      "";
    const deviceMetaLabel =
      deviceId && deviceId !== UNKNOWN_DEVICE_KEY
        ? deviceId
        : device?.device_id ||
          (deviceId === UNKNOWN_DEVICE_KEY ? "No device ID" : "");
    const isExpanded = state.expandedDevices.has(deviceId);

    const deviceRow = document.createElement("tr");
    deviceRow.classList.add("device-row");
    deviceRow.dataset.deviceId = deviceId;

    const blacklistCell = document.createElement("td");
    blacklistCell.dataset.label = "Blacklist";
    const deviceButton = createBlacklistButton({
      action: "blacklist-device",
      id: deviceId !== UNKNOWN_DEVICE_KEY ? deviceId : undefined,
      label:
        deviceId !== UNKNOWN_DEVICE_KEY
          ? `Add device ${deviceDisplayName} to blacklist`
          : "Device ID unavailable",
      disabled: deviceId === UNKNOWN_DEVICE_KEY,
    });
    blacklistCell.appendChild(deviceButton);
    deviceRow.appendChild(blacklistCell);

    const deviceCell = document.createElement("td");
    deviceCell.dataset.label = "Device";
    deviceCell.classList.add("device-cell");
    const toggleButton = document.createElement("button");
    toggleButton.type = "button";
    toggleButton.className = "toggle-entities";
    toggleButton.dataset.action = "toggle-device";
    toggleButton.dataset.id = deviceId;
    toggleButton.setAttribute("aria-expanded", String(isExpanded));
    const toggleIcon = document.createElement("span");
    toggleIcon.className = "toggle-icon";
    toggleIcon.textContent = isExpanded ? "▾" : "▸";
    const toggleLabel = document.createElement("span");
    toggleLabel.className = "toggle-label";
    toggleLabel.textContent = deviceDisplayName;
    const toggleCount = document.createElement("span");
    toggleCount.className = "toggle-count";
    toggleCount.textContent = `(${entities.length})`;
    toggleButton.append(toggleIcon, toggleLabel, toggleCount);
    deviceCell.appendChild(toggleButton);
    if (deviceMetaLabel) {
      const meta = document.createElement("div");
      meta.className = "device-id-tag";
      meta.textContent = deviceMetaLabel;
      deviceCell.appendChild(meta);
    }
    const deviceInfo =
      device?.model && device?.manufacturer
        ? `${device.manufacturer} ${device.model}`.trim()
        : device?.model || device?.manufacturer || "";
    if (deviceInfo) {
      deviceCell.title = deviceInfo;
    }
    deviceRow.appendChild(deviceCell);

    const deviceEntityCell = document.createElement("td");
    deviceEntityCell.dataset.label = "Entity Name";
    deviceEntityCell.textContent = "";
    deviceRow.appendChild(deviceEntityCell);

    const deviceIntegrationCell = document.createElement("td");
    deviceIntegrationCell.dataset.label = "Integration";
    deviceIntegrationCell.textContent = integrationLabel;
    deviceRow.appendChild(deviceIntegrationCell);

    const deviceMeasurementCell = document.createElement("td");
    deviceMeasurementCell.dataset.label = "Unit";
    deviceMeasurementCell.textContent = "";
    deviceRow.appendChild(deviceMeasurementCell);

    const deviceAreaCell = document.createElement("td");
    deviceAreaCell.dataset.label = "Area";
    deviceAreaCell.textContent = areaLabel;
    deviceRow.appendChild(deviceAreaCell);

    entityBody.appendChild(deviceRow);

    if (!isExpanded) {
      return;
    }

    entities.forEach((entity) => {
      const entityRow = document.createElement("tr");
      entityRow.classList.add("entity-row");
      entityRow.dataset.parentDevice = deviceId;

      const entityBlacklistCell = document.createElement("td");
      entityBlacklistCell.dataset.label = "Blacklist";
      const entityButton = createBlacklistButton({
        action: "blacklist-entity",
        id: entity.entity_id,
        label: `Add entity ${entity.entity_id} to blacklist`,
      });
      entityBlacklistCell.appendChild(entityButton);
      entityRow.appendChild(entityBlacklistCell);

      const entityDeviceCell = document.createElement("td");
      entityDeviceCell.dataset.label = "Device";
      entityDeviceCell.classList.add("entity-device-cell");
      entityRow.appendChild(entityDeviceCell);

      const attributes = entity.attributes || {};
      const entityNameCell = document.createElement("td");
      entityNameCell.dataset.label = "Entity Name";
      const entityDisplayName =
        entity.name ||
        entity.original_name ||
        entity.friendly_name ||
        attributes.friendly_name ||
        entity.object_id ||
        entity.entity_id ||
        "";
      entityNameCell.textContent = entityDisplayName;
      if (entity.entity_id && entity.entity_id !== entityDisplayName) {
        entityNameCell.title = entity.entity_id;
      }
      entityRow.appendChild(entityNameCell);

      const entityIntegrationCell = document.createElement("td");
      entityIntegrationCell.dataset.label = "Integration";
      entityIntegrationCell.textContent =
        entity.integration_id || integrationLabel || "";
      entityRow.appendChild(entityIntegrationCell);

      const entityMeasurementCell = document.createElement("td");
      entityMeasurementCell.dataset.label = "Unit";
      entityMeasurementCell.textContent = formatMeasurement(entity);
      entityRow.appendChild(entityMeasurementCell);

      const entityAreaCell = document.createElement("td");
      entityAreaCell.dataset.label = "Area";
      entityAreaCell.textContent =
        entity.area || entity.area_id || attributes.area || areaLabel || "";
      entityRow.appendChild(entityAreaCell);

      entityBody.appendChild(entityRow);
    });
  });

  if (entityCount) {
    entityCount.textContent = `${state.entities.length} entities`;
  }
}

async function loadSelectedDomains() {
  try {
    const data = await fetchJson("/api/integrations/selected");
    state.selectedDomains = data || [];
    renderSelectedDomains();
  } catch (error) {
    showStatus(`Failed to load selected domains: ${error.message}`, "error", 7000);
  }
}

async function loadBlacklist() {
  try {
    const data = await fetchJson("/api/blacklist");
    state.blacklist = data || { entities: [], devices: [] };
    renderBlacklist();
  } catch (error) {
    showStatus(`Failed to load blacklist: ${error.message}`, "error", 7000);
  }
}

async function loadWhitelist() {
  try {
    const data = await fetchJson("/api/whitelist");
    state.whitelist = data?.entities || [];
    renderWhitelist();
  } catch (error) {
    showStatus(`Failed to load whitelist: ${error.message}`, "error", 7000);
  }
}

async function loadEntities(showStatusMessage = false) {
  try {
    const data = await fetchJson("/api/entities");
    state.entities = data?.entities || [];
    state.devices = data?.devices || [];
    renderEntities();
    if (showStatusMessage) {
      showStatus("Loaded stored entity data.");
    }
  } catch (error) {
    showStatus(`Failed to load entities: ${error.message}`, "error", 7000);
  }
}

async function ingestEntities() {
  try {
    showStatus("Ingesting entities from Home Assistant…", "info", 0);
    const data = await fetchJson("/api/entities/ingest", { method: "POST", body: "{}" });
    state.entities = data?.entities || [];
    state.devices = data?.devices || [];
    renderEntities();
    showStatus("Entity ingest completed successfully.");
  } catch (error) {
    showStatus(`Entity ingest failed: ${error.message}`, "error", 7000);
  }
}

async function fetchAvailableDomains() {
  try {
    const data = await fetchJson("/api/integrations/available");
    state.availableDomains = (data || []).sort((a, b) => {
      const labelA = (a.title || a.domain || "").toLowerCase();
      const labelB = (b.title || b.domain || "").toLowerCase();
      return labelA.localeCompare(labelB);
    });
    const select = document.getElementById("domain-select");
    if (select) {
      select.innerHTML = "";
      if (!state.availableDomains.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No domains found";
        select.appendChild(option);
        select.disabled = true;
      } else {
        state.availableDomains.forEach((integration) => {
          const option = document.createElement("option");
          option.value = integration.domain;
          option.textContent = `${integration.title || integration.domain}`;
          select.appendChild(option);
        });
        select.disabled = false;
      }
    }
  } catch (error) {
    showStatus(`Failed to load domains from Home Assistant: ${error.message}`, "error", 7000);
    throw error;
  }
}

async function addDomain(domain) {
  try {
    await fetchJson("/api/integrations/selected", {
      method: "POST",
      body: JSON.stringify({ domain }),
    });
    showStatus("Domain added.");
    await loadSelectedDomains();
  } catch (error) {
    showStatus(`Unable to add domain: ${error.message}`, "error", 7000);
    throw error;
  }
}

async function removeDomain(domain) {
  try {
    await fetchJson(`/api/integrations/selected/${encodeURIComponent(domain)}`, {
      method: "DELETE",
    });
    showStatus("Domain removed.");
    await loadSelectedDomains();
  } catch (error) {
    showStatus(`Unable to remove domain: ${error.message}`, "error", 7000);
  }
}

async function addBlacklistEntry(type, id) {
  try {
    await fetchJson("/api/blacklist", {
      method: "POST",
      body: JSON.stringify({ target_type: type, target_id: id }),
    });
    showStatus("Blacklist updated.");
    await loadBlacklist();
  } catch (error) {
    showStatus(`Failed to update blacklist: ${error.message}`, "error", 7000);
  }
}

async function removeBlacklistEntry(type, id) {
  try {
    await fetchJson(`/api/blacklist/${encodeURIComponent(type)}/${encodeURIComponent(id)}`, {
      method: "DELETE",
    });
    showStatus("Blacklist entry removed.");
    await loadBlacklist();
  } catch (error) {
    showStatus(`Failed to remove blacklist entry: ${error.message}`, "error", 7000);
  }
}

async function addWhitelistEntry(id) {
  try {
    await fetchJson("/api/whitelist", {
      method: "POST",
      body: JSON.stringify({ entity_id: id }),
    });
    showStatus("Whitelist updated.");
    await loadWhitelist();
  } catch (error) {
    showStatus(`Failed to update whitelist: ${error.message}`, "error", 7000);
  }
}

async function removeWhitelistEntry(id) {
  try {
    await fetchJson(`/api/whitelist/${encodeURIComponent(id)}`, { method: "DELETE" });
    showStatus("Whitelist entry removed.");
    await loadWhitelist();
  } catch (error) {
    showStatus(`Failed to remove whitelist entry: ${error.message}`, "error", 7000);
  }
}

function setupEventHandlers() {
  document.getElementById("add-domain")?.addEventListener("click", async (event) => {
    const modal = document.getElementById("domain-modal");
    const button = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    try {
      await withButtonLoading(button, () => fetchAvailableDomains(), "Loading…");
      if (modal) {
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
      }
    } catch (error) {
      // Error already handled in fetchAvailableDomains
    }
  });

  document.getElementById("cancel-domain")?.addEventListener("click", () => {
    const modal = document.getElementById("domain-modal");
    if (modal) {
      modal.classList.remove("active");
      modal.setAttribute("aria-hidden", "true");
    }
  });

  document.getElementById("confirm-domain")?.addEventListener("click", async (event) => {
    const select = document.getElementById("domain-select");
    if (!(select instanceof HTMLSelectElement)) return;
    const button = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    const domain = select.value;
    if (!domain) {
      showStatus("Select a domain before adding.", "error", 4000);
      return;
    }
    try {
      await withButtonLoading(button, () => addDomain(domain), "Adding…");
      const modal = document.getElementById("domain-modal");
      if (modal) {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
      }
    } catch (error) {
      // Status already shown
    }
  });

  document.getElementById("refresh-domains")?.addEventListener("click", async (event) => {
    const button = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    await withButtonLoading(button, async () => {
      await loadSelectedDomains();
      showStatus("Domains refreshed.");
    }, "Refreshing…");
  });

  document.querySelector("#domains-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-domain") {
      const domain = target.dataset.id;
      if (domain) {
        void withButtonLoading(target, () => removeDomain(domain), "Removing…");
      }
    }
  });

  document.getElementById("blacklist-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const formData = new FormData(form);
    const type = formData.get("targetType");
    const id = (formData.get("targetId") || "").toString().trim();
    if (!type || !id) {
      showStatus("Provide both target type and ID.", "error", 4000);
      return;
    }
    const submitButton = form.querySelector("button[type='submit']");
    await withButtonLoading(submitButton, async () => {
      await addBlacklistEntry(type.toString(), id);
      form.reset();
    }, "Saving…");
  });

  document.getElementById("whitelist-form")?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const formData = new FormData(form);
    const id = (formData.get("entityId") || "").toString().trim();
    if (!id) {
      showStatus("Provide an entity ID.", "error", 4000);
      return;
    }
    const submitButton = form.querySelector("button[type='submit']");
    await withButtonLoading(submitButton, async () => {
      await addWhitelistEntry(id);
      form.reset();
    }, "Saving…");
  });

  document.querySelector("#blacklist-entities tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-blacklist") {
      const id = target.dataset.id;
      if (id) {
        void withButtonLoading(target, () => removeBlacklistEntry("entity", id), "Removing…");
      }
    }
  });

  document.querySelector("#blacklist-devices tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-blacklist") {
      const id = target.dataset.id;
      if (id) {
        void withButtonLoading(target, () => removeBlacklistEntry("device", id), "Removing…");
      }
    }
  });

  document.querySelector("#whitelist-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-whitelist") {
      const id = target.dataset.id;
      if (id) {
        void withButtonLoading(target, () => removeWhitelistEntry(id), "Removing…");
      }
    }
  });

  document.querySelector("#entities-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof HTMLElement)) return;
    const button = target.closest("button");
    if (!(button instanceof HTMLButtonElement)) return;
    const action = button.dataset.action;
    if (action === "toggle-device") {
      const deviceId = button.dataset.id;
      if (!deviceId) {
        return;
      }
      if (state.expandedDevices.has(deviceId)) {
        state.expandedDevices.delete(deviceId);
      } else {
        state.expandedDevices.add(deviceId);
      }
      renderEntities();
    } else if (action === "blacklist-device") {
      const deviceId = button.dataset.id;
      if (!deviceId) {
        showStatus("Device ID unavailable for blacklist.", "error", 4000);
        return;
      }
      void withButtonLoading(button, () => addBlacklistEntry("device", deviceId), "Adding…");
    } else if (action === "blacklist-entity") {
      const entityId = button.dataset.id;
      if (!entityId) {
        showStatus("Entity ID unavailable for blacklist.", "error", 4000);
        return;
      }
      void withButtonLoading(button, () => addBlacklistEntry("entity", entityId), "Adding…");
    }
  });

  document.getElementById("load-entities")?.addEventListener("click", (event) => {
    const button = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    void withButtonLoading(button, () => loadEntities(true), "Loading…");
  });
  document.getElementById("ingest-entities")?.addEventListener("click", (event) => {
    const button = event.currentTarget instanceof HTMLButtonElement ? event.currentTarget : null;
    void withButtonLoading(button, () => ingestEntities(), "Refreshing…");
  });
}

async function init() {
  setupEventHandlers();
  await Promise.all([
    loadSelectedDomains(),
    loadBlacklist(),
    loadWhitelist(),
    loadEntities(),
  ]);
}

init().catch((error) => {
  showStatus(`Failed to initialise UI: ${error.message}`, "error", 8000);
});
