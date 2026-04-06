from AlgorithmImports import *
from entry_strategies import ENTRY_STRATEGIES

class ATRTrailingStop(QCAlgorithm):
    """
    EP8: Viral Dip-Buying Strategies
    Exit: ATR Chandelier (clamped) — constant across all tests.
    Entry: Swap via ENTRY_STRATEGY parameter.
    """

    def initialize(self):
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        self.set_cash(100000)

        # ============================================
        # PARAMETERS — change these per test run
        # ============================================

        ticker = "TSLA"

        # --- Exit: ATR Chandelier (clamped) ---
        self.atr_period = 14
        self.atr_multiplier = 3.0

        # --- Entry: pick ONE ---
        # "three_red"    → Buy after 3 consecutive red days
        # "pct_crash"    → Buy after -5% drop in 2 days
        # "new_low"      → Buy when price < 20-day low
        # "gap_down"     → Buy when open gaps down >= 2%
        # "rsi_oversold" → Buy when RSI(14) crosses below 30
        ENTRY_STRATEGY = "three_red"

        ENTRY_PARAMS = {
            # "three_red":    {},
            # "pct_crash":    {"drop_pct": 5.0, "lookback": 2},
            # "new_low":      {"period": 20},
            # "gap_down":     {"gap_pct": 2.0},
            # "rsi_oversold": {"rsi_period": 14, "oversold": 30},
        }

        # ============================================
        # SETUP
        # ============================================

        self.equity_symbol = self.add_equity(ticker, Resolution.DAILY).symbol
        self.ticker_name = ticker

        self.atr_indicator = self.atr(self.equity_symbol, self.atr_period)

        params = ENTRY_PARAMS.get(ENTRY_STRATEGY, {})
        self.entry = ENTRY_STRATEGIES[ENTRY_STRATEGY](**params)
        self.entry.setup(self, self.equity_symbol)

        warmup = max(self.entry.warmup_period(), self.atr_period)
        self.set_warm_up(warmup, Resolution.DAILY)

        self.highest_price = 0
        self.entry_price = 0
        self.entry_atr = 0
        self.trades = []

    def on_data(self, data):
        if self.is_warming_up:
            return
        if not data.contains_key(self.equity_symbol) or data[self.equity_symbol] is None:
            return
        if not self.atr_indicator.is_ready:
            return

        price = data[self.equity_symbol].close
        current_atr = self.atr_indicator.current.value

        # Update strategy state every bar (tracks prices even while invested)
        # Must run BEFORE is_ready check — some strategies populate state here
        if hasattr(self.entry, 'update'):
            self.entry.update(price, data)

        if self.portfolio[self.equity_symbol].invested:
            self._check_exit(price, current_atr)
        elif self.entry.is_ready():
            self._check_entry(price, current_atr, data)

    def _check_entry(self, price, current_atr, data):
        if not self.entry.should_enter(price, data):
            return

        self.set_holdings(self.equity_symbol, 1.0)
        self.highest_price = price
        self.entry_price = price
        self.entry_atr = current_atr

    def _check_exit(self, price, current_atr):
        self.highest_price = max(self.highest_price, price)

        # Clamped: stop can tighten but never widen
        effective_atr = min(current_atr, self.entry_atr)
        stop_price = self.highest_price - (effective_atr * self.atr_multiplier)

        if price < stop_price:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            self.trades.append({"pnl_pct": pnl_pct})
            self.liquidate(self.equity_symbol)
            self.highest_price = 0
            self.entry_price = 0
            self.entry_atr = 0

    def on_end_of_algorithm(self):
        total_return = (self.portfolio.total_portfolio_value - 100000) / 100000 * 100
        self.debug(f"{'='*50}")
        self.debug(f"{self.ticker_name} | {self.entry.label()} | Clamped ATR x{self.atr_multiplier}")
        self.debug(f"Final: ${self.portfolio.total_portfolio_value:,.0f} | Return: {total_return:+.1f}%")
        self.debug(f"Trades: {len(self.trades)}")
        if self.trades:
            w = [t for t in self.trades if t["pnl_pct"] > 0]
            l = [t for t in self.trades if t["pnl_pct"] <= 0]
            self.debug(f"Win Rate: {len(w)/len(self.trades)*100:.0f}% ({len(w)}W/{len(l)}L)")
            if w:
                self.debug(f"Avg Win: {sum(t['pnl_pct'] for t in w)/len(w):+.1f}% | Best: {max(t['pnl_pct'] for t in w):+.1f}%")
            if l:
                self.debug(f"Avg Loss: {sum(t['pnl_pct'] for t in l)/len(l):+.1f}% | Worst: {min(t['pnl_pct'] for t in l):+.1f}%")
        self.debug(f"{'='*50}")
