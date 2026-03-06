from AlgorithmImports import *

class SMA200GatedStrategy(QCAlgorithm):
    
    def initialize(self):
        # Set start and end dates for backtest
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        
        # Set initial capital
        self.set_cash(100000)
        
        # Add equity
        self.symbol = self.add_equity("QQQ", Resolution.DAILY).symbol
        
        # Create 200-day SMA indicator
        self.sma200 = self.sma(self.symbol, 200, Resolution.DAILY)
        
        # Warm up the indicator (need 200 days of data before trading)
        self.set_warm_up(200, Resolution.DAILY)
    
    def on_data(self, data):
        # Don't trade during warm-up period
        if self.is_warming_up:
            return
            
        # Make sure we have valid data
        if not data.contains_key(self.symbol) or data[self.symbol] is None:
            return
        
        # Get current price
        price = data[self.symbol].close
        
        # Entry: Buy when price crosses above SMA200
        if price > self.sma200.current.value:
            if not self.portfolio[self.symbol].invested:
                self.set_holdings(self.symbol, 1.0)
                self.debug(f"{self.time.date()} BUY at ${price:.2f} (SMA200: ${self.sma200.current.value:.2f})")
        
        # Exit: Sell when price crosses below SMA200
        else:
            if self.portfolio[self.symbol].invested:
                self.liquidate(self.symbol)
                self.debug(f"{self.time.date()} SELL at ${price:.2f} (SMA200: ${self.sma200.current.value:.2f})")
    
    def on_end_of_algorithm(self):
        self.debug(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
