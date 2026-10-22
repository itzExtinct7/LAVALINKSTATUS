#!/usr/bin/env python3
"""Poll a Lavalink REST API and publish a sanitized public status snapshot."""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
STATUS_FILE = DATA_DIR / "status.json"
HISTORY_FILE = DATA_DIR / "history.json"

HOST = os.getenv("LAVALINK_HOST", "budget-us7.bot.heavencloud.in").strip()
PORT = os.getenv("LAVALINK_PORT", "6706").strip()
SECURE = os.getenv("LAVALINK_SECURE", "false").strip().lower() in {"1", "true", "yes", "on"}
# No GitHub Actions secret required. WARNING: committing this file to a public repo exposes the password.
PASSWORD = "youshallnotpass"
BASE_URL = f"{'https' if SECURE else 'http'}://{HOST}:{PORT}"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return fallback


def request(path: str, timeout: int = 10):
    headers = {"User-Agent": "Lavalink-Pulse-Monitor/1.0", "Accept": "application/json, text/plain"}
    if PASSWORD:
        headers["Authorization"] = PASSWORD
    req = Request(f"{BASE_URL}{path}", headers=headers, method="GET")
    started = time.monotonic()
    try:
        with urlopen(req, timeout=timeout) as response:
            body = response.read()
            elapsed_ms = round((time.monotonic() - started) * 1000, 2)
            text = body.decode("utf-8", errors="replace")
            if "json" in response.headers.get("Content-Type", "").lower() or text.lstrip().startswith(("{", "[")):
                try:
                    return response.status, json.loads(text), elapsed_ms
                except json.JSONDecodeError:
                    return response.status, text, elapsed_ms
            return response.status, text.strip(), elapsed_ms
    except HTTPError as exc:
        # Do not copy response bodies into the public status file: they can vary by server.
        raise RuntimeError(f"HTTP {exc.code}: {http_error_message(exc.code)}") from None
    except (URLError, TimeoutError, OSError) as exc:
        reason = getattr(exc, "reason", None)
        if isinstance(reason, TimeoutError) or "timed out" in str(exc).lower():
            raise RuntimeError("Connection timed out") from None
        if isinstance(reason, OSError) or isinstance(exc, OSError):
            raise RuntimeError("Connection failed or node is unreachable") from None
        raise RuntimeError("Could not connect to Lavalink REST API") from None


def http_error_message(code: int) -> str:
    if code == 401:
        return "authentication failed; check the password configured in monitor.py"
    if code == 403:
        return "request forbidden by the node"
    if code == 404:
        return "endpoint not found; API version may differ"
    if code == 429:
        return "rate limited by the node"
    return "request rejected by node"


def fetch_stats_and_info():
    # Lavalink v4 uses /v4; try /v3 only if v4's stats endpoint is not present.
    try:
        code, stats, latency_ms = request("/v4/stats")
        api_version = "v4"
    except RuntimeError as exc:
        if "HTTP 404" not in str(exc):
            raise
        code, stats, latency_ms = request("/v3/stats")
        api_version = "v3"

    if not isinstance(stats, dict):
        raise RuntimeError("Stats endpoint returned an unexpected response")

    info = {}
    try:
        _, info_result, _ = request(f"/{api_version}/info")
        if isinstance(info_result, dict):
            info = info_result
    except RuntimeError:
        # Stats still confirms the node is responding; info is a supplemental field.
        pass

    version = "unknown"
    try:
        _, version_result, _ = request("/version")
        if isinstance(version_result, str) and version_result:
            version = version_result[:120]
    except RuntimeError:
        version_obj = info.get("version", {}) if isinstance(info, dict) else {}
        if isinstance(version_obj, dict):
            version = str(version_obj.get("semver") or version_obj.get("version") or "unknown")

    memory = stats.get("memory") if isinstance(stats.get("memory"), dict) else {}
    cpu = stats.get("cpu") if isinstance(stats.get("cpu"), dict) else {}
    metrics = {
        "players": safe_num(stats.get("players")),
        "playing_players": safe_num(stats.get("playingPlayers")),
        "uptime_ms": safe_num(stats.get("uptime")),
        "memory": {
            "free": safe_num(memory.get("free")),
            "used": safe_num(memory.get("used")),
            "allocated": safe_num(memory.get("allocated")),
            "reservable": safe_num(memory.get("reservable")),
        },
        "cpu": {
            "cores": safe_num(cpu.get("cores")),
            "systemLoad": safe_num(cpu.get("systemLoad")),
            "lavalinkLoad": safe_num(cpu.get("lavalinkLoad")),
        },
    }
    return api_version, version, metrics, latency_ms, info


