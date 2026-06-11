# src/plutus/data/reddit.py
import praw
from typing import Dict
from datetime import datetime, timedelta
from plutus.config import settings

SUBREDDITS = ["IndianStreetBets", "IndiaInvestments", "Zerodha", "stocks"]


def get_reddit_client():
    return praw.Reddit(
        client_id=settings.REDDIT_CLIENT_ID,
        client_secret=settings.REDDIT_CLIENT_SECRET,
        user_agent=settings.REDDIT_USER_AGENT,
    )


def get_reddit_sentiment(symbol: str, days: int = 7) -> Dict:
    """
    Returns mention count + sentiment estimate for a stock.
    Falls back gracefully if Reddit is not configured.
    """
    if not settings.REDDIT_ENABLED:
        return {"mentions": 0, "sentiment": "neutral", "posts": []}

    reddit = get_reddit_client()
    cutoff = datetime.utcnow() - timedelta(days=days)
    mentions = []

    for subreddit_name in SUBREDDITS:
        try:
            subreddit = reddit.subreddit(subreddit_name)
            for post in subreddit.search(symbol, time_filter="week", limit=20):
                if datetime.utcfromtimestamp(post.created_utc) > cutoff:
                    mentions.append(
                        {
                            "title": post.title,
                            "score": post.score,
                            "upvote_ratio": post.upvote_ratio,
                            "num_comments": post.num_comments,
                            "subreddit": subreddit_name,
                        }
                    )
        except Exception:
            continue

    if not mentions:
        return {"mentions": 0, "sentiment": "neutral", "posts": []}

    avg_ratio = sum(m["upvote_ratio"] for m in mentions) / len(mentions)
    high_engagement = [m for m in mentions if m["num_comments"] > 10]

    if avg_ratio > 0.75 and len(high_engagement) > 2:
        sentiment = "positive"
    elif avg_ratio < 0.45:
        sentiment = "negative"
    else:
        sentiment = "neutral"

    return {
        "mentions": len(mentions),
        "sentiment": sentiment,
        "avg_upvote_ratio": round(avg_ratio, 2),
        "high_engagement_posts": len(high_engagement),
        "posts": mentions[:5],
    }
