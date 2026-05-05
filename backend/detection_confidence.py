"""
detection_confidence.py
=======================

Non-invasive augmentation layer for Interference_error.py.

This module does NOT modify the existing detection algorithm. It wraps
detection output and adds four orthogonal enhancements:

    A. Temporal covariance confidence (RMT / Marchenko-Pastur inspired)
    B. Majority-vote persistence buffer (5-frame memory, M-of-N rule)
    C. Slope-asymmetry / envelope-deviation shoulder detector
    D. Classification confidence scoring (probability vector)

All four are exposed through a single ConfidenceEngine class with one
entry-point: .augment(). The caller's existing detection logic is
untouched; augment() only adds fields to hit dicts and may append new
hits discovered by the shoulder detector.

Integration into Interference_error.py requires TWO added lines total:

    # near top of file, once:
    from detection_confidence import ConfidenceEngine
    _conf = ConfidenceEngine(fft_size=FFT_SIZE)

    # inside update(), after each detect_interference_in_carrier() call:
    intf_hits = _conf.augment(
        psd_raw=psd, display_psd=display_psd,
        carrier_span=(r, f), carrier_cf=f_center, intf_hits=intf_hits,
        noise_floor=noise, frame_idx=_frame_counter,
    )

Author: additive layer for ISTRAC Interference Detection System
"""

from __future__ import annotations
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Dict, List, Optional, Tuple
import numpy as np


# ═════════════════════════════════════════════════════════════════════════════
# CONFIGURATION — tune without touching main pipeline
# ═════════════════════════════════════════════════════════════════════════════

# Module A: Temporal covariance (MME)
COV_FRAME_DEPTH          = 6       # K = frames in covariance window
COV_MIN_SPAN_BINS        = 8       # minimum span width to run MME
COV_MME_NOISE_MARGIN     = 1.15    # ratio must exceed MP bound × this factor

# Module B: Majority-vote persistence
VOTE_WINDOW_FRAMES       = 5       # N = memory depth
VOTE_CONFIRM_FRAMES      = 3       # M = required hits out of N
VOTE_FREQ_BUCKET_HZ      = 25e3    # lateral grouping tolerance
VOTE_WIDTH_BUCKET_HZ     = 50e3    # width grouping tolerance

# Module C: Shoulder / envelope-deviation detector
SHOULDER_MIN_CARRIER_BINS  = 20    # below this the detector won't trigger
SHOULDER_EDGE_FRAC         = 0.18  # fraction of carrier width used for edge
SHOULDER_ASYMMETRY_THR     = 0.35  # |s_L - s_R| / max(|s_L|, |s_R|)
SHOULDER_ENVELOPE_LIFT_DB  = 2.0   # envelope residual > this = shoulder lift
SHOULDER_MIN_LIFT_BINS     = 3     # contiguous bins above residual threshold

# Module D: Classification probability weights (heuristic, tune from data)
CLS_CW_MAX_WIDTH_BINS      = 4     # width ≤ this → CW candidate
CLS_CW_MIN_STRENGTH_DB     = 4.0
CLS_OVERLAP_MIN_DEPTH_DB   = 3.0   # gap-method depth threshold
CLS_NOISE_RISE_MAX_STRENGTH = 2.5

# Internal
_EPS = 1e-12


# ═════════════════════════════════════════════════════════════════════════════
# DATA STRUCTURES
# ═════════════════════════════════════════════════════════════════════════════

@dataclass
class _FrameRecord:
    """One raw-PSD snapshot kept in the covariance ring buffer."""
    psd:       np.ndarray                       # length = fft_size
    noise:     float                            # global noise estimate
    frame_idx: int


@dataclass
class _VoteRecord:
    """One frame's interference fingerprint used for majority voting."""
    frame_idx: int
    keys:      set = field(default_factory=set) # set of (c_bucket, i_bucket, w_bucket)


# ═════════════════════════════════════════════════════════════════════════════
# MAIN ENGINE
# ═════════════════════════════════════════════════════════════════════════════

