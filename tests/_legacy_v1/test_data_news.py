"""Tests for plutus.data.news module."""

import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from plutus.data import news
from plutus.db.models import RejectedHeadline


class TestLoadKeywords:
    def test_loads_and_caches_keywords(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A,B")

        # Reset cache
        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        keywords, stoplist = news._load_keywords()

        assert "earnings" in keywords
        assert "profit" in keywords
        assert "expansion" in keywords
        assert "rumor" in stoplist
        assert "speculation" in stoplist

    def test_filters_by_tier(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        keywords, stoplist = news._load_keywords()

        assert "earnings" in keywords
        assert "expansion" not in keywords  # tier_B excluded

    def test_caches_on_second_call(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        keywords1, stoplist1 = news._load_keywords()
        keywords2, stoplist2 = news._load_keywords()

        assert keywords1 is keywords2
        assert stoplist1 is stoplist2


class TestFetchNews:
    @patch("plutus.data.news.requests.get")
    def test_fetches_from_newsapi(self, mock_get, monkeypatch):
        monkeypatch.setattr("plutus.data.news.settings.NEWS_API_KEY", "test-key")

        mock_response = Mock()
        mock_response.json.return_value = {
            "articles": [
                {
                    "title": "RELIANCE earnings report",
                    "source": {"name": "NewsAPI"},
                    "publishedAt": "2026-05-30T10:00:00Z",
                    "url": "https://example.com/1",
                }
            ]
        }
        mock_get.return_value = mock_response

        with patch("plutus.data.news.feedparser.parse", return_value=Mock(entries=[])):
            results = news.fetch_news("RELIANCE", hours=48)

        assert len(results) >= 1
        assert any("RELIANCE" in r["headline"] for r in results)

    @patch("plutus.data.news.feedparser.parse")
    def test_fetches_from_rss_feeds(self, mock_parse, monkeypatch):
        monkeypatch.setattr("plutus.data.news.settings.NEWS_API_KEY", "")

        mock_entry = Mock()
        mock_entry.title = "RELIANCE stock update"
        mock_entry.published = "2026-05-30T10:00:00Z"
        mock_entry.link = "https://example.com/rss"
        mock_entry.get = lambda k, default="": {
            "title": "RELIANCE stock update",
            "published": "2026-05-30T10:00:00Z",
            "link": "https://example.com/rss",
        }.get(k, default)

        mock_feed = Mock()
        mock_feed.entries = [mock_entry]
        mock_parse.return_value = mock_feed

        results = news.fetch_news("RELIANCE", hours=48)

        assert len(results) >= 1
        assert any("RELIANCE" in r["headline"] for r in results)

    @patch("plutus.data.news.requests.get")
    @patch("plutus.data.news.feedparser.parse")
    def test_handles_api_failures_gracefully(self, mock_parse, mock_get, monkeypatch):
        monkeypatch.setattr("plutus.data.news.settings.NEWS_API_KEY", "test-key")

        mock_get.side_effect = Exception("API down")
        mock_parse.side_effect = Exception("Feed down")

        results = news.fetch_news("RELIANCE", hours=48)
        assert results == []


class TestPrefilterHeadlines:
    def test_keeps_keyword_matches(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A,B")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        headlines = [
            {"headline": "Company reports strong earnings", "source": "test"},
            {"headline": "Stock price update", "source": "test"},
        ]

        kept, rejected = news.prefilter_headlines(headlines)

        assert len(kept) == 1
        assert "earnings" in kept[0]["headline"]
        assert kept[0]["filter_status"] == "kept"

    def test_rejects_stoplist_matches(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A,B")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        headlines = [
            {"headline": "Unconfirmed rumor about earnings", "source": "test"},
        ]

        kept, rejected = news.prefilter_headlines(headlines)

        assert len(rejected) == 1
        assert rejected[0]["filter_status"] == "stoplist"

    def test_rejects_no_keyword_match(self, sample_keywords_yaml, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A,B")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        headlines = [
            {"headline": "Generic stock market news", "source": "test"},
        ]

        kept, rejected = news.prefilter_headlines(headlines)

        assert len(rejected) == 1
        assert rejected[0]["filter_status"] == "no_keyword"


class TestSaveRejectedHeadlines:
    @patch("plutus.data.news.SessionLocal")
    def test_saves_to_database(self, mock_session_local):
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        rejected = [
            {
                "headline": "Rejected 1",
                "source": "test",
                "published_at": "2026-05-30",
                "filter_status": "stoplist",
            },
            {
                "headline": "Rejected 2",
                "source": "test",
                "published_at": "2026-05-30",
                "filter_status": "no_keyword",
            },
        ]

        news.save_rejected_headlines("RELIANCE", rejected)

        assert mock_session.add.call_count == 2
        mock_session.commit.assert_called_once()

    @patch("plutus.data.news.SessionLocal")
    def test_handles_empty_list(self, mock_session_local):
        mock_session = MagicMock()
        mock_session_local.return_value.__enter__.return_value = mock_session

        news.save_rejected_headlines("RELIANCE", [])

        mock_session.add.assert_not_called()


class TestClassifyNews:
    def test_returns_neutral_for_empty_headlines(self):
        result = news.classify_news("RELIANCE", [])

        assert result["sentiment_score"] == 0
        assert result["sentiment_label"] == "neutral"
        assert result["is_material"] is False

    @patch("plutus.data.news.save_rejected_headlines")
    @patch("plutus.data.news._llm_batch_classify")
    def test_calls_llm_for_kept_headlines(
        self, mock_llm, mock_save, sample_keywords_yaml, monkeypatch
    ):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        mock_llm.return_value = {
            "sentiment_score": 8,
            "sentiment_label": "positive",
            "is_material": True,
            "material_event_type": "earnings",
            "summary": "Strong earnings",
        }

        headlines = [
            {"headline": "Company reports strong earnings", "source": "test"},
        ]

        result = news.classify_news("RELIANCE", headlines)

        assert result["sentiment_score"] == 8
        assert result["is_material"] is True
        mock_llm.assert_called_once()

    @patch("plutus.data.news.save_rejected_headlines")
    def test_skips_llm_when_all_rejected(
        self, mock_save, sample_keywords_yaml, monkeypatch
    ):
        monkeypatch.setattr(
            "plutus.data.news.settings.MATERIAL_KEYWORDS_YAML",
            str(sample_keywords_yaml),
        )
        monkeypatch.setattr("plutus.data.news.settings.MATERIAL_KEYWORD_TIERS", "A")

        news._KEYWORDS_CACHE = None
        news._STOPLIST_CACHE = None

        headlines = [
            {"headline": "Generic news", "source": "test"},
        ]

        result = news.classify_news("RELIANCE", headlines)

        assert result["sentiment_score"] == 0
        assert "filtered" in result["summary"]


class TestLlmBatchClassify:
    @patch("plutus.agents.openrouter_client.call_llm")
    def test_successful_classification(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.DEEPSEEK_FAST_MODEL", "test-model"
        )

        mock_llm.return_value = json.dumps(
            {
                "sentiment_score": 7,
                "sentiment_label": "positive",
                "is_material": True,
                "material_event_type": "earnings",
                "summary": "Strong quarterly results",
            }
        )

        kept = [
            {"headline": "Company reports earnings", "source": "test"},
        ]

        result = news._llm_batch_classify("RELIANCE", kept)

        assert result["sentiment_score"] == 7
        assert result["sentiment_label"] == "positive"
        assert result["is_material"] is True
        assert result["material_event_type"] == "earnings"

    @patch("plutus.agents.openrouter_client.call_llm")
    def test_handles_invalid_json(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.DEEPSEEK_FAST_MODEL", "test-model"
        )

        mock_llm.return_value = "invalid json"

        kept = [{"headline": "Test", "source": "test"}]
        result = news._llm_batch_classify("RELIANCE", kept)

        assert result["sentiment_score"] == 0
        assert result["sentiment_label"] == "neutral"
        assert "failed" in result["summary"].lower()

    @patch("plutus.agents.openrouter_client.call_llm")
    def test_handles_llm_exception(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.DEEPSEEK_FAST_MODEL", "test-model"
        )

        mock_llm.side_effect = Exception("LLM API error")

        kept = [{"headline": "Test", "source": "test"}]
        result = news._llm_batch_classify("RELIANCE", kept)

        assert result["sentiment_score"] == 0
        assert result["is_material"] is False

    @patch("plutus.agents.openrouter_client.call_llm")
    def test_limits_headlines_to_15(self, mock_llm, monkeypatch):
        monkeypatch.setattr(
            "plutus.data.news.settings.DEEPSEEK_FAST_MODEL", "test-model"
        )

        mock_llm.return_value = json.dumps(
            {
                "sentiment_score": 5,
                "sentiment_label": "neutral",
                "is_material": False,
                "material_event_type": None,
                "summary": "Test",
            }
        )

        kept = [{"headline": f"Headline {i}", "source": "test"} for i in range(20)]
        news._llm_batch_classify("RELIANCE", kept)

        # Check that the user message contains only 15 headlines
        # (count individual list items — "Headlines:" header also contains "Headline" once)
        call_args = mock_llm.call_args[0][0]
        user_msg = call_args[1]["content"]
        items = [ln for ln in user_msg.splitlines() if ln.startswith("- ")]
        assert len(items) == 15
