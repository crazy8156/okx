
import os
import ccxt
from dotenv import load_dotenv

# Load env directly to be sure
load_dotenv('C:\\Users\\crazy\\.gemini\\antigravity\\scratch\\okx\\.env')

def test_connection():
    api_key = os.getenv('OKX_API_KEY')
    secret = os.getenv('OKX_SECRET_KEY')
    password = os.getenv('OKX_PASSPHRASE')
    
    print(f"Testing with Key: {api_key[:5]}... and Passphrase: {password[:2]}...")
    
    try:
        exchange = ccxt.okx({
            'apiKey': api_key,
            'secret': secret,
            'password': password,
            'enableRateLimit': True,
        })
        # Use Sandbox mode if configured
        if os.getenv('SANDBOX_MODE', 'False').lower() == 'true':
            exchange.set_sandbox_mode(True)
            print("sandbox mode enabled")
            
        print("Fetching balance...")
        balance = exchange.fetch_balance()
        print("Connection Successful!")
        print("USDT Free:", balance['free']['USDT'] if 'USDT' in balance['free'] else "0")
        
    except Exception as e:
        print(f"Connection Failed: {str(e)}")

if __name__ == "__main__":
    test_connection()
