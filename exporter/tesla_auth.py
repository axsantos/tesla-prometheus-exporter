import json
import logging
import os
import secrets
import tempfile
import time
from urllib.parse import urlencode

import requests

from config import Config

logger = logging.getLogger(__name__)


class TeslaAuth:
    def __init__(self, config: Config):
        self._config = config
        self._token_data: dict | None = None

    @property
    def access_token(self) -> str | None:
        if self._token_data is None:
            return None
        if not self.is_token_valid:
            self.refresh_access_token()
        return self._token_data.get("access_token") if self._token_data else None

    @property
    def is_token_valid(self) -> bool:
        if self._token_data is None:
            return False
        expires_at = self._token_data.get("expires_at", 0)
        # Refresh proactively 5 minutes before expiry
        return time.time() < (expires_at - 300)

    def load_token(self) -> bool:
        path = self._config.token_file_path
        if not os.path.exists(path):
            logger.warning("Token file not found at %s", path)
            return False
        try:
            with open(path) as f:
                self._token_data = json.load(f)
            logger.info("Loaded token from %s", path)
            return True
        except (json.JSONDecodeError, OSError) as e:
            logger.error("Failed to load token file: %s", e)
            return False

    def save_token(self, token_data: dict) -> None:
        path = self._config.token_file_path
        os.makedirs(os.path.dirname(path), exist_ok=True)
        # Atomic write: write to temp file then rename
        dir_name = os.path.dirname(path)
        try:
            fd, tmp_path = tempfile.mkstemp(dir=dir_name, suffix=".tmp")
            with os.fdopen(fd, "w") as f:
                json.dump(token_data, f, indent=2)
            os.replace(tmp_path, path)
            self._token_data = token_data
            logger.info("Token saved to %s", path)
        except OSError as e:
            logger.critical("Failed to save token file: %s", e)
            # Try to clean up temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise

    def refresh_access_token(self) -> None:
        if self._token_data is None or "refresh_token" not in self._token_data:
            logger.error("No refresh token available")
            return

        url = f"{self._config.tesla_token_base}/oauth2/v3/token"
        payload = {
            "grant_type": "refresh_token",
            "client_id": self._config.tesla_client_id,
            "client_secret": self._config.tesla_client_secret,
            "refresh_token": self._token_data["refresh_token"],
        }

        backoff = 1
        max_retries = 5
        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 200:
                    data = resp.json()
                    token_data = {
                        "access_token": data["access_token"],
                        "refresh_token": data["refresh_token"],
                        "expires_at": time.time() + data.get("expires_in", 3600),
                        "token_type": data.get("token_type", "Bearer"),
                        "created_at": time.time(),
                    }
                    # Save immediately — refresh tokens are single-use
                    self.save_token(token_data)
                    logger.info("Token refreshed successfully")
                    return
                else:
                    logger.warning(
                        "Token refresh failed (attempt %d/%d): %d %s",
                        attempt + 1,
                        max_retries,
                        resp.status_code,
                        resp.text[:200],
                    )
            except requests.RequestException as e:
                logger.warning(
                    "Token refresh request failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )

            if attempt < max_retries - 1:
                time.sleep(min(backoff, 60))
                backoff *= 2

        logger.critical(
            "Token refresh failed after %d attempts. "
            "Old refresh token may remain valid for ~24 hours.",
            max_retries,
        )
        self._token_data = None

    def get_authorization_url(self) -> tuple[str, str]:
        state = secrets.token_urlsafe(32)
        params = {
            "response_type": "code",
            "client_id": self._config.tesla_client_id,
            "redirect_uri": self._config.tesla_redirect_uri,
            "scope": self._config.tesla_scopes,
            "state": state,
        }
        url = f"{self._config.tesla_auth_base}/oauth2/v3/authorize?{urlencode(params)}"
        return url, state

    def exchange_code(self, code: str) -> dict:
        url = f"{self._config.tesla_token_base}/oauth2/v3/token"
        payload = {
            "grant_type": "authorization_code",
            "client_id": self._config.tesla_client_id,
            "client_secret": self._config.tesla_client_secret,
            "code": code,
            "audience": self._config.tesla_api_base,
            "redirect_uri": self._config.tesla_redirect_uri,
        }
        resp = requests.post(url, json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        token_data = {
            "access_token": data["access_token"],
            "refresh_token": data["refresh_token"],
            "expires_at": time.time() + data.get("expires_in", 3600),
            "token_type": data.get("token_type", "Bearer"),
            "created_at": time.time(),
        }
        self.save_token(token_data)
        return token_data
