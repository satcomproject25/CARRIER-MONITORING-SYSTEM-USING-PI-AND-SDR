import zmq
import numpy as np
import matplotlib.pyplot as plt
import sys
import threading
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit, QPushButton, QLabel, QApplication)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
from scipy.signal import get_window
from matplotlib.widgets import CheckButtons, Button, TextBox
from datetime import datetime
import matplotlib
from matplotlib.widgets import Slider
import time

matplotlib.use("QtAgg")   # or "Qt5Agg"

# =========================
# CONFIG
# =========================
FFT_SIZE = 2048

# ---------------------------------------------------------
# HW_SAMPLE_RATE = actual ADC rate from hardware/metadata
#   → determines df (Hz per bin) → determines REAL BW
#   → this is the TREE'S REAL HEIGHT
#
# DISPLAY_BW = how much bandwidth you SHOW on screen
#   → only controls x-axis zoom (how far you stand)
#   → NEVER affects detection or BW calculation
# ---------------------------------------------------------
HW_SAMPLE_RATE = 20e6       # actual hardware rate — ONLY metadata changes this
DISPLAY_BW = 20e6           # view bandwidth (zoom) — text box changes this

HW_CENTER_FREQ = 70e6
DISPLAY_CENTER_FREQ = 70e6
CENTER_FREQ = 70e6

ZMQ_ADDR = "tcp://127.0.0.1:5555"
ZMQ_META_ADDR = "tcp://127.0.0.1:5556"

# Detection params in Hz (sample-rate-invariant)
'''Instead of smoothing over 1 bin (which is noisy),
you smooth over:5 bins≈ 48.8 kHz'''
SMOOTH_BW_HZ = 5 * (20e6 / 2048)      # ≈ 48.8 kHz
MIN_CARRIER_BW_HZ = 5 * (20e6 / 2048) # ≈ 48.8 kHz
THRESHOLD_RATIO = 0.35

Y_MIN = -70
Y_MAX = 80

# df always from HARDWARE rate — this is the "real ruler"
df = HW_SAMPLE_RATE / FFT_SIZE

# =========================
# ZMQ SETUP
# =========================
ctx = zmq.Context()

sock = ctx.socket(zmq.SUB)
sock.connect(ZMQ_ADDR)
sock.setsockopt(zmq.SUBSCRIBE, b"")
sock.setsockopt(zmq.CONFLATE, 1)   # always keep only latest frame
sock.setsockopt(zmq.RCVHWM, 1)
sock.setsockopt(zmq.LINGER, 0)

carrier_sock = ctx.socket(zmq.SUB)
carrier_sock.connect("tcp://127.0.0.1:5557")
carrier_sock.setsockopt(zmq.SUBSCRIBE, b"")
carrier_sock.setsockopt(zmq.CONFLATE, 1)   # ← NEW: drop stale carrier msgs
carrier_sock.setsockopt(zmq.RCVHWM, 1)     # ← NEW

meta_sock = ctx.socket(zmq.SUB)
meta_sock.connect(ZMQ_META_ADDR)
meta_sock.setsockopt(zmq.SUBSCRIBE, b"")
meta_sock.setsockopt(zmq.CONFLATE, 1)   # ← NEW: drop stale meta msgs
meta_sock.setsockopt(zmq.RCVHWM, 1)     # ← NEW

# =========================
# SHARED STATE (thread-safe)
# =========================
# The DataFetcher thread writes here; the render loop reads from here.
# Because we only ever store the LATEST value (not a queue), the render
# loop naturally skips stale frames — this is what kills the lag.

_state_lock = threading.Lock()

_latest_iq        = None   # np.ndarray or None
_latest_meta      = None   # dict or None
_latest_carriers  = None   # list or None


