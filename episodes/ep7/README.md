# EP7 - Clamped ATR Trailing Stop

ATR trailing stop study focused on one question: can a small change to the stop
logic improve trade behavior in a way that survives across conditions?

This episode compares three ATR stop modes:
- `live`: use the current ATR (original behavior)
- `locked`: freeze ATR at the entry value
- `clamped`: use the smaller of current ATR and entry ATR

The default EP7 configuration is TSLA with an ATR breakout entry and the
`clamped` stop mode.

Key details:
- Asset: configurable in `main.py` (default `TSLA`)
- Entry: one of the pluggable strategies in `entry_strategies.py` (default `atr_breakout`)
- Exit: highest price - (effective ATR * multiplier)
- ATR period: `14`
- ATR multiplier: `3.0`
- Stop mode: `live`, `locked`, or `clamped`
- Warmup: max(entry warmup, ATR period)

Entry options:
- `dual_ema`: Dual EMA crossover
- `pullback`: Pullback to EMA (buy the dip)
- `breakout_volume`: Donchian breakout with volume filter
- `rsi_momentum`: RSI threshold cross with optional trend filter
- `atr_breakout`: ATR volatility breakout
- `random`: Random baseline

How to use:
- Set `ticker`, `atr_multiplier`, and `self.atr_stop_mode` in `main.py`
- Set `ENTRY_STRATEGY` to the desired entry signal
- Optionally add overrides in `ENTRY_PARAMS`
- Run separate backtests for `live`, `locked`, and `clamped`
- Export trade logs if you want to compare matched trades, extra trades, and whipsaw effects

Files:
- `main.py`
- `entry_strategies.py`
