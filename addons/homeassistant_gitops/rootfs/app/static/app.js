const MAX_DIFF_LINES = 400;
const MONACO_BASE = window.MONACO_BASE || "https://cdn.jsdelivr.net/npm/monaco-editor@0.44.0/min";
const MODULES_REFRESH_INTERVAL_MS = 10000;

const state = {
  diffMode: "all",
  status: null,
  config: null,
  branches: [],
  selectedBranch: null,
  commits: [],
  selectedCommit: null,
  modulesIndex: [],
  selectedModuleId: null,
  selectedModuleFile: null,
  moduleFileContent: "",
  moduleFileDirty: false,
  modulesStale: false,
};

const dom = {
  statusSummary: document.getElementById("status-summary"),
  statusMessage: document.getElementById("status-message"),
  statusRefresh: document.getElementById("status-refresh"),
  remoteRefresh: document.getElementById("remote-refresh"),
  commitMessage: document.getElementById("commit-message"),
  commitStaged: document.getElementById("commit-staged"),
  commitAll: document.getElementById("commit-all"),
  commitStatus: document.getElementById("commit-status"),
  pullBtn: document.getElementById("pull-btn"),
  pushBtn: document.getElementById("push-btn"),
  diffList: document.getElementById("diff-list"),
  diffMode: document.getElementById("diff-mode"),
  stageAll: document.getElementById("stage-all"),
  unstageAll: document.getElementById("unstage-all"),
  branchSelect: document.getElementById("branch-select"),
  commitList: document.getElementById("commit-list"),
  commitMeta: document.getElementById("commit-meta"),
  commitDiffs: document.getElementById("commit-diffs"),
  resetCommit: document.getElementById("reset-commit"),
  configRemoteUrl: document.getElementById("config-remote-url"),
  configRemoteBranch: document.getElementById("config-remote-branch"),
  configGitUserName: document.getElementById("config-git-user-name"),
  configGitUserEmail: document.getElementById("config-git-user-email"),
  configWebhookPath: document.getElementById("config-webhook-path"),
  configPollInterval: document.getElementById("config-poll-interval"),
  configNotifications: document.getElementById("config-notifications"),
  configWebhookEnabled: document.getElementById("config-webhook-enabled"),
  configYamlModules: document.getElementById("config-yaml-modules"),
  configTheme: document.getElementById("config-ui-theme"),
  saveConfig: document.getElementById("save-config"),
  configStatus: document.getElementById("config-status"),
  sshStatus: document.getElementById("ssh-status"),
  sshPublicKey: document.getElementById("ssh-public-key"),
  sshInstructions: document.getElementById("ssh-instructions"),
  sshGenerateBtn: document.getElementById("ssh-generate-btn"),
  sshLoadBtn: document.getElementById("ssh-load-btn"),
  sshTestBtn: document.getElementById("ssh-test-btn"),
  sshTestStatus: document.getElementById("ssh-test-status"),
  modulesStatus: document.getElementById("modules-status"),
  modulesSyncBtn: document.getElementById("modules-sync-btn"),
  moduleSelect: document.getElementById("module-select"),
  moduleFileList: document.getElementById("module-file-list"),
  moduleFileMeta: document.getElementById("module-file-meta"),
  moduleSaveBtn: document.getElementById("module-save-btn"),
  moduleDeleteBtn: document.getElementById("module-delete-btn"),
  moduleEditor: document.getElementById("module-editor"),
  moduleEditorStatus: document.getElementById("module-editor-status"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;
let moduleEditor = null;
let moduleEditorTextarea = null;
let moduleEditorPromise = null;
let moduleEditorSetting = false;
let moduleRefreshTimer = null;
let moduleIndexLoading = false;

function qs(selector, scope = document) {
  return scope.querySelector(selector);
}

function qsa(selector, scope = document) {
  return Array.from(scope.querySelectorAll(selector));
}

function showToast(message) {
  if (!dom.toast) {
    return;
  }
  dom.toast.textContent = message;
  dom.toast.classList.add("is-visible");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    dom.toast.classList.remove("is-visible");
  }, 3200);
}

