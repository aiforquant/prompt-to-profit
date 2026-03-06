# EP2 - SMA200 Gated Strategy (QQQ)

Trend-following strategy that is either fully invested or fully in cash based
on price vs the 200-day SMA.

Key details:
- Asset: QQQ (daily)
- Entry: price > SMA200
- Exit: price < SMA200
- Warmup: 200 bars

Files:
- main.py
