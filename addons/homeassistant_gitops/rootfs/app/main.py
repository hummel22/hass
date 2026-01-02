from __future__ import annotations

import argparse
import asyncio
import contextlib
import fnmatch
import json
import os
import shutil
import subprocess
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import httpx
from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from watchdog.events import FileSystemEvent, FileSystemEventHandler
from watchdog.observers import Observer

CONFIG_DIR = Path("/config")
OPTIONS_PATH = Path("/data/options.json")
GITOPS_CONFIG_PATH = CONFIG_DIR / ".gitops.yaml"
SSH_DIR = CONFIG_DIR / ".ssh"
GITIGNORE_TEMPLATE = Path("/app/gitignore_example")
WATCH_EXTENSIONS = {".yaml", ".yml"}
DEBOUNCE_SECONDS = 0.6
GITIGNORE_CACHE: tuple[float, list[tuple[bool, str, bool, bool, bool]]] | None = None


@dataclass
class Options:
    remote_url: str | None
    remote_branch: str
    notification_enabled: bool
    webhook_enabled: bool
    webhook_path: str
    poll_interval_minutes: int | None
    merge_automations: bool
    ui_theme: str


def _parse_bool(value: str) -> bool | None:
    lowered = value.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    return None


def load_gitops_config() -> dict[str, Any]:
    if not GITOPS_CONFIG_PATH.exists():
        return {}
    data: dict[str, Any] = {}
    for line in GITOPS_CONFIG_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip().strip('"').strip("'")
        if not key:
            continue
        if value.lower() in {"null", "none"}:
            data[key] = None
            continue
        parsed_bool = _parse_bool(value)
        if parsed_bool is not None:
            data[key] = parsed_bool
            continue
        if value.isdigit():
            data[key] = int(value)
            continue
        data[key] = value
    return data


