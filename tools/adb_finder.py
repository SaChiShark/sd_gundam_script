"""ADB and Emulator Port Finder Utility."""
import os
import shutil
import socket
import subprocess
import sys
from typing import Dict, List, Tuple


COMMON_EMULATOR_PORTS: Dict[str, int] = {
    "BlueStacks 5 (Standard)": 5555,
    "MuMu Player 12": 16384,
    "LDPlayer 9": 5555,
    "Nox App Player (Instance 1)": 62001,
    "MEmu Play": 21503,
}

COMMON_ADB_PATHS: List[str] = [
    r"C:\Program Files\BlueStacks_nxt\HD-Adb.exe",
    r"C:\Program Files\Netease\MuMuPlayer-12.0\shell\adb.exe",
    r"C:\leidian\LDPlayer9\adb.exe",
    r"C:\Program Files\Nox\bin\nox_adb.exe",
]


def check_port(host: str, port: int, timeout: float = 1.0) -> bool:
    """Check if a local TCP port is listening."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        try:
            s.connect((host, port))
            return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            return False


def find_adb_binary() -> str:
    """Locate available ADB binary."""
    which_adb = shutil.which("adb")
    if which_adb:
        return which_adb

    for path in COMMON_ADB_PATHS:
        if os.path.isfile(path):
            return path

    return "adb"


def scan_devices() -> None:
    """Scan and report available ADB targets and emulators."""
    print("=" * 60)
    print(" ADB & Emulator Diagnostic Tool")
    print("=" * 60)

    # 1. Check ADB binary
    adb_bin = find_adb_binary()
    print(f"\n[1] ADB Executable: {adb_bin} ({'Found' if os.path.exists(adb_bin) else 'Using PATH'})")

    # 2. Check Emulator Ports
    print("\n[2] Scanning Local Emulator Ports (127.0.0.1):")
    detected = []
    for name, port in COMMON_EMULATOR_PORTS.items():
        is_open = check_port("127.0.0.1", port)
        status_str = "OPEN (Listening)" if is_open else "Closed"
        print(f"  - {name:30} : Port {port:<5} -> {status_str}")
        if is_open:
            detected.append((name, port))

    # 3. Query ADB devices
    print("\n[3] Querying Connected ADB Devices:")
    try:
        # Try connect first
        for _, port in detected:
            subprocess.run([adb_bin, "connect", f"127.0.0.1:{port}"], capture_output=True, timeout=5)

        res = subprocess.run([adb_bin, "devices"], capture_output=True, text=True, timeout=5)
        lines = res.stdout.strip().splitlines()
        for line in lines:
            print(f"  {line}")
    except Exception as e:
        print(f"  Error querying adb devices: {e}")

    print("\n" + "=" * 60)
    if detected:
        print(f"Summary: Found {len(detected)} active emulator port(s):")
        for name, port in detected:
            print(f"  -> {name} at 127.0.0.1:{port}")
    else:
        print("Summary: No active emulator ports detected.")
        print("Please ensure your emulator (BlueStacks, MuMu, etc.) is running and ADB is enabled.")
    print("=" * 60)


if __name__ == "__main__":
    scan_devices()
