
import google.generativeai as genai
import logging
import json
import asyncio

logger = logging.getLogger("OKX_Bot")

class AIManager:
    def __init__(self, api_key, model_name="gemini-pro"):
        self.api_key = api_key
        self.model_name = model_name
        self.enabled = False
        
        if self.api_key:
            try:
                genai.configure(api_key=self.api_key)
                self.model = genai.GenerativeModel(self.model_name)
                self.enabled = True
                logger.info(f"✅ AI Manager Initialized with {model_name}")
            except Exception as e:
                logger.error(f"❌ AI Init Failed: {e}")
        else:
            logger.warning("⚠️ No GOOGLE_API_KEY provided. AI features disabled.")

    async def analyze(self, market_data, news_summary):
        """
        Analyzes market data and news to decide on a trade action.
        """
        if not self.enabled:
            return {"action": "HOLD", "reason": "AI Disabled", "confidence": 0}

        prompt = f"""
        Act as an expert crypto trader. Analyze the following data and decide whether to BUY, SELL, or HOLD.
        
        Market Data:
        {market_data}
        
        News Context:
        {news_summary}
        
        Respond ONLY in JSON format:
        {{
            "action": "BUY" | "SELL" | "HOLD",
            "confidence": <number 0-100>,
            "reason": "<short explanation>"
        }}
        """
        
        try:
            # Run blocking AI call in executor
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(None, self.model.generate_content, prompt)
            
            text = response.text.replace('```json', '').replace('```', '').strip()
            result = json.loads(text)
            return result
            
        except Exception as e:
            logger.error(f"AI Analysis Error: {e}")
            return {"action": "HOLD", "reason": f"AI Error: {str(e)}", "confidence": 0}