class ConfidenceEngine:
    """
    Confidence + persistence + shoulder + classification wrapper.

    Thread-safety: call from the same thread that runs detection (typically
    the Qt GUI thread via QTimer). Ring buffers are plain deques.
    """

    # ─────────────────────────────────────────────────────────────────────
    def __init__(self, fft_size: int,
                 cov_frame_depth: int = COV_FRAME_DEPTH,
                 vote_window: int = VOTE_WINDOW_FRAMES,
                 vote_confirm: int = VOTE_CONFIRM_FRAMES):
        self.fft_size        = int(fft_size)
        self.cov_depth       = int(cov_frame_depth)
        self.vote_window     = int(vote_window)
        self.vote_confirm    = int(vote_confirm)

        # Module A: raw PSD ring buffer
        self._psd_buffer: Deque[_FrameRecord] = deque(maxlen=self.cov_depth)

        # Module B: vote ring buffer
        self._vote_buffer: Deque[_VoteRecord] = deque(maxlen=self.vote_window)

        # Diagnostics
        self._stats = {
            'frames_seen':        0,
            'mme_computed':       0,
            'shoulders_found':    0,
            'votes_confirmed':    0,
            'votes_rejected':     0,
        }

    # ─────────────────────────────────────────────────────────────────────
    # PUBLIC ENTRY POINT
    # ─────────────────────────────────────────────────────────────────────
    def augment(self,
                psd_raw:      np.ndarray,
                display_psd:  np.ndarray,
                carrier_span: Tuple[int, int],
                carrier_cf:   float,
                intf_hits:    List[Dict],
                noise_floor:  float,
                frame_idx:    int = 0,
                freq_axis:    Optional[np.ndarray] = None,
                ) -> List[Dict]:
        """
        Augment detection output for ONE carrier span.

        Parameters
        ----------
        psd_raw : ndarray
            Unsmoothed PSD (pre-EMA, pre-Fast-AD). Used for MME only.
        display_psd : ndarray
            Whatever PSD the caller uses for detection/drawing. Used for
            shoulder detection and classification features.
        carrier_span : (r, f)
            Carrier bin indices (same as in caller).
        carrier_cf : float
            Carrier center freq in Hz.
        intf_hits : list of dict
            Existing hits from detect_interference_in_carrier(). Kept intact;
            new fields are APPENDED into each dict.
        noise_floor : float
            Global noise floor (dB).
        frame_idx : int
            Monotonically increasing frame counter (for vote bookkeeping).
        freq_axis : ndarray (optional)
            Full freq_axis. Required only if returning freq-domain shoulder
            hits; if omitted, shoulder detection still runs but reports bin
            indices only.

        Returns
        -------
        list of dict
            Original hits with these ADDED fields:
                'mme_confidence'     (float ∈ [0, 1], higher = more persistent)
                'majority_confirmed' (bool, True if M-of-N vote passes)
                'vote_count'         (int, hits in last N frames)
                'probs'              (dict of class → probability)
                'top_class'          (str, argmax of probs)
            Plus any shoulder/CUC hits newly discovered by module C, with
                'method' = 'shoulder_asym' or 'shoulder_env'
                'source' = 'confidence_engine'
        """
        self._stats['frames_seen'] += 1

        # ── Module A: push this frame's raw PSD for future covariance calls
        self._push_psd_frame(psd_raw, noise_floor, frame_idx)

        r, f = int(carrier_span[0]), int(carrier_span[1])

        # ── Module C: shoulder detection (runs FIRST so its hits get A/B/D)
        shoulder_hits = self._detect_shoulder(display_psd, r, f, freq_axis)
        if shoulder_hits:
            self._stats['shoulders_found'] += len(shoulder_hits)
        all_hits = list(intf_hits) + shoulder_hits

        # ── Module A per-hit: MME confidence
        for h in all_hits:
            h['mme_confidence'] = self._mme_confidence_for_hit(h, r, f, freq_axis)

        # ── Module B: majority-vote bookkeeping (must be done exactly once
        #              per frame per carrier; caller invokes augment per span)
        self._register_vote_frame(carrier_cf, all_hits, frame_idx)
        for h in all_hits:
            count = self._count_vote(carrier_cf, h)
            h['vote_count']         = count
            h['majority_confirmed'] = (count >= self.vote_confirm)
            if h['majority_confirmed']:
                self._stats['votes_confirmed'] += 1
            else:
                self._stats['votes_rejected'] += 1

        # ── Module D: classification probabilities
        for h in all_hits:
            probs = self._classify_probs(h, r, f, carrier_cf, display_psd,
                                         noise_floor)
            h['probs']     = probs
            h['top_class'] = max(probs, key=probs.get) if probs else 'unknown'

        return all_hits

    # ─────────────────────────────────────────────────────────────────────
    def stats(self) -> Dict[str, int]:
        """Return a copy of internal diagnostics."""
        return dict(self._stats)

    def reset(self):
        """Clear ring buffers (e.g. on meta-update / sample-rate change)."""
        self._psd_buffer.clear()
        self._vote_buffer.clear()

    # ═════════════════════════════════════════════════════════════════════
    # MODULE A — TEMPORAL COVARIANCE (MME)
    # ═════════════════════════════════════════════════════════════════════

    def _push_psd_frame(self, psd_raw: np.ndarray, noise: float,
                        frame_idx: int):
        """Append raw PSD frame to ring buffer. O(N) copy."""
        if psd_raw is None or len(psd_raw) == 0:
            return
        if len(psd_raw) != self.fft_size:
            # FFT size changed (meta update); reset and accept new size.
            self.fft_size = len(psd_raw)
            self._psd_buffer.clear()
        # Only store unique frames (avoid duplicate same-frame calls across
        # multiple carriers stacking identical records).
        if self._psd_buffer and self._psd_buffer[-1].frame_idx == frame_idx:
            return
        self._psd_buffer.append(_FrameRecord(
            psd=psd_raw.astype(np.float32, copy=True),
            noise=float(noise),
            frame_idx=int(frame_idx),
        ))

    def _mme_confidence_for_hit(self, hit: Dict, carr_r: int, carr_f: int,
                                freq_axis: Optional[np.ndarray]) -> float:
        """
        Compute MME-derived confidence in [0, 1] for a single hit.

        Theory (Marchenko-Pastur):
            Under H0 (noise only), for a K×w covariance matrix with
            c = K/w (K frames, w freq bins in the hit span), the eigenvalue
            ratio λ_max / λ_min is bounded by:
                bound_upper = (1 + √c)² / (1 - √c)²   for c < 1
            Under H1 (structured signal present), λ_max is pushed above the
            upper MP edge → ratio ≫ bound_upper.

        We map (ratio / bound_upper) → [0, 1] via a tanh squasher so a
        single scalar feeds downstream logic (rendering, gating, logging).
        """
        if len(self._psd_buffer) < max(3, self.cov_depth // 2):
            return 0.5   # neutral — not enough history yet

        # Resolve hit's bin span
        span = self._hit_to_bins(hit, freq_axis, carr_r, carr_f)
        if span is None:
            return 0.5
        s_r, s_f = span
        w = s_f - s_r + 1
        if w < COV_MIN_SPAN_BINS:
            return 0.5

        K = len(self._psd_buffer)
        # Need K < w for a stable covariance; if not, truncate history
        if K >= w:
            K = max(3, w - 1)
        try:
            # Build K × w matrix of raw PSD slices (subtract per-frame mean)
            Y = np.empty((K, w), dtype=np.float32)
            for i, rec in enumerate(list(self._psd_buffer)[-K:]):
                slice_ = rec.psd[s_r:s_f + 1]
                if len(slice_) != w:   # safety for FFT-size changes mid-run
                    return 0.5
                Y[i] = slice_ - np.mean(slice_)

            # Sample covariance (K × K) — smaller matrix, cheaper eigendecomp
            M = (Y @ Y.T) / float(w)

            # Eigenvalues (K is small, typically 6 → negligible cost)
            eigs = np.linalg.eigvalsh(M)
            eigs = np.clip(eigs, _EPS, None)
            lam_max = float(eigs[-1])
            lam_min = float(eigs[0])
            if lam_min <= _EPS:
                return 0.5
            ratio = lam_max / lam_min

            # MP bound
            c = K / float(w)
            if c >= 1.0:
                return 0.5   # theory assumes c < 1
            mp_bound_upper = (1.0 + np.sqrt(c)) ** 2 / \
                             (1.0 - np.sqrt(c)) ** 2
            mp_bound_upper *= COV_MME_NOISE_MARGIN

            # Squash (ratio / bound) → [0, 1]
            if mp_bound_upper <= 0:
                return 0.5
            excess = max(0.0, ratio / mp_bound_upper - 1.0)
            conf   = float(np.tanh(excess))   # 0 when ratio = bound, →1 for spike
            self._stats['mme_computed'] += 1
            return conf
        except np.linalg.LinAlgError:
            return 0.5

    # ═════════════════════════════════════════════════════════════════════
    # MODULE B — MAJORITY-VOTE PERSISTENCE
    # ═════════════════════════════════════════════════════════════════════

    def _register_vote_frame(self, carrier_cf: float, hits: List[Dict],
                             frame_idx: int):
        """Record this frame's interference fingerprints for this carrier."""
        # If a record for this frame already exists (multiple carriers in
        # same update() pass), add keys to it. Otherwise create new.
        if self._vote_buffer and self._vote_buffer[-1].frame_idx == frame_idx:
            rec = self._vote_buffer[-1]
        else:
            rec = _VoteRecord(frame_idx=frame_idx)
            self._vote_buffer.append(rec)
        for h in hits:
            rec.keys.add(self._vote_key(carrier_cf, h))

    def _count_vote(self, carrier_cf: float, hit: Dict) -> int:
        """Count how many frames in the ring buffer contain this hit's key."""
        key = self._vote_key(carrier_cf, hit)
        return sum(1 for rec in self._vote_buffer if key in rec.keys)

    @staticmethod
    def _vote_key(carrier_cf: float, hit: Dict) -> Tuple[int, int, int]:
        """
        Bucketize (carrier_cf, intf_center, intf_width) into a
        frame-stable hashable key. Buckets absorb small jitter.
        """
        c_b = int(round(carrier_cf / VOTE_FREQ_BUCKET_HZ))
        i_c = 0.5 * (float(hit.get('start_freq', 0.0)) +
                     float(hit.get('end_freq',   0.0)))
        i_b = int(round(i_c / VOTE_FREQ_BUCKET_HZ))
        i_w = abs(float(hit.get('end_freq',   0.0)) -
                  float(hit.get('start_freq', 0.0)))
        w_b = int(round(i_w / VOTE_WIDTH_BUCKET_HZ))
        return (c_b, i_b, w_b)

    # ═════════════════════════════════════════════════════════════════════
    # MODULE C — SHOULDER / ENVELOPE-DEVIATION DETECTOR
    # ═════════════════════════════════════════════════════════════════════

    def _detect_shoulder(self, psd: np.ndarray, r: int, f: int,
                         freq_axis: Optional[np.ndarray]) -> List[Dict]:
        """
        Detect shoulder-interference and carrier-on-carrier lift that the
        narrow median-envelope bump detector can miss.

        Two independent sub-tests — both must be tried, either one triggers:

        (1) SLOPE-ASYMMETRY TEST
            Compare mean |gradient| on left EDGE_FRAC and right EDGE_FRAC.
            A clean carrier: both shoulders fall at similar rates.
            A shoulder-interfered carrier: one side has a broken/stretched
            slope (gradient magnitude differs ≥ SHOULDER_ASYMMETRY_THR).

        (2) ENVELOPE DEVIATION TEST
            Fit a "clean carrier reference" = trapezoidal boxcar of the
            carrier's central plateau level. Any contiguous region where
            psd - reference exceeds SHOULDER_ENVELOPE_LIFT_DB for ≥ N bins
            is flagged as a lift.

        Note: this runs OUTSIDE detect_interference_in_carrier and
        therefore does not interact with its bump/variance/curvature
        thresholds. It sees the WHOLE carrier at once, which is precisely
        why it catches wide shoulder lifts that local detectors miss.
        """
        hits: List[Dict] = []
        w = f - r + 1
        if w < SHOULDER_MIN_CARRIER_BINS:
            return hits
        seg = np.asarray(psd[r:f + 1], dtype=np.float32)
        if seg.size < SHOULDER_MIN_CARRIER_BINS:
            return hits

        # ── (1) Slope-asymmetry ─────────────────────────────────────────
        edge_n = max(3, int(w * SHOULDER_EDGE_FRAC))
        left_edge  = seg[:edge_n]
        right_edge = seg[-edge_n:]
        # Use mean absolute gradient (more robust than single linear fit
        # when edges are jagged)
        s_L = float(np.mean(np.abs(np.diff(left_edge))))  + _EPS
        s_R = float(np.mean(np.abs(np.diff(right_edge)))) + _EPS
        asym = abs(s_L - s_R) / max(s_L, s_R)
        if asym > SHOULDER_ASYMMETRY_THR:
            # Flag the weaker-slope side as shoulder lift
            if s_L < s_R:
                # Left side is too gradual → shoulder is on left
                lift_r, lift_f = r, r + edge_n - 1
            else:
                lift_r, lift_f = f - edge_n + 1, f
            hits.append(self._make_shoulder_hit(
                psd, lift_r, lift_f, freq_axis,
                method='shoulder_asym', score=float(asym),
            ))

        # ── (2) Envelope deviation ──────────────────────────────────────
        # Reference level = 75th percentile of the carrier's central 60%
        # (avoids being pulled up by the very lift we're hunting).
        core_r = r + int(0.20 * w)
        core_f = f - int(0.20 * w)
        if core_f > core_r + 3:
            ref_level = float(np.percentile(psd[core_r:core_f + 1], 75))
        else:
            ref_level = float(np.percentile(seg, 75))

        # Residual against a boxcar at ref_level
        residual = seg - ref_level
        mask = residual > SHOULDER_ENVELOPE_LIFT_DB
        # Find contiguous runs
        if mask.any():
            edges = np.diff(mask.astype(np.int8))
            rises = np.where(edges == 1)[0] + 1
            falls = np.where(edges == -1)[0] + 1
            if mask[0]:  rises = np.insert(rises, 0, 0)
            if mask[-1]: falls = np.append(falls, len(mask))
            for a_r, a_f in zip(rises, falls):
                if (a_f - a_r) < SHOULDER_MIN_LIFT_BINS:
                    continue
                # Skip if this run already overlaps the slope-asym hit
                lift_r_abs = r + a_r
                lift_f_abs = r + min(a_f, len(mask)) - 1
                # Suppress duplicates against asym detection
                dup = any(
                    self._bin_overlap(lift_r_abs, lift_f_abs,
                                      h['_bin_r'], h['_bin_f']) > 0.5
                    for h in hits
                )
                if dup:
                    continue
                lift_peak_bin = int(np.argmax(seg[a_r:a_f])) + a_r
                hits.append(self._make_shoulder_hit(
                    psd, lift_r_abs, lift_f_abs, freq_axis,
                    method='shoulder_env',
                    score=float(residual[lift_peak_bin]),
                ))
        return hits

    @staticmethod
    def _bin_overlap(a1: int, a2: int, b1: int, b2: int) -> float:
        """Jaccard overlap of two bin intervals."""
        inter = max(0, min(a2, b2) - max(a1, b1) + 1)
        union = max(a2, b2) - min(a1, b1) + 1
        return inter / union if union > 0 else 0.0

    @staticmethod
    def _make_shoulder_hit(psd: np.ndarray, r_abs: int, f_abs: int,
                           freq_axis: Optional[np.ndarray],
                           method: str, score: float) -> Dict:
        r_abs = max(0, int(r_abs))
        f_abs = max(r_abs, int(f_abs))
        if freq_axis is not None and len(freq_axis) > f_abs:
            f_start = float(freq_axis[r_abs])
            f_end   = float(freq_axis[f_abs])
            f_peak  = float(freq_axis[
                r_abs + int(np.argmax(psd[r_abs:f_abs + 1]))
            ])
        else:
            f_start = float(r_abs)
            f_end   = float(f_abs)
            f_peak  = 0.5 * (f_start + f_end)
        strength = float(score)
        return {
            'start_freq':  f_start,
            'end_freq':    f_end,
            'peak_freq':   f_peak,
            'strength_db': strength,
            'method':      method,
            'is_gap':      False,
            'source':      'confidence_engine',
            '_bin_r':      r_abs,     # internal, used for overlap dedup
            '_bin_f':      f_abs,
        }

    # ═════════════════════════════════════════════════════════════════════
    # MODULE D — CLASSIFICATION CONFIDENCE
    # ═════════════════════════════════════════════════════════════════════

    def _classify_probs(self, hit: Dict, carr_r: int, carr_f: int,
                        carrier_cf: float, psd: np.ndarray,
                        noise_floor: float) -> Dict[str, float]:
        """
        Return a probability-like vector over interference classes using
        feature-based soft scoring. Not calibrated — meant as a relative
        confidence across classes for the SAME hit.

        Classes:
            CW          — narrow spike (modern, jammer-like)
            shoulder    — asymmetric edge lift (adjacent-channel leakage)
            overlap     — wide deep gap (carrier-under-carrier with split)
            narrowband  — narrow, strong, possibly unauth spike
            noise_rise  — wide, weak elevation (noise-floor lift)
            unknown     — residual mass

        Scoring is done in logits, then softmax normalized. Weights chosen
        so the argmax is stable and interpretable; tune from labeled data
        when available.
        """
        # ── Feature extraction ──
        df = self._bin_spacing(psd)
        start_hz = float(hit.get('start_freq', 0.0))
        end_hz   = float(hit.get('end_freq',   0.0))
        peak_hz  = float(hit.get('peak_freq', 0.5 * (start_hz + end_hz)))
        strength = float(hit.get('strength_db', 0.0))
        method   = str(hit.get('method', ''))
        is_gap   = bool(hit.get('is_gap', False))

        width_hz   = abs(end_hz - start_hz)
        width_bins = width_hz / df if df > 0 else 0.0

        # Position within carrier: 0 = left edge, 1 = right edge, 0.5 = center
        carr_left_hz  = self._freq_of_bin(psd, carr_r)
        carr_right_hz = self._freq_of_bin(psd, carr_f)
        span_hz       = max(_EPS, carr_right_hz - carr_left_hz)
        pos_norm      = (peak_hz - carr_left_hz) / span_hz
        pos_norm      = float(np.clip(pos_norm, 0.0, 1.0))
        edge_prox     = min(pos_norm, 1.0 - pos_norm)  # small near edges

        # ── Logits ──
        L = {
            'CW':         0.0,
            'shoulder':   0.0,
            'overlap':    0.0,
            'narrowband': 0.0,
            'noise_rise': 0.0,
            'unknown':    0.5,   # prior
        }

        # CW: very narrow, moderately strong, INSIDE carrier
        if width_bins <= CLS_CW_MAX_WIDTH_BINS:
            L['CW'] += 1.5
            if strength >= CLS_CW_MIN_STRENGTH_DB:
                L['CW'] += 1.5
            # Narrowband is distinguished from CW by being stronger AND
            # nearer the edge / outside main carrier
            if edge_prox < 0.1 or strength >= 2 * CLS_CW_MIN_STRENGTH_DB:
                L['narrowband'] += 1.2

        # Shoulder: method tells us directly, AND edge_prox is low
        if method.startswith('shoulder_'):
            L['shoulder'] += 2.5
        if edge_prox < 0.12 and width_bins > CLS_CW_MAX_WIDTH_BINS:
            L['shoulder'] += 1.0

        # Overlap / CUC: gap method with deep depth
        if is_gap or method == 'gap':
            if strength >= CLS_OVERLAP_MIN_DEPTH_DB:
                L['overlap'] += 2.5
            else:
                L['overlap'] += 0.8

        # Noise rise: wide and weak
        if width_bins > 10 and strength < CLS_NOISE_RISE_MAX_STRENGTH:
            L['noise_rise'] += 1.8

        # Method hints from existing detectors
        if 'variance' in method:
            L['noise_rise'] += 0.4
            L['shoulder']   += 0.2
        if 'bump' in method and width_bins <= 6:
            L['CW'] += 0.5
        if 'curvature' in method:
            L['overlap']  += 0.3
            L['shoulder'] += 0.2

        # MME confidence (if already computed) → boost whichever class leads
        mme = float(hit.get('mme_confidence', 0.5))
        if mme > 0.7:
            top = max(L, key=L.get)
            L[top] += 0.6

        # ── Softmax ──
        keys = list(L.keys())
        logits = np.array([L[k] for k in keys], dtype=np.float64)
        logits -= logits.max()
        exps = np.exp(logits)
        probs = exps / exps.sum()
        return {k: float(p) for k, p in zip(keys, probs)}

    # ═════════════════════════════════════════════════════════════════════
    # HELPERS
    # ═════════════════════════════════════════════════════════════════════

    def _hit_to_bins(self, hit: Dict, freq_axis: Optional[np.ndarray],
                     carr_r: int, carr_f: int
                     ) -> Optional[Tuple[int, int]]:
        """Map a hit's freq span back to PSD bin indices."""
        # Prefer internal bin indices when available (shoulder hits)
        if '_bin_r' in hit and '_bin_f' in hit:
            return int(hit['_bin_r']), int(hit['_bin_f'])
        if freq_axis is None or len(freq_axis) == 0:
            return (int(carr_r), int(carr_f))
        try:
            s = int(np.searchsorted(freq_axis, float(hit['start_freq'])))
            e = int(np.searchsorted(freq_axis, float(hit['end_freq'])))
            s = max(0, min(s, len(freq_axis) - 1))
            e = max(0, min(e, len(freq_axis) - 1))
            if e < s:
                s, e = e, s
            return (s, e)
        except (KeyError, TypeError, ValueError):
            return (int(carr_r), int(carr_f))

    def _bin_spacing(self, psd: np.ndarray) -> float:
        """Rough bin spacing from the latest stored frame (in Hz)."""
        # We don't store freq_axis; callers pass it in augment() when they
        # need freq-space shoulder output. For classification features we
        # only need a length-normalized estimate. Fallback to 1.0 if no
        # history — then width_bins collapses to width_hz which is still a
        # monotone feature and the classifier still functions.
        if not self._psd_buffer:
            return 1.0
        # Heuristic: assume 20 MHz over fft_size bins if nothing else known.
        return 20e6 / max(1, self.fft_size)

    def _freq_of_bin(self, psd: np.ndarray, bin_idx: int) -> float:
        """Rough absolute freq estimate — same heuristic as _bin_spacing."""
        return float(bin_idx) * self._bin_spacing(psd)


# ═════════════════════════════════════════════════════════════════════════════
# QUICK SELF-TEST
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Smoke test: synthesize 10 frames of a wideband carrier with a shoulder
    # lift on the right side, verify shoulder detector fires and MME
    # confidence is high.
    import numpy as _np
    _rng = _np.random.default_rng(0)
    FFT = 2048
    eng = ConfidenceEngine(fft_size=FFT)

    # Build a noise floor + wide carrier (bins 800:1200) with right shoulder lift
    freq = _np.linspace(60e6, 80e6, FFT)
    for fi in range(12):
        psd = -80 + _rng.normal(0, 1.5, FFT).astype(_np.float32)
        psd[800:1200] += 40.0   # main carrier plateau
        # Shoulder lift on right side (bins 1200:1280)
        psd[1180:1260] += 8.0
        carrier_r, carrier_f = 800, 1280
        carrier_cf = 0.5 * (freq[carrier_r] + freq[carrier_f])
        pre_existing = []   # imagine the variance detector missed the shoulder
        out = eng.augment(
            psd_raw=psd, display_psd=psd,
            carrier_span=(carrier_r, carrier_f),
            carrier_cf=carrier_cf, intf_hits=pre_existing,
            noise_floor=-80.0, frame_idx=fi, freq_axis=freq,
        )
        if fi == 11:
            print(f"[SELF-TEST] frame {fi}: {len(out)} hits returned")
            for h in out:
                print(f"  method={h['method']:20s}  "
                      f"strength={h['strength_db']:+.2f} dB  "
                      f"mme_conf={h['mme_confidence']:.3f}  "
                      f"vote={h['vote_count']}/{eng.vote_window}  "
                      f"confirmed={h['majority_confirmed']}  "
                      f"class={h['top_class']:10s}  "
                      f"P={h['probs'][h['top_class']]:.2f}")
    print("\n[SELF-TEST] stats:", eng.stats())
