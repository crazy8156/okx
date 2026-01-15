import pandas as pd
import numpy as np
from okx_bot.strategy_base import StrategyBase

class TrendRSIStrategy(StrategyBase):
    def __init__(self, client, symbol, timeframe='1m', sma_period=20, rsi_period=14):
        super().__init__(client, symbol, timeframe)
        self.sma_period = sma_period
        self.rsi_period = rsi_period
        self.df = None
        
        # Risk Management State
        self.position = None # None, 'LONG', 'SHORT'
        self.entry_price = 0
        self.sl_pct = 0.03 # 3%
        self.tp_pct = 0.06 # 6%
        self.rsi_buy_thresh = 30 # Buy when RSI < 30
        self.rsi_sell_thresh = 70 # Sell when RSI > 70

    async def update(self):
        """Fetches data and updates indicators."""
        df = await self.fetch_data(limit=100)
        if df is None or df.empty:
            return None
            
        # 1. SMA 20
        df['sma_20'] = df['close'].rolling(window=self.sma_period).mean()
        
        # 2. RSI 14
        delta = df['close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=self.rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=self.rsi_period).mean()
        rs = gain / loss
        df['rsi'] = 100 - (100 / (1 + rs))
        
        self.df = df
        return df

    def get_strategy_info(self):
        if self.df is None or self.df.empty:
            return {}
            
        last = self.df.iloc[-1]
        
        info = {
            "sma_20": last.get('sma_20', 0),
            "rsi": last.get('rsi', 0),
            "next_action": self.get_next_action(last),
            "target_price": last.get('sma_20', 0),
            "strategy_name": f"Trend-RSI (Strict < {self.rsi_buy_thresh})"
        }
        
        if self.position:
            info["position_status"] = f"{self.position} @ {self.entry_price:.2f}"
            if self.position == 'LONG':
                info["sl"] = self.entry_price * (1 - self.sl_pct)
                info["tp"] = self.entry_price * (1 + self.tp_pct)
            else:
                info["sl"] = self.entry_price * (1 + self.sl_pct)
                info["tp"] = self.entry_price * (1 - self.tp_pct)
                
        return info

    def get_next_action(self, row):
        if pd.isna(row.get('sma_20')) or pd.isna(row.get('rsi')):
            return "初始化指標中..."
            
        price = row['close']
        rsi = row['rsi']
        sma = row['sma_20']
        
        # Entry Logic
        if not self.position:
            if price > sma and rsi < self.rsi_buy_thresh:
                return "✅ 買入訊號 (Long Entry)"
            elif price < sma and rsi > self.rsi_sell_thresh:
                return "🔻 賣出訊號 (Short Entry)"
            return f"等待訊號 (RSI < {self.rsi_buy_thresh} 或 > {self.rsi_sell_thresh})"
            
        # Exit Logic (Position Management)
        if self.position == 'LONG':
            sl_price = self.entry_price * (1 - self.sl_pct)
            if price <= sl_price:
                return f"🛑 出場: 觸發止損 {self.sl_pct*100}% (< {sl_price:.2f})"
            if price >= self.entry_price * (1 + self.tp_pct):
                return f"💰 出場: 止盈 (+{self.tp_pct*100}%)"
            if rsi > self.rsi_sell_thresh:
                return f"⚡ 出場: RSI 超買 (>{self.rsi_sell_thresh})"
            return f"持有多單 (止損價: {sl_price:.2f})"
            
        if self.position == 'SHORT':
            sl_price = self.entry_price * (1 + self.sl_pct)
            if price >= sl_price:
                return f"🛑 出場: 觸發止損 {self.sl_pct*100}% (> {sl_price:.2f})"
            if price <= self.entry_price * (1 - self.tp_pct):
                return f"💰 出場: 止盈 (+{self.tp_pct*100}%)"
            if rsi < self.rsi_buy_thresh:
                return f"⚡ 出場: RSI 超賣 (<{self.rsi_buy_thresh})"
            return f"持有空單 (止損價: {sl_price:.2f})"
            
        return "等待中..."

    def check_signals(self):
        """Generates BUY/SELL signals for the controller."""
        if self.df is None or len(self.df) < 2:
            return None
            
        curr = self.df.iloc[-1]
        price = curr['close']
        rsi = curr['rsi']
        sma = curr['sma_20']
        
        # Entry Signal (ONLY IF NO CURRENT POSITION)
        if not self.position:
            # Stricter Condition: RSI < 30 (Oversold) AND Up-Trend (Price > SMA) ??
            # Actually normally "Trend Following" buys when Price > SMA.
            # "RSI Dip" buys when RSI is low.
            # Combining them: Price is above SMA (Uptrend) but pulled back (RSI low).
            if price > sma and rsi < self.rsi_buy_thresh:
                self.position = 'LONG'
                self.entry_price = price
                return 'BUY'
            elif price < sma and rsi > self.rsi_sell_thresh:
                self.position = 'SHORT'
                self.entry_price = price
                return 'SELL'
        
        # Exit Signal
        if self.position == 'LONG':
            # Stop Loss
            if price <= self.entry_price * (1 - self.sl_pct):
                self.position = None
                return 'SELL'
            # Take Profit
            if price >= self.entry_price * (1 + self.tp_pct):
                self.position = None
                return 'SELL'
            # RSI Exit
            if rsi > self.rsi_sell_thresh:
                self.position = None
                return 'SELL'
                
        if self.position == 'SHORT':
            # Stop Loss
            if price >= self.entry_price * (1 + self.sl_pct):
                self.position = None
                return 'BUY'
            # Take Profit
            if price <= self.entry_price * (1 - self.tp_pct):
                self.position = None
                return 'BUY'
            # RSI Exit
            if rsi < self.rsi_buy_thresh:
                self.position = None
                return 'BUY'
                
        return None
