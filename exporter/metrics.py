import logging
import time

from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

logger = logging.getLogger(__name__)

# Conversion factors
MILES_TO_KM = 1.609344
MPH_TO_KMH = 1.609344

# Charging states reported by the Tesla API
CHARGING_STATES = ("Charging", "Complete", "Disconnected", "Stopped", "NoPower")

# Shift states
SHIFT_STATES = ("P", "D", "R", "N")

# Door labels
DOORS = ("driver_front", "driver_rear", "passenger_front", "passenger_rear")

# Trunk labels
TRUNKS = ("front", "rear")

# Tire labels
TIRES = ("front_left", "front_right", "rear_left", "rear_right")

# Seat heater labels
SEATS = ("front_left", "front_right")


class TeslaCollector:
    """Custom Prometheus collector that serves cached Tesla vehicle data."""

    def __init__(self):
        self._vehicle_data: dict | None = None
        self._vehicle_state: str = "unknown"
        self._vehicle_name: str = "unknown"
        self._last_successful_poll: float = 0.0
        self._api_reachable: bool = False
        self._poll_errors: dict[str, int] = {}

    def update(
        self,
        vehicle_data: dict | None,
        vehicle_state: str,
        vehicle_name: str,
    ) -> None:
        self._vehicle_state = vehicle_state
        self._vehicle_name = vehicle_name
        self._api_reachable = True

        if vehicle_data is not None:
            self._vehicle_data = vehicle_data
            self._last_successful_poll = time.time()

    def record_error(self, error_type: str) -> None:
        self._poll_errors[error_type] = self._poll_errors.get(error_type, 0) + 1

    def mark_api_unreachable(self) -> None:
        self._api_reachable = False

    def collect(self):
        name = self._vehicle_name

        # --- Exporter health metrics ---
        up = GaugeMetricFamily(
            "tesla_exporter_up",
            "Whether the exporter can reach the Tesla API",
            labels=["vehicle_name"],
        )
        up.add_metric([name], 1.0 if self._api_reachable else 0.0)
        yield up

        reachable = GaugeMetricFamily(
            "tesla_exporter_vehicle_reachable",
            "Whether the vehicle is online",
            labels=["vehicle_name"],
        )
        reachable.add_metric(
            [name], 1.0 if self._vehicle_state == "online" else 0.0
        )
        yield reachable

        last_poll = GaugeMetricFamily(
            "tesla_exporter_last_successful_poll_timestamp_seconds",
            "Unix timestamp of last successful vehicle_data fetch",
            labels=["vehicle_name"],
        )
        if self._last_successful_poll > 0:
            last_poll.add_metric([name], self._last_successful_poll)
        yield last_poll

        errors = CounterMetricFamily(
            "tesla_exporter_poll_errors_total",
            "Count of polling errors by type",
            labels=["vehicle_name", "error_type"],
        )
        for err_type, count in self._poll_errors.items():
            errors.add_metric([name, err_type], count)
        yield errors

        # If we have no vehicle data yet, stop here
        if self._vehicle_data is None:
            return

        data = self._vehicle_data

        # --- Battery / Charge metrics (converted to km) ---
        charge = data.get("charge_state", {})
        if charge:
            yield self._gauge("tesla_battery_level_percent", "Battery level 0-100", name, charge.get("battery_level"))
            yield self._gauge("tesla_battery_usable_level_percent", "Usable battery level 0-100", name, charge.get("usable_battery_level"))
            yield self._gauge("tesla_battery_range_km", "Rated range in km", name, self._miles_to_km(charge.get("battery_range")))
            yield self._gauge("tesla_battery_ideal_range_km", "Ideal range in km", name, self._miles_to_km(charge.get("ideal_battery_range")))
            yield self._gauge("tesla_battery_estimated_range_km", "Estimated range in km", name, self._miles_to_km(charge.get("est_battery_range")))
            yield self._gauge("tesla_charge_limit_percent", "Charge limit SOC", name, charge.get("charge_limit_soc"))
            yield self._gauge("tesla_charge_energy_added_kwh", "Energy added in session (kWh)", name, charge.get("charge_energy_added"))
            yield self._gauge("tesla_charge_rate_kmh", "Charge rate (km/h)", name, self._miles_to_km(charge.get("charge_rate")))
            yield self._gauge("tesla_charger_power_kw", "Charger power (kW)", name, charge.get("charger_power"))
            yield self._gauge("tesla_charger_voltage_volts", "Charger voltage", name, charge.get("charger_voltage"))
            yield self._gauge("tesla_charger_actual_current_amps", "Charger current (amps)", name, charge.get("charger_actual_current"))
            yield self._gauge("tesla_charge_time_remaining_hours", "Time to full charge (hours)", name, charge.get("time_to_full_charge"))
            yield self._gauge("tesla_charge_port_door_open", "Charge port door open", name, self._bool(charge.get("charge_port_door_open")))
            yield self._gauge("tesla_battery_heater_on", "Battery heater active", name, self._bool(charge.get("battery_heater_on")))
            yield self._gauge("tesla_scheduled_charging_pending", "Scheduled charge pending", name, self._bool(charge.get("scheduled_charging_pending")))

            # Charging state as labeled gauge
            cs = GaugeMetricFamily(
                "tesla_charging_state",
                "Charging state (1 for active state)",
                labels=["vehicle_name", "state"],
            )
            current_charging = charge.get("charging_state", "")
            for s in CHARGING_STATES:
                cs.add_metric([name, s], 1.0 if s == current_charging else 0.0)
            yield cs

        # --- Climate metrics ---
        climate = data.get("climate_state", {})
        if climate:
            yield self._gauge("tesla_inside_temperature_celsius", "Interior temperature", name, climate.get("inside_temp"))
            yield self._gauge("tesla_outside_temperature_celsius", "Exterior temperature", name, climate.get("outside_temp"))
            yield self._gauge("tesla_driver_temperature_setting_celsius", "Driver temp setting", name, climate.get("driver_temp_setting"))
            yield self._gauge("tesla_passenger_temperature_setting_celsius", "Passenger temp setting", name, climate.get("passenger_temp_setting"))
            yield self._gauge("tesla_climate_on", "HVAC on", name, self._bool(climate.get("is_climate_on")))
            yield self._gauge("tesla_preconditioning", "Preconditioning active", name, self._bool(climate.get("is_preconditioning")))
            yield self._gauge("tesla_fan_status", "Fan speed level", name, climate.get("fan_status"))
            yield self._gauge("tesla_defrost_mode", "Defrost mode", name, climate.get("defrost_mode"))

            # Seat heaters
            sh = GaugeMetricFamily(
                "tesla_seat_heater_level",
                "Seat heater level",
                labels=["vehicle_name", "seat"],
            )
            seat_map = {
                "front_left": "seat_heater_left",
                "front_right": "seat_heater_right",
            }
            for seat_label, api_key in seat_map.items():
                val = climate.get(api_key)
                if val is not None:
                    sh.add_metric([name, seat_label], float(val))
            yield sh

        # --- Drive state metrics (speed converted to km/h) ---
        drive = data.get("drive_state", {})
        if drive:
            # Log drive_state for debugging location
            logger.debug("drive_state contents: %s", drive)

            # Location — try multiple possible key names
            lat = drive.get("latitude") or drive.get("active_route_latitude")
            lon = drive.get("longitude") or drive.get("active_route_longitude")
            yield self._gauge("tesla_latitude", "GPS latitude", name, lat)
            yield self._gauge("tesla_longitude", "GPS longitude", name, lon)
            yield self._gauge("tesla_heading_degrees", "Heading 0-360", name, drive.get("heading"))

            # Speed: API returns mph (or None when parked)
            speed_mph = drive.get("speed")
            speed_kmh = float(speed_mph) * MPH_TO_KMH if speed_mph is not None else 0.0
            yield self._gauge("tesla_speed_kmh", "Speed in km/h", name, speed_kmh)
            yield self._gauge("tesla_power_watts", "Drive power draw", name, drive.get("power"))

            # Shift state as labeled gauge
            ss = GaugeMetricFamily(
                "tesla_shift_state",
                "Shift state (1 for active state)",
                labels=["vehicle_name", "state"],
            )
            current_shift = drive.get("shift_state") or "P"
            for s in SHIFT_STATES:
                ss.add_metric([name, s], 1.0 if s == current_shift else 0.0)
            yield ss

        # --- Vehicle state metrics (odometer converted to km) ---
        vs = data.get("vehicle_state", {})
        if vs:
            yield self._gauge("tesla_odometer_km", "Odometer reading in km", name, self._miles_to_km(vs.get("odometer")))
            yield self._gauge("tesla_locked", "Vehicle locked", name, self._bool(vs.get("locked")))
            yield self._gauge("tesla_sentry_mode", "Sentry mode active", name, self._bool(vs.get("sentry_mode")))
            yield self._gauge("tesla_valet_mode", "Valet mode active", name, self._bool(vs.get("valet_mode")))
            yield self._gauge("tesla_user_present", "User present in vehicle", name, self._bool(vs.get("is_user_present")))
            yield self._gauge("tesla_remote_start", "Remote start active", name, self._bool(vs.get("remote_start")))
            yield self._gauge("tesla_center_display_state", "Center display state", name, vs.get("center_display_state"))

            # Doors
            doors_g = GaugeMetricFamily(
                "tesla_door_open",
                "Door open (1=open, 0=closed)",
                labels=["vehicle_name", "door"],
            )
            door_map = {
                "driver_front": "df",
                "driver_rear": "dr",
                "passenger_front": "pf",
                "passenger_rear": "pr",
            }
            for door_label, api_key in door_map.items():
                val = vs.get(api_key)
                if val is not None:
                    doors_g.add_metric([name, door_label], float(val))
            yield doors_g

            # Trunks
            trunks_g = GaugeMetricFamily(
                "tesla_trunk_open",
                "Trunk open (1=open, 0=closed)",
                labels=["vehicle_name", "trunk"],
            )
            trunk_map = {"front": "ft", "rear": "rt"}
            for trunk_label, api_key in trunk_map.items():
                val = vs.get(api_key)
                if val is not None:
                    trunks_g.add_metric([name, trunk_label], float(val))
            yield trunks_g

            # Tire pressure (already in bar — metric system)
            tpms_g = GaugeMetricFamily(
                "tesla_tpms_pressure_bar",
                "Tire pressure in bar",
                labels=["vehicle_name", "tire"],
            )
            tpms_map = {
                "front_left": "tpms_pressure_fl",
                "front_right": "tpms_pressure_fr",
                "rear_left": "tpms_pressure_rl",
                "rear_right": "tpms_pressure_rr",
            }
            for tire_label, api_key in tpms_map.items():
                val = vs.get(api_key)
                if val is not None:
                    tpms_g.add_metric([name, tire_label], float(val))
            yield tpms_g

            # Software version info metric
            version = vs.get("car_version", "unknown")
            sv = GaugeMetricFamily(
                "tesla_software_version_info",
                "Software version (always 1, version in label)",
                labels=["vehicle_name", "version"],
            )
            sv.add_metric([name, version], 1.0)
            yield sv

    @staticmethod
    def _gauge(metric_name: str, doc: str, vehicle_name: str, value) -> GaugeMetricFamily:
        g = GaugeMetricFamily(metric_name, doc, labels=["vehicle_name"])
        if value is not None:
            try:
                g.add_metric([vehicle_name], float(value))
            except (ValueError, TypeError):
                logger.debug("Cannot convert %s=%r to float", metric_name, value)
        return g

    @staticmethod
    def _bool(value) -> float | None:
        if value is None:
            return None
        return 1.0 if value else 0.0

    @staticmethod
    def _miles_to_km(value) -> float | None:
        if value is None:
            return None
        try:
            return float(value) * MILES_TO_KM
        except (ValueError, TypeError):
            return None
