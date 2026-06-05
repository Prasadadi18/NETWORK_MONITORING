from scapy.all import sniff, IP
import sys

print("Testing Scapy sniff... (will stop after 1 packet or 5 seconds)")
try:
    pkts = sniff(filter="ip", count=1, timeout=5)
    if pkts:
        print(f"Captured: {pkts[0].summary()}")
    else:
        print("Timed out - no packets captured.")
except Exception as e:
    print(f"Error during sniff: {e}")
    sys.exit(1)
