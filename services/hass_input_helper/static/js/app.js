(() => {
  const state = {
    helpers: [],
    selected: null,
    chart: null,
    toastTimer: null,
  };

  const toastEl = document.getElementById('toast');
  const mqttForm = document.getElementById('mqtt-form');
  const testMqttBtn = document.getElementById('test-mqtt');
  const refreshBtn = document.getElementById('refresh-helpers');
  const entityList = document.getElementById('entity-list');
  const detailCard = document.getElementById('entity-detail-card');
  const detailTitle = document.getElementById('detail-title');
  const detailEntityId = document.getElementById('detail-entity-id');
  const detailLastValue = document.getElementById('detail-last-value');
  const detailUpdated = document.getElementById('detail-updated');
  const deleteBtn = document.getElementById('delete-helper');
  const createForm = document.getElementById('create-helper-form');
  const updateForm = document.getElementById('update-helper-form');
  const valueForm = document.getElementById('value-form');
  const historyCanvas = document.getElementById('history-chart');
  const historyList = document.getElementById('history-list');

  const helperTypeMap = {
    input_text: 'Input text',
    input_number: 'Input number',
    input_boolean: 'Input boolean',
    input_select: 'Input select',
  };

  async function init() {
    mqttForm.addEventListener('submit', handleMqttSubmit);
    testMqttBtn.addEventListener('click', handleMqttTest);
    refreshBtn.addEventListener('click', loadHelpers);
    createForm.addEventListener('submit', handleCreateHelper);
    updateForm.addEventListener('submit', handleUpdateHelper);
    deleteBtn.addEventListener('click', handleDeleteHelper);

    await loadMqttConfig();
    await loadHelpers();
  }

  function showToast(message, type = 'info') {
    toastEl.textContent = message;
    toastEl.classList.remove('hidden', 'success', 'error', 'info', 'visible');
    toastEl.classList.add('visible', type);
    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      toastEl.classList.remove('visible');
    }, 3500);
  }

  async function loadMqttConfig() {
    try {
      const response = await fetch('/config/mqtt');
      if (response.status === 404) {
        mqttForm.reset();
        return;
      }
      if (!response.ok) {
        throw new Error(response.statusText);
      }
      const data = await response.json();
      mqttForm.host.value = data.host || '';
      mqttForm.port.value = data.port ?? 1883;
      mqttForm.username.value = data.username || '';
      mqttForm.password.value = data.password || '';
      mqttForm.client_id.value = data.client_id || '';
      mqttForm.topic_prefix.value = data.topic_prefix || 'homeassistant/input_helper';
      mqttForm.use_tls.checked = Boolean(data.use_tls);
    } catch (error) {
      console.error('Failed to load MQTT config', error);
      showToast(`Unable to load MQTT settings: ${error.message}`, 'error');
    }
  }

  async function handleMqttSubmit(event) {
    event.preventDefault();
    const formData = new FormData(mqttForm);
    const payload = {
      host: formData.get('host')?.trim(),
      port: Number(formData.get('port') || 1883),
      username: formData.get('username')?.trim() || null,
      password: formData.get('password') || null,
      client_id: formData.get('client_id')?.trim() || null,
      topic_prefix: formData.get('topic_prefix')?.trim() || 'homeassistant/input_helper',
      use_tls: formData.get('use_tls') === 'on',
    };

    if (!payload.host) {
      showToast('MQTT host is required.', 'error');
      return;
    }

    try {
      const saved = await requestJson('/config/mqtt', {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      mqttForm.topic_prefix.value = saved.topic_prefix;
      showToast('MQTT configuration saved.', 'success');
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  async function handleMqttTest(event) {
    event?.preventDefault?.();
    const snapshot = {
      host: mqttForm.host.value.trim(),
      port: Number(mqttForm.port.value || 1883),
      use_tls: mqttForm.use_tls.checked,
      username_present: Boolean(mqttForm.username.value.trim()),
      client_id_present: Boolean(mqttForm.client_id.value.trim()),
      topic_prefix: mqttForm.topic_prefix.value.trim() || 'homeassistant/input_helper',
    };

    console.groupCollapsed('MQTT Test');
    console.info('Starting MQTT connection test with configuration', snapshot);

    try {
      await requestJson('/config/mqtt/test', { method: 'POST' });
      console.info('MQTT connection test succeeded.');
      showToast('MQTT connection successful.', 'success');
    } catch (error) {
      console.error('MQTT connection test failed', {
        message: error?.message,
        stack: error?.stack,
        config: snapshot,
      });
      showToast(`MQTT connection failed: ${error.message}`, 'error');
    } finally {
      console.groupEnd?.();
    }
  }

  async function loadHelpers() {
    try {
      const helpers = await requestJson('/inputs');
      state.helpers = helpers;
      renderHelperList();
      if (state.selected) {
        const refreshed = helpers.find((item) => item.slug === state.selected.slug);
        if (refreshed) {
          state.selected = refreshed;
          populateDetail(refreshed);
          await loadHistory(refreshed.slug);
        } else {
          hideDetail();
        }
      }
    } catch (error) {
      showToast(`Failed to load entities: ${error.message}`, 'error');
    }
  }

  function renderHelperList() {
    entityList.innerHTML = '';
    if (!state.helpers.length) {
      const empty = document.createElement('p');
      empty.className = 'card__subtitle';
      empty.textContent = 'No entities created yet.';
      entityList.appendChild(empty);
      return;
    }

    state.helpers.forEach((helper) => {
      const button = document.createElement('button');
      button.type = 'button';
      button.className = 'entity-item';
      if (state.selected?.slug === helper.slug) {
        button.classList.add('active');
      }

      const title = document.createElement('span');
      title.className = 'entity-item__title';
      title.textContent = helper.name;

      const meta = document.createElement('small');
      meta.textContent = helper.helper_type;

      button.append(title, meta);
      button.addEventListener('click', () => selectHelper(helper.slug));
      entityList.appendChild(button);
    });
  }

  async function selectHelper(slug) {
    const helper = state.helpers.find((item) => item.slug === slug);
    if (!helper) {
      showToast('Entity not found.', 'error');
      return;
    }
    state.selected = helper;
    populateDetail(helper);
    await loadHistory(helper.slug);
  }

  function populateDetail(helper) {
    detailCard.classList.remove('hidden');
    detailTitle.textContent = helper.name;
    detailEntityId.textContent = `${helper.entity_id} · ${helper.slug}`;
    updateForm.elements.name.value = helper.name;
    updateForm.elements.entity_id.value = helper.entity_id;
    updateForm.elements.helper_type.value = helperTypeMap[helper.helper_type] || helper.helper_type;
    updateForm.elements.description.value = helper.description ?? '';
    updateForm.elements.default_value.value = helper.default_value ?? '';
    updateForm.elements.device_class.value = helper.device_class ?? '';
    updateForm.elements.unit_of_measurement.value = helper.unit_of_measurement ?? '';

    const optionsField = updateForm.elements.options;
    if (helper.helper_type === 'input_select') {
      optionsField.value = (helper.options || []).join(', ');
      optionsField.disabled = false;
    } else {
      optionsField.value = '';
      optionsField.disabled = true;
    }

    detailLastValue.textContent = helper.last_value ?? '—';
    detailUpdated.textContent = helper.updated_at ? formatTimestamp(helper.updated_at) : '—';

    renderValueInput(helper);
  }

  function hideDetail() {
    detailCard.classList.add('hidden');
    state.selected = null;
    updateForm.reset();
    valueForm.innerHTML = '';
    historyCanvas.classList.remove('hidden');
    historyList.classList.add('hidden');
    historyList.innerHTML = '';
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
  }

  async function handleCreateHelper(event) {
    event.preventDefault();
    const formData = new FormData(createForm);
    const helperType = formData.get('helper_type');

    try {
      const payload = buildCreatePayload(formData);
      await requestJson('/inputs', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      createForm.reset();
      showToast('Entity created.', 'success');
      await loadHelpers();
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  function buildCreatePayload(formData) {
    const helperType = formData.get('helper_type');
    const name = formData.get('name')?.trim();
    const entityId = formData.get('entity_id')?.trim();
    const description = formData.get('description')?.trim();
    const defaultRaw = formData.get('default_value')?.trim();
    const optionsRaw = formData.get('options')?.trim();
    const deviceClass = formData.get('device_class')?.trim();
    const unit = formData.get('unit_of_measurement')?.trim();

    const payload = {
      name,
      entity_id: entityId,
      helper_type: helperType,
    };

    if (description) payload.description = description;
    if (defaultRaw) payload.default_value = coerceValue(helperType, defaultRaw);

    if (helperType === 'input_select') {
      const options = (optionsRaw || '')
        .split(',')
        .map((item) => item.trim())
        .filter(Boolean);
      if (options.length) {
        payload.options = options;
      }
    }

    if (deviceClass) payload.device_class = deviceClass;
    if (unit) payload.unit_of_measurement = unit;

    return payload;
  }

  async function handleUpdateHelper(event) {
    event.preventDefault();
    if (!state.selected) {
      showToast('Select an entity to edit.', 'error');
      return;
    }

    const formData = new FormData(updateForm);
    const helperType = state.selected.helper_type;

    try {
      const payload = buildUpdatePayload(formData, helperType);
      const updated = await requestJson(`/inputs/${state.selected.slug}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('Entity updated.', 'success');
      state.helpers = state.helpers.map((item) =>
        item.slug === updated.slug ? updated : item,
      );
      state.selected = updated;
      populateDetail(updated);
      renderHelperList();
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  function buildUpdatePayload(formData, helperType) {
    const payload = {
      name: formData.get('name')?.trim(),
      entity_id: formData.get('entity_id')?.trim(),
      description: formData.get('description')?.trim() || null,
      default_value: null,
      device_class: formData.get('device_class')?.trim() || null,
      unit_of_measurement: formData.get('unit_of_measurement')?.trim() || null,
    };

    const defaultRaw = formData.get('default_value')?.trim();
    if (defaultRaw) {
      payload.default_value = coerceValue(helperType, defaultRaw);
    }

    if (helperType === 'input_select') {
      const optionsRaw = formData.get('options')?.trim();
      if (optionsRaw) {
        payload.options = optionsRaw
          .split(',')
          .map((item) => item.trim())
          .filter(Boolean);
      }
    }

    return payload;
  }

  async function handleDeleteHelper() {
    if (!state.selected) {
      showToast('Select an entity to delete.', 'error');
      return;
    }

    const confirmed = window.confirm(
      `Delete ${state.selected.name}? This action cannot be undone.`,
    );
    if (!confirmed) {
      return;
    }

    try {
      await requestJson(`/inputs/${state.selected.slug}`, { method: 'DELETE' });
      showToast('Entity deleted.', 'success');
      state.helpers = state.helpers.filter((item) => item.slug !== state.selected.slug);
      hideDetail();
      renderHelperList();
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  function renderValueInput(helper) {
    valueForm.innerHTML = '';
    const field = document.createElement('label');
    field.className = 'form-field';
    field.innerHTML = '<span>Value</span>';

    let input;
    if (helper.helper_type === 'input_boolean') {
      input = document.createElement('select');
      input.name = 'value';
      const trueOption = document.createElement('option');
      trueOption.value = 'true';
      trueOption.textContent = 'On';
      const falseOption = document.createElement('option');
      falseOption.value = 'false';
      falseOption.textContent = 'Off';
      input.append(falseOption, trueOption);
      if (helper.last_value === true) {
        input.value = 'true';
      } else if (helper.last_value === false) {
        input.value = 'false';
      }
    } else if (helper.helper_type === 'input_number') {
      input = document.createElement('input');
      input.type = 'number';
      input.name = 'value';
      if (helper.unit_of_measurement) {
        input.placeholder = `Enter value in ${helper.unit_of_measurement}`;
      }
      if (typeof helper.last_value === 'number') {
        input.value = helper.last_value;
      }
    } else if (helper.helper_type === 'input_select') {
      input = document.createElement('select');
      input.name = 'value';
      (helper.options || []).forEach((option) => {
        const optionEl = document.createElement('option');
        optionEl.value = option;
        optionEl.textContent = option;
        input.appendChild(optionEl);
      });
      if (helper.last_value) {
        input.value = helper.last_value;
      }
    } else {
      input = document.createElement('input');
      input.type = 'text';
      input.name = 'value';
      if (helper.last_value) {
        input.value = helper.last_value;
      }
    }

    field.appendChild(input);

    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'btn primary';
    submit.textContent = 'Publish to MQTT';

    valueForm.append(field, submit);
    valueForm.removeEventListener('submit', handleValueSubmit);
    valueForm.addEventListener('submit', handleValueSubmit);
  }

  async function handleValueSubmit(event) {
    event.preventDefault();
    if (!state.selected) {
      showToast('Select an entity to update.', 'error');
      return;
    }

    const helper = state.selected;
    const valueInput = valueForm.querySelector('[name="value"]');
    const rawValue = valueInput.value;

    try {
      const payload = { value: coerceValue(helper.helper_type, rawValue) };
      const updated = await requestJson(`/inputs/${helper.slug}/set`, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      showToast('Value sent to MQTT.', 'success');
      state.selected = updated;
      state.helpers = state.helpers.map((item) =>
        item.slug === updated.slug ? updated : item,
      );
      populateDetail(updated);
      renderHelperList();
      await loadHistory(updated.slug);
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  async function loadHistory(slug) {
    try {
      const history = await requestJson(`/inputs/${slug}/history`);
      renderHistory(state.selected, history || []);
    } catch (error) {
      showToast(`Failed to load history: ${error.message}`, 'error');
    }
  }

  function renderHistory(helper, history) {
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }

    if (!history.length) {
      historyCanvas.classList.add('hidden');
      historyList.classList.remove('hidden');
      historyList.innerHTML = '<li><span>No values yet</span><span>—</span></li>';
      return;
    }

    const labels = history.map((item) => formatTimestamp(item.timestamp));
    const numericValues = history.map((item) => normalizeHistoryValue(helper.helper_type, item.value));
    const allNumeric = numericValues.every((value) => value !== null && !Number.isNaN(value));

    if (allNumeric) {
      historyCanvas.classList.remove('hidden');
      historyList.classList.add('hidden');
      const dataset = numericValues.map((value) => Number(value));

      const yTicks = helper.helper_type === 'input_boolean'
        ? {
            callback: (value) => (value === 1 ? 'On' : 'Off'),
            max: 1,
            min: 0,
            stepSize: 1,
          }
        : {};

      state.chart = new Chart(historyCanvas, {
        type: 'line',
        data: {
          labels,
          datasets: [
            {
              label: helper.name,
              data: dataset,
              fill: false,
              borderColor: '#2563eb',
              backgroundColor: 'rgba(37, 99, 235, 0.15)',
              tension: 0.25,
            },
          ],
        },
        options: {
          responsive: true,
          scales: {
            y: {
              beginAtZero: helper.helper_type !== 'input_number' ? true : false,
              ...yTicks,
            },
          },
          plugins: {
            legend: { display: false },
          },
        },
      });
      return;
    }

    historyCanvas.classList.add('hidden');
    historyList.classList.remove('hidden');
    historyList.innerHTML = '';
    history.forEach((item) => {
      const li = document.createElement('li');
      const label = document.createElement('span');
      label.textContent = formatTimestamp(item.timestamp);
      const value = document.createElement('span');
      value.textContent = String(item.value);
      li.append(label, value);
      historyList.appendChild(li);
    });
  }

  function normalizeHistoryValue(helperType, value) {
    if (value === null || value === undefined) {
      return null;
    }
    if (helperType === 'input_boolean') {
      if (value === true || value === 'true' || value === 'on') return 1;
      if (value === false || value === 'false' || value === 'off') return 0;
      return null;
    }
    if (helperType === 'input_number') {
      const numberValue = Number(value);
      return Number.isFinite(numberValue) ? numberValue : null;
    }
    return null;
  }

  function coerceValue(helperType, rawValue) {
    if (rawValue === null || rawValue === undefined) {
      return null;
    }
    if (helperType === 'input_boolean') {
      const normalized = String(rawValue).toLowerCase();
      if (['true', 'on', '1', 'yes'].includes(normalized)) return true;
      if (['false', 'off', '0', 'no'].includes(normalized)) return false;
      throw new Error('Boolean helpers expect true/false values.');
    }
    if (helperType === 'input_number') {
      const parsed = Number(rawValue);
      if (Number.isNaN(parsed)) {
        throw new Error('Number helpers expect numeric values.');
      }
      return parsed;
    }
    return rawValue;
  }

  function formatTimestamp(value) {
    try {
      const date = new Date(value);
      if (Number.isNaN(date.getTime())) {
        return String(value);
      }
      return date.toLocaleString();
    } catch (error) {
      return String(value);
    }
  }

  async function requestJson(url, options = {}) {
    const defaultHeaders = { 'Content-Type': 'application/json' };
    const method = options?.method || 'GET';
    const hasBody = Boolean(options?.body);
    console.debug('requestJson -> sending request', { url, method, hasBody });

    const response = await fetch(url, {
      headers: defaultHeaders,
      ...options,
    });

    console.debug('requestJson <- received response', {
      url,
      method,
      status: response.status,
      ok: response.ok,
      contentType: response.headers.get('content-type'),
    });

    if (response.status === 204) {
      return null;
    }

    const contentType = response.headers.get('content-type') || '';
    const isJson = contentType.includes('application/json');

    if (!response.ok) {
      console.warn('requestJson !ok response', { url, method, status: response.status });
      let message = response.statusText;
      if (isJson) {
        const data = await response.json();
        message = data?.detail || data?.message || message;
      }
      console.debug('requestJson error payload', { url, method, message });
      throw new Error(message);
    }

    if (!isJson) {
      return null;
    }

    return response.json();
  }

  document.addEventListener('DOMContentLoaded', init);
})();
