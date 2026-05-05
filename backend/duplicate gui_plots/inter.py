import zmq
import numpy as np
import matplotlib.pyplot as plt
import sys
import threading
from PyQt5 import QtCore
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QTextEdit,
                              QPushButton, QLabel, QApplication)
from PyQt5.QtGui import QFont, QColor
from PyQt5.QtCore import Qt
from scipy.signal import get_window, savgol_filter
from scipy.ndimage import minimum_filter1d, uniform_filter1d, median_filter
from matplotlib.widgets import CheckButtons, Button, TextBox
from datetime import datetime
import matplotlib
from matplotlib.widgets import Slider
from matplotlib.colors import Normalize
import time
from config_manager import AuthorizedFrequencyManager
config_mgr = AuthorizedFrequencyManager()
matplotlib.use("QtAgg")

# =========================
# CONFIG
# =========================
FFT_SIZE = 2048

HW_SAMPLE_RATE = 20e6
DISPLAY_BW = 20e6

HW_CENTER_FREQ = 70e6
DISPLAY_CENTER_FREQ = 70e6
CENTER_FREQ = 70e6

# zmq address link with the zmq block and the python script
ZMQ_ADDR = "tcp://127.0.0.1:5555"
ZMQ_META_ADDR = "tcp://127.0.0.1:5556"


# ═════════════════════════════════════════════════════════════════════════════
# v3 ADAPTIVE LOCAL NOISE FLOOR — CONFIGURATION
# ═════════════════════════════════════════════════════════════════════════════

# ── Morphological noise floor ───────────────────────────────────────────────
MORPH_MIN_WINDOW_BINS  = 101
MORPH_SMOOTH_WINDOW    = 51
LOCAL_SIGMA_WINDOW     = 201
MORPH_GUARD_DB         = 2.0

# ── Carrier detection ───────────────────────────────────────────────────────
CARRIER_SIGNAL_K       = 4.0
CARRIER_MIN_MARGIN_DB  = 3.0
CARRIER_MIN_BW_HZ      = 5 * (20e6 / 2048)
CARRIER_SMOOTH_BW_HZ   = 5 * (20e6 / 2048)

# ── Simple threshold-crossing params ─────────────────────────────────────────
SMOOTH_BW_HZ      = CARRIER_SMOOTH_BW_HZ
MIN_CARRIER_BW_HZ = CARRIER_MIN_BW_HZ
THRESHOLD_RATIO   = 0.35

# ── Carrier persistence ─────────────────────────────────────────────────────
CARRIER_PERSIST_FRAMES = 5
CARRIER_BUCKET_HZ      = 50e3

# ── Interference persistence ─────────────────────────────────────────────────
INTF_PERSIST_FRAMES    = 2

# ── Waterfall ─────────────────────────────────────────────────────────────────
WATERFALL_ROWS         = 200
WATERFALL_CMAP         = "inferno"
WATERFALL_VMIN         = -60
WATERFALL_VMAX         = 40

# ── Persistence state ─────────────────────────────────────────────────────────
_carrier_persistence: dict = {}
_intf_persistence:    dict = {}

# ── Advanced detector state ───────────────────────────────────────────────────
_psd_reference: np.ndarray = None          # slowly-updated reference spectrum
_psd_reference_init: bool  = False         # True once first clean frame stored
ML_HISTORY_LEN             = 50
_ml_history_buffer: list   = []            # rolling list of last N PSD frames

# ── Advanced detector thresholds ──────────────────────────────────────────────
KURTOSIS_DEVIATION_THRESH  = 0.5           # |K-3| threshold
PSD_RATIO_THRESH_DB        = 6.0           # dB above reference to flag spur
PSD_REF_ALPHA              = 0.01          # EMA update weight for reference
MER_THRESHOLD_DB           = 28.0          # MER below this → flag
ML_ANOMALY_THRESH_DB       = 4.0           # RMS deviation threshold
EBNO_MIN_DB                = 8.0           # Eb/No floor for divergence check


# ═════════════════════════════════════════════════════════════════════════════
# STEP 1 — LOCAL MORPHOLOGICAL NOISE FLOOR ESTIMATION
# ═════════════════════════════════════════════════════════════════════════════

def estimate_local_noise_floor(psd_s):
    N = len(psd_s)
    local_min = minimum_filter1d(psd_s, size=MORPH_MIN_WINDOW_BINS, mode='reflect')
    noise_baseline = uniform_filter1d(local_min, size=MORPH_SMOOTH_WINDOW, mode='reflect')
    noise_baseline += MORPH_GUARD_DB
    residual     = psd_s - noise_baseline
    abs_residual = np.abs(residual)
    local_mad    = median_filter(abs_residual, size=LOCAL_SIGMA_WINDOW, mode='reflect')
    noise_sigma  = np.maximum(1.4826 * local_mad, 0.3)
    threshold  = noise_baseline + CARRIER_SIGNAL_K * noise_sigma
    noise_mask = psd_s <= threshold
    noise_scalar = float(np.median(noise_baseline))
    return noise_baseline, noise_sigma, noise_scalar, noise_mask


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2 — STRUCTURAL CARRIER DETECTION
# ═════════════════════════════════════════════════════════════════════════════

def detect_carriers_structural(psd_s, noise_baseline, noise_sigma,
                                noise_mask, df, fft_size):
    min_bins = max(2, int(round(CARRIER_MIN_BW_HZ / df)))
    threshold   = noise_baseline + CARRIER_SIGNAL_K * noise_sigma
    signal_mask = psd_s > threshold
    padded = np.concatenate([[False], signal_mask, [False]])
    diff   = np.diff(padded.astype(np.int8))
    starts = np.where(diff == 1)[0]
    ends   = np.where(diff == -1)[0]
    carriers      = []
    interferences = []
    for s, e in zip(starts.tolist(), ends.tolist()):
        width = e - s
        if width < min_bins:
            continue
        region_peak = float(np.max(psd_s[s:e]))
        peak_bin    = s + int(np.argmax(psd_s[s:e]))
        local_floor = float(noise_baseline[peak_bin])
        if (region_peak - local_floor) < CARRIER_MIN_MARGIN_DB:
            continue
        left_touches_noise  = (s == 0) or noise_mask[s - 1]
        right_touches_noise = (e >= fft_size) or noise_mask[min(e, fft_size - 1)]
        if left_touches_noise and right_touches_noise:
            carriers.append((s, e - 1))
        else:
            interferences.append((s, e - 1))
    return carriers, interferences


# ═════════════════════════════════════════════════════════════════════════════
# STEP 2b — CARRIER PERSISTENCE FILTER
# ═════════════════════════════════════════════════════════════════════════════

def apply_carrier_persistence(detected_spans, freq_axis):
    global _carrier_persistence
    current_buckets = set()
    for r, f in detected_spans:
        center_freq = 0.5 * (freq_axis[r] + freq_axis[min(f, len(freq_axis) - 1)])
        bucket = int(round(center_freq / CARRIER_BUCKET_HZ))
        current_buckets.add(bucket)
        if bucket in _carrier_persistence:
            _carrier_persistence[bucket]["count"] = CARRIER_PERSIST_FRAMES
            _carrier_persistence[bucket]["span"]  = (r, f)
        else:
            _carrier_persistence[bucket] = {
                "span": (r, f), "count": CARRIER_PERSIST_FRAMES,
            }
    for bucket in list(_carrier_persistence):
        if bucket not in current_buckets:
            _carrier_persistence[bucket]["count"] -= 1
            if _carrier_persistence[bucket]["count"] <= 0:
                del _carrier_persistence[bucket]
    return [data["span"] for data in _carrier_persistence.values()]


