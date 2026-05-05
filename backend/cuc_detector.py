import zmq
import numpy as np
import matplotlib.pyplot as plt
import sys
import threading
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QApplication)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
from scipy.signal import get_window, find_peaks
from matplotlib.widgets import CheckButtons, Button, TextBox
from datetime import datetime
import matplotlib
from matplotlib.widgets import Slider
import time
from collections import deque
from config_manager import AuthorizedFrequencyManager

config_mgr = AuthorizedFrequencyManager()

matplotlib.use("QtAgg")   # or "Qt5Agg"

# =========================
# CONFIG
# =========================
FFT_SIZE = 2048

HW_SAMPLE_RATE = 20e6
DISPLAY_BW = 20e6

HW_CENTER_FREQ = 70e6
DISPLAY_CENTER_FREQ = 70e6
CENTER_FREQ = 70e6

ZMQ_ADDR = "tcp://127.0.0.1:5555"
ZMQ_META_ADDR = "tcp://127.0.0.1:5556"

SMOOTH_BW_HZ = 5 * (20e6 / 2048)
MIN_CARRIER_BW_HZ = 5 * (20e6 / 2048)
THRESHOLD_RATIO = 0.35

Y_MIN = -70
Y_MAX = 80

# =====================================================
# ADAPTIVE DETECTION CONFIG — IMPROVEMENT 1
# All parameters are tunable; no hardcoded constants below this block.
# =====================================================
NF_PERCENTILE            = 15.0   # rolling noise floor percentile (lower = conservative)
NF_ROLLING_WINDOW_DIV    = 8      # noise window = FFT_SIZE // this value
CARRIER_K_SIGMA          = 3.5    # adaptive carrier threshold: noise + k·σ
MORPH_OPEN_BINS          = 3      # morphological open kernel size (spike removal)
MORPH_CLOSE_BINS         = 5      # morphological close kernel size (gap filling)
ADAPTIVE_MERGE_BW_FACTOR = 0.5    # merge gap < this × min(bw1, bw2)

# =====================================================
# INTERFERENCE DETECTION CONFIG (intra-carrier)
# =====================================================
INTF_ENABLED           = True
INTF_BUMP_THRESHOLD_DB = 2
INTF_MIN_BUMP_BINS     = 1.5
INTF_ENVELOPE_ORDER    = 15
INTF_VARIANCE_WINDOW   = 7
INTF_VARIANCE_SIGMA    = 2.5
INTF_CUC_CURV_SIGMA    = 3.5
INTF_MERGE_GAP_HZ      = 200e3

# =====================================================
# CARRIER-UNDER-CARRIER (CuC) DETECTION CONFIG
# =====================================================
CUC_ENABLED              = True
CUC_TEMPLATE_MEDIAN_BINS = 31      # median smoother width to build primary-carrier template
CUC_SAVGOL_WINDOW        = 11      # Savitzky-Golay window for residual smoothing (odd)
CUC_SAVGOL_POLY          = 3       # Savitzky-Golay polynomial order
CUC_BUMP_THRESHOLD_DB    = 2.5     # min residual excess above local noise to flag a bump
CUC_BUMP_MIN_BINS        = 4       # min width (bins) of a bump to be considered
CUC_HOS_WINDOW           = 32      # sliding window (bins) for local kurtosis estimate
CUC_HOS_THRESHOLD        = 1.5     # excess kurtosis threshold (Gaussian noise = 0)
CUC_CURV_SIGMA           = 3.5     # curvature anomaly threshold (multiples of local MAD)
CUC_CONFIDENCE_THRESHOLD = 0.40    # joint confidence [0-1] required to report a CuC event
CUC_PERSIST_FRAMES       = 3       # debounce: frames a CuC must persist before logging

# Intra-carrier gap detector parameters
GAP_DEPTH_DB           = 2.5
GAP_MIN_BINS           = 32
GAP_ENABLED            = True

# =====================================================
# VALLEY / CARRIER SPLIT DETECTION CONFIG
# =====================================================
VALLEY_DEPTH_DB        = 3.0
VALLEY_MIN_WIDTH_HZ    = 10e3
VALLEY_ENABLED         = True

# =====================================================
# UNAUTHORIZED CARRIER DETECTION CONFIG
# =====================================================
UNAUTH_ENABLED         = True
UNAUTH_PERSIST_FRAMES  = 2
UNAUTH_BUCKET_HZ       = 50e3

_unauth_persistence: dict = {}

CARRIER_BUCKET_HZ     = 50e3
CARRIER_PERSIST_FRAMES = 5
_carrier_persistence: dict = {}

# =====================================================
# DETECTION STABILITY CONFIG (temporal filtering + debounce + hysteresis)
# =====================================================
STABILITY_BUCKET_HZ       = 50e3    # frequency bucket for tracking detections
STABILITY_DEBOUNCE_ON     = 3       # frames a detection must persist before logging
STABILITY_DEBOUNCE_OFF    = 5       # frames a detection must be absent before removing
STABILITY_CONFIDENCE_MIN  = 0.6     # minimum confidence score to allow logging
STABILITY_STRENGTH_HISTORY = 8      # rolling window for strength stability calc
STABILITY_HYSTERESIS_DB   = 1.5     # strength hysteresis: ON threshold is this above OFF

# Fast attack / slow decay smoothing config
FAST_AD_ENABLED           = False
FAST_AD_ATTACK_ALPHA      = 0.7     # fast: new data dominates when signal rises
FAST_AD_DECAY_ALPHA       = 0.15    # slow: old data persists when signal falls
_fast_ad_buffer           = None    # per-bin smoothed PSD for fast attack/slow decay

df = HW_SAMPLE_RATE / FFT_SIZE

# =========================
# ZMQ SETUP
# =========================
ctx = zmq.Context()

sock = ctx.socket(zmq.SUB)
sock.connect(ZMQ_ADDR)
sock.setsockopt(zmq.SUBSCRIBE, b"")
sock.setsockopt(zmq.CONFLATE, 1)
sock.setsockopt(zmq.RCVHWM, 1)
sock.setsockopt(zmq.LINGER, 0)

carrier_sock = ctx.socket(zmq.SUB)
carrier_sock.connect("tcp://127.0.0.1:5557")
carrier_sock.setsockopt(zmq.SUBSCRIBE, b"")
carrier_sock.setsockopt(zmq.CONFLATE, 1)
carrier_sock.setsockopt(zmq.RCVHWM, 1)

meta_sock = ctx.socket(zmq.SUB)
meta_sock.connect(ZMQ_META_ADDR)
meta_sock.setsockopt(zmq.SUBSCRIBE, b"")
meta_sock.setsockopt(zmq.CONFLATE, 1)
meta_sock.setsockopt(zmq.RCVHWM, 1)

# =========================
# SHARED STATE
# =========================
_state_lock = threading.Lock()
_latest_iq        = None
_latest_meta      = None
_latest_carriers  = None


class DataFetcher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._poller = zmq.Poller()
        self._poller.register(sock,         zmq.POLLIN)
        self._poller.register(meta_sock,    zmq.POLLIN)
        self._poller.register(carrier_sock, zmq.POLLIN)

    def stop(self):
        self._stop_event.set()

    def run(self):
        global _latest_iq, _latest_meta, _latest_carriers
        while not self._stop_event.is_set():
            events = dict(self._poller.poll(timeout=10))
            if not events: continue
            if sock in events:
                data = sock.recv()
                iq = np.frombuffer(data, dtype=np.complex64)
                with _state_lock: _latest_iq = iq.copy()
            if meta_sock in events:
                with _state_lock: _latest_meta = meta_sock.recv_json()
            if carrier_sock in events:
                with _state_lock: _latest_carriers = carrier_sock.recv_json()


# =========================
# PLOT SETUP
# =========================
fig, ax = plt.subplots(figsize=(12, 6))
manager = plt.get_current_fig_manager()
manager.window.showMaximized()
plt.subplots_adjust(right=0.88, bottom=0.25)

def update_axis():
    global freq_axis, df
    df = HW_SAMPLE_RATE / FFT_SIZE
    freq_axis = np.arange(-FFT_SIZE // 2, FFT_SIZE // 2) * df + HW_CENTER_FREQ
    ax.set_xlim(
        (DISPLAY_CENTER_FREQ - DISPLAY_BW / 2) / 1e6,
        (DISPLAY_CENTER_FREQ + DISPLAY_BW / 2) / 1e6
    )

update_axis()

line_live, = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), lw=1)
line_max,  = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), color="green", lw=1)
line_min,  = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), color="red",   lw=0.5)

ax.set_ylim(Y_MIN, Y_MAX)
ax.set_xlabel("Frequency (MHz)")
ax.set_ylabel("Power (dB)")
ax.set_title("Real-Time FFT Spectrum + Unauthorized Carrier Detection")

window     = get_window("hann", FFT_SIZE)
iq_buffer  = np.zeros(FFT_SIZE, dtype=np.complex64)

monitor_ax = plt.axes([0.02, 0.75, 0.3, 0.4])
monitor_ax.axis("off")
monitor_text = monitor_ax.text(0.0, 1.0, "", verticalalignment='top',
                               fontsize=10, family='monospace')


# =====================================================
# LOG VIEWER WINDOW
# =====================================================
MAX_LOG_LINES    = 5000
LOG_THROTTLE_SEC = 0.5

