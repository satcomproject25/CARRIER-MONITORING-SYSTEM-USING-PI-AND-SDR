from flask import Flask, request, jsonify, send_from_directory
from config_manager import AuthorizedFrequencyManager
import os

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
config_mgr = AuthorizedFrequencyManager()

# -----------------------------
# ROUTES (DEFINE FIRST)
# -----------------------------

@app.route("/")
def index():
    return send_from_directory(os.path.join(BASE_DIR, '..', 'frontend'), "index.html")

@app.route("/api/config", methods=["GET"])
def get_config():
    centers = config_mgr.get_centers()
    return jsonify({
        "centers_mhz": [f / 1e6 for f in centers],
        "tolerance_mhz": 0.3
    })

@app.route("/api/add", methods=["POST"])
def add_frequency():
    data = request.json
    config_mgr.add_frequency(data["freq_mhz"])
    return jsonify({"status": "ok"})

@app.route("/api/delete", methods=["POST"])
def delete_frequency():
    data = request.json
    config_mgr.remove_frequency(data["freq_mhz"])
    return jsonify({"status": "ok"})

# -----------------------------
# START SERVER (LAST)
# -----------------------------

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)