# ═════════════════════════════════════════════════════════════════════════════
# INTERFERENCE PERSISTENCE FILTER
# ═════════════════════════════════════════════════════════════════════════════

def apply_intf_persistence(all_hits):
    global _intf_persistence
    confirmed       = []
    hits_this_frame = set()
    for hit in all_hits:
        bucket = int(round(hit['f_center'] / 50e3))
        hits_this_frame.add(bucket)
        _intf_persistence[bucket] = _intf_persistence.get(bucket, 0) + 1
        if _intf_persistence[bucket] >= INTF_PERSIST_FRAMES:
            confirmed.append(hit)
    for key in list(_intf_persistence):
        if key not in hits_this_frame:
            del _intf_persistence[key]
    return confirmed


# ═════════════════════════════════════════════════════════════════════════════
# INTRA-CARRIER SHAPE ANOMALY DETECTOR  (±2 dB envelope deviation)
#
# For each authorized carrier:
#   1. Extract carrier region
#   2. Skip first/last 10% (rolloff shoulders)
#   3. Build a smoothed reference envelope (uniform_filter1d, 21-tap)
#   4. Compute residual = actual − envelope
#   5. Flag contiguous bins where |residual| > 2 dB
#   6. Return only those flagged regions
# Detects: carrier-inside-carrier, shoulder bumps, plateau distortion,
#          asymmetric shape, spectral humps — without triggering on rolloff.
# ═════════════════════════════════════════════════════════════════════════════

SHAPE_DEVIATION_DB     = 2.5     # ±dB threshold for envelope deviation
SHAPE_MIN_BINS         = 3       # minimum contiguous bins to count as hit
SHAPE_EDGE_SKIP_RATIO  = 0.10   # skip 10% of carrier edges (rolloff)
SHAPE_SMOOTH_TAPS      = 21     # envelope smoothing kernel size
SHAPE_PERSIST_FRAMES   = 2      # frames before confirming a shape hit

_shape_persistence: dict = {}


def detect_center_shape_anomaly(psd, freq_axis, r, f, noise_floor):
    """
    Detect intra-carrier interference by looking for ±2 dB deviations
    from the expected smoothed carrier shape.
    """
    hits = []
    r = int(r)
    f = int(f)
    width = f - r + 1

    if width < 30:
        return hits

    # Skip rolloff edges
    edge_skip   = int(width * SHAPE_EDGE_SKIP_RATIO)
    inner_start = r + edge_skip
    inner_end   = f - edge_skip

    segment = psd[inner_start:inner_end + 1].astype(np.float64)

    # Smoothed reference envelope
    kern = min(SHAPE_SMOOTH_TAPS, len(segment))
    if kern % 2 == 0:
        kern -= 1
    kern = max(kern, 3)
    smooth = uniform_filter1d(segment, size=kern)

    residual = segment - smooth

    # ±2 dB threshold
    anomaly_mask = np.abs(residual) > SHAPE_DEVIATION_DB

    # Find contiguous anomaly regions
    pad  = np.concatenate(([False], anomaly_mask, [False]))
    diff = np.diff(pad.astype(np.int8))
    starts = np.where(diff == 1)[0]
    ends   = np.where(diff == -1)[0]

    for s, e in zip(starts, ends):
        if (e - s) < SHAPE_MIN_BINS:
            continue

        abs_start = inner_start + s
        abs_end   = inner_start + e - 1

        peak    = float(np.max(psd[abs_start:abs_end + 1]))
        excess  = float(np.max(np.abs(residual[s:e])))

        fs = float(freq_axis[abs_start])
        fe = float(freq_axis[abs_end])

        hits.append({
            'r': abs_start,
            'f': abs_end,
            'f_start': fs,
            'f_stop': fe,
            'f_center': 0.5 * (fs + fe),
            'bw': fe - fs,
            'peak_pwr': peak,
            'excess_db': excess,
            'trigger': 'SHAPE-2DB',
            'local_noise': noise_floor,
        })

    return hits


def apply_shape_persistence(all_hits):
    """Persistence filter for shape anomaly hits (separate from unauthorized)."""
    global _shape_persistence
    confirmed       = []
    hits_this_frame = set()
    for hit in all_hits:
        bucket = int(round(hit['f_center'] / 50e3))
        hits_this_frame.add(bucket)
        _shape_persistence[bucket] = _shape_persistence.get(bucket, 0) + 1
        if _shape_persistence[bucket] >= SHAPE_PERSIST_FRAMES:
            confirmed.append(hit)
    for key in list(_shape_persistence):
        if key not in hits_this_frame:
            del _shape_persistence[key]
    return confirmed


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 1 — STATISTICAL KURTOSIS DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def detect_kurtosis_anomaly(psd_segment, freq_axis_segment, r_abs, f_abs):
    """
    Detect non-Gaussian interference via excess kurtosis.
    Additional logic:
    Detect multi-rise multi-fall structures caused by overlapping carriers.
    """

    if len(psd_segment) < 8:
        return None

    # =========================
    # ORIGINAL KURTOSIS LOGIC
    # =========================
    linear = 10.0 ** (psd_segment / 10.0)

    mu  = np.mean(linear)
    var = np.mean((linear - mu) ** 2)

    if var < 1e-30:
        return None

    mu4      = np.mean((linear - mu) ** 4)
    kurtosis = mu4 / (var ** 2)

    # =========================
    # KURTOSIS TRIGGER
    # =========================
    if abs(kurtosis - 3) <= KURTOSIS_DEVIATION_THRESH:
        return None

    # =========================
    # NEW RISE-FALL STRUCTURE DETECTOR
    # =========================

    noise_floor = np.min(psd_segment)
    threshold   = noise_floor + 2.5

    above = psd_segment > threshold

    edges = np.diff(above.astype(np.int8))

    rises = np.where(edges == 1)[0]
    falls = np.where(edges == -1)[0]

    if len(falls) > 0 and (len(rises) == 0 or falls[0] < rises[0]):
        rises = np.insert(rises, 0, 0)

    if len(rises) > 0 and (len(falls) == 0 or rises[-1] > falls[-1]):
        falls = np.append(falls, len(psd_segment) - 1)

    segments = []

    for r, f in zip(rises, falls):

        if (f - r) < 2:
            continue

        seg_start = r_abs + r
        seg_end   = r_abs + f

        fs = float(freq_axis_segment[r])
        fe = float(freq_axis_segment[f])

        segments.append({
            "r": seg_start,
            "f": seg_end,
            "f_start": fs,
            "f_stop": fe,
            "f_center": 0.5*(fs+fe),
            "bw": fe - fs
        })

    # If multiple rise-fall structures exist → interference
    if len(segments) <= 1:
        return None

    # Return each interference bump separately
    results = []

    for seg in segments:

        results.append({
            'trigger':  'MULTI_CARRIER_INTERFERENCE',
            'kurtosis': float(kurtosis),
            'r':        int(seg["r"]),
            'f':        int(seg["f"]),
            'f_center': seg["f_center"],
            'f_start':  seg["f_start"],
            'f_stop':   seg["f_stop"],
            'bw':       seg["bw"],
        })

    return results


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 2 — PSD RATIO SPUR DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def detect_psd_ratio_spurs(psd_current, psd_reference, freq_axis):
    """
    Detect narrowband tones/spurs by comparing current PSD to a slowly
    updated reference.  Flags bins where ratio > PSD_RATIO_THRESH_DB.
    """
    if psd_reference is None or len(psd_reference) != len(psd_current):
        return []

    lin_cur = 10.0 ** (psd_current  / 10.0)
    lin_ref = 10.0 ** (psd_reference / 10.0)

    with np.errstate(divide='ignore', invalid='ignore'):
        ratio_db = 10.0 * np.log10(np.maximum(lin_cur, 1e-30) /
                                    np.maximum(lin_ref, 1e-30))

    spur_mask = ratio_db > PSD_RATIO_THRESH_DB
    pad  = np.concatenate(([False], spur_mask, [False]))
    diff = np.diff(pad.astype(np.int8))
    starts = np.where(diff == 1)[0]
    ends   = np.where(diff == -1)[0]

    hits = []
    for s, e in zip(starts, ends):
        if (e - s) < 2:
            continue
        peak_ratio = float(np.max(ratio_db[s:e]))
        fs = float(freq_axis[s])
        fe = float(freq_axis[min(e - 1, len(freq_axis) - 1)])
        hits.append({
            'trigger':    'PSD_RATIO',
            'ratio_db':   peak_ratio,
            'r':          int(s),
            'f':          int(e - 1),
            'f_start':    fs,
            'f_stop':     fe,
            'f_center':   0.5 * (fs + fe),
            'bw':         fe - fs,
            'excess_db':  peak_ratio,
        })
    return hits


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 4 — MER / EVM ESTIMATION
# ═════════════════════════════════════════════════════════════════════════════

