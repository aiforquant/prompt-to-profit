from AlgorithmImports import *

class ATRTrailingStop(QCAlgorithm):
    """
    ATR-Based Trailing Stop Strategy
    
    Entry: Price crosses above EMA200 (trend confirmation)
    Exit: Price drops below (Highest High - ATR * Multiplier)
    
    The ATR-based stop adapts to current volatility:
    - Calm markets → tighter stop (preserves profits)
    - Volatile markets → wider stop (avoids noise)
    """
    
    def initialize(self):
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        self.set_cash(100000)
        
        # ============================================
        # PARAMETERS TO TEST
        # ============================================
        
        # Ticker: Try "QQQ", "TSLA", "AAPL", "MSFT", "SMH"
        ticker = "TSLA"
        
        # ATR Period: How many days to measure volatility
        # Shorter = more responsive, Longer = smoother
        # Test: 10, 14, 21
        self.atr_period = 14
        
        # ATR Multiplier: How many ATRs below the high
        # Lower = tighter stop (more exits, less drawdown)
        # Higher = looser stop (fewer exits, ride trends longer)
        # Test: 2.0, 2.5, 3.0, 3.5, 4.0
        self.atr_multiplier = 3.0
        
        # EMA Period for entry signal
        # Test: 50, 100, 200
        self.ema_period = 200
        
        # ============================================
        # SETUP
        # ============================================
        
        self.equity_symbol = self.add_equity(ticker, Resolution.DAILY).symbol
        
        # Indicators
        self.ema_indicator = self.ema(self.equity_symbol, self.ema_period, Resolution.DAILY)
        self.atr_indicator = self.atr(self.equity_symbol, self.atr_period)
        
        # Warm up for longest indicator
        warmup_period = max(self.ema_period, self.atr_period)
        self.set_warm_up(warmup_period, Resolution.DAILY)
        
        # Tracking variables
        self.highest_price = 0
        self.entry_price = 0
        self.entry_date = None
        self.ticker_name = ticker
        
        # For logging summary
        self.trades = []
    
    def on_data(self, data):
        if self.is_warming_up:
            return
            
        if not data.contains_key(self.equity_symbol) or data[self.equity_symbol] is None:
            return
        
        if not self.atr_indicator.is_ready or not self.ema_indicator.is_ready:
            return
        
        price = data[self.equity_symbol].close
        current_atr = self.atr_indicator.current.value
        
        if self.portfolio[self.equity_symbol].invested:
            # Update highest price since entry
            self.highest_price = max(self.highest_price, price)
            
            # Calculate dynamic stop: Highest - (ATR * Multiplier)
            stop_price = self.highest_price - (current_atr * self.atr_multiplier)
            stop_pct = (self.highest_price - stop_price) / self.highest_price * 100
            
            # Exit on trailing stop
            if price < stop_price:
                pnl_pct = (price - self.entry_price) / self.entry_price * 100
                self.trades.append({
                    'entry': self.entry_date,
                    'exit': self.time.date(),
                    'pnl_pct': pnl_pct
                })
                
                self.debug(f"{self.time.date()} EXIT | Price: ${price:.2f} | "
                          f"Stop: ${stop_price:.2f} ({stop_pct:.1f}% from high) | "
                          f"ATR: ${current_atr:.2f} | PnL: {pnl_pct:+.1f}%")
                
                self.liquidate(self.equity_symbol)
                self.highest_price = 0
                self.entry_price = 0
        else:
            # Entry: price above EMA
            if price > self.ema_indicator.current.value:
                self.set_holdings(self.equity_symbol, 1.0)
                self.highest_price = price
                self.entry_price = price
                self.entry_date = self.time.date()
                
                # Show what the initial stop would be
                initial_stop = price - (current_atr * self.atr_multiplier)
                initial_stop_pct = (current_atr * self.atr_multiplier) / price * 100
                
                self.debug(f"{self.time.date()} BUY  | Price: ${price:.2f} | "
                          f"EMA{self.ema_period}: ${self.ema_indicator.current.value:.2f} | "
                          f"Initial Stop: ${initial_stop:.2f} ({initial_stop_pct:.1f}% below)")
    
    def on_end_of_algorithm(self):
        # Summary statistics
        total_return = (self.portfolio.total_portfolio_value - 100000) / 100000 * 100
        
        self.debug("=" * 60)
        self.debug(f"STRATEGY: {self.ticker_name} with ATR({self.atr_period}) x {self.atr_multiplier}")
        self.debug(f"Final Value: ${self.portfolio.total_portfolio_value:,.2f}")
        self.debug(f"Total Return: {total_return:+.1f}%")
        self.debug(f"Total Trades: {len(self.trades)}")
        
        if self.trades:
            winners = [t for t in self.trades if t['pnl_pct'] > 0]
            losers = [t for t in self.trades if t['pnl_pct'] <= 0]
            win_rate = len(winners) / len(self.trades) * 100
            
            self.debug(f"Win Rate: {win_rate:.1f}% ({len(winners)}W / {len(losers)}L)")
            
            if winners:
                avg_win = sum(t['pnl_pct'] for t in winners) / len(winners)
                self.debug(f"Avg Win: {avg_win:+.1f}%")
            if losers:
                avg_loss = sum(t['pnl_pct'] for t in losers) / len(losers)
                self.debug(f"Avg Loss: {avg_loss:+.1f}%")
        
        self.debug("=" * 60)
