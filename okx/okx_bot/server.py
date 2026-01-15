"""
FastAPI Server for OKX Trading Bot.
Manages the bot lifecycle and exposes API endpoints.
"""
import asyncio
from fastapi import FastAPI, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel

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
        self.strategies = {} # Dict[Symbol, Strategy]
        self.config = None
        self.balance = {}
        self.trades = [] # List of {'time', 'side', 'price', 'amount', 'symbol'}
        self.news_analyzer = None 
        self.market_sentiment = {}
        self.initial_balances = {} # Dict[Symbol, Initial_NAV_USDT]
        self.market_prices = {} 
        self.last_trade_times = {} # Dict[Symbol, timestamp]
        self.virtual_capital_usdt = 0
        self.price_history = {} # Dict[Symbol, List[{time, value}]]
        self.pnl_history = [] # Global PnL history
        self._last_history_update = 0
        
        # v2.0 Features
        self.mode = 'SINGLE' # 'SINGLE', 'DUAL'
        self.active_symbols = []
        self.scanner_results = []
        self.scanner_last_update = 0

    async def initialize(self):
        try:
            self.config = Config()
            self.config.validate()
            self.client = OKXClient(self.config)
            
            print("🔄 Initializing OKX connection...")
            init_success = await self.client.initialize()
            if not init_success:
                print("⚠️ Failed to initialize OKX client.")
            
            self.virtual_capital_usdt = self.config.VIRTUAL_CAPITAL_USDT
            self.balance = await self.client.get_balance()
            
            # Init News (Background)
            self.news_analyzer = NewsAnalyzer(self.config.CRYPTOPANIC_API_KEY)
            asyncio.create_task(self.update_news())
            
        except Exception as e:
            print(f"❌ Initialization Error: {e}")

    async def update_tickers(self):
        """Fetches latest prices for active symbols + popular ones."""
        try:
            if hasattr(self.client, 'exchange'):
                watch_list = list(set(self.active_symbols + ['BTC/USDT', 'ETH/USDT', 'ETC/USDT', 'SOL/USDT', 'DOGE/USDT']))
                tickers = await self.client.exchange.fetch_tickers(watch_list)
                for symbol, ticker in tickers.items():
                    self.market_prices[symbol] = ticker['last']
        except Exception as e:
            pass 

    async def update_news(self):
        try:
            if not self.news_analyzer: return
            await self.news_analyzer.fetch_news()
            self.market_sentiment = self.news_analyzer.get_market_summary()
        except Exception as e:
            print(f"⚠️ News update failed: {e}")

    async def run_scanner(self):
        """Scans for potential opportunities."""
        if not self.client: return
        try:
            # 1. Fetch Tickers (24h stats)
            tickers = await self.client.exchange.fetch_tickers()
            candidates = []
            
            for symbol, data in tickers.items():
                if not symbol.endswith('/USDT'): continue
                if data['quoteVolume'] is None or data['quoteVolume'] < 5000000: continue # Min 5M USDT Volume
                
                change_24h = data['percentage']
                if change_24h is None: continue
                
                # Volatility criteria
                if abs(change_24h) > 5.0:
                    candidates.append({
                        'symbol': symbol,
                        'change': change_24h,
                        'price': data['last'],
                        'volume': data['quoteVolume'],
                        'type': 'VOLATILITY'
                    })
            
            # Sort by absolute change
            candidates.sort(key=lambda x: abs(x['change']), reverse=True)
            self.scanner_results = candidates[:10]
            self.scanner_last_update = asyncio.get_event_loop().time()
            # print(f"🔍 Scanner found {len(self.scanner_results)} active coins.")
            
        except Exception as e:
            print(f"⚠️ Scanner Error: {e}")

    async def run_loop(self):
        """The main trading loop handling multiple strategies."""
        print(f"🚀 Trading Loop Started. Mode: {self.mode}, Symbols: {self.active_symbols}")
        
        loop_count = 0
        while self.is_running:
            try:
                loop_count += 1
                
                # 1. Global Updates
                if loop_count % 60 == 0: asyncio.create_task(self.update_news())
                if loop_count % 2 == 0: asyncio.create_task(self.update_tickers())
                if loop_count % 120 == 0: asyncio.create_task(self.run_scanner()) # Scan every ~10 mins
                
                # 2. Update Each Strategy
                for symbol, strategy in self.strategies.items():
                    try:
                        # Update Data
                        await strategy.update()
                        
                        # Log Status (Sample)
                        if loop_count % 4 == 0 and strategy.df is not None:
                             last = strategy.df.iloc[-1]
                             print(f"[{symbol}] P: {last['close']} | RSI: {last['rsi']:.1f} | Action: {strategy.get_next_action(last)}")
                        
                        # Check Signals
                        signal = strategy.check_signals()
                        if signal:
                           self.last_signal = f"{symbol}: {signal}" # Global last signal check
                           
                           # Cooldown Check
                           import time
                           now = time.time()
                           last_t = self.last_trade_times.get(symbol, 0)
                           if (now - last_t) > 300: # 5 min cooldown per coin
                               print(f"🔔 SIGNAL {symbol}: {signal}")
                               await self.execute_order(signal, symbol, strategy)
                               self.last_trade_times[symbol] = now
                           else:
                               print(f"⏱️ Cooldown {symbol}: {int(300 - (now - last_t))}s")

                    except Exception as e:
                        print(f"⚠️ Error running strategy for {symbol}: {e}")

                # 3. Fetch Balance
                try:
                    bal = await self.client.get_balance()
                    if bal: self.balance = bal
                except: pass

                # 4. Update History (PnL)
                await self.update_history_data()

                await asyncio.sleep(5) 
                
            except Exception as e:
                import traceback
                traceback.print_exc()
                await asyncio.sleep(5)

        print("🛑 Trading Loop Stopped.")

    async def execute_order(self, side, symbol, strategy):
        # Adaptive Size
        amount = 0.001
        if 'ETC' in symbol: amount = 0.1
        if 'SOL' in symbol: amount = 0.1
        if 'DOGE' in symbol: amount = 100.0
        if 'ETH' in symbol: amount = 0.01

        order = await self.client.place_order(symbol, side.lower(), amount)
        
        if order:
            import time
            from datetime import datetime
            trade = {
                'time': str(order.get('timestamp', int(time.time()*1000))), 
                'side': side,
                'price': order.get('average') or order.get('price') or strategy.df.iloc[-1]['close'],
                'amount': amount,
                'symbol': symbol
            }
            # Fix timestamp display logic if needed later
            self.trades.insert(0, trade)
            self.trades = self.trades[:20] # Keep more history
            self.balance = await self.client.get_balance()

    async def update_history_data(self):
        import time
        now = time.time()
        if now - self._last_history_update < 10: return
        self._last_history_update = now
        
        # PnL Calculation
        total_pnl = 0
        current_nav = 0
        
        if self.balance and 'total' in self.balance:
            usdt = self.balance['total'].get('USDT', 0)
            current_nav = usdt
            
            # Add value of all active coins
            for coin, qty in self.balance['total'].items():
                if coin == 'USDT': continue
                # Find price
                price = self.market_prices.get(f"{coin}/USDT", 0)
                current_nav += (qty * price)
            
            # Compare with initial (Simple approach: Sum of initial NAVs? Or just track Session Start Total?)
            # For simplicity in v2, let's track "Session Start Total NAV"
            if hasattr(self, 'session_start_nav') and self.session_start_nav:
                total_pnl = current_nav - self.session_start_nav
                
        self.pnl_history.append({"time": now, "value": total_pnl})
        self.pnl_history = self.pnl_history[-100:]

        # Store Price History for each active symbol
        for sym in self.active_symbols:
            price = self.market_prices.get(sym)
            if price:
                if sym not in self.price_history: self.price_history[sym] = []
                self.price_history[sym].append({"time": now, "value": price})
                self.price_history[sym] = self.price_history[sym][-100:]

    async def start(self, mode="SINGLE", symbols=["BTC/USDT"]):
        if self.is_running:
            return {"message": "Bot already running"}
            
        print(f"🏁 Starting {mode} Mode for {symbols}")
        self.mode = mode
        self.active_symbols = symbols
        self.strategies = {}
        self.last_trade_times = {}
        
        # Initialize Strategies with Adaptive Params
        for sym in symbols:
            # Adaptive Logic
            if sym == 'BTC/USDT':
                # Conservative
                strat = TrendRSIStrategy(self.client, sym, '5m', sma_period=20, rsi_period=14)
                strat.rsi_buy_thresh = 35 # Easier entry for BTC
                strat.sl_pct = 0.02 # Tight SL
            elif sym == 'ETH/USDT':
                # Standard
                strat = TrendRSIStrategy(self.client, sym, '5m')
            else:
                # Altcoins (Aggressive)
                strat = TrendRSIStrategy(self.client, sym, '5m')
                strat.rsi_buy_thresh = 25 # Strict entry (deep dip)
                strat.sl_pct = 0.05 # Wider SL for volatility
                strat.tp_pct = 0.10 # Higher reward target
                
            print(f"   🔹 Strategy for {sym} initialized (Buy<{strat.rsi_buy_thresh}, SL {strat.sl_pct*100}%)")
            self.strategies[sym] = strat
            # Initial update
            try: await strat.update()
            except: pass

        # Snapshot Session Start NAV
        self.balance = await self.client.get_balance()
        if self.balance and 'total' in self.balance:
            total_nav = self.balance['total'].get('USDT', 0)
            for coin, qty in self.balance['total'].items():
                if coin == 'USDT': continue
                price = self.market_prices.get(f"{coin}/USDT", 0)
                if price == 0: 
                    # Try fetch
                    try: 
                        t = await self.client.exchange.fetch_ticker(f"{coin}/USDT")
                        price = t['last']
                    except: pass
                total_nav += (qty * price)
            self.session_start_nav = total_nav
            print(f"💰 Session Start NAV: {self.session_start_nav:.2f} USDT")

        self.is_running = True
        self.task = asyncio.create_task(self.run_loop())
        return {"message": f"Started {mode} mode"}

    async def stop(self):
        if not self.is_running: return {"message": "Already stopped"}
        self.is_running = False
        if self.task: await self.task 
        return {"message": "Bot stopped"}

    async def get_status(self):
        # Construct Status Object
        response = {
            "is_running": self.is_running,
            "mode": self.mode,
            "balance": {
                "USDT": self.balance['total'].get('USDT', 0) if self.balance and 'total' in self.balance else 0,
                # Add total equity estimate
                "estimated_nav": self.session_start_nav + self.pnl_history[-1]['value'] if self.pnl_history else 0
            },
            "strategies": {},
            "pnl": {
                "current": self.pnl_history[-1]['value'] if self.pnl_history else 0,
                "history": self.pnl_history,
                "daily_realized": self.calculate_daily_realized_pnl()
            },
            "scanner": self.scanner_results,
            "trades": self.trades,
            "prices": self.market_prices
        }
        
        # Strategy Details
        for sym, strat in self.strategies.items():
            info = strat.get_strategy_info()
            # Add History for Chart
            if sym in self.price_history:
                info['history'] = self.price_history[sym]
            response['strategies'][sym] = info
            
        return response
    
    def calculate_daily_realized_pnl(self):
        # ... (Keep existing FIFO logic)
        try:
            from datetime import datetime
            today = datetime.now().date()
            sorted_trades = sorted(self.trades, key=lambda x: x['time'])
            
            # We need per-symbol inventory now!
            inventories = {} # Dict[Symbol, List[{price, amount}]]
            daily_realized_pnl = 0.0
            
            for t in sorted_trades:
                # Parse Time
                trade_ts = t['time']
                if isinstance(trade_ts, str):
                    try: dt = datetime.fromisoformat(trade_ts)
                    except: continue
                else:
                    dt = datetime.fromtimestamp(trade_ts / 1000)
                
                is_today = (dt.date() == today)
                side = t['side'].upper()
                price = float(t['price'])
                amount = float(t['amount'])
                symbol = t.get('symbol', 'BTC/USDT') # Default fallback
                
                if symbol not in inventories: inventories[symbol] = []
                inventory = inventories[symbol]

                if side == 'BUY':
                    inventory.append({'price': price, 'amount': amount})
                
                elif side == 'SELL':
                    qty_to_fill = amount
                    cost_basis = 0.0
                    
                    while qty_to_fill > 0 and inventory:
                        batch = inventory[0]
                        if batch['amount'] > qty_to_fill:
                            cost_basis += (batch['price'] * qty_to_fill)
                            batch['amount'] -= qty_to_fill
                            qty_to_fill = 0
                        else:
                            cost_basis += (batch['price'] * batch['amount'])
                            qty_to_fill -= batch['amount']
                            inventory.pop(0)

                    if qty_to_fill > 0: cost_basis += (price * qty_to_fill)
                    
                    revenue = price * amount
                    trade_pnl = revenue - cost_basis
                    
                    if is_today: daily_realized_pnl += trade_pnl
                        
            return daily_realized_pnl
        except Exception as e:
            print(f"⚠️ Daily PnL Error: {e}")
            return 0.0

    async def get_news(self):
        return {"summary": self.market_sentiment, "news": self.news_analyzer.cached_news if self.news_analyzer else []}

# --- FastAPI App ---
bot = BotController()

@asynccontextmanager
async def lifespan(app: FastAPI):
    await bot.initialize()
    yield
    if bot.client: await bot.client.close()

app = FastAPI(lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
async def read_root(): return FileResponse('static/index.html')

@app.get("/api/status")
async def get_status(): return await bot.get_status()

@app.get("/api/news")
async def get_news(): return await bot.get_news()

class StartRequest(BaseModel):
    mode: str = "SINGLE"
    symbols: list = ["BTC/USDT"]

@app.post("/api/start")
async def start_bot(req: StartRequest):
    return await bot.start(req.mode, req.symbols)

@app.post("/api/stop")
async def stop_bot(): return await bot.stop()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("okx_bot.server:app", host="127.0.0.1", port=8000, reload=True)