def estimate_mer_for_carrier(psd, r, f):
    """
    Approximate Modulation Error Ratio from spectrum statistics.
    MER(dB) = 10·log10(P_signal / P_error)
    P_error = power outside smoothed carrier envelope.
    """
    r, f = int(r), int(f)
    segment = psd[r:f + 1].astype(np.float64)
    if len(segment) < 10:
        return None
    kern = min(21, len(segment))
    if kern % 2 == 0:
        kern -= 1
    kern = max(kern, 3)
    smooth = uniform_filter1d(segment, size=kern)
    residual_db = segment - smooth
    lin_signal = np.sum(10.0 ** (smooth / 10.0))
    lin_error  = np.sum(10.0 ** (np.abs(residual_db) / 10.0)) - len(segment)
    lin_error  = max(lin_error, 1e-30)
    mer_db = float(10.0 * np.log10(max(lin_signal, 1e-30) / lin_error))
    if mer_db < MER_THRESHOLD_DB:
        fs = float(psd[r]) if r < len(psd) else 0.0  # placeholder
        return {
            'trigger':  'MER_DROP',
            'mer_db':   mer_db,
            'r':        r,
            'f':        f,
        }
    return None


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 5 — ML (MOVING-AVERAGE) ANOMALY DETECTOR
# ═════════════════════════════════════════════════════════════════════════════

def detect_ml_anomaly(psd_current, history_buffer):
    """
    Lightweight predictive anomaly detection using rolling mean of
    recent spectra.  Flags when RMS deviation exceeds threshold.
    """
    if len(history_buffer) < 5:
        return []
    predicted = np.mean(history_buffer, axis=0)
    diff      = psd_current - predicted
    rms       = float(np.sqrt(np.mean(diff ** 2)))
    if rms > ML_ANOMALY_THRESH_DB:
        # find the worst contiguous region
        abs_diff  = np.abs(diff)
        hot_mask  = abs_diff > ML_ANOMALY_THRESH_DB
        pad  = np.concatenate(([False], hot_mask, [False]))
        d    = np.diff(pad.astype(np.int8))
        starts = np.where(d == 1)[0]
        ends   = np.where(d == -1)[0]
        hits = []
        for s, e in zip(starts, ends):
            if (e - s) < 3:
                continue
            hits.append({
                'trigger':      'ML_ANOMALY',
                'rms_score':    rms,
                'r':            int(s),
                'f':            int(e - 1),
            })
        return hits
    return []


# ═════════════════════════════════════════════════════════════════════════════
# SECTION 3 — Eb/No vs BER DIVERGENCE
# ═════════════════════════════════════════════════════════════════════════════

def detect_ebno_divergence(carrier_power, noise_floor,
                           shape_hits, psd_ratio_hits, freq_axis, r, f):
    """
    Flag when estimated Eb/No looks healthy (>8 dB) but shape anomalies
    or PSD spurs are present — indicates hidden interference degrading BER.
    """
    ebno_est = carrier_power - noise_floor
    if ebno_est <= EBNO_MIN_DB:
        return None
    has_shape = any(h['r'] <= f and h['f'] >= r for h in shape_hits)
    has_spur  = any(h['r'] <= f and h['f'] >= r for h in psd_ratio_hits)
    if has_shape or has_spur:
        fc = 0.5 * (float(freq_axis[max(0, r)]) +
                     float(freq_axis[min(f, len(freq_axis) - 1)]))
        return {
            'trigger':   'EBNO_DIVERGENCE',
            'ebno_db':   float(ebno_est),
            'f_center':  fc,
            'r':         int(r),
            'f':         int(f),
            'f_start':   float(freq_axis[max(0, r)]),
            'f_stop':    float(freq_axis[min(f, len(freq_axis) - 1)]),
        }
    return None


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

    # =========================
    # LEFT SIDE
    # =========================
    if ci > l_limit:
        local_min_l = np.min(y[l_limit:ci])
        peak_drop_l = y[ci] - local_min_l
        floor_gap_l = local_min_l - gnt
        use_gnt_l = floor_gap_l <= 0.4 * peak_drop_l
        i = ci - 1
        found_sh = False
        while i > l_limit:
            if y[i] <= noise_stop:
                ba_l = i
                break
            if not found_sh and y[i] < thr:
                sh_l = i
                found_sh = True
            if found_sh:
                if i >= 3 and y[i - 3] >= y[i]:
                    if use_gnt_l:
                        if y[i] <= gnt + 1.5:
                            ba_l = i
                            break
                    else:
                        ba_l = i
                        break
            i -= 1
        else:
            ba_l = sh_l if found_sh else ci

    # =========================
    # RIGHT SIDE
    # =========================
    if ci < r_limit:
        local_min_r = np.min(y[ci:r_limit])
        peak_drop_r = y[ci] - local_min_r
        floor_gap_r = local_min_r - gnt
        use_gnt_r = floor_gap_r <= 0.4 * peak_drop_r
        i = ci + 1
        found_sh = False
        while i < r_limit:
            if y[i] <= noise_stop:
                ba_r = i
                break
            if not found_sh and y[i] < thr:
                sh_r = i
                found_sh = True
            if found_sh:
                if i + 3 < len(y) and y[i + 3] >= y[i]:
                    if use_gnt_r:
                        if y[i] <= gnt + 1.5:
                            ba_r = i
                            break
                    else:
                        ba_r = i
                        break
            i += 1
        else:
            ba_r = sh_r if found_sh else ci

    return ba_l, sh_l, ci, sh_r, ba_r


# ═════════════════════════════════════════════════════════════════════════════
# COMPLETE DETECTION PIPELINE v3
# ═════════════════════════════════════════════════════════════════════════════