# =========================
# DATA FETCHER THREAD
# =========================
class DataFetcher(threading.Thread):
    """
    Runs in the background, polls ZMQ as fast as possible, and always
    keeps only the most-recent packet in each shared slot.
    The render loop picks up whatever is there when it fires — no queue,
    no backlog, no lag.
    """
    def __init__(self):
        super().__init__(daemon=True)   # killed automatically when main exits
        self._stop_event = threading.Event()

        # Private poller — only this thread touches it
        self._poller = zmq.Poller()
        self._poller.register(sock,         zmq.POLLIN)
        self._poller.register(meta_sock,    zmq.POLLIN)
        self._poller.register(carrier_sock, zmq.POLLIN)

    def stop(self):
        self._stop_event.set()

    def run(self):
        global _latest_iq, _latest_meta, _latest_carriers

        while not self._stop_event.is_set():
            # 10 ms poll timeout — tight loop without spinning the CPU at 100%
            events = dict(self._poller.poll(timeout=10))

            if not events:
                continue

            # --- IQ data ---
            if sock in events:
                data = sock.recv()
                iq = np.frombuffer(data, dtype=np.complex64)
                with _state_lock:
                    _latest_iq = iq.copy()   # copy so the buffer isn't re-used

            # --- Metadata ---
            if meta_sock in events:
                meta = meta_sock.recv_json()
                with _state_lock:
                    _latest_meta = meta

            # --- Carrier overlay data ---
            if carrier_sock in events:
                carriers = carrier_sock.recv_json()
                with _state_lock:
                    _latest_carriers = carriers


# =========================
# PLOT SETUP
# =========================
fig, ax = plt.subplots(figsize=(12, 6))
manager = plt.get_current_fig_manager()
manager.window.showMaximized()

plt.subplots_adjust(right=0.9, bottom=0.25)

