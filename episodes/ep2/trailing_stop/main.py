from AlgorithmImports import *

class EMA200WithTrailingStop(QCAlgorithm):
    
    def initialize(self):
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        self.set_cash(100000)
        
        self.symbol = self.add_equity("TSLA", Resolution.DAILY).symbol
        
        # EMA200 for trend confirmation on entry
        self.ema200 = self.ema(self.symbol, 200, Resolution.DAILY)
        self.set_warm_up(200, Resolution.DAILY)
        
        # Trailing stop parameters
        self.trailing_stop_pct = 0.15  # 15% from high
        self.highest_price = 0
    
    def on_data(self, data):
        if self.is_warming_up:
            return
            
        if not data.contains_key(self.symbol) or data[self.symbol] is None:
            return
        
        price = data[self.symbol].close
        
        if self.portfolio[self.symbol].invested:
            # Update highest price
            self.highest_price = max(self.highest_price, price)
            stop_price = self.highest_price * (1 - self.trailing_stop_pct)
            
            # Exit on trailing stop
            if price < stop_price:
                self.liquidate(self.symbol)
                self.debug(f"{self.time.date()} TRAILING STOP at ${price:.2f} (High: ${self.highest_price:.2f}, Stop: ${stop_price:.2f})")
                self.highest_price = 0
        else:
            # Entry: price above EMA200
            if price > self.ema200.current.value:
                self.set_holdings(self.symbol, 1.0)
                self.highest_price = price
                self.debug(f"{self.time.date()} BUY at ${price:.2f} (EMA200: ${self.ema200.current.value:.2f})")
    
    def on_end_of_algorithm(self):
        self.debug(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