def detection_pipeline(spectrum_psd, freq_axis, df, fft_size):
    smooth_taps = 2
    psd_s       = np.convolve(spectrum_psd, np.ones(smooth_taps) / smooth_taps, mode="same")
    noise     = float(np.median(psd_s))
    NF_RISE_DB = 2.5

    peak      = float(np.max(psd_s))
    threshold = noise + NF_RISE_DB
    above = psd_s > threshold
    edges = np.diff(above.astype(np.int8))
    rises = np.where(edges == 1)[0]
    falls = np.where(edges == -1)[0]

    if len(falls) > 0 and (len(rises) == 0 or falls[0] < rises[0]):
        rises = np.insert(rises, 0, 0)
    if len(rises) > 0 and (len(falls) == 0 or rises[-1] > falls[-1]):
        falls = np.append(falls, fft_size - 1)

    carrier_min_bins = max(2, int(round(MIN_CARRIER_BW_HZ / df)))
    raw_spans = [(int(r), int(f)) for r, f in zip(rises, falls)
                 if (int(f) - int(r)) >= carrier_min_bins]

    noise_baseline = np.full(fft_size, noise)
    noise_sigma    = np.full(fft_size, 1.0)
    gnt = noise

    #AUTHORIZED SPAN DECLARATION
    authorized_spans   = []  # Valid carriers detected
    authorized_edges   = []  # Exact boundaries of valid carriers
    unauthorized_spans = []  # Signals that are NOT authorized

    for r_c, f_c in raw_spans:
        r_c, f_c = int(r_c), int(f_c)
        span_center_hz = 0.5 * (float(freq_axis[r_c]) +
                                 float(freq_axis[min(f_c, fft_size - 1)]))
        span_center_mhz = span_center_hz / 1e6

        # ── Authorization check via config manager ──
        is_authorized = config_mgr.is_authorized(span_center_hz)
        best_center = span_center_mhz

        if is_authorized:
            ba_l, sh_l, ci, sh_r, ba_r = find_edges_for_carrier(
                freq_axis, psd_s, best_center, gnt,
                np.array([best_center]))
            ba_l = max(0, min(ba_l, fft_size - 1))
            ba_r = max(0, min(ba_r, fft_size - 1))
            if ba_r > ba_l:
                authorized_spans.append((ba_l, ba_r))
                authorized_edges.append((ba_l, sh_l, ci, sh_r, ba_r))
        else:
            unauthorized_spans.append((r_c, f_c))

    persistent_spans = authorized_spans if authorized_spans else raw_spans

    # ── Unauthorized interference hits ──
    all_raw_hits = []
    n_carriers   = len(authorized_spans)

    for r_c, f_c in unauthorized_spans:
        r_c, f_c = int(r_c), int(min(f_c, fft_size - 1))
        if f_c <= r_c:
            continue
        raw_pk = float(np.max(spectrum_psd[r_c:f_c + 1]))
        excess = raw_pk - noise
        fs = float(freq_axis[r_c])
        fe = float(freq_axis[f_c])
        all_raw_hits.append({
            'r': r_c, 'f': f_c,
            'f_start': fs, 'f_stop': fe,
            'f_center': 0.5 * (fs + fe),
            'bw': fe - fs,
            'peak_pwr': raw_pk,
            'excess_db': max(excess, 0.1),
            'carrier_ref_db': noise,
            'trigger': 'UNAUTHORIZED',
            'local_noise': noise,
        })

    intf_hits = apply_intf_persistence(all_raw_hits)

    # ── Shape anomaly detection inside each authorized carrier ──
    all_shape_hits = []
    for edge_info in authorized_edges:
        ba_l, sh_l, ci, sh_r, ba_r = edge_info
        hits = detect_center_shape_anomaly(
            spectrum_psd, freq_axis,
            ba_l, ba_r, noise
        )
        all_shape_hits.extend(hits)

    shape_hits = apply_shape_persistence(all_shape_hits)

    # ── Advanced detector 1: Kurtosis ──
    kurtosis_hits = []
    for r_c, f_c in authorized_spans:
        r_c, f_c = int(r_c), int(min(f_c, fft_size - 1))
        if f_c <= r_c:
            continue

        seg   = spectrum_psd[r_c:f_c + 1]
        f_seg = freq_axis[r_c:f_c + 1]

        hits = detect_kurtosis_anomaly(seg, f_seg, r_c, f_c)

        if hits:
            if isinstance(hits, list):
                kurtosis_hits.extend(hits)
            else:
                kurtosis_hits.append(hits)


    for r_c, f_c in unauthorized_spans:
        r_c, f_c = int(r_c), int(min(f_c, fft_size - 1))
        if f_c <= r_c:
            continue

        seg   = spectrum_psd[r_c:f_c + 1]
        f_seg = freq_axis[r_c:f_c + 1]

        hits = detect_kurtosis_anomaly(seg, f_seg, r_c, f_c)

        if hits:
            if isinstance(hits, list):
                kurtosis_hits.extend(hits)
            else:
                kurtosis_hits.append(hits)

    # ── Advanced detector 2: PSD ratio spurs ──
    global _psd_reference, _psd_reference_init
    if not _psd_reference_init or _psd_reference is None or len(_psd_reference) != fft_size:
        _psd_reference      = psd_s.copy()
        _psd_reference_init = True
    else:
        _psd_reference = (1.0 - PSD_REF_ALPHA) * _psd_reference + PSD_REF_ALPHA * psd_s

    psd_ratio_hits = detect_psd_ratio_spurs(psd_s, _psd_reference, freq_axis)

    # ── Advanced detector 3: MER estimation ──
    mer_hits = []
    for idx_c, (r_c, f_c) in enumerate(authorized_spans):
        hit = estimate_mer_for_carrier(spectrum_psd, r_c, f_c)
        if hit:
            fc = 0.5 * (float(freq_axis[max(0, int(r_c))]) +
                         float(freq_axis[min(int(f_c), fft_size - 1)]))
            hit['f_center'] = fc
            hit['f_start']  = float(freq_axis[max(0, int(r_c))])
            hit['f_stop']   = float(freq_axis[min(int(f_c), fft_size - 1)])
            hit['carrier_idx'] = idx_c + 1
            mer_hits.append(hit)

    # ── Advanced detector 4: ML anomaly ──
    global _ml_history_buffer
    if len(_ml_history_buffer) == 0 or len(_ml_history_buffer[0]) != fft_size:
        _ml_history_buffer = []
    _ml_history_buffer.append(psd_s.copy())
    if len(_ml_history_buffer) > ML_HISTORY_LEN:
        _ml_history_buffer.pop(0)

    ml_raw = detect_ml_anomaly(psd_s, _ml_history_buffer)
    ml_hits = []
    for hit in ml_raw:
        r_h, f_h = hit['r'], min(hit['f'], fft_size - 1)
        hit['f_center'] = 0.5 * (float(freq_axis[r_h]) + float(freq_axis[f_h]))
        hit['f_start']  = float(freq_axis[r_h])
        hit['f_stop']   = float(freq_axis[f_h])
        ml_hits.append(hit)

    # ── Advanced detector 5: Eb/No divergence ──
    performance_hits = []
    for r_c, f_c in authorized_spans:
        r_c, f_c = int(r_c), int(min(f_c, fft_size - 1))
        if f_c <= r_c:
            continue
        cpwr = float(np.max(spectrum_psd[r_c:f_c + 1]))
        hit  = detect_ebno_divergence(cpwr, noise, shape_hits, psd_ratio_hits,
                                       freq_axis, r_c, f_c)
        if hit:
            performance_hits.append(hit)

    return {
        "noise":                  noise,
        "noise_baseline":         noise_baseline,
        "noise_sigma":            noise_sigma,
        "noise_std":              1.0,
        "psd_s":                  psd_s,
        "persistent_spans":       persistent_spans,
        "intf_hits":              intf_hits,
        "all_raw_hits":           all_raw_hits,
        "shape_hits":             shape_hits,
        "all_shape_hits":         all_shape_hits,
        "n_carriers":             n_carriers,
        "carrier_min_bins":       carrier_min_bins,
        "kurtosis_hits":          kurtosis_hits,
        "psd_ratio_hits":         psd_ratio_hits,
        "mer_hits":               mer_hits,
        "ml_hits":                ml_hits,
        "performance_hits":       performance_hits,
    }


