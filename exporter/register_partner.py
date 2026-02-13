#!/usr/bin/env python3
"""Register partner account in a Tesla Fleet API region.

Tesla requires your app to be registered in each region before you can
access vehicle data. Run this once per region.

Usage:
    python register_partner.py
"""

import sys

import requests

from config import Config


def main() -> None:
    try:
        config = Config.from_env()
    except KeyError as e:
        print(f"Missing required environment variable: {e}")
        sys.exit(1)

    print("=" * 60)
    print("  Tesla Partner Registration")
    print("=" * 60)
    print()
    print(f"Region: {config.tesla_api_base}")
    print()

    # Step 1: Get a partner token (client_credentials grant)
    print("Step 1: Obtaining partner token...")
    token_url = f"{config.tesla_token_base}/oauth2/v3/token"
    token_payload = {
        "grant_type": "client_credentials",
        "client_id": config.tesla_client_id,
        "client_secret": config.tesla_client_secret,
        "scope": "openid vehicle_device_data vehicle_cmds",
        "audience": config.tesla_api_base,
    }

    try:
        resp = requests.post(token_url, json=token_payload, timeout=30)
        if resp.status_code != 200:
            print(f"Failed to get partner token: {resp.status_code}")
            print(resp.text)
            sys.exit(1)
        partner_token = resp.json()["access_token"]
        print("  Partner token obtained.")
    except Exception as e:
        print(f"Error getting partner token: {e}")
        sys.exit(1)

    # Step 2: Register partner account in the region
    print()
    print("Step 2: Registering partner account...")
    register_url = f"{config.tesla_api_base}/api/1/partner_accounts"
    headers = {"Authorization": f"Bearer {partner_token}"}
    register_payload = {"domain": config.tesla_redirect_uri.split("//")[1].split("/")[0]}

    try:
        resp = requests.post(
            register_url, json=register_payload, headers=headers, timeout=30
        )
        print(f"  Response: {resp.status_code}")
        print(f"  {resp.text}")

        if resp.status_code in (200, 201):
            print()
            print("Partner account registered successfully!")
            print("You can now run setup_token.py or start the exporter.")
        else:
            print()
            print("Registration may have failed. Check the response above.")
            print()
            print("Note: You may need to host a public key at:")
            domain = register_payload["domain"]
            print(f"  https://{domain}/.well-known/appspecific/com.tesla.3p.public-key.pem")
    except Exception as e:
        print(f"Error registering: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
