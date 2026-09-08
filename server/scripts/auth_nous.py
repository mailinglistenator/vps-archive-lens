#!/usr/bin/env python3
"""
Nous Research Device Authorization Flow
Requests a device code from Nous Portal, prints the verification URL,
and polls for user approval. Once approved, saves tokens into ~/.hermes/auth.json
and ~/.hermes/shared/nous_auth.json.
"""
import sys
import time
import json
import os
from pathlib import Path
from datetime import datetime, timezone
import urllib.request
import urllib.parse
import urllib.error

CLIENT_ID = "hermes-cli"
PORTAL_URL = "https://portal.nousresearch.com"
SCOPE = "inference:invoke tool:invoke"
INFERENCE_URL = "https://inference-api.nousresearch.com/v1"

def request_device_code():
    url = f"{PORTAL_URL}/api/oauth/device/code"
    data = urllib.parse.urlencode({
        "client_id": CLIENT_ID,
        "scope": SCOPE
    }).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def poll_for_token(device_code: str, expires_in: int = 600, interval: int = 5):
    url = f"{PORTAL_URL}/api/oauth/token"
    deadline = time.time() + expires_in
    data = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
        "client_id": CLIENT_ID,
        "device_code": device_code
    }).encode("utf-8")

    while time.time() < deadline:
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                if resp.status == 200:
                    return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            try:
                err = json.loads(e.read().decode("utf-8"))
                err_code = err.get("error")
                if err_code == "authorization_pending":
                    time.sleep(interval)
                    continue
                elif err_code == "slow_down":
                    time.sleep(interval + 2)
                    continue
                else:
                    raise RuntimeError(f"OAuth Error: {err_code} - {err.get('error_description')}")
            except Exception as parse_err:
                raise RuntimeError(f"HTTP Error {e.code}: {e.reason}") from parse_err
        time.sleep(interval)
    raise TimeoutError("Timed out waiting for authorization.")

def save_credentials(token_data):
    now = datetime.now(timezone.utc)
    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = int(token_data.get("expires_in", 3600))
    expires_at = datetime.fromtimestamp(now.timestamp() + expires_in, tz=timezone.utc).isoformat()
    inference_base_url = token_data.get("inference_base_url") or INFERENCE_URL

    auth_file = Path.home() / ".hermes/auth.json"
    auth_data = {}
    if auth_file.is_file():
        try:
            with open(auth_file, "r", encoding="utf-8") as f:
                auth_data = json.load(f)
        except Exception:
            auth_data = {}

    auth_data.setdefault("providers", {})
    auth_data["active_provider"] = "nous"
    nous_state = auth_data["providers"].get("nous", {})
    nous_state.update({
        "access_token": access_token,
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "portal_base_url": PORTAL_URL,
        "inference_base_url": inference_base_url,
        "scope": token_data.get("scope") or SCOPE,
        "obtained_at": now.isoformat(),
        "expires_at": expires_at,
        "expires_in": expires_in,
        "token_type": token_data.get("token_type", "Bearer")
    })
    auth_data["providers"]["nous"] = nous_state

    auth_file.parent.mkdir(parents=True, exist_ok=True)
    with open(auth_file, "w", encoding="utf-8") as f:
        json.dump(auth_data, f, indent=2)

    # Also update ~/.hermes/shared/nous_auth.json
    shared_file = Path.home() / ".hermes/shared/nous_auth.json"
    try:
        shared_file.parent.mkdir(parents=True, exist_ok=True)
        shared_data = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "client_id": CLIENT_ID,
            "portal_base_url": PORTAL_URL,
            "inference_base_url": inference_base_url,
            "scope": token_data.get("scope") or SCOPE,
            "obtained_at": now.isoformat(),
            "expires_at": expires_at,
            "expires_in": expires_in
        }
        with open(shared_file, "w", encoding="utf-8") as sf:
            json.dump(shared_data, sf, indent=2)
    except Exception as e:
        print(f"Warning: Could not update shared nous_auth.json: {e}")

    print(f"\n[✓] Credentials successfully saved to {auth_file}")

def test_inference(token):
    print("Testing Nous inference endpoint with 'upstage/solar-pro4:free'...")
    req_data = json.dumps({
        "model": "upstage/solar-pro4:free",
        "messages": [{"role": "user", "content": "Respond with 'Nous operational'"}],
        "max_tokens": 20
    }).encode("utf-8")
    req = urllib.request.Request(
        f"{INFERENCE_URL}/chat/completions",
        data=req_data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "HermesAgent/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            content = data["choices"][0]["message"]["content"]
            print(f"[✓] Inference test succeeded: {content.strip()}")
            return True
    except Exception as e:
        print(f"[!] Inference test failed: {e}")
        return False

def main():
    print("Requesting device code from Nous Portal...")
    device_data = request_device_code()
    verification_url = device_data["verification_uri_complete"]
    user_code = device_data["user_code"]
    expires_in = int(device_data["expires_in"])
    interval = int(device_data.get("interval", 5))

    print("\n" + "=" * 60)
    print("  NOUS RESEARCH AUTHORIZATION")
    print("=" * 60)
    print(f"  Approval URL : {verification_url}")
    print(f"  User Code    : {user_code}")
    print(f"  Valid for    : {expires_in} seconds ({expires_in // 60} minutes)")
    print("=" * 60)
    print("\nWaiting for you to approve in your browser...")
    sys.stdout.flush()

    try:
        token_data = poll_for_token(device_data["device_code"], expires_in=expires_in, interval=interval)
    except TimeoutError:
        print("\n[✗] Authorization timed out.")
        sys.exit(1)
    except Exception as e:
        print(f"\n[✗] Authorization error: {e}")
        sys.exit(1)

    save_credentials(token_data)
    test_inference(token_data["access_token"])
    print("\n[✓] Nous authentication is fully complete and active!")

if __name__ == "__main__":
    main()
