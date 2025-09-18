const statusEl = document.getElementById("status");
let statusTimer;

const state = {
  selectedDomains: [],
  availableDomains: [],
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
  document.getElementById("add-domain")?.addEventListener("click", async () => {
    const modal = document.getElementById("domain-modal");
    try {
      await fetchAvailableDomains();
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

  document.getElementById("confirm-domain")?.addEventListener("click", async () => {
    const select = document.getElementById("domain-select");
    if (!(select instanceof HTMLSelectElement)) return;
    const domain = select.value;
    if (!domain) {
      showStatus("Select a domain before adding.", "error", 4000);
      return;
    }
    try {
      await addDomain(domain);
      const modal = document.getElementById("domain-modal");
      if (modal) {
        modal.classList.remove("active");
        modal.setAttribute("aria-hidden", "true");
      }
    } catch (error) {
      // Status already shown
    }
  });

  document.getElementById("refresh-domains")?.addEventListener("click", async () => {
    await loadSelectedDomains();
    showStatus("Domains refreshed.");
  });

  document.querySelector("#domains-table tbody")?.addEventListener("click", (event) => {
    const target = event.target;
    if (target instanceof HTMLButtonElement && target.dataset.action === "remove-domain") {
      const domain = target.dataset.id;
      if (domain) {
        removeDomain(domain);
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
    loadSelectedDomains(),
    loadBlacklist(),
    loadWhitelist(),
    loadEntities(),
  ]);
}

init().catch((error) => {
  showStatus(`Failed to initialise UI: ${error.message}`, "error", 8000);
});
