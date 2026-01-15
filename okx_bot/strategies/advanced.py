import pandas as pd
import asyncio
from okx_bot.strategy_base import StrategyBase

class AdvancedStrategy(StrategyBase):
    def __init__(self, client, symbol, timeframe='1m', short_window=5, long_window=10):
        super().__init__(client, symbol, timeframe)
        self.short_window = short_window
        self.long_window = long_window
        self.df = None

    async def update(self):
        """Fetches data, updates indicators, and returns the DataFrame."""
        # Need more data for MACD/RSI (e.g. 50-100 candles)
        df = await self.fetch_data(limit=100)
        
        # 1. SMA Trend
        df['sma_short'] = df['close'].rolling(window=self.short_window).mean()
        df['sma_long'] = df['close'].rolling(window=self.long_window).mean()
        
        # 2. RSI (14)
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        # 3. MACD (12, 26, 9)
        exp12 = df['close'].ewm(span=12, adjust=False).mean()
        exp26 = df['close'].ewm(span=26, adjust=False).mean()
        df['macd'] = exp12 - exp26
        df['signal_line'] = df['macd'].ewm(span=9, adjust=False).mean()
        
        self.df = df
        return df

    def get_strategy_info(self):
        if self.df is None or self.df.empty:
            return {}
            
        last = self.df.iloc[-1]
        
        # Calculate a simple "Target Price" for the user
        # In this trend-following strategy, breaking the long-term SMA is often the first step
        target_price = last.get('sma_long', 0)
        
        return {
            "sma_short": last.get('sma_short', 0),
            "sma_long": last.get('sma_long', 0),
            "rsi": last.get('rsi', 0),
            "macd": last.get('macd', 0),
            "macd_signal": last.get('signal_line', 0),
            "next_action": self.get_next_action(last),
            "target_price": target_price
        }
        
    def get_next_action(self, row):
        # Check for insufficient data
        if pd.isna(row.get('sma_long')) or pd.isna(row.get('rsi')):
            return "Calculating Indicators..."
            
        trend = "UP" if row['sma_short'] > row['sma_long'] else "DOWN"
        
        # Detailed Status
        status_parts = []
        status_parts.append(f"Trend: {trend}")
        
        if row['rsi'] > 70:
            status_parts.append("RSI: Overbought")
        elif row['rsi'] < 30:
            status_parts.append("RSI: Oversold")
        else:
            status_parts.append("RSI: Neutral")
            
        # MACD Status
        macd_momentum = "Positive" if row['macd'] > row['signal_line'] else "Negative"
        status_parts.append(f"MACD: {macd_momentum}")

        # Buying Logic Summary
        if trend == "UP" and row['rsi'] < 70 and row['macd'] > row['signal_line']:
             return "✅ BUY SIGNAL PENDING"
        elif trend == "DOWN" and row['rsi'] > 30 and row['macd'] < row['signal_line']:
             return "🔻 SELL SIGNAL PENDING"
             
        # Waiting Logic
        wait_reasons = []
        if trend == "DOWN": wait_reasons.append("Trend UP")
        if row['rsi'] >= 70: wait_reasons.append("RSI Cool-down")
        if row['macd'] <= row['signal_line']: wait_reasons.append("MACD Cross Up")
        
        if wait_reasons:
             return f"WAITING FOR: {', '.join(wait_reasons)}"
        
        return "HOLD (Market Neutral)"

    def check_signals(self):
        if self.df is None or len(self.df) < 2:
            return None
            
        curr = self.df.iloc[-1]
        prev = self.df.iloc[-2]
        
        # LOGIC:
        # BUY: SMA Short > SMA Long AND MACD crosses above Signal AND RSI < 70
        # SELL: SMA Short < SMA Long AND MACD crosses below Signal AND RSI > 30
        
        # 1. Trend Filter (SMA)
        is_uptrend = curr['sma_short'] > curr['sma_long']
        is_downtrend = curr['sma_short'] < curr['sma_long']
        
        # 2. Momentum Trigger (MACD Crossover)
        macd_cross_up = (prev['macd'] < prev['signal_line']) and (curr['macd'] > curr['signal_line'])
        macd_cross_down = (prev['macd'] > prev['signal_line']) and (curr['macd'] < curr['signal_line'])
        
        # 3. RSI Health Check
        rsi_buy_ok = curr['rsi'] < 70 # Not overbought
        rsi_sell_ok = curr['rsi'] > 30 # Not oversold
        
        if is_uptrend and macd_cross_up and rsi_buy_ok:
            return 'BUY'
        elif is_downtrend and macd_cross_down and rsi_sell_ok:
            return 'SELL'
            
        return None
