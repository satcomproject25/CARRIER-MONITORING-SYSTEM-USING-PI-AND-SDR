"""
Authorized Frequency Manager with per-antenna isolation.

Each antenna/site gets its own authorized frequency list so frequency tuning
cannot bleed between assets (e.g. GSAT-30 list is independent from INTELSAT-28).
"""

import json
import os
import threading
from typing import Any

try:
    from flask import Flask, jsonify, render_template_string, request
    FLASK_AVAILABLE = True
except ImportError:
    FLASK_AVAILABLE = False

_CONFIG_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "authorized_freqs.json",
)

_DEFAULT_ANTENNA = "gsat-30"

_HTML_TEMPLATE = r"""
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>Authorized Frequency Manager</title>
  <style>
    body { font-family: Segoe UI, Arial, sans-serif; background:#0d1117; color:#c9d1d9; margin:0; padding:20px; }
    .wrap { max-width: 980px; margin: 0 auto; }
    h1 { margin: 0 0 8px 0; color:#79c0ff; }
    .panel { background:#161b22; border:1px solid #30363d; border-radius:10px; padding:14px; margin-bottom:14px; }
    label { font-size:12px; color:#8b949e; display:block; margin-bottom:4px; }
    input, select { background:#0d1117; color:#c9d1d9; border:1px solid #30363d; border-radius:6px; padding:8px; width:180px; }
    button { border:none; border-radius:6px; padding:8px 12px; color:white; background:#238636; cursor:pointer; }
    button.del { background:#da3633; }
    table { width:100%; border-collapse:collapse; }
    th, td { border-top:1px solid #21262d; padding:10px; text-align:left; font-size:13px; }
    th { color:#79c0ff; background:#21262d; }
    .row { display:flex; gap:10px; align-items:end; flex-wrap:wrap; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>Authorized Frequency Manager</h1>
  <div class="panel">
    <div class="row">
      <div><label>Antenna ID</label><input id="ant" placeholder="gsat-30" value="gsat-30"/></div>
      <div><label>Center (MHz)</label><input id="cf" type="number" step="0.001" /></div>
      <div><label>Bandwidth (kHz)</label><input id="bw" type="number" step="1" value="500" /></div>
      <div><label>Label</label><input id="lb" /></div>
      <button onclick="add()">Add</button>
      <button onclick="load()">Refresh</button>
    </div>
  </div>
  <div class="panel">
    <table>
      <thead><tr><th>#</th><th>Label</th><th>Center</th><th>Bandwidth</th><th>Range</th><th>Action</th></tr></thead>
      <tbody id="tb"></tbody>
    </table>
  </div>
</div>
<script>
function aid(){ return (document.getElementById('ant').value || 'gsat-30').trim().toLowerCase(); }
async function load(){
  const res = await fetch(`/api/frequencies?antenna_id=${encodeURIComponent(aid())}`);
  const data = await res.json();
  const tb = document.getElementById('tb');
  const arr = data.frequencies || [];
  if (!arr.length) { tb.innerHTML = `<tr><td colspan="6" style="color:#8b949e">No frequencies for this antenna</td></tr>`; return; }
  tb.innerHTML = arr.map((f,i)=>{
    const lo = (f.center/1e6 - f.bandwidth/2e6).toFixed(3);
    const hi = (f.center/1e6 + f.bandwidth/2e6).toFixed(3);
    return `<tr>
      <td>${i+1}</td><td>${f.label || '—'}</td>
      <td>${(f.center/1e6).toFixed(3)} MHz</td>
      <td>${(f.bandwidth/1e3).toFixed(1)} kHz</td>
      <td>${lo} - ${hi} MHz</td>
      <td><button class="del" onclick="delFreq(${i})">Delete</button></td>
    </tr>`;
  }).join('');
}
async function add(){
  const center = Number(document.getElementById('cf').value) * 1e6;
  const bandwidth = Number(document.getElementById('bw').value) * 1e3;
  const label = (document.getElementById('lb').value || '').trim();
  await fetch('/api/frequencies', {
    method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({antenna_id: aid(), center, bandwidth, label}),
  });
  await load();
}
async function delFreq(idx){
  await fetch(`/api/frequencies/${idx}?antenna_id=${encodeURIComponent(aid())}`, {method:'DELETE'});
  await load();
}
load();
</script>
</body>
</html>
"""


def _normalize_antenna_id(antenna_id: str | None) -> str:
    val = (antenna_id or _DEFAULT_ANTENNA).strip().lower()
    return val or _DEFAULT_ANTENNA


