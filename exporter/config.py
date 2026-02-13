import os
from dataclasses import dataclass


@dataclass
class Config:
    # Tesla API credentials
    tesla_client_id: str
    tesla_client_secret: str
    tesla_redirect_uri: str
    tesla_api_base: str
    tesla_auth_base: str
    tesla_token_base: str
    tesla_scopes: str
    tesla_vehicle_index: int

    # Polling
    poll_interval_seconds: int
    sleep_poll_interval_seconds: int
    wake_on_poll: bool

    # Exporter
    exporter_port: int
    token_file_path: str
    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            tesla_client_id=os.environ["TESLA_CLIENT_ID"],
            tesla_client_secret=os.environ["TESLA_CLIENT_SECRET"],
            tesla_redirect_uri=os.environ.get(
                "TESLA_REDIRECT_URI", "https://localhost/callback"
            ),
            tesla_api_base=os.environ.get(
                "TESLA_API_BASE",
                "https://fleet-api.prd.na.vn.cloud.tesla.com",
            ),
            tesla_auth_base=os.environ.get(
                "TESLA_AUTH_BASE", "https://auth.tesla.com"
            ),
            tesla_token_base=os.environ.get(
                "TESLA_TOKEN_BASE",
                "https://fleet-auth.prd.vn.cloud.tesla.com",
            ),
            tesla_scopes=os.environ.get(
                "TESLA_SCOPES",
                "openid offline_access vehicle_device_data vehicle_location",
            ),
            tesla_vehicle_index=int(os.environ.get("TESLA_VEHICLE_INDEX", "0")),
            poll_interval_seconds=int(
                os.environ.get("POLL_INTERVAL_SECONDS", "300")
            ),
            sleep_poll_interval_seconds=int(
                os.environ.get("SLEEP_POLL_INTERVAL_SECONDS", "660")
            ),
            wake_on_poll=os.environ.get("WAKE_ON_POLL", "false").lower()
            in ("true", "1", "yes"),
            exporter_port=int(os.environ.get("EXPORTER_PORT", "9090")),
            token_file_path=os.environ.get(
                "TOKEN_FILE_PATH", "/data/tokens/token.json"
            ),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
