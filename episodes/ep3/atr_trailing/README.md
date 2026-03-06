# EP3 - ATR Trailing Stop (configurable)

Trend-filtered entry with a volatility-adjusted (ATR) trailing stop. This
episode focuses on testing different ATR and EMA parameters.

Key details:
- Asset: configurable in main.py (default TSLA)
- Entry: price > EMA (default EMA200)
- Exit: highest price - (ATR * multiplier)
- Warmup: max(EMA period, ATR period)

Files:
- main.py
