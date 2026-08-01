"""Tiny HTTP client for talking to the hub.

Uses ``urllib`` from the standard library on purpose: the agent gets deployed onto nodes
where the only thing we can count on is a Python interpreter.
"""

from __future__ import annotations

import json
import logging
import ssl
import urllib.error
import urllib.request

log = logging.getLogger(__name__)


class HubClient:
    def __init__(self, url: str, token: str, timeout: float, insecure: bool = False) -> None:
        self.url = url
        self.timeout = timeout
        self._headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {token}",
        }
        self._ssl_context = ssl._create_unverified_context() if insecure else None
        self._consecutive_failures = 0

    def post_snapshot(self, payload: dict) -> dict | None:
        """Send one snapshot. Returns the hub's response, or None if it did not arrive."""
        body = json.dumps(payload).encode()
        request = urllib.request.Request(self.url, data=body, headers=self._headers, method="POST")
        try:
            kwargs = {"timeout": self.timeout}
            if self._ssl_context is not None:
                kwargs["context"] = self._ssl_context
            with urllib.request.urlopen(request, **kwargs) as response:
                data = json.loads(response.read().decode())
            if self._consecutive_failures:
                log.info("hub reachable again after %d failed push(es)", self._consecutive_failures)
                self._consecutive_failures = 0
            return data
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")[:200]
            self._note_failure(f"HTTP {exc.code}: {detail}")
        except Exception as exc:
            self._note_failure(str(exc))
        return None

    def _note_failure(self, message: str) -> None:
        self._consecutive_failures += 1
        # Noisy for the first few, then once every ~30 ticks, so a long outage does not
        # fill the log file.
        if self._consecutive_failures <= 3 or self._consecutive_failures % 30 == 0:
            log.warning("push to hub failed (%dx): %s", self._consecutive_failures, message)
