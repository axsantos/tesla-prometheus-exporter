# Tesla Prometheus Exporter

A self-hosted monitoring stack that collects metrics from your Tesla vehicle via the [Tesla Fleet API](https://developer.tesla.com/docs/fleet-api) and visualizes them in Grafana.

![Python](https://img.shields.io/badge/python-3.12-blue)
![Prometheus](https://img.shields.io/badge/prometheus-2.53-orange)
![Grafana](https://img.shields.io/badge/grafana-11.4-green)
![License](https://img.shields.io/badge/license-MIT-lightgrey)

## Features

- **40+ vehicle metrics** — battery, charging, climate, tire pressure, GPS location, doors, software version, and more
- **Metric system units** — all distances in km, speeds in km/h, pressures in bar, temperatures in Celsius
- **Smart polling** — respects vehicle sleep state to preserve 12V battery; longer intervals when car is asleep
- **Pre-built Grafana dashboard** — ready to use with gauges, time series, stat panels, and a live geomap with car icon
- **OAuth2 token lifecycle** — automatic refresh with atomic file writes and exponential backoff
- **Docker Compose stack** — one command to run exporter + Prometheus + Grafana
- **1-year data retention** — track trends over time with Prometheus TSDB

## Dashboard Preview

The pre-built dashboard includes:

| Section | Panels |
|---|---|
| **Status** | Vehicle state, software version, lock status, sentry mode |
| **Battery & Charging** | Battery level gauge, range trends, charging status, charger power, energy added |
| **Climate** | Interior/exterior temps, HVAC status, fan speed, preconditioning |
| **Tire Pressure** | Current pressure bar gauge, pressure history |
| **Odometer & Drive** | Odometer, daily distance, speed |
| **Vehicle State** | Doors, trunks, user present |
| **Location** | Live geomap with car marker |

## Prerequisites

1. **Tesla Developer Account** — register at [developer.tesla.com](https://developer.tesla.com)
2. **Tesla Developer App** — create an application to get a `client_id` and `client_secret`
3. **A domain you control** — needed for the OAuth redirect URI and to host your public key (Tesla does not allow `localhost`)
4. **Docker & Docker Compose** — to run the stack
5. **Tesla virtual key** installed on your vehicle — required for Fleet API access ([instructions](https://developer.tesla.com/docs/fleet-api#virtual-keys))

## Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/axsantos/tesla-prometheus-exporter.git
cd tesla-prometheus-exporter
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your credentials:

```env
TESLA_CLIENT_ID=your-client-id
TESLA_CLIENT_SECRET=your-client-secret
TESLA_REDIRECT_URI=https://yourdomain.com/callback
```

Set the correct regional API endpoint:

| Region | `TESLA_API_BASE` |
|---|---|
| North America | `https://fleet-api.prd.na.vn.cloud.tesla.com` |
| Europe / Middle East / Africa | `https://fleet-api.prd.eu.vn.cloud.tesla.com` |
| China | `https://fleet-api.prd.cn.vn.cloud.tesla.com` |

### 3. Generate a key pair and host the public key

Tesla requires your app's public key to be hosted at a well-known URL on your domain.

Generate an EC key pair:

```bash
mkdir -p data
openssl ecparam -name prime256v1 -genkey -noout -out data/private-key.pem
openssl ec -in data/private-key.pem -pubout -out data/public-key.pem
```

Host `data/public-key.pem` at:

```
https://yourdomain.com/.well-known/appspecific/com.tesla.3p.public-key.pem
```

> **Nginx example:** If your domain runs Nginx, add this block inside your `server {}`:
> ```nginx
> location ^~ /.well-known/appspecific/ {
>     alias /path/to/your/well-known/appspecific/;
>     default_type text/plain;
>     try_files $uri =404;
> }
> ```

### 4. Register as a Tesla partner

This is a one-time step per region:

```bash
pip install requests
python exporter/register_partner.py
```

You should see a `200` or `201` response confirming registration.

### 5. Obtain OAuth tokens

Run the interactive setup tool:

```bash
python exporter/setup_token.py
```

The tool will:

1. Print an authorization URL — open it in your browser
2. Log in with your Tesla account and authorize the app
3. You'll be redirected to your redirect URI (the page may show an error — that's normal)
4. Copy the **full redirect URL** from your browser's address bar and paste it back into the terminal
5. Tokens are saved to `data/tokens/token.json`

> **Important:** Make sure the redirect URI in your Tesla Developer App settings **exactly matches** `TESLA_REDIRECT_URI` in your `.env` (including `www.` if applicable).

### 6. Start the stack

```bash
docker compose up -d
```

Three services will start:

| Service | Port | Description |
|---|---|---|
| `tesla-exporter` | `9090` | Prometheus metrics endpoint |
| `prometheus` | `9091` | Time-series database |
| `grafana` | `3000` | Dashboard UI |

### 7. Open Grafana

Navigate to [http://localhost:3000](http://localhost:3000) and log in:

- **Username:** `admin`
- **Password:** `admin` (or whatever you set in `GF_SECURITY_ADMIN_PASSWORD`)

Go to **Dashboards > Tesla > Tesla Overview**. Data will appear after the first polling cycle (up to 5 minutes).

## Configuration Reference

All settings are configured via environment variables in `.env`:

| Variable | Default | Description |
|---|---|---|
| `TESLA_CLIENT_ID` | *(required)* | Tesla app client ID |
| `TESLA_CLIENT_SECRET` | *(required)* | Tesla app client secret |
| `TESLA_REDIRECT_URI` | `https://localhost/callback` | OAuth redirect URI |
| `TESLA_API_BASE` | `https://fleet-api.prd.na.vn.cloud.tesla.com` | Regional Fleet API base URL |
| `TESLA_AUTH_BASE` | `https://auth.tesla.com` | Tesla auth endpoint |
| `TESLA_TOKEN_BASE` | `https://fleet-auth.prd.vn.cloud.tesla.com` | Tesla token endpoint |
| `TESLA_SCOPES` | `openid offline_access vehicle_device_data vehicle_location` | OAuth scopes |
| `TESLA_VEHICLE_INDEX` | `0` | Which vehicle to monitor (0 = first) |
| `POLL_INTERVAL_SECONDS` | `300` | Polling interval when vehicle is online (seconds) |
| `SLEEP_POLL_INTERVAL_SECONDS` | `660` | Polling interval when vehicle is asleep (seconds) |
| `WAKE_ON_POLL` | `false` | Wake the vehicle on every poll (prevents sleep!) |
| `EXPORTER_PORT` | `9090` | Prometheus metrics HTTP port |
| `TOKEN_FILE_PATH` | `/data/tokens/token.json` | Path to store OAuth tokens |
| `LOG_LEVEL` | `INFO` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`) |
| `GF_SECURITY_ADMIN_PASSWORD` | `admin` | Grafana admin password |

## Metrics

The exporter exposes ~40 Prometheus metrics. Key metrics include:

### Battery & Charging

| Metric | Description |
|---|---|
| `tesla_battery_level_percent` | Battery state of charge (0-100) |
| `tesla_battery_range_km` | Rated range in km |
| `tesla_charge_energy_added_kwh` | Energy added in session |
| `tesla_charger_power_kw` | Charger power output |
| `tesla_charging_state` | Current state (Charging, Complete, Disconnected, Stopped, NoPower) |

### Climate

| Metric | Description |
|---|---|
| `tesla_inside_temperature_celsius` | Interior temperature |
| `tesla_outside_temperature_celsius` | Exterior temperature |
| `tesla_climate_on` | HVAC active (0/1) |
| `tesla_fan_status` | Fan speed level |

### Drive & Location

| Metric | Description |
|---|---|
| `tesla_latitude` / `tesla_longitude` | GPS coordinates |
| `tesla_speed_kmh` | Vehicle speed |
| `tesla_odometer_km` | Odometer reading |
| `tesla_heading_degrees` | Heading (0-360) |

### Vehicle State

| Metric | Description |
|---|---|
| `tesla_locked` | Lock state (0/1) |
| `tesla_sentry_mode` | Sentry mode (0/1) |
| `tesla_tpms_pressure_bar` | Tire pressure per wheel (bar) |
| `tesla_software_version_info` | Software version as label |
| `tesla_door_open` | Door state per door (0/1) |

### Exporter Health

| Metric | Description |
|---|---|
| `tesla_exporter_up` | Exporter can reach Tesla API (0/1) |
| `tesla_exporter_vehicle_reachable` | Vehicle is online (0/1) |
| `tesla_exporter_poll_errors_total` | Error count by type |

## Architecture

```
                   ┌──────────────┐
                   │  Tesla Fleet │
                   │     API      │
                   └──────┬───────┘
                          │ HTTPS (polling)
                   ┌──────▼───────┐
                   │    Tesla     │
                   │   Exporter   │ :9090/metrics
                   └──────┬───────┘
                          │ scrape every 60s
                   ┌──────▼───────┐
                   │  Prometheus  │ :9091
                   │   (1y TSDB)  │
                   └──────┬───────┘
                          │ query
                   ┌──────▼───────┐
                   │   Grafana    │ :3000
                   │  Dashboard   │
                   └──────────────┘
```

## Smart Polling Behaviour

The exporter tracks your vehicle's state and adjusts polling to avoid draining the 12V battery:

- **Online** — polls every 5 minutes (configurable)
- **Asleep / Offline** — polls every 11 minutes with a lightweight status check (does not wake the car)
- **Errors** — exponential backoff after 5 consecutive failures
- **`WAKE_ON_POLL=true`** — forces the car awake on every poll (not recommended for daily use)

## Troubleshooting

### "No data" in Grafana

- Wait for the first polling cycle (up to 5 minutes)
- Check exporter logs: `docker compose logs tesla-exporter`
- Verify metrics are being served: `curl http://localhost:9090/metrics | grep tesla_`
- Verify Prometheus is scraping: open `http://localhost:9091/targets`

### Token errors

- Re-run `python exporter/setup_token.py` to get fresh tokens
- Make sure `TOKEN_FILE_PATH` in `.env` is set to `./data/tokens/token.json` when running locally
- The Docker container uses `/data/tokens/token.json` automatically (set via `docker-compose.yml`)

### "Account must be registered in the current region" (412)

- Run `python exporter/register_partner.py` to register in your region
- Make sure `TESLA_API_BASE` matches your region

### "Public key download failed" (424)

- Verify your public key is accessible at `https://yourdomain.com/.well-known/appspecific/com.tesla.3p.public-key.pem`
- Test: `curl https://yourdomain.com/.well-known/appspecific/com.tesla.3p.public-key.pem`

### "We don't recognize this redirect_uri"

- The redirect URI in your Tesla Developer App must **exactly match** `TESLA_REDIRECT_URI` (including protocol, subdomain, and path)

### Vehicle location not showing on map

- The Tesla Fleet API requires the `location_data` endpoint to be explicitly requested — this is already handled by the exporter
- Make sure your OAuth scopes include `vehicle_location`

### Grafana password forgotten

```bash
docker compose exec grafana grafana cli admin reset-admin-password NEW_PASSWORD
```

## Development

Run the exporter locally (outside Docker):

```bash
cd exporter
pip install -r requirements.txt

# Make sure .env has TOKEN_FILE_PATH=./data/tokens/token.json
export $(grep -v '^#' ../.env | xargs)
python main.py
```

## License

MIT
