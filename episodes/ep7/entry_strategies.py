from AlgorithmImports import *

"""
Entry Strategy Module
=====================
Each strategy class implements:
  - setup(algorithm)    → register indicators
  - is_ready()          → all indicators warmed up?
  - warmup_period()     → bars needed for warmup
  - should_enter(price, data=None) → returns True when entry signal fires
  - label()             → human-readable description for logs
"""


class DualEMACrossover:
    """
    Enter when a fast EMA crosses above a slow EMA.
    
    Params:
        fast_period: Fast EMA lookback (default 50)
        slow_period: Slow EMA lookback (default 200)
    """

    def __init__(self, fast_period=50, slow_period=200):
        self.fast_period = fast_period
        self.slow_period = slow_period
        self.prev_fast = None
        self.prev_slow = None

    def setup(self, algorithm, symbol):
        self.ema_fast = algorithm.ema(symbol, self.fast_period, Resolution.DAILY)
        self.ema_slow = algorithm.ema(symbol, self.slow_period, Resolution.DAILY)

    def is_ready(self):
        return self.ema_fast.is_ready and self.ema_slow.is_ready

    def warmup_period(self):
        return self.slow_period

    def should_enter(self, price, data=None):
        fast_val = self.ema_fast.current.value
        slow_val = self.ema_slow.current.value

        signal = False
        if self.prev_fast is not None and self.prev_slow is not None:
            was_below = self.prev_fast <= self.prev_slow
            now_above = fast_val > slow_val
            signal = was_below and now_above

        self.prev_fast = fast_val
        self.prev_slow = slow_val
        return signal

    def label(self):
        return f"Dual EMA Crossover ({self.fast_period}/{self.slow_period})"


class PullbackToEMA:
    """
    Buy the dip in a confirmed uptrend.
    
    Params:
        trend_period:    Long EMA to confirm uptrend (default 200)
        pullback_period: Short EMA to buy the dip at (default 20)
        buffer_pct:      How close to pullback EMA to trigger (default 1.0%)
        use_trend_filter: Require price > trend EMA (default True)
    """

    def __init__(self, trend_period=200, pullback_period=20, buffer_pct=1.0,
                 use_trend_filter=True):
        self.trend_period = trend_period
        self.pullback_period = pullback_period
        self.buffer_pct = buffer_pct
        self.use_trend_filter = use_trend_filter

    def setup(self, algorithm, symbol):
        self.ema_pullback = algorithm.ema(symbol, self.pullback_period, Resolution.DAILY)
        self.ema_trend = None
        if self.use_trend_filter:
            self.ema_trend = algorithm.ema(symbol, self.trend_period, Resolution.DAILY)

    def is_ready(self):
        if self.ema_trend and not self.ema_trend.is_ready:
            return False
        return self.ema_pullback.is_ready

    def warmup_period(self):
        if self.use_trend_filter:
            return max(self.trend_period, self.pullback_period)
        return self.pullback_period

    def should_enter(self, price, data=None):
        if self.use_trend_filter and price <= self.ema_trend.current.value:
            return False

        pullback_val = self.ema_pullback.current.value
        distance_pct = ((price - pullback_val) / pullback_val) * 100

        return 0 <= distance_pct <= self.buffer_pct

    def label(self):
        trend = f"trend EMA{self.trend_period}" if self.use_trend_filter else "no trend filter"
        return (f"Pullback to EMA{self.pullback_period} "
                f"({trend}, buffer {self.buffer_pct}%)")


class BreakoutWithVolume:
    """
    Donchian channel breakout confirmed by volume.
    
    Params:
        channel_period:    N-day high lookback (default 55)
        volume_sma_period: Average volume lookback (default 20)
        volume_multiplier: Required volume vs average (default 1.5)
    
    Note: We track the previous bar's channel high so we compare
    today's close against yesterday's N-day high — a true breakout.
    Volume is read from the data slice passed to should_enter().
    """

    def __init__(self, channel_period=55, volume_sma_period=20, volume_multiplier=1.5):
        self.channel_period = channel_period
        self.volume_sma_period = volume_sma_period
        self.volume_multiplier = volume_multiplier
        self.prev_channel_high = None

    def setup(self, algorithm, symbol):
        self.symbol = symbol
        # Use High field for a proper Donchian channel (not close)
        self.max_indicator = algorithm.MAX(symbol, self.channel_period, Resolution.DAILY,
                                          Field.HIGH)
        self.vol_sma = algorithm.SMA(symbol, self.volume_sma_period, Resolution.DAILY,
                                     Field.VOLUME)

    def is_ready(self):
        return self.max_indicator.is_ready and self.vol_sma.is_ready

    def warmup_period(self):
        return max(self.channel_period, self.volume_sma_period)

    def should_enter(self, price, data=None):
        if not self.vol_sma.is_ready or self.vol_sma.current.value == 0:
            return False

        current_channel_high = self.max_indicator.current.value

        # Need previous bar's channel high to detect a breakout
        if self.prev_channel_high is None:
            self.prev_channel_high = current_channel_high
            return False

        # True breakout: today's close breaks above yesterday's channel high
        above_channel = price > self.prev_channel_high

        # Update for next bar
        self.prev_channel_high = current_channel_high

        # Get current bar volume from the data slice
        if data is None or not data.contains_key(self.symbol):
            return False
        current_volume = data[self.symbol].volume

        volume_surge = current_volume > (self.vol_sma.current.value * self.volume_multiplier)

        return above_channel and volume_surge

    def label(self):
        return (f"Breakout {self.channel_period}d High "
                f"(vol {self.volume_multiplier}x avg{self.volume_sma_period})")


