# EP6 - ATR Trailing Stop: Does the Exit Do the Heavy Lifting?

ATR trailing stop strategy with a random entry baseline to test whether the exit
signal alone is responsible for profitability. Includes a seed analyzer tool to
compare results across multiple random seeds.

Key details:
- Asset: configurable in main.py (default TSLA)
- Entry: one of the pluggable strategies in entry_strategies.py (default "random")
- Exit: highest price - (ATR(14) * multiplier)
- Warmup: max(entry warmup, ATR period)

Entry options:
- dual_ema: Dual EMA crossover
- pullback: Pullback to EMA (buy the dip)
- breakout_volume: Donchian breakout with volume filter
- rsi_momentum: RSI threshold cross with optional trend filter
- atr_breakout: ATR volatility breakout
- random: Random baseline (the focus of this episode)

How to use the random baseline:
- Set `ENTRY_STRATEGY = "random"` in main.py
- Run the same strategy with different seeds (e.g. 999, 299, 278, 123, 234, 345, 456, 567, 134, 42)
- Export each backtest's trade log as CSV
- Load all CSVs into seed_analyzer.jsx to compare equity curves and trade overlap

## Running seed_analyzer.jsx

The analyzer is a self-contained React component (no external UI dependencies).
Run it locally with Vite:

```bash
npm create vite@latest seed-analyzer -- --template react
cd seed-analyzer
cp /path/to/ep6/seed_analyzer.jsx src/App.jsx
npm install
npm run dev
```

Then open `http://localhost:5173` in your browser.

To use it:
1. Export trade logs from each QuantConnect backtest as CSV (Orders tab → Export)
2. Upload one CSV per seed using the file inputs in the UI
3. Compare equity curves, yearly rankings, trade timelines, and fuzzy-matched trades across seeds

Files:
- main.py
- entry_strategies.py
- seed_analyzer.jsx
