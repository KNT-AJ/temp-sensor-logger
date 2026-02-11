#!/usr/bin/env python3
"""
WiFi Signal Strength Monitor
Run on the Raspberry Pi to get numerical WiFi signal readings.
Useful for finding the best placement at an industrial site.

Usage:
    python3 wifi_strength.py          # continuous monitoring (updates every second)
    python3 wifi_strength.py --once   # single reading
"""

import subprocess
import re
import time
import sys


def get_wifi_stats():
    """Get WiFi signal strength from iwconfig."""
    try:
        result = subprocess.run(
            ["iwconfig", "wlan0"],
            capture_output=True, text=True, timeout=5
        )
        output = result.stdout

        stats = {}

        # ESSID (network name)
        match = re.search(r'ESSID:"(.+?)"', output)
        stats["SSID"] = match.group(1) if match else "N/A"

        # Signal level in dBm
        match = re.search(r'Signal level=(-?\d+)\s*dBm', output)
        stats["Signal (dBm)"] = int(match.group(1)) if match else None

        # Link quality
        match = re.search(r'Link Quality=(\d+)/(\d+)', output)
        if match:
            qual, max_qual = int(match.group(1)), int(match.group(2))
            stats["Quality"] = f"{qual}/{max_qual}"
            stats["Quality (%)"] = round((qual / max_qual) * 100, 1)
        else:
            stats["Quality"] = "N/A"
            stats["Quality (%)"] = None

        # Bit rate
        match = re.search(r'Bit Rate[=:](\S+\s*\S*b/s)', output)
        stats["Bit Rate"] = match.group(1).strip() if match else "N/A"

        # Frequency
        match = re.search(r'Frequency[=:](\S+\s*GHz)', output)
        stats["Frequency"] = match.group(1) if match else "N/A"

        return stats

    except FileNotFoundError:
        print("Error: 'iwconfig' not found. Install with: sudo apt install wireless-tools")
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}")
        return None


def signal_rating(dbm):
    """Rate the signal strength."""
    if dbm is None:
        return "???"
    if dbm >= -30:
        return "EXCELLENT"
    elif dbm >= -50:
        return "GREAT"
    elif dbm >= -60:
        return "GOOD"
    elif dbm >= -70:
        return "FAIR"
    elif dbm >= -80:
        return "WEAK"
    else:
        return "VERY WEAK"


def print_stats(stats):
    """Print formatted WiFi stats."""
    if not stats:
        print("Could not read WiFi stats")
        return

    dbm = stats.get("Signal (dBm)")
    rating = signal_rating(dbm)

    print(f"  SSID:        {stats['SSID']}")
    print(f"  Frequency:   {stats['Frequency']}")
    print(f"  Signal:      {dbm} dBm  [{rating}]")
    print(f"  Quality:     {stats['Quality']}  ({stats['Quality (%)']}%)")
    print(f"  Bit Rate:    {stats['Bit Rate']}")
    print()
    print("  Signal Guide:  -30=Excellent  -50=Great  -60=Good  -70=Fair  -80=Weak")


if __name__ == "__main__":
    once = "--once" in sys.argv

    if once:
        print("\n=== WiFi Signal Strength ===\n")
        stats = get_wifi_stats()
        print_stats(stats)
        print()
    else:
        print("WiFi Signal Monitor — press Ctrl+C to stop\n")
        try:
            while True:
                # Clear screen
                print("\033[2J\033[H", end="")
                print("=== WiFi Signal Strength (updating every 1s) ===")
                print(f"    Timestamp: {time.strftime('%H:%M:%S')}\n")
                stats = get_wifi_stats()
                print_stats(stats)
                print("\n  Press Ctrl+C to stop")
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nStopped.")