class RSIMomentumEntry:
    """
    Enter on RSI momentum confirmation, optionally in an uptrend.
    
    Params:
        rsi_period:       RSI lookback (default 14)
        rsi_threshold:    RSI level to cross above (default 55)
        ema_period:       Trend filter EMA (default 200)
        use_trend_filter: Require price > EMA (default True)
    """

    def __init__(self, rsi_period=14, rsi_threshold=55, ema_period=200,
                 use_trend_filter=True):
        self.rsi_period = rsi_period
        self.rsi_threshold = rsi_threshold
        self.ema_period = ema_period
        self.use_trend_filter = use_trend_filter
        self.prev_rsi = None

    def setup(self, algorithm, symbol):
        self.rsi = algorithm.RSI(symbol, self.rsi_period, MovingAverageType.WILDERS,
                                 Resolution.DAILY)
        self.ema = None
        if self.use_trend_filter:
            self.ema = algorithm.ema(symbol, self.ema_period, Resolution.DAILY)

    def is_ready(self):
        if self.ema and not self.ema.is_ready:
            return False
        return self.rsi.is_ready

    def warmup_period(self):
        if self.use_trend_filter:
            return max(self.rsi_period, self.ema_period)
        return self.rsi_period

    def should_enter(self, price, data=None):
        if self.use_trend_filter and price <= self.ema.current.value:
            self.prev_rsi = self.rsi.current.value
            return False

        current_rsi = self.rsi.current.value
        signal = False

        if self.prev_rsi is not None:
            was_below = self.prev_rsi < self.rsi_threshold
            now_above = current_rsi >= self.rsi_threshold
            signal = was_below and now_above

        self.prev_rsi = current_rsi
        return signal

    def label(self):
        trend = f"trend EMA{self.ema_period}" if self.use_trend_filter else "no trend filter"
        return f"RSI({self.rsi_period}) cross {self.rsi_threshold} ({trend})"


class ATRBreakout:
    """
    Enter when price breaks above a volatility envelope,
    optionally filtered by a long-term trend.
    
    Params:
        atr_period:       ATR lookback (default 14)
        atr_multiplier:   Envelope width in ATRs (default 1.5)
        ema_period:       Base EMA for the envelope (default 20)
        trend_period:     Long EMA trend filter (default 200)
        use_trend_filter: Require price > trend EMA (default True)
    """

    def __init__(self, atr_period=14, atr_multiplier=1.5, ema_period=20, trend_period=200,
                 use_trend_filter=True):
        self.atr_period = atr_period
        self.atr_multiplier = atr_multiplier
        self.ema_period = ema_period
        self.trend_period = trend_period
        self.use_trend_filter = use_trend_filter

    def setup(self, algorithm, symbol):
        self.atr = algorithm.atr(symbol, self.atr_period)
        self.ema_base = algorithm.ema(symbol, self.ema_period, Resolution.DAILY)
        self.ema_trend = None
        if self.use_trend_filter:
            self.ema_trend = algorithm.ema(symbol, self.trend_period, Resolution.DAILY)

    def is_ready(self):
        if self.ema_trend and not self.ema_trend.is_ready:
            return False
        return self.atr.is_ready and self.ema_base.is_ready

    def warmup_period(self):
        periods = [self.atr_period, self.ema_period]
        if self.use_trend_filter:
            periods.append(self.trend_period)
        return max(periods)

    def should_enter(self, price, data=None):
        if self.use_trend_filter and price <= self.ema_trend.current.value:
            return False

        upper_band = self.ema_base.current.value + (self.atr.current.value * self.atr_multiplier)
        return price > upper_band

    def label(self):
        trend = f"trend EMA{self.trend_period}" if self.use_trend_filter else "no trend filter"
        return (f"ATR Breakout EMA{self.ema_period} + "
                f"ATR({self.atr_period})x{self.atr_multiplier} "
                f"({trend})")


class RandomEntry:
    """
    Enter on a random coin flip each bar.
    
    Params:
        entry_probability: Chance of entering on any given bar (default 0.05 = 5%)
        seed:              Random seed for reproducibility (default 42)
    
    Why this exists:
        The ultimate benchmark. If the ATR trailing stop makes money
        with random entries, the exit is doing the heavy lifting.
        If ATR Breakout significantly outperforms this, the entry
        signal has genuine alpha beyond just "being in the market."
    
    Typical usage:
        Run multiple times with different seeds to get an average.
        A 5% probability produces roughly one entry attempt every
        20 bars, similar in frequency to the ATR breakout.
    """

    def __init__(self, entry_probability=0.05, seed=134):
        self.entry_probability = entry_probability
        self.seed = seed
        self.rng = None

    def setup(self, algorithm, symbol):
        import random
        self.rng = random.Random(self.seed)

    def is_ready(self):
        return True

    def warmup_period(self):
        return 0

    def should_enter(self, price, data=None):
        return self.rng.random() < self.entry_probability

    def label(self):
        return f"Random (p={self.entry_probability}, seed={self.seed})"


# ──────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────
ENTRY_STRATEGIES = {
    "dual_ema":          DualEMACrossover,
    "pullback":          PullbackToEMA,
    "breakout_volume":   BreakoutWithVolume,
    "rsi_momentum":      RSIMomentumEntry,
    "atr_breakout":      ATRBreakout,
    "random":            RandomEntry,
}
