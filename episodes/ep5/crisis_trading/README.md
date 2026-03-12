# EP5 - Crisis Trading (configurable)

Crisis-focused multi-asset strategy that switches between two signal models:
Cascade Momentum and Regime Divergence. Change `STRATEGY` in `main.py` to
select the active model.

Key details:
- Assets: configurable basket in `main.py` (default GLD, TLT, ITA, optional USO)
- Entry: either VIX-triggered cascade momentum or stressed-regime divergence
- Exit: ATR trailing stop, with optional convergence and max-hold exits
- Warmup: max(strategy warmup, ATR period)

Strategy options:
- cascade: VIX spike trigger with confirmation, optional energy filter, and cooldowns
- divergence: stressed-regime detector that buys laggards and can exit on convergence

Files:
- main.py
- strategies.py
