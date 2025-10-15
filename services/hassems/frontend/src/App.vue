
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

      <section class="card" id="users-card" v-if="activePage === 'settings'">
        <div class="card__header">
          <div>
            <h2>API Users</h2>
            <p class="card__subtitle">
              Generate tokens for Home Assistant and trusted services to access the HASSEMS API.
            </p>
          </div>
          <div class="card__actions">
            <button class="btn" type="button" @click="loadApiUsers">Refresh</button>
            <button class="btn primary" type="button" @click="openUserDialog()">New user</button>
          </div>
        </div>

        <p class="card__subtitle">
          The built-in superuser token is always available and cannot be removed.
        </p>

        <div v-if="apiUsers.length" class="entity-table-wrapper">
          <table class="entity-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Token</th>
                <th scope="col" class="actions-column">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="user in apiUsers" :key="user.id">
                <td>
                  <div class="entity-name">
                    <span class="entity-name__primary">{{ user.name }}</span>
                    <span v-if="user.is_superuser" class="entity-name__badge">Superuser</span>
                  </div>
                </td>
                <td><code>{{ user.token }}</code></td>
                <td class="actions-cell">
                  <div class="button-group">
                    <button class="btn" type="button" @click.stop="openUserDialog(user)">Edit</button>
                    <button
                      class="btn danger"
                      type="button"
                      @click.stop="deleteUser(user)"
                      :disabled="user.is_superuser"
                    >
                      Delete
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="card__subtitle">No API users created yet.</p>
      </section>

      <section class="card" id="integrations-card" v-if="activePage === 'settings'">
        <div class="card__header">
          <div>
            <h2>Home Assistant integrations</h2>
            <p class="card__subtitle">
              Connected Home Assistant instances using the HASSEMS integration.
            </p>
          </div>
          <div class="card__actions">
            <button class="btn" type="button" @click="loadIntegrationConnections">Refresh</button>
          </div>
        </div>

        <div v-if="integrationConnections.length" class="entity-table-wrapper">
          <table class="entity-table">
            <thead>
              <tr>
                <th scope="col">Name</th>
                <th scope="col">Entry ID</th>
                <th scope="col">API user</th>
                <th scope="col">Helpers</th>
                <th scope="col">Last seen</th>
                <th scope="col" class="actions-column">Actions</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="connection in integrationConnections" :key="connection.entry_id">
                <td>{{ connection.title || 'Home Assistant' }}</td>
                <td><code>{{ connection.entry_id }}</code></td>
                <td>{{ connection.owner?.name || 'Unknown' }}</td>
                <td>{{ connection.helper_count }}</td>
                <td>{{ connection.last_seen ? formatTimestamp(connection.last_seen) : '—' }}</td>
                <td class="actions-cell">
                  <div class="button-group">
                    <button class="btn" type="button" @click.stop="openConnectionDialog(connection, 'history')">
                      View history
                    </button>
                    <button class="btn" type="button" @click.stop="openConnectionDialog(connection, 'config')">
                      View config
                    </button>
                  </div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <p v-else class="card__subtitle">No Home Assistant integrations have connected yet.</p>
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
                <th scope="col">Entity type</th>
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
                <td>{{ entityTransportLabels[helper.entity_type] || helper.entity_type }}</td>
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
            <button
              class="icon-button"
              type="button"
              @click="openEditDialog"
              aria-label="Edit entity"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path
                  d="M16.862 3.487a1.75 1.75 0 0 1 2.475 0l1.176 1.176a1.75 1.75 0 0 1 0 2.475l-9.9 9.9a1.75 1.75 0 0 1-.74.434l-4.01 1.147a.75.75 0 0 1-.92-.92l1.147-4.01a1.75 1.75 0 0 1 .434-.74l9.9-9.9Zm-2.475 2.475-9.9 9.9a.25.25 0 0 0-.062.106l-.84 2.934 2.934-.84a.25.25 0 0 0 .106-.062l9.9-9.9-2.138-2.138Zm3.243-1.06a.25.25 0 0 0-.354 0l-1.06 1.06 2.138 2.138 1.06-1.06a.25.25 0 0 0 0-.354l-1.176-1.176a.25.25 0 0 0-.354 0Z"
                />
              </svg>
            </button>
            <button class="btn" type="button" @click="openApiDialog">Call app</button>
            <button class="btn danger" type="button" @click="deleteHelper">Delete</button>
          </div>
        </div>

        <div class="entity-summary">
          <dl class="detail-list" aria-labelledby="detail-title">
            <div
              v-for="field in detailFields"
              :key="field.key"
              class="detail-list__item"
            >
              <dt>{{ field.label }}</dt>
              <dd
                :class="[
                  'detail-list__value',
                  {
                    'detail-list__value--empty': field.isEmpty,
                    'detail-list__value--wrap': field.wrap,
                  },
                ]"
              >
                {{ field.value }}
              </dd>
            </div>
          </dl>
        </div>

        <div class="helper-status">
          <p><strong>Last value:</strong> <span id="detail-last-value">{{ selectedHelper?.last_value ?? '—' }}</span></p>
          <p><strong>Measured at:</strong> <span id="detail-measured-at">{{ selectedMeasuredAt }}</span></p>
          <p>
            <strong>Recorded (diagnostic only):</strong>
            <span id="detail-updated">{{ selectedUpdatedAt }}</span>
          </p>
          <p
            v-if="selectedHelper?.entity_type === 'hassems' && selectedHelper?.history_cursor"
            class="helper-status__history-cursor"
          >
            <strong>History cursor:</strong>
            <code>{{ selectedHelper.history_cursor }}</code>
            <span v-if="selectedHelper.history_changed_at" class="helper-status__history-cursor-updated">
              (updated {{ formatTimestamp(selectedHelper.history_changed_at) }})
            </span>
          </p>
        </div>

        <div
          v-if="selectedHelper?.history_cursor_events?.length"
          class="helper-status__timeline"
        >
          <h4>Historic cursor timeline</h4>
          <ul>
            <li
              v-for="event in selectedHelper.history_cursor_events"
              :key="`${event.history_cursor}-${event.changed_at}`"
            >
              <code>{{ event.history_cursor }}</code>
              <span>{{ formatTimestamp(event.changed_at) }}</span>
            </li>
          </ul>
        </div>

        <div class="divider"></div>

        <section class="history">
          <div class="history__header">
            <h3>Recent values</h3>
            <button
              class="icon-button"
              type="button"
              @click="openHistoryDialog"
              aria-label="Edit history entries"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path
                  d="M16.862 3.487a1.75 1.75 0 0 1 2.475 0l1.176 1.176a1.75 1.75 0 0 1 0 2.475l-9.9 9.9a1.75 1.75 0 0 1-.74.434l-4.01 1.147a.75.75 0 0 1-.92-.92l1.147-4.01a1.75 1.75 0 0 1 .434-.74l9.9-9.9Zm-2.475 2.475-9.9 9.9a.25.25 0 0 0-.062.106l-.84 2.934 2.934-.84a.25.25 0 0 0 .106-.062l9.9-9.9-2.138-2.138Zm3.243-1.06a.25.25 0 0 0-.354 0l-1.06 1.06 2.138 2.138 1.06-1.06a.25.25 0 0 0 0-.354l-1.176-1.176a.25.25 0 0 0-.354 0Z"
                />
              </svg>
            </button>
          </div>
          <div v-show="historyMode === 'chart'" class="history__chart-wrapper">
            <button
              type="button"
              class="icon-button history__debug-button"
              @click="openHistoryDebugDialog"
              aria-label="View chart dataset"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                <path
                  d="M11 2a1 1 0 0 1 1 1v1.055a7.002 7.002 0 0 1 5.945 5.945H19a1 1 0 1 1 0 2h-1.055a7.002 7.002 0 0 1-5.945 5.945V21a1 1 0 1 1-2 0v-1.055A7.002 7.002 0 0 1 4.055 12H3a1 1 0 1 1 0-2h1.055A7.002 7.002 0 0 1 11 4.055V3a1 1 0 0 1 1-1Zm0 5a5 5 0 1 0 0 10a5 5 0 0 0 0-10Zm0 3a1 1 0 0 1 1 1v2.382l.724.724a1 1 0 0 1-1.448 1.382l-1-1A1 1 0 0 1 10 14v-3a1 1 0 0 1 1-1Z"
                />
              </svg>
            </button>
            <canvas id="history-chart" height="220" ref="historyCanvas"></canvas>
          </div>
          <ul v-if="historyMode === 'list'" id="history-list" class="history-list">
            <li v-for="item in historyList" :key="item.key">
              <div class="history-list__row">
                <span class="history-list__timestamp">{{ item.measured_at }}</span>
                <span class="history-list__value">{{ item.value }}</span>
                <span v-if="item.historic" class="history-list__badge">Historic</span>
              </div>
              <span
                v-if="item.historyCursor"
                :class="['history-list__cursor', { 'history-list__cursor--change': item.historyChange }]"
              >
                Historic cursor: <code>{{ item.historyCursor }}</code>
              </span>
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
            <button class="btn primary" type="submit">{{ valueSubmitLabel }}</button>
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
      ref="connectionDialog"
      class="modal"
      @cancel.prevent="closeConnectionDialog"
      @close="onConnectionDialogClose"
    >
      <div class="modal__container">
        <div class="modal__header">
          <h3>
            {{
              connectionDialogMode === 'history'
                ? 'Integration history'
                : 'Integration configuration'
            }}
          </h3>
          <button
            type="button"
            class="modal__close"
            @click="closeConnectionDialog"
            aria-label="Close integration dialog"
          >
            ×
          </button>
        </div>
        <div class="modal__body">
          <p v-if="connectionDetailLoading" class="modal__subtitle">Loading integration details…</p>
          <template v-else-if="connectionDetail">
            <template v-if="connectionDialogMode === 'history'">
              <p class="modal__subtitle">
                Recent helper values received from
                {{ connectionDetail.title || connectionDetail.entry_id }}.
              </p>
              <p v-if="connectionHistoryLoading" class="modal__subtitle">Loading history…</p>
              <ul
                v-else-if="connectionHistory.length"
                class="history-list"
              >
                <li
                  v-for="item in connectionHistory"
                  :key="`${item.helper_slug}-${item.recorded_at}`"
                >
                  <div class="history-list__row">
                    <span class="history-list__timestamp">
                      {{ item.helper_name }} ·
                      {{ formatTimestamp(item.measured_at || item.recorded_at) }}
                    </span>
                    <span class="history-list__value">{{ item.value ?? '—' }}</span>
                    <span v-if="item.historic" class="history-list__badge">Historic</span>
                  </div>
                  <span
                    v-if="item.historic_cursor"
                    class="history-list__cursor"
                  >
                    Historic cursor: <code>{{ item.historic_cursor }}</code>
                  </span>
                  <span class="history-list__recorded-note">
                    Recorded (diagnostic): {{ formatTimestamp(item.recorded_at) }}
                  </span>
                </li>
              </ul>
              <p v-else class="modal__subtitle">No history available for this integration.</p>
            </template>
            <template v-else>
              <p class="modal__subtitle">
                Configuration details for
                {{ connectionDetail.title || connectionDetail.entry_id }}.
              </p>
              <dl class="detail-list detail-list--modal">
                <div class="detail-list__item">
                  <dt>Entry ID</dt>
                  <dd class="detail-list__value detail-list__value--wrap">
                    <code>{{ connectionDetail.entry_id }}</code>
                  </dd>
                </div>
                <div class="detail-list__item">
                  <dt>API user</dt>
                  <dd class="detail-list__value">
                    {{ connectionDetail.owner?.name || 'Unknown' }}
                  </dd>
                </div>
                <div class="detail-list__item">
                  <dt>Included helpers</dt>
                  <dd class="detail-list__value detail-list__value--wrap">
                    {{ formattedIncludedHelpers }}
                  </dd>
                </div>
                <div class="detail-list__item">
                  <dt>Ignored helpers</dt>
                  <dd class="detail-list__value detail-list__value--wrap">
                    {{ formattedIgnoredHelpers }}
                  </dd>
                </div>
                <div class="detail-list__item">
                  <dt>Helpers synced</dt>
                  <dd class="detail-list__value">{{ connectionDetail.helper_count }}</dd>
                </div>
                <div class="detail-list__item">
                  <dt>Last seen</dt>
                  <dd class="detail-list__value">
                    {{ connectionDetail.last_seen ? formatTimestamp(connectionDetail.last_seen) : '—' }}
                  </dd>
                </div>
                <template v-for="item in connectionMetadataDetails" :key="item.label">
                  <div class="detail-list__item">
                    <dt>{{ item.label }}</dt>
                    <dd class="detail-list__value detail-list__value--wrap">
                      {{ item.value }}
                    </dd>
                  </div>
                </template>
              </dl>
            </template>
          </template>
          <p v-else class="modal__subtitle">
            {{
              connectionDialogMode === 'history'
                ? 'Select an integration to load history.'
                : 'Select an integration to view configuration.'
            }}
          </p>
        </div>
        <div class="modal__actions">
          <button type="button" class="btn" @click="closeConnectionDialog">Close</button>
          <button
            v-if="connectionDetail"
            class="btn"
            type="button"
            @click="toggleConnectionDialogMode"
          >
            {{ connectionDialogMode === 'history' ? 'View config' : 'View history' }}
          </button>
        </div>
      </div>
    </dialog>

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
              <fieldset class="form-field full-width entity-type-field">
                <legend class="label-text">
                  Entity type
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Choose MQTT to sync with Home Assistant via the broker or HASSEMS to store values locally."
                  >?
                  </button>
                </legend>
                <div class="entity-type-toggle">
                  <label :class="['toggle-button', { active: createForm.entity_type === 'mqtt' }]">
                    <input v-model="createForm.entity_type" type="radio" value="mqtt" />
                    MQTT
                  </label>
                  <label :class="['toggle-button', { active: createForm.entity_type === 'hassems' }]">
                    <input v-model="createForm.entity_type" type="radio" value="hassems" />
                    HASSEMS
                  </label>
                </div>
              </fieldset>
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
                <label v-if="createForm.entity_type === 'hassems'" class="form-field">
                  <span class="label-text">
                    Statistics mode
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Controls how HASSEMS calculates hourly statistics when syncing with Home Assistant."
                    >?
                    </button>
                  </span>
                  <select v-model="createForm.statistics_mode">
                    <option
                      v-for="option in statisticsModeOptions"
                      :key="`create-statistics-${option.value}`"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label v-if="createForm.entity_type === 'hassems'" class="form-checkbox">
                  <input v-model="createForm.ha_enabled" type="checkbox" />
                  <span class="label-text">
                    Enable in Home Assistant
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Expose this entity to the Home Assistant integration. Disable to stage data before discovery."
                    >?
                    </button>
                  </span>
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
                <label v-if="isCreateMqtt" class="form-field">
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
                <label v-if="isCreateMqtt" class="form-field">
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
                    placeholder="hassems/child_metrics/input_number.child_metrics_height/state"
                    @input="createAutoFlags.stateTopic = false"
                  />
                </label>
                <label v-if="isCreateMqtt" class="form-field">
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
                    placeholder="hassems/child_metrics/input_number.child_metrics_height/availability"
                    @input="createAutoFlags.availabilityTopic = false"
                  />
                </label>
                <label v-if="isCreateMqtt" class="form-field">
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
                <label v-if="isCreateMqtt" class="form-field">
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
                <label v-if="isCreateMqtt" class="form-field">
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
                <label v-if="isCreateMqtt" class="form-field full-width">
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
              <label v-if="isCreateMqtt" class="form-checkbox">
                <input v-model="createForm.force_update" type="checkbox" />
                <span class="label-text">
                  Force update
                  <button
                    type="button"
                    class="help-icon"
                    data-tooltip="Emit state_changed events even when the value is unchanged. Useful for clean charts."
                  >?</button>
                </span>
              </label>
            </details>
          </div>
          <div class="modal__actions">
            <button class="btn primary" type="submit">Create entity</button>
            <button v-if="isCreateMqtt" class="btn" type="button" @click="previewDiscovery">Preview discovery</button>
          </div>
        </form>
      </div>
    </dialog>

    <dialog
      ref="editDialog"
      class="modal"
      @cancel.prevent="closeEditDialog"
      @close="onEditDialogClose"
    >
      <template v-if="selectedHelper">
        <div class="modal__container">
          <div class="modal__header">
            <h3>Edit entity</h3>
            <button
              type="button"
              class="modal__close"
              @click="closeEditDialog"
              aria-label="Close edit entity dialog"
            >
              ×
            </button>
          </div>
          <form class="modal__form" id="update-helper-form" @submit.prevent="updateHelper">
            <div class="modal__body">
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
                <label class="form-field full-width">
                  <span class="label-text">
                    Description
                    <button type="button" class="help-icon" data-tooltip="Reference notes about the entity.">?</button>
                  </span>
                  <textarea v-model="updateForm.description" rows="3"></textarea>
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
                    Entity type
                    <button type="button" class="help-icon" data-tooltip="Indicates whether the entity syncs over MQTT or is stored within HASSEMS.">?</button>
                  </span>
                  <input :value="selectedEntityTypeLabel" type="text" readonly />
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
                <label
                  v-if="selectedHelper?.entity_type === 'hassems'"
                  class="form-field"
                >
                  <span class="label-text">
                    Statistics mode
                    <button type="button" class="help-icon" data-tooltip="Controls how HASSEMS calculates hourly statistics when syncing with Home Assistant.">?</button>
                  </span>
                  <select v-model="updateForm.statistics_mode">
                    <option
                      v-for="option in statisticsModeOptions"
                      :key="`update-statistics-${option.value}`"
                      :value="option.value"
                    >
                      {{ option.label }}
                    </option>
                  </select>
                </label>
                <label
                  v-if="selectedHelper?.entity_type === 'hassems'"
                  class="form-checkbox"
                >
                  <input v-model="updateForm.ha_enabled" type="checkbox" />
                  <span class="label-text">
                    Enable in Home Assistant
                    <button
                      type="button"
                      class="help-icon"
                      data-tooltip="Expose this entity to the Home Assistant integration. Disable to hide it from discovery."
                    >?
                    </button>
                  </span>
                </label>
                <label
                  v-if="selectedHelper?.type === 'input_select'"
                  class="form-field full-width"
                >
                  <span class="label-text">
                    Options (comma separated)
                    <button type="button" class="help-icon" data-tooltip="Comma-delimited options for input_select helpers.">?</button>
                  </span>
                  <input v-model="updateForm.options" type="text" placeholder="short,average,tall" />
                </label>
              </div>

              <details class="form-advanced">
                <summary>Advanced configuration</summary>
                <div class="form-grid">
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
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      Node ID
                      <button type="button" class="help-icon" data-tooltip="Optional discovery topic folder.">?</button>
                    </span>
                    <input v-model="updateForm.node_id" type="text" placeholder="hassems" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      State topic
                      <button type="button" class="help-icon" data-tooltip="Topic where values are published.">?</button>
                    </span>
                    <input v-model="updateForm.state_topic" type="text" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      Availability topic
                      <button type="button" class="help-icon" data-tooltip="Topic reflecting device availability.">?</button>
                    </span>
                    <input v-model="updateForm.availability_topic" type="text" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      Device manufacturer
                      <button type="button" class="help-icon" data-tooltip="Manufacturer metadata for the device.">?</button>
                    </span>
                    <input v-model="updateForm.device_manufacturer" type="text" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      Device model
                      <button type="button" class="help-icon" data-tooltip="Model identifier used by Home Assistant.">?</button>
                    </span>
                    <input v-model="updateForm.device_model" type="text" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field"
                  >
                    <span class="label-text">
                      Device firmware
                      <button type="button" class="help-icon" data-tooltip="Software or firmware version string.">?</button>
                    </span>
                    <input v-model="updateForm.device_sw_version" type="text" />
                  </label>
                  <label
                    v-if="isUpdateMqtt"
                    class="form-field full-width"
                  >
                    <span class="label-text">
                      Device identifiers
                      <button type="button" class="help-icon" data-tooltip="Comma-separated identifiers for the parent device.">?</button>
                    </span>
                    <input v-model="updateForm.device_identifiers" type="text" />
                  </label>
                </div>
                <label v-if="isUpdateMqtt" class="form-checkbox">
                  <input v-model="updateForm.force_update" type="checkbox" />
                  <span class="label-text">
                    Force update
                    <button type="button" class="help-icon" data-tooltip="Emit state_changed events even when the value is unchanged.">?</button>
                  </span>
                </label>
              </details>
            </div>

            <div class="modal__actions">
              <button class="btn primary" type="submit">Save changes</button>
            </div>
          </form>
        </div>
      </template>
    </dialog>

    <dialog
      ref="historyDialog"
      class="modal"
      @cancel.prevent="closeHistoryDialog"
      @close="onHistoryDialogClose"
    >
      <template v-if="selectedHelper">
        <div class="modal__container">
          <div class="modal__header">
            <h3>Edit history entries</h3>
            <button
              type="button"
              class="modal__close"
              @click="closeHistoryDialog"
              aria-label="Close history editor"
            >
              ×
            </button>
          </div>
          <div class="modal__body history-editor-body">
            <p class="modal__subtitle">
              Adjust recorded values for <strong>{{ selectedHelper.name }}</strong> or remove entries you no longer need.
            </p>
            <div v-if="historyEditorRows.length" class="history-editor-wrapper">
              <table class="history-editor-table">
                <thead>
                  <tr>
                    <th scope="col">Measured at</th>
                    <th scope="col">Value</th>
                    <th scope="col">Historic?</th>
                    <th scope="col">Historic cursor</th>
                    <th scope="col">Recorded (diagnostic)</th>
                    <th scope="col" class="history-editor-actions-header">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="row in historyEditorRows" :key="row.id">
                    <td data-label="Measured at">
                      <input type="datetime-local" v-model="row.measuredInput" />
                    </td>
                    <td data-label="Value">
                      <template v-if="valueInputType === 'boolean'">
                        <select v-model="row.valueInput">
                          <option value="false">Off</option>
                          <option value="true">On</option>
                        </select>
                      </template>
                      <template v-else-if="valueInputType === 'number'">
                        <input type="number" v-model="row.valueInput" />
                      </template>
                      <template v-else-if="valueInputType === 'select'">
                        <select v-model="row.valueInput">
                          <option v-for="option in valueOptions" :key="option" :value="option">
                            {{ option }}
                          </option>
                        </select>
                      </template>
                      <template v-else>
                        <input type="text" v-model="row.valueInput" />
                      </template>
                    </td>
                    <td data-label="Historic?">
                      <span>{{ row.historic ? 'Yes' : 'No' }}</span>
                    </td>
                    <td data-label="Historic cursor">
                      <template v-if="row.historicCursor">
                        <code>{{ row.historicCursor }}</code>
                      </template>
                      <span v-else>—</span>
                    </td>
                    <td data-label="Recorded (diagnostic)">
                      <span>{{ row.recordedDisplay }}</span>
                    </td>
                    <td data-label="Actions">
                      <div class="history-editor-actions">
                        <button
                          class="btn small"
                          type="button"
                          @click="saveHistoryRow(row)"
                          :disabled="row.saving || row.deleting"
                        >
                          {{ row.saving ? 'Saving…' : 'Save' }}
                        </button>
                        <button
                          class="btn danger small"
                          type="button"
                          @click="deleteHistoryRow(row)"
                          :disabled="row.saving || row.deleting"
                        >
                          {{ row.deleting ? 'Deleting…' : 'Delete' }}
                        </button>
                      </div>
                      <p v-if="row.error" class="history-editor-error">{{ row.error }}</p>
                    </td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p v-else class="modal__subtitle">No history has been recorded for this entity yet.</p>
          </div>
          <div class="modal__actions">
            <button type="button" class="btn" @click="closeHistoryDialog">Close</button>
          </div>
        </div>
      </template>
    </dialog>

    <dialog
      ref="historyDebugDialog"
      class="modal"
      @cancel.prevent="closeHistoryDebugDialog"
    >
      <div class="modal__container">
        <div class="modal__header">
          <h3>Chart dataset</h3>
          <button
            type="button"
            class="modal__close"
            @click="closeHistoryDebugDialog"
            aria-label="Close chart dataset dialog"
          >
            ×
          </button>
        </div>
        <div class="modal__body">
          <p class="modal__subtitle">
            JSON payload representing the exact data currently rendered in the chart.
          </p>
          <pre class="debug-json" aria-live="polite">{{ historyDebugJson }}</pre>
        </div>
        <div class="modal__actions">
          <button type="button" class="btn" @click="closeHistoryDebugDialog">Close</button>
        </div>
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

    <dialog ref="userDialog" class="modal" @cancel.prevent="closeUserDialog" @close="onUserDialogClose">
      <div class="modal__container">
        <div class="modal__header">
          <h3>{{ userDialogMode === 'edit' ? 'Edit API user' : 'New API user' }}</h3>
          <button type="button" class="modal__close" @click="closeUserDialog" aria-label="Close user dialog">×</button>
        </div>
        <form class="modal__form" @submit.prevent="submitUserForm">
          <div class="modal__body">
            <label class="form-field">
              <span class="label-text">Name</span>
              <input v-model="userForm.name" type="text" required placeholder="Automation service" />
            </label>
            <label class="form-field">
              <span class="label-text">
                API token
                <button
                  type="button"
                  class="help-icon"
                  data-tooltip="Tokens authenticate API clients. Store them securely and regenerate if compromised."
                >?
                </button>
              </span>
              <div class="token-input">
                <input
                  v-model="userForm.token"
                  type="text"
                  :required="userDialogMode === 'create'"
                  :disabled="userForm.is_superuser && userDialogMode === 'edit'"
                />
                <button
                  type="button"
                  class="btn"
                  @click="generateUserToken"
                  :disabled="
                    userTokenGenerating ||
                    userSaving ||
                    (userForm.is_superuser && userDialogMode === 'edit')
                  "
                >
                  {{ userTokenGenerating ? 'Generating…' : 'Generate token' }}
                </button>
              </div>
            </label>
            <p v-if="userForm.is_superuser" class="form-helper">
              The superuser token is fixed and cannot be modified or deleted.
            </p>
          </div>
          <div class="modal__actions">
            <button type="button" class="btn" @click="closeUserDialog">Cancel</button>
            <button class="btn primary" type="submit" :disabled="userSaving">
              {{ userSaving ? 'Saving…' : userDialogMode === 'edit' ? 'Save changes' : 'Create user' }}
            </button>
          </div>
        </form>
      </div>
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
import 'chartjs-adapter-luxon';