class LogWindow(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Carrier & Interference Detection Log")
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(700, 420)
        layout = QVBoxLayout(self)
        hdr = QHBoxLayout()
        title = QLabel("CARRIER & INTERFERENCE DETECTION LOG")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        hdr.addWidget(title); hdr.addStretch()
        self.line_count_label = QLabel("Lines: 0")
        self.line_count_label.setFont(QFont("Consolas", 9))
        hdr.addWidget(self.line_count_label)
        self.autoscroll_on = True
        self.btn_autoscroll = QPushButton("Auto-scroll: ON")
        self.btn_autoscroll.setFixedWidth(120)
        self.btn_autoscroll.clicked.connect(self._toggle_autoscroll)
        hdr.addWidget(self.btn_autoscroll)
        btn_clear = QPushButton("Clear"); btn_clear.setFixedWidth(60)
        btn_clear.clicked.connect(self.clear_log); hdr.addWidget(btn_clear)
        layout.addLayout(hdr)
        self.text = QTextEdit(); self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        self.text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; }")
        layout.addWidget(self.text)
        self._line_count = 0; self._last_log_time = 0.0

    def append(self, msg, color="#d4d4d4"):
        self.text.setTextColor(QColor(color)); self.text.append(msg)
        self._line_count += msg.count('\n') + 1
        self.line_count_label.setText(f"Lines: {self._line_count}")
        if self._line_count > MAX_LOG_LINES: self._trim()
        if self.autoscroll_on:
            sb = self.text.verticalScrollBar(); sb.setValue(sb.maximum())

    def clear_log(self):
        self.text.clear(); self._line_count = 0
        self.line_count_label.setText("Lines: 0")

    def _toggle_autoscroll(self):
        self.autoscroll_on = not self.autoscroll_on
        self.btn_autoscroll.setText(
            "Auto-scroll: ON" if self.autoscroll_on else "Auto-scroll: OFF")

    def _trim(self):
        doc = self.text.document(); cursor = self.text.textCursor()
        cursor.movePosition(cursor.Start)
        for _ in range(doc.blockCount() // 2):
            cursor.movePosition(cursor.Down, cursor.KeepAnchor)
        cursor.removeSelectedText(); cursor.deleteChar()
        self._line_count = doc.blockCount()
        self.line_count_label.setText(f"Lines: {self._line_count}")

    def closeEvent(self, event): self.hide(); event.ignore()


log_win = LogWindow()
log_win.append(
    f"[{datetime.now().strftime('%H:%M:%S')}] Log started  |  "
    f"HW SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  FFT: {FFT_SIZE}  |  "
    f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz  |  "
    f"Auth freqs: {len(config_mgr.get_all())}  |  "
    f"Web UI: http://localhost:5580",
    "#569cd6")


# =====================================================
# CONTROL PANEL
# =====================================================
max_hold = np.full(FFT_SIZE, -np.inf)
min_hold = np.full(FFT_SIZE,  np.inf)
enable_max_hold = False
enable_min_hold = False

rax   = plt.axes([0.90, 0.73, 0.09, 0.08])
check = CheckButtons(rax, ["MAX HOLD", "MIN HOLD"], [False, False])
def toggle_hold(label):
    global enable_max_hold, enable_min_hold
    if label == "MAX HOLD": enable_max_hold = not enable_max_hold
    if label == "MIN HOLD": enable_min_hold = not enable_min_hold
check.on_clicked(toggle_hold)

reset_ax  = plt.axes([0.90, 0.67, 0.1, 0.04])
reset_btn = Button(reset_ax, "Reset Hold")
def reset_hold(event):
    global max_hold, min_hold
    max_hold[:] = -np.inf; min_hold[:] = np.inf
reset_btn.on_clicked(reset_hold)

smooth_enabled = False; smooth_alpha = 0.0; psd_avg = None
smooth_ax  = plt.axes([0.90, 0.62, 0.1, 0.04])
smooth_btn = Button(smooth_ax, "Smooth OFF")
def toggle_smooth(event):
    global smooth_enabled; smooth_enabled = not smooth_enabled
    smooth_btn.label.set_text("Smooth ON" if smooth_enabled else "Smooth OFF")
smooth_btn.on_clicked(toggle_smooth)

slider_ax     = plt.axes([0.15, 0.02, 0.5, 0.03])
smooth_slider = Slider(slider_ax, "Smooth", 0.0, 1.0, valinit=0.0)
def update_smooth(val):
    global smooth_alpha; smooth_alpha = val
smooth_slider.on_changed(update_smooth)

ax_freq = plt.axes([0.1,  0.1, 0.2,  0.05])
tb_freq = TextBox(ax_freq, "Center Freq (Hz)", initial=str(CENTER_FREQ))
ax_sr   = plt.axes([0.45, 0.1, 0.15, 0.05])
tb_sr   = TextBox(ax_sr, "Sample rate (Hz)", initial=str(DISPLAY_BW))
ax_fft  = plt.axes([0.7,  0.1, 0.1,  0.05])
tb_fft  = TextBox(ax_fft, "FFT", initial=str(FFT_SIZE))

def update_freq(text):
    global DISPLAY_CENTER_FREQ; DISPLAY_CENTER_FREQ = float(text); update_axis()
def update_display_bw(text):
    global DISPLAY_BW; DISPLAY_BW = float(text)
    ax.set_xlim((DISPLAY_CENTER_FREQ - DISPLAY_BW/2)/1e6,
                (DISPLAY_CENTER_FREQ + DISPLAY_BW/2)/1e6)
def update_fft(text):
    global FFT_SIZE, max_hold, min_hold, window, iq_buffer
    FFT_SIZE = int(text); update_axis()
    window = get_window("hann", FFT_SIZE)
    iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
    max_hold = np.full(FFT_SIZE, -np.inf); min_hold = np.full(FFT_SIZE, np.inf)
    for ln in [line_live, line_max, line_min]:
        ln.set_xdata(freq_axis / 1e6)
tb_freq.on_submit(update_freq)
tb_sr.on_submit(update_display_bw)
tb_fft.on_submit(update_fft)


# =====================================================
# MARKER SYSTEM
# =====================================================
MARKER_COLORS = {1: "#ff4c4c", 2: "#4ec9b0", 3: "#c586c0"}
class Marker:
    def __init__(self, idx):
        self.idx = idx; self.mode = "off"
        self.point_a = None; self.point_b = None
        self.artist_a = None; self.artist_b = None; self.text = None
markers = {1: Marker(1), 2: Marker(2), 3: Marker(3)}
markers_global_on = True; selected_marker_id = None
cursor_ghost = None; CLICK_REMOVE_THRESH_MHZ = 0.3

marker_onoff_ax  = plt.axes([0.90, 0.57, 0.1, 0.04])
marker_onoff_btn = Button(marker_onoff_ax, "Markers: ON")
m1_btn_ax = plt.axes([0.90, 0.525, 0.1, 0.035]); m1_btn = Button(m1_btn_ax, "M1: OFF")
m2_btn_ax = plt.axes([0.90, 0.485, 0.1, 0.035]); m2_btn = Button(m2_btn_ax, "M2: OFF")
m3_btn_ax = plt.axes([0.90, 0.445, 0.1, 0.035]); m3_btn = Button(m3_btn_ax, "M3: OFF")

def _freq_snap(x_mhz):
    idx = np.argmin(np.abs(freq_axis - x_mhz * 1e6))
    return freq_axis[idx], line_live.get_ydata()[idx]

def _is_near_existing(m, x_mhz, thresh=CLICK_REMOVE_THRESH_MHZ):
    if m.point_a and abs(m.point_a[0]/1e6 - x_mhz) < thresh: return 'a'
    if m.point_b and abs(m.point_b[0]/1e6 - x_mhz) < thresh: return 'b'
    return None

def on_click(event):
    global selected_marker_id
    if not markers_global_on or event.inaxes != ax or event.button != 1: return
    if selected_marker_id is None: return
    m = markers[selected_marker_id]
    if m.mode in ("off", "peak"): return
    x_mhz = event.xdata; fx, py = _freq_snap(x_mhz)
    if m.mode == "normal":
        m.point_a = None if _is_near_existing(m, x_mhz) == 'a' else (fx, py)
    elif m.mode == "delta":
        near = _is_near_existing(m, x_mhz)
        if near == 'a': m.point_a = None
        elif near == 'b': m.point_b = None
        elif m.point_a is None: m.point_a = (fx, py)
        elif m.point_b is None: m.point_b = (fx, py)
        else: m.point_a = (fx, py); m.point_b = None
fig.canvas.mpl_connect("button_press_event", on_click)

def on_mouse_move(event):
    global cursor_ghost
    if cursor_ghost:
        try: cursor_ghost.remove()
        except: pass
        cursor_ghost = None
    if not markers_global_on or event.inaxes != ax: return
    if not any(m.mode in ("normal","delta") for m in markers.values()): return
    fx, py = _freq_snap(event.xdata)
    cursor_ghost = ax.scatter(fx/1e6, py, marker="+", s=120, color="white", linewidths=1.5, zorder=25)
fig.canvas.mpl_connect("motion_notify_event", on_mouse_move)

_marker_mode_cycle  = ["off", "normal", "peak", "delta"]
_marker_btn_map     = {1: m1_btn, 2: m2_btn, 3: m3_btn}
_marker_mode_labels = {"off": "OFF", "normal": "Normal", "peak": "Peak", "delta": "Delta"}
def _make_toggle_marker(idx):
    def toggle(event):
        global selected_marker_id
        if not markers_global_on: return
        m = markers[idx]; cur = _marker_mode_cycle.index(m.mode)
        m.mode = _marker_mode_cycle[(cur+1) % len(_marker_mode_cycle)]
        if m.mode in ("off","peak"):
            m.point_a = m.point_b = None
            if selected_marker_id == idx: selected_marker_id = None
        else: selected_marker_id = idx
        _marker_btn_map[idx].label.set_text(f"M{idx}: {_marker_mode_labels[m.mode]}")
        fig.canvas.draw_idle()
    return toggle
m1_btn.on_clicked(_make_toggle_marker(1))
m2_btn.on_clicked(_make_toggle_marker(2))
m3_btn.on_clicked(_make_toggle_marker(3))

def toggle_markers_global(event):
    global markers_global_on, cursor_ghost, selected_marker_id
    markers_global_on = not markers_global_on
    marker_onoff_btn.label.set_text("Markers: ON" if markers_global_on else "Markers: OFF")
    if not markers_global_on:
        selected_marker_id = None
        for m in markers.values(): m.point_a = m.point_b = None
        if cursor_ghost:
            try: cursor_ghost.remove()
            except: pass
            cursor_ghost = None
    fig.canvas.draw_idle()
marker_onoff_btn.on_clicked(toggle_markers_global)


# =====================================================
# TOGGLE BUTTONS — View Log / Intf / Gap / Unauth / Valley
# =====================================================
log_btn_ax = plt.axes([0.90, 0.405, 0.1, 0.035]); log_btn = Button(log_btn_ax, "View Log")
def toggle_log(event):
    if log_win.isVisible(): log_win.hide()
    else: log_win.show(); log_win.raise_(); log_win.activateWindow()
log_btn.on_clicked(toggle_log)

intf_btn_ax = plt.axes([0.90, 0.365, 0.1, 0.035])
intf_btn = Button(intf_btn_ax, "Intf: ON")
def toggle_interference(event):
    global INTF_ENABLED; INTF_ENABLED = not INTF_ENABLED
    intf_btn.label.set_text("Intf: ON" if INTF_ENABLED else "Intf: OFF")
    fig.canvas.draw_idle()
intf_btn.on_clicked(toggle_interference)

gap_btn_ax = plt.axes([0.90, 0.325, 0.1, 0.035])
gap_btn = Button(gap_btn_ax, "Gap: ON")
def toggle_gap_detector(event):
    global GAP_ENABLED; GAP_ENABLED = not GAP_ENABLED
    gap_btn.label.set_text("Gap: ON" if GAP_ENABLED else "Gap: OFF")
    fig.canvas.draw_idle()
gap_btn.on_clicked(toggle_gap_detector)

unauth_btn_ax = plt.axes([0.90, 0.285, 0.1, 0.035])
unauth_btn = Button(unauth_btn_ax, "Unauth: ON")
def toggle_unauth(event):
    global UNAUTH_ENABLED; UNAUTH_ENABLED = not UNAUTH_ENABLED
    unauth_btn.label.set_text("Unauth: ON" if UNAUTH_ENABLED else "Unauth: OFF")
    fig.canvas.draw_idle()
unauth_btn.on_clicked(toggle_unauth)

valley_btn_ax = plt.axes([0.90, 0.245, 0.1, 0.035])
valley_btn = Button(valley_btn_ax, "Valley: ON")
def toggle_valley(event):
    global VALLEY_ENABLED; VALLEY_ENABLED = not VALLEY_ENABLED
    valley_btn.label.set_text("Valley: ON" if VALLEY_ENABLED else "Valley: OFF")
    fig.canvas.draw_idle()
valley_btn.on_clicked(toggle_valley)

fast_ad_btn_ax = plt.axes([0.90, 0.205, 0.1, 0.035])
fast_ad_btn = Button(fast_ad_btn_ax, "Fast A/D: OFF")
def toggle_fast_ad(event):
    global FAST_AD_ENABLED, _fast_ad_buffer
    FAST_AD_ENABLED = not FAST_AD_ENABLED
    if not FAST_AD_ENABLED:
        _fast_ad_buffer = None   # reset buffer when turning off
    fast_ad_btn.label.set_text("Fast A/D: ON" if FAST_AD_ENABLED else "Fast A/D: OFF")
    fig.canvas.draw_idle()
fast_ad_btn.on_clicked(toggle_fast_ad)


plt.show(block=False)
print("[INFO] GUI running...")
print(f"[INFO] Authorized Frequency Manager web UI: http://localhost:5580")
print(f"[INFO] Authorized frequencies loaded: {len(config_mgr.get_all())}")


# ═════════════════════════════════════════════════════════════════════════════
# UNAUTHORIZED CARRIER PERSISTENCE FILTER
# ═════════════════════════════════════════════════════════════════════════════

def apply_unauth_persistence(all_hits):
    global _unauth_persistence
    confirmed       = []
    hits_this_frame = set()
    for hit in all_hits:
        bucket = int(round(hit['f_center'] / UNAUTH_BUCKET_HZ))
        hits_this_frame.add(bucket)
        _unauth_persistence[bucket] = _unauth_persistence.get(bucket, 0) + 1
        if _unauth_persistence[bucket] >= UNAUTH_PERSIST_FRAMES:
            confirmed.append(hit)
    for key in list(_unauth_persistence):
        if key not in hits_this_frame:
            del _unauth_persistence[key]
    return confirmed


# ═════════════════════════════════════════════════════════════════════════════
# DETECTION TRACKER — Temporal stability, debounce, hysteresis, confidence
# ═════════════════════════════════════════════════════════════════════════════

class DetectionTracker:
    """
    Tracks detections (interference, gaps, valleys) across frames using
    frequency-bucket matching.  Provides:
      • Debounce:   detection must persist N consecutive frames before logging
      • Hysteresis: separate ON/OFF thresholds to avoid flicker
      • Confidence: rolling score based on persistence + strength stability
      • Tracking ID: stable ID per detection across frames
    """

    def __init__(self,
                 bucket_hz=STABILITY_BUCKET_HZ,
                 debounce_on=STABILITY_DEBOUNCE_ON,
                 debounce_off=STABILITY_DEBOUNCE_OFF,
                 confidence_min=STABILITY_CONFIDENCE_MIN,
                 strength_history_len=STABILITY_STRENGTH_HISTORY,
                 hysteresis_db=STABILITY_HYSTERESIS_DB):
        self.bucket_hz = bucket_hz
        self.debounce_on = debounce_on
        self.debounce_off = debounce_off
        self.confidence_min = confidence_min
        self.strength_history_len = strength_history_len
        self.hysteresis_db = hysteresis_db
        self._tracks = {}      # bucket_key → track dict
        self._next_id = 1
        self._frame = 0

    def _bucket_key(self, freq_hz):
        return int(round(freq_hz / self.bucket_hz))

    def _new_track(self, freq_hz, strength_db):
        tid = self._next_id
        self._next_id += 1
        return {
            'id':           tid,
            'center_freq':  freq_hz,
            'strength_db':  strength_db,
            'first_seen':   self._frame,
            'last_seen':    self._frame,
            'consecutive':  1,
            'absent_count': 0,
            'confirmed':    False,
            'logged_once':  False,     # True after first log emission
            'strength_hist': deque(maxlen=self.strength_history_len),
        }

    def _compute_confidence(self, track):
        """
        Confidence = weighted combination of:
          • persistence ratio (consecutive / debounce_on)  — capped at 1.0
          • strength stability (1 - cv of recent strengths) — higher = more stable
        """
        pers = min(1.0, track['consecutive'] / max(1, self.debounce_on))
        hist = track['strength_hist']
        if len(hist) >= 2:
            arr = np.array(hist)
            mu = np.mean(arr)
            cv = np.std(arr) / max(abs(mu), 0.01)
            stab = max(0.0, 1.0 - cv)
        else:
            stab = 0.5
        return 0.65 * pers + 0.35 * stab

    def update(self, detections):
        """
        Process one frame of detections.

        Parameters
        ----------
        detections : list of dict
            Each dict MUST have 'center_freq' (Hz) and 'strength_db'.
            May contain any additional fields — they are passed through.

        Returns
        -------
        list of dict
            Only confirmed detections (passed debounce + confidence).
            Each dict has the original fields PLUS:
              'track_id', 'confidence', 'is_new' (True on first confirmation)
        """
        self._frame += 1
        seen_buckets = set()
        confirmed = []

        for det in detections:
            bk = self._bucket_key(det['center_freq'])
            seen_buckets.add(bk)

            if bk in self._tracks:
                trk = self._tracks[bk]
                trk['last_seen'] = self._frame
                trk['consecutive'] += 1
                trk['absent_count'] = 0
                trk['center_freq'] = det['center_freq']
                trk['strength_db'] = det['strength_db']
                trk['strength_hist'].append(det['strength_db'])
            else:
                trk = self._new_track(det['center_freq'], det['strength_db'])
                trk['strength_hist'].append(det['strength_db'])
                self._tracks[bk] = trk

            # Check debounce + confidence
            conf = self._compute_confidence(trk)
            if trk['consecutive'] >= self.debounce_on and conf >= self.confidence_min:
                is_new = not trk['confirmed']
                trk['confirmed'] = True
                out = dict(det)
                out['track_id'] = trk['id']
                out['confidence'] = conf
                out['is_new'] = is_new
                confirmed.append(out)

        # Age out absent tracks (hysteresis — keep for debounce_off frames)
        for bk in list(self._tracks):
            if bk not in seen_buckets:
                trk = self._tracks[bk]
                trk['consecutive'] = 0
                trk['absent_count'] += 1
                if trk['absent_count'] >= self.debounce_off:
                    del self._tracks[bk]
                elif trk['confirmed']:
                    trk['confirmed'] = False

        return confirmed

    def reset(self):
        """Clear all tracking state (e.g. on meta update)."""
        self._tracks.clear()
        self._frame = 0


# Global tracker instances — one per detection category
_intf_tracker    = DetectionTracker()
_gap_tracker     = DetectionTracker()
_valley_tracker  = DetectionTracker(debounce_on=4)   # valleys need more stability
_carrier_tracker = DetectionTracker(debounce_on=2, debounce_off=8)
_cuc_tracker     = DetectionTracker(debounce_on=CUC_PERSIST_FRAMES, debounce_off=6)


# ═════════════════════════════════════════════════════════════════════════════
# EDGE-BASED CARRIER BOUNDARY DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def find_edges_for_carrier(f, y, fc_mhz, gnt, centers):
    idx = np.argmin(np.abs(centers - fc_mhz))
    ci = np.searchsorted(f, fc_mhz * 1e6)
    ci = min(ci, len(y) - 1)

    l_bound = centers[idx - 1] if idx > 0 else f[0] / 1e6
    r_bound = centers[idx + 1] if idx < len(centers) - 1 else f[-1] / 1e6
    l_limit = np.searchsorted(f, l_bound * 1e6)
    r_limit = np.searchsorted(f, r_bound * 1e6)

    thr = y[ci] - 6.0
    noise_stop = gnt + 1.5
    ba_l = sh_l = ba_r = sh_r = ci

    # LEFT SIDE
    if ci > l_limit:
        local_min_l = np.min(y[l_limit:ci])
        peak_drop_l = y[ci] - local_min_l
        floor_gap_l = local_min_l - gnt
        use_gnt_l = floor_gap_l <= 0.4 * peak_drop_l
        i = ci - 1; found_sh = False
        while i > l_limit:
            if y[i] <= noise_stop: ba_l = i; break
            if not found_sh and y[i] < thr: sh_l = i; found_sh = True
            if found_sh:
                if i >= 3 and y[i - 3] >= y[i]:
                    if use_gnt_l:
                        if y[i] <= gnt + 1.5: ba_l = i; break
                    else: ba_l = i; break
            i -= 1
        else:
            ba_l = sh_l if found_sh else ci

    # RIGHT SIDE
    if ci < r_limit:
        local_min_r = np.min(y[ci:r_limit])
        peak_drop_r = y[ci] - local_min_r
        floor_gap_r = local_min_r - gnt
        use_gnt_r = floor_gap_r <= 0.4 * peak_drop_r
        i = ci + 1; found_sh = False
        while i < r_limit:
            if y[i] <= noise_stop: ba_r = i; break
            if not found_sh and y[i] < thr: sh_r = i; found_sh = True
            if found_sh:
                if i + 3 < len(y) and y[i + 3] >= y[i]:
                    if use_gnt_r:
                        if y[i] <= gnt + 1.5: ba_r = i; break
                    else: ba_r = i; break
            i += 1
        else:
            ba_r = sh_r if found_sh else ci

    return ba_l, sh_l, ci, sh_r, ba_r


# ═════════════════════════════════════════════════════════════════════════════
# VALLEY / CARRIER SPLIT DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def detect_carrier_valleys(psd_segment, freq_segment, noise_floor):
    """
    Detect V/U shaped valleys between sub-carriers within a single carrier span.

    IMPROVEMENT 7: Adaptive prominence threshold.
    Prominence now scales with the carrier's local dynamic range so shallow
    valleys in low-SNR carriers are still detected while high-SNR carriers
    don't produce spurious splits from ripple.

    Cases handled:
      Case 1 — V-shape valley (narrow), above noise floor  → DETECT
      Case 2 — U-shape valley (wide, flat bottom), above NF → DETECT
      Case 3 — Shallow V-shape (≥ VALLEY_DEPTH_DB), above NF → DETECT
      Case 4 — Valley touches noise floor → SKIP (already 2 separate carriers)
      Case 5 — L-shape (one-sided drop) → SKIP (require both sides rise)

    Returns list of valley dicts with indices RELATIVE to segment start.
    """
    n = len(psd_segment)
    if n < 10:
        return []

    # ── IMPROVEMENT 7: Adaptive peak-detection prominence ─────────────────────
    # Scale prominence with the carrier's own dynamic range capped at 6 dB so
    # we don't miss shallow valleys in narrowband carriers.
    _seg_peak  = float(np.max(psd_segment))
    _seg_floor = float(np.percentile(psd_segment, NF_PERCENTILE))
    _dyn_range = max(1.0, _seg_peak - _seg_floor)
    _valley_prominence = max(1.0, min(1.5, _dyn_range * 0.12))

    # Find peaks — use moderate distance and adaptive prominence
    min_peak_dist = max(3, n // 10)
    peaks, _ = find_peaks(psd_segment, distance=min_peak_dist,
                          prominence=_valley_prominence)

    if len(peaks) < 2:
        return []

    valleys = []
    for i in range(len(peaks) - 1):
        p1, p2 = peaks[i], peaks[i + 1]

        # Find valley floor between these two peaks
        region = psd_segment[p1:p2 + 1]
        vi_local = np.argmin(region)
        vi = p1 + vi_local
        valley_power = float(psd_segment[vi])

        # ── Case 4: valley touches noise floor → skip ──
        if valley_power <= noise_floor + 1.5:
            continue

        # ── Case 5: L-shape rejection ──
        # Both sides must rise at least VALLEY_DEPTH_DB above valley
        left_depth  = float(psd_segment[p1]) - valley_power
        right_depth = float(psd_segment[p2]) - valley_power
        if left_depth < VALLEY_DEPTH_DB or right_depth < VALLEY_DEPTH_DB:
            continue

        smaller_peak_pwr = min(float(psd_segment[p1]), float(psd_segment[p2]))
        depth = smaller_peak_pwr - valley_power

        # ── Brown boundary threshold ──
        depth = smaller_peak_pwr - valley_power

        brown_threshold = valley_power + depth * 0.45

        # Find left boundary: scan from left peak rightward → first bin below threshold
        brown_left = vi  # default to valley center
        for j in range(vi, p1, -1):
            if psd_segment[j] >= brown_threshold:
                brown_left = j
                break

        # Find right boundary: scan from right peak leftward → first bin below threshold
        brown_right = vi  # default to valley center
        for j in range(vi, p2):
            if psd_segment[j] >= brown_threshold:
                brown_right = j
                break
        # limit boundary drift into carrier slopes
        max_left_span  = int((vi - p1) * 0.7)
        max_right_span = int((p2 - vi) * 0.7)

        brown_left  = max(brown_left,  vi - max_left_span)
        brown_right = min(brown_right, vi + max_right_span)
        # Ensure brown_left < brown_right
        if brown_left >= brown_right:
            brown_left, brown_right = min(brown_left, brown_right), max(brown_left, brown_right)
        if brown_left == brown_right:
            continue
        
        # ── Minimum width check ──
        gap_hz = abs(float(freq_segment[brown_right]) - float(freq_segment[brown_left]))
        if gap_hz < VALLEY_MIN_WIDTH_HZ:
            continue

        valleys.append({
            'left_peak_idx':   p1,
            'right_peak_idx':  p2,
            'valley_idx':      vi,
            'valley_power':    valley_power,
            'depth':           float(depth),
            'brown_left_idx':  brown_left,
            'brown_right_idx': brown_right,
            'gap_hz':          gap_hz,
        })

    return valleys


# =====================================================
# INTERFERENCE DETECTION ALGORITHMS (intra-carrier)
# =====================================================
def detect_interference_in_carrier(psd_segment, freq_segment):
    """
    IMPROVEMENT 6: Intra-carrier interference detection with fully adaptive
    thresholds and enhanced detection for edge, partial-overlap, and
    embedded narrowband interference.

    Changes vs original:
      6a — Bump threshold: adaptive (local σ-based) instead of fixed INTF_BUMP_THRESHOLD_DB
      6b — Variance threshold: adaptive (per-carrier variance statistics)
      6c — Edge interference: explicit left/right 20% sub-band power deviation check
      6d — Power-deviation from expected carrier shape (rolling median envelope)
      6e — Sub-band variance increase detection (partial carrier overlay)
    All other logic (gap detector, merge, structure) is unchanged.
    """
    if len(psd_segment) < 6:
        return []

    results = []
    n = len(psd_segment)

    # ── IMPROVEMENT 6a: Adaptive local statistics for this carrier segment ────
    # Compute carrier's noise floor as the lower-percentile of its own PSD.
    # This makes every threshold relative to local conditions, not global noise.
    _local_floor  = float(np.percentile(psd_segment, NF_PERCENTILE))
    _local_sigma  = float(np.std(psd_segment[psd_segment < (_local_floor + 8.0)]))
    _local_sigma  = max(_local_sigma, 0.5)   # prevent zero-sigma collapse
    # Adaptive bump threshold: max of config value or 1.5 × local σ
    _bump_thr     = max(INTF_BUMP_THRESHOLD_DB, 1.5 * _local_sigma)
    # Adaptive variance multiplier: tighten if carrier is narrow/clean
    _var_sigma    = max(INTF_VARIANCE_SIGMA, 1.5)

    # 1. SPECTRAL-BUMP DETECTOR (adaptive threshold)
    half = min(INTF_ENVELOPE_ORDER, n // 2)
    if half >= 1:
        pad      = np.pad(psd_segment, half, mode='edge')
        envelope = np.array([np.median(pad[i:i + 2*half + 1]) for i in range(n)])
        residual = psd_segment - envelope
        # IMPROVEMENT 6a: use adaptive bump threshold
        bump_mask  = residual > _bump_thr
        bump_edges = np.diff(bump_mask.astype(np.int8))
        b_rises = np.where(bump_edges == 1)[0] + 1
        b_falls = np.where(bump_edges == -1)[0] + 1
        if bump_mask[0]:  b_rises = np.insert(b_rises, 0, 0)
        if bump_mask[-1]: b_falls = np.append(b_falls, n)
        for br, bf in zip(b_rises, b_falls):
            if (bf - br) < INTF_MIN_BUMP_BINS: continue
            seg = psd_segment[br:bf]; pk_local = np.argmax(seg) + br
            results.append({
                'start_freq': float(freq_segment[br]),
                'end_freq':   float(freq_segment[min(bf, n-1)]),
                'peak_freq':  float(freq_segment[pk_local]),
                'strength_db': float(residual[pk_local]),
                'method': 'bump', 'is_gap': False,
            })

    # 2. LOCAL-VARIANCE ANOMALY (adaptive multiplier)
    w = min(INTF_VARIANCE_WINDOW, n // 3)
    if w >= 3:
        local_var = np.array([np.var(psd_segment[max(0,i-w):i+w+1]) for i in range(n)])
        med_var   = np.median(local_var) + 1e-6
        # IMPROVEMENT 6b: adaptive variance sigma
        anom_mask  = local_var > (_var_sigma * med_var)
        anom_edges = np.diff(anom_mask.astype(np.int8))
        a_rises = np.where(anom_edges == 1)[0] + 1
        a_falls = np.where(anom_edges == -1)[0] + 1
        if anom_mask[0]:  a_rises = np.insert(a_rises, 0, 0)
        if anom_mask[-1]: a_falls = np.append(a_falls, n)
        for ar, af in zip(a_rises, a_falls):
            if (af - ar) < INTF_MIN_BUMP_BINS: continue
            seg = psd_segment[ar:af]; pk_local = np.argmax(seg) + ar
            strength = float(psd_segment[pk_local] - np.median(psd_segment))
            if strength < max(2.0, _local_sigma): continue
            results.append({
                'start_freq': float(freq_segment[ar]),
                'end_freq':   float(freq_segment[min(af, n-1)]),
                'peak_freq':  float(freq_segment[pk_local]),
                'strength_db': strength,
                'method': 'variance', 'is_gap': False,
            })

    # 3. CARRIER-UNDER-CARRIER (CURVATURE)
    if n >= 10:
        kern = max(3, min(7, n // 5)) | 1
        sm = np.convolve(psd_segment, np.ones(kern)/kern, mode='same')
        d2 = np.diff(sm, n=2); d2_padded = np.concatenate(([0], d2, [0]))
        med_d2 = np.median(np.abs(d2_padded)) + 1e-6
        curv_mask  = d2_padded > (INTF_CUC_CURV_SIGMA * med_d2)
        curv_edges = np.diff(curv_mask.astype(np.int8))
        c_rises = np.where(curv_edges == 1)[0] + 1
        c_falls = np.where(curv_edges == -1)[0] + 1
        if curv_mask[0]:  c_rises = np.insert(c_rises, 0, 0)
        if curv_mask[-1]: c_falls = np.append(c_falls, n)
        for cr, cf in zip(c_rises, c_falls):
            if (cf - cr) < INTF_MIN_BUMP_BINS: continue
            seg = psd_segment[cr:cf]; pk_local = np.argmax(seg) + cr
            strength = float(psd_segment[pk_local] - np.median(psd_segment))
            if strength < max(2.5, _local_sigma): continue
            results.append({
                'start_freq': float(freq_segment[cr]),
                'end_freq':   float(freq_segment[min(cf, n-1)]),
                'peak_freq':  float(freq_segment[pk_local]),
                'strength_db': strength,
                'method': 'curvature', 'is_gap': False,
            })

    # ── IMPROVEMENT 6c: Edge interference detection ────────────────────────────
    # Check the left and right 20 % of the carrier for elevated power relative
    # to the carrier's own expected (rolling-median) shape.
    # Detects: left-edge intf, right-edge intf, and partial-overlap scenarios.
    if n >= 12 and half >= 1:
        _edge_frac = max(1, n // 5)   # 20 % of carrier width
        for _side, _sl in [('left_edge',  slice(0, _edge_frac)),
                            ('right_edge', slice(n - _edge_frac, n))]:
            _seg_edge = psd_segment[_sl]
            _env_edge = envelope[_sl]       # reuse envelope from bump detector
            _res_edge = _seg_edge - _env_edge
            _edge_pk  = int(np.argmax(_res_edge))
            _edge_str = float(_res_edge[_edge_pk])
            if _edge_str > _bump_thr and len(_seg_edge) >= int(INTF_MIN_BUMP_BINS):
                _freq_sub = freq_segment[_sl]
                results.append({
                    'start_freq':  float(_freq_sub[0]),
                    'end_freq':    float(_freq_sub[-1]),
                    'peak_freq':   float(_freq_sub[_edge_pk]),
                    'strength_db': _edge_str,
                    'method': _side, 'is_gap': False,
                })

    # ── IMPROVEMENT 6d: Sub-band variance increase (partial overlay) ───────────
    # Divide carrier into 4 equal sub-bands; flag any sub-band whose variance
    # exceeds INTF_VARIANCE_SIGMA × the carrier median variance.
    if n >= 16:
        _sb = max(4, n // 4)
        _sub_vars = [float(np.var(psd_segment[i:i + _sb]))
                     for i in range(0, n - _sb + 1, _sb)]
        _med_sv = float(np.median(_sub_vars)) + 1e-6
        for _sbi, _sv in enumerate(_sub_vars):
            if _sv > _var_sigma * _med_sv:
                _si = _sbi * _sb
                _ei = min(_si + _sb, n)
                _pk = int(np.argmax(psd_segment[_si:_ei])) + _si
                _str = float(psd_segment[_pk] - np.median(psd_segment))
                if _str < max(1.5, _local_sigma):
                    continue
                results.append({
                    'start_freq':  float(freq_segment[_si]),
                    'end_freq':    float(freq_segment[min(_ei, n-1)]),
                    'peak_freq':   float(freq_segment[_pk]),
                    'strength_db': _str,
                    'method': 'subband_var', 'is_gap': False,
                })

    # 4. INTRA-CARRIER GAP DETECTOR — RED highlight, flagged as interference
    if GAP_ENABLED and n >= 10:
        min_peak_distance = max(3, n // 10)
        peaks, _ = find_peaks(psd_segment, distance=min_peak_distance, prominence=2.0)
        if len(peaks) >= 2:
            noise_floor = np.median(psd_segment)
            for i in range(len(peaks) - 1):
                p1, p2 = peaks[i], peaks[i+1]
                valley_region = psd_segment[p1:p2+1]
                vi_local = np.argmin(valley_region); vi = p1 + vi_local
                vp = psd_segment[vi]
                smaller_pk = min(psd_segment[p1], psd_segment[p2])
                depth = smaller_pk - vp
                vthr = vp + depth * 0.5
                vmask = psd_segment[p1:p2+1] < vthr
                vedges = np.diff(vmask.astype(np.int8))
                vr = np.where(vedges == 1)[0] + 1
                vf = np.where(vedges == -1)[0] + 1
                if vmask[0]:  vr = np.insert(vr, 0, 0)
                if vmask[-1]: vf = np.append(vf, len(vmask))
                vwidth = 0; vs_local = 0; ve_local = 0
                for vri, vfi in zip(vr, vf):
                    w2 = vfi - vri
                    if w2 > vwidth: vwidth = w2; vs_local = vri; ve_local = vfi
                if depth > GAP_DEPTH_DB and vwidth >= GAP_MIN_BINS and vp > noise_floor:
                    vs_abs = p1 + vs_local; ve_abs = p1 + ve_local
                    results.append({
                        'start_freq': float(freq_segment[vs_abs]),
                        'end_freq':   float(freq_segment[min(ve_abs, n-1)]),
                        'peak_freq':  float(freq_segment[vi]),
                        'strength_db': float(depth),
                        'method': 'gap', 'is_gap': True,
                    })

    # MERGE (keep gap and non-gap separate)
    if not results: return results
    gap_results    = [r for r in results if r.get('is_gap', False)]
    nongap_results = [r for r in results if not r.get('is_gap', False)]

    def _merge(rlist):
        if not rlist: return rlist
        rlist.sort(key=lambda r: r['start_freq'])
        merged = [rlist[0].copy()]
        for r in rlist[1:]:
            prev = merged[-1]
            if r['start_freq'] - prev['end_freq'] <= INTF_MERGE_GAP_HZ:
                prev['end_freq'] = max(prev['end_freq'], r['end_freq'])
                if r['strength_db'] > prev['strength_db']:
                    prev['peak_freq'] = r['peak_freq']; prev['strength_db'] = r['strength_db']
                if r['method'] not in prev['method']:
                    prev['method'] = prev['method'] + '+' + r['method']
            else: merged.append(r.copy())
        return merged

    return _merge(nongap_results) + _merge(gap_results)

def split_carrier_by_gap(psd, freq, r, f):

    segment = psd[r:f+1]
    peaks,_ = find_peaks(segment, prominence=2)

    if len(peaks) < 2:
        return [(r,f)]

    spans=[]
    last=r

    for i in range(len(peaks)-1):

        p1=peaks[i]
        p2=peaks[i+1]

        valley_region=segment[p1:p2+1]
        vi=np.argmin(valley_region)
        vp=valley_region[vi]

        depth=min(segment[p1],segment[p2])-vp

        if depth >= GAP_DEPTH_DB:

            split=r+p1+vi

            spans.append((last,split))
            last=split

    spans.append((last,f))

    return spans


# ═════════════════════════════════════════════════════════════════════════════
# CARRIER-UNDER-CARRIER (CuC) DETECTION
# Three-stage pipeline operating on the carrier's PSD segment:
#   Stage 1 — Build primary-carrier spectral template (median + SG smooth)
#   Stage 2 — Spectral Subtraction: subtract template → SIC residual
#   Stage 3 — Bump detector + HOS kurtosis + curvature on the residual
#   Stage 4 — Multi-evidence confidence fusion
# Returns list of dicts (same schema as interference hits for easy logging).
# ═════════════════════════════════════════════════════════════════════════════

def _cuc_build_template(seg_psd: np.ndarray) -> np.ndarray:
    """
    Stage 1: Estimate what the primary carrier's spectrum SHOULD look like.

    Uses a wide median filter (removes narrow bumps from hidden carriers)
    followed by a Savitzky-Golay smoother to model the expected RRC roll-off.
    The element-wise maximum of both gives a tight envelope that hugs the
    primary shape without being distorted by a buried hidden signal.
    """
    n   = len(seg_psd)
    win = min(CUC_TEMPLATE_MEDIAN_BINS, n if n % 2 == 1 else n - 1)
    win = max(win if win % 2 == 1 else win - 1, 3)
    from scipy.signal import medfilt
    template = medfilt(seg_psd, kernel_size=win)

    sg_win = min(CUC_SAVGOL_WINDOW, n if n % 2 == 1 else n - 1)
    sg_win = max(sg_win if sg_win % 2 == 1 else sg_win + 1,
                 CUC_SAVGOL_POLY + 2)
    from scipy.signal import savgol_filter
    smoothed = savgol_filter(template, window_length=sg_win,
                             polyorder=CUC_SAVGOL_POLY)
    return np.maximum(template, smoothed)


def _cuc_spectral_subtract(seg_psd: np.ndarray,
                           template: np.ndarray) -> np.ndarray:
    """
    Stage 2: SIC in the dB domain via linear-power subtraction.

    P_residual = P_measured − P_host  (linear), then back to dB.
    A floor of −120 dB prevents log(0) artefacts.
    """
    FLOOR_DB = -120.0
    p_meas  = np.power(10.0, seg_psd  / 10.0)
    p_host  = np.power(10.0, template / 10.0)
    p_resid = np.maximum(p_meas - p_host, np.power(10.0, FLOOR_DB / 10.0))
    return 10.0 * np.log10(p_resid)


def _cuc_local_kurtosis(residual: np.ndarray) -> np.ndarray:
    """
    Stage 3a: Sliding-window excess kurtosis (4th-order cumulant proxy).

    Gaussian noise → excess kurtosis ≈ 0.
    A hidden PSK/QAM carrier → excess kurtosis significantly > 0.
    Windows overlap by 50 % for spatial continuity.
    """
    win  = CUC_HOS_WINDOW
    n    = len(residual)
    kurt = np.zeros(n)
    step = max(1, win // 2)
    for i in range(0, n, step):
        j   = min(i + win, n)
        seg = residual[i:j]
        if len(seg) < 4:
            continue
        m2 = float(np.mean(seg ** 2))
        m4 = float(np.mean(seg ** 4))
        if m2 < 1e-12:
            continue
        kurt[i:j] = np.maximum(kurt[i:j], (m4 / (m2 ** 2)) - 3.0)
    from scipy.ndimage import uniform_filter1d
    return uniform_filter1d(kurt, size=max(1, win // 2))


def detect_cuc_in_carrier(psd_segment: np.ndarray,
                           freq_segment: np.ndarray,
                           noise_floor: float) -> list:
    """
    Main CuC detection entry point for a single carrier segment.

    Parameters
    ----------
    psd_segment  : dB PSD values inside the carrier span
    freq_segment : corresponding frequency values in Hz
    noise_floor  : global noise floor estimate in dB

    Returns
    -------
    List of hit dicts (empty = no CuC detected).
    Each dict has: start_freq, end_freq, peak_freq, center_freq,
                   strength_db, confidence, method='cuc',
                   hidden_bw_hz, score_bump, score_hos, score_curv.
    """
    from scipy.signal import find_peaks, savgol_filter

    n = len(psd_segment)
    if n < 16:
        return []

    # ── Stage 1: Primary-carrier template ─────────────────────────────────────
    template = _cuc_build_template(psd_segment)

    # ── Stage 2: SIC residual ─────────────────────────────────────────────────
    residual = _cuc_spectral_subtract(psd_segment, template)

    # Residual noise floor (local percentile — immune to AWGN)
    nf_res = float(np.percentile(residual, 15.0))
    res_sigma = float(np.std(residual))

    # ── Stage 3a: Bump / spectral regrowth detection on residual ──────────────
    sg_win = min(CUC_SAVGOL_WINDOW, n if n % 2 == 1 else n - 1)
    sg_win = max(sg_win if sg_win % 2 == 1 else sg_win + 1,
                 CUC_SAVGOL_POLY + 2)
    smoothed_res = savgol_filter(residual, window_length=sg_win,
                                 polyorder=CUC_SAVGOL_POLY)

    bump_thr    = max(CUC_BUMP_THRESHOLD_DB, 1.5 * res_sigma)
    detect_lvl  = nf_res + bump_thr

    peaks, _ = find_peaks(
        smoothed_res,
        height     = detect_lvl,
        distance   = max(CUC_BUMP_MIN_BINS, 8),
        prominence = max(1.0, 0.5 * bump_thr),
        width      = CUC_BUMP_MIN_BINS,
    )

    if len(peaks) > 0:
        max_excess  = float(np.max(smoothed_res[peaks])) - detect_lvl
        score_bump  = float(1.0 - np.exp(-max_excess / 6.0))
    else:
        max_excess  = 0.0
        score_bump  = 0.0

    # ── Stage 3b: HOS — local kurtosis ───────────────────────────────────────
    kurt_arr   = _cuc_local_kurtosis(residual)
    high_kurt  = kurt_arr > CUC_HOS_THRESHOLD
    frac_kurt  = float(high_kurt.sum()) / max(1, n)
    max_kurt   = float(np.max(kurt_arr)) if high_kurt.any() else 0.0
    score_hos  = float(np.clip(
        frac_kurt * (1.0 - np.exp(-max_kurt / (2.0 * CUC_HOS_THRESHOLD))),
        0.0, 1.0
    ))

    # ── Stage 3c: Second-derivative curvature anomaly ─────────────────────────
    kern     = max(3, min(7, n // 5)) | 1
    sm2      = np.convolve(residual, np.ones(kern) / kern, mode='same')
    d2       = np.diff(sm2, n=2)
    d2p      = np.concatenate(([0.0], d2, [0.0]))
    med_d2   = float(np.median(np.abs(d2p))) + 1e-9
    norm_d2  = np.abs(d2p) / med_d2
    frac_cv  = float((norm_d2 > CUC_CURV_SIGMA).sum()) / max(1, n)
    mean_exc = float(np.mean(norm_d2[norm_d2 > CUC_CURV_SIGMA])) if frac_cv > 0 else 0.0
    score_cv = float(np.clip(
        frac_cv * (1.0 - np.exp(-mean_exc / (2.0 * CUC_CURV_SIGMA))),
        0.0, 1.0
    ))

    # ── Stage 4: Multi-evidence confidence fusion ─────────────────────────────
    confidence = 0.40 * score_bump + 0.30 * score_hos + 0.30 * score_cv
    confidence = float(np.clip(confidence, 0.0, 1.0))

    if confidence < CUC_CONFIDENCE_THRESHOLD:
        return []

    # ── Extract hidden carrier region ─────────────────────────────────────────
    grow_thr = nf_res + 0.5 * CUC_BUMP_THRESHOLD_DB
    if len(peaks) > 0:
        hidden_mask = np.zeros(n, dtype=bool)
        for pk in peaks:
            left  = pk
            right = pk
            while left  > 0     and residual[left  - 1] > grow_thr: left  -= 1
            while right < n - 1 and residual[right + 1] > grow_thr: right += 1
            hidden_mask[left:right + 1] = True
    else:
        hidden_mask = residual > grow_thr

    if not hidden_mask.any():
        return []

    hidden_freqs = freq_segment[hidden_mask]
    hidden_mags  = residual[hidden_mask]
    pk_local     = int(np.argmax(hidden_mags))
    peak_freq    = float(hidden_freqs[pk_local])
    start_freq   = float(hidden_freqs[0])
    end_freq     = float(hidden_freqs[-1])
    center_freq  = 0.5 * (start_freq + end_freq)
    hidden_bw    = end_freq - start_freq
    strength_db  = float(hidden_mags[pk_local]) - nf_res

    return [{
        'start_freq':   start_freq,
        'end_freq':     end_freq,
        'peak_freq':    peak_freq,
        'center_freq':  center_freq,
        'strength_db':  max(strength_db, 0.1),
        'confidence':   confidence,
        'hidden_bw_hz': hidden_bw,
        'score_bump':   score_bump,
        'score_hos':    score_hos,
        'score_curv':   score_cv,
        'residual':     residual,           # kept for optional overlay line
        'hidden_mask':  hidden_mask,
        'method':       'cuc',
        'is_gap':       False,
    }]
# Replaces static np.median(psd_s) throughout the pipeline.
# ═════════════════════════════════════════════════════════════════════════════

def estimate_noise_floor_adaptive(psd, percentile=None):
    """
    Rolling-percentile noise floor estimation.

    Robust to:
      • Wide carriers (a single carrier cannot dominate all rolling windows)
      • Multiple adjacent carriers (each window is independently low-clipped)
      • Interference spikes (upper percentiles are ignored by design)

    Algorithm:
      1. Slide a window of size (FFT_SIZE // NF_ROLLING_WINDOW_DIV) across psd.
      2. In each window compute the NF_PERCENTILE-th percentile (e.g. 15th).
      3. Return the median of all window floors → stable global noise estimate.
    """
    if percentile is None:
        percentile = NF_PERCENTILE
    n      = len(psd)
    window = max(32, n // NF_ROLLING_WINDOW_DIV)
    step   = max(1, window // 4)
    floors = []
    for i in range(0, n - window + 1, step):
        floors.append(float(np.percentile(psd[i:i + window], percentile)))
    if not floors:
        return float(np.percentile(psd, percentile))
    return float(np.median(floors))


# =========================
# CASE LOGS
# =========================
def classify_interference(carrier_cf, intf_cf, authorized_list=None):

    carrier_auth = config_mgr.is_authorized(carrier_cf)
    intf_auth    = config_mgr.is_authorized(intf_cf)

    if carrier_auth and intf_auth:
        return "NOISE FLOOR RISE"

    if not carrier_auth and intf_auth:
        return "AUTHORIZED CARRIER MASKED BY UNAUTHORIZED SIGNAL"

    if carrier_auth and not intf_auth:

        if abs(carrier_cf - intf_cf) < 50e3:
            return "INTERFERENCE AT CARRIER CENTER"

        if intf_cf > carrier_cf:
            return "INTERFERENCE ON RIGHT OF CARRIER"

        return "INTERFERENCE ON LEFT OF CARRIER"

    return "UNKNOWN INTERFERENCE"
# =========================
# UPDATE FUNCTION
# =========================
def update():
    global _latest_iq, _latest_meta, _latest_carriers
    global HW_SAMPLE_RATE, FFT_SIZE, HW_CENTER_FREQ
    global window, iq_buffer, max_hold, min_hold
    global psd_avg, smooth_enabled, smooth_alpha
    global _fast_ad_buffer

    with _state_lock:
        iq_frame       = _latest_iq
        meta_frame     = _latest_meta
        carrier_frame  = _latest_carriers
        _latest_iq = _latest_meta = _latest_carriers = None

    # METADATA UPDATE
    if meta_frame is not None:
        HW_SAMPLE_RATE = meta_frame["rate"]
        FFT_SIZE       = meta_frame["fft"]
        HW_CENTER_FREQ = meta_frame["cf"]
        window    = get_window("hann", FFT_SIZE)
        iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
        max_hold  = np.full(FFT_SIZE, -np.inf)
        min_hold  = np.full(FFT_SIZE,  np.inf)
        _unauth_persistence.clear(); _carrier_persistence.clear()
        _intf_tracker.reset(); _gap_tracker.reset()
        _valley_tracker.reset(); _carrier_tracker.reset()
        _cuc_tracker.reset()
        _fast_ad_buffer = None
        update_axis()
        for ln in [line_live, line_max, line_min]: ln.set_xdata(freq_axis / 1e6)
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] META UPDATE  |  "
            f"SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  FFT: {FFT_SIZE}  |  "
            f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz", "#dcdcaa")

    if iq_frame is None: return
    iq = iq_frame
    if len(iq) < FFT_SIZE: return
    iq_buffer[:] = iq[:FFT_SIZE]

    # FFT -> PSD
    spectrum = np.fft.fftshift(np.fft.fft(iq_buffer * window))
    psd      = 20 * np.log10(np.abs(spectrum) + 1e-12)
    psd     += np.random.normal(0, 3, len(psd))

    # SMOOTH
    if psd_avg is None: psd_avg = psd.copy()
    if smooth_enabled:
        alpha = 1 - (1 - smooth_alpha) ** 2
        psd_avg = alpha * psd_avg + (1 - alpha) * psd
        display_psd = psd_avg
    else:
        display_psd = psd

    # FAST ATTACK / SLOW DECAY (additional layer — works on top of smooth or raw)
    if FAST_AD_ENABLED:
        if _fast_ad_buffer is None or len(_fast_ad_buffer) != len(display_psd):
            _fast_ad_buffer = display_psd.copy()
        else:
            rising  = display_psd > _fast_ad_buffer
            alpha_vec = np.where(rising, FAST_AD_ATTACK_ALPHA, FAST_AD_DECAY_ALPHA)
            _fast_ad_buffer = alpha_vec * display_psd + (1.0 - alpha_vec) * _fast_ad_buffer
        display_psd = _fast_ad_buffer.copy()

    line_live.set_ydata(display_psd)

    if enable_max_hold: max_hold = np.maximum(max_hold, psd)
    if enable_min_hold: min_hold = np.minimum(min_hold, psd)
    line_max.set_ydata(max_hold); line_min.set_ydata(min_hold)

    if carrier_frame is not None:
        txt = "ACTIVE CARRIERS\n\n"
        if not carrier_frame: txt += "None detected"
        else:
            for c in carrier_frame:
                txt += (f"ID {c['id']}\nFreq: {c['freq']/1e6:.3f} MHz\n"
                        f"BW: {c['bw']/1e3:.1f} kHz\nPwr: {c['power']:.1f} dB\n---\n")
        monitor_text.set_text(txt)

    # CLEAR OVERLAYS
    for patch in ax.patches[:]: patch.remove()
    for txt_obj in ax.texts[:]: txt_obj.remove()
    for l in ax.lines[3:]: l.remove()

    # =====================================================
    # CARRIER DETECTION
    # =====================================================
    smooth_taps = max(3, int(round(SMOOTH_BW_HZ / df))) | 1
    min_bins    = max(2, int(round(MIN_CARRIER_BW_HZ / df)))

    psd_s = np.convolve(display_psd, np.ones(smooth_taps)/smooth_taps, mode="same")

    # ── IMPROVEMENT 3a: Adaptive noise floor (replaces static median) ─────────
    # Rolling-percentile approach — robust to wide/multiple carriers and spikes.
    noise = estimate_noise_floor_adaptive(psd_s, percentile=NF_PERCENTILE)
    peak  = float(np.max(psd_s))
    threshold = noise + THRESHOLD_RATIO * (peak - noise)   # kept for compat

    # ── IMPROVEMENT 3b: Adaptive detection threshold (noise + k·σ) ────────────
    # σ is computed only over bins that are plausibly noise (< noise + 10 dB)
    # to avoid carrier power inflating the spread estimate.
    _nf_mask     = psd_s < (noise + 10.0)
    noise_sigma  = float(np.std(psd_s[_nf_mask])) if _nf_mask.sum() > 4 else 1.0
    noise_sigma  = max(noise_sigma, 0.3)            # floor — avoid zero-sigma collapse
    detect_threshold = noise + max(2.5, CARRIER_K_SIGMA * noise_sigma)

    # Binary carrier mask
    above = psd_s > detect_threshold

    # ── IMPROVEMENT 3c: Morphological opening — remove isolated false-positive bins
    # (erode then dilate with MORPH_OPEN_BINS kernel).
    if MORPH_OPEN_BINS > 1:
        _k = MORPH_OPEN_BINS
        _h = _k // 2
        # Erosion: a bin is True only if all bins in the kernel window are True
        _eroded = above.copy()
        for _ki in range(-_h, _h + 1):
            _eroded &= np.roll(above, _ki)
        # Dilation: restore the shape of surviving regions
        _dilated = np.zeros(len(above), dtype=bool)
        for _ki in range(-_h, _h + 1):
            _dilated |= np.roll(_eroded, _ki)
        above = _dilated

    # ── IMPROVEMENT 3d: Morphological closing — bridge tiny intra-carrier notches
    # (dilate then erode with MORPH_CLOSE_BINS kernel).
    if MORPH_CLOSE_BINS > 1:
        _k = MORPH_CLOSE_BINS
        _h = _k // 2
        _dilated2 = np.zeros(len(above), dtype=bool)
        for _ki in range(-_h, _h + 1):
            _dilated2 |= np.roll(above, _ki)
        _eroded2 = _dilated2.copy()
        for _ki in range(-_h, _h + 1):
            _eroded2 &= np.roll(_dilated2, _ki)
        above = _eroded2

    edges = np.diff(above.astype(np.int8))
    rises = np.where(edges == 1)[0]
    falls = np.where(edges == -1)[0]

    if len(falls) > 0 and (len(rises) == 0 or falls[0] < rises[0]):
        rises = np.insert(rises, 0, 0)
    if len(rises) > 0 and (len(falls) == 0 or rises[-1] > falls[-1]):
        falls = np.append(falls, FFT_SIZE - 1)

    carrier_min_bins = max(2, int(round(MIN_CARRIER_BW_HZ / df)))
    raw_spans = [(int(r), int(f)) for r, f in zip(rises, falls)
                 if (int(f) - int(r)) >= carrier_min_bins]

    # ── IMPROVEMENT 3e: Adaptive carrier merging (bandwidth-aware gap threshold) ─
    # Gap threshold adapts to the narrower of the two neighbouring carriers.
    # Prevents fragmentation of wide carriers with shallow internal notches
    # while correctly keeping narrow separated carriers apart.
    if len(raw_spans) > 1:
        _merged = [list(raw_spans[0])]
        for _r2, _f2 in raw_spans[1:]:
            _r1, _f1 = _merged[-1]
            _bw1_hz  = (_f1 - _r1) * df
            _bw2_hz  = (_f2 - _r2) * df
            _gap_hz  = max(0.0, float(freq_axis[_r2] - freq_axis[_f1]))
            _merge_thr = max(MIN_CARRIER_BW_HZ,
                             ADAPTIVE_MERGE_BW_FACTOR * min(_bw1_hz, _bw2_hz))
            if _gap_hz < _merge_thr:
                _merged[-1][1] = _f2          # extend previous span
            else:
                _merged.append([_r2, _f2])
        raw_spans = [tuple(s) for s in _merged]

    # =====================================================
    # VALLEY DETECTION & CARRIER SPLITTING
    # =====================================================
    # Run BEFORE auth check so each split sub-carrier is independently
    # auth-checked, highlighted, and interference-detected.
    valley_overlay_records = []   # for brown overlay drawing later
    # Track the original (pre-split) span for each split sub-span so we can
    # draw the full carrier highlight once instead of per-sub-span.
    valley_split_map: dict = {}   # sub-span (r,f) → original (r_c, f_c)

    if VALLEY_ENABLED:
        split_raw_spans = []
        for r_c, f_c in raw_spans:
            r_c, f_c = int(r_c), int(f_c)

            if (f_c - r_c) < 10:
                split_raw_spans.append((r_c, f_c))
                continue

            segment  = psd_s[r_c:f_c + 1]
            freq_seg = freq_axis[r_c:f_c + 1]
            valleys  = detect_carrier_valleys(segment, freq_seg, noise)

            if not valleys:
                split_raw_spans.append((r_c, f_c))
                continue

            # Sort valleys left-to-right
            valleys.sort(key=lambda v: v['valley_idx'])

            # Record valleys for brown overlay
            for v in valleys:
                bl_abs = r_c + v['brown_left_idx']
                br_abs = r_c + v['brown_right_idx']
                bl_abs = max(0, min(bl_abs, FFT_SIZE - 1))
                br_abs = max(0, min(br_abs, FFT_SIZE - 1))
                valley_overlay_records.append({
                    'brown_left_freq':  float(freq_axis[bl_abs]),
                    'brown_right_freq': float(freq_axis[br_abs]),
                    'depth':            v['depth'],
                    'valley_freq':      float(freq_axis[r_c + v['valley_idx']]),
                    'gap_hz':           v['gap_hz'],
                })

            # Split the span at valley boundaries
            last_start = r_c
            for v in valleys:
                bl_abs = r_c + v['brown_left_idx']
                br_abs = r_c + v['brown_right_idx']
                bl_abs = max(0, min(bl_abs, FFT_SIZE - 1))
                br_abs = max(0, min(br_abs, FFT_SIZE - 1))

                # Left sub-carrier: from last_start to brown_left
                if bl_abs > last_start + 1:
                    split_raw_spans.append((last_start, bl_abs))
                    valley_split_map[(last_start, bl_abs)] = (r_c, f_c)
                last_start = br_abs

            # Right-most sub-carrier: from last valley's brown_right to span end
            if last_start < f_c - 1:
                split_raw_spans.append((last_start, f_c))
                valley_split_map[(last_start, f_c)] = (r_c, f_c)

        raw_spans = split_raw_spans

    # =====================================================
    # BUILD RENDER RECORDS
    # Each entry describes one sub-carrier to draw:
    #   r, f         — bin indices (signal extent)
    #   f_start/stop — Hz of highlight edges (noise-floor walk)
    #   f_center     — Hz center
    #   bw           — Hz bandwidth
    #   is_auth      — True if CF is in authorized list
    #   is_valley_sub— True if came from a valley split
    #   valley_boundary_left/right — Hz of valley dotted lines (valley subs only)
    # =====================================================
    gnt = noise
    has_auth_config = len(config_mgr.get_all()) > 0
    noise_stop      = noise + 1.5   # used by _edge_walk and valley helpers

    # ── IMPROVEMENT 4: Slope-based edge refinement with valley snap ───────────
    # Pre-compute gradient once; reused for every carrier's edge walk.
    _psd_s_grad = np.gradient(psd_s)

    def _edge_walk(r_bin, f_bin):
        """
        IMPROVEMENT 4: Walk outward from [r_bin, f_bin] to noise floor.

        Enhancements over original:
          • Gradient (slope) transition detection — snaps the boundary to the
            nearest spectral edge (sharp drop) rather than the noise floor alone.
          • Valley-snap — stops at local minima (gradient sign flip) so the
            edge doesn't cross into an adjacent carrier's slope.

        Returns (f_start_hz, f_stop_hz).
        """
        stop_level = noise + 1.5

        # LEFT edge: walk left; stop at noise floor OR at a local minimum
        # (gradient flips from negative to positive → valley bottom)
        le = r_bin
        while le > 1 and psd_s[le] > stop_level:
            # Valley snap: gradient flips sign → we've passed a local minimum
            if _psd_s_grad[le] > 0.0 and _psd_s_grad[le - 1] <= 0.0:
                break
            le -= 1

        # RIGHT edge: symmetric
        re = f_bin
        while re < FFT_SIZE - 2 and psd_s[re] > stop_level:
            if _psd_s_grad[re] < 0.0 and _psd_s_grad[re + 1] >= 0.0:
                break
            re += 1

        return float(freq_axis[le]), float(freq_axis[re])

    render_records = []   # list of dicts, one per sub-carrier to display

    for r_c, f_c in raw_spans:
        r_c, f_c = int(r_c), int(f_c)
        is_valley_sub = (r_c, f_c) in valley_split_map

        span_center_hz  = 0.5 * (float(freq_axis[r_c]) +
                                   float(freq_axis[min(f_c, FFT_SIZE - 1)]))
        span_center_mhz = span_center_hz / 1e6

        if has_auth_config:
            is_auth = config_mgr.is_authorized(span_center_hz)
        else:
            is_auth = True   # no config → treat everything as authorized

        # Tight boundary: noise-floor walk from raw detection edges
        fs, fe = _edge_walk(r_c, f_c)

        # Valley sub-carriers use the valley boundary lines as their inner edges
        v_left_hz  = None
        v_right_hz = None
        if is_valley_sub:
            parent = valley_split_map[(r_c, f_c)]
            # Find which valley record owns this sub-span
            # The valley records store the brown_left/right in Hz; match by
            # checking if the sub-span's center falls to the left or right.
            for vr in valley_overlay_records:
                if vr.get('_parent') == parent:
                    sub_cf = span_center_hz
                    if sub_cf < vr['valley_freq']:
                        # this is the LEFT sub-carrier → inner edge = brown_left
                        v_right_hz = vr['brown_left_freq']
                    else:
                        # this is the RIGHT sub-carrier → inner edge = brown_right
                        v_left_hz  = vr['brown_right_freq']

        render_records.append({
            'r': r_c, 'f': f_c,
            'f_start': fs, 'f_stop': fe,
            'f_center': span_center_hz,
            'bw': fe - fs,
            'is_auth': is_auth,
            'is_valley_sub': is_valley_sub,
            'v_left_hz': v_left_hz,    # None unless right sub-carrier
            'v_right_hz': v_right_hz,  # None unless left sub-carrier
        })

    # Tag each valley_overlay_record with its parent span using position-based matching.
    # A valley belongs to the parent span whose freq range contains the valley_freq.
    _parent_sub_map: dict = {}   # parent (r_c,f_c) → list of sub-spans
    for (r_sub, f_sub), parent in valley_split_map.items():
        _parent_sub_map.setdefault(parent, []).append((r_sub, f_sub))

    for vr in valley_overlay_records:
        vr.pop('_parent', None)   # clear any stale tag first
        vf = vr['valley_freq']
        for parent, _subs in _parent_sub_map.items():
            r_c, f_c = parent
            if float(freq_axis[r_c]) <= vf <= float(freq_axis[min(f_c, FFT_SIZE-1)]):
                vr['_parent'] = parent
                break

    # Fix up render_records v_left_hz / v_right_hz using correct parent tagging
    for rec in render_records:
        if not rec['is_valley_sub']:
            continue
        parent = valley_split_map[(rec['r'], rec['f'])]
        sub_cf = rec['f_center']
        for vr in valley_overlay_records:
            if vr.get('_parent') != parent:
                continue
            if sub_cf < vr['valley_freq']:
                rec['v_right_hz'] = vr['brown_left_freq']   # left sub → inner right edge
                rec['v_left_hz']  = None
            else:
                rec['v_left_hz']  = vr['brown_right_freq']  # right sub → inner left edge
                rec['v_right_hz'] = None

    # Build unauth hits list for persistence (spans where CF is not authorized)
    all_unauth_hits = []
    if UNAUTH_ENABLED and has_auth_config:
        for rec in render_records:
            if not rec['is_auth']:
                r_c, f_c = rec['r'], rec['f']
                raw_pk = float(np.max(display_psd[r_c:f_c + 1]))
                excess = raw_pk - noise
                all_unauth_hits.append({
                    'r': r_c, 'f': f_c,
                    'f_start': rec['f_start'], 'f_stop': rec['f_stop'],
                    'f_center': rec['f_center'], 'bw': rec['bw'],
                    'peak_pwr': raw_pk, 'excess_db': max(excess, 0.1),
                    'carrier_ref_db': noise, 'trigger': 'UNAUTHORIZED',
                    'local_noise': noise,
                })

    confirmed_unauth_hits = apply_unauth_persistence(all_unauth_hits)
    # Build set of confirmed unauth centers for quick lookup
    confirmed_unauth_centers = {
        int(round(h['f_center'] / UNAUTH_BUCKET_HZ)) for h in confirmed_unauth_hits
    }

    # =====================================================
    # UPDATE MARKERS
    # =====================================================
    def safe_remove(obj):
        try:
            if obj is not None: obj.remove()
        except: pass
        return None

    for m in markers.values():
        m.artist_a = safe_remove(m.artist_a)
        m.artist_b = safe_remove(m.artist_b)
        m.text     = safe_remove(m.text)
        if not markers_global_on: continue
        color = MARKER_COLORS[m.idx]
        if m.mode == "peak":
            pidx = int(np.argmax(display_psd))
            m.point_a = (float(freq_axis[pidx]), float(display_psd[pidx]))
        if m.point_a:
            fx, py = m.point_a
            if m.mode == "normal":
                bidx = int(np.argmin(np.abs(freq_axis - fx)))
                py = float(display_psd[bidx]); m.point_a = (fx, py)
            m.artist_a = ax.scatter(fx/1e6, py, marker="D", s=80, color=color, zorder=20)
            label = f"M{m.idx}\n{fx/1e6:.3f} MHz\n{py:.1f} dB"
            if m.mode == "delta" and m.point_b:
                fx2, py2 = m.point_b
                m.artist_b = ax.scatter(fx2/1e6, py2, marker="D", s=80, color=color, zorder=20)
                label += f"\nΔf: {abs(fx-fx2)/1e6:.3f} MHz\nΔP: {abs(py-py2):.1f} dB"
            elif m.mode == "delta" and not m.point_b:
                label += "\n[click ref point]"
            m.text = ax.text(fx/1e6, py + 3, label, color=color, fontsize=9,
                             bbox=dict(fc="black", alpha=0.6), zorder=21)

    # =====================================================
    # DRAW CARRIERS + INTERFERENCE + VALLEY LINES
    # =====================================================
    now            = time.time()
    log_this_frame = (now - log_win._last_log_time) >= LOG_THROTTLE_SEC
    carrier_id     = 0
    GREEN_SHADES   = ["#4ec9b0", "#6abf69", "#98e898", "#00ff7f", "#b2fab4"]

    # Track already-drawn valley dotted lines to avoid duplicates
    drawn_valley_lines: set = set()
    # Track authorized spans for log counting
    authorized_spans = [rec for rec in render_records if rec['is_auth']]

    # Collect detections across all carriers for single-call tracker update
    _all_intf_dets   = []   # non-gap interference detections
    _all_gap_dets    = []   # gap interference detections
    _all_carrier_dets = []  # carrier detections
    _all_cuc_dets    = []   # carrier-under-carrier detections

    for rec in render_records:
        r, f = int(rec['r']), int(rec['f'])
        if (f - r) < min_bins:
            continue

        carrier_id += 1    # increment at top so it's available for tagging

        f_start   = rec['f_start']
        f_stop    = rec['f_stop']
        f_center  = rec['f_center']
        bw        = rec['bw']
        is_auth   = rec['is_auth']

        # ── For valley sub-carriers, use valley boundary as inner edge ──
        # Left sub-carrier: draw from f_start → v_right_hz
        # Right sub-carrier: draw from v_left_hz → f_stop
        if rec['is_valley_sub']:
            if rec['v_right_hz'] is not None:
                # LEFT sub-carrier: clamp f_stop to valley left boundary
                f_stop  = rec['v_right_hz']
            elif rec['v_left_hz'] is not None:
                # RIGHT sub-carrier: clamp f_start to valley right boundary
                f_start = rec['v_left_hz']
            bw       = f_stop - f_start
            f_center = 0.5 * (f_start + f_stop)

        # ── Choose highlight color ──
        # - Authorized CF → green
        # - Unauthorized CF → red
        # - Authorized CF that is confirmed unauth (overlaying) → brown
        is_confirmed_unauth = (
            int(round(rec['f_center'] / UNAUTH_BUCKET_HZ)) in confirmed_unauth_centers
        )
        if not has_auth_config:
            span_color = "green"
            span_label = f"{bw/1e3:.0f} kHz"
        elif is_auth and not is_confirmed_unauth:
            span_color = "green"
            span_label = f"{bw/1e3:.0f} kHz"
        elif is_auth and is_confirmed_unauth:
            # Authorized CF but detected as overlaying/unauth → brown
            span_color = "#8B4513"
            span_label = f"AUTH-OVERLAY\n{bw/1e3:.0f} kHz"
        else:
            # Not authorized → red (drawn only if UNAUTH_ENABLED)
            span_color = "red"
            span_label = f"UNAUTH\n{bw/1e3:.0f} kHz"

        # Skip drawing un-authorized spans when UNAUTH is disabled
        if not is_auth and not UNAUTH_ENABLED:
            continue

        # Draw span highlight
        span_alpha = 0.25 if span_color == "green" else 0.40
        ax.axvspan(f_start/1e6, f_stop/1e6, color=span_color, alpha=span_alpha, zorder=2)
        ax.axvline(f_start/1e6, color="orange", lw=1, zorder=3)
        ax.axvline(f_stop /1e6, color="orange", lw=1, zorder=3)
        ax.text(f_center/1e6, Y_MAX - 5, span_label,
                ha="center", va="top", fontsize=7.5,
                color="white" if span_color != "green" else "black",
                bbox=dict(boxstyle="round", fc="white" if span_color == "green" else span_color,
                          alpha=0.8), zorder=4)

        # ── Valley dotted boundary lines (drawn once per unique boundary) ──
        if rec['is_valley_sub']:
            for vline_hz in [rec['v_left_hz'], rec['v_right_hz']]:
                if vline_hz is None:
                    continue
                vline_key = round(vline_hz / 1e3)  # unique key per kHz bucket
                if vline_key not in drawn_valley_lines:
                    drawn_valley_lines.add(vline_key)
                    ax.axvline(vline_hz/1e6, color='#D2691E', lw=1.5, ls='--', zorder=6)

        # ── Power / BW stats ──
        cpk = float(np.max(display_psd[r:f+1]))
        lp  = float(np.sum(10 ** (display_psd[r:f+1] / 10)))
        ctp = float(10 * np.log10(lp + 1e-12))
        bins_in = f - r + 1
        nl  = float(np.median(10 ** (display_psd / 10)))
        ntd = float(10 * np.log10(nl * bins_in + 1e-12))
        cn  = ctp - ntd

        # ── INTERFERENCE DETECTION (always run, including valley sub-carriers) ──
        intf_hits   = []
        gap_hits    = []
        nongap_hits = []

        if INTF_ENABLED and (f - r) >= 6:
            intf_hits   = detect_interference_in_carrier(display_psd[r:f+1], freq_axis[r:f+1])
            gap_hits    = [h for h in intf_hits if h.get('is_gap', False)]
            nongap_hits = [h for h in intf_hits if not h.get('is_gap', False)]

        # Draw non-gap interference
        if nongap_hits:
            ids = min(h['start_freq'] for h in nongap_hits)
            ide = max(h['end_freq']   for h in nongap_hits)
            # Clip to this sub-carrier's display boundaries
            ids = max(ids, f_start)
            ide = min(ide, f_stop)
            if ide > ids:
                best           = max(nongap_hits, key=lambda h: h['strength_db'])
                # LOG FIX: use strongest hit's actual peak_freq, not merged span midpoint
                intf_center_visual = 0.5 * (ids + ide)   # for overlay drawing position
                intf_center_log    = best['peak_freq']    # actual detected frequency for log
                classification = classify_interference(f_center, intf_center_log)
                carrier_auth = config_mgr.is_authorized(f_center)
                intf_auth    = config_mgr.is_authorized(intf_center_log)

                # Suppress visualization when both carrier and interference are unauthorized
                if not carrier_auth and not intf_auth:
                    pass  # detection still happens, but do not draw highlight
                else:

                    intf_color = ("green"
                                  if classification == "AUTHORIZED CARRIER MASKED BY UNAUTHORIZED SIGNAL"
                                  else "red")

                    ax.axvspan(ids/1e6, ide/1e6, color=intf_color, alpha=0.35, zorder=7)

                    ax.text(intf_center_visual/1e6, Y_MAX - 10,
                            f"INTF\n{best['strength_db']:.1f}dB",
                            ha="center", va="top", fontsize=7, color="white",
                            bbox=dict(boxstyle="round", fc=intf_color, alpha=0.8), zorder=10)

                    # CARRIER-BOUND CHECK: only collect if intf center is within this carrier's span
                    if f_start <= intf_center_log <= f_stop:
                        _all_intf_dets.append({
                            'center_freq': intf_center_log,
                            'strength_db': best['strength_db'],
                            'method': best['method'],
                            'ids': ids, 'ide': ide,
                            'classification': classification,
                            'parent_carrier_id': carrier_id,
                        })

        # Draw GAP interference — clipped to sub-carrier boundaries
        for gh in gap_hits:
            gs = max(gh['start_freq'], f_start)
            ge = min(gh['end_freq'],   f_stop)

            if ge <= gs:
                continue
            gc = 0.5 * (gs + ge)
            carrier_auth = config_mgr.is_authorized(f_center)
            intf_auth    = config_mgr.is_authorized(gc)

            if not carrier_auth and not intf_auth:
                continue
            ax.axvspan(gs/1e6, ge/1e6, color="red", alpha=0.55, zorder=6)
            ax.axvline(gs/1e6, color="#ff6666", lw=1.5, ls="--", zorder=7)
            ax.axvline(ge/1e6, color="#ff6666", lw=1.5, ls="--", zorder=7)
            ax.text(gc/1e6, Y_MAX - 16,
                    f"GAP-INTF\n{gh['strength_db']:.1f}dB",
                    ha="center", va="top", fontsize=7.5, color="#ff4444",
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.85),
                    zorder=10)
            # CARRIER-BOUND CHECK: only collect if gap center is within this carrier's span
            gap_log_center = gh['peak_freq']
            if f_start <= gap_log_center <= f_stop:
                _all_gap_dets.append({
                    'center_freq': gap_log_center,
                    'strength_db': gh['strength_db'],
                    'method': gh['method'],
                    'gs': gs, 'ge': ge,
                    'parent_carrier_id': carrier_id,
                })

        # ── CUC DETECTION — runs after all other intra-carrier checks ────────
        if CUC_ENABLED and (f - r) >= 24:
            _cuc_hits = detect_cuc_in_carrier(
                display_psd[r:f + 1], freq_axis[r:f + 1], noise
            )
            for _ch in _cuc_hits:
                cs = _ch['center_freq']
                ce = _ch['end_freq']
                cst = _ch['start_freq']

                # ── Draw hidden carrier overlay on the live PSD ──────────────
                # 1. Magenta axvspan showing the hidden carrier region
                ax.axvspan(cst / 1e6, ce / 1e6,
                           color='#ff00ff', alpha=0.18, zorder=8)
                # 2. Dotted boundary lines
                ax.axvline(cst / 1e6, color='#ff00ff', lw=1.0,
                           ls=':', zorder=9)
                ax.axvline(ce  / 1e6, color='#ff00ff', lw=1.0,
                           ls=':', zorder=9)
                # 3. Residual waveform overlaid on the live PSD
                #    (offset up by the carrier's peak so it's visually readable)
                _res_freqs = freq_axis[r:f + 1][_ch['hidden_mask']]
                _res_mags  = _ch['residual'][_ch['hidden_mask']]
                # Normalise residual to sit just above the carrier's noise floor
                _res_offset = noise + 3.0
                _res_scale  = (_res_mags - float(np.min(_res_mags)))
                _res_max    = float(np.max(_res_scale)) if _res_scale.max() > 0 else 1.0
                _res_plot   = _res_offset + 8.0 * (_res_scale / _res_max)
                ax.plot(_res_freqs / 1e6, _res_plot,
                        color='#ff00ff', lw=1.5, ls='-', zorder=10,
                        label='_nolegend_')
                # 4. Label badge
                ax.text(
                    cs / 1e6,
                    Y_MAX - 22,
                    f"CuC\n{cs/1e6:.4f}MHz\n"
                    f"BW≈{_ch['hidden_bw_hz']/1e3:.0f}kHz\n"
                    f"Conf={_ch['confidence']:.0%}",
                    ha='center', va='top', fontsize=6.5,
                    color='#ff00ff', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3',
                              fc='black', ec='#ff00ff', alpha=0.88),
                    zorder=11
                )

                # Collect for tracker + logging
                if f_start <= cs <= f_stop:
                    _all_cuc_dets.append({
                        'center_freq':      cs,
                        'strength_db':      _ch['strength_db'],
                        'confidence':       _ch['confidence'],
                        'hidden_bw_hz':     _ch['hidden_bw_hz'],
                        'start_freq':       cst,
                        'end_freq':         ce,
                        'score_bump':       _ch['score_bump'],
                        'score_hos':        _ch['score_hos'],
                        'score_curv':       _ch['score_curv'],
                        'parent_carrier_id': carrier_id,
                        'parent_cf':        f_center,
                    })

        # Collect carrier detection for post-loop tracker update
        _all_carrier_dets.append({
            'center_freq': f_center,
            'strength_db': cpk,
            'carrier_id': carrier_id,
            'is_auth': is_auth,
            'is_confirmed_unauth': is_confirmed_unauth,
            'is_valley_sub': rec['is_valley_sub'],
            'ctp': ctp, 'bw': bw, 'cpk': cpk, 'noise': noise,
            'f_start': f_start, 'f_stop': f_stop, 'cn': cn,
        })

    # =====================================================
    # POST-LOOP: Single tracker update + NESTED carrier-bound logging
    # =====================================================
    # Update all trackers ONCE per frame (prevents premature aging)
    _intf_stable    = _intf_tracker.update(_all_intf_dets)
    _gap_stable     = _gap_tracker.update(_all_gap_dets)
    _carrier_stable = _carrier_tracker.update(_all_carrier_dets)
    _cuc_stable     = _cuc_tracker.update(_all_cuc_dets)

    # Build lookup: stable tracker results keyed by bucket for quick matching
    _carrier_stable_bk = {}
    for cs in _carrier_stable:
        bk = int(round(cs['center_freq'] / STABILITY_BUCKET_HZ))
        _carrier_stable_bk[bk] = cs

    # Build child lookup: interference/gap grouped by parent_carrier_id
    _intf_by_carrier = {}
    for _si in _intf_stable:
        pcid = _si.get('parent_carrier_id')
        if pcid is not None:
            _intf_by_carrier.setdefault(pcid, []).append(_si)

    _gap_by_carrier = {}
    for _gs in _gap_stable:
        pcid = _gs.get('parent_carrier_id')
        if pcid is not None:
            _gap_by_carrier.setdefault(pcid, []).append(_gs)

    _cuc_by_carrier = {}
    for _cu in _cuc_stable:
        pcid = _cu.get('parent_carrier_id')
        if pcid is not None:
            _cuc_by_carrier.setdefault(pcid, []).append(_cu)

    # NESTED LOG: Carrier → its interferences → its gaps
    if log_this_frame and log_win.isVisible():
        for _cd in _all_carrier_dets:
            cid = _cd['carrier_id']
            bk  = int(round(_cd['center_freq'] / STABILITY_BUCKET_HZ))

            # Skip carrier if not yet stable (debounce)
            _ct = _carrier_stable_bk.get(bk)
            if _ct is None:
                continue
            if not _cd['is_auth']:
                continue

            # ── Log carrier line ──
            _tid_tag = f"T{_ct['track_id']}"
            status_tag = ("[AUTH]" if (_cd['is_auth'] and not _cd['is_confirmed_unauth']) else
                          "[AUTH-OVERLAY]" if (_cd['is_auth'] and _cd['is_confirmed_unauth']) else
                          "[UNAUTH]")
            valley_tag = " [VALLEY-SUB]" if _cd['is_valley_sub'] else ""
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"Carrier {cid} {status_tag}{valley_tag} [{_tid_tag}]  |  "
                f"Freq: {_cd['center_freq']/1e6:.3f} MHz  |  Pwr: {_cd['ctp']:.1f} dB  |  "
                f"BW: {_cd['bw']/1e3:.1f} kHz  |  Peak: {_cd['cpk']:.1f} dB  |  "
                f"Noise: {_cd['noise']:.1f} dB  |  "
                f"Range: {_cd['f_start']/1e6:.3f}-{_cd['f_stop']/1e6:.3f} MHz  |  "
                f"C/N: {_cd['cn']:.2f} dB",
                GREEN_SHADES[(cid - 1) % len(GREEN_SHADES)])

            # ── Log interference NESTED under this carrier ──
            for _si in _intf_by_carrier.get(cid, []):
                intf_bw = (_si['ide'] - _si['ids']) / 1e3
                _itid = f"T{_si['track_id']}"
                _iconf = f"C:{_si['confidence']:.0%}"
                log_win.append(
                    f"  └─ INTERFERENCE [{_si['method'].upper()}] [{_itid}|{_iconf}]  |  "
                    f"Center: {_si['center_freq']/1e6:.4f} MHz  |  "
                    f"BW: {intf_bw:.1f} kHz  |  "
                    f"Strength: +{_si['strength_db']:.1f} dB  |  "
                    f"Range: {_si['ids']/1e6:.4f}-{_si['ide']/1e6:.4f} MHz",
                    "#ff4c4c")
                log_win.append(f"      ↳ TYPE: {_si['classification']}", "#ffd700")

            # ── Log gap interference NESTED under this carrier ──
            for _gs in _gap_by_carrier.get(cid, []):
                _gtid = f"T{_gs['track_id']}"
                _gconf = f"C:{_gs['confidence']:.0%}"
                log_win.append(
                    f"  └─ GAP-INTERFERENCE [{_gs['method'].upper()}] [{_gtid}|{_gconf}]  |  "
                    f"Center: {_gs['center_freq']/1e6:.4f} MHz  |  "
                    f"BW: {(_gs['ge']-_gs['gs'])/1e3:.1f} kHz  |  "
                    f"Depth: {_gs['strength_db']:.1f} dB  |  "
                    f"Range: {_gs['gs']/1e6:.4f}-{_gs['ge']/1e6:.4f} MHz",
                    "#ff4444")

            # ── Log CuC NESTED under this carrier ────────────────────────────
            for _cu in _cuc_by_carrier.get(cid, []):
                _cutid  = f"T{_cu['track_id']}"
                _cuconf = f"C:{_cu['confidence']:.0%}"
                log_win.append(
                    f"  └─ CuC [CARRIER-UNDER-CARRIER] [{_cutid}|{_cuconf}]  |  "
                    f"Center: {_cu['center_freq']/1e6:.4f} MHz  |  "
                    f"BW: {_cu['hidden_bw_hz']/1e3:.1f} kHz  |  "
                    f"Strength: +{_cu['strength_db']:.1f} dB  |  "
                    f"Range: {_cu['start_freq']/1e6:.4f}-{_cu['end_freq']/1e6:.4f} MHz  |  "
                    f"Scores bump={_cu['score_bump']:.2f} "
                    f"hos={_cu['score_hos']:.2f} "
                    f"curv={_cu['score_curv']:.2f}",
                    "#ff00ff")
                log_win.append(
                    f"      ↳ TYPE: CARRIER-UNDER-CARRIER (hidden secondary signal)",
                    "#ff80ff")
    # =====================================================
    # DRAW BROWN GAP BETWEEN SPLIT CARRIERS
    # =====================================================
    if VALLEY_ENABLED and valley_overlay_records:

        for vr in valley_overlay_records:

            bl = vr['brown_left_freq']
            br = vr['brown_right_freq']
            valley_freq = vr['valley_freq']

            # Determine which carriers exist on each side
            left_auth  = False
            right_auth = False

            for rec in render_records:

                cf = rec['f_center']

                if cf < valley_freq:
                    if rec['is_auth']:
                        left_auth = True

                if cf > valley_freq:
                    if rec['is_auth']:
                        right_auth = True

            # Skip if BOTH carriers are unauthorized
            if not (left_auth or right_auth):
                continue

            # Draw brown interference region
            ax.axvspan(
                bl/1e6,
                br/1e6,
                color="#8B4513",
                alpha=0.45,
                zorder=5
            )
    # =====================================================
    # LOG VALLEY SPLITS (with stability tracking)
    # =====================================================
    if VALLEY_ENABLED and valley_overlay_records:
        _valley_dets = [{
            'center_freq': vr['valley_freq'],
            'strength_db': vr['depth'],
            'gap_hz': vr['gap_hz'],
            'brown_left_freq': vr['brown_left_freq'],
            'brown_right_freq': vr['brown_right_freq'],
        } for vr in valley_overlay_records]
        _valley_stable = _valley_tracker.update(_valley_dets)
        if log_this_frame and log_win.isVisible():
            for _vs in _valley_stable:
                _tid_tag = f"T{_vs['track_id']}"
                _conf_tag = f"C:{_vs['confidence']:.0%}"
                log_win.append(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                    f"[CARRIER SPLIT] [{_tid_tag}|{_conf_tag}]  |  "
                    f"Valley: {_vs['center_freq']/1e6:.4f} MHz  |  "
                    f"Depth: {_vs['strength_db']:.1f} dB  |  "
                    f"Gap: {_vs['gap_hz']/1e3:.1f} kHz  |  "
                    f"Range: {_vs['brown_left_freq']/1e6:.4f}-"
                    f"{_vs['brown_right_freq']/1e6:.4f} MHz",
                    "#D2691E")
    elif VALLEY_ENABLED:
        # No valleys this frame — age out stale valley tracks
        _valley_tracker.update([])

    # =====================================================
    # DRAW UNAUTHORIZED CARRIERS (confirmed unauth, not authorized CF)
    # =====================================================
    RED_SHADES   = ["#ff6b6b", "#ff4757", "#ff6348", "#e84393", "#ff7f50"]
    unauth_count = 0

    if UNAUTH_ENABLED:
        for hit in confirmed_unauth_hits:
            # Skip if this hit's CF is authorized (already drawn as brown above)
            if has_auth_config and config_mgr.is_authorized(hit['f_center']):
                continue
            # Unauth cyan boundary lines (span already drawn as red above)
            ax.axvline(hit['f_start']/1e6, color="cyan", lw=1.2, ls="--", zorder=9)
            ax.axvline(hit['f_stop'] /1e6, color="cyan", lw=1.2, ls="--", zorder=9)
            unauth_count += 1
            if log_this_frame and log_win.isVisible():
                log_win.append(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                    f"[UNAUTH] #{unauth_count}  |  "
                    f"Freq: {hit['f_center']/1e6:.3f} MHz  |  "
                    f"Excess: +{hit['excess_db']:.1f} dB  |  "
                    f"BW: {hit['bw']/1e3:.1f} kHz  |  "
                    f"Trigger: {hit['trigger']}",
                    RED_SHADES[(unauth_count - 1) % len(RED_SHADES)])

            # Interference inside unauthorized carrier — highlight authorized signals inside it
            r_u, f_u = int(hit['r']), int(hit['f'])
            if INTF_ENABLED and (f_u - r_u) >= 6:
                unauth_intf_hits = detect_interference_in_carrier(
                    display_psd[r_u:f_u + 1], freq_axis[r_u:f_u + 1])
                gap_hits_u    = [h for h in unauth_intf_hits if h.get('is_gap', False)]
                nongap_hits_u = [h for h in unauth_intf_hits if not h.get('is_gap', False)]

                if nongap_hits_u:
                    ids_u    = min(h['start_freq'] for h in nongap_hits_u)
                    ide_u    = max(h['end_freq']   for h in nongap_hits_u)
                    center_u = 0.5 * (ids_u + ide_u)
                    best_u   = max(nongap_hits_u, key=lambda h: h['strength_db'])
                    if config_mgr.is_authorized(center_u):
                        ax.axvspan(ids_u/1e6, ide_u/1e6, color="green", alpha=0.45, zorder=9)
                        ax.text(center_u/1e6, Y_MAX - 10,
                                f"MASKED AUTH\n{best_u['strength_db']:.1f}dB",
                                ha="center", va="top", fontsize=7, color="white",
                                bbox=dict(boxstyle="round", fc="green", alpha=0.85), zorder=11)
                        if log_this_frame and log_win.isVisible():
                            log_win.append(
                                f"  └─ AUTH SIGNAL INSIDE UNAUTH CARRIER "
                                f"[{best_u['method'].upper()}]  |  "
                                f"Center: {center_u/1e6:.4f} MHz  |  "
                                f"BW: {(ide_u-ids_u)/1e3:.1f} kHz  |  "
                                f"Strength: +{best_u['strength_db']:.1f} dB  |  "
                                f"Range: {ids_u/1e6:.4f}-{ide_u/1e6:.4f} MHz",
                                "#ffd700")
                            log_win.append(
                                "      ↳ TYPE: AUTH SIGNAL INSIDE UNAUTH CARRIER", "#ffd700")

                for gh_u in gap_hits_u:
                    gcenter_u = 0.5 * (gh_u['start_freq'] + gh_u['end_freq'])
                    if config_mgr.is_authorized(gcenter_u):
                        ax.axvspan(gh_u['start_freq']/1e6, gh_u['end_freq']/1e6,
                                   color="green", alpha=0.55, zorder=9)
                        ax.axvline(gh_u['start_freq']/1e6, color="#66ff66", lw=1.5, ls="--", zorder=10)
                        ax.axvline(gh_u['end_freq']  /1e6, color="#66ff66", lw=1.5, ls="--", zorder=10)
                        ax.text(gcenter_u/1e6, Y_MAX - 16,
                                f"MASKED AUTH\n(GAP)\n{gh_u['strength_db']:.1f}dB",
                                ha="center", va="top", fontsize=7.5, color="#00ff7f",
                                fontweight="bold",
                                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.85), zorder=11)
                        if log_this_frame and log_win.isVisible():
                            log_win.append(
                                f"  └─ AUTH SIGNAL INSIDE UNAUTH CARRIER [GAP]  |  "
                                f"Center: {gcenter_u/1e6:.4f} MHz  |  "
                                f"BW: {(gh_u['end_freq']-gh_u['start_freq'])/1e3:.1f} kHz  |  "
                                f"Depth: {gh_u['strength_db']:.1f} dB  |  "
                                f"Range: {gh_u['start_freq']/1e6:.4f}-{gh_u['end_freq']/1e6:.4f} MHz",
                                "#ffd700")
                            log_win.append(
                                "      ↳ TYPE: AUTH SIGNAL INSIDE UNAUTH CARRIER", "#ffd700")

    if unauth_count == 0 and UNAUTH_ENABLED and has_auth_config:
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"No unauthorized carriers  |  Auth: {len(authorized_spans)}  |  "
                f"Raw: {len(all_unauth_hits)}  |  Pending: {len(_unauth_persistence)}",
                "#555555")

    if carrier_id == 0 and log_this_frame and log_win.isVisible():
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
            f"No carriers  |  Noise: {noise:.1f} dB  |  Threshold: {threshold:.1f} dB",
            "#808080")

    if log_this_frame:
        log_win._last_log_time = now

    fig.canvas.draw_idle()


# =========================
# START
# =========================
fetcher = DataFetcher()
fetcher.start()
print("[INFO] DataFetcher thread started.")

_render_timer = QtCore.QTimer()
_render_timer.timeout.connect(update)
_render_timer.start(33)

app = QApplication.instance()
sys.exit(app.exec_())