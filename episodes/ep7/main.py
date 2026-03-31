from AlgorithmImports import *
from entry_strategies import ENTRY_STRATEGIES

class ATRTrailingStop(QCAlgorithm):
    """
    ATR-Based Trailing Stop Strategy with pluggable entry signals.
    
    Exit (fixed):  Price drops below (Highest High - ATR * Multiplier)
    Entry (swap):  Change ENTRY_STRATEGY below to test different entries.
    """

    def initialize(self):
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        self.set_cash(100000)

        # ============================================
        # PARAMETERS
        # ============================================

        ticker = "TSLA"

        # --- Exit: ATR Trailing Stop (keep constant across tests) ---
        self.atr_period = 14
        self.atr_multiplier = 3.0

        # --- ATR Lockdown Mode ---
        # "live"     → use current ATR (original behavior)
        # "locked"   → freeze ATR at entry value (stop never widens)
        # "clamped"  → use min(current, entry) ATR (stop can tighten, never widen)
        self.atr_stop_mode = "clamped"

        # --- Entry: pick ONE strategy ---
        # Options:
        #   "dual_ema"        → Dual EMA Crossover
        #   "pullback"        → Pullback to EMA (buy the dip)
        #   "breakout_volume" → Donchian Breakout + Volume
        #   "rsi_momentum"    → RSI Cross + Trend Filter
        #   "atr_breakout"    → ATR Volatility Breakout
        ENTRY_STRATEGY = "atr_breakout"

        # Strategy-specific overrides (optional).
        # Pass any constructor kwargs here; omit to use defaults.
        # use_trend_filter=False removes the EMA200 requirement
        ENTRY_PARAMS = {
            # "dual_ema":        {"fast_period": 50, "slow_period": 200},
            # "pullback":        {"trend_period": 200, "pullback_period": 20, "buffer_pct": 1.0, "use_trend_filter": False},
            # "breakout_volume": {"channel_period": 55, "volume_sma_period": 20, "volume_multiplier": 1.5},
            # "rsi_momentum":    {"rsi_period": 14, "rsi_threshold": 55, "ema_period": 200, "use_trend_filter": False},
            # "atr_breakout":    {"atr_period": 14, "atr_multiplier": 1.5, "ema_period": 20, "trend_period": 200, "use_trend_filter": False},
            # "random":            { "entry_probability": 0.05, "seed": 42},  # 999, 299, 278, 123, 234, 345, 456, 567, 134, 42
        }

        # ============================================
        # SETUP
        # ============================================

        self.equity_symbol = self.add_equity(ticker, Resolution.DAILY).symbol
        self.ticker_name = ticker

        # Exit indicator (ATR for trailing stop)
        self.atr_indicator = self.atr(self.equity_symbol, self.atr_period)

        # Entry strategy — instantiate and wire up
        params = ENTRY_PARAMS.get(ENTRY_STRATEGY, {})
        self.entry = ENTRY_STRATEGIES[ENTRY_STRATEGY](**params)
        self.entry.setup(self, self.equity_symbol)

        # Warmup must cover both entry and exit indicators
        warmup = max(self.entry.warmup_period(), self.atr_period)
        self.set_warm_up(warmup, Resolution.DAILY)

        # Tracking
        self.highest_price = 0
        self.entry_price = 0
        self.entry_date = None
        self.entry_atr = 0
        self.trades = []

        self.debug(f"Entry strategy: {self.entry.label()}")
        self.debug(f"Exit strategy:  ATR({self.atr_period}) x {self.atr_multiplier} trailing stop [mode={self.atr_stop_mode}]")

    # ────────────────────────────────────────────
    # CORE LOOP
    # ────────────────────────────────────────────

    def on_data(self, data):
        if self.is_warming_up:
            return
        if not data.contains_key(self.equity_symbol) or data[self.equity_symbol] is None:
            return
        if not self.atr_indicator.is_ready or not self.entry.is_ready():
            return

        price = data[self.equity_symbol].close
        current_atr = self.atr_indicator.current.value

        if self.portfolio[self.equity_symbol].invested:
            self._check_exit(price, current_atr)
        else:
            self._check_entry(price, current_atr, data)

    def _check_entry(self, price, current_atr, data):
        if not self.entry.should_enter(price, data):
            return

        atr_pct = current_atr / price * 100
        initial_stop = price - (current_atr * self.atr_multiplier)
        stop_pct = (current_atr * self.atr_multiplier) / price * 100

        tag = (
            f"Signal:{self.entry.label()}"
            f"|EntryATR:{current_atr:.4f}"
            f"|EntryATR%:{atr_pct:.2f}"
            f"|Stop:{initial_stop:.2f}"
            f"|StopDist%:{stop_pct:.1f}"
        )

        self.set_holdings(self.equity_symbol, 1.0, tag=tag)
        self.highest_price = price
        self.entry_price = price
        self.entry_date = self.time.date()
        self.entry_atr = current_atr

        self.debug(
            f"{self.time.date()} BUY  | Price: ${price:.2f} | "
            f"Signal: {self.entry.label()} | "
            f"ATR: ${current_atr:.4f} ({atr_pct:.2f}%) | "
            f"Initial Stop: ${initial_stop:.2f} ({stop_pct:.1f}% below)"
        )

    def _check_exit(self, price, current_atr):
        self.highest_price = max(self.highest_price, price)

        # ATR lockdown: choose effective ATR for stop calculation
        if self.atr_stop_mode == "locked":
            effective_atr = self.entry_atr
        elif self.atr_stop_mode == "clamped":
            effective_atr = min(current_atr, self.entry_atr)
        else:  # "live" — original behavior
            effective_atr = current_atr

        stop_price = self.highest_price - (effective_atr * self.atr_multiplier)
        stop_pct = (self.highest_price - stop_price) / self.highest_price * 100

        if price < stop_price:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            exit_atr_pct = current_atr / price * 100
            entry_atr_pct = self.entry_atr / self.entry_price * 100
            effective_atr_pct = effective_atr / price * 100
            atr_expansion = (current_atr - self.entry_atr) / self.entry_atr * 100

            self.trades.append({
                "entry": self.entry_date,
                "exit": self.time.date(),
                "pnl_pct": pnl_pct,
            })

            tag = (
                f"PnL:{pnl_pct:+.1f}%"
                f"|Mode:{self.atr_stop_mode}"
                f"|EntryATR:{self.entry_atr:.4f}"
                f"|EntryATR%:{entry_atr_pct:.2f}"
                f"|ExitATR:{current_atr:.4f}"
                f"|ExitATR%:{exit_atr_pct:.2f}"
                f"|EffATR:{effective_atr:.4f}"
                f"|EffATR%:{effective_atr_pct:.2f}"
                f"|ATRchg:{atr_expansion:+.1f}%"
            )

            self.debug(
                f"{self.time.date()} EXIT | Price: ${price:.2f} | "
                f"Stop: ${stop_price:.2f} ({stop_pct:.1f}% from high) | "
                f"Mode: {self.atr_stop_mode} | "
                f"EntryATR: ${self.entry_atr:.4f} ({entry_atr_pct:.2f}%) | "
                f"ExitATR: ${current_atr:.4f} ({exit_atr_pct:.2f}%) | "
                f"EffATR: ${effective_atr:.4f} ({effective_atr_pct:.2f}%) | "
                f"ATR chg: {atr_expansion:+.1f}% | "
                f"PnL: {pnl_pct:+.1f}%"
            )

            self.liquidate(self.equity_symbol, tag=tag)
            self.highest_price = 0
            self.entry_price = 0
            self.entry_atr = 0

    # ────────────────────────────────────────────
    # END-OF-BACKTEST SUMMARY
    # ────────────────────────────────────────────

    def on_end_of_algorithm(self):
        total_return = (self.portfolio.total_portfolio_value - 100000) / 100000 * 100

        self.debug("=" * 60)
        self.debug(f"TICKER:  {self.ticker_name}")
        self.debug(f"ENTRY:   {self.entry.label()}")
        self.debug(f"EXIT:    ATR({self.atr_period}) x {self.atr_multiplier} trailing stop [mode={self.atr_stop_mode}]")
        self.debug(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.debug(f"Total Return: {total_return:+.1f}%")
        self.debug(f"Total Trades: {len(self.trades)}")

        if self.trades:
            winners = [t for t in self.trades if t["pnl_pct"] > 0]
            losers = [t for t in self.trades if t["pnl_pct"] <= 0]
            win_rate = len(winners) / len(self.trades) * 100

            self.debug(f"Win Rate: {win_rate:.1f}% ({len(winners)}W / {len(losers)}L)")

            if winners:
                avg_win = sum(t["pnl_pct"] for t in winners) / len(winners)
                best = max(t["pnl_pct"] for t in winners)
                self.debug(f"Avg Win:  {avg_win:+.1f}%  |  Best: {best:+.1f}%")
            if losers:
                avg_loss = sum(t["pnl_pct"] for t in losers) / len(losers)
                worst = min(t["pnl_pct"] for t in losers)
                self.debug(f"Avg Loss: {avg_loss:+.1f}%  |  Worst: {worst:+.1f}%")

        self.debug("=" * 60)