# ═════════════════════════════════════════════════════════════════════════════
# C/I RATIO
# ═════════════════════════════════════════════════════════════════════════════

def compute_ci_ratio(spectrum_psd, carrier_start, carrier_end, intf_hits_in_carrier):
    r, f = int(carrier_start), int(carrier_end)
    carrier_linear = 10.0 ** (spectrum_psd[r:f+1] / 10.0)
    total_power    = float(np.sum(carrier_linear))
    intf_mask = np.zeros(f - r + 1, dtype=bool)
    for hit in intf_hits_in_carrier:
        hs = max(0, int(hit['r']) - r)
        he = min(f - r, int(hit['f']) - r)
        intf_mask[hs:he+1] = True
    intf_power  = float(np.sum(carrier_linear[intf_mask]))
    clean_power = total_power - intf_power
    if intf_power > 1e-15:
        ci_db = float(10.0 * np.log10(max(clean_power, 1e-15) / intf_power))
    else:
        ci_db = 99.9
    p_total_db = float(10.0 * np.log10(total_power + 1e-15))
    p_intf_db  = float(10.0 * np.log10(intf_power  + 1e-15))
    return ci_db, p_total_db, p_intf_db


CI_ENABLED = False

# ── Render toggle flags ────────────────────────────────────────────────────────
RENDER_A_ON = True   # Carrier spans (green)
RENDER_B_ON = True   # Unauthorized interference (red)
RENDER_D_ON = True   # Intra-carrier shape anomaly (magenta)  — Section 3
RENDER_E_ON = True   # Kurtosis anomaly (cyan)                — Section 1
RENDER_F_ON = True   # PSD ratio spurs (yellow)               — Section 2
RENDER_G_ON = True   # MER drop (blue)                        — Section 4
RENDER_H_ON = True   # ML anomaly (white)                     — Section 5
RENDER_I_ON = True   # Eb/No divergence (orange-red)          — Section 3

Y_MIN = -70
Y_MAX = 80
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

_state_lock = threading.Lock()
_latest_iq       = None
_latest_meta     = None
_latest_carriers = None


class DataFetcher(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self._stop_event = threading.Event()
        self._poller = zmq.Poller()
        self._poller.register(sock,         zmq.POLLIN)
        self._poller.register(meta_sock,    zmq.POLLIN)
        self._poller.register(carrier_sock, zmq.POLLIN)

    def stop(self):  self._stop_event.set()

    def run(self):
        global _latest_iq, _latest_meta, _latest_carriers
        while not self._stop_event.is_set():
            events = dict(self._poller.poll(timeout=10))
            if not events: continue
            if sock in events:
                iq = np.frombuffer(sock.recv(), dtype=np.complex64)
                with _state_lock: _latest_iq = iq.copy()
            if meta_sock in events:
                with _state_lock: _latest_meta = meta_sock.recv_json()
            if carrier_sock in events:
                with _state_lock: _latest_carriers = carrier_sock.recv_json()


# ═════════════════════════════════════════════════════════════════════════════
# PLOT SETUP
# ═════════════════════════════════════════════════════════════════════════════

fig, (ax, ax_wf) = plt.subplots(
    2, 1, figsize=(12, 8),
    gridspec_kw={'height_ratios': [3, 2], 'hspace': 0.08},
    sharex=True
)
manager = plt.get_current_fig_manager()
manager.window.showMaximized()
plt.subplots_adjust(right=0.88, bottom=0.18, top=0.95)

_wf_data = np.full((WATERFALL_ROWS, FFT_SIZE), WATERFALL_VMIN, dtype=np.float32)
_wf_row  = 0

def update_axis():
    global freq_axis, df
    df = HW_SAMPLE_RATE / FFT_SIZE
    freq_axis = np.arange(-FFT_SIZE // 2, FFT_SIZE // 2) * df + HW_CENTER_FREQ
    xlim = ((DISPLAY_CENTER_FREQ - DISPLAY_BW / 2) / 1e6,
            (DISPLAY_CENTER_FREQ + DISPLAY_BW / 2) / 1e6)
    ax.set_xlim(*xlim)
    ax_wf.set_xlim(*xlim)

update_axis()

line_live,  = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), lw=1, color='#00bfff')
line_max,   = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), color="green", lw=1)
line_min,   = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE), color="red",   lw=0.5)
line_noise, = ax.plot(freq_axis / 1e6, np.zeros(FFT_SIZE),
                      color="#ffd700", lw=0.8, ls='--', alpha=0.7, label='Noise Floor')

ax.set_ylim(Y_MIN, Y_MAX)
ax.set_ylabel("Power (dB)")
ax.set_title("Real-Time FFT Spectrum + Adaptive Carrier Detection v3")
ax.tick_params(axis='x', labelbottom=False)

f_lo = freq_axis[0] / 1e6
f_hi = freq_axis[-1] / 1e6
_wf_img = ax_wf.imshow(
    _wf_data, aspect='auto', origin='upper', cmap=WATERFALL_CMAP,
    extent=[f_lo, f_hi, WATERFALL_ROWS, 0],
    vmin=WATERFALL_VMIN, vmax=WATERFALL_VMAX, interpolation='none'
)
ax_wf.set_ylabel("Time →")
ax_wf.set_xlabel("Frequency (MHz)")
ax_wf.set_yticks([])

window    = get_window("hann", FFT_SIZE)
iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)

monitor_ax = plt.axes([0.01, 0.78, 0.22, 0.17])
monitor_ax.axis("off")
monitor_text = monitor_ax.text(0.0, 1.0, "", va='top', fontsize=9, family='monospace')


# =====================================================
# LOG VIEWER WINDOW
# =====================================================
MAX_LOG_LINES    = 5000
LOG_THROTTLE_SEC = 5.0

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
    f"[{datetime.now().strftime('%H:%M:%S')}] v3 Log started  |  "
    f"HW SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  FFT: {FFT_SIZE}  |  "
    f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz  |  Morph: {MORPH_MIN_WINDOW_BINS} bins",
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

smooth_enabled = True; smooth_alpha = 0.86; psd_avg = None
smooth_ax  = plt.axes([0.90, 0.62, 0.1, 0.04])
smooth_btn = Button(smooth_ax, "Smooth ON")
def toggle_smooth(event):
    global smooth_enabled; smooth_enabled = not smooth_enabled
    smooth_btn.label.set_text("Smooth ON" if smooth_enabled else "Smooth OFF")
smooth_btn.on_clicked(toggle_smooth)

slider_ax     = plt.axes([0.15, 0.02, 0.5, 0.03])
smooth_slider = Slider(slider_ax, "Smooth", 0.0, 1.0, valinit=0.86)
def update_smooth(val):
    global smooth_alpha; smooth_alpha = val
smooth_slider.on_changed(update_smooth)

