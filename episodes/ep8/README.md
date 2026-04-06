# EP8 - Viral Dip-Buying Strategies

EP8 tests five popular dip-buying entries under one controlled exit:
a clamped ATR chandelier stop. The goal is not to find one universal winner,
but to compare how these viral entry ideas behave under the same exit logic.

This episode keeps the exit constant and swaps only the entry rule.

The default EP8 configuration is TSLA with the `three_red` entry.

Key details:
- Asset: configurable in `main.py` (default `TSLA`)
- Exit: clamped ATR chandelier
- ATR period: `14`
- ATR multiplier: `3.0`
- Start cash: `$100,000`
- Date range: `2011-01-01` to `2026-01-22`

Entry options:
- `three_red`: buy after 3 consecutive down candles
- `pct_crash`: buy after a configurable percent drop over a configurable lookback
- `new_low`: buy when price breaks below the rolling N-day low
- `gap_down`: buy after an overnight gap down of at least the configured threshold
- `rsi_oversold`: buy when RSI crosses below the oversold threshold

Default tuning:
- `three_red`: no extra parameters
- `pct_crash`: `drop_pct=5.0`, `lookback=2`
- `new_low`: `period=20`
- `gap_down`: `gap_pct=2.0`
- `rsi_oversold`: `rsi_period=14`, `oversold=30`

How to use:
- Set `ticker` in `main.py`
- Set `ENTRY_STRATEGY` in `main.py`
- Optionally add overrides in `ENTRY_PARAMS`
- Run one backtest per entry rule
- Compare end equity, trade count, win rate, and cross-ticker behavior

Files:
- `main.py`
- `entry_strategies.py`
