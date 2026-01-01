from __future__ import annotations

import argparse
import asyncio
import contextlib
import fnmatch
import json
import os
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
    ]
    return "\n".join(lines) + "\n"


def write_gitops_config(options: Options) -> None:
    content = render_gitops_config(options)
    GITOPS_CONFIG_PATH.write_text(content, encoding="utf-8")


def _build_options(data: dict[str, Any]) -> Options:
    return Options(
        remote_url=data.get("remote_url") or None,
        remote_branch=data.get("remote_branch", "main"),
        notification_enabled=bool(data.get("notification_enabled", True)),
        webhook_enabled=bool(data.get("webhook_enabled", False)),
        webhook_path=data.get("webhook_path", "pull"),
        poll_interval_minutes=data.get("poll_interval_minutes", 15),
        merge_automations=bool(data.get("merge_automations", True)),
    )


def load_options() -> Options:
    if not GITOPS_CONFIG_PATH.exists():
        seed: dict[str, Any] = {}
        if OPTIONS_PATH.exists():
            seed = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
        write_gitops_config(_build_options(seed))
    data = load_gitops_config()
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


def run_git(args: Iterable[str], check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args],
        cwd=CONFIG_DIR,
        text=True,
        capture_output=True,
        check=check,
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


def git_status() -> list[dict[str, str]]:
    result = run_git(["status", "--porcelain"], check=False)
    changes = []
    for line in result.stdout.splitlines():
        if not line:
            continue
        status = line[:2]
        path = line[3:]
        changes.append({"status": status, "path": path})
    return changes


def git_log(limit: int = 20) -> list[dict[str, str]]:
    result = run_git([
        "--no-pager",
        "log",
        f"-n{limit}",
        "--pretty=format:%h%x09%an%x09%ad%x09%s",
        "--date=short",
    ], check=False)
    entries = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            entries.append(
                {
                    "sha": parts[0],
                    "author": parts[1],
                    "date": parts[2],
                    "subject": parts[3],
                }
            )
    return entries


def git_diff(path: str) -> str:
    result = run_git(["--no-pager", "diff", "--", path], check=False)
    return result.stdout


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
    return JSONResponse(
        {
            "pending": pending,
            "changes": git_status(),
            "commits": git_log(),
            "remote": OPTIONS.remote_url,
            "merge_automations": OPTIONS.merge_automations,
            "gitops_config_path": str(GITOPS_CONFIG_PATH),
        }
    )


@app.get("/api/config")
async def api_config() -> JSONResponse:
    return JSONResponse({"config": load_config_data(), "requires_restart": True})


@app.post("/api/config")
async def api_update_config(payload: dict[str, Any] = Body(...)) -> JSONResponse:
    try:
        updated = apply_config_update(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse({"status": "updated", "config": updated, "requires_restart": True})


@app.get("/api/diff")
async def api_diff(path: str) -> JSONResponse:
    diff = git_diff(path)
    return JSONResponse({"path": path, "diff": diff})


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
    if not message:
        raise HTTPException(status_code=400, detail="Commit message required")
    if files:
        run_git(["add", "--", *files])
    else:
        run_git(["add", "-A"])
    result = run_git(["commit", "-m", message], check=False)
    if result.returncode != 0:
        raise HTTPException(status_code=400, detail=result.stderr.strip() or "Commit failed")
    return JSONResponse({"status": "committed", "message": message})


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
    SSH_DIR.mkdir(parents=True, exist_ok=True)
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
    return JSONResponse({"status": "generated", "public_key": key_path.with_suffix(".pub").read_text(encoding="utf-8")})


@app.get("/api/ssh/public_key")
async def api_public_key() -> JSONResponse:
    key_path = SSH_DIR / "id_ed25519.pub"
    if not key_path.exists():
        raise HTTPException(status_code=404, detail="No public key found")
    return JSONResponse({"public_key": key_path.read_text(encoding="utf-8")})


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