ax_freq = plt.axes([0.1,  0.07, 0.2,  0.04])
tb_freq = TextBox(ax_freq, "Center Freq (Hz)", initial=str(CENTER_FREQ))
ax_sr   = plt.axes([0.45, 0.07, 0.15, 0.04])
tb_sr   = TextBox(ax_sr, "Sample rate (Hz)", initial=str(DISPLAY_BW))
ax_fft  = plt.axes([0.7,  0.07, 0.1,  0.04])
tb_fft  = TextBox(ax_fft, "FFT", initial=str(FFT_SIZE))

def update_freq(text):
    global DISPLAY_CENTER_FREQ; DISPLAY_CENTER_FREQ = float(text); update_axis()
def update_display_bw(text):
    global DISPLAY_BW; DISPLAY_BW = float(text)
    xlim = ((DISPLAY_CENTER_FREQ - DISPLAY_BW/2)/1e6, (DISPLAY_CENTER_FREQ + DISPLAY_BW/2)/1e6)
    ax.set_xlim(*xlim); ax_wf.set_xlim(*xlim)
def update_fft(text):
    global FFT_SIZE, max_hold, min_hold, window, iq_buffer, _wf_data, _wf_row
    FFT_SIZE = int(text); update_axis()
    window = get_window("hann", FFT_SIZE)
    iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
    max_hold = np.full(FFT_SIZE, -np.inf); min_hold = np.full(FFT_SIZE, np.inf)
    _wf_data = np.full((WATERFALL_ROWS, FFT_SIZE), WATERFALL_VMIN, dtype=np.float32)
    _wf_row = 0
    for ln in [line_live, line_max, line_min, line_noise]:
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

log_btn_ax = plt.axes([0.90, 0.405, 0.1, 0.035]); log_btn = Button(log_btn_ax, "View Log")
def toggle_log(event):
    if log_win.isVisible(): log_win.hide()
    else: log_win.show(); log_win.raise_(); log_win.activateWindow()
log_btn.on_clicked(toggle_log)

ci_btn_ax = plt.axes([0.90, 0.365, 0.1, 0.035]); ci_btn = Button(ci_btn_ax, "C/I: OFF")
def toggle_ci(event):
    global CI_ENABLED; CI_ENABLED = not CI_ENABLED
    ci_btn.label.set_text("C/I: ON" if CI_ENABLED else "C/I: OFF")
    fig.canvas.draw_idle()
ci_btn.on_clicked(toggle_ci)

_show_noise_line = True
noise_btn_ax = plt.axes([0.90, 0.325, 0.1, 0.035]); noise_btn = Button(noise_btn_ax, "NF Line: ON")
def toggle_noise_line(event):
    global _show_noise_line; _show_noise_line = not _show_noise_line
    noise_btn.label.set_text("NF Line: ON" if _show_noise_line else "NF Line: OFF")
    line_noise.set_visible(_show_noise_line); fig.canvas.draw_idle()
noise_btn.on_clicked(toggle_noise_line)

# ── Render ON/OFF toggle buttons ──────────────────────────────────────────────
_render_btn_defs = [
    ("A: Carriers",   "RENDER_A_ON", 0.285),
    ("B: Unauth",     "RENDER_B_ON", 0.245),
    ("D: Shape",      "RENDER_D_ON", 0.205),
    ("E: Kurtosis",   "RENDER_E_ON", 0.165),
    ("F: PSD Spur",   "RENDER_F_ON", 0.125),
    ("G: MER",        "RENDER_G_ON", 0.085),
    ("H: ML Anom",    "RENDER_H_ON", 0.045),
    ("I: Eb/No",      "RENDER_I_ON", 0.005),
]

_render_btn_axes   = {}
_render_btns       = {}

def _make_render_toggle(flag_name, label_base, btn_ref_list):
    def toggle(event):
        g = globals()
        g[flag_name] = not g[flag_name]
        new_val = g[flag_name]
        btn_ref_list[0].label.set_text(
            f"{label_base}: ON" if new_val else f"{label_base}: OFF")
        fig.canvas.draw_idle()
    return toggle

for _lbl, _flag, _y in _render_btn_defs:
    _ax = plt.axes([0.90, _y, 0.1, 0.033])
    _btn = Button(_ax, f"{_lbl}: ON",
                  color="#1a3a1a", hovercolor="#2d5a2d")
    _btn.label.set_fontsize(7.5)
    _render_btn_axes[_flag] = _ax
    _render_btns[_flag]     = _btn
    _ref = [_btn]
    _btn.on_clicked(_make_render_toggle(_flag, _lbl, _ref))

print("[INFO] v3 GUI — local morphological noise floor + waterfall")


# ═══════════════════════════════════════════════════════════════════════════
# UPDATE FUNCTION  (called by QTimer at ~30 fps)
# ═══════════════════════════════════════════════════════════════════════════