async function requestJSON(url, options = {}) {
  const headers = options.headers || {};
  if (!(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(url, { ...options, headers });
  let payload = {};
  try {
    payload = await response.json();
  } catch (err) {
    payload = {};
  }
  if (!response.ok) {
    throw new Error(payload.detail || payload.status || "Request failed");
  }
  return payload;
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme || "system";
  setEditorTheme();
}

function getEditorTheme() {
  const theme = document.documentElement.dataset.theme;
  if (theme === "dark") {
    return "vs-dark";
  }
  if (theme === "light") {
    return "vs";
  }
  if (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) {
    return "vs-dark";
  }
  return "vs";
}

function setEditorTheme() {
  if (!moduleEditor || !window.monaco || !window.monaco.editor) {
    return;
  }
  window.monaco.editor.setTheme(getEditorTheme());
}

function setTab(tab) {
  qsa(".tab-btn[data-tab]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  qsa(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tab}`);
  });
  if (tab === "modules" && moduleEditor) {
    setTimeout(() => moduleEditor.layout(), 0);
  }
  if (tab === "modules") {
    startModulesRefresh();
  } else {
    stopModulesRefresh();
  }
}

function isModulesTabActive() {
  const panel = document.getElementById("tab-modules");
  return panel ? panel.classList.contains("is-active") : false;
}

function startModulesRefresh() {
  if (!moduleRefreshTimer) {
    moduleRefreshTimer = setInterval(() => {
      if (!isModulesTabActive()) {
        return;
      }
      loadModulesIndex({ allowDirty: false });
    }, MODULES_REFRESH_INTERVAL_MS);
  }
  loadModulesIndex({ allowDirty: false });
}

function stopModulesRefresh() {
  if (!moduleRefreshTimer) {
    return;
  }
  clearInterval(moduleRefreshTimer);
  moduleRefreshTimer = null;
}

function updateModulesStatus(enabled) {
  dom.modulesStatus.textContent = enabled
    ? "YAML Modules sync is enabled."
    : "YAML Modules sync is disabled in add-on options.";
  dom.modulesSyncBtn.disabled = !enabled;
}

function renderSummaryItem(label, value) {
  const item = document.createElement("div");
  item.className = "summary-item";
  const span = document.createElement("span");
  span.textContent = label;
  const strong = document.createElement("strong");
  strong.textContent = value;
  item.append(span, strong);
  return item;
}

function formatRemoteStatus(remoteStatus) {
  if (!remoteStatus || !remoteStatus.configured) {
    return "Not configured";
  }
  if (remoteStatus.error) {
    return remoteStatus.error;
  }
  const ahead = remoteStatus.ahead || 0;
  const behind = remoteStatus.behind || 0;
  if (!ahead && !behind) {
    return "Up to date";
  }
  if (ahead && behind) {
    return `Ahead ${ahead}, behind ${behind}`;
  }
  if (ahead) {
    return `Ahead by ${ahead}`;
  }
  return `Behind by ${behind}`;
}

function renderStatus(data) {
  dom.statusSummary.innerHTML = "";
  dom.statusSummary.append(
    renderSummaryItem("Branch", data.branch || "-"),
    renderSummaryItem("Remote", data.remote || "Not configured"),
    renderSummaryItem("Remote Sync", formatRemoteStatus(data.remote_status)),
    renderSummaryItem("Staged", String(data.staged_count || 0)),
    renderSummaryItem("Unstaged", String(data.unstaged_count || 0)),
    renderSummaryItem("Untracked", String(data.untracked_count || 0)),
    renderSummaryItem("Pending", String((data.pending || []).length))
  );

  if (data.commits && data.commits.length) {
    dom.statusSummary.append(
      renderSummaryItem("Latest Commit", data.commits[0].subject)
    );
  }

  const needsRemote = !data.remote;
  dom.pullBtn.disabled = needsRemote;
  dom.pushBtn.disabled = needsRemote;
  dom.remoteRefresh.disabled = needsRemote;
  dom.statusMessage.textContent = needsRemote
    ? "Remote is not configured. Push and pull are disabled."
    : "";

  updateModulesStatus(Boolean(data.yaml_modules_enabled));
}

function matchesDiffMode(change) {
  if (state.diffMode === "staged") {
    return change.staged;
  }
  if (state.diffMode === "unstaged") {
    return change.unstaged || change.untracked;
  }
  return true;
}

function buildChangeLabel(change) {
  if (change.rename_from) {
    return `${change.rename_from} -> ${change.path}`;
  }
  return change.path;
}

function isBinaryDiff(diffText) {
  return diffText.includes("Binary files") || diffText.includes("GIT binary patch");
}

async function loadDiff(details, options) {
  if (details.dataset.loaded === "true" && !options.force) {
    return;
  }
  const body = qs(".diff-body", details);
  body.innerHTML = "Loading diff...";
  const url = new URL(options.endpoint, window.location.origin);
  Object.entries(options.query).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      url.searchParams.set(key, String(value));
    }
  });
  try {
    const data = await requestJSON(url.pathname + url.search);
    if (!data.diff || !data.diff.trim()) {
      body.innerHTML = "<div class=\"diff-placeholder\">No diff available.</div>";
    } else if (isBinaryDiff(data.diff)) {
      body.innerHTML = "<div class=\"diff-placeholder\">Binary file changed. Diff not available.</div>";
    } else {
      if (!window.Diff2Html || typeof window.Diff2Html.html !== "function") {
        body.innerHTML = "<div class=\"diff-placeholder\">Diff viewer failed to load.</div>";
      } else {
        body.innerHTML = Diff2Html.html(data.diff, {
          inputFormat: "diff",
          outputFormat: "side-by-side",
          drawFileList: false,
          matching: "lines",
        });
      }
    }

    if (data.truncated) {
      const loadMore = document.createElement("button");
      loadMore.className = "btn";
      loadMore.textContent = `Load full diff (${data.total_lines} lines)`;
      loadMore.addEventListener("click", async (event) => {
        event.stopPropagation();
        loadMore.disabled = true;
        await loadDiff(details, {
          endpoint: options.endpoint,
          query: { ...options.query, max_lines: "" },
          force: true,
        });
      });
      body.append(loadMore);
    }
  } catch (err) {
    body.innerHTML = `<div class=\"diff-placeholder\">${err.message}</div>`;
  }
  details.dataset.loaded = "true";
}

