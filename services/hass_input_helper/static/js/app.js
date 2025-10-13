(() => {
  const state = {
    helpers: [],
    selected: null,
    chart: null,
    toastTimer: null,
    mqttConfig: null,
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
  const detailMeasuredAt = document.getElementById('detail-measured-at');
  const detailUpdated = document.getElementById('detail-updated');
  const detailComponent = document.getElementById('detail-component');
  const detailDiscoveryTopic = document.getElementById('detail-discovery-topic');
  const detailStateTopic = document.getElementById('detail-state-topic');
  const detailAvailabilityTopic = document.getElementById('detail-availability-topic');
  const deleteBtn = document.getElementById('delete-helper');
  const createForm = document.getElementById('create-helper-form');
  const updateForm = document.getElementById('update-helper-form');
  const valueForm = document.getElementById('value-form');
  const historyCanvas = document.getElementById('history-chart');
  const historyList = document.getElementById('history-list');

  const createTypeSelect = createForm?.elements.namedItem('type');
  const createNameInput = createForm?.elements.namedItem('name');
  const createEntityInput = createForm?.elements.namedItem('entity_id');
  const createDeviceNameInput = createForm?.elements.namedItem('device_name');
  const createUniqueInput = createForm?.elements.namedItem('unique_id');
  const createObjectInput = createForm?.elements.namedItem('object_id');
  const createNodeInput = createForm?.elements.namedItem('node_id');
  const createStateTopicInput = createForm?.elements.namedItem('state_topic');
  const createAvailabilityInput = createForm?.elements.namedItem('availability_topic');

  const createAutoFlags = {
    entityId: true,
    uniqueId: true,
    objectId: true,
    stateTopic: true,
    availabilityTopic: true,
  };

  const helperTypeMap = {
    input_text: 'Input text',
    input_number: 'Input number',
    input_boolean: 'Input boolean',
    input_select: 'Input select',
  };

  function slugifyIdentifier(value) {
    if (!value) return '';
    const normalized = value
      .toString()
      .toLowerCase()
      .trim()
      .replace(/[^a-z0-9]+/g, '_')
      .replace(/_+/g, '_')
      .replace(/^_+|_+$/g, '');
    return normalized;
  }

  function buildStateTopic(nodeId, objectId) {
    const node = slugifyIdentifier(nodeId) || 'hassems';
    const object = slugifyIdentifier(objectId);
    if (!object) return '';
    return `${node}/${object}/state`;
  }

  function buildAvailabilityTopic(nodeId, objectId) {
    const node = slugifyIdentifier(nodeId) || 'hassems';
    const object = slugifyIdentifier(objectId);
    if (!object) return '';
    return `${node}/${object}/availability`;
  }

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

  const COMPONENT_OPTIONS = [
    { value: 'sensor', label: 'Sensor' },
    { value: 'binary_sensor', label: 'Binary sensor' },
    { value: 'number', label: 'Number' },
    { value: 'switch', label: 'Switch' },
    { value: 'select', label: 'Select' },
    { value: 'text', label: 'Text' },
    { value: 'button', label: 'Button' },
  ];

  const STATE_CLASS_OPTIONS = [
    { value: '', label: 'None' },
    { value: 'measurement', label: 'Measurement' },
    { value: 'total', label: 'Total' },
    { value: 'total_increasing', label: 'Total increasing' },
  ];

  async function init() {
    mqttForm.addEventListener('submit', handleMqttSubmit);
    testMqttBtn.addEventListener('click', handleMqttTest);
    refreshBtn.addEventListener('click', loadHelpers);
    createForm.addEventListener('submit', handleCreateHelper);
    updateForm.addEventListener('submit', handleUpdateHelper);
    deleteBtn.addEventListener('click', handleDeleteHelper);

    if (createTypeSelect) {
      createTypeSelect.addEventListener('change', (event) => {
        handleCreateTypeChange(event);
        syncCreateAutofill();
      });
    }
    if (createNameInput) {
      createNameInput.addEventListener('input', () => {
        syncCreateAutofill();
      });
    }
    if (createEntityInput) {
      createEntityInput.addEventListener('input', () => {
        createAutoFlags.entityId = false;
      });
    }
    if (createUniqueInput) {
      createUniqueInput.addEventListener('input', () => {
        createAutoFlags.uniqueId = false;
        if (createAutoFlags.objectId && createObjectInput) {
          createObjectInput.value = slugifyIdentifier(createUniqueInput.value);
        }
      });
      createUniqueInput.addEventListener('blur', () => {
        createUniqueInput.value = slugifyIdentifier(createUniqueInput.value);
        if (createAutoFlags.objectId && createObjectInput) {
          createObjectInput.value = slugifyIdentifier(createUniqueInput.value);
        }
        syncCreateAutofill();
      });
    }
    if (createObjectInput) {
      createObjectInput.addEventListener('input', () => {
        createAutoFlags.objectId = false;
      });
      createObjectInput.addEventListener('blur', () => {
        createObjectInput.value = slugifyIdentifier(createObjectInput.value);
        syncCreateAutofill();
      });
    }
    if (createNodeInput) {
      createNodeInput.addEventListener('input', () => {
        if (createAutoFlags.stateTopic || createAutoFlags.availabilityTopic) {
          syncCreateAutofill();
        }
      });
      createNodeInput.addEventListener('blur', () => {
        const cleaned = slugifyIdentifier(createNodeInput.value) || 'hassems';
        createNodeInput.value = cleaned;
        syncCreateAutofill();
      });
    }
    if (createStateTopicInput) {
      createStateTopicInput.addEventListener('input', () => {
        createAutoFlags.stateTopic = false;
      });
    }
    if (createAvailabilityInput) {
      createAvailabilityInput.addEventListener('input', () => {
        createAutoFlags.availabilityTopic = false;
      });
    }
    if (createDeviceNameInput) {
      createDeviceNameInput.addEventListener('input', () => {
        syncCreateAutofill();
      });
    }

    populateSelectControls();
    await loadMqttConfig();
    await loadHelpers();
  }

  function populateSelectControls() {
    const deviceSelects = document.querySelectorAll('select[name="device_class"]');
    const unitSelects = document.querySelectorAll('select[name="unit_of_measurement"]');
    const componentSelects = document.querySelectorAll('select[name="component"]');
    const stateClassSelects = document.querySelectorAll('select[name="state_class"]');

    deviceSelects.forEach((select) => populateSelect(select, DEVICE_CLASS_OPTIONS));
    unitSelects.forEach((select) => populateSelect(select, UNIT_OPTIONS));
    componentSelects.forEach((select) => populateSelect(select, COMPONENT_OPTIONS));
    stateClassSelects.forEach((select) => populateSelect(select, STATE_CLASS_OPTIONS));
    setCreateDefaults();
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

  function resetCreateAutofillFlags() {
    createAutoFlags.entityId = true;
    createAutoFlags.uniqueId = true;
    createAutoFlags.objectId = true;
    createAutoFlags.stateTopic = true;
    createAutoFlags.availabilityTopic = true;
  }

  function syncCreateAutofill() {
    if (!createForm) return;
    const nameValue = createNameInput?.value ?? '';
    const typeValue = createTypeSelect?.value ?? '';
    const nameSlug = slugifyIdentifier(nameValue);
    const deviceNameValue = createDeviceNameInput?.value ?? '';
    const deviceSlug = slugifyIdentifier(deviceNameValue);

    if (createUniqueInput) {
      if (createAutoFlags.uniqueId) {
        createUniqueInput.value = nameSlug;
      } else {
        createUniqueInput.value = slugifyIdentifier(createUniqueInput.value);
      }
    }

    const uniqueValue = createUniqueInput?.value?.trim() || nameSlug;

    if (createObjectInput) {
      if (createAutoFlags.objectId) {
        createObjectInput.value = slugifyIdentifier(uniqueValue) || uniqueValue;
      } else {
        createObjectInput.value = slugifyIdentifier(createObjectInput.value);
      }
    }

    const objectSlug = slugifyIdentifier(createObjectInput?.value || '');
    if (createObjectInput) {
      createObjectInput.value = objectSlug;
    }

    if (createEntityInput && createAutoFlags.entityId) {
      if (typeValue) {
        const slugParts = [];
        if (deviceSlug) slugParts.push(deviceSlug);
        if (nameSlug) slugParts.push(nameSlug);
        const combinedSlug = slugParts.join('_');
        createEntityInput.value = combinedSlug ? `${typeValue}.${combinedSlug}` : '';
      } else {
        createEntityInput.value = '';
      }
    }

    if (createNodeInput && !createNodeInput.value) {
      createNodeInput.value = 'hassems';
    }
    const nodeSegment = createNodeInput?.value ?? 'hassems';

    if (createStateTopicInput && createAutoFlags.stateTopic) {
      createStateTopicInput.value = buildStateTopic(nodeSegment, objectSlug);
    }
    if (createAvailabilityInput && createAutoFlags.availabilityTopic) {
      createAvailabilityInput.value = buildAvailabilityTopic(nodeSegment, objectSlug);
    }
  }

  function setCreateDefaults() {
    if (!createForm) return;
    if (createForm.elements.component) {
      setSelectValue(createForm.elements.component, 'sensor');
    }
    if (createForm.elements.state_class) {
      setSelectValue(createForm.elements.state_class, 'measurement');
    }
    if (createNodeInput) {
      createNodeInput.value = 'hassems';
    }
    if (createForm.elements.force_update) {
      createForm.elements.force_update.checked = true;
    }
    if (createForm.elements.device_manufacturer) {
      const manufacturer = createForm.elements.device_manufacturer.value?.trim();
      if (!manufacturer) {
        createForm.elements.device_manufacturer.value = 'HASSEMS';
      }
    }
    const advancedSection = createForm.querySelector('.form-advanced');
    if (advancedSection instanceof HTMLDetailsElement) {
      advancedSection.open = false;
    }
    resetCreateAutofillFlags();
    handleCreateTypeChange();
    syncCreateAutofill();
  }

  function handleCreateTypeChange(event) {
    const stateClassSelect = createForm?.elements.namedItem('state_class');
    if (!stateClassSelect) return;
    const type = event?.target?.value ?? createTypeSelect?.value ?? '';
    if (type === 'input_number') {
      setSelectValue(stateClassSelect, 'measurement');
    } else {
      setSelectValue(stateClassSelect, '');
    }
    if (createForm.elements.options) {
      const isSelect = type === 'input_select';
      createForm.elements.options.disabled = !isSelect;
      if (!isSelect) {
        createForm.elements.options.value = '';
      }
    }
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
        mqttForm.discovery_prefix.value = 'homeassistant';
        state.mqttConfig = null;
        return;
      }
      if (!response.ok) {
        throw new Error(response.statusText);
      }
      const data = await response.json();
      state.mqttConfig = data;
      mqttForm.host.value = data.host || '';
      mqttForm.port.value = data.port ?? 1883;
      mqttForm.username.value = data.username || '';
      mqttForm.password.value = data.password || '';
      mqttForm.client_id.value = data.client_id || '';
      mqttForm.discovery_prefix.value = data.discovery_prefix || 'homeassistant';
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
      discovery_prefix: 'homeassistant',
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
      state.mqttConfig = saved;
      mqttForm.discovery_prefix.value = saved.discovery_prefix || 'homeassistant';
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
      discovery_prefix: mqttForm.discovery_prefix.value.trim() || 'homeassistant',
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
      const metaParts = [helper.component];
      if (helper.device_class) {
        metaParts.push(helper.device_class);
      }
      if (helper.unit_of_measurement) {
        metaParts.push(helper.unit_of_measurement);
      }
      if (helper.last_measured_at) {
        metaParts.push(formatTimestamp(helper.last_measured_at));
      }
      meta.textContent = metaParts.join(' · ');

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
    detailEntityId.textContent = `${helper.entity_id} · ${helper.unique_id}`;
    const advancedSection = updateForm.querySelector('.form-advanced');
    if (advancedSection instanceof HTMLDetailsElement) {
      advancedSection.open = false;
    }
    updateForm.elements.name.value = helper.name;
    updateForm.elements.entity_id.value = helper.entity_id;
    const typeDisplay = helperTypeMap[helper.type] || helper.type;
    const typeInput = updateForm.elements.namedItem('type');
    if (typeInput) {
      typeInput.value = typeDisplay;
    }
    updateForm.elements.description.value = helper.description ?? '';
    updateForm.elements.default_value.value = helper.default_value ?? '';
    setSelectValue(updateForm.elements.component, helper.component ?? 'sensor');
    setSelectValue(updateForm.elements.device_class, helper.device_class ?? '');
    setSelectValue(updateForm.elements.unit_of_measurement, helper.unit_of_measurement ?? '');
    const defaultStateClass = helper.type === 'input_number' ? 'measurement' : '';
    setSelectValue(updateForm.elements.state_class, helper.state_class ?? defaultStateClass);
    updateForm.elements.unique_id.value = helper.unique_id ?? '';
    updateForm.elements.object_id.value = helper.object_id ?? '';
    updateForm.elements.node_id.value = helper.node_id ?? 'hassems';
    updateForm.elements.state_topic.value = helper.state_topic ?? '';
    updateForm.elements.availability_topic.value = helper.availability_topic ?? '';
    updateForm.elements.icon.value = helper.icon ?? '';
    updateForm.elements.force_update.checked = Boolean(helper.force_update);
    updateForm.elements.device_name.value = helper.device_name ?? '';
    updateForm.elements.device_manufacturer.value = helper.device_manufacturer ?? '';
    updateForm.elements.device_model.value = helper.device_model ?? '';
    updateForm.elements.device_sw_version.value = helper.device_sw_version ?? '';
    updateForm.elements.device_identifiers.value = (helper.device_identifiers || []).join(', ');

    const optionsField = updateForm.elements.options;
    if (helper.type === 'input_select') {
      optionsField.value = (helper.options || []).join(', ');
      optionsField.disabled = false;
    } else {
      optionsField.value = '';
      optionsField.disabled = true;
    }

    detailLastValue.textContent = helper.last_value ?? '—';
    detailMeasuredAt.textContent = helper.last_measured_at
      ? formatTimestamp(helper.last_measured_at)
      : '—';
    detailUpdated.textContent = helper.updated_at ? formatTimestamp(helper.updated_at) : '—';
    detailComponent.textContent = helper.component || '—';
    detailStateTopic.textContent = helper.state_topic || '—';
    detailAvailabilityTopic.textContent = helper.availability_topic || '—';
    detailDiscoveryTopic.textContent = computeDiscoveryTopic(helper);

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
    detailComponent.textContent = '—';
    detailDiscoveryTopic.textContent = '—';
    detailStateTopic.textContent = '—';
    detailAvailabilityTopic.textContent = '—';
    if (state.chart) {
      state.chart.destroy();
      state.chart = null;
    }
  }

  async function handleCreateHelper(event) {
    event.preventDefault();
    const formData = new FormData(createForm);
    const helperType = formData.get('type');

    try {
      const payload = buildCreatePayload(formData);
      await requestJson('/inputs', {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      createForm.reset();
      setCreateDefaults();
      showToast('Entity created.', 'success');
      await loadHelpers();
    } catch (error) {
      showToast(error.message, 'error');
    }
  }

  function buildCreatePayload(formData) {
    const helperType = formData.get('type');
    const payload = {
      name: formData.get('name')?.trim(),
      entity_id: formData.get('entity_id')?.trim(),
      type: helperType,
      component: formData.get('component')?.trim() || 'sensor',
      unique_id: slugifyIdentifier(formData.get('unique_id')?.trim()) || null,
      object_id: slugifyIdentifier(formData.get('object_id')?.trim()) || null,
      node_id: slugifyIdentifier(formData.get('node_id')?.trim()) || null,
      state_topic: formData.get('state_topic')?.trim(),
      availability_topic: formData.get('availability_topic')?.trim(),
      force_update: formData.get('force_update') === 'on',
      device_name: formData.get('device_name')?.trim(),
    };

    const description = formData.get('description')?.trim();
    if (description) payload.description = description;

    const defaultRaw = formData.get('default_value')?.trim();
    if (defaultRaw) {
      payload.default_value = coerceValue(helperType, defaultRaw);
    }

    if (helperType === 'input_select') {
      const options = parseCsv(formData.get('options'));
      if (options.length) {
        payload.options = options;
      }
    }

    const deviceClass = formData.get('device_class')?.trim();
    if (deviceClass) payload.device_class = deviceClass;

    const unit = formData.get('unit_of_measurement')?.trim();
    if (unit) payload.unit_of_measurement = unit;

    const stateClass = formData.get('state_class')?.trim();
    if (stateClass) payload.state_class = stateClass;

    const icon = formData.get('icon')?.trim();
    if (icon) payload.icon = icon;

    const manufacturer = formData.get('device_manufacturer')?.trim();
    if (manufacturer) payload.device_manufacturer = manufacturer;

    const model = formData.get('device_model')?.trim();
    if (model) payload.device_model = model;

    const swVersion = formData.get('device_sw_version')?.trim();
    if (swVersion) payload.device_sw_version = swVersion;

    const identifiers = parseCsv(formData.get('device_identifiers'));
    if (identifiers.length) payload.device_identifiers = identifiers;

    return removeUndefined(payload);
  }

  async function handleUpdateHelper(event) {
    event.preventDefault();
    if (!state.selected) {
      showToast('Select an entity to edit.', 'error');
      return;
    }

    const formData = new FormData(updateForm);
    const helperType = state.selected.type;

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
      component: formData.get('component')?.trim() || null,
      unique_id: slugifyIdentifier(formData.get('unique_id')?.trim()) || null,
      object_id: slugifyIdentifier(formData.get('object_id')?.trim()) || null,
      node_id: slugifyIdentifier(formData.get('node_id')?.trim()) || null,
      state_topic: formData.get('state_topic')?.trim(),
      availability_topic: formData.get('availability_topic')?.trim(),
      icon: formData.get('icon')?.trim() || null,
      device_class: formData.get('device_class')?.trim() || null,
      unit_of_measurement: formData.get('unit_of_measurement')?.trim() || null,
      state_class: formData.get('state_class')?.trim() || null,
      force_update: formData.get('force_update') === 'on',
      device_name: formData.get('device_name')?.trim(),
      device_manufacturer: formData.get('device_manufacturer')?.trim() || null,
      device_model: formData.get('device_model')?.trim() || null,
      device_sw_version: formData.get('device_sw_version')?.trim() || null,
    };

    const defaultRaw = formData.get('default_value')?.trim();
    if (defaultRaw) {
      payload.default_value = coerceValue(helperType, defaultRaw);
    }

    if (helperType === 'input_select') {
      const options = parseCsv(formData.get('options'));
      if (options.length) {
        payload.options = options;
      }
    }

    const identifiersRaw = formData.get('device_identifiers');
    if (identifiersRaw !== null) {
      const trimmed = identifiersRaw.trim();
      payload.device_identifiers = trimmed ? parseCsv(trimmed) : [];
    }

    return removeUndefined(payload);
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
    field.innerHTML = '<span class="label-text">Value</span>';

    let input;
    if (helper.type === 'input_boolean') {
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
    } else if (helper.type === 'input_number') {
      input = document.createElement('input');
      input.type = 'number';
      input.name = 'value';
      if (helper.unit_of_measurement) {
        input.placeholder = `Enter value in ${helper.unit_of_measurement}`;
      }
      if (typeof helper.last_value === 'number') {
        input.value = helper.last_value;
      }
    } else if (helper.type === 'input_select') {
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

    const measuredField = document.createElement('label');
    measuredField.className = 'form-field';
    measuredField.innerHTML = '<span class="label-text">Measured at</span>';

    const measuredContainer = document.createElement('div');
    measuredContainer.className = 'datetime-inputs';

    const measuredDate = document.createElement('input');
    measuredDate.type = 'date';
    measuredDate.name = 'measured_date';

    const measuredTime = document.createElement('input');
    measuredTime.type = 'time';
    measuredTime.name = 'measured_time';
    measuredTime.step = 60;

    measuredContainer.append(measuredDate, measuredTime);
    measuredField.appendChild(measuredContainer);

    setMeasuredInputsToNow(measuredDate, measuredTime);

    const submit = document.createElement('button');
    submit.type = 'submit';
    submit.className = 'btn primary';
    submit.textContent = 'Publish to MQTT';

    valueForm.append(field, measuredField, submit);
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
    const measuredDate = valueForm.querySelector('[name="measured_date"]');
    const measuredTime = valueForm.querySelector('[name="measured_time"]');
    const rawValue = valueInput.value;

    try {
      const payload = { value: coerceValue(helper.type, rawValue) };
      const customDate = measuredDate?.value;
      const customTime = measuredTime?.value;

      if (customDate || customTime) {
        if (!customDate) {
          throw new Error('Provide a measurement date.');
        }
        const timePortion = customTime && customTime.trim() ? customTime : '00:00';
        const parsed = new Date(`${customDate}T${timePortion}`);
        if (Number.isNaN(parsed.getTime())) {
          throw new Error('Provide a valid measured at timestamp.');
        }
        payload.measured_at = parsed.toISOString();
      } else {
        const now = new Date();
        payload.measured_at = now.toISOString();
        setMeasuredInputsToNow(measuredDate, measuredTime, now);
      }
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
      setMeasuredInputsToNow(measuredDate, measuredTime);
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

    const labels = history.map((item) => formatTimestamp(item.measured_at));
    const numericValues = history.map((item) => normalizeHistoryValue(helper.type, item.value));
    const allNumeric = numericValues.every((value) => value !== null && !Number.isNaN(value));

    if (allNumeric) {
      historyCanvas.classList.remove('hidden');
      historyList.classList.add('hidden');
      const dataset = numericValues.map((value) => Number(value));

      const yTicks = helper.type === 'input_boolean'
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
              beginAtZero: helper.type !== 'input_number',
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
      label.textContent = formatTimestamp(item.measured_at);
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

  function computeDiscoveryTopic(helper) {
    const prefix = (state.mqttConfig?.discovery_prefix || 'homeassistant').replace(/\/+$/, '');
    const parts = [prefix, helper.component];
    const nodeSegment = helper.node_id ?? 'hassems';
    if (nodeSegment) {
      parts.push(nodeSegment);
    }
    parts.push(helper.object_id);
    parts.push('config');
    return parts.join('/');
  }

  function parseCsv(rawValue) {
    if (!rawValue) {
      return [];
    }
    return String(rawValue)
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function removeUndefined(payload) {
    const entries = Object.entries(payload).filter(([, value]) => value !== undefined);
    return Object.fromEntries(entries);
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

  function setMeasuredInputsToNow(dateInput, timeInput, referenceDate = new Date()) {
    if (!dateInput && !timeInput) {
      return;
    }
    const localDate = toLocalDateValue(referenceDate);
    const localTime = toLocalTimeValue(referenceDate);
    if (dateInput) {
      dateInput.value = localDate;
    }
    if (timeInput) {
      timeInput.value = localTime;
    }
  }

  function toLocalDateValue(date) {
    const pad = (input) => String(input).padStart(2, '0');
    const year = date.getFullYear();
    const month = pad(date.getMonth() + 1);
    const day = pad(date.getDate());
    return `${year}-${month}-${day}`;
  }

  function toLocalTimeValue(date) {
    const pad = (input) => String(input).padStart(2, '0');
    const hours = pad(date.getHours());
    const minutes = pad(date.getMinutes());
    return `${hours}:${minutes}`;
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