def safe_num(value):
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = float(value)
        if number.is_integer():
            return int(number)
        return number
    except (TypeError, ValueError, OverflowError):
        return None


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    checked_at = iso_now()
    status = {
        "checked_at": checked_at,
        "status": "pending",
        "online": None,
        "host": HOST,
        "port": int(PORT) if PORT.isdigit() else PORT,
        "secure": SECURE,
        "api_version": None,
        "version": None,
        "latency_ms": None,
        "metrics": {},
        "error": None,
        "monitor_interval_seconds": 300,
    }
    try:
        api_version, version, metrics, latency_ms, info = fetch_stats_and_info()
        status.update({
            "status": "online",
            "online": True,
            "api_version": api_version,
            "version": version,
            "latency_ms": latency_ms,
            "metrics": metrics,
            "server_info": {
                "version": info.get("version", {}) if isinstance(info, dict) else {},
                "sourceManagers": info.get("sourceManagers", []) if isinstance(info, dict) else [],
                "filters": info.get("filters", []) if isinstance(info, dict) else [],
                "plugins": info.get("plugins", []) if isinstance(info, dict) else [],
            },
        })
    except RuntimeError as exc:
        status.update({"status": "offline", "online": False, "error": str(exc)})
    except Exception as exc:  # Best-effort monitor: publish a sanitized generic error.
        print(f"Unexpected monitor error: {type(exc).__name__}", file=sys.stderr)
        status.update({"status": "offline", "online": False, "error": "Unexpected monitor error; inspect the workflow log."})

    metrics = status.get("metrics") or {}
    memory = metrics.get("memory") or {}
    cpu = metrics.get("cpu") or {}
    sample = {
        "checked_at": status["checked_at"],
        "status": status["status"],
        "online": status["online"],
        "latency_ms": status["latency_ms"],
        "version": status["version"],
        "players": metrics.get("players"),
        "playing_players": metrics.get("playing_players"),
        "uptime_ms": metrics.get("uptime_ms"),
        "memory_used_bytes": memory.get("used"),
        "memory_allocated_bytes": memory.get("allocated"),
        "cpu_system_load": cpu.get("systemLoad"),
        "error": status["error"],
    }

    history = read_json(HISTORY_FILE, [])
    if not isinstance(history, list):
        history = []
    history.append(sample)
    cutoff = utc_now() - timedelta(days=30, minutes=10)
    kept = []
    for item in history:
        try:
            t = datetime.fromisoformat(str(item.get("checked_at", "")).replace("Z", "+00:00"))
            if t.tzinfo is None:
                t = t.replace(tzinfo=timezone.utc)
            if t >= cutoff:
                kept.append(item)
        except (TypeError, ValueError):
            continue
    history = kept[-9000:]

    STATUS_FILE.write_text(json.dumps(status, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    HISTORY_FILE.write_text(json.dumps(history, separators=(",", ":"), ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Monitor result: {status['status']} | {checked_at} | API={status.get('api_version') or 'unknown'} | samples={len(history)}")
    if status.get("error"):
        print(f"Status message: {status['error']}")
    return 0  # publish failures as status data instead of failing before files are committed


if __name__ == "__main__":
    raise SystemExit(main())
