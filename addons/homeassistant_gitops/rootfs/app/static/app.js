const MAX_DIFF_LINES = 400;

const state = {
  diffMode: "all",
  status: null,
  config: null,
  branches: [],
  selectedBranch: null,
  commits: [],
  selectedCommit: null,
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
  configMergeAutomations: document.getElementById("config-merge-automations"),
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
  automationStatus: document.getElementById("automation-status"),
  mergeBtn: document.getElementById("merge-btn"),
  syncBtn: document.getElementById("sync-btn"),
  toast: document.getElementById("toast"),
};

let toastTimer = null;

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
}

function setTab(tab) {
  qsa(".tab-btn[data-tab]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  qsa(".tab-panel").forEach((panel) => {
    panel.classList.toggle("is-active", panel.id === `tab-${tab}`);
  });
}

function updateAutomationStatus(enabled) {
  dom.automationStatus.textContent = enabled
    ? "Automation builder is enabled."
    : "Automation builder is disabled in add-on options.";
  dom.mergeBtn.disabled = !enabled;
  dom.syncBtn.disabled = !enabled;
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

  updateAutomationStatus(Boolean(data.merge_automations));
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
    dom.configMergeAutomations.checked = Boolean(config.merge_automations);
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
    merge_automations: dom.configMergeAutomations.checked,
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

async function mergeAutomations() {
  try {
    await requestJSON("/api/automation/merge", { method: "POST" });
    showToast("Automations merged");
  } catch (err) {
    showToast(err.message);
  }
}

async function syncAutomations() {
  try {
    await requestJSON("/api/automation/sync", { method: "POST" });
    showToast("Automations synced");
  } catch (err) {
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
  dom.mergeBtn.addEventListener("click", mergeAutomations);
  dom.syncBtn.addEventListener("click", syncAutomations);
}

async function init() {
  bindEvents();
  await loadConfig();
  await loadStatus();
  await loadBranches();
  await loadSshStatus();
}

init();
