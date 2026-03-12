from AlgorithmImports import *
from strategies import CascadeMomentumStrategy, RegimeDivergenceStrategy


class GeopoliticalStrategy(QCAlgorithm):

    def initialize(self):
        self.set_cash(100000)

        # ── TEST PERIOD — uncomment ONE ──────────────────
        self.set_start_date(2011, 1, 1);  self.set_end_date(2026, 1, 22)   # Full
        # self.set_start_date(2013, 6, 1);  self.set_end_date(2015, 6, 30) # Crimea+oil
        # self.set_start_date(2018, 1, 1);  self.set_end_date(2020, 6, 30) # Trade war
        # self.set_start_date(2021, 6, 1);  self.set_end_date(2023, 6, 30) # Russia-Ukraine
        # self.set_start_date(2023, 6, 1);  self.set_end_date(2025, 12, 31)# Mid-East

        # ── STRATEGY ─────────────────────────────────────
        STRATEGY = "cascade"  # "cascade" or "divergence"

        # ── INSTRUMENTS: (direction, size) ───────────────
        CASCADE_INSTRUMENTS = {
            "GLD": ("long",  0.40),
            "TLT": ("long",  0.20),
            "USO": ("long",  0.0),
            "ITA": ("long",  0.45),
        }

        DIVERGENCE_INSTRUMENTS = {
            "GLD": ("long",  0.35),
            "TLT": ("long",  0.30),
            "ITA": ("long",  0.35),
            "USO": ("long",  0.0),
        }

        # ── ATR EXIT ─────────────────────────────────────
        self.atr_period     = 14
        self.atr_multiplier = 2.5     # try 2.5 for cascade(Gull), 3.5 for cascade(Fly)

        # ── MOD SWITCHES ─────────────────────────────────
        USE_VIX_ROC          = False  # [MOD 2] Cascade: fast VIX spike required
        USE_CONVERGENCE_EXIT = True   # [MOD 3] Divergence: exit on z convergence
        USE_MAX_HOLD         = True   # [MOD 4] Force exit after N days
        USE_ASYMMETRIC_SIZE  = True   # [MOD 5] Scale size by signal intensity
        USE_PER_TICKER_CD    = True   # [MOD 6] Per-instrument cooldowns

        # ── [MOD 4] MAX HOLDING DAYS ─────────────────────
        self.use_max_hold  = USE_MAX_HOLD
        self.max_hold_days = {"cascade": 60, "divergence": 20}

        # ── STRATEGY PARAMS ──────────────────────────────
        CASCADE_P = {
            "vix_lookback": 14,
            "vix_spike_threshold": 2.0,
            "confirmation_required": 2,
            "confirmation_lookback": 3,
            "confirmation_threshold": 1.0,
            "cascade_delay_days": 0,
            "cooldown_days": 5,
            "energy_filter": True,
            "energy_momentum_lookback": 5,
            "energy_momentum_threshold": 0.02,
            "energy_ticker": "USO",
            "use_vix_roc_filter": USE_VIX_ROC,
            "vix_roc_lookback": 3,
            "vix_roc_threshold": 0.15,
            "use_asymmetric_sizing": USE_ASYMMETRIC_SIZE,
            "asym_vix_lo": 2.0,
            "asym_vix_hi": 3.5,
            "asym_scale_min": 0.5,
            "asym_scale_max": 1.0,
            "use_per_instrument_cooldown": USE_PER_TICKER_CD,
        }

        DIVERGE_P = {
            "zscore_lookback": 14,
            "return_lookback": 5,
            "stress_threshold": 1.0,
            "min_stressed_count": 3,
            "divergence_threshold": -0.8,
            "cooldown_days": 5,
            "use_convergence_exit": USE_CONVERGENCE_EXIT,
            "convergence_exit_threshold": 0.5,
            "use_asymmetric_sizing": USE_ASYMMETRIC_SIZE,
            "asym_str_lo": 3,
            "asym_str_hi": 5,
            "asym_scale_min": 0.5,
            "asym_scale_max": 1.0,
            "use_per_instrument_cooldown": USE_PER_TICKER_CD,
        }

        # ── SETUP ────────────────────────────────────────
        self.vix_symbol = self.add_index("VIX", Resolution.DAILY).symbol
        self.sname = STRATEGY
        INSTRUMENTS = CASCADE_INSTRUMENTS if STRATEGY == "cascade" else DIVERGENCE_INSTRUMENTS

        self.tradeable = {}
        for tk,(dr,sz) in INSTRUMENTS.items():
            if sz <= 0: continue
            sym = self.add_equity(tk, Resolution.DAILY).symbol
            self.tradeable[tk] = {"symbol":sym,"direction":dr,"size":sz,
                "atr":self.atr(sym,self.atr_period),
                "highest":0.0,"lowest":float("inf"),"entry_price":0.0,"entry_date":None}

        if STRATEGY == "cascade":
            self.strategy = CascadeMomentumStrategy(CASCADE_P)
        else:
            self.strategy = RegimeDivergenceStrategy(DIVERGE_P)
        self.strategy.setup(self, self.vix_symbol, self.tradeable)
        self.set_warm_up(max(self.strategy.warmup_period(), self.atr_period), Resolution.DAILY)

        self.trades=[]; self.last_vix=None; self.vix_n=0; self.bars=0
        sizes=" ".join(f"{t}={s*100:.0f}%" for t,(_,s) in INSTRUMENTS.items() if s>0)
        mods=[m for m,v in [("VIX_RoC",USE_VIX_ROC),("ConvExit",USE_CONVERGENCE_EXIT),
              ("MaxHold",USE_MAX_HOLD),("AsymSize",USE_ASYMMETRIC_SIZE),
              ("PerTickCD",USE_PER_TICKER_CD)] if v]
        self.debug(f"{self.strategy.name} | ATR {self.atr_period}x{self.atr_multiplier} | {sizes}")
        self.debug(f"Mods: {', '.join(mods) if mods else 'None'}")

    def on_data(self, data):
        if self.is_warming_up: return
        self.bars += 1
        vix = None
        if data.contains_key(self.vix_symbol) and data[self.vix_symbol] is not None:
            vix = data[self.vix_symbol].close
            if vix and vix > 0: self.last_vix=vix; self.vix_n+=1
        if (vix is None or vix<=0) and self.last_vix: vix=self.last_vix
        if vix is None: return

        px = {}
        for t,info in self.tradeable.items():
            if data.contains_key(info["symbol"]) and data[info["symbol"]] is not None:
                px[t] = data[info["symbol"]].close
        if len(px) < len(self.tradeable): return

        if self.bars<=5 or self.bars%500==0:
            self.debug(f"Bar {self.bars} | {self.time.date()} | VIX:{vix:.2f}")

        self.strategy.update_windows(px, vix)
        if not all(i["atr"].is_ready for i in self.tradeable.values()): return
        if not self.strategy.is_ready(): return

        if self.use_max_hold:
            md=self.max_hold_days.get(self.sname,60)
            for t,info in self.tradeable.items():
                if not self.portfolio[info["symbol"]].invested or not info["entry_date"]: continue
                if (self.time.date()-info["entry_date"]).days>=md and t in px:
                    self._exit(t,px[t],f"MaxHold({md}d)")

        for t,info in self.tradeable.items():
            if t not in px or not self.portfolio[info["symbol"]].invested: continue
            p=px[t]; atr=info["atr"].current.value
            il=self.portfolio[info["symbol"]].quantity>0
            if il:
                info["highest"]=max(info["highest"],p)
                if p<info["highest"]-atr*self.atr_multiplier: self._exit(t,p,"ATR(L)")
            else:
                info["lowest"]=min(info["lowest"],p)
                if p>info["lowest"]+atr*self.atr_multiplier: self._exit(t,p,"ATR(S)")

        conv={}
        if self.sname=="divergence":
            sigs,conv=self.strategy.generate_signals(px,vix,data)
        else:
            sigs=self.strategy.generate_signals(px,vix,data)

        for t in conv:
            info=self.tradeable[t]
            if self.portfolio[info["symbol"]].invested and t in px:
                self._exit(t,px[t],"Converge")

        for t,sig in sigs.items():
            info=self.tradeable[t]
            if self.portfolio[info["symbol"]].invested or t not in px: continue
            d=sig["dir"]; sz=info["size"]*sig.get("sm",1.0)
            p=px[t]
            if d=="long":
                self.set_holdings(info["symbol"],sz); info["highest"]=p
                self.debug(f"{self.time.date()} BUY  {t:>4} ${p:.2f} {sz*100:.0f}%")
            else:
                self.set_holdings(info["symbol"],-sz); info["lowest"]=p
                self.debug(f"{self.time.date()} SHRT {t:>4} ${p:.2f} {sz*100:.0f}%")
            info["entry_price"]=p; info["entry_date"]=self.time.date()

    def _exit(self, t, p, reason):
        info=self.tradeable[t]; il=self.portfolio[info["symbol"]].quantity>0
        pnl=(p-info["entry_price"])/info["entry_price"]*100
        if not il: pnl=-pnl
        hd=(self.time.date()-info["entry_date"]).days if info["entry_date"] else 0
        self.trades.append({"t":t,"d":"L" if il else "S","pnl":pnl,"hd":hd,"r":reason})
        self.debug(f"{self.time.date()} EXIT {t:>4} ${p:.2f} {'L' if il else 'S'} {hd}d {pnl:+.1f}% {reason}")
        self.liquidate(info["symbol"])
        info["highest"]=0.0;info["lowest"]=float("inf");info["entry_price"]=0.0;info["entry_date"]=None
        self.strategy.on_exit(t)

    def on_end_of_algorithm(self):
        ret=(self.portfolio.total_portfolio_value-100000)/100000*100
        self.debug("="*60)
        self.debug(f"{self.strategy.name} | Return:{ret:+.1f}% | ${self.portfolio.total_portfolio_value:,.0f}")
        self.debug(f"Trades:{len(self.trades)} | VIX pts:{self.vix_n}")
        if not self.trades: self.debug("NO TRADES"); self.debug("="*60); return
        W=[t for t in self.trades if t["pnl"]>0]; L=[t for t in self.trades if t["pnl"]<=0]
        self.debug(f"WR:{len(W)/len(self.trades)*100:.1f}% ({len(W)}W/{len(L)}L) | AvgHold:{sum(t['hd'] for t in self.trades)/len(self.trades):.0f}d")
        if W: self.debug(f"AvgWin:{sum(t['pnl'] for t in W)/len(W):+.1f}% Best:{max(t['pnl'] for t in W):+.1f}%")
        if L: self.debug(f"AvgLoss:{sum(t['pnl'] for t in L)/len(L):+.1f}% Worst:{min(t['pnl'] for t in L):+.1f}%")
        self.debug("-"*60)
        rs={}
        for t in self.trades: rs.setdefault(t["r"],{"n":0,"p":0}); rs[t["r"]]["n"]+=1; rs[t["r"]]["p"]+=t["pnl"]
        for r,v in sorted(rs.items()): self.debug(f"  {r}: {v['n']}t {v['p']:+.1f}%")
        self.debug("-"*60)
        for tk in sorted(set(t["t"] for t in self.trades)):
            tt=[t for t in self.trades if t["t"]==tk]; tw=[t for t in tt if t["pnl"]>0]
            self.debug(f"  {tk:>4}: {len(tt)}t WR{len(tw)/len(tt)*100:.0f}% Hold{sum(t['hd'] for t in tt)/len(tt):.0f}d PnL{sum(t['pnl'] for t in tt):+.1f}%")
        self.debug("="*60)
