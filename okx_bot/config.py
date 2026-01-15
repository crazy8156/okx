"""
Configuration settings for the OKX Trading Bot.
Loads environment variables.
"""
import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Config:
    API_KEY = os.getenv("OKX_API_KEY")
    SECRET_KEY = os.getenv("OKX_SECRET_KEY")
    PASSPHRASE = os.getenv("OKX_PASSPHRASE")
    
    # Proxy Settings
    HTTP_PROXY = os.getenv("HTTP_PROXY")
    
    # Sandbox mode (Demo Trading)
    # Ensure this is True for testing!
    SANDBOX_MODE = os.getenv('SANDBOX_MODE', 'True').lower() == 'true'
        
    # Virtual Capital Limit (for testing with limited funds)
    VIRTUAL_CAPITAL_USDT = float(os.getenv('VIRTUAL_CAPITAL_USDT', 0))

    # CryptoPanic API Key
    CRYPTOPANIC_API_KEY = os.getenv("CRYPTOPANIC_API_KEY")

    def validate(self):
        if not all([self.API_KEY, self.SECRET_KEY, self.PASSPHRASE]):
            raise ValueError("Missing API credentials. Please set OKX_API_KEY, OKX_SECRET_KEY, and OKX_PASSPHRASE in .env file.")
