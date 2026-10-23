"""A small client for a helpdesk REST API (Zendesk-style endpoints).

What it takes care of:

- Every call uses HTTPS with certificate verification and a timeout.
- Rate limits: on HTTP 429 it waits as long as the server asks (Retry-After)
  and tries again, a limited number of times.
- Server errors (5xx) are retried with a growing wait; other errors stop at once.
- Open tickets are read page by page until there are no more pages.

The HTTP layer is passed in as a function, so tests can replace it.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request
from typing import Callable

# transport(method, url, headers, body) -> (status, response headers, response body)
Transport = Callable[[str, str, dict, bytes | None], tuple[int, dict, bytes]]


class HelpdeskError(Exception):
    pass


def https_transport(method: str, url: str, headers: dict, body: bytes | None) -> tuple[int, dict, bytes]:
    if not url.startswith("https://"):
        raise HelpdeskError("only HTTPS is allowed")
    context = ssl.create_default_context()  # verifies certificates
    request = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=30, context=context) as response:
            return response.status, dict(response.headers), response.read()
    except urllib.error.HTTPError as error:
        return error.code, dict(error.headers), error.read()


class HelpdeskClient:
    def __init__(self, base_url: str, token: str, transport: Transport = https_transport,
                 max_retries: int = 3, sleep: Callable[[float], None] = time.sleep):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.transport = transport
        self.max_retries = max_retries
        self.sleep = sleep

    def _request(self, method: str, path_or_url: str, payload: dict | None = None) -> dict:
        url = path_or_url if path_or_url.startswith("https://") else f"{self.base_url}{path_or_url}"
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        body = json.dumps(payload).encode() if payload is not None else None

        for attempt in range(self.max_retries + 1):
            status, response_headers, raw = self.transport(method, url, headers, body)
            if 200 <= status < 300:
                return json.loads(raw) if raw else {}
            retryable = status == 429 or status >= 500
            if not retryable or attempt == self.max_retries:
                raise HelpdeskError(f"{method} {url} failed with HTTP {status}")
            if status == 429:
                self.sleep(float(response_headers.get("Retry-After", 1)))
            else:
                self.sleep(2 ** attempt)
        raise HelpdeskError("unreachable")

    def open_tickets(self) -> list[dict]:
        tickets, next_page = [], "/api/v2/tickets?status=open"
        while next_page:
            page = self._request("GET", next_page)
            tickets.extend(page.get("tickets", []))
            next_page = page.get("next_page")
        return tickets

    def reply(self, ticket_id: str, text: str) -> None:
        """Public reply the customer sees."""
        self._request("PUT", f"/api/v2/tickets/{ticket_id}", {"ticket": {"comment": {"body": text, "public": True}}})

    def hold_for_person(self, ticket_id: str, reason: str) -> None:
        """Internal note with the reason, plus a tag so the ticket shows up in the person's view."""
        self._request("PUT", f"/api/v2/tickets/{ticket_id}", {
            "ticket": {"comment": {"body": f"Held for a person: {reason}", "public": False},
                       "additional_tags": ["needs-person"]},
        })

    def set_aside(self, ticket_id: str, reason: str) -> None:
        """Junk or duplicate: an internal note and a tag, no reply, so it never reaches the person's view."""
        self._request("PUT", f"/api/v2/tickets/{ticket_id}", {
            "ticket": {"comment": {"body": f"Set aside: {reason}", "public": False},
                       "additional_tags": ["filtered"]},
        })
