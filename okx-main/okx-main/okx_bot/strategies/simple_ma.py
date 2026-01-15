"""
Simple Moving Average (SMA) Crossover Strategy (Async).
"""
import pandas as pd
from ..strategy_base import StrategyBase

class SMACrossoverStrategy(StrategyBase):
    def __init__(self, client, symbol, timeframe, short_window=10, long_window=20):
        super().__init__(client, symbol, timeframe)
        self.short_window = short_window
        self.long_window = long_window
        self.df = None

    async def fetch_data(self, limit=50):
        """Fetches OHLCV data from OKX asynchronously."""
        # await the async ccxt call
        ohlcv = await self.client.exchange.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
        df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df

    async def update(self):
        """Fetches data, updates indicators, and returns the DataFrame."""
        df = await self.fetch_data(limit=self.long_window + 10)
        
        # Calculate Indicators (SMA)
        df['sma_short'] = df['close'].rolling(window=self.short_window).mean()
        df['sma_long'] = df['close'].rolling(window=self.long_window).mean()
        
        self.df = df
        
        # --- Advanced: Calculate Price to Cross ---
        # Formula: SMA_S = (Sum_S_prev + P) / S, SMA_L = (Sum_L_prev + P) / L
        # We want SMA_S = SMA_L for a cross.
        # (Sum_S_prev + P) * L = (Sum_L_prev + P) * S
        # L*Sum_S_prev + L*P = S*Sum_L_prev + S*P
        # P * (L - S) = S*Sum_L_prev - L*Sum_S_prev
        # P = (S*Sum_L_prev - L*Sum_S_prev) / (L - S)
        # Note: Sum_prev means sum of the LAST (Window-1) candles excluding current?
        # Actually, rolling mean includes current. So we look at specific windows.
        # Simplified approximation: The "Crossover" happens when the Difference goes to 0.
        
        return df

    def get_strategy_info(self):
        """Returns extra info about the strategy state."""
        if self.df is None or self.df.empty:
            return {}
            
        last = self.df.iloc[-1]
        sma_s = last.get('sma_short', 0)
        sma_l = last.get('sma_long', 0)
        
        return {
            "sma_short": sma_s,
            "sma_long": sma_l,
            "spread": sma_s - sma_l,
            "next_action": "BUY" if sma_s < sma_l else "SELL"
        }

    def check_signals(self):
        if self.df is None:
            return None
            
        current = self.df.iloc[-1]
        prev = self.df.iloc[-2]
        
        # Gold Cross (Short crosses above Long) -> BUY
        if prev['sma_short'] <= prev['sma_long'] and current['sma_short'] > current['sma_long']:
            return 'BUY'
            
        # Death Cross (Short crosses below Long) -> SELL
        if prev['sma_short'] >= prev['sma_long'] and current['sma_short'] < current['sma_long']:
            return 'SELL'
            
        return None
