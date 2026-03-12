"""
strategies.py — Cascade Momentum & Regime Divergence
=====================================================
IMPORTANT: This file must NOT import AlgorithmImports.
           It uses only standard Python + numpy.
           The algo instance is passed in via setup().

Create this file in QC using the "+" button in the project
file tree. Name it exactly: strategies.py
"""

from collections import deque
import numpy as np


class RollingBuffer:
    def __init__(self, size):
        self.size = size
        self._data = deque(maxlen=size)
    def add(self, v): self._data.append(v)
    @property
    def is_ready(self): return len(self._data) == self.size
    @property
    def count(self): return len(self._data)
    def to_array(self): return np.array(self._data)


# ═══════════════════════════════════════════════════════════
# CASCADE MOMENTUM
# ═══════════════════════════════════════════════════════════

class CascadeMomentumStrategy:
    def __init__(self, p=None):
        d = {"vix_lookback":20,"vix_spike_threshold":2.0,
             "confirmation_required":2,"confirmation_lookback":3,
             "confirmation_threshold":0.5,"cascade_delay_days":1,
             "cooldown_days":10,"energy_filter":True,
             "energy_momentum_lookback":5,"energy_momentum_threshold":0.02,
             "energy_ticker":"USO",
             "use_vix_roc_filter":False,"vix_roc_lookback":3,
             "vix_roc_threshold":0.15,
             "use_asymmetric_sizing":False,"asym_vix_lo":2.0,
             "asym_vix_hi":3.0,"asym_scale_min":0.5,"asym_scale_max":1.0,
             "use_per_instrument_cooldown":True}
        self.p = {**d, **(p or {})}
        self.name = "Cascade Momentum"

    def setup(self, algo, vix_sym, tradeable):
        self.algo, self.tradeable = algo, tradeable
        bs = max(self.p["vix_lookback"],
                 self.p["confirmation_lookback"],
                 self.p["energy_momentum_lookback"],
                 self.p.get("vix_roc_lookback",3)+1) + 1
        self.vix_w = RollingBuffer(self.p["vix_lookback"])
        self.vix_px = RollingBuffer(bs)
        self.pw = {t: RollingBuffer(bs) for t in tradeable}
        self.triggered = False
        self.trig_day = 0
        self.trig_vz = 0.0
        self.last_trig = -9999
        self.day = 0
        self.cd = {}

    def warmup_period(self):
        return max(self.p["vix_lookback"],
                   self.p["energy_momentum_lookback"]) + 5

    def is_ready(self):
        return (self.vix_w.is_ready and
                all(w.is_ready for w in self.pw.values()))

    def update_windows(self, prices, vix):
        self.vix_w.add(vix)
        self.vix_px.add(vix)
        for t, px in prices.items():
            if t in self.pw:
                self.pw[t].add(px)

    def generate_signals(self, prices, vix, data):
        self.day += 1
        sigs = {}

        arr = self.vix_w.to_array()
        mu = np.mean(arr[:-1])
        sd = np.std(arr[:-1])
        if sd < 0.01:
            return sigs
        vz = (vix - mu) / sd

        if self.day <= 5 or self.day % 100 == 0:
            self.algo.debug(
                f"{self.algo.time.date()} VIX | "
                f"px={vix:.1f} z={vz:.2f}")

        # cooldown
        if self.p["use_per_instrument_cooldown"]:
            gok = True
        else:
            gok = ((self.day - self.last_trig)
                   >= self.p["cooldown_days"])

        # trigger
        if (vz >= self.p["vix_spike_threshold"]
                and not self.triggered and gok):

            # [MOD 2] RoC filter
            if (self.p["use_vix_roc_filter"]
                    and self.vix_px.is_ready):
                vp = self.vix_px.to_array()
                lb = min(self.p["vix_roc_lookback"],
                         len(vp) - 1)
                roc = ((vp[-1] - vp[-(lb+1)])
                       / vp[-(lb+1)])
                if roc < self.p["vix_roc_threshold"]:
                    return sigs

            # confirmation
            cc = 1
            for ct in ["GLD", "TLT"]:
                pw = self.pw.get(ct)
                if not pw or not pw.is_ready:
                    continue
                a = pw.to_array()
                lb = min(self.p["confirmation_lookback"],
                         len(a) - 1)
                ret = (a[-1] - a[-(lb+1)]) / a[-(lb+1)]
                rets = np.diff(a) / a[:-1]
                if len(rets) > 1:
                    rm = np.mean(rets)
                    rs = np.std(rets)
                    if (rs > 1e-8
                            and (ret - rm) / rs
                            >= self.p["confirmation_threshold"]):
                        cc += 1

            if cc >= self.p["confirmation_required"]:
                self.triggered = True
                self.trig_day = self.day
                self.trig_vz = vz
                self.last_trig = self.day
                self.algo.debug(
                    f"{self.algo.time.date()} CASCADE TRIGGER | "
                    f"z={vz:.2f} conf={cc}")

        # enter after delay
        if (self.triggered
                and (self.day - self.trig_day)
                >= self.p["cascade_delay_days"]):
            self.triggered = False

            # [MOD 5] asymmetric sizing
            sm = 1.0
            if self.p["use_asymmetric_sizing"]:
                lo = self.p["asym_vix_lo"]
                hi = self.p["asym_vix_hi"]
                mn = self.p["asym_scale_min"]
                mx = self.p["asym_scale_max"]
                if vz <= lo:
                    sm = mn
                elif vz >= hi:
                    sm = mx
                else:
                    sm = mn + (mx-mn) * (vz-lo) / (hi-lo)

            et = self.p["energy_ticker"]
            for t, info in self.tradeable.items():
                if self.algo.portfolio[info["symbol"]].invested:
                    continue
                if (self.p["use_per_instrument_cooldown"]
                        and self.cd.get(t, 0) > self.day):
                    continue

                # energy filter
                if t == et and self.p["energy_filter"]:
                    pw = self.pw.get(et)
                    if pw and pw.is_ready:
                        a = pw.to_array()
                        lb = min(
                            self.p["energy_momentum_lookback"],
                            len(a) - 1)
                        eret = ((a[-1] - a[-(lb+1)])
                                / a[-(lb+1)])
                        if eret < self.p["energy_momentum_threshold"]:
                            continue

                sigs[t] = {"dir": info["direction"],
                           "sm": sm}

        return sigs

    def on_exit(self, t):
        self.cd[t] = self.day + self.p["cooldown_days"]


