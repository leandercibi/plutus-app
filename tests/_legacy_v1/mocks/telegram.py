"""Mock utilities for Telegram bot and push endpoints."""

from unittest.mock import AsyncMock, MagicMock
from typing import Optional


class MockTelegramBot:
    """Mock Telegram bot for testing."""

    def __init__(self):
        self.send_message = AsyncMock(return_value=MagicMock(message_id=12345))
        self.messages_sent = []

    async def send_message_tracked(self, chat_id: str, text: str, **kwargs):
        """Track sent messages for assertions."""
        self.messages_sent.append({"chat_id": chat_id, "text": text, "kwargs": kwargs})
        return await self.send_message(chat_id, text, **kwargs)


class MockPushEndpoint:
    """Mock plutus-bot push endpoint responses."""

    def __init__(self, success: bool = True, status_code: int = 200):
        self.success = success
        self.status_code = status_code
        self.calls = []

    def record_call(self, path: str, payload: dict):
        """Record push endpoint calls."""
        self.calls.append({"path": path, "payload": payload})

    def get_response(self):
        """Return mock HTTP response."""
        response = MagicMock()
        response.status_code = self.status_code
        if self.success:
            response.raise_for_status = MagicMock()
        else:
            response.raise_for_status = MagicMock(
                side_effect=Exception(f"HTTP {self.status_code}")
            )
        return response


def create_mock_telegram_bot():
    """Factory for creating mock Telegram bot."""
    return MockTelegramBot()


def create_mock_push_endpoint(success: bool = True, status_code: int = 200):
    """Factory for creating mock push endpoint."""
    return MockPushEndpoint(success=success, status_code=status_code)
