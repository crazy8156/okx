"""
Strategy Base Class (Async)
Defines the interface that all trading strategies must implement.
"""
from abc import ABC, abstractmethod

class StrategyBase(ABC):
    def __init__(self, client, symbol, timeframe):
        self.client = client
        self.symbol = symbol
        self.timeframe = timeframe

    @abstractmethod
    async def update(self):
        """
        Called on every loop iteration.
        Should fetch data, calculate indicators, and generate signals.
        """
        pass

    @abstractmethod
    def check_signals(self):
        """
        Returns a signal: 'BUY', 'SELL', or None.
        (Can remain synchronous if just checking internal state, but usually good to keep simple)
        """
        pass
    async def fetch_data(self, limit=100):
        """
        Common method to fetch OHLCV data using ccxt.
        """
        if not self.client:
            return None
            
        try:
            # Fetch OHLCV (Open, High, Low, Close, Volume)
            ohlcv = await self.client.fetch_ohlcv(self.symbol, self.timeframe, limit=limit)
            if not ohlcv:
                return None
                
            import pandas as pd
            # Create DataFrame
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            return df
        except Exception as e:
            print(f"❌ Error fetching data for {self.symbol}: {e}")
            return None
