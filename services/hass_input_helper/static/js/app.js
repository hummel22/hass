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

  const DEVICE_CLASS_OPTIONS = [
    { value: '', label: 'None' },
    { value: 'apparent_power', label: 'Apparent power' },
    { value: 'aqi', label: 'Air quality index' },
    { value: 'atmospheric_pressure', label: 'Atmospheric pressure' },
    { value: 'battery', label: 'Battery' },
    { value: 'carbon_dioxide', label: 'Carbon dioxide' },
    { value: 'carbon_monoxide', label: 'Carbon monoxide' },
    { value: 'cold', label: 'Cold (binary)' },
    { value: 'connectivity', label: 'Connectivity' },
    { value: 'concentration', label: 'Concentration' },
    { value: 'conductivity', label: 'Conductivity' },
    { value: 'consumption', label: 'Consumption' },
    { value: 'current', label: 'Current' },
    { value: 'data_rate', label: 'Data rate' },
    { value: 'data_size', label: 'Data size' },
    { value: 'date', label: 'Date' },
    { value: 'distance', label: 'Distance' },
    { value: 'door', label: 'Door (binary)' },
    { value: 'duration', label: 'Duration' },
    { value: 'enum', label: 'Enum' },
    { value: 'energy', label: 'Energy' },
    { value: 'energy_storage', label: 'Energy storage' },
    { value: 'frequency', label: 'Frequency' },
    { value: 'gas', label: 'Gas' },
    { value: 'garage_door', label: 'Garage door (binary)' },
    { value: 'heat', label: 'Heat (binary)' },
    { value: 'humidity', label: 'Humidity' },
    { value: 'illuminance', label: 'Illuminance' },
    { value: 'irradiance', label: 'Irradiance' },
    { value: 'light', label: 'Light (binary)' },
    { value: 'lock', label: 'Lock (binary)' },
    { value: 'monetary', label: 'Monetary' },
    { value: 'moisture', label: 'Moisture (binary)' },
    { value: 'motion', label: 'Motion (binary)' },
    { value: 'moving', label: 'Moving (binary)' },
    { value: 'nitrogen_dioxide', label: 'Nitrogen dioxide' },
    { value: 'nitrogen_monoxide', label: 'Nitrogen monoxide' },
    { value: 'nitrous_oxide', label: 'Nitrous oxide' },
    { value: 'occupancy', label: 'Occupancy (binary)' },
    { value: 'opening', label: 'Opening (binary)' },
    { value: 'ozone', label: 'Ozone' },
    { value: 'pm1', label: 'Particulate matter 1µm' },
    { value: 'pm10', label: 'Particulate matter 10µm' },
    { value: 'pm25', label: 'Particulate matter 2.5µm' },
    { value: 'plug', label: 'Plug (binary)' },
    { value: 'power', label: 'Power' },
    { value: 'power_factor', label: 'Power factor' },
    { value: 'precipitation', label: 'Precipitation' },
    { value: 'precipitation_intensity', label: 'Precipitation intensity' },
    { value: 'pressure', label: 'Pressure' },
    { value: 'presence', label: 'Presence (binary)' },
    { value: 'problem', label: 'Problem (binary)' },
    { value: 'reactive_power', label: 'Reactive power' },
    { value: 'running', label: 'Running (binary)' },
    { value: 'safety', label: 'Safety (binary)' },
    { value: 'signal_strength', label: 'Signal strength' },
    { value: 'smoke', label: 'Smoke (binary)' },
    { value: 'sound', label: 'Sound (binary)' },
    { value: 'sound_pressure', label: 'Sound pressure' },
    { value: 'speed', label: 'Speed' },
    { value: 'sulphur_dioxide', label: 'Sulphur dioxide' },
    { value: 'tamper', label: 'Tamper (binary)' },
    { value: 'temperature', label: 'Temperature' },
    { value: 'timestamp', label: 'Timestamp' },
    { value: 'update', label: 'Update (binary)' },
    { value: 'uv_index', label: 'UV index' },
    { value: 'vibration', label: 'Vibration (binary)' },
    { value: 'volatile_organic_compounds', label: 'VOC' },
    { value: 'volatile_organic_compounds_parts', label: 'VOC parts' },
    { value: 'voltage', label: 'Voltage' },
    { value: 'volume', label: 'Volume' },
    { value: 'volume_flow_rate', label: 'Volume flow rate' },
    { value: 'water', label: 'Water' },
    { value: 'weight', label: 'Weight' },
    { value: 'wind_speed', label: 'Wind speed' },
    { value: 'window', label: 'Window (binary)' },
  ];

  const UNIT_OPTIONS = [
    { value: '', label: 'None' },
    { value: '%', label: 'Percent (%)' },
    { value: '°C', label: 'Degrees Celsius (°C)' },
    { value: '°F', label: 'Degrees Fahrenheit (°F)' },
    { value: 'K', label: 'Kelvin (K)' },
    { value: 'A', label: 'Amperes (A)' },
    { value: 'mA', label: 'Milliamperes (mA)' },
    { value: 'µA', label: 'Microamperes (µA)' },
    { value: 'V', label: 'Volts (V)' },
    { value: 'W', label: 'Watts (W)' },
    { value: 'kW', label: 'Kilowatts (kW)' },
    { value: 'MW', label: 'Megawatts (MW)' },
    { value: 'Wh', label: 'Watt hours (Wh)' },
    { value: 'kWh', label: 'Kilowatt hours (kWh)' },
    { value: 'VA', label: 'Volt-ampere (VA)' },
    { value: 'var', label: 'Volt-ampere reactive (var)' },
    { value: 'Hz', label: 'Hertz (Hz)' },
    { value: 'lx', label: 'Lux (lx)' },
    { value: 'lm', label: 'Lumens (lm)' },
    { value: 'dB', label: 'Decibels (dB)' },
    { value: 'ppm', label: 'Parts per million (ppm)' },
    { value: 'ppb', label: 'Parts per billion (ppb)' },
    { value: 'µg/m³', label: 'Micrograms per cubic meter (µg/m³)' },
    { value: 'mg/m³', label: 'Milligrams per cubic meter (mg/m³)' },
    { value: 'mg/L', label: 'Milligrams per litre (mg/L)' },
    { value: 'µg/L', label: 'Micrograms per litre (µg/L)' },
    { value: 'm³', label: 'Cubic meters (m³)' },
    { value: 'm³/h', label: 'Cubic meters per hour (m³/h)' },
    { value: 'L', label: 'Litres (L)' },
    { value: 'gal', label: 'Gallons (gal)' },
    { value: 'm', label: 'Meters (m)' },
    { value: 'cm', label: 'Centimeters (cm)' },
    { value: 'mm', label: 'Millimeters (mm)' },
    { value: 'in', label: 'Inches (in)' },
    { value: 'ft', label: 'Feet (ft)' },
    { value: 'km', label: 'Kilometers (km)' },
    { value: 'mi', label: 'Miles (mi)' },
    { value: 'nm', label: 'Nautical miles (nm)' },
    { value: 's', label: 'Seconds (s)' },
    { value: 'min', label: 'Minutes (min)' },
    { value: 'h', label: 'Hours (h)' },
    { value: 'd', label: 'Days (d)' },
    { value: '°', label: 'Degrees (°)' },
    { value: '°/s', label: 'Degrees per second (°/s)' },
    { value: 'm/s', label: 'Meters per second (m/s)' },
    { value: 'km/h', label: 'Kilometers per hour (km/h)' },
    { value: 'mph', label: 'Miles per hour (mph)' },
    { value: 'kt', label: 'Knots (kt)' },
    { value: 'Pa', label: 'Pascal (Pa)' },
    { value: 'hPa', label: 'Hectopascal (hPa)' },
    { value: 'kPa', label: 'Kilopascal (kPa)' },
    { value: 'bar', label: 'Bar' },
    { value: 'psi', label: 'Pounds per square inch (psi)' },
    { value: 'mbar', label: 'Millibar (mbar)' },
    { value: 'mmHg', label: 'Millimeters of mercury (mmHg)' },
    { value: 'inHg', label: 'Inches of mercury (inHg)' },
    { value: '°Bx', label: 'Degrees Brix (°Bx)' },
    { value: 'g', label: 'Grams (g)' },
    { value: 'kg', label: 'Kilograms (kg)' },
    { value: 'lb', label: 'Pounds (lb)' },
    { value: 'oz', label: 'Ounces (oz)' },
  ];

  async function init() {
    mqttForm.addEventListener('submit', handleMqttSubmit);
    testMqttBtn.addEventListener('click', handleMqttTest);
    refreshBtn.addEventListener('click', loadHelpers);
    createForm.addEventListener('submit', handleCreateHelper);
    updateForm.addEventListener('submit', handleUpdateHelper);
    deleteBtn.addEventListener('click', handleDeleteHelper);

    populateSelectControls();
    await loadMqttConfig();
    await loadHelpers();
  }

  function populateSelectControls() {
    const deviceSelects = document.querySelectorAll('select[name="device_class"]');
    const unitSelects = document.querySelectorAll('select[name="unit_of_measurement"]');

    deviceSelects.forEach((select) => populateSelect(select, DEVICE_CLASS_OPTIONS));
    unitSelects.forEach((select) => populateSelect(select, UNIT_OPTIONS));
  }

  function populateSelect(select, options) {
    select.innerHTML = '';
    options.forEach((option) => {
      const opt = document.createElement('option');
      opt.value = option.value;
      opt.textContent = option.label;
      select.appendChild(opt);
    });
  }

  function setSelectValue(select, value) {
    const normalized = value ?? '';
    if (![...select.options].some((option) => option.value === normalized)) {
      const opt = document.createElement('option');
      opt.value = normalized;
      opt.textContent = normalized || 'None';
      select.appendChild(opt);
    }
    select.value = normalized;
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
    setSelectValue(updateForm.elements.device_class, helper.device_class ?? '');
    setSelectValue(updateForm.elements.unit_of_measurement, helper.unit_of_measurement ?? '');

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
