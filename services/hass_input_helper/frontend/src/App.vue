
<template>
  <div>
    <header class="navbar">
      <div class="navbar__brand">
        <span class="navbar__title">HASSEMS</span>
        <span class="navbar__subtitle">Home Assistant Entity Management System</span>
      </div>
      <nav class="navbar__links">
        <button
          type="button"
          :class="{ active: activePage === 'entities' }"
          @click="activePage = 'entities'"
        >
          Entities
        </button>
        <button
          type="button"
          :class="{ active: activePage === 'settings' }"
          @click="activePage = 'settings'"
        >
          Settings
        </button>
      </nav>
    </header>

    <main class="layout">
      <section class="card" id="mqtt-card" v-if="activePage === 'settings'">
        <div class="card__header">
          <div>
            <h2>MQTT Broker</h2>
            <p class="card__subtitle">
              Connect HASSEMS to the Mosquitto add-on exposed by your Home Assistant instance.
            </p>
          </div>
        </div>

        <form class="form-grid" @submit.prevent="saveMqttConfig">
          <label class="form-field">
            <span class="label-text">
              Host
              <button
                type="button"
                class="help-icon"
                data-tooltip="Hostname or IP address of your MQTT broker. Example: homeassistant.local."
              >?
              </button>
            </span>
            <input v-model="mqttForm.host" type="text" required placeholder="homeassistant.local" />
          </label>
          <label class="form-field">
            <span class="label-text">
              Port
              <button
                type="button"
                class="help-icon"
                data-tooltip="TCP port exposed by the MQTT broker. Mosquitto defaults to 1883 for unencrypted connections."
              >?
              </button>
            </span>
            <input v-model.number="mqttForm.port" type="number" min="1" max="65535" />
          </label>
          <label class="form-field">
            <span class="label-text">
              Username
              <button
                type="button"
                class="help-icon"
                data-tooltip="MQTT username created in Home Assistant (Settings → People &amp; Services → Users). Leave blank for anonymous brokers."
              >?
              </button>
            </span>
            <input v-model="mqttForm.username" type="text" autocomplete="username" />
          </label>
          <label class="form-field">
            <span class="label-text">
              Password
              <button
                type="button"
                class="help-icon"
                data-tooltip="Password for the MQTT account above. Stored encrypted in the local SQLite database."
              >?
              </button>
            </span>
            <input v-model="mqttForm.password" type="password" autocomplete="current-password" />
          </label>
          <label class="form-field">
            <span class="label-text">
              Client ID
              <button
                type="button"
                class="help-icon"
                data-tooltip="Optional MQTT client identifier. HASSEMS auto-generates one if left blank."
              >?
              </button>
            </span>
            <input v-model="mqttForm.client_id" type="text" placeholder="auto-generated if empty" />
          </label>
          <label class="form-field">
            <span class="label-text">
              Discovery prefix
              <button
                type="button"
                class="help-icon"
                data-tooltip="Home Assistant listens for discovery payloads under this prefix. The integration defaults to homeassistant and HASSEMS enforces that value."
              >?
              </button>
            </span>
            <input v-model="mqttForm.discovery_prefix" type="text" readonly />
          </label>
          <label class="form-checkbox">
            <input v-model="mqttForm.use_tls" type="checkbox" />
            <span class="label-text">
              Use TLS
              <button
                type="button"
                class="help-icon"
                data-tooltip="Enable if your broker requires TLS/SSL (typically port 8883). HASSEMS uses system certificates."
              >?
              </button>
            </span>
          </label>
          <div class="form-actions">
            <button class="btn primary" type="submit" :disabled="mqttSaving">
              {{ mqttSaving ? 'Saving…' : 'Save configuration' }}
            </button>
            <button class="btn" type="button" @click="testMqttConfig" :disabled="mqttSaving">
              Test connection
            </button>
          </div>
          <p class="form-helper">
            Configure the Mosquitto add-on and MQTT integration first, then supply matching credentials here. Settings
            are stored in <code>data/input_helpers.db</code>.
          </p>
        </form>
      </section>


      <section class="card" id="entities-card" v-if="activePage === 'entities'">
        <div class="card__header">
          <div>
            <h2>Entities</h2>
            <p class="card__subtitle">
              Manage helper entities stored in HASSEMS and published to Home Assistant.
            </p>
          </div>
          <div class="card__actions">
            <button class="btn" type="button" @click="loadHelpers">Refresh</button>
            <button class="btn primary" type="button" @click="openCreateDialog">New entity</button>
          </div>
        </div>

        <div v-if="helpers.length" class="entity-table-wrapper">
          <table class="entity-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Entity ID</th>
                <th scope="col">Type</th>
                <th scope="col">Last value</th>
                <th scope="col">Updated</th>
              </tr>
            </thead>
            <tbody>
              <tr
                v-for="helper in helpers"
                :key="helper.slug"
                :class="{ active: helper.slug === selectedSlug }"
                @click="selectHelper(helper.slug)"
                @keydown.enter.prevent="selectHelper(helper.slug)"
                @keydown.space.prevent="selectHelper(helper.slug)"
                role="button"
                tabindex="0"
              >
                <td>
                  <div class="entity-name">
                    <span class="entity-name__primary">{{ helper.name }}</span>
                    <span v-if="helper.device_name" class="entity-name__secondary">{{ helper.device_name }}</span>
                  </div>
                </td>
                <td><code>{{ helper.entity_id }}</code></td>
                <td>{{ helperTypeMap[helper.type] || helper.type }}</td>
                <td>{{ helper.last_value ?? '—' }}</td>
                <td>{{ helper.updated_at ? formatTimestamp(helper.updated_at) : '—' }}</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="card__subtitle">No entities created yet.</p>
      </section>


      <section v-if="activePage === 'entities' && selectedHelper" class="card" id="entity-detail-card">
        <div class="card__header">
          <div>
            <h2 id="detail-title">Entity details</h2>
            <p class="card__subtitle" id="detail-entity-id">
              {{ selectedHelper?.entity_id }} · {{ selectedHelper?.unique_id }}
            </p>
          </div>
          <div class="card__actions">
            <button class="btn" type="button" @click="openApiDialog">Call app</button>
            <button class="btn danger" type="button" @click="deleteHelper">Delete</button>
          </div>
        </div>

        <form id="update-helper-form" @submit.prevent="updateHelper">
          <div class="form-grid form-grid--base">
            <label class="form-field">
              <span class="label-text">
                Device name
                <button type="button" class="help-icon" data-tooltip="Parent device name in Home Assistant.">?</button>
              </span>
              <input v-model="updateForm.device_name" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Entity name
                <button type="button" class="help-icon" data-tooltip="Update the friendly name shown in Home Assistant.">?</button>
              </span>
              <input v-model="updateForm.name" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Description
                <button type="button" class="help-icon" data-tooltip="Reference notes about the entity.">?</button>
              </span>
              <textarea v-model="updateForm.description" rows="2"></textarea>
            </label>
            <label class="form-field">
              <span class="label-text">
                Type
                <button type="button" class="help-icon" data-tooltip="Helper domain mirrored in Home Assistant. This cannot be edited.">?</button>
              </span>
              <input :value="selectedTypeLabel" type="text" readonly />
            </label>
            <label class="form-field">
              <span class="label-text">
                Device class
                <button type="button" class="help-icon" data-tooltip="Home Assistant device class.">?</button>
              </span>
              <select v-model="updateForm.device_class">
                <option v-for="option in deviceClassOptions" :key="`update-device-${option.value}`" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">
                Unit of measurement
                <button type="button" class="help-icon" data-tooltip="Measurement unit reported to Home Assistant.">?</button>
              </span>
              <select v-model="updateForm.unit_of_measurement">
                <option v-for="option in unitOptions" :key="`update-unit-${option.value}`" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">
                Icon
                <button type="button" class="help-icon" data-tooltip="Material Design Icon reference used in the UI.">?</button>
              </span>
              <select v-model="updateForm.icon">
                <option v-for="option in iconOptions" :key="`update-icon-${option.value}`" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">
                Entity ID
                <button type="button" class="help-icon" data-tooltip="Home Assistant helper entity ID (domain.object_id).">?</button>
              </span>
              <input v-model="updateForm.entity_id" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Default value
                <button type="button" class="help-icon" data-tooltip="Value stored by default in HASSEMS and Home Assistant.">?</button>
              </span>
              <input v-model="updateForm.default_value" type="text" />
            </label>
            <label class="form-field">
              <span class="label-text">
                Component
                <button type="button" class="help-icon" data-tooltip="MQTT discovery platform.">?</button>
              </span>
              <select v-model="updateForm.component">
                <option v-for="option in componentOptions" :key="`update-component-${option.value}`" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">
                State class
                <button type="button" class="help-icon" data-tooltip="Controls Home Assistant statistics handling.">?</button>
              </span>
              <select v-model="updateForm.state_class">
                <option v-for="option in stateClassOptions" :key="`update-state-${option.value}`" :value="option.value">
                  {{ option.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">
                Unique ID
                <button type="button" class="help-icon" data-tooltip="Identifier tracked by Home Assistant.">?</button>
              </span>
              <input v-model="updateForm.unique_id" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Object ID
                <button type="button" class="help-icon" data-tooltip="Final segment of the discovery topic.">?</button>
              </span>
              <input v-model="updateForm.object_id" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Device ID
                <button type="button" class="help-icon" data-tooltip="Slug used to group entities from the same device.">?</button>
              </span>
              <input v-model="updateForm.device_id" type="text" />
            </label>
            <label class="form-field">
              <span class="label-text">
                Node ID
                <button type="button" class="help-icon" data-tooltip="Optional discovery topic folder.">?</button>
              </span>
              <input v-model="updateForm.node_id" type="text" placeholder="hassems" />
            </label>
            <label class="form-field">
              <span class="label-text">
                State topic
                <button type="button" class="help-icon" data-tooltip="Topic where values are published.">?</button>
              </span>
              <input v-model="updateForm.state_topic" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Availability topic
                <button type="button" class="help-icon" data-tooltip="Topic reflecting device availability.">?</button>
              </span>
              <input v-model="updateForm.availability_topic" type="text" required />
            </label>
            <label class="form-field">
              <span class="label-text">
                Device manufacturer
                <button type="button" class="help-icon" data-tooltip="Manufacturer metadata for the device.">?</button>
              </span>
              <input v-model="updateForm.device_manufacturer" type="text" />
            </label>
            <label class="form-field">
              <span class="label-text">
                Device model
                <button type="button" class="help-icon" data-tooltip="Model identifier used by Home Assistant.">?</button>
              </span>
              <input v-model="updateForm.device_model" type="text" />
            </label>
            <label class="form-field">
              <span class="label-text">
                Device firmware
                <button type="button" class="help-icon" data-tooltip="Software or firmware version string.">?</button>
              </span>
              <input v-model="updateForm.device_sw_version" type="text" />
            </label>
            <label class="form-field full-width">
              <span class="label-text">
                Device identifiers
                <button type="button" class="help-icon" data-tooltip="Comma-separated identifiers for the parent device. Defaults to node_id:unique_id when left blank.">?</button>
              </span>
              <input v-model="updateForm.device_identifiers" type="text" />
            </label>
            <label class="form-checkbox">
              <input v-model="updateForm.force_update" type="checkbox" />
              <span class="label-text">
                Force update
                <button type="button" class="help-icon" data-tooltip="Emit state_changed events even when the value is unchanged.">?</button>
              </span>
            </label>
          </div>

          <div class="form-actions">
            <button class="btn primary" type="submit">Save changes</button>
          </div>
        </form>

        <div class="helper-status">
          <div class="helper-meta">
            <p><strong>Component:</strong> <span id="detail-component">{{ selectedHelper?.component || '—' }}</span></p>
            <p><strong>Discovery topic:</strong> <span id="detail-discovery-topic">{{ selectedDiscoveryTopic }}</span></p>
            <p><strong>State topic:</strong> <span id="detail-state-topic">{{ selectedHelper?.state_topic || '—' }}</span></p>
            <p><strong>Availability topic:</strong> <span id="detail-availability-topic">{{ selectedHelper?.availability_topic || '—' }}</span></p>
          </div>
          <p><strong>Last value:</strong> <span id="detail-last-value">{{ selectedHelper?.last_value ?? '—' }}</span></p>
          <p><strong>Measured at:</strong> <span id="detail-measured-at">{{ selectedMeasuredAt }}</span></p>
          <p><strong>Recorded:</strong> <span id="detail-updated">{{ selectedUpdatedAt }}</span></p>
        </div>

        <div class="divider"></div>

        <section class="history">
          <h3>Recent values</h3>
          <canvas
            v-show="historyMode === 'chart'"
            id="history-chart"
            height="220"
            ref="historyCanvas"
          ></canvas>
          <ul v-if="historyMode === 'list'" id="history-list" class="history-list">
            <li v-for="item in historyList" :key="item.measured_at">
              <span>{{ item.measured_at }}</span>
              <span>{{ item.value }}</span>
            </li>
          </ul>
          <p v-else-if="historyMode === 'empty'">No values yet</p>
        </section>

        <div class="divider"></div>

        <section>
          <h3>Send new value</h3>
          <form id="value-form" class="value-form" @submit.prevent="submitValue">
            <label class="form-field">
              <span class="label-text">Value</span>
              <template v-if="valueInputType === 'boolean'">
                <select v-model="valueForm.value">
                  <option value="false">Off</option>
                  <option value="true">On</option>
                </select>
              </template>
              <template v-else-if="valueInputType === 'number'">
                <input v-model="valueForm.value" type="number" :placeholder="valuePlaceholder" />
              </template>
              <template v-else-if="valueInputType === 'select'">
                <select v-model="valueForm.value">
                  <option v-for="option in valueOptions" :key="option" :value="option">
                    {{ option }}
                  </option>
                </select>
              </template>
              <template v-else>
                <input v-model="valueForm.value" type="text" />
              </template>
            </label>
            <label class="form-field">
              <span class="label-text">Measured at</span>
              <div class="datetime-inputs">
                <input v-model="valueForm.measured_date" type="date" name="measured_date" />
                <input v-model="valueForm.measured_time" type="time" name="measured_time" step="60" />
              </div>
            </label>
            <button class="btn primary" type="submit">Publish to MQTT</button>
          </form>
        </section>
      </section>
      <section v-else-if="activePage === 'entities'" class="card card--empty" id="entity-detail-card">
        <div class="card__header">
          <h2>Entity details</h2>
        </div>
        <p class="card__subtitle">Select an entity from the table to view configuration and history.</p>
      </section>
    </main>

    <dialog
      ref="createDialog"
      class="modal"
      @cancel.prevent="closeCreateDialog"
      @close="onCreateDialogClose"
    >
      <div class="modal__container">
        <div class="modal__header">
          <h3>New entity</h3>
          <button
            type="button"
            class="modal__close"
            @click="closeCreateDialog"
            aria-label="Close create entity dialog"
          >
            ×
          </button>
        </div>
        <form class="modal__form" id="create-helper-form" @submit.prevent="createHelper">
          <div class="modal__body">
            <div class="form-grid form-grid--base">
              <label class="form-field">
                <span class="label-text">
                  Device name
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Name shown for the parent device grouping in Home Assistant's Devices tab."
                  >?
                  </button>
                </span>
                <input v-model="createForm.device_name" type="text" required placeholder="Child Metrics" />
              </label>
              <label class="form-field">
                <span class="label-text">
                  Entity name
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Friendly label shown in Home Assistant once the entity is discovered."
                  >?
                  </button>
                </span>
                <input v-model="createForm.name" type="text" required />
              </label>
              <label class="form-field">
                <span class="label-text">
                  Description
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Internal notes about the entity's purpose. Stored for reference only."
                  >?
                  </button>
                </span>
                <textarea v-model="createForm.description" rows="2"></textarea>
              </label>
              <label class="form-field">
                <span class="label-text">
                  Type
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Select the Home Assistant helper domain this entity mirrors (input_text, input_number, etc.)."
                  >?
                  </button>
                </span>
                <select v-model="createForm.type">
                  <option value="input_text">Input text</option>
                  <option value="input_number">Input number</option>
                  <option value="input_boolean">Input boolean</option>
                  <option value="input_select">Input select</option>
                </select>
              </label>
              <label class="form-field">
                <span class="label-text">
                  Device class
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Maps the measurement to a Home Assistant concept (distance, temperature, humidity, etc.)."
                  >?
                  </button>
                </span>
                <select v-model="createForm.device_class">
                  <option v-for="option in deviceClassOptions" :key="`create-device-${option.value}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="form-field">
                <span class="label-text">
                  Unit of measurement
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Unit string shown in Home Assistant. The options follow device class guidelines."
                  >?
                  </button>
                </span>
                <select v-model="createForm.unit_of_measurement">
                  <option v-for="option in unitOptions" :key="`create-unit-${option.value}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="form-field">
                <span class="label-text">
                  Icon
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Select an icon from the Material Design Icons set to represent the entity in Home Assistant."
                  >?
                  </button>
                </span>
                <select v-model="createForm.icon">
                  <option v-for="option in iconOptions" :key="`create-icon-${option.value}`" :value="option.value">
                    {{ option.label }}
                  </option>
                </select>
              </label>
              <label class="form-field">
                <span class="label-text">
                  Entity ID
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Automatically generated from the device and entity names. Update if you already created a matching helper in Home Assistant."
                  >?
                  </button>
                </span>
                <input
                  v-model="createForm.entity_id"
                  type="text"
                  required
                  placeholder="input_number.child_metrics_height"
                  @input="createAutoFlags.entityId = false"
                />
              </label>
              <label class="form-checkbox">
                <input v-model="createForm.force_update" type="checkbox" />
                <span class="label-text">
                  Force update
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Emit state_changed events even when the value is unchanged. Useful for clean charts."
                  >?
                  </button>
                </span>
              </label>
            </div>

            <details class="form-advanced">
              <summary>Advanced configuration</summary>
              <div class="form-grid">
                <label class="form-field">
                  <span class="label-text">
                    Options (comma separated)
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Comma-delimited options for input_select helpers. Example: short,average,tall."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.options"
                    type="text"
                    placeholder="Only for input_select"
                    :disabled="createOptionsDisabled"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Default value
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Optional initial value stored in both HASSEMS and Home Assistant when the entity is created."
                    >?
                    </button>
                  </span>
                  <input v-model="createForm.default_value" type="text" />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Component
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="MQTT discovery platform (sensor, binary_sensor, number, etc.). Determines how Home Assistant treats the entity."
                    >?
                    </button>
                  </span>
                  <select v-model="createForm.component">
                    <option v-for="option in componentOptions" :key="`create-component-${option.value}`" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="form-field">
                  <span class="label-text">
                    State class
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Controls Home Assistant statistics handling. Choose measurement for most sensors."
                    >?
                    </button>
                  </span>
                  <select v-model="createForm.state_class">
                    <option v-for="option in stateClassOptions" :key="`create-state-${option.value}`" :value="option.value">
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Unique ID
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Auto-generated from the device and entity names. Edit to override the identifier Home Assistant tracks."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.unique_id"
                    type="text"
                    required
                    placeholder="child_metrics_child_height"
                    @input="createAutoFlags.uniqueId = false"
                    @blur="handleCreateUniqueBlur"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Object ID
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Final segment of the discovery topic. Defaults to the unique ID."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.object_id"
                    type="text"
                    required
                    placeholder="child_metrics_child_height"
                    @input="createAutoFlags.objectId = false"
                    @blur="handleCreateObjectBlur"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Device ID
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Slug used to group entities from the same device. Generated from the device name by default."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.device_id"
                    type="text"
                    placeholder="child_metrics"
                    @input="createAutoFlags.deviceId = false"
                    @blur="handleCreateDeviceIdBlur"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Node ID
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Optional grouping folder between the component and object ID. Defaults to hassems."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.node_id"
                    type="text"
                    placeholder="hassems"
                    @blur="handleCreateNodeBlur"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    State topic
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="MQTT topic where HASSEMS publishes value updates. Generated from the node ID, device ID, and entity ID."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.state_topic"
                    type="text"
                    required
                    placeholder="hassems/child_metrics/input_number.child_metrics_height/state"
                    @input="createAutoFlags.stateTopic = false"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Availability topic
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="MQTT topic that reports if the device is online (payloads: online/offline). Generated alongside the state topic."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.availability_topic"
                    type="text"
                    required
                    placeholder="hassems/child_metrics/input_number.child_metrics_height/availability"
                    @input="createAutoFlags.availabilityTopic = false"
                  />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Device manufacturer
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Manufacturer metadata reported to Home Assistant. Defaults to HASSEMS."
                    >?
                    </button>
                  </span>
                  <input v-model="createForm.device_manufacturer" type="text" placeholder="HASSEMS" />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Device model
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Model identifier used when grouping entities under a device."
                    >?
                    </button>
                  </span>
                  <input v-model="createForm.device_model" type="text" placeholder="Input Number" />
                </label>
                <label class="form-field">
                  <span class="label-text">
                    Device firmware
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Optional firmware or software version string shown in the device panel."
                    >?
                    </button>
                  </span>
                  <input v-model="createForm.device_sw_version" type="text" placeholder="1.0.0" />
                </label>
                <label class="form-field full-width">
                  <span class="label-text">
                    Device identifiers
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Comma-separated identifiers that uniquely describe the device in Home Assistant's registry. Defaults to node_id:unique_id."
                    >?
                    </button>
                  </span>
                  <input
                    v-model="createForm.device_identifiers"
                    type="text"
                    placeholder="hassems:child_metrics_child_height"
                  />
                </label>
              </div>
            </details>
          </div>
          <div class="modal__actions">
            <button class="btn primary" type="submit">Create entity</button>
            <button class="btn" type="button" @click="previewDiscovery">Preview discovery</button>
          </div>
        </form>
      </div>
    </dialog>

    <dialog ref="discoveryDialog" class="modal" @cancel.prevent="closeDiscoveryPreview" @close="onDiscoveryDialogClose">
      <template v-if="discoveryPreview">
        <div class="modal__container">
          <div class="modal__header">
            <h3>Discovery payload preview</h3>
            <button type="button" class="modal__close" @click="closeDiscoveryPreview" aria-label="Close discovery preview">
              ×
            </button>
          </div>
          <div class="modal__body">
            <p class="modal__topic">
              <strong>Topic:</strong>
              <code id="discovery-preview-topic">{{ discoveryPreview.topic }}</code>
            </p>
            <pre id="discovery-preview-payload" class="modal__pre">{{ discoveryPreview.payload }}</pre>
          </div>
          <div class="modal__actions">
            <button type="button" class="btn" @click="closeDiscoveryPreview">Close</button>
          </div>
        </div>
      </template>
    </dialog>

    <dialog ref="apiDialog" class="modal" @cancel.prevent="closeApiDialog" @close="onApiDialogClose">
      <template v-if="selectedHelper">
        <div class="modal__container">
          <div class="modal__header">
            <h3>Call this helper from another app</h3>
            <button type="button" class="modal__close" @click="closeApiDialog" aria-label="Close API details dialog">
              ×
            </button>
          </div>
          <div class="modal__body">
            <p>
              Use this endpoint to push values into HASSEMS. It records history and publishes MQTT messages the same way as the
              "Send new value" form.
            </p>
            <p class="modal__topic">
              <strong>Endpoint:</strong>
              <code id="api-endpoint">{{ selectedApiUrl }}</code>
            </p>
            <p class="modal__note">
              Send a <code>POST</code> request with a JSON body like the example below. Replace the value with the reading you want
              to report.
            </p>
            <pre id="api-payload-example" class="modal__pre">{{ selectedApiPayloadPretty }}</pre>
            <p>
              Example using <code>curl</code>:
            </p>
            <pre id="api-curl-example" class="modal__pre">{{ selectedApiCurl }}</pre>
            <p class="modal__note">
              The <code>measured_at</code> field is optional. If it is omitted the server stores the current timestamp automatically.
            </p>
          </div>
          <div class="modal__actions">
            <button type="button" class="btn" @click="closeApiDialog">Close</button>
          </div>
        </div>
      </template>
    </dialog>

    <div
      id="toast"
      class="toast"
      :class="[toast.type, { visible: toast.visible }]"
      role="status"
      aria-live="polite"
    >
      {{ toast.message }}
    </div>
  </div>
</template>


<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import Chart from 'chart.js/auto';

const helperTypeMap = {
  input_text: 'Input text',
  input_number: 'Input number',
  input_boolean: 'Input boolean',
  input_select: 'Input select',
};

const deviceClassOptions = [
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

const unitOptions = [
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

const componentOptions = [
  { value: 'sensor', label: 'Sensor' },
  { value: 'binary_sensor', label: 'Binary sensor' },
  { value: 'number', label: 'Number' },
  { value: 'switch', label: 'Switch' },
  { value: 'select', label: 'Select' },
  { value: 'text', label: 'Text' },
  { value: 'button', label: 'Button' },
];

const stateClassOptions = [
  { value: '', label: 'None' },
  { value: 'measurement', label: 'Measurement' },
  { value: 'total', label: 'Total' },
  { value: 'total_increasing', label: 'Total increasing' },
];

const iconOptions = [
  { value: '', label: 'Auto (based on device class)' },
  { value: 'mdi:account', label: 'Person (mdi:account)' },
  { value: 'mdi:calendar', label: 'Calendar (mdi:calendar)' },
  { value: 'mdi:chart-line', label: 'Chart line (mdi:chart-line)' },
  { value: 'mdi:clipboard-pulse', label: 'Clipboard pulse (mdi:clipboard-pulse)' },
  { value: 'mdi:counter', label: 'Counter (mdi:counter)' },
  { value: 'mdi:gauge', label: 'Gauge (mdi:gauge)' },
  { value: 'mdi:human-height', label: 'Human height (mdi:human-height)' },
  { value: 'mdi:information-outline', label: 'Info outline (mdi:information-outline)' },
  { value: 'mdi:scale', label: 'Scale (mdi:scale)' },
  { value: 'mdi:ruler', label: 'Ruler (mdi:ruler)' },
  { value: 'mdi:thermometer', label: 'Thermometer (mdi:thermometer)' },
  { value: 'mdi:water-percent', label: 'Water percent (mdi:water-percent)' },
  { value: 'mdi:weight-kilogram', label: 'Weight kilogram (mdi:weight-kilogram)' },
  { value: 'mdi:speedometer', label: 'Speedometer (mdi:speedometer)' },
  { value: 'mdi:flash', label: 'Flash (mdi:flash)' },
  { value: 'mdi:lightbulb-on', label: 'Lightbulb (mdi:lightbulb-on)' },
  { value: 'mdi:timeline-clock', label: 'Timeline clock (mdi:timeline-clock)' },
  { value: 'mdi:heart-pulse', label: 'Heart pulse (mdi:heart-pulse)' },
  { value: 'mdi:alpha-h-box', label: 'H box (mdi:alpha-h-box)' },
];

const toast = reactive({
  message: '',
  type: 'info',
  visible: false,
});
let toastTimer = null;

const activePage = ref('entities');

const mqttForm = reactive({
  host: '',
  port: 1883,
  username: '',
  password: '',
  client_id: '',
  discovery_prefix: 'homeassistant',
  use_tls: false,
});
const mqttConfig = ref(null);
const mqttSaving = ref(false);

const helpers = ref([]);
const selectedSlug = ref(null);
const historyRecords = ref([]);
const historyMode = ref('empty');
const historyList = ref([]);
const historyCanvas = ref(null);
const chartInstance = ref(null);

const discoveryPreview = ref(null);
const discoveryDialog = ref(null);
const createDialog = ref(null);
const apiDialog = ref(null);
const apiOrigin = typeof window !== 'undefined' && window.location ? window.location.origin : '';

function createCreateDefaults() {
  return {
    device_name: '',
    name: '',
    description: '',
    type: 'input_text',
    device_class: '',
    unit_of_measurement: '',
    icon: '',
    entity_id: '',
    force_update: true,
    options: '',
    default_value: '',
    component: 'sensor',
    state_class: 'measurement',
    unique_id: '',
    object_id: '',
    device_id: '',
    node_id: 'hassems',
    state_topic: '',
    availability_topic: '',
    device_manufacturer: 'HASSEMS',
    device_model: '',
    device_sw_version: '',
    device_identifiers: '',
  };
}

const createForm = reactive(createCreateDefaults());
const createAutoFlags = reactive({
  entityId: true,
  deviceId: true,
  uniqueId: true,
  objectId: true,
  stateTopic: true,
  availabilityTopic: true,
});

const updateForm = reactive({
  device_name: '',
  name: '',
  description: '',
  entity_id: '',
  default_value: '',
  options: '',
  component: 'sensor',
  device_class: '',
  unit_of_measurement: '',
  icon: '',
  state_class: '',
  unique_id: '',
  object_id: '',
  device_id: '',
  node_id: 'hassems',
  state_topic: '',
  availability_topic: '',
  device_manufacturer: '',
  device_model: '',
  device_sw_version: '',
  device_identifiers: '',
  force_update: true,
});

const valueForm = reactive({
  value: '',
  measured_date: '',
  measured_time: '',
});

const selectedHelper = computed(() => helpers.value.find((item) => item.slug === selectedSlug.value) ?? null);
const selectedTypeLabel = computed(() => {
  const helper = selectedHelper.value;
  return helper ? helperTypeMap[helper.type] || helper.type : '';
});
const selectedMeasuredAt = computed(() => {
  const helper = selectedHelper.value;
  return helper?.last_measured_at ? formatTimestamp(helper.last_measured_at) : '—';
});
const selectedUpdatedAt = computed(() => {
  const helper = selectedHelper.value;
  return helper?.updated_at ? formatTimestamp(helper.updated_at) : '—';
});
const selectedDiscoveryTopic = computed(() => {
  const helper = selectedHelper.value;
  return helper ? computeDiscoveryTopic(helper) : '—';
});
const selectedApiPath = computed(() => {
  const helper = selectedHelper.value;
  return helper ? `/api/inputs/${helper.slug}/set` : '';
});
const selectedApiUrl = computed(() => {
  const path = selectedApiPath.value;
  if (!path) {
    return '';
  }
  return apiOrigin ? `${apiOrigin}${path}` : path;
});
const selectedApiPayload = computed(() => {
  const helper = selectedHelper.value;
  const measuredAt = new Date().toISOString();
  if (!helper) {
    return {
      value: 'example',
      measured_at: measuredAt,
    };
  }
  return {
    value: exampleValueFor(helper),
    measured_at: measuredAt,
  };
});
const selectedApiPayloadPretty = computed(() => JSON.stringify(selectedApiPayload.value, null, 2));
const selectedApiPayloadMinified = computed(() => JSON.stringify(selectedApiPayload.value));
const selectedApiCurl = computed(() => {
  const url = selectedApiUrl.value;
  const payload = selectedApiPayloadMinified.value;
  if (!url || !payload) {
    return '';
  }
  const sanitized = payload.replace(/'/g, "'\\''");
  return `curl -X POST "${url}" \\\n  -H "Content-Type: application/json" \\\n  -d '${sanitized}'`;
});
const valueInputType = computed(() => {
  const helper = selectedHelper.value;
  if (!helper) return 'text';
  if (helper.type === 'input_boolean') return 'boolean';
  if (helper.type === 'input_number') return 'number';
  if (helper.type === 'input_select') return 'select';
  return 'text';
});
const valueOptions = computed(() => selectedHelper.value?.options ?? []);
const valuePlaceholder = computed(() => {
  const helper = selectedHelper.value;
  if (!helper) return '';
  if (helper.type === 'input_number' && helper.unit_of_measurement) {
    return `Enter value in ${helper.unit_of_measurement}`;
  }
  return '';
});
const createOptionsDisabled = computed(() => createForm.type !== 'input_select');

watch(
  () => [createForm.name, createForm.device_name, createForm.type, createForm.node_id],
  () => {
    syncCreateAutofill();
  },
);

watch(
  () => createForm.type,
  (type) => {
    if (type === 'input_number') {
      createForm.state_class = 'measurement';
    } else if (createForm.state_class === 'measurement') {
      createForm.state_class = '';
    }
    if (type !== 'input_select') {
      createForm.options = '';
    }
  },
);

watch(discoveryPreview, (preview) => {
  const dialog = discoveryDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  if (preview) {
    if (!dialog.open) {
      dialog.showModal();
    }
  } else if (dialog.open) {
    dialog.close();
  }
});

watch(selectedHelper, async (helper, previous) => {
  if (helper) {
    populateUpdateForm(helper);
    populateValueForm(helper);
    await loadHistory(helper.slug);
  } else {
    resetUpdateForm();
    clearValueForm();
    historyRecords.value = [];
    historyList.value = [];
    historyMode.value = 'empty';
    closeApiDialog();
  }
});

watch(activePage, (page) => {
  if (page !== 'entities') {
    closeApiDialog();
  }
});

watch(
  [historyRecords, selectedHelper],
  ([records, helper]) => {
    if (!helper) {
      destroyChart();
      historyMode.value = 'empty';
      historyList.value = [];
      return;
    }
    nextTick(() => {
      renderHistory(helper, records);
    });
  },
  { deep: true },
);

async function loadMqttConfig() {
  try {
    const response = await fetch('/api/config/mqtt');
    if (response.status === 404) {
      Object.assign(mqttForm, {
        host: '',
        port: 1883,
        username: '',
        password: '',
        client_id: '',
        discovery_prefix: 'homeassistant',
        use_tls: false,
      });
      mqttConfig.value = null;
      return;
    }
    if (!response.ok) {
      throw new Error(response.statusText);
    }
    const data = await response.json();
    mqttConfig.value = data;
    Object.assign(mqttForm, {
      host: data.host || '',
      port: data.port ?? 1883,
      username: data.username || '',
      password: data.password || '',
      client_id: data.client_id || '',
      discovery_prefix: data.discovery_prefix || 'homeassistant',
      use_tls: Boolean(data.use_tls),
    });
  } catch (error) {
    console.error('Failed to load MQTT config', error);
    showToast(`Unable to load MQTT settings: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

async function saveMqttConfig() {
  if (!mqttForm.host.trim()) {
    showToast('MQTT host is required.', 'error');
    return;
  }
  const payload = {
    host: mqttForm.host.trim(),
    port: Number(mqttForm.port) || 1883,
    username: mqttForm.username.trim() || null,
    password: mqttForm.password || null,
    client_id: mqttForm.client_id.trim() || null,
    discovery_prefix: 'homeassistant',
    use_tls: Boolean(mqttForm.use_tls),
  };
  try {
    mqttSaving.value = true;
    const saved = await requestJson('/config/mqtt', {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    mqttConfig.value = saved;
    Object.assign(mqttForm, {
      host: saved.host || '',
      port: saved.port ?? 1883,
      username: saved.username || '',
      password: '',
      client_id: saved.client_id || '',
      discovery_prefix: saved.discovery_prefix || 'homeassistant',
      use_tls: Boolean(saved.use_tls),
    });
    showToast('MQTT configuration saved.', 'success');
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  } finally {
    mqttSaving.value = false;
  }
}

async function testMqttConfig() {
  try {
    mqttSaving.value = true;
    await requestJson('/config/mqtt/test', { method: 'POST' });
    showToast('MQTT connection successful.', 'success');
  } catch (error) {
    showToast(`MQTT connection failed: ${error instanceof Error ? error.message : String(error)}`, 'error');
  } finally {
    mqttSaving.value = false;
  }
}

async function loadHelpers() {
  try {
    const data = await requestJson('/inputs');
    helpers.value = Array.isArray(data) ? data : [];
    if (selectedSlug.value) {
      const exists = helpers.value.some((helper) => helper.slug === selectedSlug.value);
      if (!exists) {
        selectedSlug.value = null;
      }
    }
  } catch (error) {
    showToast(`Failed to load entities: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

function selectHelper(slug) {
  selectedSlug.value = slug;
}

function openCreateDialog() {
  const dialog = createDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  resetCreateForm();
  if (!dialog.open) {
    dialog.showModal();
  }
}

function closeCreateDialog() {
  const dialog = createDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
}

function onCreateDialogClose() {
  resetCreateForm();
}

function openApiDialog() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to view API details.', 'error');
    return;
  }
  const dialog = apiDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

function closeApiDialog() {
  const dialog = apiDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
}

function onApiDialogClose() {
  // Dialog state is managed directly via the native <dialog> element.
}

function helperMeta(helper) {
  const parts = [helper.component];
  if (helper.device_class) {
    parts.push(helper.device_class);
  }
  if (helper.unit_of_measurement) {
    parts.push(helper.unit_of_measurement);
  }
  if (helper.last_measured_at) {
    parts.push(formatTimestamp(helper.last_measured_at));
  }
  return parts.join(' · ');
}

function resetCreateAutoFlags() {
  createAutoFlags.entityId = true;
  createAutoFlags.deviceId = true;
  createAutoFlags.uniqueId = true;
  createAutoFlags.objectId = true;
  createAutoFlags.stateTopic = true;
  createAutoFlags.availabilityTopic = true;
}

function resetCreateForm() {
  Object.assign(createForm, createCreateDefaults());
  resetCreateAutoFlags();
  syncCreateAutofill();
}

function syncCreateAutofill() {
  const nameValue = createForm.name ?? '';
  const nameSlug = slugifyIdentifier(nameValue);
  const typeValue = createForm.type ?? '';
  const deviceNameValue = createForm.device_name ?? '';
  const deviceSlug = slugifyIdentifier(deviceNameValue);

  if (createAutoFlags.deviceId) {
    createForm.device_id = deviceSlug;
  }
  const deviceId = (createForm.device_id ?? '').trim() || deviceSlug;

  if (createAutoFlags.uniqueId) {
    if (deviceId && nameSlug) {
      createForm.unique_id = `${deviceId}_${nameSlug}`;
    } else {
      createForm.unique_id = nameSlug;
    }
  }

  const uniqueValue = slugifyIdentifier(createForm.unique_id || '') || nameSlug;

  if (createAutoFlags.objectId) {
    createForm.object_id = slugifyIdentifier(uniqueValue) || uniqueValue;
  }

  if (createAutoFlags.entityId) {
    if (typeValue) {
      const slugParts = [];
      if (deviceSlug) slugParts.push(deviceSlug);
      if (nameSlug) slugParts.push(nameSlug);
      const combinedSlug = slugParts.join('_');
      createForm.entity_id = combinedSlug ? `${typeValue}.${combinedSlug}` : '';
    } else {
      createForm.entity_id = '';
    }
  }

  if (!createForm.node_id) {
    createForm.node_id = 'hassems';
  }
  const nodeSegment = createForm.node_id || 'hassems';

  if (createAutoFlags.stateTopic) {
    createForm.state_topic = buildStateTopic(nodeSegment, deviceId, nameValue);
  }
  if (createAutoFlags.availabilityTopic) {
    createForm.availability_topic = buildAvailabilityTopic(nodeSegment, deviceId, nameValue);
  }
}

function handleCreateUniqueBlur() {
  createForm.unique_id = slugifyIdentifier(createForm.unique_id || '');
  if (createAutoFlags.objectId) {
    createForm.object_id = slugifyIdentifier(createForm.unique_id || '');
  }
  syncCreateAutofill();
}

function handleCreateObjectBlur() {
  createForm.object_id = slugifyIdentifier(createForm.object_id || '');
  syncCreateAutofill();
}

function handleCreateDeviceIdBlur() {
  createForm.device_id = slugifyIdentifier(createForm.device_id || '');
  syncCreateAutofill();
}

function handleCreateNodeBlur() {
  createForm.node_id = slugifyIdentifier(createForm.node_id || '') || 'hassems';
  syncCreateAutofill();
}

async function createHelper() {
  try {
    const payload = buildCreatePayload();
    await requestJson('/inputs', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showToast('Entity created.', 'success');
    resetCreateForm();
    await loadHelpers();
    closeCreateDialog();
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function buildCreatePayload() {
  const type = createForm.type;
  const payload = {
    name: createForm.name?.trim(),
    entity_id: createForm.entity_id?.trim(),
    type,
    component: createForm.component?.trim() || 'sensor',
    unique_id: slugifyIdentifier(createForm.unique_id?.trim() || ''),
    object_id: slugifyIdentifier(createForm.object_id?.trim() || ''),
    node_id: slugifyIdentifier(createForm.node_id?.trim() || '') || null,
    state_topic: createForm.state_topic?.trim(),
    availability_topic: createForm.availability_topic?.trim(),
    force_update: Boolean(createForm.force_update),
    device_name: createForm.device_name?.trim(),
    device_id: slugifyIdentifier(createForm.device_id?.trim() || '') || null,
  };

  if (createForm.description?.trim()) {
    payload.description = createForm.description.trim();
  }
  if (createForm.device_class?.trim()) {
    payload.device_class = createForm.device_class.trim();
  }
  if (createForm.unit_of_measurement?.trim()) {
    payload.unit_of_measurement = createForm.unit_of_measurement.trim();
  }
  if (createForm.state_class?.trim()) {
    payload.state_class = createForm.state_class.trim();
  }
  if (createForm.icon?.trim()) {
    payload.icon = createForm.icon.trim();
  }
  if (createForm.device_manufacturer?.trim()) {
    payload.device_manufacturer = createForm.device_manufacturer.trim();
  }
  if (createForm.device_model?.trim()) {
    payload.device_model = createForm.device_model.trim();
  }
  if (createForm.device_sw_version?.trim()) {
    payload.device_sw_version = createForm.device_sw_version.trim();
  }

  const defaultRaw = createForm.default_value?.trim();
  if (defaultRaw) {
    payload.default_value = coerceValue(type, defaultRaw);
  }

  if (type === 'input_select') {
    const options = parseCsv(createForm.options);
    if (options.length) {
      payload.options = options;
    }
  }

  const identifiers = parseCsv(createForm.device_identifiers);
  if (identifiers.length) {
    payload.device_identifiers = identifiers;
  }

  return removeUndefined(payload);
}

function previewDiscovery() {
  try {
    const helperDraft = buildHelperDraft();
    const topic = computeDiscoveryTopic(helperDraft);
    const payload = buildDiscoveryPreviewPayload(helperDraft);
    discoveryPreview.value = {
      topic,
      payload: JSON.stringify(payload, null, 2),
    };
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function buildHelperDraft() {
  const payload = buildCreatePayload();
  if (!payload.name) {
    throw new Error('Provide a name before previewing the discovery payload.');
  }
  if (!payload.device_name) {
    throw new Error('Provide a device name before previewing the discovery payload.');
  }
  if (!payload.type) {
    throw new Error('Select an entity type before previewing the discovery payload.');
  }
  const nameSlug = slugifyIdentifier(payload.name);
  const deviceNameSlug = slugifyIdentifier(payload.device_name);
  const deviceId = slugifyIdentifier(payload.device_id || deviceNameSlug);
  if (!deviceId) {
    throw new Error('Unable to determine a device ID. Adjust the advanced device ID field.');
  }
  const entityIdValue = payload.entity_id || '';
  if (!entityIdValue) {
    throw new Error('Provide an entity ID before previewing the discovery payload.');
  }
  const uniqueCandidate = payload.unique_id || `${deviceId}_${nameSlug}`;
  const uniqueId = slugifyIdentifier(uniqueCandidate);
  if (!uniqueId) {
    throw new Error('Unable to determine a unique ID. Adjust the advanced unique ID field.');
  }
  const objectId = slugifyIdentifier(payload.object_id || uniqueId);
  const nodeId = slugifyIdentifier(payload.node_id || '') || 'hassems';
  const stateTopic =
    payload.state_topic || buildStateTopic(nodeId, deviceId, payload.name);
  const availabilityTopic =
    payload.availability_topic || buildAvailabilityTopic(nodeId, deviceId, payload.name);

  const identifiers = Array.isArray(payload.device_identifiers)
    ? payload.device_identifiers.filter(Boolean)
    : [];
  if (!identifiers.length) {
    identifiers.push(`${nodeId || 'hassems'}:${uniqueId}`);
  }

  return {
    ...payload,
    unique_id: uniqueId,
    object_id: objectId,
    node_id: nodeId,
    device_id: deviceId,
    state_topic: stateTopic,
    availability_topic: availabilityTopic,
    device_identifiers: identifiers,
    force_update: payload.force_update !== false,
    device_manufacturer: payload.device_manufacturer || 'HASSEMS',
  };
}

function buildDiscoveryPreviewPayload(helper) {
  const stateTopic = helper.state_topic;
  const payload = {
    name: helper.name,
    unique_id: helper.unique_id,
    object_id: helper.object_id,
    state_topic: stateTopic,
    availability_topic: helper.availability_topic,
    payload_available: 'online',
    payload_not_available: 'offline',
    force_update: helper.force_update !== false,
    value_template: valueTemplateFor(helper.type),
    json_attributes_topic: stateTopic,
    json_attributes_template: "{{ {'measured_at': value_json.measured_at} | tojson }}",
    device: {
      identifiers: helper.device_identifiers,
      name: helper.device_name,
    },
  };

  if (helper.device_class) {
    payload.device_class = helper.device_class;
  }
  if (helper.unit_of_measurement) {
    payload.unit_of_measurement = helper.unit_of_measurement;
  }
  const stateClass = helper.state_class || (helper.type === 'input_number' ? 'measurement' : undefined);
  if (stateClass) {
    payload.state_class = stateClass;
  }
  if (helper.icon) {
    payload.icon = helper.icon;
  }
  if (helper.device_manufacturer) {
    payload.device.manufacturer = helper.device_manufacturer;
  }
  if (helper.device_model) {
    payload.device.model = helper.device_model;
  }
  if (helper.device_sw_version) {
    payload.device.sw_version = helper.device_sw_version;
  }

  return removeUndefined(payload);
}

function valueTemplateFor(helperType) {
  if (helperType === 'input_number') {
    return '{{ value_json.value | float }}';
  }
  if (helperType === 'input_boolean') {
    return '{{ value_json.value | lower }}';
  }
  return '{{ value_json.value }}';
}

function closeDiscoveryPreview() {
  discoveryPreview.value = null;
}

function onDiscoveryDialogClose() {
  discoveryPreview.value = null;
}

function populateUpdateForm(helper) {
  Object.assign(updateForm, {
    device_name: helper.device_name ?? '',
    name: helper.name ?? '',
    description: helper.description ?? '',
    entity_id: helper.entity_id ?? '',
    default_value: helper.default_value ?? '',
    options: helper.type === 'input_select' ? (helper.options || []).join(', ') : '',
    component: helper.component ?? 'sensor',
    device_class: helper.device_class ?? '',
    unit_of_measurement: helper.unit_of_measurement ?? '',
    icon: helper.icon ?? '',
    state_class: helper.state_class ?? (helper.type === 'input_number' ? 'measurement' : ''),
    unique_id: helper.unique_id ?? '',
    object_id: helper.object_id ?? '',
    device_id: helper.device_id ?? slugifyIdentifier(helper.device_name ?? ''),
    node_id: helper.node_id ?? 'hassems',
    state_topic: helper.state_topic ?? '',
    availability_topic: helper.availability_topic ?? '',
    device_manufacturer: helper.device_manufacturer ?? '',
    device_model: helper.device_model ?? '',
    device_sw_version: helper.device_sw_version ?? '',
    device_identifiers: (helper.device_identifiers || []).join(', '),
    force_update: helper.force_update !== false,
  });
}

function resetUpdateForm() {
  Object.assign(updateForm, {
    device_name: '',
    name: '',
    description: '',
    entity_id: '',
    default_value: '',
    options: '',
    component: 'sensor',
    device_class: '',
    unit_of_measurement: '',
    icon: '',
    state_class: '',
    unique_id: '',
    object_id: '',
    device_id: '',
    node_id: 'hassems',
    state_topic: '',
    availability_topic: '',
    device_manufacturer: '',
    device_model: '',
    device_sw_version: '',
    device_identifiers: '',
    force_update: true,
  });
}

async function updateHelper() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to edit.', 'error');
    return;
  }
  try {
    const payload = buildUpdatePayload(helper.type);
    const updated = await requestJson(`/inputs/${helper.slug}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    showToast('Entity updated.', 'success');
    helpers.value = helpers.value.map((item) => (item.slug === updated.slug ? updated : item));
    selectedSlug.value = updated.slug;
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function buildUpdatePayload(helperType) {
  const payload = {
    name: updateForm.name?.trim(),
    entity_id: updateForm.entity_id?.trim(),
    description: updateForm.description?.trim() || null,
    default_value: null,
    component: updateForm.component?.trim() || null,
    unique_id: slugifyIdentifier(updateForm.unique_id?.trim() || '') || null,
    object_id: slugifyIdentifier(updateForm.object_id?.trim() || '') || null,
    node_id: slugifyIdentifier(updateForm.node_id?.trim() || '') || null,
    state_topic: updateForm.state_topic?.trim(),
    availability_topic: updateForm.availability_topic?.trim(),
    icon: updateForm.icon?.trim() || null,
    device_class: updateForm.device_class?.trim() || null,
    unit_of_measurement: updateForm.unit_of_measurement?.trim() || null,
    state_class: updateForm.state_class?.trim() || null,
    force_update: Boolean(updateForm.force_update),
    device_name: updateForm.device_name?.trim(),
    device_id: slugifyIdentifier(updateForm.device_id?.trim() || '') || null,
    device_manufacturer: updateForm.device_manufacturer?.trim() || null,
    device_model: updateForm.device_model?.trim() || null,
    device_sw_version: updateForm.device_sw_version?.trim() || null,
  };

  const defaultRaw = updateForm.default_value?.trim();
  if (defaultRaw) {
    payload.default_value = coerceValue(helperType, defaultRaw);
  }

  if (helperType === 'input_select') {
    const options = parseCsv(updateForm.options || '');
    if (options.length) {
      payload.options = options;
    }
  }

  const identifiersRaw = updateForm.device_identifiers ?? '';
  const trimmed = identifiersRaw.trim();
  payload.device_identifiers = trimmed ? parseCsv(trimmed) : [];

  return removeUndefined(payload);
}

async function deleteHelper() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to delete.', 'error');
    return;
  }
  const confirmed = window.confirm(`Delete ${helper.name}? This action cannot be undone.`);
  if (!confirmed) {
    return;
  }
  try {
    await requestJson(`/inputs/${helper.slug}`, { method: 'DELETE' });
    helpers.value = helpers.value.filter((item) => item.slug !== helper.slug);
    selectedSlug.value = null;
    showToast('Entity deleted.', 'success');
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function exampleValueFor(helper) {
  if (!helper) {
    return 'example';
  }
  const fallback = helper.last_value ?? helper.default_value ?? null;
  if (helper.type === 'input_boolean') {
    if (fallback !== null && fallback !== undefined) {
      const normalized = String(fallback).toLowerCase();
      if (['true', 'on', '1', 'yes'].includes(normalized)) return true;
      if (['false', 'off', '0', 'no'].includes(normalized)) return false;
    }
    return true;
  }
  if (helper.type === 'input_number') {
    if (fallback !== null && fallback !== undefined) {
      const parsed = Number(fallback);
      if (Number.isFinite(parsed)) {
        return parsed;
      }
    }
    return 0;
  }
  if (helper.type === 'input_select') {
    const options = Array.isArray(helper.options) ? helper.options : [];
    if (options.length) {
      return options[0];
    }
    if (fallback !== null && fallback !== undefined && String(fallback).trim() !== '') {
      return String(fallback);
    }
    return 'choice';
  }
  if (fallback !== null && fallback !== undefined && String(fallback).trim() !== '') {
    return String(fallback);
  }
  return 'example';
}

function populateValueForm(helper) {
  if (helper.type === 'input_boolean') {
    if (helper.last_value === true || helper.last_value === 'true') {
      valueForm.value = 'true';
    } else if (helper.last_value === false || helper.last_value === 'false') {
      valueForm.value = 'false';
    } else {
      valueForm.value = 'false';
    }
  } else if (helper.type === 'input_number') {
    valueForm.value = helper.last_value ?? '';
  } else {
    valueForm.value = helper.last_value ?? '';
  }
  setMeasuredInputsToNow();
}

function clearValueForm() {
  valueForm.value = '';
  valueForm.measured_date = '';
  valueForm.measured_time = '';
}

async function submitValue() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to update.', 'error');
    return;
  }
  try {
    const payload = {
      value: coerceValue(helper.type, valueForm.value),
    };
    const customDate = valueForm.measured_date?.trim();
    const customTime = valueForm.measured_time?.trim();
    if (customDate || customTime) {
      if (!customDate) {
        throw new Error('Provide a measurement date.');
      }
      const timePortion = customTime || '00:00';
      const parsed = new Date(`${customDate}T${timePortion}`);
      if (Number.isNaN(parsed.getTime())) {
        throw new Error('Provide a valid measured at timestamp.');
      }
      payload.measured_at = parsed.toISOString();
    } else {
      payload.measured_at = new Date().toISOString();
      setMeasuredInputsToNow();
    }
    const updated = await requestJson(`/inputs/${helper.slug}/set`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    showToast('Value sent to MQTT.', 'success');
    helpers.value = helpers.value.map((item) => (item.slug === updated.slug ? updated : item));
    selectedSlug.value = updated.slug;
    await loadHistory(updated.slug);
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

async function loadHistory(slug) {
  try {
    const history = await requestJson(`/inputs/${slug}/history`);
    historyRecords.value = Array.isArray(history) ? history : [];
  } catch (error) {
    showToast(`Failed to load history: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

function renderHistory(helper, history) {
  destroyChart();
  if (!history || !history.length) {
    historyMode.value = 'empty';
    historyList.value = [];
    return;
  }
  const labels = history.map((item) => formatTimestamp(item.measured_at));
  const numericValues = history.map((item) => normalizeHistoryValue(helper.type, item.value));
  const allNumeric = numericValues.every((value) => value !== null && !Number.isNaN(value));
  if (allNumeric && historyCanvas.value) {
    historyMode.value = 'chart';
    const dataset = numericValues.map((value) => Number(value));
  const yScaleOptions = helper.type === 'input_boolean'
    ? {
        ticks: {
          callback: (value) => (value === 1 ? 'On' : 'Off'),
          stepSize: 1,
        },
        suggestedMin: 0,
        suggestedMax: 1,
      }
    : {};
    chartInstance.value = new Chart(historyCanvas.value, {
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
            ...yScaleOptions,
          },
        },
        plugins: {
          legend: { display: false },
        },
      },
    });
    return;
  }
  historyMode.value = 'list';
  historyList.value = history.map((item) => ({
    measured_at: formatTimestamp(item.measured_at),
    value: String(item.value ?? '—'),
  }));
}

function destroyChart() {
  if (chartInstance.value) {
    chartInstance.value.destroy();
    chartInstance.value = null;
  }
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
  const prefix = (mqttConfig.value?.discovery_prefix || mqttForm.discovery_prefix || 'homeassistant').replace(/\/+$/, '');
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
  return Object.fromEntries(
    Object.entries(payload).filter(([, value]) => value !== undefined),
  );
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
  return String(rawValue);
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

function setMeasuredInputsToNow(referenceDate = new Date()) {
  const pad = (input) => String(input).padStart(2, '0');
  const year = referenceDate.getFullYear();
  const month = pad(referenceDate.getMonth() + 1);
  const day = pad(referenceDate.getDate());
  const hours = pad(referenceDate.getHours());
  const minutes = pad(referenceDate.getMinutes());
  valueForm.measured_date = `${year}-${month}-${day}`;
  valueForm.measured_time = `${hours}:${minutes}`;
}

async function requestJson(url, options = {}) {
  const fullUrl = url.startsWith('/api') ? url : `/api${url}`;
  const response = await fetch(fullUrl, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) {
    return null;
  }
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  if (!response.ok) {
    let message = response.statusText;
    if (isJson) {
      try {
        const data = await response.json();
        message = data?.detail || data?.message || message;
      } catch (error) {
        // ignore JSON parsing errors
      }
    }
    throw new Error(message);
  }
  if (!isJson) {
    return null;
  }
  return response.json();
}

function showToast(message, type = 'info') {
  toast.message = message;
  toast.type = type;
  toast.visible = true;
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  toastTimer = setTimeout(() => {
    toast.visible = false;
  }, 3500);
}

function slugifyIdentifier(value) {
  if (!value) return '';
  return value
    .toString()
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9_]+/g, '_')
    .replace(/_+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function buildStateTopic(nodeId, deviceId, entityName) {
  const node = slugifyIdentifier(nodeId) || 'hassems';
  const device = slugifyIdentifier(deviceId);
  const entity = slugifyIdentifier(entityName);
  if (!device || !entity) return '';
  return `${node}/${device}/${entity}/state`;
}

function buildAvailabilityTopic(nodeId, deviceId, entityName) {
  const node = slugifyIdentifier(nodeId) || 'hassems';
  const device = slugifyIdentifier(deviceId);
  const entity = slugifyIdentifier(entityName);
  if (!device || !entity) return '';
  return `${node}/${device}/${entity}/availability`;
}

onMounted(async () => {
  resetCreateForm();
  await loadMqttConfig();
  await loadHelpers();
});

onBeforeUnmount(() => {
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  destroyChart();
});
</script>