def _quote_yaml(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f"\"{escaped}\""


def render_gitops_config(options: Options) -> str:
    lines = [
        "# Home Assistant GitOps Bridge configuration",
        f"remote_url: {_quote_yaml(options.remote_url or '')}",
        f"remote_branch: {_quote_yaml(options.remote_branch)}",
        f"notification_enabled: {'true' if options.notification_enabled else 'false'}",
        f"webhook_enabled: {'true' if options.webhook_enabled else 'false'}",
        f"webhook_path: {_quote_yaml(options.webhook_path)}",
        f"poll_interval_minutes: {options.poll_interval_minutes if options.poll_interval_minutes is not None else 'null'}",
        f"merge_automations: {'true' if options.merge_automations else 'false'}",
        f"ui_theme: {_quote_yaml(options.ui_theme)}",
    ]
    return "\n".join(lines) + "\n"


def write_gitops_config(options: Options) -> None:
    content = render_gitops_config(options)
    GITOPS_CONFIG_PATH.write_text(content, encoding="utf-8")


def _build_options(data: dict[str, Any]) -> Options:
    ui_theme = str(data.get("ui_theme", "system") or "system").lower()
    if ui_theme not in {"light", "dark", "system"}:
        ui_theme = "system"
    return Options(
        remote_url=data.get("remote_url") or None,
        remote_branch=data.get("remote_branch", "main"),
        notification_enabled=bool(data.get("notification_enabled", True)),
        webhook_enabled=bool(data.get("webhook_enabled", False)),
        webhook_path=data.get("webhook_path", "pull"),
        poll_interval_minutes=data.get("poll_interval_minutes", 15),
        merge_automations=bool(data.get("merge_automations", True)),
        ui_theme=ui_theme,
    )


def run_git(args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=CONFIG_DIR,
        text=True,
        capture_output=True,
        check=check,
    )


def get_origin_url() -> str | None:
    try:
        result = run_git(["remote", "get-url", "origin"], check=False)
    except OSError:
        return None
    if result.returncode != 0:
        return None
    url = result.stdout.strip()
    return url or None


def get_git_config_value(key: str) -> str | None:
    result = run_git(["config", "--local", "--get", key], check=False)
    if result.returncode != 0:
        return None
    value = result.stdout.strip()
    return value or None


def set_git_config_value(key: str, value: str | None) -> None:
    if value is None or str(value).strip() == "":
        run_git(["config", "--local", "--unset", key], check=False)
        return
    run_git(["config", "--local", key, str(value).strip()], check=False)


def load_options() -> Options:
    if not GITOPS_CONFIG_PATH.exists():
        seed: dict[str, Any] = {}
        if OPTIONS_PATH.exists():
            seed = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
        write_gitops_config(_build_options(seed))
    data = load_gitops_config()
    origin_url = get_origin_url()
    if origin_url and data.get("remote_url") != origin_url:
        data["remote_url"] = origin_url
        write_gitops_config(_build_options(data))
    return _build_options(data)


OPTIONS = load_options()


async def call_service(domain: str, service: str, data: dict[str, Any] | None = None) -> None:
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return
    url = f"http://supervisor/core/api/services/{domain}/{service}"
    headers = {"Authorization": f"Bearer {token}"}
    payload = data or {}
    async with httpx.AsyncClient(timeout=10.0) as client:
        await client.post(url, headers=headers, json=payload)


async def notify(title: str, message: str, notification_id: str) -> None:
    if not OPTIONS.notification_enabled:
        return
    await call_service(
        "persistent_notification",
        "create",
        {
            "title": title,
            "message": message,
            "notification_id": notification_id,
        },
    )


def get_ssh_status() -> dict[str, Any]:
    key_path = SSH_DIR / "id_ed25519"
    pub_path = SSH_DIR / "id_ed25519.pub"
    ssh_keygen = shutil.which("ssh-keygen")
    ssh_client = shutil.which("ssh")
    ssh_add = shutil.which("ssh-add")
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if SSH_DIR.exists():
        ssh_dir_writable = os.access(SSH_DIR, os.W_OK)
    else:
        ssh_dir_writable = os.access(CONFIG_DIR, os.W_OK)
    ssh_agent_available = ssh_add is not None and bool(ssh_auth_sock)
    ssh_key_loaded = False
    if ssh_agent_available and key_path.exists():
        list_result = subprocess.run(
            ["ssh-add", "-L"],
            capture_output=True,
            text=True,
            check=False,
        )
        if list_result.returncode == 0:
            ssh_key_loaded = key_path.name in list_result.stdout
    return {
        "ssh_dir": str(SSH_DIR),
        "private_key_exists": key_path.exists(),
        "public_key_exists": pub_path.exists(),
        "ssh_dir_writable": ssh_dir_writable,
        "ssh_keygen_available": ssh_keygen is not None,
        "ssh_available": ssh_client is not None,
        "ssh_agent_available": ssh_agent_available,
        "ssh_key_loaded": ssh_key_loaded,
    }


def ensure_ssh_agent_key() -> None:
    key_path = SSH_DIR / "id_ed25519"
    ssh_add = shutil.which("ssh-add")
    ssh_auth_sock = os.environ.get("SSH_AUTH_SOCK")
    if not ssh_add or not ssh_auth_sock or not key_path.exists():
        return
    subprocess.run(
        ["ssh-add", str(key_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def load_gitignore_template() -> list[str]:
    if not GITIGNORE_TEMPLATE.exists():
        return []
    lines = [
        line.strip()
        for line in GITIGNORE_TEMPLATE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    return lines


def load_gitignore_patterns() -> list[tuple[bool, str, bool, bool, bool]]:
    gitignore_path = CONFIG_DIR / ".gitignore"
    if not gitignore_path.exists():
        return []
    patterns: list[tuple[bool, str, bool, bool, bool]] = []
    for line in gitignore_path.read_text(encoding="utf-8").splitlines():
        entry = line.strip()
        if not entry or entry.startswith("#"):
            continue
        negated = entry.startswith("!")
        if negated:
            entry = entry[1:].strip()
            if not entry:
                continue
        is_dir = entry.endswith("/")
        pattern = entry.rstrip("/") if is_dir else entry
        is_glob = any(char in pattern for char in "*?[]")
        is_path = "/" in pattern
        patterns.append((negated, pattern, is_dir, is_path, is_glob))
    return patterns


def get_gitignore_patterns() -> list[tuple[bool, str, bool, bool, bool]]:
    global GITIGNORE_CACHE
    gitignore_path = CONFIG_DIR / ".gitignore"
    try:
        mtime = gitignore_path.stat().st_mtime
    except FileNotFoundError:
        return []
    if GITIGNORE_CACHE and GITIGNORE_CACHE[0] == mtime:
        return GITIGNORE_CACHE[1]
    patterns = load_gitignore_patterns()
    GITIGNORE_CACHE = (mtime, patterns)
    return patterns


def ensure_gitignore() -> None:
    gitignore_path = CONFIG_DIR / ".gitignore"
    template_lines = load_gitignore_template()
    existing = set()
    if gitignore_path.exists():
        existing = {line.strip() for line in gitignore_path.read_text(encoding="utf-8").splitlines()}
    new_lines = [entry for entry in template_lines if entry not in existing]
    if not existing:
        if not template_lines:
            return
        content = "\n".join(template_lines) + "\n"
        gitignore_path.write_text(content, encoding="utf-8")
        return
    if new_lines:
        with gitignore_path.open("a", encoding="utf-8") as handle:
            handle.write("\n" + "\n".join(new_lines) + "\n")


def ensure_repo() -> None:
    if (CONFIG_DIR / ".git").exists():
        return
    ensure_gitignore()
    init_result = run_git(["init", "-b", OPTIONS.remote_branch], check=False)
    if init_result.returncode != 0:
        run_git(["init"])
        run_git(["branch", "-M", OPTIONS.remote_branch])
    run_git(["add", "-A"])
    run_git(["commit", "-m", "Initial Home Assistant configuration"], check=False)


def ensure_gitops_config() -> None:
    if GITOPS_CONFIG_PATH.exists():
        return
    write_gitops_config(OPTIONS)


def ensure_remote() -> None:
    if not OPTIONS.remote_url:
        return
    result = run_git(["remote"], check=False)
    remotes = {line.strip() for line in result.stdout.splitlines()}
    if "origin" not in remotes:
        run_git(["remote", "add", "origin", OPTIONS.remote_url])
    else:
        run_git(["remote", "set-url", "origin", OPTIONS.remote_url])


def working_tree_clean() -> bool:
    result = run_git(["status", "--porcelain"], check=False)
    return result.stdout.strip() == ""


def current_branch() -> str:
    result = run_git(["rev-parse", "--abbrev-ref", "HEAD"], check=False)
    branch = result.stdout.strip()
    return branch or "HEAD"


def branch_exists(name: str) -> bool:
    result = run_git(["show-ref", "--verify", "--quiet", f"refs/heads/{name}"], check=False)
    return result.returncode == 0


def commit_exists(sha: str) -> bool:
    result = run_git(["cat-file", "-e", f"{sha}^{{commit}}"], check=False)
    return result.returncode == 0


def list_branches() -> list[str]:
    result = run_git(["for-each-ref", "--format=%(refname:short)", "refs/heads"], check=False)
    branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return sorted(branches)


def get_remote_status(refresh: bool = False) -> dict[str, Any]:
    if not OPTIONS.remote_url:
        return {"configured": False, "ahead": 0, "behind": 0, "branch": OPTIONS.remote_branch}
    ensure_remote()
    if refresh:
        run_git(["fetch", "origin", OPTIONS.remote_branch], check=False)
    remote_ref = f"origin/{OPTIONS.remote_branch}"
    remote_exists = run_git(["rev-parse", "--verify", remote_ref], check=False).returncode == 0
    if not remote_exists:
        return {
            "configured": True,
            "ahead": 0,
            "behind": 0,
            "branch": OPTIONS.remote_branch,
            "error": f"Remote branch {remote_ref} not found",
        }
    result = run_git(
        ["rev-list", "--left-right", "--count", f"HEAD...{remote_ref}"], check=False
    )
    ahead = behind = 0
    if result.returncode == 0 and result.stdout.strip():
        left, right = result.stdout.strip().split()
        ahead = int(left)
        behind = int(right)
    return {"configured": True, "ahead": ahead, "behind": behind, "branch": OPTIONS.remote_branch}


def git_status() -> list[dict[str, Any]]:
    result = run_git(["status", "--porcelain=v1", "-z"], check=False)
    changes: list[dict[str, Any]] = []
    if result.returncode != 0:
        return changes
    entries = result.stdout.split("\0")
    idx = 0
    while idx < len(entries):
        entry = entries[idx]
        if not entry:
            idx += 1
            continue
        status = entry[:2]
        path = entry[3:] if len(entry) > 3 else ""
        rename_from = None
        if status[0] in {"R", "C"}:
            rename_from = path
            idx += 1
            if idx >= len(entries):
                break
            path = entries[idx]
        staged = status[0] not in {" ", "?"}
        unstaged = status[1] not in {" ", "?"}
        untracked = status == "??"
        changes.append(
            {
                "status": status,
                "path": path,
                "staged": staged,
                "unstaged": unstaged,
                "untracked": untracked,
                "rename_from": rename_from,
            }
        )
        idx += 1
    return changes


def git_log(limit: int = 20) -> list[dict[str, str]]:
    result = run_git(
        [
            "--no-pager",
            "log",
            f"-n{limit}",
            "--pretty=format:%H%x09%h%x09%an%x09%ad%x09%s",
            "--date=short",
        ],
        check=False,
    )
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) == 5:
            entries.append(
                {
                    "sha_full": parts[0],
                    "sha": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
    return entries


def git_commits(ref: str, limit: int = 50) -> list[dict[str, str]]:
    result = run_git(
        [
            "--no-pager",
            "log",
            ref,
            f"-n{limit}",
            "--pretty=format:%H%x09%h%x09%an%x09%ad%x09%s",
            "--date=short",
        ],
        check=False,
    )
    entries: list[dict[str, str]] = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 4)
        if len(parts) == 5:
            entries.append(
                {
                    "sha_full": parts[0],
                    "sha": parts[1],
                    "author": parts[2],
                    "date": parts[3],
                    "subject": parts[4],
                }
            )
    return entries


def _truncate_diff(diff: str, max_lines: int | None) -> tuple[str, bool, int]:
    total_lines = diff.count("\n")
    if max_lines is None or max_lines <= 0:
        return diff, False, total_lines
    lines = diff.splitlines()
    if len(lines) <= max_lines:
        return diff, False, len(lines)
    truncated = "\n".join(lines[:max_lines]) + "\n"
    return truncated, True, len(lines)


def git_diff(
    path: str,
    mode: str = "unstaged",
    max_lines: int | None = None,
    untracked: bool = False,
) -> dict[str, Any]:
    if untracked and mode in {"unstaged", "all"}:
        result = run_git(
            ["--no-pager", "diff", "--no-index", "--", "/dev/null", path], check=False
        )
    elif mode == "staged":
        result = run_git(["--no-pager", "diff", "--cached", "--", path], check=False)
    elif mode == "all":
        result = run_git(["--no-pager", "diff", "HEAD", "--", path], check=False)
    else:
        result = run_git(["--no-pager", "diff", "--", path], check=False)
    diff = result.stdout
    truncated, is_truncated, total_lines = _truncate_diff(diff, max_lines)
    return {"diff": truncated, "truncated": is_truncated, "total_lines": total_lines}


def git_commit_changes(sha: str) -> list[dict[str, Any]]:
    result = run_git(
        ["diff-tree", "--no-commit-id", "--name-status", "-r", sha], check=False
    )
    if result.returncode != 0:
        return []
    changes: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        parts = line.split("\t")
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            if len(parts) >= 3:
                changes.append(
                    {
                        "status": status,
                        "path": parts[2],
                        "rename_from": parts[1],
                    }
                )
            continue
        if len(parts) >= 2:
            changes.append({"status": status, "path": parts[1], "rename_from": None})
    return changes


def git_commit_diff(sha: str, path: str, max_lines: int | None = None) -> dict[str, Any]:
    result = run_git(
        ["--no-pager", "show", sha, "--pretty=format:", "--", path], check=False
    )
    diff = result.stdout
    truncated, is_truncated, total_lines = _truncate_diff(diff, max_lines)
    return {"diff": truncated, "truncated": is_truncated, "total_lines": total_lines}


def create_gitops_stash_branch(message: str | None = None) -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    base_name = f"gitops-stash-{timestamp}"
    branch_name = base_name
    counter = 1
    while branch_exists(branch_name):
        branch_name = f"{base_name}-{counter}"
        counter += 1
    original_branch = current_branch()
    original_sha = run_git(["rev-parse", "HEAD"], check=False).stdout.strip()
    checkout_result = run_git(["checkout", "-b", branch_name], check=False)
    if checkout_result.returncode != 0:
        raise HTTPException(
            status_code=400, detail=checkout_result.stderr.strip() or "Failed to create stash branch"
        )
    run_git(["add", "-A"], check=False)
    commit_message = message or f"GitOps stash before reset {timestamp} UTC"
    commit_result = run_git(["commit", "-m", commit_message], check=False)
    if original_branch == "HEAD":
        return_result = run_git(["checkout", "--detach", original_sha], check=False)
    else:
        return_result = run_git(["checkout", original_branch], check=False)
    if commit_result.returncode != 0:
        raise HTTPException(
            status_code=400, detail=commit_result.stderr.strip() or "Failed to commit stash branch"
        )
    if return_result.returncode != 0:
        raise HTTPException(
            status_code=400,
            detail=return_result.stderr.strip() or "Failed to return to original branch",
        )
    return branch_name


def should_ignore(path: Path) -> bool:
    rel = path.as_posix()
    ignored = False
    for negated, pattern, is_dir, is_path, is_glob in get_gitignore_patterns():
        matched = False
        if is_dir:
            matched = pattern in path.parts
        elif is_glob:
            matched = fnmatch.fnmatch(rel, pattern) or fnmatch.fnmatch(path.name, pattern)
        elif is_path:
            matched = rel == pattern
        else:
            matched = path.name == pattern
        if matched:
            ignored = not negated
    if ignored:
        return True
    if path.suffix.lower() not in WATCH_EXTENSIONS:
        return True
    return False


def list_changed_domains(paths: Iterable[str]) -> set[str]:
    domains: set[str] = set()
    for path in paths:
        lowered = path.lower()
        if lowered.endswith("automations.yaml") or lowered.startswith("automations/"):
            domains.add("automation")
        if lowered.endswith("scripts.yaml") or lowered.startswith("scripts/"):
            domains.add("script")
        if lowered.endswith("scenes.yaml") or lowered.startswith("scenes/"):
            domains.add("scene")
    return domains


def _build_automation_blocks() -> dict[str, list[str]]:
    automations_dir = CONFIG_DIR / "automations"
    if not automations_dir.exists():
        return {}
    entries: dict[str, list[str]] = {}
    for file_path in sorted(automations_dir.glob("*.y*ml")):
        contents = file_path.read_text(encoding="utf-8")
        rel_path = str(file_path.relative_to(CONFIG_DIR))
        block = [
            f"# BEGIN {rel_path}",
            contents.rstrip(),
            f"# END {rel_path}",
            "",
        ]
        entries[rel_path] = block
    return entries


def merge_automations() -> list[str]:
    blocks = _build_automation_blocks()
    if not blocks:
        return []
    merged_path = CONFIG_DIR / "automations.yaml"
    existing_lines: list[str] = []
    if merged_path.exists():
        existing_lines = merged_path.read_text(encoding="utf-8").splitlines()
    if not existing_lines:
        new_content = "\n".join(
            line for block in blocks.values() for line in block
        ).strip() + "\n"
        merged_path.write_text(new_content, encoding="utf-8")
        return [str(merged_path.relative_to(CONFIG_DIR))]

    output: list[str] = []
    used_blocks: set[str] = set()
    index = 0
    while index < len(existing_lines):
        line = existing_lines[index]
        if line.startswith("# BEGIN "):
            marker = line.replace("# BEGIN ", "", 1).strip()
            index += 1
            while index < len(existing_lines) and not existing_lines[index].startswith("# END "):
                index += 1
            if index < len(existing_lines):
                index += 1
            block = blocks.get(marker)
            if block:
                output.extend(block)
                used_blocks.add(marker)
            continue
        output.append(line)
        index += 1

    remaining = [block for key, block in blocks.items() if key not in used_blocks]
    if remaining:
        if output and output[-1].strip():
            output.append("")
        for block in remaining:
            output.extend(block)
    new_content = "\n".join(output).strip() + "\n"
    old_content = "\n".join(existing_lines).strip() + "\n"
    if new_content != old_content:
        merged_path.write_text(new_content, encoding="utf-8")
        return [str(merged_path.relative_to(CONFIG_DIR))]
    return []


def update_source_from_markers() -> list[str]:
    merged_path = CONFIG_DIR / "automations.yaml"
    if not merged_path.exists():
        return []
    lines = merged_path.read_text(encoding="utf-8").splitlines()
    current_file: Path | None = None
    buffer: list[str] = []
    updated: list[str] = []

    def flush() -> None:
        nonlocal buffer, current_file
        if current_file is None:
            buffer = []
            return
        current_file.parent.mkdir(parents=True, exist_ok=True)
        current_file.write_text("\n".join(buffer).strip() + "\n", encoding="utf-8")
        updated.append(str(current_file.relative_to(CONFIG_DIR)))
        buffer = []

    for line in lines:
        if line.startswith("# BEGIN "):
            flush()
            rel = line.replace("# BEGIN ", "", 1).strip()
            current_file = CONFIG_DIR / rel
            buffer = []
            continue
        if line.startswith("# END "):
            flush()
            current_file = None
            continue
        if current_file is not None:
            buffer.append(line)
    flush()
    return updated


CONFIG_KEYS = {
    "remote_url",
    "remote_branch",
    "notification_enabled",
    "webhook_enabled",
    "webhook_path",
    "poll_interval_minutes",
    "merge_automations",
    "ui_theme",
}


def _coerce_config_value(key: str, value: Any) -> Any:
    if key in {"notification_enabled", "webhook_enabled", "merge_automations"}:
        if isinstance(value, bool):
            return value
        raise ValueError(f"{key} must be true or false")
    if key in {"remote_url", "remote_branch", "webhook_path"}:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        raise ValueError(f"{key} must be a string")
    if key == "ui_theme":
        if isinstance(value, str) and value.lower() in {"light", "dark", "system"}:
            return value.lower()
        raise ValueError("ui_theme must be light, dark, or system")
    if key == "poll_interval_minutes":
        if value is None:
            return None
        if isinstance(value, int):
            return value
        raise ValueError("poll_interval_minutes must be an integer or null")
    raise ValueError(f"Unsupported config key: {key}")


def load_config_data() -> dict[str, Any]:
    if not GITOPS_CONFIG_PATH.exists():
        write_gitops_config(OPTIONS)
    return load_gitops_config()


def load_full_config() -> dict[str, Any]:
    data = load_config_data()
    data["git_user_name"] = get_git_config_value("user.name")
    data["git_user_email"] = get_git_config_value("user.email")
    return data


def apply_config_update(payload: dict[str, Any]) -> dict[str, Any]:
    data = load_config_data()
    for key, value in payload.items():
        if key not in CONFIG_KEYS:
            raise ValueError(f"Unsupported config key: {key}")
        data[key] = _coerce_config_value(key, value)
    updated = _build_options(data)
    write_gitops_config(updated)
    return load_gitops_config()

class PendingTracker:
    def __init__(self) -> None:
        self.pending: set[str] = set()
        self.tasks: dict[str, asyncio.Task[None]] = {}
        self.lock = asyncio.Lock()
        self.loop: asyncio.AbstractEventLoop | None = None

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop

    def schedule(self, rel_path: str) -> None:
        if self.loop is None:
            return

        def _schedule() -> None:
            existing = self.tasks.get(rel_path)
            if existing:
                existing.cancel()
            self.tasks[rel_path] = asyncio.create_task(self._debounce_add(rel_path))

        self.loop.call_soon_threadsafe(_schedule)

    async def _debounce_add(self, rel_path: str) -> None:
        await asyncio.sleep(DEBOUNCE_SECONDS)
        async with self.lock:
            self.pending.add(rel_path)
        self.tasks.pop(rel_path, None)

    async def flush(self) -> list[str]:
        async with self.lock:
            pending = sorted(self.pending)
            self.pending.clear()
        return pending

    async def snapshot(self) -> list[str]:
        async with self.lock:
            return sorted(self.pending)


class ConfigEventHandler(FileSystemEventHandler):
    def __init__(self, tracker: PendingTracker) -> None:
        self.tracker = tracker

    def _handle(self, event: FileSystemEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if path.is_relative_to(CONFIG_DIR):
            rel = path.relative_to(CONFIG_DIR)
        else:
            return
        if should_ignore(rel):
            return
        self.tracker.schedule(str(rel))

    def on_modified(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_created(self, event: FileSystemEvent) -> None:
        self._handle(event)

    def on_moved(self, event: FileSystemEvent) -> None:
        self._handle(event)


tracker = PendingTracker()


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_gitops_config()
    ensure_repo()
    ensure_remote()
    ensure_ssh_agent_key()
    tracker.set_loop(asyncio.get_running_loop())
    observer = Observer()
    handler = ConfigEventHandler(tracker)
    observer.schedule(handler, str(CONFIG_DIR), recursive=True)
    observer.start()

    periodic_task = None
    if OPTIONS.poll_interval_minutes:
        periodic_task = asyncio.create_task(periodic_remote_check())

    try:
        yield
    finally:
        observer.stop()
        observer.join(timeout=5)
        if periodic_task:
            periodic_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await periodic_task


app = FastAPI(lifespan=lifespan)

static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(static_dir / "index.html")


@app.get("/api/status")
async def api_status() -> JSONResponse:
    pending = await tracker.snapshot()
    changes = git_status()
    staged_count = sum(1 for change in changes if change["staged"])
    unstaged_count = sum(1 for change in changes if change["unstaged"])
    untracked_count = sum(1 for change in changes if change["untracked"])
    remote_status = get_remote_status(refresh=False)
    return JSONResponse(
        {
            "pending": pending,
            "changes": changes,
            "commits": git_log(),
            "remote": OPTIONS.remote_url,
            "remote_status": remote_status,
            "branch": current_branch(),
            "staged_count": staged_count,
            "unstaged_count": unstaged_count,
            "untracked_count": untracked_count,
            "dirty": bool(changes),
            "merge_automations": OPTIONS.merge_automations,
            "gitops_config_path": str(GITOPS_CONFIG_PATH),
        }
    )


@app.get("/api/remote/status")
async def api_remote_status(refresh: bool = False) -> JSONResponse:
    return JSONResponse(get_remote_status(refresh=refresh))


@app.get("/api/config")
async def api_config() -> JSONResponse:
    return JSONResponse({"config": load_full_config(), "requires_restart": True})


@app.post("/api/config")
async def api_update_config(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        config_payload = dict(payload)
        if "git_user_name" in config_payload:
            set_git_config_value("user.name", config_payload.pop("git_user_name"))
        if "git_user_email" in config_payload:
            set_git_config_value("user.email", config_payload.pop("git_user_email"))
        requires_restart = bool(config_payload)
        if config_payload:
            apply_config_update(config_payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(
        {
            "status": "updated",
            "config": load_full_config(),
            "requires_restart": requires_restart,
        }
    )


@app.get("/api/branches")
async def api_branches() -> JSONResponse:
    return JSONResponse({"current": current_branch(), "branches": list_branches()})


@app.get("/api/commits")
async def api_commits(branch: str | None = None, limit: int = 50) -> JSONResponse:
    ref = branch or current_branch()
    if branch and not branch_exists(branch):
        raise HTTPException(status_code=404, detail="Branch not found")
    return JSONResponse({"branch": ref, "commits": git_commits(ref, limit=limit)})


@app.get("/api/commit/files")
async def api_commit_files(sha: str) -> JSONResponse:
    if not commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    changes = git_commit_changes(sha)
    return JSONResponse({"sha": sha, "files": changes})


@app.get("/api/commit/diff")
async def api_commit_diff(sha: str, path: str, max_lines: int | None = None) -> JSONResponse:
    if not commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    diff_data = git_commit_diff(sha, path, max_lines=max_lines)
    return JSONResponse({"sha": sha, "path": path, **diff_data})


@app.get("/api/diff")
async def api_diff(
    path: str,
    mode: str = "unstaged",
    max_lines: int | None = None,
    untracked: bool = False,
) -> JSONResponse:
    mode = mode.lower()
    if mode not in {"unstaged", "staged", "all"}:
        raise HTTPException(status_code=400, detail="Invalid diff mode")
    diff_data = git_diff(path, mode=mode, max_lines=max_lines, untracked=untracked)
    return JSONResponse({"path": path, "mode": mode, **diff_data})


@app.post("/api/stage")
async def api_stage(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    files = payload.get("files") or []
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    run_git(["add", "--", *files])
    return JSONResponse({"status": "staged", "files": files})


@app.post("/api/unstage")
async def api_unstage(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    files = payload.get("files") or []
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")
    run_git(["reset", "HEAD", "--", *files])
    return JSONResponse({"status": "unstaged", "files": files})


@app.post("/api/commit")
async def api_commit(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    message = payload.get("message")
    files = payload.get("files") or []
    include_unstaged = bool(payload.get("include_unstaged", True))
    if not message:
        raise HTTPException(status_code=400, detail="Commit message required")
    if files:
        run_git(["add", "--", *files])
    elif include_unstaged:
        run_git(["add", "-A"])
    result = run_git(["commit", "-m", message], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Commit failed")
    return JSONResponse({"status": "committed", "message": message})


@app.post("/api/reset")
async def api_reset(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    sha = payload.get("sha")
    confirm_dirty = bool(payload.get("confirm_dirty", False))
    stash_message = payload.get("message")
    if not sha:
        raise HTTPException(status_code=400, detail="Commit SHA required")
    if not commit_exists(sha):
        raise HTTPException(status_code=404, detail="Commit not found")
    dirty = not working_tree_clean()
    stash_branch = None
    if dirty:
        if not confirm_dirty:
            raise HTTPException(
                status_code=409,
                detail="Working tree has uncommitted changes. Confirmation required.",
            )
        stash_branch = create_gitops_stash_branch(stash_message)
    result = run_git(["reset", "--hard", sha], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Reset failed")
    return JSONResponse(
        {"status": "reset", "sha": sha, "stash_branch": stash_branch, "dirty": dirty}
    )


@app.post("/api/push")
async def api_push() -> JSONResponse:
    ensure_remote()
    if not OPTIONS.remote_url:
        raise HTTPException(status_code=400, detail="Remote URL is not configured")
    result = run_git(["push", "origin", OPTIONS.remote_branch], check=False)
    if result.returncode == 0:
        return JSONResponse({"status": "pushed"})
    if "non-fast-forward" in result.stderr or "fetch first" in result.stderr:
        branch = f"ha-local-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        run_git(["checkout", "-b", branch])
        run_git(["push", "-u", "origin", branch])
        run_git(["checkout", OPTIONS.remote_branch])
        await notify(
            "HA Config Version Control",
            f"Remote has new commits. Your changes were pushed to {branch}.",
            "gitops-push-conflict",
        )
        return JSONResponse({"status": "pushed", "branch": branch})
    raise HTTPException(status_code=400, detail=result.stderr.strip() or "Push failed")


@app.post("/api/pull")
async def api_pull() -> JSONResponse:
    changes = await handle_pull()
    return JSONResponse({"status": "pulled", "changes": changes})


@app.post("/api/ssh/generate")
async def api_generate_key() -> JSONResponse:
    if not get_ssh_status()["ssh_keygen_available"]:
        raise HTTPException(status_code=500, detail="ssh-keygen is not available in the add-on image")
    try:
        SSH_DIR.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Unable to create {SSH_DIR}: {exc.strerror or 'permission denied'}",
        ) from exc
    if not os.access(SSH_DIR, os.W_OK):
        raise HTTPException(status_code=500, detail=f"SSH directory is not writable: {SSH_DIR}")
    key_path = SSH_DIR / "id_ed25519"
    if key_path.exists():
        raise HTTPException(status_code=400, detail="SSH key already exists")
    result = subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(key_path), "-N", ""],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise HTTPException(status_code=500, detail=result.stderr.strip() or "Key generation failed")
    ensure_ssh_agent_key()
    return JSONResponse({"status": "generated", "public_key": key_path.with_suffix(".pub").read_text(encoding="utf-8")})


@app.get("/api/ssh/status")
async def api_ssh_status() -> JSONResponse:
    return JSONResponse(get_ssh_status())


@app.get("/api/ssh/public_key")
async def api_public_key() -> JSONResponse:
    key_path = SSH_DIR / "id_ed25519.pub"
    if not key_path.exists():
        raise HTTPException(status_code=404, detail="No public key found")
    return JSONResponse({"public_key": key_path.read_text(encoding="utf-8")})


@app.post("/api/ssh/test")
async def api_ssh_test(payload: dict[str, Any] | None = Body(default=None)) -> JSONResponse:
    data = payload or {}
    host = data.get("host") or "git@github.com"
    if not isinstance(host, str) or not host:
        raise HTTPException(status_code=400, detail="Host must be a string")
    status = get_ssh_status()
    if not status["ssh_available"]:
        raise HTTPException(status_code=500, detail="ssh client is not available in the add-on image")
    if not status["private_key_exists"]:
        raise HTTPException(status_code=400, detail="SSH key not found")
    result = subprocess.run(
        [
            "ssh",
            "-T",
            "-o",
            "BatchMode=yes",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            "ConnectTimeout=8",
            host,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    output = f"{result.stdout}\n{result.stderr}".strip()
    normalized = output.lower()
    success = result.returncode == 0 or (
        result.returncode == 1 and "successfully authenticated" in normalized
    )
    message = "SSH authentication succeeded." if success else "SSH authentication failed."
    if "github" in normalized and "successfully authenticated" in normalized:
        message = "Authenticated with GitHub. GitHub does not provide shell access."
    return JSONResponse(
        {
            "status": "success" if success else "failed",
            "returncode": result.returncode,
            "message": message,
            "output": output,
            "host": host,
        }
    )


@app.post("/api/automation/merge")
async def api_merge_automations() -> JSONResponse:
    if not OPTIONS.merge_automations:
        raise HTTPException(status_code=400, detail="Automation merge is disabled")
    changed = merge_automations()
    return JSONResponse({"status": "merged", "files": changed})


@app.post("/api/automation/sync")
async def api_sync_automations() -> JSONResponse:
    if not OPTIONS.merge_automations:
        raise HTTPException(status_code=400, detail="Automation merge is disabled")
    changed = update_source_from_markers()
    return JSONResponse({"status": "synced", "files": changed})


@app.post("/api/webhook/{path}")
async def api_webhook(path: str) -> JSONResponse:
    if not OPTIONS.webhook_enabled or path != OPTIONS.webhook_path:
        raise HTTPException(status_code=404, detail="Webhook not enabled")
    changes = await handle_pull()
    return JSONResponse({"status": "pulled", "changes": changes})


async def handle_pull() -> list[str]:
    ensure_remote()
    if not OPTIONS.remote_url:
        raise HTTPException(status_code=400, detail="Remote URL is not configured")
    if not working_tree_clean():
        await notify(
            "HA Config Version Control",
            "Remote updates are available, but there are local uncommitted changes.",
            "gitops-pull-blocked",
        )
        raise HTTPException(status_code=409, detail="Working tree is dirty")
    run_git(["fetch", "origin", OPTIONS.remote_branch])
    result = run_git(["pull", "--ff-only", "origin", OPTIONS.remote_branch], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Pull failed")
    pull_output = f"{result.stdout}\n{result.stderr}".lower()
    if "already up to date" in pull_output:
        return []
    previous_head = run_git(["rev-parse", "HEAD@{1}"], check=False)
    if previous_head.returncode != 0:
        return []
    changed_files = run_git(
        ["diff", "--name-only", previous_head.stdout.strip(), "HEAD"], check=False
    ).stdout.splitlines()
    if OPTIONS.merge_automations and any(
        path.lower().startswith("automations/") for path in changed_files
    ):
        changed_files.extend(merge_automations())
    domains = list_changed_domains(changed_files)
    for domain in domains:
        await call_service(domain, "reload")
    if not domains and changed_files:
        await notify(
            "HA Config Version Control",
            "Configuration changes pulled. A Home Assistant restart may be required.",
            "gitops-restart-needed",
        )
    return changed_files


async def periodic_remote_check() -> None:
    while True:
        interval = OPTIONS.poll_interval_minutes or 0
        await asyncio.sleep(interval * 60)
        if not OPTIONS.remote_url:
            continue
        ensure_remote()
        run_git(["fetch", "origin", OPTIONS.remote_branch], check=False)
        behind = run_git(
            ["rev-list", "--count", f"HEAD..origin/{OPTIONS.remote_branch}"]
        ).stdout.strip()
        if behind and int(behind) > 0:
            if working_tree_clean():
                await handle_pull()
            else:
                await notify(
                    "HA Config Version Control",
                    "Remote updates are available but local changes are uncommitted.",
                    "gitops-periodic-behind",
                )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8099)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=args.port)


if __name__ == "__main__":
    main()