function createDiffCard(change, context) {
  const details = document.createElement("details");
  details.className = "diff-card";

  const summary = document.createElement("summary");

  const title = document.createElement("div");
  title.className = "diff-title";
  const fileLine = document.createElement("div");
  fileLine.textContent = buildChangeLabel(change);
  const meta = document.createElement("div");
  meta.className = "diff-meta";

  if (change.staged) {
    const chip = document.createElement("span");
    chip.className = "chip staged";
    chip.textContent = "Staged";
    meta.append(chip);
  }
  if (change.unstaged) {
    const chip = document.createElement("span");
    chip.className = "chip unstaged";
    chip.textContent = "Unstaged";
    meta.append(chip);
  }
  if (change.untracked) {
    const chip = document.createElement("span");
    chip.className = "chip untracked";
    chip.textContent = "Untracked";
    meta.append(chip);
  }
  if (context === "commit" && change.status) {
    const chip = document.createElement("span");
    chip.className = "chip";
    chip.textContent = change.status;
    meta.append(chip);
  }

  title.append(fileLine, meta);
  summary.append(title);

  if (context === "status") {
    const actions = document.createElement("div");
    actions.className = "diff-actions";
    if (change.unstaged || change.untracked) {
      const stageBtn = document.createElement("button");
      stageBtn.className = "btn";
      stageBtn.textContent = "Stage";
      stageBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        stageFiles([change.path]);
      });
      actions.append(stageBtn);
    }
    if (change.staged) {
      const unstageBtn = document.createElement("button");
      unstageBtn.className = "btn";
      unstageBtn.textContent = "Unstage";
      unstageBtn.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        unstageFiles([change.path]);
      });
      actions.append(unstageBtn);
    }
    summary.append(actions);
  }

  details.append(summary);

  const body = document.createElement("div");
  body.className = "diff-body";
  body.innerHTML = "<div class=\"diff-placeholder\">Expand to load diff.</div>";
  details.append(body);

  details.addEventListener("toggle", () => {
    if (!details.open) {
      return;
    }
    if (context === "commit") {
      loadDiff(details, {
        endpoint: "/api/commit/diff",
        query: {
          sha: change.sha,
          path: change.path,
          max_lines: MAX_DIFF_LINES,
        },
      });
      return;
    }
    loadDiff(details, {
      endpoint: "/api/diff",
      query: {
        path: change.path,
        mode: state.diffMode,
        max_lines: MAX_DIFF_LINES,
        untracked: change.untracked ? "true" : "",
      },
    });
  });

  return details;
}

function renderDiffList(changes) {
  dom.diffList.innerHTML = "";
  const filtered = changes.filter(matchesDiffMode);
  if (!filtered.length) {
    dom.diffList.innerHTML = "<div class=\"diff-placeholder\">No diffs for this view.</div>";
    return;
  }
  filtered.forEach((change) => {
    dom.diffList.append(createDiffCard(change, "status"));
  });
}

async function loadStatus() {
  try {
    const data = await requestJSON("/api/status");
    state.status = data;
    renderStatus(data);
    renderDiffList(data.changes || []);
  } catch (err) {
    dom.statusMessage.textContent = err.message;
  }
}

async function refreshRemoteStatus() {
  try {
    const data = await requestJSON("/api/remote/status?refresh=true");
    if (state.status) {
      state.status.remote_status = data;
      renderStatus(state.status);
    }
  } catch (err) {
    dom.statusMessage.textContent = err.message;
  }
}