def update_axis():
    """
    freq_axis + df always use HW_SAMPLE_RATE (the truth).
    x-axis DISPLAY limits use DISPLAY_BW (the zoom level).
    """
    global freq_axis, df

    # df from HARDWARE rate — never from display
    df = HW_SAMPLE_RATE / FFT_SIZE

    # freq_axis maps each bin to its TRUE frequency in Hz
    freq_axis = (
        np.arange(-FFT_SIZE // 2, FFT_SIZE // 2) * df
    ) + HW_CENTER_FREQ

    # x-axis limits = zoom window (how far you stand from the tree)
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
ax.set_title("Real-Time FFT Spectrum")

window     = get_window("hann", FFT_SIZE)
iq_buffer  = np.zeros(FFT_SIZE, dtype=np.complex64)

monitor_ax = plt.axes([0.02, 0.75, 0.3, 0.4])
monitor_ax.axis("off")
monitor_text = monitor_ax.text(
    0.0, 1.0, "",
    verticalalignment='top',
    fontsize=10,
    family='monospace'
)


# =====================================================
# LOG VIEWER WINDOW
# =====================================================
MAX_LOG_LINES    = 5000     # auto-trim after this many lines
LOG_THROTTLE_SEC = 0.5      # don't log faster than every 0.5 s

class LogWindow(QWidget):
    """Floating log window — open/close via View Log button."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Carrier Detection Log")
        self.setWindowFlags(Qt.Window | Qt.WindowMinimizeButtonHint |
                            Qt.WindowMaximizeButtonHint | Qt.WindowCloseButtonHint)
        self.resize(700, 420)

        layout = QVBoxLayout(self)

        # --- header bar ---
        hdr = QHBoxLayout()
        title = QLabel("CARRIER DETECTION LOG")
        title.setFont(QFont("Segoe UI", 11, QFont.Bold))
        hdr.addWidget(title)
        hdr.addStretch()

        self.line_count_label = QLabel("Lines: 0")
        self.line_count_label.setFont(QFont("Consolas", 9))
        hdr.addWidget(self.line_count_label)

        self.autoscroll_on = True
        self.btn_autoscroll = QPushButton("Auto-scroll: ON")
        self.btn_autoscroll.setFixedWidth(120)
        self.btn_autoscroll.clicked.connect(self._toggle_autoscroll)
        hdr.addWidget(self.btn_autoscroll)

        btn_clear = QPushButton("Clear")
        btn_clear.setFixedWidth(60)
        btn_clear.clicked.connect(self.clear_log)
        hdr.addWidget(btn_clear)

        layout.addLayout(hdr)

        # --- log text area ---
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setFont(QFont("Consolas", 10))
        self.text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "border: 1px solid #3c3c3c; }"
        )
        layout.addWidget(self.text)

        self._line_count    = 0
        self._last_log_time = 0.0

    def append(self, msg, color="#d4d4d4"):
        self.text.setTextColor(QColor(color))
        self.text.append(msg)
        self._line_count += msg.count('\n') + 1
        self.line_count_label.setText(f"Lines: {self._line_count}")

        if self._line_count > MAX_LOG_LINES:
            self._trim()

        if self.autoscroll_on:
            sb = self.text.verticalScrollBar()
            sb.setValue(sb.maximum())

    def clear_log(self):
        self.text.clear()
        self._line_count = 0
        self.line_count_label.setText("Lines: 0")

    def _toggle_autoscroll(self):
        self.autoscroll_on = not self.autoscroll_on
        self.btn_autoscroll.setText(
            "Auto-scroll: ON" if self.autoscroll_on else "Auto-scroll: OFF"
        )

    def _trim(self):
        """Keep only the last MAX_LOG_LINES/2 lines."""
        doc    = self.text.document()
        cursor = self.text.textCursor()
        cursor.movePosition(cursor.Start)
        half = doc.blockCount() // 2
        for _ in range(half):
            cursor.movePosition(cursor.Down, cursor.KeepAnchor)
        cursor.removeSelectedText()
        cursor.deleteChar()
        self._line_count = doc.blockCount()
        self.line_count_label.setText(f"Lines: {self._line_count}")

    def closeEvent(self, event):
        """Hide instead of destroy so we can reopen."""
        self.hide()
        event.ignore()


# Create the log window (hidden by default)
log_win = LogWindow()
log_win.append(
    f"[{datetime.now().strftime('%H:%M:%S')}] Log started  |  "
    f"HW SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  "
    f"FFT: {FFT_SIZE}  |  "
    f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz",
    "#569cd6"
)


# =====================================================
# CONTROL PANEL — MAX HOLD / MIN HOLD
# =====================================================
max_hold       = np.full(FFT_SIZE, -np.inf)
min_hold       = np.full(FFT_SIZE,  np.inf)
enable_max_hold = False
enable_min_hold = False

rax   = plt.axes([0.915, 0.65, 0.09, 0.1])
check = CheckButtons(rax, ["MAX HOLD", "MIN HOLD"], [False, False])

def toggle_hold(label):
    global enable_max_hold, enable_min_hold
    if label == "MAX HOLD":
        enable_max_hold = not enable_max_hold
    if label == "MIN HOLD":
        enable_min_hold = not enable_min_hold

check.on_clicked(toggle_hold)

reset_ax  = plt.axes([0.92, 0.58, 0.1, 0.05])
reset_btn = Button(reset_ax, "Reset Hold")

def reset_hold(event):
    global max_hold, min_hold
    max_hold[:] = -np.inf
    min_hold[:] =  np.inf

reset_btn.on_clicked(reset_hold)


# =====================================================
# CONTROL PANEL — SMOOTH
# =====================================================
smooth_enabled = False
smooth_alpha   = 0.0
psd_avg        = None

smooth_ax  = plt.axes([0.92, 0.53, 0.1, 0.05])
smooth_btn = Button(smooth_ax, "Smooth OFF")

def toggle_smooth(event):
    global smooth_enabled
    smooth_enabled = not smooth_enabled
    smooth_btn.label.set_text("Smooth ON" if smooth_enabled else "Smooth OFF")

smooth_btn.on_clicked(toggle_smooth)

slider_ax    = plt.axes([0.15, 0.02, 0.5, 0.03])
smooth_slider = Slider(slider_ax, "Smooth", 0.0, 1.0, valinit=0.0)

def update_smooth(val):
    global smooth_alpha
    smooth_alpha = val

smooth_slider.on_changed(update_smooth)


# =====================================================
# CONTROL PANEL — TEXT BOXES (Center Freq / BW / FFT)
# =====================================================
ax_freq = plt.axes([0.1,  0.1, 0.2,  0.05])
tb_freq = TextBox(ax_freq, "Center Freq (Hz)", initial=str(CENTER_FREQ))

ax_sr   = plt.axes([0.45, 0.1, 0.15, 0.05])
tb_sr   = TextBox(ax_sr, "Sample rate (Hz)", initial=str(DISPLAY_BW))

ax_fft  = plt.axes([0.7,  0.1, 0.1,  0.05])
tb_fft  = TextBox(ax_fft, "FFT", initial=str(FFT_SIZE))

def update_freq(text):
    global DISPLAY_CENTER_FREQ
    DISPLAY_CENTER_FREQ = float(text)
    update_axis()

def update_display_bw(text):
    """
    Only changes ZOOM level (how far you stand from the tree).
    Does NOT change df, freq_axis, or detection — the tree's
    real height stays the same.
    """
    global DISPLAY_BW
    DISPLAY_BW = float(text)
    ax.set_xlim(
        (DISPLAY_CENTER_FREQ - DISPLAY_BW / 2) / 1e6,
        (DISPLAY_CENTER_FREQ + DISPLAY_BW / 2) / 1e6
    )

def update_fft(text):
    global FFT_SIZE, max_hold, min_hold, window, iq_buffer
    FFT_SIZE  = int(text)
    update_axis()
    window    = get_window("hann", FFT_SIZE)
    iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
    max_hold  = np.full(FFT_SIZE, -np.inf)
    min_hold  = np.full(FFT_SIZE,  np.inf)
    line_live.set_xdata(freq_axis / 1e6)
    line_max.set_xdata(freq_axis / 1e6)
    line_min.set_xdata(freq_axis / 1e6)

tb_freq.on_submit(update_freq)
tb_sr.on_submit(update_display_bw)
tb_fft.on_submit(update_fft)


# =====================================================
# MARKER SYSTEM
# =====================================================
MARKER_COLORS = {
    1: "#ff4c4c",   # red
    2: "#4ec9b0",   # cyan
    3: "#c586c0"    # violet
}

class Marker:
    def __init__(self, idx):
        self.idx      = idx
        self.mode     = "off"   # off / normal / peak / delta
        self.point_a  = None
        self.point_b  = None
        self.artist_a = None
        self.artist_b = None
        self.text     = None

markers = {
    1: Marker(1),
    2: Marker(2),
    3: Marker(3)
}

markers_global_on      = True
cursor_ghost           = None
CLICK_REMOVE_THRESH_MHZ = 0.3

marker_onoff_ax  = plt.axes([0.92, 0.48, 0.1, 0.05])
marker_onoff_btn = Button(marker_onoff_ax, "Markers: ON")

m1_btn_ax = plt.axes([0.92, 0.425, 0.1, 0.04])
m1_btn    = Button(m1_btn_ax, "M1: OFF")

m2_btn_ax = plt.axes([0.92, 0.38, 0.1, 0.04])
m2_btn    = Button(m2_btn_ax, "M2: OFF")

m3_btn_ax = plt.axes([0.92, 0.335, 0.1, 0.04])
m3_btn    = Button(m3_btn_ax, "M3: OFF")

def _freq_snap(x_mhz):
    """Snap x (in MHz) to nearest freq_axis point, return (freq_hz, power_dB)."""
    x_hz  = x_mhz * 1e6
    idx   = np.argmin(np.abs(freq_axis - x_hz))
    ydata = line_live.get_ydata()
    return freq_axis[idx], ydata[idx]

def _is_near_existing(m, x_mhz, thresh=CLICK_REMOVE_THRESH_MHZ):
    if m.point_a is not None:
        if abs(m.point_a[0] / 1e6 - x_mhz) < thresh:
            return 'a'
    if m.point_b is not None:
        if abs(m.point_b[0] / 1e6 - x_mhz) < thresh:
            return 'b'
    return None

def on_click(event):
    global selected_marker_id

    if not markers_global_on:
        return
    if event.inaxes != ax:
        return
    if event.button != 1:
        return
    if selected_marker_id is None:
        return

    m = markers[selected_marker_id]   # only the selected marker responds

    if m.mode == "off" or m.mode == "peak":
        return                        # safety guard; shouldn't be selected

    x_mhz  = event.xdata
    fx, py = _freq_snap(x_mhz)

    if m.mode == "normal":
        near = _is_near_existing(m, x_mhz)
        if near == 'a':
            m.point_a = None
        else:
            m.point_a = (fx, py)

    elif m.mode == "delta":
        near = _is_near_existing(m, x_mhz)
        if near == 'a':
            m.point_a = None
        elif near == 'b':
            m.point_b = None
        elif m.point_a is None:
            m.point_a = (fx, py)
        elif m.point_b is None:
            m.point_b = (fx, py)
        else:
            # Both placed — re-anchor point_a to the new click
            m.point_a = (fx, py)
            m.point_b = None

fig.canvas.mpl_connect("button_press_event", on_click)

def on_mouse_move(event):
    global cursor_ghost
    if cursor_ghost is not None:
        try:
            cursor_ghost.remove()
        except Exception:
            pass
        cursor_ghost = None

    if not markers_global_on:
        fig.canvas.draw_idle()
        return
    if event.inaxes != ax:
        fig.canvas.draw_idle()
        return

    active = any(m.mode in ("normal", "delta") for m in markers.values())
    if not active:
        fig.canvas.draw_idle()
        return

    fx, py = _freq_snap(event.xdata)
    cursor_ghost = ax.scatter(
        fx / 1e6, py,
        marker="+",
        s=120,
        color="white",
        linewidths=1.5,
        zorder=25
    )
    fig.canvas.draw_idle()

fig.canvas.mpl_connect("motion_notify_event", on_mouse_move)

_marker_mode_cycle  = ["off", "normal", "peak", "delta"]
_marker_btn_map     = {1: m1_btn, 2: m2_btn, 3: m3_btn}
_marker_mode_labels = {"off": "OFF", "normal": "Normal", "peak": "Peak", "delta": "Delta"}

def _make_toggle_marker(idx):
    def toggle(event):
        global selected_marker_id

        if not markers_global_on:
            return

        m   = markers[idx]
        cur = _marker_mode_cycle.index(m.mode)
        m.mode = _marker_mode_cycle[(cur + 1) % len(_marker_mode_cycle)]

        if m.mode in ("off", "peak"):
            # peak is auto-tracking, needs no click; off means deselect
            m.point_a = None
            m.point_b = None
            # Release selection only if THIS marker held it
            if selected_marker_id == idx:
                selected_marker_id = None
        else:
            # "normal" or "delta" — this marker now owns the cursor
            selected_marker_id = idx

        btn = _marker_btn_map[idx]
        btn.label.set_text(f"M{idx}: {_marker_mode_labels[m.mode]}")
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
        selected_marker_id = None          # ← release selection
        for m in markers.values():
            m.point_a = None
            m.point_b = None
        if cursor_ghost is not None:
            try:
                cursor_ghost.remove()
            except Exception:
                pass
            cursor_ghost = None

    fig.canvas.draw_idle()

marker_onoff_btn.on_clicked(toggle_markers_global)


# =====================================================
# VIEW LOG BUTTON
# =====================================================
log_btn_ax = plt.axes([0.92, 0.285, 0.1, 0.04])
log_btn    = Button(log_btn_ax, "View Log")

def toggle_log(event):
    if log_win.isVisible():
        log_win.hide()
    else:
        log_win.show()
        log_win.raise_()
        log_win.activateWindow()

log_btn.on_clicked(toggle_log)


plt.show(block=False)
print("[INFO] GUI running...")


# =========================
# UPDATE FUNCTION
# (called by QTimer — reads from shared state, never touches ZMQ)
# =========================
def update():
    """
    Render the latest data that the DataFetcher thread has collected.

    Design contract
    ---------------
    * Grab-and-clear each shared slot under the lock — one atomic swap.
    * If no IQ arrived since the last render tick, do nothing (skip frame).
    * Because CONFLATE=1 is set on all sockets AND the thread always
      overwrites (never appends), this function can never build a backlog.
    """
    global _latest_iq, _latest_meta, _latest_carriers
    global HW_SAMPLE_RATE, FFT_SIZE, HW_CENTER_FREQ
    global window, iq_buffer, max_hold, min_hold
    global psd_avg, smooth_enabled, smooth_alpha

    # ── atomic snapshot ──────────────────────────────────────────────────
    with _state_lock:
        iq_frame       = _latest_iq
        meta_frame     = _latest_meta
        carrier_frame  = _latest_carriers
        # Clear so we don't re-process on the next tick if nothing new arrives
        _latest_iq       = None
        _latest_meta     = None
        _latest_carriers = None

    # ─────────────────────────────────────────────────────────────────────
    # METADATA UPDATE
    # ─────────────────────────────────────────────────────────────────────
    if meta_frame is not None:
        HW_SAMPLE_RATE = meta_frame["rate"]
        FFT_SIZE       = meta_frame["fft"]
        HW_CENTER_FREQ = meta_frame["cf"]

        window    = get_window("hann", FFT_SIZE)
        iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
        max_hold  = np.full(FFT_SIZE, -np.inf)
        min_hold  = np.full(FFT_SIZE,  np.inf)

        update_axis()
        line_live.set_xdata(freq_axis / 1e6)
        line_max.set_xdata(freq_axis / 1e6)
        line_min.set_xdata(freq_axis / 1e6)

        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] META UPDATE  |  "
            f"SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  "
            f"FFT: {FFT_SIZE}  |  "
            f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz",
            "#dcdcaa"
        )

    # ─────────────────────────────────────────────────────────────────────
    # IQ DATA — bail early if nothing new
    # ─────────────────────────────────────────────────────────────────────
    if iq_frame is None:
        return   # ← no draw, no lag

    iq = iq_frame
    if len(iq) >= FFT_SIZE:
        iq_buffer[:] = iq[:FFT_SIZE]
    else:
        return

    # ─────────────────────────────────────────────────────────────────────
    # FFT → PSD
    # ─────────────────────────────────────────────────────────────────────
    spectrum = np.fft.fftshift(np.fft.fft(iq_buffer * window))
    psd      = 20 * np.log10(np.abs(spectrum) + 1e-12)
    psd     += np.random.normal(0, 3, len(psd))

    # ─────────────────────────────────────────────────────────────────────
    # SMOOTH
    # ─────────────────────────────────────────────────────────────────────
    if psd_avg is None:
        psd_avg = psd.copy()

    if smooth_enabled:
        alpha   = 1 - (1 - smooth_alpha) ** 2
        psd_avg = alpha * psd_avg + (1 - alpha) * psd
        display_psd = psd_avg
    else:
        display_psd = psd

    line_live.set_ydata(display_psd)

    # ─────────────────────────────────────────────────────────────────────
    # MAX / MIN HOLD
    # ─────────────────────────────────────────────────────────────────────
    if enable_max_hold:
        max_hold = np.maximum(max_hold, psd)
    if enable_min_hold:
        min_hold = np.minimum(min_hold, psd)

    line_max.set_ydata(max_hold)
    line_min.set_ydata(min_hold)

    # ─────────────────────────────────────────────────────────────────────
    # CARRIER SOCKET OVERLAY (external data)
    # ─────────────────────────────────────────────────────────────────────
    if carrier_frame is not None:
        display_text = "ACTIVE CARRIERS\n\n"
        if not carrier_frame:
            display_text += "None detected"
        else:
            for c in carrier_frame:
                display_text += (
                    f"ID {c['id']}\n"
                    f"Freq : {c['freq']/1e6:.3f} MHz\n"
                    f"BW   : {c['bw']/1e3:.1f} kHz\n"
                    f"Pwr  : {c['power']:.1f} dB\n"
                    "---------------------\n"
                )
        monitor_text.set_text(display_text)

    # ─────────────────────────────────────────────────────────────────────
    # CLEAR OVERLAYS
    # ─────────────────────────────────────────────────────────────────────
    for patch in ax.patches[:]:
        patch.remove()
    for txt in ax.texts[:]:
        txt.remove()
    for l in ax.lines[3:]:
        l.remove()

    # =====================================================
    # CARRIER DETECTION — SAMPLE-RATE-INVARIANT
    # =====================================================
    smooth_taps = max(3, int(round(SMOOTH_BW_HZ / df))) | 1
    min_bins    = max(2, int(round(MIN_CARRIER_BW_HZ / df)))

    psd_s     = np.convolve(display_psd, np.ones(smooth_taps) / smooth_taps, mode="same")
    noise     = np.median(psd_s)
    peak      = np.max(psd_s)
    threshold = noise + THRESHOLD_RATIO * (peak - noise)

    above  = psd_s > threshold
    edges  = np.diff(above.astype(np.int8))
    rises  = np.where(edges == 1)[0]
    falls  = np.where(edges == -1)[0]

    if len(falls) > 0 and (len(rises) == 0 or falls[0] < rises[0]):
        rises = np.insert(rises, 0, 0)
    if len(rises) > 0 and (len(falls) == 0 or rises[-1] > falls[-1]):
        falls = np.append(falls, FFT_SIZE - 1)

    # =====================================================
    # UPDATE MARKERS
    # =====================================================
    def safe_remove(obj):
        try:
            if obj is not None:
                obj.remove()
        except Exception:
            pass
        return None

    for m in markers.values():
        m.artist_a = safe_remove(m.artist_a)
        m.artist_b = safe_remove(m.artist_b)
        m.text     = safe_remove(m.text)

        if not markers_global_on:
            continue

        color = MARKER_COLORS[m.idx]

        if m.mode == "peak":
            peak_idx   = np.argmax(display_psd)
            peak_freq  = freq_axis[peak_idx]
            peak_power = display_psd[peak_idx]
            m.point_a  = (peak_freq, peak_power)

        if m.point_a:
            fx, py = m.point_a
            if m.mode == "normal":
                bin_idx   = np.argmin(np.abs(freq_axis - fx))
                py        = display_psd[bin_idx]
                m.point_a = (fx, py)

            m.artist_a = ax.scatter(fx / 1e6, py, marker="D", s=80, color=color, zorder=20)
            label      = f"M{m.idx}\n{fx/1e6:.3f} MHz\n{py:.1f} dB"

            # Inside the marker drawing loop in update(), replace the delta label block:
            if m.mode == "delta" and m.point_a and m.point_b:
                fx2, py2   = m.point_b
                m.artist_b = ax.scatter(fx2 / 1e6, py2, marker="D", s=80, color=color, zorder=20)
                delta_f    = abs(fx - fx2) / 1e6
                delta_p    = abs(py - py2)
                label     += f"\nΔf: {delta_f:.3f} MHz\nΔP: {delta_p:.1f} dB"
            elif m.mode == "delta" and m.point_a and not m.point_b:
                label += "\n[click ref point]"    # visual hint that point_b is pending

            m.text = ax.text(
                fx / 1e6, py + 3, label,
                color=color, fontsize=9,
                bbox=dict(fc="black", alpha=0.6),
                zorder=21
            )

    # =====================================================
    # DRAW DETECTED CARRIERS + LOG
    # =====================================================
    now           = time.time()
    log_this_frame = (now - log_win._last_log_time) >= LOG_THROTTLE_SEC
    carrier_id    = 0
    GREEN_SHADES  = ["#4ec9b0", "#6abf69", "#98e898", "#00ff7f", "#b2fab4"]

    for r, f in zip(rises, falls):
        bins = f - r
        if bins < min_bins:
            continue

        carrier_peak  = np.max(psd_s[r:f+1])
        low_level     = noise + 0.1 * (carrier_peak - noise)
        high_level    = noise + 0.9 * (carrier_peak - noise)

        # ---- Rising Transition Width ----
        rise_start = r
        while rise_start > 1 and psd_s[rise_start] > low_level:
            rise_start -= 1
        rise_end = r
        while rise_end < f and psd_s[rise_end] < high_level:
            rise_end += 1
        rise_width_bins = rise_end - rise_start

        # ---- Falling Transition Width ----
        fall_start = f
        while fall_start > r and psd_s[fall_start] > high_level:
            fall_start -= 1
        fall_end = f
        while fall_end < FFT_SIZE - 2 and psd_s[fall_end] > low_level:
            fall_end += 1
        fall_width_bins = fall_end - fall_start

        transition_bins = max(rise_width_bins, fall_width_bins)
        transition_bw   = transition_bins * df

        HIGHLIGHT_MARGIN = 100e3 if transition_bw > 150e3 else 60e3

        f_start = freq_axis[r] - HIGHLIGHT_MARGIN
        f_stop  = freq_axis[min(f, FFT_SIZE - 1)] + HIGHLIGHT_MARGIN

        bw       = f_stop - f_start
        f_center = 0.5 * (f_start + f_stop)

        carrier_peak_pwr    = np.max(display_psd[r:f+1])
        lin_power           = np.sum(10 ** (display_psd[r:f+1] / 10))
        carrier_total_power_db = 10 * np.log10(lin_power + 1e-12)

        bins_in_carrier  = f - r + 1
        noise_linear     = np.median(10 ** (display_psd / 10))
        noise_total_db   = 10 * np.log10(noise_linear * bins_in_carrier + 1e-12)
        cn_db            = carrier_total_power_db - noise_total_db

        ax.axvspan(f_start / 1e6, f_stop / 1e6, color="green", alpha=0.25)
        ax.axvline(f_start / 1e6, color="orange")
        ax.axvline(f_stop  / 1e6, color="orange")
        ax.text(
            f_center / 1e6, Y_MAX - 5,
            f"{bw/1e3:.0f} kHz",
            ha="center", va="top",
            bbox=dict(boxstyle="round", fc="white", alpha=0.8)
        )

        carrier_id += 1
        if log_this_frame and log_win.isVisible():
            color = GREEN_SHADES[(carrier_id - 1) % len(GREEN_SHADES)]
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"Carrier {carrier_id}  |  "
                f"Freq: {f_center/1e6:.3f} MHz  |  "
                f"Total Power: {carrier_total_power_db:.1f} dB  |  "
                f"BW: {bw/1e3:.1f} kHz  |  "
                f"Peak: {carrier_peak_pwr:.1f} dB  |  "
                f"Noise: {noise:.1f} dB  |  "
                f"Range: {f_start/1e6:.3f}–{f_stop/1e6:.3f} MHz |"
                f"C/N:{cn_db:.2f}db |",
                color
            )

    if carrier_id == 0 and log_this_frame and log_win.isVisible():
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
            f"No carriers  |  Noise: {noise:.1f} dB  |  Threshold: {threshold:.1f} dB",
            "#808080"
        )

    if log_this_frame:
        log_win._last_log_time = now

    # ─────────────────────────────────────────────────────────────────────
    # DRAW  (draw_idle schedules one redraw per event-loop cycle —
    #        far cheaper than fig.canvas.draw() which forces a synchronous flush)
    # ─────────────────────────────────────────────────────────────────────
    fig.canvas.draw_idle()


# =========================
# START DATA FETCHER THREAD
# =========================
fetcher = DataFetcher()
fetcher.start()
print("[INFO] DataFetcher thread started.")

# =========================
# START RENDER TIMER
# =========================
# QTimer fires in the Qt event loop — it will simply skip ticks if the
# previous render is still executing, so it CANNOT build a backlog.
# 33 ms ≈ 30 fps; lower for faster refresh, higher to reduce CPU load.
_render_timer = QtCore.QTimer()
_render_timer.timeout.connect(update)
_render_timer.start(33)   # ms

# Grab the Qt app that matplotlib already created and enter its event loop.
app = QApplication.instance()
sys.exit(app.exec_())