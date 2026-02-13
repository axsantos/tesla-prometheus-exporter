#!/usr/bin/env python3
"""Tesla Prometheus Exporter - Main entry point.

Polls the Tesla Fleet API for vehicle data and exposes metrics
on an HTTP endpoint for Prometheus to scrape.
"""

import logging
import signal
import sys
import threading

from prometheus_client import REGISTRY
from prometheus_client.exposition import start_http_server

from config import Config
from metrics import TeslaCollector
from sleep_tracker import SleepTracker
from tesla_auth import TeslaAuth
from tesla_client import TeslaClient

logger = logging.getLogger("tesla_exporter")


def main() -> None:
    # Load configuration
    try:
        config = Config.from_env()
    except KeyError as e:
        print(f"Missing required environment variable: {e}", file=sys.stderr)
        print("Set TESLA_CLIENT_ID and TESLA_CLIENT_SECRET.", file=sys.stderr)
        sys.exit(1)

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, config.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    # Initialize components
    auth = TeslaAuth(config)
    if not auth.load_token():
        logger.error(
            "No token file found at %s. "
            "Run 'python setup_token.py' first to authenticate.",
            config.token_file_path,
        )
        sys.exit(1)

    client = TeslaClient(config, auth)
    tracker = SleepTracker(config)
    collector = TeslaCollector()

    # Register the custom collector (unregister defaults we don't need)
    REGISTRY.register(collector)

    # Start Prometheus HTTP server
    start_http_server(config.exporter_port)
    logger.info("Prometheus metrics server started on port %d", config.exporter_port)

    # Graceful shutdown
    stop_event = threading.Event()

    def shutdown_handler(signum, frame):
        logger.info("Received signal %d, shutting down...", signum)
        stop_event.set()

    signal.signal(signal.SIGTERM, shutdown_handler)
    signal.signal(signal.SIGINT, shutdown_handler)

    # Resolve target vehicle
    vehicle_id = None
    vehicle_name = "unknown"

    # Main polling loop
    logger.info(
        "Starting polling loop (interval=%ds, sleep_interval=%ds, wake_on_poll=%s)",
        config.poll_interval_seconds,
        config.sleep_poll_interval_seconds,
        config.wake_on_poll,
    )

    while not stop_event.is_set():
        try:
            # List vehicles to get state (lightweight call, does not wake)
            vehicles = client.list_vehicles()

            if not vehicles:
                logger.warning("No vehicles returned from API")
                collector.mark_api_unreachable()
                tracker.record_error()
            else:
                vehicle = vehicles[min(config.tesla_vehicle_index, len(vehicles) - 1)]
                vehicle_id = vehicle.get("id")
                vehicle_name = vehicle.get("display_name", "Tesla")
                current_state = vehicle.get("state", "unknown")

                tracker.update_state(current_state)

                if tracker.should_fetch_data(current_state):
                    # Wake if needed
                    if current_state == "asleep" and config.wake_on_poll:
                        if not client.wake_vehicle(vehicle_id):
                            collector.update(None, current_state, vehicle_name)
                            tracker.record_error()
                            wait_interval = tracker.get_poll_interval()
                            stop_event.wait(wait_interval)
                            continue

                    # Fetch vehicle data
                    data = client.get_vehicle_data(vehicle_id)
                    if data is not None:
                        collector.update(data, current_state, vehicle_name)
                        tracker.record_successful_fetch()
                        logger.info(
                            "Fetched data for '%s' (state=%s)",
                            vehicle_name,
                            current_state,
                        )
                        # Debug: log drive_state keys to diagnose location
                        drive_state = data.get("drive_state", {})
                        logger.debug(
                            "drive_state keys: %s",
                            list(drive_state.keys()) if drive_state else "empty",
                        )
                        logger.debug(
                            "drive_state latitude=%r longitude=%r",
                            drive_state.get("latitude"),
                            drive_state.get("longitude"),
                        )
                    else:
                        collector.update(None, current_state, vehicle_name)
                        collector.record_error("vehicle_data_failed")
                        tracker.record_error()
                        logger.warning("Failed to fetch vehicle data")
                else:
                    # Not fetching data but still update state
                    collector.update(None, current_state, vehicle_name)

        except Exception:
            logger.exception("Unexpected error in polling loop")
            collector.record_error("unexpected_error")
            tracker.record_error()

        # Wait for next poll cycle
        wait_interval = tracker.get_poll_interval()
        logger.debug("Next poll in %ds", wait_interval)
        stop_event.wait(wait_interval)

    logger.info("Exporter shut down cleanly")


if __name__ == "__main__":
    main()
