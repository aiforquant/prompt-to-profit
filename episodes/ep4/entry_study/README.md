# EP4 - Entry Study + ATR Trailing Stop

A fixed ATR trailing stop exit paired with multiple swappable entry signals to
compare their impact. Change ENTRY_STRATEGY in main.py to switch entries.

Key details:
- Asset: configurable in main.py (default AAPL)
- Entry: one of the entry strategies in entry_strategies.py
- Exit: highest price - (ATR * multiplier)
- Warmup: max(entry warmup, ATR period)

Entry options:
- dual_ema: Dual EMA crossover
- pullback: Pullback to EMA
- breakout_volume: Donchian breakout with volume filter
- rsi_momentum: RSI threshold cross with optional trend filter
- atr_breakout: ATR volatility breakout
- random: Random baseline

Files:
- main.py
- entry_strategies.py