def update():
    global _latest_iq, _latest_meta, _latest_carriers
    global HW_SAMPLE_RATE, FFT_SIZE, HW_CENTER_FREQ
    global window, iq_buffer, max_hold, min_hold
    global psd_avg, smooth_enabled, smooth_alpha
    global _wf_data, _wf_row

    with _state_lock:
        iq_frame      = _latest_iq
        meta_frame    = _latest_meta
        carrier_frame = _latest_carriers
        _latest_iq = _latest_meta = _latest_carriers = None

    if meta_frame is not None:
        HW_SAMPLE_RATE = meta_frame["rate"]
        FFT_SIZE       = meta_frame["fft"]
        HW_CENTER_FREQ = meta_frame["cf"]
        window    = get_window("hann", FFT_SIZE)
        iq_buffer = np.zeros(FFT_SIZE, dtype=np.complex64)
        max_hold  = np.full(FFT_SIZE, -np.inf)
        min_hold  = np.full(FFT_SIZE,  np.inf)
        _wf_data  = np.full((WATERFALL_ROWS, FFT_SIZE), WATERFALL_VMIN, dtype=np.float32)
        _wf_row   = 0
        _carrier_persistence.clear(); _intf_persistence.clear(); _shape_persistence.clear()
        global _psd_reference, _psd_reference_init, _ml_history_buffer
        _psd_reference = None; _psd_reference_init = False; _ml_history_buffer = []
        update_axis()
        for ln in [line_live, line_max, line_min, line_noise]:
            ln.set_xdata(freq_axis / 1e6)
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S')}] META  |  "
            f"SR: {HW_SAMPLE_RATE/1e6:.1f} MHz  |  FFT: {FFT_SIZE}  |  "
            f"CF: {HW_CENTER_FREQ/1e6:.1f} MHz", "#dcdcaa")

    if iq_frame is None: return
    iq = iq_frame
    if len(iq) < FFT_SIZE: return
    iq_buffer[:] = iq[:FFT_SIZE]

    spectrum = np.fft.fftshift(np.fft.fft(iq_buffer * window))
    psd      = 20.0 * np.log10(np.abs(spectrum) + 1e-12)

    global psd_avg
    if psd_avg is None or len(psd_avg) != len(psd):
        psd_avg = psd.copy()

    raw_psd = psd.copy()

    if smooth_enabled:
        alpha = 1.0 - (1.0 - smooth_alpha) ** 2
        psd_avg = alpha * psd_avg + (1.0 - alpha) * raw_psd
        spectrum_psd = psd_avg
    else:
        spectrum_psd = raw_psd

    line_live.set_ydata(spectrum_psd)

    if len(spectrum_psd) == _wf_data.shape[1]:
        wf_row = np.clip(raw_psd, WATERFALL_VMIN, WATERFALL_VMAX)
        _wf_data[_wf_row, :] = wf_row
        _wf_row = (_wf_row + 1) % WATERFALL_ROWS
        _wf_img.set_data(_wf_data)
        _wf_img.set_extent([
            freq_axis[0] / 1e6,
            freq_axis[-1] / 1e6,
            WATERFALL_ROWS,
            0
        ])

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

    for patch in ax.patches[:]: patch.remove()
    for txt   in ax.texts[:]:   txt.remove()
    for ln    in ax.lines[4:]:  ln.remove()

    det = detection_pipeline(spectrum_psd, freq_axis, df, FFT_SIZE)

    noise                 = det["noise"]
    noise_baseline        = det["noise_baseline"]
    psd_s                 = det["psd_s"]
    threshold             = det["noise"] + THRESHOLD_RATIO * (float(np.max(det["psd_s"])) - det["noise"])
    persistent_spans      = det["persistent_spans"]
    intf_hits             = det["intf_hits"]
    all_raw_hits          = det["all_raw_hits"]
    shape_hits            = det["shape_hits"]
    all_shape_hits        = det["all_shape_hits"]
    n_carriers            = det["n_carriers"]
    carrier_min_bins      = det["carrier_min_bins"]
    kurtosis_hits         = det.get("kurtosis_hits", [])
    psd_ratio_hits        = det.get("psd_ratio_hits", [])
    mer_hits              = det.get("mer_hits", [])
    ml_hits               = det.get("ml_hits", [])
    performance_hits      = det.get("performance_hits", [])

    if _show_noise_line and len(noise_baseline) == len(freq_axis):
        line_noise.set_ydata(noise_baseline)

    def safe_remove(obj):
        try:
            if obj is not None: obj.remove()
        except Exception:
            pass
        return None

    for m in markers.values():
        m.artist_a = safe_remove(m.artist_a)
        m.artist_b = safe_remove(m.artist_b)
        m.text     = safe_remove(m.text)
        if not markers_global_on: continue
        color = MARKER_COLORS[m.idx]
        if m.mode == "peak":
            pidx = int(np.argmax(spectrum_psd))
            m.point_a = (float(freq_axis[pidx]), float(spectrum_psd[pidx]))
        if m.point_a:
            fx, py = m.point_a
            if m.mode == "normal":
                bidx = int(np.argmin(np.abs(freq_axis - fx)))
                py = float(spectrum_psd[bidx]); m.point_a = (fx, py)
            m.artist_a = ax.scatter(fx / 1e6, py, marker="D", s=80, color=color, zorder=20)
            label_txt = f"M{m.idx}\n{fx/1e6:.3f} MHz\n{py:.1f} dB"
            if m.mode == "delta" and m.point_b:
                fx2, py2 = m.point_b
                m.artist_b = ax.scatter(fx2 / 1e6, py2, marker="D", s=80, color=color, zorder=20)
                label_txt += f"\nΔf: {abs(fx-fx2)/1e6:.3f} MHz\nΔP: {abs(py-py2):.1f} dB"
            elif m.mode == "delta" and not m.point_b:
                label_txt += "\n[click ref point]"
            m.text = ax.text(fx / 1e6, py + 3, label_txt, color=color, fontsize=9,
                             bbox=dict(fc="black", alpha=0.6), zorder=21)

    now            = time.time()
    log_this_frame = (now - log_win._last_log_time) >= LOG_THROTTLE_SEC

    # ═════════════════════════════════════════════════════════════════════
    # RENDER A — CARRIER SPANS  (green highlights)
    # ═════════════════════════════════════════════════════════════════════
    carrier_count = 0
    GREEN_SHADES  = ["#4ec9b0", "#6abf69", "#98e898", "#00ff7f", "#b2fab4"]

    for r_c, f_c in (persistent_spans if RENDER_A_ON else []):
        r_c, f_c = int(r_c), int(f_c)
        if (f_c - r_c) < carrier_min_bins:
            continue

        f_start  = float(freq_axis[max(0, r_c)]) - df
        f_stop   = float(freq_axis[min(f_c, FFT_SIZE - 1)]) + df
        bw       = f_stop - f_start
        f_center = 0.5 * (f_start + f_stop)

        cpk  = float(np.max(spectrum_psd[r_c:f_c + 1]))
        lp   = float(np.sum(10.0 ** (spectrum_psd[r_c:f_c + 1] / 10.0)))
        ctp  = float(10.0 * np.log10(lp + 1e-12))
        bins_in_carrier = f_c - r_c + 1
        noise_linear    = float(np.median(10.0 ** (spectrum_psd / 10.0)))
        ntd  = float(10.0 * np.log10(noise_linear * bins_in_carrier + 1e-12))
        cn   = ctp - ntd

        ax.axvspan(f_start / 1e6, f_stop / 1e6, color="green", alpha=0.25, zorder=2)
        ax.axvline(f_start / 1e6, color="orange", lw=1, zorder=3)
        ax.axvline(f_stop  / 1e6, color="orange", lw=1, zorder=3)
        ax.text(f_center / 1e6, Y_MAX - 5, f"{bw/1e3:.0f} kHz",
                ha="center", va="top",
                bbox=dict(boxstyle="round", fc="white", alpha=0.8), zorder=4)

        carrier_count += 1
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"Carrier {carrier_count}  |  Freq: {f_center/1e6:.3f} MHz  |  "
                f"Pwr: {ctp:.1f} dB  |  BW: {bw/1e3:.1f} kHz  |  "
                f"Peak: {cpk:.1f} dB  |  Noise: {noise:.1f} dB  |  C/N: {cn:.2f} dB",
                GREEN_SHADES[(carrier_count - 1) % len(GREEN_SHADES)])
            log_win._last_log_time = now

    if carrier_count == 0 and log_this_frame and log_win.isVisible():
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
            f"No carriers  |  Noise: {noise:.1f} dB  |  Threshold: {threshold:.1f} dB",
            "#808080")

    # ═════════════════════════════════════════════════════════════════════
    # RENDER B — UNAUTHORIZED INTERFERENCE  (red highlights)
    # ═════════════════════════════════════════════════════════════════════
    intf_count = 0
    RED_SHADES = ["#ff6b6b", "#ff4757", "#ff6348", "#e84393", "#ff7f50"]

    for hit in (intf_hits if RENDER_B_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="red", alpha=0.45, zorder=8)
        ax.axvline(fs / 1e6, color="cyan", lw=1.2, ls="--", zorder=9)
        ax.axvline(fe / 1e6, color="cyan", lw=1.2, ls="--", zorder=9)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 17,
                f"INTF\n+{hit['excess_db']:.1f} dB\n[{hit['trigger']}]",
                ha="center", va="top", fontsize=7.5, color="red",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        intf_count += 1
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[UNAUTH-INTF] #{intf_count}  |  "
                f"Freq: {hit['f_center']/1e6:.3f} MHz  |  "
                f"Excess: +{hit['excess_db']:.1f} dB  |  "
                f"Trigger: {hit['trigger']}",
                RED_SHADES[(intf_count - 1) % len(RED_SHADES)])

    if intf_count == 0 and log_this_frame and log_win.isVisible():
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
            f"No unauthorized interference  |  Carriers: {n_carriers}  |  "
            f"Raw hits: {len(all_raw_hits)}  |  Pending: {len(_intf_persistence)}",
            "#555555")

    # ═════════════════════════════════════════════════════════════════════
    # RENDER D — INTRA-CARRIER SHAPE ANOMALY  (magenta highlights)
    #
    # These are ±2 dB envelope deviations detected inside authorized
    # carriers — indicates carrier-on-carrier interference, shoulder
    # bumps, plateau distortion, or spectral humps.
    # ═════════════════════════════════════════════════════════════════════
    shape_count = 0
    MAGENTA_SHADES = ["#ff00ff", "#e040fb", "#d500f9", "#aa00ff", "#ea80fc"]

    for hit in (shape_hits if RENDER_D_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="#ff00ff", alpha=0.35, zorder=8)
        ax.axvline(fs / 1e6, color="#ff80ff", lw=1.2, ls="--", zorder=9)
        ax.axvline(fe / 1e6, color="#ff80ff", lw=1.2, ls="--", zorder=9)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 23,
                f"SHAPE\n±{hit['excess_db']:.1f} dB\n[{hit['trigger']}]",
                ha="center", va="top", fontsize=7.5, color="#ff80ff",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        shape_count += 1
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[SHAPE-INTF] #{shape_count}  |  "
                f"Freq: {hit['f_center']/1e6:.3f} MHz  |  "
                f"Deviation: ±{hit['excess_db']:.1f} dB  |  "
                f"BW: {hit['bw']/1e3:.1f} kHz  |  "
                f"Trigger: {hit['trigger']}",
                MAGENTA_SHADES[(shape_count - 1) % len(MAGENTA_SHADES)])

    if shape_count == 0 and log_this_frame and log_win.isVisible():
        log_win.append(
            f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
            f"No shape anomalies  |  Carriers: {n_carriers}  |  "
            f"Raw shape hits: {len(all_shape_hits)}  |  "
            f"Pending: {len(_shape_persistence)}",
            "#555555")

    # ═════════════════════════════════════════════════════════════════════
    # RENDER E — KURTOSIS ANOMALY  (cyan highlights)
    # ═════════════════════════════════════════════════════════════════════
    CYAN_SHADES = ["#00ffff", "#00e5ff", "#18ffff", "#84ffff"]
    for ki, hit in enumerate(kurtosis_hits if RENDER_E_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="cyan", alpha=0.25, zorder=7)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 35,
                f"KURT\nK={hit['kurtosis']:.1f}",
                ha="center", va="top", fontsize=7, color="cyan",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[KURTOSIS] {hit['f_center']/1e6:.3f} MHz  |  "
                f"K={hit['kurtosis']:.1f}",
                CYAN_SHADES[ki % len(CYAN_SHADES)])

    # ═════════════════════════════════════════════════════════════════════
    # RENDER F — PSD RATIO SPURS  (yellow highlights)
    # ═════════════════════════════════════════════════════════════════════
    YELLOW_SHADES = ["#ffff00", "#ffd600", "#ffea00", "#fff176"]
    for si, hit in enumerate(psd_ratio_hits if RENDER_F_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="yellow", alpha=0.25, zorder=7)
        ax.axvline(fs / 1e6, color="yellow", lw=0.8, ls=":", zorder=8)
        ax.axvline(fe / 1e6, color="yellow", lw=0.8, ls=":", zorder=8)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 41,
                f"PSD-SPUR\n+{hit['ratio_db']:.1f} dB",
                ha="center", va="top", fontsize=7, color="yellow",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[PSD-SPUR] {hit['f_center']/1e6:.3f} MHz  |  "
                f"+{hit['ratio_db']:.1f} dB ratio",
                YELLOW_SHADES[si % len(YELLOW_SHADES)])

    # ═════════════════════════════════════════════════════════════════════
    # RENDER G — MER DROP  (blue highlights)
    # ═════════════════════════════════════════════════════════════════════
    BLUE_SHADES = ["#448aff", "#2979ff", "#82b1ff", "#536dfe"]
    for mi, hit in enumerate(mer_hits if RENDER_G_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="#448aff", alpha=0.20, zorder=6)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 47,
                f"MER\n{hit['mer_db']:.1f} dB",
                ha="center", va="top", fontsize=7, color="#82b1ff",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[MER-DROP] Carrier {hit.get('carrier_idx','?')}  |  "
                f"MER={hit['mer_db']:.1f} dB",
                BLUE_SHADES[mi % len(BLUE_SHADES)])

    # ═════════════════════════════════════════════════════════════════════
    # RENDER H — ML ANOMALY  (white highlights)
    # ═════════════════════════════════════════════════════════════════════
    for ai, hit in enumerate(ml_hits if RENDER_H_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="white", alpha=0.15, zorder=5)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 53,
                f"ML-ANOM\nRMS={hit['rms_score']:.1f}",
                ha="center", va="top", fontsize=7, color="white",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[ML-ANOM] Spectral deviation detected  |  "
                f"RMS={hit['rms_score']:.1f} dB",
                "#ffffff")

    # ═════════════════════════════════════════════════════════════════════
    # RENDER I — Eb/No DIVERGENCE  (orange-red highlights)
    # ═════════════════════════════════════════════════════════════════════
    PERF_SHADES = ["#ff9100", "#ff6d00", "#ffab40", "#ff3d00"]
    for pi, hit in enumerate(performance_hits if RENDER_I_ON else []):
        fs, fe = hit['f_start'], hit['f_stop']
        ax.axvspan(fs / 1e6, fe / 1e6, color="#ff6d00", alpha=0.20, zorder=6)
        ax.text(hit['f_center'] / 1e6, Y_MAX - 59,
                f"Eb/No DIV\n{hit['ebno_db']:.1f} dB",
                ha="center", va="top", fontsize=7, color="#ffab40",
                bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.75), zorder=10)
        if log_this_frame and log_win.isVisible():
            log_win.append(
                f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                f"[EBNO-DIV] {hit['f_center']/1e6:.3f} MHz  |  "
                f"Eb/No={hit['ebno_db']:.1f} dB  (hidden interference)",
                PERF_SHADES[pi % len(PERF_SHADES)])

    # ═════════════════════════════════════════════════════════════════════
    # RENDER C — C/I RATIO LABELS
    # ═════════════════════════════════════════════════════════════════════
    if CI_ENABLED:
        ci_num = 0
        for r_c, f_c in persistent_spans:
            r_c, f_c = int(r_c), int(f_c)
            if (f_c - r_c) < carrier_min_bins: continue
            ci_num += 1
            hits_in = [h for h in intf_hits if h['r'] <= f_c and h['f'] >= r_c]
            hits_in += [h for h in shape_hits if h['r'] <= f_c and h['f'] >= r_c]
            ci_db, ptot, pint = compute_ci_ratio(spectrum_psd, r_c, f_c, hits_in)

            f_start = float(freq_axis[max(0, r_c)]) - df
            f_stop  = float(freq_axis[min(f_c, FFT_SIZE - 1)]) + df
            fc      = 0.5 * (f_start + f_stop)

            ci_color = "#00e676" if ci_db >= 20 else ("#ffd700" if ci_db >= 10 else "#ff4444")
            ax.text(fc / 1e6, Y_MAX - 29, f"C/I: {ci_db:.1f} dB",
                    ha="center", va="top", fontsize=8, color=ci_color,
                    fontweight="bold",
                    bbox=dict(boxstyle="round,pad=0.3", fc="black", alpha=0.85), zorder=12)
            if log_this_frame and log_win.isVisible():
                log_win.append(
                    f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] "
                    f"[C/I] Carrier {ci_num}  |  C/I: {ci_db:.1f} dB  |  "
                    f"P_total: {ptot:.1f}  |  P_intf: {pint:.1f}", "#ffd700")

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