class AuthorizedFrequencyManager:
    def __init__(self, port: int = 5580, auto_start: bool = True, active_antenna: str | None = None):
        self._lock = threading.Lock()
        self._port = port
        self._active_antenna = _normalize_antenna_id(active_antenna)
        self._frequencies_by_antenna: dict[str, list[dict[str, Any]]] = {}
        self._load()
        if auto_start and FLASK_AVAILABLE:
            self._start_web_server()

    def set_active_antenna(self, antenna_id: str | None):
        with self._lock:
            self._active_antenna = _normalize_antenna_id(antenna_id)

    def get_active_antenna(self) -> str:
        with self._lock:
            return self._active_antenna

    def _ensure_antenna(self, antenna_id: str):
        if antenna_id not in self._frequencies_by_antenna:
            self._frequencies_by_antenna[antenna_id] = []

    def _load(self):
        if not os.path.exists(_CONFIG_FILE):
            self._frequencies_by_antenna = {_DEFAULT_ANTENNA: []}
            return
        try:
            with open(_CONFIG_FILE, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if isinstance(payload, list):
                # Backward compatibility: single shared list -> default antenna list
                self._frequencies_by_antenna = {_DEFAULT_ANTENNA: payload}
            elif isinstance(payload, dict):
                self._frequencies_by_antenna = {}
                for k, v in payload.items():
                    if isinstance(v, list):
                        self._frequencies_by_antenna[_normalize_antenna_id(k)] = v
            else:
                self._frequencies_by_antenna = {_DEFAULT_ANTENNA: []}
        except Exception as exc:
            print(f"[CONFIG] Failed to load {_CONFIG_FILE}: {exc}")
            self._frequencies_by_antenna = {_DEFAULT_ANTENNA: []}

    def _save(self):
        try:
            with open(_CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self._frequencies_by_antenna, f, indent=2)
        except Exception as exc:
            print(f"[CONFIG] Save error: {exc}")

    def is_authorized(self, freq_hz: float, antenna_id: str | None = None) -> bool:
        aid = _normalize_antenna_id(antenna_id or self.get_active_antenna())
        with self._lock:
            for entry in self._frequencies_by_antenna.get(aid, []):
                c = entry["center"]
                half_bw = entry["bandwidth"] / 2.0
                if (c - half_bw) <= freq_hz <= (c + half_bw):
                    return True
        return False

    def get_all(self, antenna_id: str | None = None) -> list[dict]:
        aid = _normalize_antenna_id(antenna_id or self.get_active_antenna())
        with self._lock:
            return list(self._frequencies_by_antenna.get(aid, []))

    def add(self, center_hz: float, bandwidth_hz: float, label: str = "", antenna_id: str | None = None):
        aid = _normalize_antenna_id(antenna_id or self.get_active_antenna())
        with self._lock:
            self._ensure_antenna(aid)
            self._frequencies_by_antenna[aid].append({
                "center": float(center_hz),
                "bandwidth": float(bandwidth_hz),
                "label": label,
            })
            self._save()

    def remove(self, index: int, antenna_id: str | None = None):
        aid = _normalize_antenna_id(antenna_id or self.get_active_antenna())
        with self._lock:
            arr = self._frequencies_by_antenna.get(aid, [])
            if 0 <= index < len(arr):
                arr.pop(index)
                self._save()

    def update(self, index: int, center_hz=None, bandwidth_hz=None, label=None, antenna_id: str | None = None):
        aid = _normalize_antenna_id(antenna_id or self.get_active_antenna())
        with self._lock:
            arr = self._frequencies_by_antenna.get(aid, [])
            if 0 <= index < len(arr):
                entry = arr[index]
                if center_hz is not None:
                    entry["center"] = float(center_hz)
                if bandwidth_hz is not None:
                    entry["bandwidth"] = float(bandwidth_hz)
                if label is not None:
                    entry["label"] = label
                self._save()

    def _start_web_server(self):
        app = Flask(__name__)
        mgr = self

        def _req_aid(default_to_active: bool = True) -> str:
            aid = request.args.get("antenna_id")
            if aid is None and request.is_json:
                payload = request.get_json(silent=True) or {}
                aid = payload.get("antenna_id")
            if aid is None and default_to_active:
                aid = mgr.get_active_antenna()
            return _normalize_antenna_id(aid)

        @app.route("/")
        def index():
            return render_template_string(_HTML_TEMPLATE)

        @app.route("/api/active-antenna", methods=["GET", "POST"])
        def active_antenna():
            if request.method == "POST":
                payload = request.get_json(force=True) if request.is_json else {}
                aid = _normalize_antenna_id(payload.get("antenna_id"))
                mgr.set_active_antenna(aid)
                return jsonify({"status": "ok", "antenna_id": aid})
            return jsonify({"antenna_id": mgr.get_active_antenna()})

        @app.route("/api/frequencies", methods=["GET"])
        def get_freqs():
            aid = _req_aid()
            return jsonify({"antenna_id": aid, "frequencies": mgr.get_all(aid)})

        @app.route("/api/frequencies", methods=["POST"])
        def add_freq():
            data = request.get_json(force=True)
            aid = _normalize_antenna_id(data.get("antenna_id"))
            center = data.get("center")
            bw = data.get("bandwidth", 500e3)
            label = data.get("label", "")
            if center is None:
                return jsonify({"status": "error", "error": "Missing center"}), 400
            mgr.add(float(center), float(bw), label, aid)
            return jsonify({"status": "ok", "antenna_id": aid})

        @app.route("/api/frequencies/<int:idx>", methods=["DELETE"])
        def del_freq(idx):
            aid = _req_aid()
            mgr.remove(idx, aid)
            return jsonify({"status": "ok", "antenna_id": aid})

        @app.route("/api/frequencies/<int:idx>", methods=["PUT"])
        def update_freq(idx):
            data = request.get_json(force=True)
            aid = _normalize_antenna_id(data.get("antenna_id"))
            mgr.update(
                idx,
                center_hz=data.get("center"),
                bandwidth_hz=data.get("bandwidth"),
                label=data.get("label"),
                antenna_id=aid,
            )
            return jsonify({"status": "ok", "antenna_id": aid})

        def _run():
            import logging
            logging.getLogger("werkzeug").setLevel(logging.ERROR)
            app.run(host="0.0.0.0", port=self._port, debug=False, use_reloader=False)

        t = threading.Thread(target=_run, daemon=True, name="ConfigWebServer")
        t.start()
        print(f"[CONFIG] Web UI running at http://localhost:{self._port}")
        print(f"[CONFIG] Active antenna: {self.get_active_antenna()}")


if __name__ == "__main__":
    mgr = AuthorizedFrequencyManager(port=5580)
    print("Authorized frequencies:", mgr.get_all())
    print("Manager running. Open http://localhost:5580 in your browser.")
    import time
    while True:
        time.sleep(1)