function debugLog(message, payload = undefined) {
  const prefix = '[HASSEMS dashboard]';
  if (payload !== undefined) {
    console.debug(prefix, message, payload);
  } else {
    console.debug(prefix, message);
  }
}

const helperTypeMap = {
  input_text: 'Input text',
  input_number: 'Input number',
  input_boolean: 'Input boolean',
  input_select: 'Input select',
};

const entityTransportLabels = {
  mqtt: 'MQTT',
  hassems: 'HASSEMS',
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

const statisticsModeOptions = [
  { value: 'linear', label: 'Linear interpolation' },
  { value: 'step', label: 'Step (hold last value)' },
  { value: 'point', label: 'Point (recorded hours only)' },
];

const statisticsModeValues = statisticsModeOptions.map((option) => option.value);

const statisticsModeLabels = Object.fromEntries(
  statisticsModeOptions.map((option) => [option.value, option.label]),
);

function normalizeStatisticsModeValue(value) {
  const text = typeof value === 'string' ? value.trim().toLowerCase() : '';
  return statisticsModeValues.includes(text) ? text : 'linear';
}

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

const apiUsers = ref([]);
const userDialog = ref(null);
const userDialogMode = ref('create');
const userTokenGenerating = ref(false);
const userSaving = ref(false);
const userForm = reactive({
  id: null,
  name: '',
  token: '',
  is_superuser: false,
});

const integrationConnections = ref([]);
const connectionDialog = ref(null);
const connectionDetail = ref(null);
const connectionDialogMode = ref('history');
const connectionDetailLoading = ref(false);
const connectionHistory = ref([]);
const connectionHistoryLoading = ref(false);
const selectedConnectionEntryId = ref(null);

const helpers = ref([]);
const selectedSlug = ref(null);
const historyRecords = ref([]);
const historyMode = ref('empty');
const historyList = ref([]);
const historyCanvas = ref(null);
const chartInstance = ref(null);
const historyDialog = ref(null);
const historyDialogVisible = ref(false);
const historyEditorRows = ref([]);
const historyDebugDialog = ref(null);
const historyChartDataset = ref([]);
const historyDebugJson = computed(() => JSON.stringify(historyChartDataset.value, null, 2));

const formattedIncludedHelpers = computed(() =>
  formatHelperList(connectionDetail.value?.included_helpers),
);
const formattedIgnoredHelpers = computed(() =>
  formatHelperList(connectionDetail.value?.ignored_helpers),
);
const connectionMetadataDetails = computed(() => {
  const detail = connectionDetail.value;
  const metadata = detail?.metadata;
  if (!metadata || typeof metadata !== 'object') {
    return [];
  }
  const entries = [];
  if (metadata.base_url) {
    entries.push({ label: 'HASSEMS URL', value: metadata.base_url });
  }
  if (metadata.webhook_id) {
    entries.push({ label: 'Webhook ID', value: metadata.webhook_id });
  }
  if (metadata.subscription_id) {
    entries.push({ label: 'Subscription ID', value: metadata.subscription_id });
  }
  const haMeta = metadata.home_assistant || {};
  if (haMeta.name) {
    entries.push({ label: 'Home Assistant name', value: haMeta.name });
  }
  if (haMeta.version) {
    entries.push({ label: 'Home Assistant version', value: haMeta.version });
  }
  if (haMeta.unit_system) {
    entries.push({ label: 'Unit system', value: haMeta.unit_system });
  }
  if (haMeta.time_zone) {
    entries.push({ label: 'Time zone', value: haMeta.time_zone });
  }
  return entries;
});

const discoveryPreview = ref(null);
const discoveryDialog = ref(null);
const createDialog = ref(null);
const editDialog = ref(null);
const apiDialog = ref(null);
const apiOrigin = typeof window !== 'undefined' && window.location ? window.location.origin : '';

function createCreateDefaults() {
  return {
    entity_type: 'mqtt',
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
    statistics_mode: 'linear',
    ha_enabled: true,
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
  statistics_mode: 'linear',
  ha_enabled: true,
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
const selectedEntityTypeLabel = computed(() => {
  const helper = selectedHelper.value;
  if (!helper) return '';
  return entityTransportLabels[helper.entity_type] || helper.entity_type;
});
const selectedMeasuredAt = computed(() => {
  const helper = selectedHelper.value;
  return helper?.last_measured_at ? formatTimestamp(helper.last_measured_at) : '—';
});
const selectedUpdatedAt = computed(() => {
  // recorded_at values are diagnostic only; surfaced here for troubleshooting.
  const helper = selectedHelper.value;
  return helper?.updated_at ? formatTimestamp(helper.updated_at) : '—';
});
const isUpdateMqtt = computed(() => selectedHelper.value?.entity_type === 'mqtt');
const detailFields = computed(() => {
  const helper = selectedHelper.value;
  if (!helper) {
    return [];
  }
  const description = (helper.description || '').trim();
  const typeLabel = selectedTypeLabel.value || helper.type || '';
  const deviceClass = helper.device_class || '';
  const unit = helper.unit_of_measurement || '';
  const stateClass = helper.state_class || '';
  const fields = [
    {
      key: 'device_name',
      label: 'Device name',
      value: helper.device_name || '—',
      isEmpty: !helper.device_name,
      wrap: false,
    },
    {
      key: 'entity_name',
      label: 'Entity name',
      value: helper.name || '—',
      isEmpty: !helper.name,
      wrap: false,
    },
    {
      key: 'description',
      label: 'Description',
      value: description || '—',
      isEmpty: !description,
      wrap: true,
    },
    {
      key: 'type',
      label: 'Type',
      value: typeLabel || '—',
      isEmpty: !typeLabel,
      wrap: false,
    },
    {
      key: 'device_class',
      label: 'Device class',
      value: deviceClass || '—',
      isEmpty: !deviceClass,
      wrap: false,
    },
    {
      key: 'unit',
      label: 'Unit of measurement',
      value: unit || '—',
      isEmpty: !unit,
      wrap: false,
    },
    {
      key: 'state_class',
      label: 'State class',
      value: stateClass || '—',
      isEmpty: !stateClass,
      wrap: false,
    },
  ];
  if (helper.entity_type === 'hassems') {
    const statsValue = normalizeStatisticsModeValue(helper.statistics_mode || 'linear');
    const statsLabel = statisticsModeLabels[statsValue] || statsValue || '';
    fields.push({
      key: 'statistics_mode',
      label: 'Statistics mode',
      value: statsLabel || '—',
      isEmpty: !statsLabel,
      wrap: false,
    });
    fields.push({
      key: 'ha_enabled',
      label: 'Home Assistant integration',
      value: helper.ha_enabled !== false ? 'Enabled' : 'Hidden',
      isEmpty: false,
      wrap: false,
    });
  }
  return fields;
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
const valueSubmitLabel = computed(() => {
  const helper = selectedHelper.value;
  return helper?.entity_type === 'hassems' ? 'Record value' : 'Publish to MQTT';
});
const createOptionsDisabled = computed(() => createForm.type !== 'input_select');
const isCreateMqtt = computed(() => createForm.entity_type === 'mqtt');

watch(
  () => [createForm.name, createForm.device_name, createForm.type, createForm.node_id],
  () => {
    syncCreateAutofill();
  },
);

watch(
  () => createForm.entity_type,
  (entityType) => {
    if (entityType === 'mqtt') {
      createForm.force_update = true;
      if (!createForm.node_id) {
        createForm.node_id = 'hassems';
      }
      createForm.statistics_mode = 'linear';
      createForm.ha_enabled = true;
    } else {
      createForm.force_update = false;
      createForm.node_id = '';
      createForm.state_topic = '';
      createForm.availability_topic = '';
      createForm.device_manufacturer = '';
      createForm.device_model = '';
      createForm.device_sw_version = '';
      createForm.device_identifiers = '';
      createForm.statistics_mode = normalizeStatisticsModeValue(createForm.statistics_mode);
      if (createForm.ha_enabled === undefined || createForm.ha_enabled === null) {
        createForm.ha_enabled = true;
      }
    }
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
  debugLog('selectedHelper changed', {
    previous: previous?.slug ?? null,
    current: helper?.slug ?? null,
  });
  closeHistoryDialog();
  if (helper) {
    populateUpdateForm(helper);
    populateValueForm(helper);
    await loadHistory(helper.slug);
  } else {
    closeEditDialog();
    resetUpdateForm();
    clearValueForm();
    historyRecords.value = [];
    historyList.value = [];
    historyMode.value = 'empty';
    closeApiDialog();
    historyEditorRows.value = [];
  }
});

watch(activePage, (page) => {
  if (page !== 'entities') {
    closeApiDialog();
    closeEditDialog();
    closeHistoryDialog();
  }
  if (page === 'settings') {
    loadIntegrationConnections();
  }
  if (page !== 'settings') {
    closeConnectionDialog();
  }
});

watch(
  [historyRecords, selectedHelper],
  ([records, helper]) => {
    debugLog('History records or helper changed', {
      helper: helper?.slug ?? null,
      recordCount: records?.length ?? 0,
    });
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

watch(historyMode, (mode) => {
  if (mode !== 'chart') {
    closeHistoryDebugDialog();
  }
});

async function loadMqttConfig() {
  debugLog('Loading MQTT config');
  try {
    const data = await requestJson('/config/mqtt');
    if (!data) {
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
    mqttConfig.value = data;
    debugLog('Loaded MQTT config', data);
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

function normalizeHelper(helper) {
  if (!helper || typeof helper !== 'object') {
    return helper;
  }
  return {
    ...helper,
    ha_enabled: helper.ha_enabled !== false,
    history_cursor_events: Array.isArray(helper.history_cursor_events)
      ? helper.history_cursor_events
      : [],
  };
}

async function loadHelpers() {
  try {
    const data = await requestJson('/inputs');
    debugLog('Loaded helpers response', data);
    const rawList = Array.isArray(data) ? data : [];
    helpers.value = rawList.map((helper) => normalizeHelper(helper));
    if (selectedSlug.value) {
      const exists = helpers.value.some((helper) => helper.slug === selectedSlug.value);
      if (!exists) {
        debugLog('Previously selected helper no longer exists, clearing selection', selectedSlug.value);
        selectedSlug.value = null;
      }
    }
  } catch (error) {
    showToast(`Failed to load entities: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

async function loadApiUsers() {
  try {
    const data = await requestJson('/users');
    const items = Array.isArray(data) ? data : [];
    debugLog('Loaded API users', items);
    apiUsers.value = items
      .map((item) => ({
        ...item,
        is_superuser: Boolean(item.is_superuser),
      }))
      .sort((a, b) => {
        if (a.is_superuser !== b.is_superuser) {
          return a.is_superuser ? -1 : 1;
        }
        return a.name.localeCompare(b.name, undefined, { sensitivity: 'base' });
      });
  } catch (error) {
    showToast(`Failed to load API users: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

async function loadIntegrationConnections() {
  try {
    const data = await requestJson('/integrations/home-assistant/connections');
    debugLog('Loaded integration connections', data);
    integrationConnections.value = Array.isArray(data) ? data : [];
  } catch (error) {
    showToast(
      `Failed to load integrations: ${error instanceof Error ? error.message : String(error)}`,
      'error',
    );
  }
}

function resetUserForm() {
  userForm.id = null;
  userForm.name = '';
  userForm.token = '';
  userForm.is_superuser = false;
  userTokenGenerating.value = false;
}

function openUserDialog(user = null) {
  const dialog = userDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  resetUserForm();
  if (user) {
    userDialogMode.value = 'edit';
    userForm.id = user.id;
    userForm.name = user.name;
    userForm.token = user.token;
    userForm.is_superuser = Boolean(user.is_superuser);
  } else {
    userDialogMode.value = 'create';
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

function closeUserDialog() {
  const dialog = userDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
}

function onUserDialogClose() {
  resetUserForm();
  userDialogMode.value = 'create';
}

async function generateUserToken() {
  if (userTokenGenerating.value) {
    return;
  }
  if (userForm.is_superuser && userDialogMode.value === 'edit') {
    return;
  }
  try {
    userTokenGenerating.value = true;
    const data = await requestJson('/users/generate-token', { method: 'POST' });
    const token = data && typeof data.token === 'string' ? data.token : '';
    if (!token) {
      throw new Error('Server did not return a token.');
    }
    userForm.token = token;
    showToast('Generated a new API token. Save the user to store it.', 'success');
  } catch (error) {
    showToast(`Failed to generate API token: ${error instanceof Error ? error.message : String(error)}`, 'error');
  } finally {
    userTokenGenerating.value = false;
  }
}

async function submitUserForm() {
  const name = userForm.name.trim();
  const token = userForm.token.trim();
  if (!name) {
    showToast('Provide a name for the API user.', 'error');
    return;
  }
  if (userDialogMode.value === 'create' && !token) {
    showToast('Provide a token for the new API user.', 'error');
    return;
  }
  try {
    userSaving.value = true;
    if (userDialogMode.value === 'create') {
      await requestJson('/users', {
        method: 'POST',
        body: JSON.stringify({ name, token }),
      });
      showToast('API user created.', 'success');
    } else if (userForm.id !== null) {
      const payload = { name };
      if (!userForm.is_superuser && token) {
        payload.token = token;
      }
      await requestJson(`/users/${userForm.id}`, {
        method: 'PUT',
        body: JSON.stringify(payload),
      });
      showToast('API user updated.', 'success');
    }
    await loadApiUsers();
    closeUserDialog();
  } catch (error) {
    showToast(`Failed to save API user: ${error instanceof Error ? error.message : String(error)}`, 'error');
  } finally {
    userSaving.value = false;
  }
}

async function deleteUser(user) {
  if (user.is_superuser) {
    showToast('The built-in superuser cannot be deleted.', 'error');
    return;
  }
  if (typeof window !== 'undefined') {
    const confirmed = window.confirm(`Delete API user "${user.name}"?`);
    if (!confirmed) {
      return;
    }
  }
  try {
    await requestJson(`/users/${user.id}`, { method: 'DELETE' });
    showToast('API user deleted.', 'success');
    await loadApiUsers();
  } catch (error) {
    showToast(`Failed to delete API user: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

async function fetchConnectionDetail(entryId, { fetchHistory = false, force = false } = {}) {
  const needsDetail =
    force ||
    !connectionDetail.value ||
    connectionDetail.value.entry_id !== entryId;
  if (needsDetail) {
    connectionDetailLoading.value = true;
    try {
      const detail = await requestJson(`/integrations/home-assistant/connections/${entryId}`);
      connectionDetail.value = detail || null;
      if (detail && typeof detail === 'object') {
        integrationConnections.value = integrationConnections.value.map((item) =>
          item.entry_id === detail.entry_id ? { ...item, ...detail } : item,
        );
      }
    } catch (error) {
      connectionDetail.value = null;
      throw error;
    } finally {
      connectionDetailLoading.value = false;
    }
  }
  if (fetchHistory) {
    connectionHistoryLoading.value = true;
    try {
      const history = await requestJson(
        `/integrations/home-assistant/connections/${entryId}/history`,
      );
      const items = Array.isArray(history) ? history : [];
      connectionHistory.value = items.map((item) => ({
        ...item,
        historic: Boolean(item.historic),
        historic_cursor: (() => {
          const cursorValue = item.historic_cursor || item.history_cursor || null;
          return cursorValue ? String(cursorValue) : null;
        })(),
      }));
    } catch (error) {
      connectionHistory.value = [];
      throw error;
    } finally {
      connectionHistoryLoading.value = false;
    }
  } else {
    connectionHistory.value = [];
  }
}

async function openConnectionDialog(connection, mode = 'history') {
  const dialog = connectionDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  const entryId = connection?.entry_id;
  if (!entryId) {
    showToast('Unable to open integration details. Missing entry id.', 'error');
    return;
  }
  selectedConnectionEntryId.value = entryId;
  connectionDialogMode.value = mode;
  if (!dialog.open) {
    dialog.showModal();
  }
  try {
    await fetchConnectionDetail(entryId, { fetchHistory: mode === 'history' });
  } catch (error) {
    showToast(
      `Failed to load integration details: ${error instanceof Error ? error.message : String(error)}`,
      'error',
    );
    closeConnectionDialog();
  }
}

function closeConnectionDialog() {
  const dialog = connectionDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
}

function onConnectionDialogClose() {
  connectionDetail.value = null;
  connectionHistory.value = [];
  selectedConnectionEntryId.value = null;
  connectionDialogMode.value = 'history';
  connectionDetailLoading.value = false;
  connectionHistoryLoading.value = false;
}

async function toggleConnectionDialogMode() {
  const entryId = selectedConnectionEntryId.value;
  if (!entryId) {
    return;
  }
  const nextMode = connectionDialogMode.value === 'history' ? 'config' : 'history';
  connectionDialogMode.value = nextMode;
  try {
    await fetchConnectionDetail(entryId, { fetchHistory: nextMode === 'history', force: false });
  } catch (error) {
    showToast(
      `Failed to update integration view: ${error instanceof Error ? error.message : String(error)}`,
      'error',
    );
  }
}

function selectHelper(slug) {
  debugLog('Selecting helper', { slug });
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

function openEditDialog() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to edit.', 'error');
    return;
  }
  populateUpdateForm(helper);
  const dialog = editDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

function closeEditDialog() {
  const dialog = editDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
}

function onEditDialogClose() {
  if (!selectedHelper.value) {
    resetUpdateForm();
  }
}

function openHistoryDialog() {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity to edit history.', 'error');
    return;
  }
  syncHistoryEditorRows();
  const dialog = historyDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  if (!dialog.open) {
    dialog.showModal();
  }
  historyDialogVisible.value = true;
}

function closeHistoryDialog() {
  const dialog = historyDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
  historyDialogVisible.value = false;
}

function onHistoryDialogClose() {
  historyDialogVisible.value = false;
  syncHistoryEditorRows();
}

function openHistoryDebugDialog() {
  if (!historyChartDataset.value.length) {
    showToast('No chart data available to display.', 'info');
    return;
  }
  const dialog = historyDebugDialog.value;
  if (!dialog || typeof dialog.showModal !== 'function') {
    return;
  }
  if (!dialog.open) {
    dialog.showModal();
  }
}

function closeHistoryDebugDialog() {
  const dialog = historyDebugDialog.value;
  if (dialog?.open) {
    dialog.close();
  }
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
  const isMqtt = createForm.entity_type === 'mqtt';

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

  if (!isMqtt) {
    if (createAutoFlags.stateTopic) {
      createForm.state_topic = '';
    }
    if (createAutoFlags.availabilityTopic) {
      createForm.availability_topic = '';
    }
    return;
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
  const isMqtt = createForm.entity_type === 'mqtt';
  const payload = {
    name: createForm.name?.trim(),
    entity_id: createForm.entity_id?.trim(),
    type,
    entity_type: createForm.entity_type,
    component: createForm.component?.trim() || 'sensor',
    unique_id: slugifyIdentifier(createForm.unique_id?.trim() || ''),
    object_id: slugifyIdentifier(createForm.object_id?.trim() || ''),
    device_name: createForm.device_name?.trim(),
    device_id: slugifyIdentifier(createForm.device_id?.trim() || '') || null,
  };

  if (isMqtt) {
    payload.node_id = slugifyIdentifier(createForm.node_id?.trim() || '') || null;
    payload.state_topic = createForm.state_topic?.trim();
    payload.availability_topic = createForm.availability_topic?.trim();
    payload.force_update = Boolean(createForm.force_update);
  } else {
    payload.statistics_mode = normalizeStatisticsModeValue(createForm.statistics_mode);
    payload.ha_enabled = Boolean(createForm.ha_enabled);
  }

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
  if (isMqtt && createForm.device_manufacturer?.trim()) {
    payload.device_manufacturer = createForm.device_manufacturer.trim();
  }
  if (isMqtt && createForm.device_model?.trim()) {
    payload.device_model = createForm.device_model.trim();
  }
  if (isMqtt && createForm.device_sw_version?.trim()) {
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
  if (isMqtt && identifiers.length) {
    payload.device_identifiers = identifiers;
  }

  return removeUndefined(payload);
}

function previewDiscovery() {
  if (!isCreateMqtt.value) {
    showToast('Discovery preview is only available for MQTT entities.', 'info');
    return;
  }
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
  const isMqtt = helper.entity_type === 'mqtt';
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
    statistics_mode:
      helper.entity_type === 'hassems'
        ? normalizeStatisticsModeValue(helper.statistics_mode)
        : 'linear',
    ha_enabled:
      helper.entity_type === 'hassems'
        ? helper.ha_enabled !== false
        : true,
    unique_id: helper.unique_id ?? '',
    object_id: helper.object_id ?? '',
    device_id: helper.device_id ?? slugifyIdentifier(helper.device_name ?? ''),
    node_id: isMqtt ? helper.node_id ?? 'hassems' : '',
    state_topic: isMqtt ? helper.state_topic ?? '' : '',
    availability_topic: isMqtt ? helper.availability_topic ?? '' : '',
    device_manufacturer: isMqtt ? helper.device_manufacturer ?? '' : '',
    device_model: isMqtt ? helper.device_model ?? '' : '',
    device_sw_version: isMqtt ? helper.device_sw_version ?? '' : '',
    device_identifiers: isMqtt ? (helper.device_identifiers || []).join(', ') : '',
    force_update: isMqtt ? helper.force_update !== false : false,
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
    statistics_mode: 'linear',
    ha_enabled: true,
    unique_id: '',
    object_id: '',
    device_id: '',
    node_id: '',
    state_topic: '',
    availability_topic: '',
    device_manufacturer: '',
    device_model: '',
    device_sw_version: '',
    device_identifiers: '',
    force_update: false,
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
    const response = await requestJson(`/inputs/${helper.slug}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    const updated = normalizeHelper(response);
    showToast('Entity updated.', 'success');
    helpers.value = helpers.value.map((item) => (item.slug === updated.slug ? updated : item));
    selectedSlug.value = updated.slug;
    closeEditDialog();
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function buildUpdatePayload(helperType) {
  const helper = selectedHelper.value;
  const isMqtt = helper?.entity_type === 'mqtt';
  const payload = {
    name: updateForm.name?.trim(),
    entity_id: updateForm.entity_id?.trim(),
    description: updateForm.description?.trim() || null,
    default_value: null,
    component: updateForm.component?.trim() || null,
    unique_id: slugifyIdentifier(updateForm.unique_id?.trim() || '') || null,
    object_id: slugifyIdentifier(updateForm.object_id?.trim() || '') || null,
    icon: updateForm.icon?.trim() || null,
    device_class: updateForm.device_class?.trim() || null,
    unit_of_measurement: updateForm.unit_of_measurement?.trim() || null,
    state_class: updateForm.state_class?.trim() || null,
    device_name: updateForm.device_name?.trim(),
    device_id: slugifyIdentifier(updateForm.device_id?.trim() || '') || null,
  };

  if (isMqtt) {
    payload.node_id = slugifyIdentifier(updateForm.node_id?.trim() || '') || null;
    payload.state_topic = updateForm.state_topic?.trim() || null;
    payload.availability_topic = updateForm.availability_topic?.trim() || null;
    payload.force_update = Boolean(updateForm.force_update);
    payload.device_manufacturer = updateForm.device_manufacturer?.trim() || null;
    payload.device_model = updateForm.device_model?.trim() || null;
    payload.device_sw_version = updateForm.device_sw_version?.trim() || null;
  }

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
  if (isMqtt) {
    payload.device_identifiers = trimmed ? parseCsv(trimmed) : [];
  }

  if (!isMqtt) {
    payload.statistics_mode = normalizeStatisticsModeValue(updateForm.statistics_mode);
    payload.ha_enabled = Boolean(updateForm.ha_enabled);
  }

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
    debugLog('Submitting value payload', { helper: helper.slug, payload });
    const response = await requestJson(`/inputs/${helper.slug}/set`, {
      method: 'POST',
      body: JSON.stringify(payload),
    });
    const updated = normalizeHelper(response);
    debugLog('Value submission response', { helper: helper.slug, updated });
    const successMessage = helper.entity_type === 'hassems' ? 'Value recorded locally.' : 'Value sent to MQTT.';
    showToast(successMessage, 'success');
    helpers.value = helpers.value.map((item) => (item.slug === updated.slug ? updated : item));
    selectedSlug.value = updated.slug;
    await loadHistory(updated.slug);
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  }
}

function getHistoryTimestamp(entry) {
  if (!entry) {
    return 0;
  }
  const source = entry.measured_at || entry.recorded_at;
  if (!source) {
    return 0;
  }
  const timestamp = new Date(source).getTime();
  return Number.isNaN(timestamp) ? 0 : timestamp;
}

function sortHistoryRecords(records) {
  if (!Array.isArray(records)) {
    return [];
  }
  return [...records].sort((a, b) => getHistoryTimestamp(a) - getHistoryTimestamp(b));
}

function formatHistoryValueForInput(helperType, value) {
  if (helperType === 'input_boolean') {
    const normalized = String(value).toLowerCase();
    if (['true', 'on', '1', 'yes'].includes(normalized)) {
      return 'true';
    }
    return 'false';
  }
  if (value === null || value === undefined) {
    return '';
  }
  return String(value);
}

function toDateTimeLocalString(value) {
  if (!value) {
    return '';
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return '';
  }
  const pad = (input) => String(input).padStart(2, '0');
  const year = date.getFullYear();
  const month = pad(date.getMonth() + 1);
  const day = pad(date.getDate());
  const hours = pad(date.getHours());
  const minutes = pad(date.getMinutes());
  return `${year}-${month}-${day}T${hours}:${minutes}`;
}

function buildHistoryEditorRows(records) {
  const helper = selectedHelper.value;
  if (!helper) {
    return [];
  }
  const helperType = helper.type;
  return records.map((entry) => ({
    id: entry.id,
    valueInput: formatHistoryValueForInput(helperType, entry.value),
    measuredInput: toDateTimeLocalString(entry.measured_at || entry.recorded_at),
    recordedDisplay: formatTimestamp(entry.recorded_at),
    historic: Boolean(entry.historic),
    historicCursor: (() => {
      const cursorValue = entry.historic_cursor || entry.history_cursor || null;
      return cursorValue ? String(cursorValue) : null;
    })(),
    saving: false,
    deleting: false,
    error: '',
  }));
}

function syncHistoryEditorRows() {
  historyEditorRows.value = buildHistoryEditorRows(historyRecords.value);
}

async function loadHistory(slug) {
  debugLog('Loading history for helper', { slug });
  try {
    const history = await requestJson(`/inputs/${slug}/history`);
    const records = Array.isArray(history) ? history : [];
    debugLog('History response', { slug, recordsCount: records.length, records });
    const normalizedRecords = records.map((entry) => ({
      ...entry,
      historic: Boolean(entry.historic),
      historic_cursor: entry.historic_cursor || entry.history_cursor || null,
      history_cursor: entry.history_cursor || entry.historic_cursor || null,
    }));
    historyRecords.value = sortHistoryRecords(normalizedRecords);
    syncHistoryEditorRows();
  } catch (error) {
    showToast(`Failed to load history: ${error instanceof Error ? error.message : String(error)}`, 'error');
  }
}

async function saveHistoryRow(row) {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity before editing history.', 'error');
    return;
  }
  let measuredAtIso = null;
  if (row.measuredInput) {
    const measuredDate = new Date(row.measuredInput);
    if (Number.isNaN(measuredDate.getTime())) {
      row.error = 'Enter a valid measurement time.';
      return;
    }
    measuredAtIso = measuredDate.toISOString();
  }
  let value;
  try {
    value = coerceValue(helper.type, row.valueInput);
  } catch (error) {
    row.error = error instanceof Error ? error.message : String(error);
    return;
  }
  row.error = '';
  row.saving = true;
  try {
    await requestJson(`/inputs/${helper.slug}/history/${row.id}`, {
      method: 'PUT',
      body: JSON.stringify({
        value,
        measured_at: measuredAtIso,
      }),
    });
    showToast('History entry updated.', 'success');
    await loadHistory(helper.slug);
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  } finally {
    row.saving = false;
  }
}

async function deleteHistoryRow(row) {
  const helper = selectedHelper.value;
  if (!helper) {
    showToast('Select an entity before editing history.', 'error');
    return;
  }
  const confirmed =
    typeof window === 'undefined' || window.confirm('Delete this history entry? This cannot be undone.');
  if (!confirmed) {
    return;
  }
  row.error = '';
  row.deleting = true;
  try {
    await requestJson(`/inputs/${helper.slug}/history/${row.id}`, {
      method: 'DELETE',
    });
    showToast('History entry deleted.', 'success');
    await loadHistory(helper.slug);
  } catch (error) {
    showToast(error instanceof Error ? error.message : String(error), 'error');
  } finally {
    row.deleting = false;
  }
}

function renderHistory(helper, history) {
  destroyChart();
  historyChartDataset.value = [];
  const sorted = sortHistoryRecords(history);
  debugLog('Rendering history', {
    helper: helper.slug,
    entries: sorted.length,
    rawHistory: history,
  });
  if (!sorted.length) {
    historyMode.value = 'empty';
    historyList.value = [];
    debugLog('No history entries to render', { helper: helper.slug });
    return;
  }
  const datasetPoints = [];
  const skippedEntries = [];
  let lastHistoryCursor = null;
  for (const item of sorted) {
    const timestampSource = item.measured_at || item.recorded_at;
    const timestampDate = timestampSource ? new Date(timestampSource) : null;
    const timestampValid = timestampDate instanceof Date && !Number.isNaN(timestampDate?.getTime?.());
    const normalizedValue = normalizeHistoryValue(helper.type, item.value);
    const numericValue = normalizedValue === null ? null : Number(normalizedValue);
    const cursorValue = item.historic_cursor || item.history_cursor || null;
    const historyCursor = cursorValue ? String(cursorValue) : null;
    const isHistoric = Boolean(item.historic);
    const historyChange = Boolean(historyCursor && historyCursor !== lastHistoryCursor);
    if (!timestampValid || numericValue === null || Number.isNaN(numericValue)) {
      skippedEntries.push({
        timestamp: timestampSource ?? null,
        value: item.value,
        normalizedValue,
        timestampValid,
      });
      continue;
    }
    datasetPoints.push({
      x: timestampDate,
      y: numericValue,
      historyCursor,
      historyChange,
      historic: isHistoric,
    });
    if (historyCursor) {
      lastHistoryCursor = historyCursor;
    }
  }
  debugLog('Prepared history dataset', {
    helper: helper.slug,
    points: datasetPoints.length,
    skippedEntries: skippedEntries.length,
  });
  if (skippedEntries.length) {
    debugLog('Skipped history entries that could not be charted', {
      helper: helper.slug,
      skippedEntries,
    });
  }
  if (datasetPoints.length) {
    historyChartDataset.value = datasetPoints.map((point) => ({
      x: point.x instanceof Date ? point.x.toISOString() : point.x,
      y: point.y,
      history_cursor: point.historyCursor ?? null,
      history_change: Boolean(point.historyChange),
      historic: Boolean(point.historic),
    }));
    const canvasEl = historyCanvas.value;
    if (canvasEl instanceof HTMLCanvasElement && canvasEl.isConnected) {
      const context = canvasEl.getContext('2d');
      if (context) {
        historyMode.value = 'chart';
        historyList.value = [];
        debugLog('Rendering chart dataset', {
          helper: helper.slug,
          datasetPoints,
        });
        const firstPoint = datasetPoints[0];
        const lastPoint = datasetPoints[datasetPoints.length - 1];
        const xScaleBounds = {};
        if (firstPoint?.x instanceof Date) {
          xScaleBounds.min = firstPoint.x;
        }
        if (lastPoint?.x instanceof Date) {
          xScaleBounds.max = lastPoint.x;
        }
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
        try {
          chartInstance.value = new Chart(canvasEl, {
            type: 'line',
            data: {
              datasets: [
                {
                  label: helper.name,
                  data: datasetPoints,
                  fill: false,
                  borderColor: '#2563eb',
                  backgroundColor: 'rgba(37, 99, 235, 0.15)',
                  tension: 0.25,
                },
              ],
            },
            options: {
              parsing: false,
              responsive: true,
              scales: {
                x: {
                  type: 'time',
                  time: {
                    tooltipFormat: 'yyyy-LL-dd HH:mm:ss',
                    displayFormats: {
                      minute: 'HH:mm',
                      hour: 'HH:mm',
                      day: 'MMM d',
                    },
                  },
                  ...xScaleBounds,
                  ticks: {
                    source: 'auto',
                    autoSkip: true,
                    maxRotation: 0,
                  },
                },
                y: {
                  beginAtZero: helper.type !== 'input_number',
                  ...yScaleOptions,
                },
              },
              plugins: {
                decimation: { enabled: false },
                legend: { display: false },
                tooltip: {
                  callbacks: {
                    title: (items) => {
                      const timestamp = items?.[0]?.parsed?.x ?? null;
                      return timestamp ? formatTimestamp(timestamp) : '';
                    },
                    label: (item) => {
                      const value = item?.parsed?.y;
                      if (value === undefined || value === null) {
                        return '';
                      }
                      if (helper.type === 'input_boolean') {
                        return value === 1 ? 'On' : 'Off';
                      }
                      const formatted = typeof value === 'number' ? value.toLocaleString() : String(value);
                      const unit = helper.unit_of_measurement || '';
                      return unit ? `${formatted} ${unit}` : formatted;
                    },
                    afterLabel: (context) => {
                      const rawPoint = context?.raw ?? {};
                      const details = [];
                      if (rawPoint.historic) {
                        details.push('Historic point');
                      }
                      if (rawPoint.historyCursor) {
                        details.push(`Historic cursor: ${rawPoint.historyCursor}`);
                      }
                      return details.join('\n');
                    },
                  },
                },
              },
            },
          });
          debugLog('Chart rendered successfully', { helper: helper.slug });
          return;
        } catch (error) {
          console.error('Failed to render history chart', error, { helper, datasetPoints });
        }
      } else {
        debugLog('Canvas context unavailable, cannot render chart', { helper: helper.slug });
      }
    }
  }
  debugLog('Falling back to history list view', { helper: helper.slug });
  historyChartDataset.value = [];
  historyMode.value = 'list';
  const listEntries = [];
  lastHistoryCursor = null;
  for (const item of sorted) {
    const cursorValue = item.historic_cursor || item.history_cursor || null;
    const historyCursor = cursorValue ? String(cursorValue) : null;
    const isHistoric = Boolean(item.historic);
    const historyChange = Boolean(historyCursor && historyCursor !== lastHistoryCursor);
    if (historyCursor) {
      lastHistoryCursor = historyCursor;
    }
    listEntries.push({
      key: item.id ?? `${item.measured_at ?? item.recorded_at}-${item.value}`,
      measured_at: formatTimestamp(item.measured_at || item.recorded_at),
      value: String(item.value ?? '—'),
      historyCursor,
      historyChange,
      historic: isHistoric,
    });
  }
  historyList.value = listEntries;
}

function destroyChart() {
  if (!chartInstance.value) {
    debugLog('destroyChart called with no active chart');
    return;
  }
  try {
    const chart = chartInstance.value;
    if (typeof chart.stop === 'function') {
      chart.stop();
    }
    chart.destroy();
    debugLog('Destroyed existing chart instance');
  } catch (error) {
    console.warn('Failed to destroy chart instance', error);
  } finally {
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

function formatHelperList(list) {
  if (!Array.isArray(list) || list.length === 0) {
    return 'None';
  }
  return list.join(', ');
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
  debugLog('HTTP request', { url: fullUrl, options });
  const response = await fetch(fullUrl, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (response.status === 204) {
    debugLog('HTTP 204 response', { url: fullUrl });
    return null;
  }
  const contentType = response.headers.get('content-type') || '';
  const isJson = contentType.includes('application/json');
  if (!response.ok) {
    let message = response.statusText;
    if (isJson) {
      try {
        const data = await response.json();
        debugLog('HTTP error payload', { url: fullUrl, status: response.status, data });
        message = data?.detail || data?.message || message;
      } catch (error) {
        // ignore JSON parsing errors
      }
    }
    throw new Error(message);
  }
  if (!isJson) {
    debugLog('HTTP non-JSON response ignored', { url: fullUrl, status: response.status });
    return null;
  }
  const data = await response.json();
  debugLog('HTTP response', { url: fullUrl, status: response.status, data });
  return data;
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
  debugLog('App mounted - initializing data loads');
  resetCreateForm();
  await loadMqttConfig();
  await loadHelpers();
  await loadApiUsers();
  await loadIntegrationConnections();
});

onBeforeUnmount(() => {
  debugLog('App unmounting - cleaning up timers and charts');
  if (toastTimer) {
    clearTimeout(toastTimer);
  }
  destroyChart();
});
</script>
