const statusEl = document.getElementById("status");
let statusTimer;

const state = {
  selectedIntegrations: [],
  availableIntegrations: [],
  blacklist: { entities: [], devices: [] },
  whitelist: [],
  entities: [],
  devices: [],
};

function showStatus(message, type = "info", timeout = 5000) {
  if (!statusEl) return;
  clearTimeout(statusTimer);
  statusEl.textContent = message;
  statusEl.classList.toggle("error", type === "error");
  statusEl.hidden = false;
  if (timeout > 0) {
    statusTimer = setTimeout(() => {
      statusEl.hidden = true;
    }, timeout);
  }
}

function hideStatus() {
  if (!statusEl) return;
  clearTimeout(statusTimer);
  statusEl.hidden = true;
}

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

function renderSelectedIntegrations() {
  const tbody = document.querySelector("#integrations-table tbody");
  if (!tbody) return;
  tbody.innerHTML = "";
  if (!state.selectedIntegrations.length) {
    const row = document.createElement("tr");
    row.innerHTML = '<td colspan="4" data-label="Message">No integrations selected.</td>';
    tbody.appendChild(row);
    return;
  }
  state.selectedIntegrations.forEach((entry) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td data-label="Title">${entry.title || "Unknown"}</td>
      <td data-label="Domain">${entry.domain || ""}</td>
      <td data-label="Entry ID">${entry.entry_id}</td>
      <td class="actions">
        <button class="danger" data-action="remove-integration" data-id="${entry.entry_id}">Remove</button>
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
  const deviceBody = document.querySelector("#devices-table tbody");
  const deviceCount = document.getElementById("device-count");

  if (entityBody) {
    entityBody.innerHTML = "";
    if (!state.entities.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="6" data-label="Message">No entities ingested yet.</td>';
      entityBody.appendChild(row);
    } else {
      state.entities.forEach((entity) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td data-label="Entity ID">${entity.entity_id}</td>
          <td data-label="Name">${entity.name || entity.original_name || ""}</td>
          <td data-label="State">${entity.state ?? ""}</td>
          <td data-label="Device ID">${entity.device_id ?? ""}</td>
          <td data-label="Area">${entity.area_id ?? ""}</td>
          <td data-label="Integration">${entity.integration_id ?? ""}</td>
        `;
        entityBody.appendChild(row);
      });
    }
  }
  if (entityCount) {
    entityCount.textContent = `${state.entities.length} entities`;
  }

  if (deviceBody) {
    deviceBody.innerHTML = "";
    if (!state.devices.length) {
      const row = document.createElement("tr");
      row.innerHTML = '<td colspan="5" data-label="Message">No devices ingested yet.</td>';
      deviceBody.appendChild(row);
    } else {
      state.devices.forEach((device) => {
        const row = document.createElement("tr");
        row.innerHTML = `
          <td data-label="Device ID">${device.id}</td>
          <td data-label="Name">${device.name || device.name_by_user || ""}</td>
          <td data-label="Manufacturer">${device.manufacturer || ""}</td>
          <td data-label="Model">${device.model || ""}</td>
          <td data-label="Area">${device.area_id || ""}</td>
        `;
        deviceBody.appendChild(row);
      });
    }
  }
  if (deviceCount) {
    deviceCount.textContent = `${state.devices.length} devices`;
  }
}

async function loadSelectedIntegrations() {
  try {
    const data = await fetchJson("/api/integrations/selected");
    state.selectedIntegrations = data || [];
    renderSelectedIntegrations();
  } catch (error) {
    showStatus(`Failed to load selected integrations: ${error.message}`, "error", 7000);
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

async function fetchAvailableIntegrations() {
  try {
    const data = await fetchJson("/api/integrations/available");
    state.availableIntegrations = data || [];
    const select = document.getElementById("integration-select");
    if (select) {
      select.innerHTML = "";
      if (!state.availableIntegrations.length) {
        const option = document.createElement("option");
        option.value = "";
        option.textContent = "No integrations found";
        select.appendChild(option);
        select.disabled = true;
      } else {
        state.availableIntegrations.forEach((integration) => {
          const option = document.createElement("option");
          option.value = integration.entry_id;
          option.textContent = `${integration.title || integration.domain || integration.entry_id}`;
          select.appendChild(option);
        });
        select.disabled = false;
      }
    }
  } catch (error) {
    showStatus(`Failed to load integrations from Home Assistant: ${error.message}`, "error", 7000);
    throw error;
  }
}

async function addIntegration(entryId) {
  try {
    await fetchJson("/api/integrations/selected", {
      method: "POST",
      body: JSON.stringify({ integration_id: entryId }),
    });
    showStatus("Integration added.");
    await loadSelectedIntegrations();
  } catch (error) {
    showStatus(`Unable to add integration: ${error.message}`, "error", 7000);
    throw error;
  }
}

async function removeIntegration(entryId) {
  try {
    await fetchJson(`/api/integrations/selected/${encodeURIComponent(entryId)}`, {
      method: "DELETE",
    });
    showStatus("Integration removed.");
    await loadSelectedIntegrations();
  } catch (error) {
    showStatus(`Unable to remove integration: ${error.message}`, "error", 7000);
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
  document.getElementById("add-integration")?.addEventListener("click", async () => {
    const modal = document.getElementById("integration-modal");
    try {
      await fetchAvailableIntegrations();
      if (modal) {
        modal.classList.add("active");
        modal.setAttribute("aria-hidden", "false");
      }
    } catch (error) {
      // Error already handled in fetchAvailableIntegrations
    }
  });

  document.getElementById("cancel-integration")?.addEventListener("click", () => {
    const modal = document.getElementById("integration-modal");
    if (modal) {
      modal.classList.remove("active");
      modal.setAttribute("aria-hidden", "true");
    }
  });

  document.getElementById("confirm-integration")?.addEventListener("click", async () => {
    const select = document.getElementById("integration-select");
    if (!(select instanceof HTMLSelectElement)) return;
    const entryId = select.value;
    if (!entryId) {
      showStatus("Select an integration before adding.", "error", 4000);
      return;
    }
    try {
      await addIntegration(entryId);
      const modal = document.getElementById("integration-modal");
      if (modal) {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
      }
    } catch (error) {
      // Status already shown
    }
  });

  document.getElementById("refresh-integrations")?.addEventListener("click", async () => {
    await loadSelectedIntegrations();
    showStatus("Integrations refreshed.");
  });

  document.querySelector("#integrations-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-integration") {
      const entryId = target.dataset.id;
      if (entryId) {
        removeIntegration(entryId);
      }
    }
  });

  document.getElementById("blacklist-form")?.addEventListener("submit", (event) => {
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
    addBlacklistEntry(type.toString(), id).then(() => form.reset());
  });

  document.getElementById("whitelist-form")?.addEventListener("submit", (event) => {
    event.preventDefault();
    const form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    const formData = new FormData(form);
    const id = (formData.get("entityId") || "").toString().trim();
    if (!id) {
      showStatus("Provide an entity ID.", "error", 4000);
      return;
    }
    addWhitelistEntry(id).then(() => form.reset());
  });

  document.querySelector("#blacklist-entities tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-blacklist") {
      const id = target.dataset.id;
      if (id) {
        removeBlacklistEntry("entity", id);
      }
    }
  });

  document.querySelector("#blacklist-devices tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-blacklist") {
      const id = target.dataset.id;
      if (id) {
        removeBlacklistEntry("device", id);
      }
    }
  });

  document.querySelector("#whitelist-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-whitelist") {
      const id = target.dataset.id;
      if (id) {
        removeWhitelistEntry(id);
      }
    }
  });

  document.getElementById("load-entities")?.addEventListener("click", () => loadEntities(true));
  document.getElementById("ingest-entities")?.addEventListener("click", () => ingestEntities());
}

async function init() {
  setupEventHandlers();
  await Promise.all([
    loadSelectedIntegrations(),
    loadBlacklist(),
    loadWhitelist(),
    loadEntities(),
  ]);
}

init().catch((error) => {
  showStatus(`Failed to initialise UI: ${error.message}`, "error", 8000);
});
