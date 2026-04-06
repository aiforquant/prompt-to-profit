from AlgorithmImports import *

"""
Viral Dip-Buying Entry Strategies
==================================
EP8: Testing 5 viral trading strategies from social media.
Same ATR chandelier exit across all — only the entry changes.

Each strategy class implements:
  - setup(algorithm, symbol) → register indicators / state
  - is_ready()               → all indicators warmed up?
  - warmup_period()          → bars needed
  - should_enter(price, data) → True when entry signal fires
  - label()                  → human-readable name
"""


class ThreeRedDays:
    """
    Buy after 3 consecutive red (down) daily candles.
    Red = close < open.
    update() runs every bar to keep red count accurate.
    """

    def __init__(self):
        self.red_count = 0
        self._signal = False

    def setup(self, algorithm, symbol):
        self.symbol = symbol

    def is_ready(self):
        return True

    def warmup_period(self):
        return 0

    def update(self, price, data=None):
        """Called every bar from on_data, even while invested."""
        if data is None or not data.contains_key(self.symbol):
            return
        bar = data[self.symbol]
        if bar.close < bar.open:
            self.red_count += 1
        else:
            self.red_count = 0

        self._signal = self.red_count >= 3
        if self._signal:
            self.red_count = 0

    def should_enter(self, price, data=None):
        return self._signal

    def label(self):
        return "Three Red Days"


class PercentageCrash:
    """
    Buy after a -5% drop within 2 trading days.
    Tracks close from 2 bars ago vs current close.
    update() runs every bar to keep the window accurate.
    """

    def __init__(self, drop_pct=5.0, lookback=2):
        self.drop_pct = drop_pct
        self.lookback = lookback
        self.closes = []
        self._signal = False

    def setup(self, algorithm, symbol):
        self.symbol = symbol

    def is_ready(self):
        return len(self.closes) >= self.lookback

    def warmup_period(self):
        return self.lookback

    def update(self, price, data=None):
        """Called every bar from on_data, even while invested."""
        self.closes.append(price)
        if len(self.closes) > self.lookback + 1:
            self.closes.pop(0)

        self._signal = False
        if len(self.closes) > self.lookback:
            ref_price = self.closes[0]
            change_pct = (price - ref_price) / ref_price * 100
            self._signal = change_pct <= -self.drop_pct

    def should_enter(self, price, data=None):
        return self._signal

    def label(self):
        return f"{self.drop_pct}% Drop in {self.lookback} Days"


class New20DayLow:
    """
    Buy when price drops below the lowest close of the past N days.
    Uses QuantConnect MIN indicator on Close field.
    update() runs every bar to keep prev_min accurate.
    """

    def __init__(self, period=20):
        self.period = period
        self._signal = False

    def setup(self, algorithm, symbol):
        self.symbol = symbol
        self.min_indicator = algorithm.MIN(symbol, self.period, Resolution.DAILY, Field.CLOSE)
        self.prev_min = None

    def is_ready(self):
        return self.min_indicator.is_ready

    def warmup_period(self):
        return self.period

    def update(self, price, data=None):
        """Called every bar from on_data, even while invested."""
        current_min = self.min_indicator.current.value
        self._signal = False

        if self.prev_min is not None:
            self._signal = price < self.prev_min

        self.prev_min = current_min

    def should_enter(self, price, data=None):
        return self._signal

    def label(self):
        return f"New {self.period}-Day Low"


class GapDown:
    """
    Buy when today's open gaps down >= threshold% below yesterday's close.
    Signal fires on the same bar (buy at close after confirming the gap).
    update() runs every bar to keep prev_close accurate.
    """

    def __init__(self, gap_pct=2.0):
        self.gap_pct = gap_pct
        self.prev_close = None
        self._signal = False

    def setup(self, algorithm, symbol):
        self.symbol = symbol

    def is_ready(self):
        return self.prev_close is not None

    def warmup_period(self):
        return 1

    def update(self, price, data=None):
        """Called every bar from on_data, even while invested."""
        if data is None or not data.contains_key(self.symbol):
            return

        bar = data[self.symbol]
        self._signal = False

        if self.prev_close is not None:
            gap_pct = (bar.open - self.prev_close) / self.prev_close * 100
            self._signal = gap_pct <= -self.gap_pct

        self.prev_close = bar.close

    def should_enter(self, price, data=None):
        return self._signal

    def label(self):
        return f"Gap Down {self.gap_pct}%"


class RSIOversold:
    """
    Buy when RSI(14) drops below oversold threshold.
    Classic "buy oversold" signal from every beginner trading video.
    update() runs every bar to track RSI cross accurately.
    """

    def __init__(self, rsi_period=14, oversold=30):
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.prev_rsi = None
        self._signal = False

    def setup(self, algorithm, symbol):
        self.rsi = algorithm.RSI(symbol, self.rsi_period, MovingAverageType.WILDERS, Resolution.DAILY)

    def is_ready(self):
        return self.rsi.is_ready

    def warmup_period(self):
        return self.rsi_period

    def update(self, price, data=None):
        """Called every bar from on_data, even while invested."""
        current_rsi = self.rsi.current.value
        self._signal = False

        if self.prev_rsi is not None:
            was_above = self.prev_rsi >= self.oversold
            now_below = current_rsi < self.oversold
            self._signal = was_above and now_below

        self.prev_rsi = current_rsi

    def should_enter(self, price, data=None):
        return self._signal

    def label(self):
        return f"RSI({self.rsi_period}) Below {self.oversold}"


# ──────────────────────────────────────────────
# Registry
# ──────────────────────────────────────────────
ENTRY_STRATEGIES = {
    "three_red":       ThreeRedDays,
    "pct_crash":       PercentageCrash,
    "new_low":         New20DayLow,
    "gap_down":        GapDown,
    "rsi_oversold":    RSIOversold,
}
