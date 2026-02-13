import logging
import time

from config import Config

logger = logging.getLogger(__name__)


class SleepTracker:
    def __init__(self, config: Config):
        self._config = config
        self._last_known_state: str = "unknown"
        self._last_data_fetch: float = 0.0
        self._consecutive_errors: int = 0

    @property
    def last_known_state(self) -> str:
        return self._last_known_state

    def update_state(self, state: str) -> None:
        if state != self._last_known_state:
            logger.info(
                "Vehicle state changed: %s -> %s",
                self._last_known_state,
                state,
            )
        self._last_known_state = state
        self._consecutive_errors = 0

    def record_error(self) -> None:
        self._consecutive_errors += 1
        if self._consecutive_errors >= 5:
            logger.warning(
                "Consecutive errors: %d. Using reduced poll rate.",
                self._consecutive_errors,
            )

    def record_successful_fetch(self) -> None:
        self._last_data_fetch = time.time()

    def should_fetch_data(self, current_state: str) -> bool:
        if current_state == "online":
            return True

        if current_state == "asleep":
            if self._config.wake_on_poll:
                logger.info("Vehicle asleep, will wake (WAKE_ON_POLL=true)")
                return True
            logger.info("Vehicle asleep, skipping data fetch to preserve battery")
            return False

        if current_state == "offline":
            logger.info("Vehicle offline, skipping data fetch")
            return False

        # Unknown or error state
        logger.info("Vehicle state '%s', skipping data fetch", current_state)
        return False

    def get_poll_interval(self) -> int:
        # After many consecutive errors, slow down
        if self._consecutive_errors >= 5:
            return max(
                self._config.poll_interval_seconds,
                self._config.sleep_poll_interval_seconds,
            )

        if self._last_known_state in ("asleep", "offline", "unknown"):
            return self._config.sleep_poll_interval_seconds

        return self._config.poll_interval_seconds
