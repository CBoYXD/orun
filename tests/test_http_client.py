from __future__ import annotations

import socket
import sys
import urllib.error
from email.message import Message
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from orun.http_client import (  # noqa: E402
    HttpClient,
    HttpClientError,
    HttpClientSettings,
    HttpRetryError,
    HttpResponse,
    HttpTimeoutError,
)


class DummyResponse:
    def __init__(self, body: bytes, status: int = 200, headers: Message | None = None):
        self.status = status
        self._body = body
        self.headers = headers or Message()

    def read(self) -> bytes:
        return self._body

    def getcode(self) -> int:
        return self.status

    def __enter__(self) -> "DummyResponse":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        return None


class SequenceOpener:
    def __init__(self, outcomes: list[Exception | DummyResponse]):
        self.outcomes = outcomes
        self.calls: list[tuple[str, float | None]] = []

    def open(self, request, timeout=None):
        self.calls.append((request.full_url, timeout))
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


class HttpClientTests(TestCase):
    def test_timeout_retries_then_raises(self) -> None:
        opener = SequenceOpener([TimeoutError(), TimeoutError(), TimeoutError()])
        client = HttpClient(
            HttpClientSettings(timeout=0.01, retries=2, backoff_factor=0.1),
            opener=opener,
        )

        with patch("orun.http_client.time.sleep") as sleep_mock:
            with self.assertRaises(HttpRetryError) as ctx:
                client.get("https://example.com")

        self.assertEqual(len(opener.calls), 3)
        self.assertIsInstance(ctx.exception.last_error, HttpTimeoutError)
        self.assertEqual(sleep_mock.call_count, 2)

    def test_network_error_raises_retry_error(self) -> None:
        opener = SequenceOpener(
            [urllib.error.URLError(socket.timeout("boom")), urllib.error.URLError("boom")]
        )
        client = HttpClient(
            HttpClientSettings(timeout=0.01, retries=1, backoff_factor=0.0),
            opener=opener,
        )

        with self.assertRaises(HttpRetryError) as ctx:
            client.get("https://example.com")

        self.assertIsInstance(ctx.exception.last_error, HttpClientError)
        self.assertEqual(len(opener.calls), 2)

    def test_successful_response_returns_text(self) -> None:
        headers = Message()
        headers.add_header("Content-Type", "text/plain; charset=utf-8")
        opener = SequenceOpener([DummyResponse(b"hello", headers=headers)])
        client = HttpClient(
            HttpClientSettings(timeout=1, retries=0, backoff_factor=0.0),
            opener=opener,
        )

        response: HttpResponse = client.get("https://example.com")
        self.assertEqual(response.text(), "hello")
        self.assertEqual(response.status, 200)