async function stageFiles(files) {
  if (!files.length) {
    return;
  }
  try {
    await requestJSON("/api/stage", {
      method: "POST",
      body: JSON.stringify({ files }),
    });
    showToast("Staged changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function unstageFiles(files) {
  if (!files.length) {
    return;
  }
  try {
    await requestJSON("/api/unstage", {
      method: "POST",
      body: JSON.stringify({ files }),
    });
    showToast("Unstaged changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function commitChanges(includeUnstaged) {
  const message = dom.commitMessage.value.trim();
  if (!message) {
    showToast("Commit message required");
    return;
  }
  try {
    await requestJSON("/api/commit", {
      method: "POST",
      body: JSON.stringify({ message, include_unstaged: includeUnstaged }),
    });
    dom.commitMessage.value = "";
    showToast("Committed changes");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function pullChanges() {
  try {
    const data = await requestJSON("/api/pull", { method: "POST" });
    showToast(data.changes && data.changes.length ? "Pulled updates" : "Already up to date");
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function pushChanges() {
  try {
    const data = await requestJSON("/api/push", { method: "POST" });
    const branchInfo = data.branch ? ` to ${data.branch}` : "";
    showToast(`Pushed${branchInfo}`);
    await loadStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadBranches() {
  try {
    const data = await requestJSON("/api/branches");
    state.branches = data.branches || [];
    state.selectedBranch = data.current || state.branches[0];
    dom.branchSelect.innerHTML = "";
    state.branches.forEach((branch) => {
      const option = document.createElement("option");
      option.value = branch;
      option.textContent = branch;
      dom.branchSelect.append(option);
    });
    if (state.selectedBranch) {
      dom.branchSelect.value = state.selectedBranch;
      await loadCommits(state.selectedBranch);
    }
  } catch (err) {
    showToast(err.message);
  }
}

function renderCommitList(commits) {
  dom.commitList.innerHTML = "";
  if (!commits.length) {
    dom.commitList.innerHTML = "<div class=\"diff-placeholder\">No commits found.</div>";
    return;
  }
  commits.forEach((commit) => {
    const item = document.createElement("div");
    item.className = "commit-item";
    const subject = document.createElement("div");
    subject.textContent = commit.subject;
    const meta = document.createElement("div");
    meta.className = "note";
    meta.textContent = `${commit.sha} - ${commit.author} - ${commit.date}`;
    item.append(subject, meta);
    item.addEventListener("click", () => {
      qsa(".commit-item").forEach((el) => el.classList.remove("is-active"));
      item.classList.add("is-active");
      loadCommitDetails(commit);
    });
    dom.commitList.append(item);
  });
}

async function loadCommits(branch) {
  try {
    const data = await requestJSON(`/api/commits?branch=${encodeURIComponent(branch)}&limit=50`);
    state.commits = data.commits || [];
    renderCommitList(state.commits);
    dom.commitMeta.textContent = "Select a commit to inspect its diff.";
    dom.commitDiffs.innerHTML = "";
    dom.resetCommit.disabled = true;
  } catch (err) {
    showToast(err.message);
  }
}

async function loadCommitDetails(commit) {
  state.selectedCommit = commit;
  dom.commitMeta.textContent = `${commit.sha} - ${commit.subject}`;
  dom.commitDiffs.innerHTML = "<div class=\"diff-placeholder\">Loading diffs...</div>";
  dom.resetCommit.disabled = false;
  try {
    const files = await requestJSON(`/api/commit/files?sha=${commit.sha_full}`);
    dom.commitDiffs.innerHTML = "";
    if (!files.files.length) {
      dom.commitDiffs.innerHTML = "<div class=\"diff-placeholder\">No diff for this commit.</div>";
      return;
    }
    files.files.forEach((file) => {
      dom.commitDiffs.append(
        createDiffCard({
          ...file,
          sha: commit.sha_full,
        }, "commit")
      );
    });
  } catch (err) {
    dom.commitDiffs.innerHTML = `<div class=\"diff-placeholder\">${err.message}</div>`;
  }
}

async function resetToCommit() {
  if (!state.selectedCommit) {
    return;
  }
  const sha = state.selectedCommit.sha_full || state.selectedCommit.sha;
  const status = state.status || (await requestJSON("/api/status"));
  const dirty = Boolean(status.dirty);
  let message = `Hard reset to ${sha}?`;
  if (dirty) {
    message = "Uncommitted changes detected. A gitops-stash branch will be created, all changes will be committed, then a hard reset will run. Continue?";
  }
  if (!window.confirm(message)) {
    return;
  }
  try {
    const payload = {
      sha,
      confirm_dirty: dirty,
      message: `GitOps stash before reset to ${sha}`,
    };
    const result = await requestJSON("/api/reset", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (result.stash_branch) {
      showToast(`Stashed changes on ${result.stash_branch} and reset.`);
    } else {
      showToast("Reset complete.");
    }
    await loadStatus();
    await loadCommits(state.selectedBranch);
  } catch (err) {
    showToast(err.message);
  }
}

async function loadConfig() {
  try {
    const data = await requestJSON("/api/config");
    const config = data.config || {};
    state.config = config;
    dom.configRemoteUrl.value = config.remote_url || "";
    dom.configRemoteBranch.value = config.remote_branch || "main";
    dom.configGitUserName.value = config.git_user_name || "";
    dom.configGitUserEmail.value = config.git_user_email || "";
    dom.configWebhookPath.value = config.webhook_path || "pull";
    dom.configPollInterval.value =
      config.poll_interval_minutes === null || config.poll_interval_minutes === undefined
        ? ""
        : String(config.poll_interval_minutes);
    dom.configNotifications.checked = Boolean(config.notification_enabled);
    dom.configWebhookEnabled.checked = Boolean(config.webhook_enabled);
    dom.configYamlModules.checked = Boolean(config.yaml_modules_enabled);
    dom.configTheme.value = config.ui_theme || "system";
    applyTheme(dom.configTheme.value);
  } catch (err) {
    dom.configStatus.textContent = err.message;
  }
}

async function saveConfig() {
  const pollValue = dom.configPollInterval.value.trim();
  const payload = {
    remote_url: dom.configRemoteUrl.value.trim(),
    remote_branch: dom.configRemoteBranch.value.trim() || "main",
    git_user_name: dom.configGitUserName.value.trim(),
    git_user_email: dom.configGitUserEmail.value.trim(),
    webhook_path: dom.configWebhookPath.value.trim() || "pull",
    poll_interval_minutes: pollValue === "" ? null : Number(pollValue),
    notification_enabled: dom.configNotifications.checked,
    webhook_enabled: dom.configWebhookEnabled.checked,
    yaml_modules_enabled: dom.configYamlModules.checked,
    ui_theme: dom.configTheme.value,
  };
  if (Number.isNaN(payload.poll_interval_minutes)) {
    dom.configStatus.textContent = "Poll interval must be a number or blank.";
    return;
  }
  try {
    const data = await requestJSON("/api/config", {
      method: "POST",
      body: JSON.stringify(payload),
    });
    if (data.status) {
      dom.configStatus.textContent = data.requires_restart
        ? "Saved. Restart the add-on to apply backend changes."
        : "Saved.";
    } else {
      dom.configStatus.textContent = "Save failed.";
    }
    applyTheme(payload.ui_theme);
    await loadStatus();
  } catch (err) {
    dom.configStatus.textContent = err.message;
  }
}

async function loadSshStatus() {
  try {
    const data = await requestJSON("/api/ssh/status");
    dom.sshStatus.textContent = data.private_key_exists
      ? "SSH keypair exists."
      : "No SSH keypair yet.";
    dom.sshGenerateBtn.disabled = data.private_key_exists || !data.ssh_dir_writable;
    dom.sshLoadBtn.disabled = !data.public_key_exists;
    dom.sshTestBtn.disabled = !data.private_key_exists || !data.ssh_available;
    dom.sshInstructions.textContent = data.private_key_exists
      ? "Add the public key to your Git provider."
      : "Generate a keypair, then add the public key to your Git provider.";
    dom.sshTestStatus.textContent = data.ssh_available
      ? "Test the SSH connection to GitHub once the key is added."
      : "SSH client is not available in the add-on image.";
  } catch (err) {
    dom.sshStatus.textContent = err.message;
  }
}

async function generateSshKey() {
  try {
    await requestJSON("/api/ssh/generate", { method: "POST" });
    showToast("SSH key generated");
    await loadSshStatus();
  } catch (err) {
    showToast(err.message);
  }
}

async function loadPublicKey() {
  try {
    const data = await requestJSON("/api/ssh/public_key");
    dom.sshPublicKey.textContent = data.public_key || "";
  } catch (err) {
    showToast(err.message);
  }
}

async function testSshKey() {
  dom.sshTestStatus.textContent = "Testing SSH connection to GitHub...";
  try {
    const data = await requestJSON("/api/ssh/test", {
      method: "POST",
      body: JSON.stringify({ host: "git@github.com" }),
    });
    const output = data.output ? data.output.trim().replace(/\s+/g, " ") : "";
    const message =
      data.message ||
      (data.status === "success" ? "SSH authentication succeeded." : "SSH authentication failed.");
    dom.sshTestStatus.textContent = output ? `${message} ${output}` : message;
    showToast(message);
  } catch (err) {
    dom.sshTestStatus.textContent = err.message;
    showToast(err.message);
  }
}

function loadMonaco() {
  if (window.monaco) {
    return Promise.resolve(window.monaco);
  }
  if (!window.require) {
    return Promise.reject(new Error("Editor loader is unavailable."));
  }
  if (!moduleEditorPromise) {
    moduleEditorPromise = new Promise((resolve, reject) => {
      window.require.config({ paths: { vs: `${MONACO_BASE}/vs` } });
      window.require(
        ["vs/editor/editor.main"],
        () => resolve(window.monaco),
        (err) => reject(err)
      );
    });
  }
  return moduleEditorPromise;
}

function createFallbackEditor() {
  dom.moduleEditor.innerHTML = "";
  const textarea = document.createElement("textarea");
  textarea.className = "module-editor-textarea";
  textarea.disabled = true;
  textarea.placeholder = "Select a module file to start editing.";
  textarea.addEventListener("input", () => {
    if (moduleEditorSetting) {
      return;
    }
    handleModuleEditorChange();
  });
  dom.moduleEditor.append(textarea);
  moduleEditorTextarea = textarea;
}

function ensureModuleEditor() {
  if (moduleEditor || moduleEditorTextarea || !dom.moduleEditor) {
    return Promise.resolve();
  }
  return loadMonaco()
    .then(() => {
      dom.moduleEditor.innerHTML = "";
      moduleEditor = window.monaco.editor.create(dom.moduleEditor, {
        value: "",
        language: "yaml",
        theme: getEditorTheme(),
        readOnly: true,
        automaticLayout: true,
        minimap: { enabled: false },
        scrollBeyondLastLine: false,
      });
      moduleEditor.onDidChangeModelContent(() => {
        if (moduleEditorSetting) {
          return;
        }
        handleModuleEditorChange();
      });
      dom.moduleEditorStatus.textContent = "";
    })
    .catch(() => {
      createFallbackEditor();
      dom.moduleEditorStatus.textContent =
        "Editor failed to load. Using the basic text editor.";
    });
}

function getModuleEditorValue() {
  if (moduleEditor) {
    return moduleEditor.getValue();
  }
  if (moduleEditorTextarea) {
    return moduleEditorTextarea.value;
  }
  return "";
}

function setModuleEditorReadOnly(readOnly) {
  if (moduleEditor) {
    moduleEditor.updateOptions({ readOnly });
  }
  if (moduleEditorTextarea) {
    moduleEditorTextarea.disabled = readOnly;
  }
}

function setModuleEditorContent(content, markClean = true) {
  const nextValue = content || "";
  moduleEditorSetting = true;
  if (moduleEditor) {
    moduleEditor.setValue(nextValue);
    requestAnimationFrame(() => moduleEditor && moduleEditor.layout());
  } else if (moduleEditorTextarea) {
    moduleEditorTextarea.value = nextValue;
  } else if (dom.moduleEditor) {
    dom.moduleEditor.innerHTML = `<div class="module-editor-placeholder">${nextValue
      ? "Loading editor..."
      : "Select a module file to start editing."}</div>`;
  }
  moduleEditorSetting = false;
  if (markClean) {
    state.moduleFileContent = nextValue;
    setModuleDirty(false);
  }
}

function handleModuleEditorChange() {
  const current = getModuleEditorValue();
  setModuleDirty(current !== state.moduleFileContent);
}

function updateModuleFileMeta() {
  if (!dom.moduleFileMeta) {
    return;
  }
  if (!state.selectedModuleFile) {
    dom.moduleFileMeta.textContent = "Select a module file to inspect and edit.";
    return;
  }
  const status = state.moduleFileDirty ? "Unsaved changes." : "Ready.";
  dom.moduleFileMeta.textContent = `${state.selectedModuleFile} - ${status}`;
}

function setModuleDirty(isDirty) {
  state.moduleFileDirty = isDirty;
  dom.moduleSaveBtn.disabled = !state.selectedModuleFile || !isDirty;
  updateModuleFileMeta();
  if (!isDirty && state.modulesStale && isModulesTabActive()) {
    state.modulesStale = false;
    loadModulesIndex();
  }
}

function clearModuleSelection() {
  state.selectedModuleFile = null;
  state.moduleFileContent = "";
  state.moduleFileDirty = false;
  dom.moduleSaveBtn.disabled = true;
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "";
  updateModuleFileMeta();
  if (moduleEditor || moduleEditorTextarea) {
    setModuleEditorContent("", true);
    setModuleEditorReadOnly(true);
  } else if (dom.moduleEditor) {
    dom.moduleEditor.innerHTML =
      "<div class=\"module-editor-placeholder\">Select a module file to start editing.</div>";
  }
}

function confirmDiscardModuleChanges() {
  if (!state.moduleFileDirty) {
    return true;
  }
  const target = state.selectedModuleFile || "this file";
  return window.confirm(`Discard unsaved changes to ${target}?`);
}

function getModuleById(moduleId) {
  return state.modulesIndex.find((module) => module.id === moduleId);
}

function renderModuleSelect(modules) {
  dom.moduleSelect.innerHTML = "";
  if (!modules.length) {
    dom.moduleSelect.disabled = true;
    const option = document.createElement("option");
    option.textContent = "No modules found";
    dom.moduleSelect.append(option);
    return;
  }
  dom.moduleSelect.disabled = false;
  const nameCounts = modules.reduce((acc, module) => {
    acc[module.name] = (acc[module.name] || 0) + 1;
    return acc;
  }, {});

  const packages = modules.filter((module) => module.kind === "package");
  const oneOffs = modules.filter((module) => module.kind === "one_offs");
  const unassigned = modules.filter((module) => module.kind === "unassigned");

  const kindLabel = (kind) => {
    if (kind === "one_offs") {
      return "one-offs";
    }
    return kind || "module";
  };

  const appendGroup = (label, items) => {
    if (!items.length) {
      return;
    }
    const group = document.createElement("optgroup");
    group.label = label;
    items.forEach((module) => {
      const option = document.createElement("option");
      option.value = module.id;
      const suffix = nameCounts[module.name] > 1 ? ` (${kindLabel(module.kind)})` : "";
      option.textContent = `${module.name}${suffix}`;
      group.append(option);
    });
    dom.moduleSelect.append(group);
  };

  appendGroup("Packages", packages);
  appendGroup("One-offs", oneOffs);
  appendGroup("Unassigned", unassigned);
}

function renderModuleFileList(module) {
  dom.moduleFileList.innerHTML = "";
  if (!module || !module.files || !module.files.length) {
    dom.moduleFileList.innerHTML =
      "<div class=\"diff-placeholder\">No module files found.</div>";
    return;
  }
  module.files.forEach((filePath) => {
    const item = document.createElement("div");
    item.className = "commit-item";
    if (state.selectedModuleFile === filePath) {
      item.classList.add("is-active");
    }
    const title = document.createElement("div");
    title.textContent = filePath;
    item.append(title);
    item.addEventListener("click", async () => {
      const loaded = await selectModuleFile(filePath);
      if (loaded) {
        renderModuleFileList(module);
      }
    });
    dom.moduleFileList.append(item);
  });
}

async function loadModulesIndex(options = {}) {
  const allowDirty = options.allowDirty !== false;
  if (!dom.moduleSelect || !dom.moduleFileList) {
    return;
  }
  if (!allowDirty && state.moduleFileDirty) {
    state.modulesStale = true;
    return;
  }
  if (moduleIndexLoading) {
    return;
  }
  moduleIndexLoading = true;
  dom.moduleFileList.innerHTML =
    "<div class=\"diff-placeholder\">Loading module files...</div>";
  dom.moduleSelect.disabled = true;
  try {
    const data = await requestJSON("/api/modules/index");
    state.modulesIndex = data.modules || [];
    state.modulesStale = false;
    renderModuleSelect(state.modulesIndex);
    if (!state.modulesIndex.length) {
      dom.moduleFileList.innerHTML =
        "<div class=\"diff-placeholder\">No YAML module files found.</div>";
      state.selectedModuleId = null;
      clearModuleSelection();
      return;
    }
    if (!state.selectedModuleId || !getModuleById(state.selectedModuleId)) {
      state.selectedModuleId = state.modulesIndex[0].id;
    }
    dom.moduleSelect.value = state.selectedModuleId;
    const activeModule = getModuleById(state.selectedModuleId);
    if (
      state.selectedModuleFile &&
      (!activeModule || !activeModule.files.includes(state.selectedModuleFile))
    ) {
      clearModuleSelection();
    }
    renderModuleFileList(activeModule);
  } catch (err) {
    state.modulesIndex = [];
    state.selectedModuleId = null;
    dom.moduleSelect.innerHTML = "";
    dom.moduleSelect.disabled = true;
    dom.moduleFileList.innerHTML = `<div class="diff-placeholder">${err.message}</div>`;
    clearModuleSelection();
  } finally {
    moduleIndexLoading = false;
  }
}

async function selectModuleFile(filePath) {
  if (state.selectedModuleFile === filePath) {
    return true;
  }
  if (!confirmDiscardModuleChanges()) {
    return false;
  }
  state.selectedModuleFile = filePath;
  dom.moduleFileMeta.textContent = `Loading ${filePath}...`;
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleSaveBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "";
  try {
    const data = await requestJSON(
      `/api/modules/file?path=${encodeURIComponent(filePath)}`
    );
    await ensureModuleEditor();
    setModuleEditorReadOnly(false);
    setModuleEditorContent(data.content || "", true);
    state.selectedModuleFile = data.path || filePath;
    dom.moduleDeleteBtn.disabled = false;
    updateModuleFileMeta();
    return true;
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
    clearModuleSelection();
    return false;
  }
}

async function saveModuleFile() {
  if (!state.selectedModuleFile) {
    return;
  }
  const content = getModuleEditorValue();
  dom.moduleSaveBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "Saving module file...";
  try {
    await requestJSON("/api/modules/file", {
      method: "POST",
      body: JSON.stringify({ path: state.selectedModuleFile, content }),
    });
    state.moduleFileContent = content;
    setModuleDirty(false);
    dom.moduleEditorStatus.textContent = "Module file saved.";
    showToast("Module file saved");
    await loadStatus();
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function deleteModuleFile() {
  if (!state.selectedModuleFile) {
    return;
  }
  const warning = state.moduleFileDirty
    ? "Unsaved changes will be lost."
    : "This cannot be undone.";
  if (!window.confirm(`Delete ${state.selectedModuleFile}? ${warning}`)) {
    return;
  }
  dom.moduleDeleteBtn.disabled = true;
  dom.moduleEditorStatus.textContent = "Deleting module file...";
  try {
    await requestJSON(
      `/api/modules/file?path=${encodeURIComponent(state.selectedModuleFile)}`,
      { method: "DELETE" }
    );
    showToast("Module file deleted");
    clearModuleSelection();
    await loadStatus();
    await loadModulesIndex();
  } catch (err) {
    dom.moduleEditorStatus.textContent = err.message;
    showToast(err.message);
  }
}

async function syncModules() {
  dom.modulesStatus.textContent = "Syncing YAML Modules...";
  try {
    const data = await requestJSON("/api/modules/sync", { method: "POST" });
    showToast("YAML Modules synced");
    await loadStatus();
    if (!state.moduleFileDirty) {
      await loadModulesIndex();
    }
    const reconciledCount = (data.reconciled_ids || []).length;
    const reconcileNote = reconciledCount
      ? ` Automation IDs reconciled (${reconciledCount}). Review and commit changes.`
      : "";
    if (data.warnings && data.warnings.length) {
      dom.modulesStatus.textContent =
        `Sync complete with warnings: ${data.warnings.join(" | ")}` + reconcileNote;
    } else {
      dom.modulesStatus.textContent = `Sync complete.${reconcileNote}`;
    }
  } catch (err) {
    dom.modulesStatus.textContent = err.message;
    showToast(err.message);
  }
}

function bindEvents() {
  qsa(".tab-btn[data-tab]").forEach((btn) => {
    btn.addEventListener("click", () => setTab(btn.dataset.tab));
  });

  dom.statusRefresh.addEventListener("click", loadStatus);
  dom.remoteRefresh.addEventListener("click", refreshRemoteStatus);

  dom.commitStaged.addEventListener("click", () => commitChanges(false));
  dom.commitAll.addEventListener("click", () => commitChanges(true));
  dom.pullBtn.addEventListener("click", pullChanges);
  dom.pushBtn.addEventListener("click", pushChanges);

  dom.stageAll.addEventListener("click", () => {
    const changes = (state.status && state.status.changes) || [];
    const files = changes
      .filter((change) => change.unstaged || change.untracked)
      .map((change) => change.path);
    stageFiles(files);
  });
  dom.unstageAll.addEventListener("click", () => {
    const changes = (state.status && state.status.changes) || [];
    const files = changes.filter((change) => change.staged).map((change) => change.path);
    unstageFiles(files);
  });

  qsa("#diff-mode .segmented-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.diffMode = btn.dataset.mode;
      qsa("#diff-mode .segmented-btn").forEach((el) =>
        el.classList.toggle("is-active", el === btn)
      );
      if (state.status) {
        renderDiffList(state.status.changes || []);
      }
    });
  });

  dom.branchSelect.addEventListener("change", async (event) => {
    state.selectedBranch = event.target.value;
    await loadCommits(state.selectedBranch);
  });

  dom.resetCommit.addEventListener("click", resetToCommit);

  dom.saveConfig.addEventListener("click", saveConfig);
  dom.sshGenerateBtn.addEventListener("click", generateSshKey);
  dom.sshLoadBtn.addEventListener("click", loadPublicKey);
  dom.sshTestBtn.addEventListener("click", testSshKey);
  dom.modulesSyncBtn.addEventListener("click", syncModules);
  dom.moduleSelect.addEventListener("change", (event) => {
    const nextId = event.target.value;
    if (!confirmDiscardModuleChanges()) {
      dom.moduleSelect.value = state.selectedModuleId || "";
      return;
    }
    state.selectedModuleId = nextId;
    clearModuleSelection();
    renderModuleFileList(getModuleById(nextId));
  });
  dom.moduleSaveBtn.addEventListener("click", saveModuleFile);
  dom.moduleDeleteBtn.addEventListener("click", deleteModuleFile);
}

async function init() {
  bindEvents();
  await loadConfig();
  await loadStatus();
  await loadModulesIndex();
  await loadBranches();
  await loadSshStatus();
  if (isModulesTabActive()) {
    startModulesRefresh();
  }
}

init();
