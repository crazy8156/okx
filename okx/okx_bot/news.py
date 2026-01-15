
import feedparser
from textblob import TextBlob
from datetime import datetime
import re

class NewsAnalyzer:
    def __init__(self, api_key=None):
        self.api_key = api_key
        self.rss_urls = [
            "https://cointelegraph.com/rss",
            "https://www.coindesk.com/arc/outboundfeeds/rss/",
            "https://decrypt.co/feed"
        ]
        self.cached_news = []
        self.last_fetch = None
        self.api_url = "https://cryptopanic.com/api/developer/v2/posts/"

    def clean_html(self, raw_html):
        cleanr = re.compile('<.*?>')
        cleantext = re.sub(cleanr, '', raw_html)
        return cleantext

    def get_sentiment(self, text):
        analysis = TextBlob(text)
        # Polarity: -1 (Negative) to 1 (Positive)
        polarity = analysis.sentiment.polarity
        
        if polarity > 0.1:
            return "BULLISH", polarity
        elif polarity < -0.1:
            return "BEARISH", polarity
        else:
            return "NEUTRAL", polarity

    async def fetch_rss(self):
        """Fetches news from RSS feeds with specific logic for each source."""
        rss_news = []
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            
            for url in self.rss_urls:
                # Run blocking feedparser in executor
                feed = await loop.run_in_executor(None, feedparser.parse, url)
                
                source_name = "RSS"
                if "coindesk" in url: source_name = "CoinDesk"
                elif "cointelegraph" in url: source_name = "CoinTelegraph"
                elif "decrypt" in url: source_name = "Decrypt"
                
                for entry in feed.entries[:5]:
                    title = entry.title
                    summary = self.clean_html(entry.summary) if 'summary' in entry else ""
                    text_content = title + " " + summary
                    
                    # Sentiment Analysis
                    sentiment, score = self.get_sentiment(text_content)
                    
                    # --- Source Specific Logic ---
                    # CoinDesk: "Breaking" or "SEC" has high impact
                    if source_name == "CoinDesk":
                        if "Breaking" in title or "SEC" in title:
                            score *= 1.5 # Boost impact
                            if abs(score) < 0.2: score = 0.5 if score >= 0 else -0.5 # Ensure it's not neutral
                    
                    # CoinTelegraph: Keyword filtering (Optional, currently just boosting "Regulation")
                    if source_name == "CoinTelegraph":
                        if "Regulation" in title:
                            score *= 1.2

                    # Identify Coins
                    coins = []
                    if re.search(r'\b(Bitcoin|BTC)\b', title, re.IGNORECASE): coins.append('BTC')
                    if re.search(r'\b(Ethereum|ETH)\b', title, re.IGNORECASE): coins.append('ETH')
                    if re.search(r'\b(Solana|SOL)\b', title, re.IGNORECASE): coins.append('SOL')

                    news_item = {
                        "title": title,
                        "link": entry.link,
                        "published": entry.published if 'published' in entry else str(datetime.now()),
                        "sentiment": sentiment,
                        "score": round(score, 2),
                        "coins": coins,
                        "source": source_name 
                    }
                    rss_news.append(news_item)
            return rss_news
        except Exception as e:
            print(f"❌ RSS Fetch Error: {e}")
            return []

    async def fetch_cryptopanic(self):
        """Fetches from CryptoPanic API."""
        if not self.api_key: return []
        
        cp_news = []
        try:
            import aiohttp
            params = {"auth_token": self.api_key, "public": "true"}
            async with aiohttp.ClientSession() as session:
                async with session.get(self.api_url, params=params) as response:
                    if response.status == 200:
                        data = await response.json()
                        for post in data.get('results', [])[:10]: # Top 10 from API
                            title = post.get('title', '')
                            votes = post.get('votes', {})
                            bullish = votes.get('bullish', 0)
                            bearish = votes.get('bearish', 0)
                            
                            score = 0
                            sentiment = "NEUTRAL"
                            if bullish > bearish:
                                sentiment = "BULLISH"
                                score = 0.6 # Stronger signal from community
                            elif bearish > bullish:
                                sentiment = "BEARISH"
                                score = -0.6
                            else:
                                sentiment, score = self.get_sentiment(title)

                            cp_news.append({
                                "title": title,
                                "link": post.get('url'),
                                "published": post.get('created_at'),
                                "sentiment": sentiment,
                                "score": round(score, 2),
                                "coins": [c.get('code') for c in post.get('currencies', [])],
                                "source": "CryptoPanic"
                            })
        except Exception as e:
            print(f"❌ CryptoPanic Error: {e}")
        return cp_news

    async def fetch_news(self):
        """Fetches from BOTH CryptoPanic and RSS, merging results."""
        print("🔗 Fetching Hybrid News (CryptoPanic + Premium RSS)...")
        
        # Run both tasks concurrently
        tasks = [self.fetch_rss()]
        if self.api_key:
            tasks.append(self.fetch_cryptopanic())
            
        import asyncio
        results = await asyncio.gather(*tasks)
        
        # Flatten list
        all_news = [item for sublist in results for item in sublist]
        
        # Deduplication (Simple check by title similarity could be better, but Link is safer)
        seen_links = set()
        unique_news = []
        for item in all_news:
            if item['link'] not in seen_links:
                unique_news.append(item)
                seen_links.add(item['link'])
        
        # Sort by published date (if possible) or just keep order (API usually new first)
        # For simplicity, we trust the fetch order but maybe prioritize API
        
        self.cached_news = unique_news[:20] # Keep top 20
        return self.cached_news

    def get_market_summary(self):
        """Aggregates sentiment to give a market overview."""
        if not self.cached_news:
            return {"sentiment": "NEUTRAL", "score": 0, "top_coins": []}
            
        total_score = sum([n['score'] for n in self.cached_news])
        avg_score = total_score / len(self.cached_news)
        
        overall = "NEUTRAL"
        if avg_score > 0.05: overall = "BULLISH"
        if avg_score < -0.05: overall = "BEARISH"
        
        return {
            "sentiment": overall,
            "score": round(avg_score, 2),
            "news_count": len(self.cached_news)
        }