# ═══════════════════════════════════════════════════════════
# REGIME DIVERGENCE
# ═══════════════════════════════════════════════════════════

class RegimeDivergenceStrategy:
    def __init__(self, p=None):
        d = {"zscore_lookback":20,"return_lookback":5,
             "stress_threshold":1.0,"min_stressed_count":3,
             "divergence_threshold":-0.5,"cooldown_days":5,
             "use_convergence_exit":False,
             "convergence_exit_threshold":0.5,
             "use_asymmetric_sizing":False,
             "asym_str_lo":3,"asym_str_hi":5,
             "asym_scale_min":0.5,"asym_scale_max":1.0,
             "use_per_instrument_cooldown":True}
        self.p = {**d, **(p or {})}
        self.name = "Regime Divergence"

    def setup(self, algo, vix_sym, tradeable):
        self.algo = algo
        self.tradeable = tradeable

        # build stress signs from tradeable directions
        self.SS = {}
        for t, info in tradeable.items():
            self.SS[t] = (-1.0 if info["direction"] == "short"
                          else 1.0)

        ws = (self.p["zscore_lookback"]
              + self.p["return_lookback"] + 5)
        self.vix_w = RollingBuffer(ws)
        self.pw = {t: RollingBuffer(ws) for t in tradeable}
        self.day = 0
        self.cd = {}
        self.pos = {}

    def warmup_period(self):
        return (self.p["zscore_lookback"]
                + self.p["return_lookback"] + 10)

    def is_ready(self):
        return (self.vix_w.is_ready and
                all(w.is_ready for w in self.pw.values()))

    def update_windows(self, prices, vix):
        self.vix_w.add(vix)
        for t, px in prices.items():
            if t in self.pw:
                self.pw[t].add(px)

    def generate_signals(self, prices, vix, data):
        self.day += 1
        sigs = {}
        conv = {}

        # z-scores
        zs = {}
        for t in self.tradeable:
            z = self._sz(t)
            if z is not None:
                zs[t] = z
        if len(zs) < len(self.tradeable):
            return sigs, conv

        vz = self._vz()

        # regime
        stressed = sum(1 for z in zs.values()
                       if z >= self.p["stress_threshold"])
        if (vz is not None
                and vz >= self.p["stress_threshold"]):
            stressed += 1
        regime = stressed >= self.p["min_stressed_count"]

        if self.day <= 5 or self.day % 100 == 0:
            zstr = " ".join(f"{t}={z:.2f}"
                            for t, z in zs.items())
            vzs = (f"{vz:.2f}" if vz is not None
                   else "N/A")
            self.algo.debug(
                f"{self.algo.time.date()} REGIME | "
                f"str={stressed} vz={vzs} | {zstr}")

        # [MOD 5] asymmetric sizing
        sm = 1.0
        if self.p["use_asymmetric_sizing"]:
            lo = self.p["asym_str_lo"]
            hi = self.p["asym_str_hi"]
            mn = self.p["asym_scale_min"]
            mx = self.p["asym_scale_max"]
            if stressed <= lo:
                sm = mn
            elif stressed >= hi:
                sm = mx
            else:
                sm = (mn + (mx-mn)
                      * (stressed-lo) / (hi-lo))

        # [MOD 3] convergence exits
        if self.p["use_convergence_exit"]:
            for t in list(self.pos.keys()):
                info = self.tradeable[t]
                if not self.algo.portfolio[
                        info["symbol"]].invested:
                    self.pos.pop(t, None)
                    continue
                if (t in zs and zs[t]
                        >= self.p["convergence_exit_threshold"]):
                    conv[t] = True
                    self.algo.debug(
                        f"{self.algo.time.date()} CONVERGE | "
                        f"{t} z={zs[t]:.2f}")

        # divergent entries
        if regime:
            for t, z in zs.items():
                info = self.tradeable[t]
                if self.algo.portfolio[
                        info["symbol"]].invested:
                    continue
                if (self.p["use_per_instrument_cooldown"]
                        and self.cd.get(t, 0) > self.day):
                    continue
                if z <= self.p["divergence_threshold"]:
                    d = ("long" if self.SS.get(t, 1) > 0
                         else "short")
                    sigs[t] = {"dir": d, "sm": sm}
                    self.pos[t] = {"day": self.day}
                    self.algo.debug(
                        f"{self.algo.time.date()} DIVERGE | "
                        f"{t} z={z:.2f} str={stressed} "
                        f"-> {d}")

        return sigs, conv

    def on_exit(self, t):
        self.cd[t] = self.day + self.p["cooldown_days"]
        self.pos.pop(t, None)

    def _sz(self, t):
        pw = self.pw.get(t)
        if not pw or not pw.is_ready:
            return None
        a = pw.to_array()
        rl = self.p["return_lookback"]
        zl = self.p["zscore_lookback"]
        if len(a) < rl + zl:
            return None
        cur = (a[-1] - a[-(rl+1)]) / a[-(rl+1)]
        h = []
        for i in range(zl):
            ei = -(i + 1)
            si = ei - rl
            if abs(si) > len(a):
                break
            h.append((a[ei] - a[si]) / a[si])
        if len(h) < 5:
            return None
        mu = np.mean(h)
        sd = np.std(h)
        if sd < 1e-8:
            return None
        return ((cur - mu) / sd) * self.SS.get(t, 1.0)

    def _vz(self):
        if not self.vix_w.is_ready:
            return None
        a = self.vix_w.to_array()
        zl = self.p["zscore_lookback"]
        if len(a) < zl:
            return None
        b = a[-zl-1:-1]
        if len(b) < 5:
            return None
        mu = np.mean(b)
        sd = np.std(b)
        if sd < 1e-8:
            return None
        return (a[-1] - mu) / sd
