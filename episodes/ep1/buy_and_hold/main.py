from AlgorithmImports import *

class QQQBuyAndHold(QCAlgorithm):
    
    def initialize(self):
        # Set start and end dates for backtest
        self.set_start_date(2011, 1, 1)
        self.set_end_date(2026, 1, 22)
        
        # Set initial capital
        self.set_cash(100000)
        
        # Add QQQ ETF
        self.qqq = self.add_equity("QQQ", Resolution.DAILY).symbol
        
        # Track if we've already bought
        self.invested = False
    
    def on_data(self, data):
        # Buy and hold: only buy once at the beginning
        if not self.invested:
            if data.contains_key(self.qqq) and data[self.qqq] is not None:
                # Invest 100% of portfolio in QQQ
                self.set_holdings(self.qqq, 1.0)
                self.invested = True
                self.debug(f"Bought QQQ on {self.time}")
    
    def on_end_of_algorithm(self):
        # Log final portfolio value
        self.debug(f"Final Portfolio Value: ${self.portfolio.total_portfolio_value:,.2f}")
