import logging
import time

import requests

from config import Config
from tesla_auth import TeslaAuth

logger = logging.getLogger(__name__)


class TeslaClient:
    def __init__(self, config: Config, auth: TeslaAuth):
        self._config = config
        self._auth = auth
        self._session = requests.Session()

    def _request(self, method: str, path: str, **kwargs) -> dict | None:
        url = f"{self._config.tesla_api_base}{path}"
        max_retries = 3
        backoff = 1

        for attempt in range(max_retries):
            token = self._auth.access_token
            if token is None:
                logger.error("No valid access token available")
                return None

            headers = kwargs.pop("headers", {})
            headers["Authorization"] = f"Bearer {token}"

            try:
                resp = self._session.request(
                    method, url, headers=headers, timeout=30, **kwargs
                )

                if resp.status_code == 200:
                    return resp.json()

                if resp.status_code == 401 and attempt == 0:
                    logger.warning("Got 401, refreshing token and retrying")
                    self._auth.refresh_access_token()
                    continue

                if resp.status_code == 408:
                    logger.info("Vehicle offline/unreachable (408)")
                    return None

                if resp.status_code == 429:
                    retry_after = int(resp.headers.get("Retry-After", 30))
                    logger.warning("Rate limited, sleeping %ds", retry_after)
                    time.sleep(retry_after)
                    continue

                if resp.status_code >= 500:
                    logger.warning(
                        "Server error %d (attempt %d/%d): %s",
                        resp.status_code,
                        attempt + 1,
                        max_retries,
                        resp.text[:200],
                    )
                    if attempt < max_retries - 1:
                        time.sleep(min(backoff, 60))
                        backoff *= 2
                    continue

                # Other 4xx
                logger.error(
                    "API error %d: %s", resp.status_code, resp.text[:200]
                )
                return None

            except requests.RequestException as e:
                logger.warning(
                    "Request failed (attempt %d/%d): %s",
                    attempt + 1,
                    max_retries,
                    e,
                )
                if attempt < max_retries - 1:
                    time.sleep(min(backoff, 60))
                    backoff *= 2

        logger.error("All %d request attempts failed for %s", max_retries, path)
        return None

    def list_vehicles(self) -> list[dict]:
        result = self._request("GET", "/api/1/vehicles")
        if result is None:
            return []
        return result.get("response", [])

    def get_vehicle_data(self, vehicle_id: int) -> dict | None:
        # Request all data categories explicitly, including location_data
        endpoints = (
            "charge_state;"
            "climate_state;"
            "drive_state;"
            "location_data;"
            "vehicle_state;"
            "vehicle_config"
        )
        result = self._request(
            "GET",
            f"/api/1/vehicles/{vehicle_id}/vehicle_data",
            params={"endpoints": endpoints},
        )
        if result is None:
            return None
        return result.get("response")

    def wake_vehicle(self, vehicle_id: int) -> bool:
        logger.info("Sending wake command to vehicle %d", vehicle_id)
        self._request("POST", f"/api/1/vehicles/{vehicle_id}/wake_up")

        # Poll until online or timeout
        max_wait = 60
        interval = 5
        elapsed = 0

        while elapsed < max_wait:
            time.sleep(interval)
            elapsed += interval
            vehicles = self.list_vehicles()
            for v in vehicles:
                if v.get("id") == vehicle_id and v.get("state") == "online":
                    logger.info("Vehicle %d is now online", vehicle_id)
                    return True

        logger.warning("Vehicle %d did not wake within %ds", vehicle_id, max_wait)
        return False
