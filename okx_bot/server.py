"""
FastAPI Server for OKX Trading Bot.
Manages the bot lifecycle and exposes API endpoints.
"""
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager

from okx_bot.config import Config
from okx_bot.client import OKXClient
from okx_bot.config import Config
from okx_bot.client import OKXClient
from okx_bot.strategies.advanced import AdvancedStrategy
from okx_bot.strategies.trend_rsi import TrendRSIStrategy
from okx_bot.news import NewsAnalyzer

# --- Bot Controller ---
class BotController:
    def __init__(self):
        self.is_running = False
        self.task = None
        self.client = None
        self.strategy = None
        self.last_price = None
        self.last_signal = None
        self.config = None
        self.balance = {}
        self.trades = [] # List of {'time', 'side', 'price', 'amount'}
        self.news_analyzer = None # To be initialized with API Key
        self.market_sentiment = {}
        self.initial_balance_usdt = None
        self.trades = [] # List of {time, side, price, amount}
        self.market_prices = {} # Store multiple coin prices
        self.last_trade_time = None  # For cooldown period
        self.virtual_capital_usdt = 0  # Virtual capital limit (if set)
        self.price_history = [] # List of {time, value}
        self.pnl_history = [] # List of {time, value}
        self._last_history_update = 0

    async def initialize(self):
        try:
            self.config = Config()
            self.config.validate()
            self.client = OKXClient(self.config)
            
            # Initialize client (load markets)
            print("🔄 Initializing OKX connection...")
            init_success = await self.client.initialize()
            if not init_success:
                print("⚠️ Failed to initialize OKX client. Some features may not work.")
            
            # Set Virtual Capital if configured
            self.virtual_capital_usdt = self.config.VIRTUAL_CAPITAL_USDT
            if self.virtual_capital_usdt > 0:
                print(f"💰 Virtual Capital Limit: {self.virtual_capital_usdt} USDT")
            
            # Initial Balance Fetch
            self.balance = await self.client.get_balance()
            
            # Init Strategy (for display even when stopped)
            self.symbol = 'BTC/USDT'
            timeframe = '5m'  # Changed from 1m to 5m for less noise
            self.strategy = TrendRSIStrategy(self.client, self.symbol, timeframe, sma_period=20, rsi_period=14)
            
            # Sync Historical Trades
            print("📜 Syncing recent trade history...")
            recent_orders = await self.client.fetch_recent_trades(self.symbol)
            for order in recent_orders:
                # CCXT structure: 'avgPrice' or 'price', 'amount', 'side', 'timestamp'
                # We need to map to our internal format: {'time', 'side', 'price', 'amount'}
                trade_record = {
                    'time': order.get('timestamp'), # Keep as ms for consistency or convert? Frontend expects ms usually or date obj
                    'side': order.get('side').upper(),
                    'price': order.get('average') or order.get('price'),
                    'amount': order.get('amount')
                }
                # Prepend to keep chronological if needed, but fetch usually gives new->old or old->new
                # We'll just re-populate self.trades.
                # Avoid duplicates if any (though on init it's empty)
                self.trades.append(trade_record)
            
            # Sort trades by time descending for display (Newest first)
            self.trades.sort(key=lambda x: x['time'], reverse=True)
            print(f"✅ Synced {len(self.trades)} historical trades.")

            # Initial Data Fetch for UI
            print("📊 Fetching initial market data...")
            await self.strategy.update()
            current = self.strategy.df.iloc[-1]
            self.last_price = current['close']
            
            # Initial News Fetch (Background)
            self.news_analyzer = NewsAnalyzer(self.config.CRYPTOPANIC_API_KEY)
            asyncio.create_task(self.update_news())
            
        except Exception as e:
            print(f"❌ Initialization Error: {e}")

    async def update_tickers(self):
        """Fetches latest prices for watched symbols."""
        try:
            if hasattr(self.client, 'exchange'):
                tickers = await self.client.exchange.fetch_tickers(['BTC/USDT', 'ETH/USDT', 'ETC/USDT'])
                for symbol, ticker in tickers.items():
                    self.market_prices[symbol] = ticker['last']
        except Exception as e:
            pass  # Silent fail

    async def update_news(self):
        """Fetches news periodically."""
        try:
            if not self.news_analyzer:
                return
            print("📰 Fetching News...")
            await self.news_analyzer.fetch_news()
            self.market_sentiment = self.news_analyzer.get_market_summary()
            print(f"📰 News Updated. Sentiment: {self.market_sentiment.get('sentiment')}")
        except Exception as e:
            print(f"⚠️ News update failed: {e}")

    async def run_loop(self):
        """The main trading loop."""
        print(f"🚀 Trading Loop Started for {self.symbol}.")
        
        # Strategy should be re-initialized in start() to ensure correct symbol
        
        loop_count = 0
        while self.is_running:
            try:
                loop_count += 1
                
                # Fetch News every ~5 minutes (approx 60 loops of 5s)
                if loop_count % 60 == 0:
                     asyncio.create_task(self.update_news())
                
                # Fetch Tickers every loop (or every other loop)
                if loop_count % 2 == 0:
                     asyncio.create_task(self.update_tickers())

                # Update Strategy
                if self.strategy:
                    try:
                        df = await self.strategy.update()
                        
                        # Store State for UI
                        if df is not None and not df.empty:
                            current_data = df.iloc[-1]
                            self.last_price = current_data['close']
                            timestamp = current_data['timestamp']
                    except Exception as e:
                        print(f"⚠️ Strategy Update Failed: {e}")
                
                if loop_count % 2 == 0 and self.strategy and hasattr(self.strategy, 'df') and self.strategy.df is not None:
                     try:
                        last_row = self.strategy.df.iloc[-1]
                        action = self.strategy.get_next_action(last_row)
                        price = last_row.get('close', 0)
                        rsi = last_row.get('rsi', 0)
                        sma_s = last_row.get('sma_short', 0)
                        sma_l = last_row.get('sma_long', 0)
                        
                        log_msg = f"📊 Price: {price} | RSI: {rsi:.1f} | SMA(20/50): {sma_s:.1f}/{sma_l:.1f}"
                        print(log_msg)
                        print(f"   ↳ Status: {action}")
                     except Exception as e:
                        print(f"⚠️ Log Generation Error: {e}")
                elif loop_count % 2 == 0 and self.strategy:
                     print(f"⏳ Strategy Initializing... Fetching {self.symbol} data ({loop_count})")

                # Fetch Balance periodically (every loop is fine for low freq)
                # In real prod, maybe throttle this
                try:
                    bal = await self.client.get_balance()
                    if bal: self.balance = bal
                except Exception as e:
                    print(f"⚠️ Balance fetch failed: {e}")

                # Check Signals
                if self.strategy:
                    signal = self.strategy.check_signals()
                    self.last_signal = signal if signal else self.last_signal
                    
                    if signal:
                        # Cooldown check - prevent trades within 5 minutes of last trade
                        import time
                        current_time = time.time()
                        
                        if self.last_trade_time is None or (current_time - self.last_trade_time) >= 300:  # 300 seconds = 5 minutes
                            print(f"🔔 SIGNAL: {signal}")
                            
                            # Execute Real Order
                            await self.execute_order(signal, self.symbol)
                            self.last_trade_time = current_time
                        else:
                            time_since_last = int(current_time - self.last_trade_time)
                            cooldown_remaining = 300 - time_since_last
                            print(f"⏱️ Cooldown Active: {cooldown_remaining}s remaining (Signal: {signal})")
                
                # Update Price & PnL History
                import time
                current_timestamp = time.time()
                if current_timestamp - self._last_history_update >= 5: # Update every 10s
                    self._last_history_update = current_timestamp
                    
                    # 1. Price History
                    if self.last_price:
                        self.price_history.append({"time": current_timestamp, "value": self.last_price})
                        self.price_history = self.price_history[-100:]
                    
                    # 2. PnL History
                    current_pnl_usdt = 0
                    if self.initial_balance_usdt and self.last_price and self.balance and 'total' in self.balance:
                        usdt_bal = self.balance['total'].get('USDT', 0)
                        coin_name = self.symbol.split('/')[0] if self.symbol else 'BTC'
                        coin_bal = self.balance['total'].get(coin_name, 0)
                        current_nav = usdt_bal + (coin_bal * self.last_price)
                        current_pnl_usdt = current_nav - self.initial_balance_usdt
                        
                        self.pnl_history.append({"time": current_timestamp, "value": current_pnl_usdt})
                        self.pnl_history = self.pnl_history[-100:]

                # Sleep (Non-blocking)
                await asyncio.sleep(5) 
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                print(f"❌ Error in loop: {e}")
                await asyncio.sleep(5) # Wait before retry

        print("🛑 Trading Loop Stopped.")

    async def execute_order(self, side, symbol):
        """Executes an order and updates UI state."""
        amount = 0.001 # TODO: Make this dynamic based on balance/risk management
        # For ETC, amount needs to be larger (price is lower)
        if 'ETC' in symbol:
            amount = 0.1 
        
        # Place Order via Client
        order = await self.client.place_order(symbol, side.lower(), amount)
        
        if order:
            # Update UI Trade History
            trade = {
                'time': str(order.get('timestamp', '')), 
                # If timestamp is None/Empty, use current time? 
                # better to rely on order response execution time if available
                'side': side,
                'price': order.get('average') or order.get('price') or self.last_price,
                'amount': amount
            }
            # Fallback for time if timestamp is milliseconds int
            import time
            if 'timestamp' in order:
               # CCXT returns timestamp in ms
               from datetime import datetime
               dt_object = datetime.fromtimestamp(order['timestamp'] / 1000)
               trade['time'] = dt_object.isoformat()
            
            self.trades.insert(0, trade)
            self.trades = self.trades[:10]
            
            # Refresh Balance immediately after trade
            self.balance = await self.client.get_balance()

    async def start(self, symbol="BTC/USDT"):
        if self.is_running:
            return {"message": f"Bot already running for {self.symbol}"}
        
        print(f"🏁 Starting Bot for {symbol}...")
        self.symbol = symbol
        
        # Re-Init Strategy with new symbol
        timeframe = '5m'  # 5-minute candles for better trend detection
        self.strategy = TrendRSIStrategy(self.client, self.symbol, timeframe, sma_period=20, rsi_period=14)
        
        # Record Initial Balance (Session Start)
        # Calculate Total USDT Value
        if self.balance and 'total' in self.balance:
             # Refresh price for NAV calculation
             try:
                await self.strategy.update()
                self.last_price = self.strategy.df.iloc[-1]['close']
             except:
                pass

             usdt_bal = self.balance['total'].get('USDT', 0)
             # Assumption: Initial Coin Balance is negligible or we include it?
             # Better to calculate Net Asset Value (NAV)
             # NAV = USDT + (Coin_Amount * Current_Price)
             coin_name = self.symbol.split('/')[0] if self.symbol else 'BTC'
             coin_bal = self.balance['total'].get(coin_name, 0)
             
             if self.last_price:
                 self.initial_balance_usdt = usdt_bal + (coin_bal * self.last_price)
                 print(f"💰 Session Start NAV: {self.initial_balance_usdt:.2f} USDT")
        else:
             print("⚠️ Could not calculate initial balance (missing data)")
             self.initial_balance_usdt = None

        self.is_running = True
        # Create Task
        self.task = asyncio.create_task(self.run_loop())
        return {"message": f"Bot started for {symbol}"}

    async def stop(self):
        if not self.is_running:
            return {"message": "Already stopped"}
        
        self.is_running = False
        if self.task:
            await self.task 
        return {"message": "Bot stopped"}

    async def get_status(self):
        # Calculate Balance Display
        usdt_bal = 0
        coin_bal = 0
        coin_name = self.symbol.split('/')[0] if self.symbol else 'BTC'
        
        if self.balance and 'total' in self.balance:
            usdt_bal = self.balance['total'].get('USDT', 0)
            
            # Dynamic Coin Name (re-evaluate in case symbol changed or was not set initially)
            if hasattr(self, 'symbol') and self.symbol:
                coin_name = self.symbol.split('/')[0] # e.g. BTC
                coin_bal = self.balance['total'].get(coin_name, 0)
            else:
                # Fallback if loop hasn't started
                coin_name = 'BTC' 
                coin_bal = self.balance['total'].get(coin_name, 0)

        # Calculate PnL
        pnl_usdt = 0
        pnl_pct = 0
        if self.initial_balance_usdt and self.last_price:
             current_nav = usdt_bal + (coin_bal * self.last_price)
             pnl_usdt = current_nav - self.initial_balance_usdt
             if self.initial_balance_usdt > 0:
                 pnl_pct = (pnl_usdt / self.initial_balance_usdt) * 100

        # Get OKX Total Account Equity (Native Value)
        total_eq = 0
        if self.balance and 'info' in self.balance:
            # OKX API v5 returns balance in 'info' dict, field is 'totalEq'
            try:
               total_eq = float(self.balance['info'].get('totalEq', 0))
            except:
               total_eq = 0

        return {
            "is_running": self.is_running,
            "last_price": self.last_price,
            "last_signal": self.last_signal,
            "balance": {
                "USDT": usdt_bal,
                "coin_name": coin_name,
                "coin_amount": coin_bal,
                "total_equity": total_eq # New field
            },
            "pnl": {
                "usdt": pnl_usdt,
                "pct": pnl_pct,
                "active": self.is_running,
                "daily_realized": self.calculate_daily_realized_pnl()
            },
            "trades": self.trades,
            "market_prices": self.market_prices,
            "mode": "DEMO" if self.config.SANDBOX_MODE else "REAL",
            "strategy": self.strategy.get_strategy_info() if self.strategy else {},
            "trade_amount": 0.001,
            "history": {
                "price": self.price_history,
                "pnl": self.pnl_history
            }
        }
    
    def calculate_daily_realized_pnl(self):
        """Calculates realized PnL for trades occurring today using FIFO matching."""
        try:
            from datetime import datetime, timezone
            # Use Local Time for 'Today' definition as requested by typical users
            today = datetime.now().date()
            
            # 1. Sort trades by time (Oldest First) for FIFO
            # self.trades is currently Newest First, so reverse it
            sorted_trades = sorted(self.trades, key=lambda x: x['time'])
            
            inventory = [] # List of {'price': float, 'amount': float}
            daily_realized_pnl = 0.0
            
            for t in sorted_trades:
                # Parse Time
                trade_ts = t['time']
                if isinstance(trade_ts, str):
                    try:
                        dt = datetime.fromisoformat(trade_ts)
                    except:
                        # Fallback for ISO strings potentially
                        continue
                else:
                    # Milliseconds integer
                    dt = datetime.fromtimestamp(trade_ts / 1000)
                
                is_today = (dt.date() == today)
                
                side = t['side'].upper()
                price = float(t['price'])
                amount = float(t['amount'])
                
                if side == 'BUY':
                    # Add to inventory
                    inventory.append({'price': price, 'amount': amount})
                
                elif side == 'SELL':
                    # Match against inventory (FIFO)
                    qty_to_fill = amount
                    cost_basis = 0.0
                    
                    while qty_to_fill > 0 and inventory:
                        batch = inventory[0]
                        
                        if batch['amount'] > qty_to_fill:
                            # Partial fill from this batch
                            cost_basis += (batch['price'] * qty_to_fill)
                            batch['amount'] -= qty_to_fill # Reduce batch
                            qty_to_fill = 0
                            # Batch remains in inventory with reduced amount
                        else:
                            # Full consumption of this batch
                            cost_basis += (batch['price'] * batch['amount'])
                            qty_to_fill -= batch['amount']
                            inventory.pop(0) # Remove batch
                            
                    # If inventory ran out but we still sold (Shorting or missing history), 
                    # we assume entry price = current exit price (0 PnL) for the remainder to avoid huge skew,
                    # or just ignore. For now, let's assume 0 profit on unmatched part.
                    if qty_to_fill > 0:
                        cost_basis += (price * qty_to_fill)
                        
                    # Revenue from this sell
                    revenue = price * amount
                    trade_pnl = revenue - cost_basis
                    
                    # Accumulate ONLY if this Sell happened TODAY
                    if is_today:
                        daily_realized_pnl += trade_pnl
                        
            return daily_realized_pnl
            
        except Exception as e:
            print(f"⚠️ Daily PnL Calc Error: {e}")
            return 0.0

    async def get_news(self):
        return {
            "summary": self.market_sentiment,
            "news": self.news_analyzer.cached_news
        }

# --- FastAPI App ---
bot = BotController()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await bot.initialize()
    yield
    # Shutdown
    if bot.client:
        await bot.client.close()

app = FastAPI(lifespan=lifespan)

# Static Files (UI)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root():
    return FileResponse('static/index.html')

@app.get("/api/status")
async def get_status():
    return await bot.get_status()

@app.get("/api/news")
async def get_news():
    return await bot.get_news()

from pydantic import BaseModel

class StartRequest(BaseModel):
    symbol: str = "BTC/USDT"

@app.post("/api/start")
async def start_bot(req: StartRequest = None):
    try:
        # Default to BTC if no body
        symbol = req.symbol if req else "BTC/USDT"
        return await bot.start(symbol)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"message": f"Error starting bot: {str(e)}", "error": True}

@app.post("/api/stop")
async def stop_bot():
    return await bot.stop()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("okx_bot.server:app", host="127.0.0.1", port=8000, reload=True)
