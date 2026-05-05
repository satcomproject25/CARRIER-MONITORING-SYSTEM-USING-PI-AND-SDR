"""
CMS orchestrator — single HTTP control plane for the Loveable/Vite frontend.

Starts/stops the GNU Radio flowgraph (sdr_scipy.py) and the headless detector
(Interference.py) without opening desktop spectrum windows. Detection math is
unchanged; only window visibility and process wiring differ.

Environment (optional):
  SCIPY_BACKEND_DIR — override backend directory (default: this file's folder)
  SCIPY_SNAPSHOT_PORT — port where Interference exposes /api/snapshot (default: 8766)
  SCIPY_ORCHESTRATOR_PORT — this service (default: 8780)
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
import json
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from flask import Flask, jsonify, request

BACKEND_DIR = Path(os.environ.get("SCIPY_BACKEND_DIR", Path(__file__).resolve().parent))
SNAPSHOT_PORT = int(os.environ.get("SCIPY_SNAPSHOT_PORT", "8766"))
ORCHESTRATOR_PORT = int(os.environ.get("SCIPY_ORCHESTRATOR_PORT", "8780"))
CONFIG_MANAGER_PORT = int(os.environ.get("SCIPY_CONFIG_PORT", "5580"))

_sdr_proc: subprocess.Popen | None = None
_det_proc: subprocess.Popen | None = None

app = Flask(__name__)


def _cors(resp):
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type"
    resp.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    return resp


@app.after_request
def _after(resp):
    return _cors(resp)


@app.route("/api/health", methods=["GET"])
def health():
    return jsonify({
        "status": "ok",
        "sdr_running": _sdr_proc is not None and _sdr_proc.poll() is None,
        "detector_running": _det_proc is not None and _det_proc.poll() is None,
        "snapshot_port": SNAPSHOT_PORT,
    })


def _python() -> str:
    return sys.executable


def _start_sdr(headless: bool = True) -> subprocess.Popen:
    env = os.environ.copy()
    if headless:
        env["SCIPY_SDR_HEADLESS"] = "1"
    script = BACKEND_DIR / "sdr_scipy.py"
    return subprocess.Popen(
        [_python(), "-u", str(script)],
        cwd=str(BACKEND_DIR),
        env=env,
    )


def _start_detector(headless: bool = True, antenna_id: str = "gsat-30") -> subprocess.Popen:
    env = os.environ.copy()
    if headless:
        env["SCIPY_HEADLESS"] = "1"
    env["SCIPY_SNAPSHOT_PORT"] = str(SNAPSHOT_PORT)
    env["SCIPY_ACTIVE_ANTENNA"] = antenna_id
    script = BACKEND_DIR / "Interference.py"
    return subprocess.Popen(
        [_python(), "-u", str(script)],
        cwd=str(BACKEND_DIR),
        env=env,
    )


def _config_api_url(path: str, antenna_id: str | None = None) -> str:
    base = f"http://127.0.0.1:{CONFIG_MANAGER_PORT}{path}"
    if antenna_id:
        sep = "&" if "?" in base else "?"
        base = f"{base}{sep}antenna_id={urllib.parse.quote(antenna_id)}"
    return base


def _http_json(url: str, method: str = "GET", body: dict | None = None, timeout: float = 2.0):
    payload = None
    headers = {}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url=url, data=payload, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _terminate(proc: subprocess.Popen | None):
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()


@app.route("/api/monitor/start", methods=["POST", "OPTIONS"])
def monitor_start():
    global _sdr_proc, _det_proc
    if request.method == "OPTIONS":
        return ("", 204)

    body = request.get_json(silent=True) or {}
    start_sdr = body.get("start_sdr", True)
    delay_s = float(body.get("sdr_settle_s", 2.0))
    antenna_id = (body.get("antenna_id") or "gsat-30").strip().lower()

    if _det_proc is not None and _det_proc.poll() is None:
        return jsonify({"status": "already_running"}), 200

    if start_sdr:
        if _sdr_proc is None or _sdr_proc.poll() is not None:
            _sdr_proc = _start_sdr(headless=True)
        time.sleep(max(0.0, delay_s))
    _det_proc = _start_detector(headless=True, antenna_id=antenna_id)
    return jsonify({
        "status": "started",
        "antenna_id": antenna_id,
        "sdr_pid": _sdr_proc.pid if _sdr_proc else None,
        "detector_pid": _det_proc.pid if _det_proc else None,
    })


@app.route("/api/monitor/stop", methods=["POST", "OPTIONS"])
def monitor_stop():
    global _sdr_proc, _det_proc
    if request.method == "OPTIONS":
        return ("", 204)

    body = request.get_json(silent=True) or {}
    stop_sdr = body.get("stop_sdr", True)

    _terminate(_det_proc)
    _det_proc = None
    if stop_sdr:
        _terminate(_sdr_proc)
        _sdr_proc = None
    return jsonify({"status": "stopped"})


@app.route("/api/snapshot", methods=["GET"])
def snapshot_proxy():
    url = f"http://127.0.0.1:{SNAPSHOT_PORT}/api/snapshot"
    try:
        with urllib.request.urlopen(url, timeout=2.0) as r:
            return (r.read(), 200, {"Content-Type": "application/json"})
    except urllib.error.URLError as e:
        return jsonify({"error": "detector_unreachable", "detail": str(e)}), 503


@app.route("/api/set_smoothing", methods=["POST", "OPTIONS"])
def set_smoothing_proxy():
    if request.method == "OPTIONS":
        return ("", 204)
    url = f"http://127.0.0.1:{SNAPSHOT_PORT}/api/set_smoothing"
    try:
        payload = json.dumps(request.get_json(silent=True) or {}).encode("utf-8")
        req = urllib.request.Request(
            url=url, data=payload, method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=2.0) as r:
            return (r.read(), 200, {"Content-Type": "application/json"})
    except urllib.error.URLError as e:
        return jsonify({"error": "detector_unreachable", "detail": str(e)}), 503


@app.route("/api/frequencies", methods=["GET", "POST", "OPTIONS"])
def frequencies():
    if request.method == "OPTIONS":
        return ("", 204)
    antenna_id = request.args.get("antenna_id")
    if request.method == "GET":
        url = _config_api_url("/api/frequencies", antenna_id=antenna_id)
        try:
            return jsonify(_http_json(url, "GET"))
        except Exception as e:
            return jsonify({"error": "config_manager_unreachable", "detail": str(e)}), 503
    body = request.get_json(silent=True) or {}
    antenna_id = (body.get("antenna_id") or antenna_id or "gsat-30").strip().lower()
    url = _config_api_url("/api/frequencies")
    try:
        return jsonify(_http_json(url, "POST", {
            "antenna_id": antenna_id,
            "center": body.get("center"),
            "bandwidth": body.get("bandwidth", 500e3),
            "label": body.get("label", ""),
        }))
    except Exception as e:
        return jsonify({"error": "config_manager_unreachable", "detail": str(e)}), 503


@app.route("/api/frequencies/<int:idx>", methods=["DELETE", "OPTIONS"])
def frequency_delete(idx: int):
    if request.method == "OPTIONS":
        return ("", 204)
    antenna_id = (request.args.get("antenna_id") or "gsat-30").strip().lower()
    url = _config_api_url(f"/api/frequencies/{idx}", antenna_id=antenna_id)
    try:
        return jsonify(_http_json(url, "DELETE"))
    except Exception as e:
        return jsonify({"error": "config_manager_unreachable", "detail": str(e)}), 503


if __name__ == "__main__":
    import logging
    logging.getLogger("werkzeug").setLevel(logging.ERROR)
    print(f"[orchestrator] http://127.0.0.1:{ORCHESTRATOR_PORT}")
    print("  POST /api/monitor/start   — headless SDR + Interference.py")
    print("  POST /api/monitor/stop")
    print("  GET  /api/snapshot        — proxy to detector")
    app.run(host="127.0.0.1", port=ORCHESTRATOR_PORT, threaded=True, use_reloader=False)
