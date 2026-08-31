"""
Automated Integration Test for RFID Terminal Backend Sync & API Communication
"""
import urllib.request
import json
import os
import sys

BACKEND_URL = os.environ.get("SERVER_URL", "http://localhost:3001")

def test_health():
    print(f"1. Testing Health Endpoint on {BACKEND_URL}/health...")
    req = urllib.request.Request(f"{BACKEND_URL}/health", headers={"User-Agent": "RFID-Test/1.0"})
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200, f"Expected 200, got {res.status}"
        data = json.loads(res.read().decode("utf-8"))
        assert data.get("status") == "ok", f"Expected status ok, got {data}"
        print(f"   [OK] Health Check passed: status={data.get('status')}, uptime={data.get('uptime')}")

def test_rfid_registration():
    print(f"\n2. Testing RFID Registration (Student 2204099 + RFID 'E200001906')...")
    payload = json.dumps({
        "studentId": "2204099",
        "rfid": "E200001906"
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{BACKEND_URL}/api/auth/register",
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "RFID-Test/1.0"},
        method="POST"
    )

    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data.get("success") == True, f"Registration failed: {data}"
        assert data.get("player", {}).get("rfid") == "E200001906"
        print(f"   [OK] Registration passed: Dept={data.get('player', {}).get('deptCode')}, RFID={data.get('player', {}).get('rfid')}")

def test_rfid_lookup():
    print(f"\n3. Testing RFID Card Lookup (/api/player/rfid/E200001906)...")
    req = urllib.request.Request(
        f"{BACKEND_URL}/api/player/rfid/E200001906",
        headers={"User-Agent": "RFID-Test/1.0"}
    )
    with urllib.request.urlopen(req, timeout=5) as res:
        assert res.status == 200
        data = json.loads(res.read().decode("utf-8"))
        assert data.get("success") == True
        assert data.get("player", {}).get("studentId") == "2204099"
        print(f"   [OK] Lookup by RFID passed! Matched Student: {data.get('player', {}).get('studentId')}")

def test_invalid_rfid_lookup():
    print(f"\n4. Testing Unregistered RFID Card Lookup (/api/player/rfid/UNKNOWN999)...")
    try:
        req = urllib.request.Request(
            f"{BACKEND_URL}/api/player/rfid/UNKNOWN999",
            headers={"User-Agent": "RFID-Test/1.0"}
        )
        with urllib.request.urlopen(req, timeout=5) as res:
            print("   [FAIL] Should have 404'd!")
            sys.exit(1)
    except urllib.error.HTTPError as e:
        assert e.code == 404
        print("   [OK] Correctly returned 404 for unregistered card")

if __name__ == "__main__":
    try:
        test_health()
        test_rfid_registration()
        test_rfid_lookup()
        test_invalid_rfid_lookup()
        print("\n=== ALL RFID BACKEND INTEGRATION TESTS PASSED SUCCESSFULLY! ===\n")
    except Exception as e:
        print(f"\n[FAIL] Test Failed: {e}")
        sys.exit(1)
