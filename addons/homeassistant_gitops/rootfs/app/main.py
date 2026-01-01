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


def load_options() -> Options:
    data: dict[str, Any] = {}
    if OPTIONS_PATH.exists():
        data = json.loads(OPTIONS_PATH.read_text(encoding="utf-8"))
    return Options(
        remote_url=data.get("remote_url") or None,
        remote_branch=data.get("remote_branch", "main"),
        notification_enabled=bool(data.get("notification_enabled", True)),
        webhook_enabled=bool(data.get("webhook_enabled", False)),
        webhook_path=data.get("webhook_path", "pull"),
        poll_interval_minutes=data.get("poll_interval_minutes", 15),
        merge_automations=bool(data.get("merge_automations", True)),
    )


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


def merge_automations() -> list[str]:
    automations_dir = CONFIG_DIR / "automations"
    if not automations_dir.exists():
        return []
    merged_path = CONFIG_DIR / "automations.yaml"
    entries: list[str] = []
    for file_path in sorted(automations_dir.glob("*.y*ml")):
        contents = file_path.read_text(encoding="utf-8")
        entries.append(f"# BEGIN {file_path.relative_to(CONFIG_DIR)}")
        entries.append(contents.rstrip())
        entries.append(f"# END {file_path.relative_to(CONFIG_DIR)}")
        entries.append("")
    merged_path.write_text("\n".join(entries).strip() + "\n", encoding="utf-8")
    return [str(merged_path.relative_to(CONFIG_DIR))]


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
    ensure_repo()
    ensure_remote()
    if OPTIONS.merge_automations:
        merge_automations()
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
        }
    )


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
    changed = merge_automations()
    return JSONResponse({"status": "merged", "files": changed})


@app.post("/api/automation/sync")
async def api_sync_automations() -> JSONResponse:
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
