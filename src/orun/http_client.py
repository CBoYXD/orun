from __future__ import annotations

import socket
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Mapping


class HttpClientError(Exception):
    """Base class for HTTP client errors."""


class HttpTimeoutError(HttpClientError):
    """Raised when a request exceeds the configured timeout."""


class HttpRetryError(HttpClientError):
    """Raised when all retry attempts are exhausted."""

    def __init__(self, message: str, last_error: Exception | None = None):
        super().__init__(message)
        self.last_error = last_error


class HttpResponseError(HttpClientError):
    """Raised for non-2xx HTTP responses."""

    def __init__(self, status: int, message: str, body: bytes | None = None):
        super().__init__(message)
        self.status = status
        self.body = body


@dataclass(frozen=True)
class HttpClientSettings:
    """Configuration for HTTP requests."""

    timeout: float
    retries: int
    backoff_factor: float
    user_agent: str = "Mozilla/5.0 (compatible; orun/1.0)"


@dataclass
class HttpResponse:
    """Represents an HTTP response."""

    url: str
    status: int
    body: bytes
    headers: Mapping[str, Any]

    def text(self, fallback_encoding: str = "utf-8") -> str:
        """Return the response body as text using charset hints."""
        charset = None
        try:
            if hasattr(self.headers, "get_content_charset"):
                charset = self.headers.get_content_charset()
            else:
                charset = self.headers.get("content-type", None)
                if charset and "charset=" in charset:
                    charset = charset.split("charset=")[-1].split(";")[0].strip()
        except Exception:
            charset = None

        encoding = charset or fallback_encoding
        return self.body.decode(encoding, errors="ignore")


class HttpClient:
    """Small HTTP client with retry/backoff and session reuse."""

    def __init__(
        self,
        settings: HttpClientSettings,
        opener: urllib.request.OpenerDirector | None = None,
    ) -> None:
        self.settings = settings
        self._opener = opener or urllib.request.build_opener()

    def get(
        self, url: str, headers: Mapping[str, str] | None = None
    ) -> HttpResponse:
        """Perform an HTTP GET request."""
        request_headers = {"User-Agent": self.settings.user_agent, "Connection": "keep-alive"}
        if headers:
            request_headers.update(headers)

        request = urllib.request.Request(url, headers=request_headers, method="GET")
        return self._request_with_retries(request)

    def _request_with_retries(
        self, request: urllib.request.Request
    ) -> HttpResponse:
        last_error: Exception | None = None
        for attempt in range(self.settings.retries + 1):
            try:
                with self._opener.open(request, timeout=self.settings.timeout) as response:
                    body = response.read()
                    status = getattr(response, "status", response.getcode())
                    if status >= 400:
                        raise HttpResponseError(
                            status,
                            f"HTTP {status} for {request.full_url}",
                            body=body,
                        )
                    return HttpResponse(
                        url=request.full_url,
                        status=status,
                        body=body,
                        headers=response.headers,
                    )
            except (TimeoutError, socket.timeout):
                last_error = HttpTimeoutError(f"Request to {request.full_url} timed out")
            except urllib.error.HTTPError as exc:
                last_error = HttpResponseError(
                    exc.code, f"HTTP {exc.code} for {request.full_url}", body=exc.read()
                )
            except urllib.error.URLError as exc:
                if isinstance(exc.reason, socket.timeout):
                    last_error = HttpTimeoutError(f"Request to {request.full_url} timed out")
                else:
                    last_error = HttpClientError(f"Network error for {request.full_url}: {exc.reason}")
            except Exception as exc:  # pragma: no cover - defensive
                last_error = HttpClientError(f"Unexpected error for {request.full_url}: {exc}")

            if attempt < self.settings.retries:
                time.sleep(self.settings.backoff_factor * (2**attempt))
            else:
                break

        raise HttpRetryError(
            f"Failed to fetch {request.full_url} after {self.settings.retries + 1} attempt(s)",
            last_error=last_error,
        )
