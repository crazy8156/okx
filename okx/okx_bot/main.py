"""
Main entry point for the OKX Trading Bot.
"""
import time
import schedule
from okx_bot.config import Config
from okx_bot.client import OKXClient
from okx_bot.strategies import SMACrossoverStrategy

def run_bot(strategy):
    """
    Job to run periodically.
    """
    try:
        print("\n--- Updating Strategy ---")
        strategy.update()
        signal = strategy.check_signals()
        
        if signal:
            print(f"🔔 SIGNAL DETECTED: {signal}")
            # Execute Order
            side = signal.lower() # 'buy' or 'sell'
            # Fixed amount for demo testing (e.g., 0.001 BTC or 10 USDT value equivalent)
            amount = 0.001 
            order_type = 'market'
            
            try:
                print(f"🚀 Placing {side.upper()} order for {amount} {strategy.symbol}...")
                order = strategy.client.exchange.create_order(strategy.symbol, order_type, side, amount)
                print(f"✅ Order Placed: {order['id']} | Status: {order['status']}")
            except Exception as e:
                print(f"❌ Order Failed: {e}")

        else:
            print("No signal.")
            
    except Exception as e:
        print(f"❌ Error in bot loop: {e}")

def main():
    print("🤖 Initializing OKX Auto Trading System...")
    
    # 1. Load Configuration
    config = Config()
    try:
        config.validate()
    except ValueError as e:
        print(f"Configuration Error: {e}")
        return

    # 2. Initialize Client
    client = OKXClient(config)
    if not client.check_connection():
        return

    # 3. Initialize Strategy
    # Using BTC/USDT and 1m timeframe for quick demos
    symbol = 'BTC/USDT'
    timeframe = '1m'
    print(f"📈 Starting SMA Strategy for {symbol} [{timeframe}]")
    strategy = SMACrossoverStrategy(client, symbol, timeframe, short_window=5, long_window=10) # Short windows for testing

    # 4. Schedule Job
    # Run every 10 seconds for testing purposes (real usage might be aligned with timeframe)
    schedule.every(10).seconds.do(run_bot, strategy=strategy)
    
    # Run once immediately
    run_bot(strategy)

    print("🚀 Bot is running... Press Ctrl+C to stop.")
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    main()
