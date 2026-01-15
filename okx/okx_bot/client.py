"""
Async OKX Client Wrapper using CCXT (Async Support).
Handles authentication, connection, and basic trading operations asynchronously.
"""
import ccxt.async_support as ccxt
from .config import Config

class OKXClient:
    def __init__(self, config: Config):
        self.config = config
        options = {
            'apiKey': config.API_KEY,
            'secret': config.SECRET_KEY,
            'password': config.PASSPHRASE,
            'enableRateLimit': True,
        }
        
        # Configure custom aiohttp session to fix DNS issues
        import aiohttp
        import asyncio
        
        # Use default asyncio resolver instead of aiodns to avoid DNS errors
        connector = aiohttp.TCPConnector(
            use_dns_cache=False,
            ttl_dns_cache=300,
            resolver=None,  # Use default asyncio resolver
            limit=100,
        )
        
        # Configure Proxy
        if config.HTTP_PROXY:
            print(f"🌍 Using Proxy: {config.HTTP_PROXY}")
            options['proxies'] = {
                'http': config.HTTP_PROXY,
                'https': config.HTTP_PROXY,
            }
            options['aiohttp_proxy'] = config.HTTP_PROXY
        
        # Set custom session
        options['aiohttp_connector'] = connector
            
        self.exchange = ccxt.okx(options)
        
        # Set Sandbox Mode
        if config.SANDBOX_MODE:
            self.exchange.set_sandbox_mode(True)
            print("🧪 Sandbox Mode Enabled (Demo Trading)")
            print(f"   API URLs: {self.exchange.urls}")
        else:
            print("⚠️ LIVE TRADING MODE - Real Money!")
            print(f"   API URLs: {self.exchange.urls}")
    
    async def initialize(self):
        """Initialize the exchange by loading markets."""
        try:
            await self.exchange.load_markets()
            print(f"✅ Loaded {len(self.exchange.markets)} markets from OKX")
            return True
        except Exception as e:
            print(f"❌ Failed to load markets: {e}")
            print(f"   Error Type: {type(e).__name__}")
            if hasattr(e, 'args') and len(e.args) > 0:
                print(f"   Details: {e.args}")
            import traceback
            traceback.print_exc()
            return False

    async def close(self):
        """Closes the exchange connection properly."""
        await self.exchange.close()

    async def check_connection(self):
        """Checks connection to the exchange by fetching the ticker for BTC/USDT."""
        try:
            ticker = await self.exchange.fetch_ticker('BTC/USDT')
            print(f"✅ Connection Successful! BTC/USDT Price: {ticker['last']}")
            return True
        except Exception as e:
            print(f"❌ Connection Failed: {e}")
            return False

    async def get_balance(self):
        """Fetches total balance."""
        try:
            balance = await self.exchange.fetch_balance()
            return balance
        except Exception as e:
            print(f"❌ Error fetching balance: {e}")
            return None

    async def fetch_ohlcv(self, symbol, timeframe='1m', limit=100):
        """Fetches OHLCV (candlestick) data from the exchange."""
        try:
            ohlcv = await self.exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
            return ohlcv
        except Exception as e:
            print(f"❌ Error fetching OHLCV for {symbol}: {e}")
            return None

    async def place_order(self, symbol, side, amount, order_type='market', price=None):
        """Places an order on the exchange."""
        try:
            order = await self.exchange.create_order(symbol, order_type, side, amount, price)
            print(f"✅ Order Placed: {side} {amount} {symbol}")
            return order
        except Exception as e:
            print(f"❌ Order Failed: {e}")
            return None
    async def fetch_recent_trades(self, symbol, limit=20):
        """Fetches recent filled orders."""
        try:
            # OKX specific: fetch_orders with status='filled'
            # Note: fetch_orders might return open orders too depending on params, 
            # but usually for history we might need fetch_closed_orders or fetch_my_trades
            # fetch_my_trades is often cleaner for "execution history"
            
            trades = await self.exchange.fetch_closed_orders(symbol, limit=limit)
            return trades
        except Exception as e:
            print(f"❌ Error fetching recent trades: {e}")
            return []
