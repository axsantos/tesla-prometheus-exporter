#!/usr/bin/env python3
"""CLI tool to perform the initial Tesla OAuth2 authorization flow.

Run this once to obtain access and refresh tokens before starting the exporter.

Usage:
    python setup_token.py
"""

import sys
from urllib.parse import parse_qs, urlparse

from config import Config
from tesla_auth import TeslaAuth


def main() -> None:
    try:
        config = Config.from_env()
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        print("Set TESLA_CLIENT_ID and TESLA_CLIENT_SECRET before running.")
        sys.exit(1)

    auth = TeslaAuth(config)

    print("=" * 60)
    print("  Tesla OAuth2 Setup")
    print("=" * 60)
    print()

    auth_url, state = auth.get_authorization_url()

    print("Step 1: Open the following URL in your browser:")
    print()
    print(f"  {auth_url}")
    print()
    print("Step 2: Log in to your Tesla account and authorize the app.")
    print()
    print("Step 3: After authorizing, your browser will redirect to a URL")
    print(f"  starting with: {config.tesla_redirect_uri}")
    print()
    print("  The page will likely show an error (that's normal).")
    print("  Copy the FULL URL from the browser's address bar.")
    print()

    redirect_url = input("Paste the redirect URL here: ").strip()
    if not redirect_url:
        print("No URL provided. Aborting.")
        sys.exit(1)

    # Parse the authorization code from the redirect URL
    parsed = urlparse(redirect_url)
    params = parse_qs(parsed.query)

    if "code" not in params:
        print("Error: No 'code' parameter found in the URL.")
        print(f"URL parameters found: {list(params.keys())}")
        sys.exit(1)

    code = params["code"][0]
    returned_state = params.get("state", [None])[0]

    if returned_state != state:
        print("Warning: State parameter mismatch. Proceeding anyway.")

    print()
    print("Exchanging authorization code for tokens...")

    try:
        auth.exchange_code(code)
    except Exception as e:
        print(f"Error exchanging code: {e}")
        sys.exit(1)

    print(f"Tokens saved to: {config.token_file_path}")
    print()

    # Verify by listing vehicles
    print("Verifying access by listing your vehicles...")
    print()

    import requests

    headers = {"Authorization": f"Bearer {auth.access_token}"}
    resp = requests.get(
        f"{config.tesla_api_base}/api/1/vehicles",
        headers=headers,
        timeout=30,
    )

    if resp.status_code == 200:
        vehicles = resp.json().get("response", [])
        if vehicles:
            print(f"Found {len(vehicles)} vehicle(s):")
            for i, v in enumerate(vehicles):
                print(f"  [{i}] {v.get('display_name', 'Unknown')} "
                      f"(VIN: {v.get('vin', 'N/A')}, "
                      f"State: {v.get('state', 'N/A')})")
        else:
            print("No vehicles found. Make sure your app has the correct scopes")
            print("and the virtual key is installed on your vehicle.")
    else:
        print(f"Failed to list vehicles: {resp.status_code} {resp.text[:200]}")

    print()
    print("Setup complete! You can now start the exporter with:")
    print("  docker compose up -d")


if __name__ == "__main__":
    main()
