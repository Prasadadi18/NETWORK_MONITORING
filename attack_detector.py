"""
attack_detector.py

Now detects five attack types simultaneously.
Each detector runs its own independent logic
on the same stream of PacketMetadata objects.

DETECTION LOGIC SUMMARY:
  ICMP Flood    → count ICMP packets per IP per second
  SYN Flood     → count bare SYN packets per IP per second
  UDP Flood     → count UDP packets per IP per second
  Port Scan     → count unique destination ports per IP per window
  Fragmentation → count fragmented packets per IP per second
"""

import time
import logging
from collections import defaultdict, deque
from typing import Optional

import shared_state
from shared_state import PacketMetadata, ThreatEvent, AttackType

logger = logging.getLogger("detector")


# ==============================================================================
# Thresholds
# These are deliberately conservative for a local test machine.
# Lower = more sensitive (more false positives).
# Higher = less sensitive (might miss slow attacks).
# ==============================================================================

THRESHOLDS = {
    AttackType.ICMP_FLOOD:     20,   # ICMP packets per second
    AttackType.SYN_FLOOD:      20,   # SYN packets per second
    AttackType.UDP_FLOOD:      20,   # UDP packets per second
    AttackType.FRAGMENTATION:  10,   # Fragmented packets per second
    AttackType.PORT_SCAN:      10,   # Unique ports per 5 seconds
}

WINDOW_SECONDS    = 1.0    # Rate window for flood attacks
PORT_SCAN_WINDOW  = 5.0    # Wider window for port scans
                           # Slow scanners take longer than 1 second
COOLDOWN_SECONDS  = 60.0   # Don't re-alert same IP + attack type


# ==============================================================================
# Sliding Window Counter (same as before)
# ==============================================================================

class SlidingWindowCounter:
    """
    Tracks timestamps in a sliding window per key.
    Key can be an IP string or a (ip, attack_type) tuple.
    """

    def __init__(self, window_seconds: float):
        self.window = window_seconds
        self._timestamps: dict[str, deque] = defaultdict(deque)

    def record_and_count(self, key: str, now: float) -> int:
        ts = self._timestamps[key]
        ts.append(now)
        cutoff = now - self.window
        while ts and ts[0] < cutoff:
            ts.popleft()
        return len(ts)

    def reset(self, key: str):
        self._timestamps[key].clear()


# ==============================================================================
# Port Scan Tracker
# Different from the sliding window counter.
# Tracks unique DESTINATION PORTS per IP, not packet count.
# A port scan hits many ports — normal traffic hits one or two.
# ==============================================================================

class PortScanTracker:
    """
    Tracks unique destination ports per source IP
    within a sliding time window.

    Data structure:
      ip → deque of (timestamp, dst_port) tuples

    On each packet:
      1. Append (now, dst_port)
      2. Evict old entries outside the window
      3. Count unique ports still in the window
    """

    def __init__(self, window_seconds: float):
        self.window = window_seconds
        # ip → deque of (timestamp, port)
        self._data: dict[str, deque] = defaultdict(deque)

    def record_and_count_unique(self, ip: str, dst_port: int, now: float) -> int:
        """
        Records a packet to dst_port from ip at time now.
        Returns count of unique ports seen in the window.
        """
        if dst_port is None:
            return 0

        d = self._data[ip]
        d.append((now, dst_port))

        # Evict old entries
        cutoff = now - self.window
        while d and d[0][0] < cutoff:
            d.popleft()

        # Count unique ports in the current window
        unique_ports = {entry[1] for entry in d}
        return len(unique_ports)

    def get_scanned_ports(self, ip: str) -> list:
        """Returns the list of unique ports seen for this IP."""
        unique = {entry[1] for entry in self._data.get(ip, [])}
        return sorted(unique)

    def reset(self, ip: str):
        self._data[ip].clear()


# ==============================================================================
# Individual Detection Functions
# Each returns a ThreatEvent or None.
# They share counters passed in from run_detector.
# ==============================================================================

def _check_icmp_flood(
    pkt: PacketMetadata,
    counter: SlidingWindowCounter,
    now: float
) -> Optional[ThreatEvent]:
    """
    Simple: count ICMP packets per source IP per second.
    """
    if pkt.protocol != "ICMP":
        return None

    count = counter.record_and_count(pkt.source_ip, now)

    if count > THRESHOLDS[AttackType.ICMP_FLOOD]:
        counter.reset(pkt.source_ip)
        return ThreatEvent(
            attacker_ip    = pkt.source_ip,
            attack_type    = AttackType.ICMP_FLOOD,
            packet_count   = count,
            detection_time = now,
            extra_info     = {"protocol": "ICMP"},
            mitigation_status = "PENDING"
        )
    return None


def _check_syn_flood(
    pkt: PacketMetadata,
    counter: SlidingWindowCounter,
    now: float
) -> Optional[ThreatEvent]:
    """
    Counts TCP packets where flags == 0x02 (SYN only, no ACK).

    TCP Flags byte breakdown:
      Bit 0 (0x01): FIN
      Bit 1 (0x02): SYN   ← we want this
      Bit 2 (0x04): RST
      Bit 3 (0x08): PSH
      Bit 4 (0x10): ACK   ← we do NOT want this (SYN-ACK is normal)
      Bit 5 (0x20): URG

    flags == 0x02 means ONLY the SYN bit is set.
    flags == 0x12 would be SYN+ACK — that is a server response, not attack.
    """
    if pkt.protocol != "TCP":
        return None
    if pkt.tcp_flags is None:
        return None
    if pkt.tcp_flags != 0x02:   # Must be pure SYN — no other flags
        return None

    count = counter.record_and_count(pkt.source_ip, now)

    if count > THRESHOLDS[AttackType.SYN_FLOOD]:
        counter.reset(pkt.source_ip)
        return ThreatEvent(
            attacker_ip    = pkt.source_ip,
            attack_type    = AttackType.SYN_FLOOD,
            packet_count   = count,
            detection_time = now,
            extra_info     = {
                "dst_port": pkt.dst_port,
                "flags":    hex(pkt.tcp_flags)
            },
            mitigation_status = "PENDING"
        )
    return None


def _check_udp_flood(
    pkt: PacketMetadata,
    counter: SlidingWindowCounter,
    now: float
) -> Optional[ThreatEvent]:
    """
    Counts UDP packets per source IP per second.

    UDP floods are effective because:
    1. UDP is connectionless — no handshake overhead for attacker
    2. Your machine must check each port and reply with ICMP unreachable
    3. This wastes CPU on both sides

    We track the destination port in extra_info.
    Multiple different destination ports = likely a UDP flood.
    Single destination port = possibly legitimate service traffic.
    """
    if pkt.protocol != "UDP":
        return None

    count = counter.record_and_count(pkt.source_ip, now)

    if count > THRESHOLDS[AttackType.UDP_FLOOD]:
        counter.reset(pkt.source_ip)
        return ThreatEvent(
            attacker_ip    = pkt.source_ip,
            attack_type    = AttackType.UDP_FLOOD,
            packet_count   = count,
            detection_time = now,
            extra_info     = {"dst_port": pkt.dst_port},
            mitigation_status = "PENDING"
        )
    return None


def _check_port_scan(
    pkt: PacketMetadata,
    tracker: PortScanTracker,
    now: float
) -> Optional[ThreatEvent]:
    """
    Detects port scanning by counting unique destination ports
    from a single source IP within a 5-second window.

    Port scanners probe many ports in sequence:
    e.g., trying port 22, 23, 25, 80, 443, 8080, 3306 ...
    Normal clients connect to ONE or TWO ports, not dozens.

    We check TCP and UDP — scanners often probe both.

    Why 5 second window instead of 1 second?
    Slow scanners (like nmap default) take several seconds
    to work through ports. 1 second would miss them.
    """
    if pkt.protocol not in ("TCP", "UDP"):
        return None
    if pkt.dst_port is None:
        return None

    unique_count = tracker.record_and_count_unique(
        pkt.source_ip, pkt.dst_port, now
    )

    if unique_count > THRESHOLDS[AttackType.PORT_SCAN]:
        scanned_ports = tracker.get_scanned_ports(pkt.source_ip)
        tracker.reset(pkt.source_ip)

        return ThreatEvent(
            attacker_ip    = pkt.source_ip,
            attack_type    = AttackType.PORT_SCAN,
            packet_count   = unique_count,
            detection_time = now,
            extra_info     = {
                "unique_ports_scanned": unique_count,
                "sample_ports": scanned_ports[:10]  # First 10 for display
            },
            mitigation_status = "PENDING"
        )
    return None


def _check_fragmentation(
    pkt: PacketMetadata,
    counter: SlidingWindowCounter,
    now: float
) -> Optional[ThreatEvent]:
    """
    Detects IP fragmentation attacks.

    Why fragmentation is used as an attack:
    1. Evasion: Some firewalls only inspect the first fragment.
       Putting attack payload in later fragments can bypass them.
    2. Resource exhaustion: The target must reassemble fragments.
       Sending many incomplete fragment sets wastes memory.
    3. Teardrop attack: Sending overlapping fragments crashes
       old OS TCP/IP stacks (patched in modern systems).

    Normal traffic rarely has many fragments because:
    - Modern systems use Path MTU Discovery to avoid fragmentation
    - Most packets fit within the 1500 byte Ethernet MTU
    - Applications typically send data that fits in one packet

    Seeing 30+ fragmented packets per second is very suspicious.
    """
    if not pkt.fragmented:
        return None

    count = counter.record_and_count(pkt.source_ip, now)

    if count > THRESHOLDS[AttackType.FRAGMENTATION]:
        counter.reset(pkt.source_ip)
        return ThreatEvent(
            attacker_ip    = pkt.source_ip,
            attack_type    = AttackType.FRAGMENTATION,
            packet_count   = count,
            detection_time = now,
            extra_info     = {"protocol": pkt.protocol},
            mitigation_status = "PENDING"
        )
    return None


# ==============================================================================
# Main Detector Loop
# ==============================================================================

def run_detector():
    """
    Single loop that runs ALL five detectors on every packet.
    Each detector has its own counter so they do not interfere.

    Cooldown is tracked per (ip, attack_type) pair so:
    - SYN flood from IP X does not suppress ICMP flood from IP X
    - Same attack type from same IP is suppressed during cooldown
    """
    logger.info("Detector started with %d attack detectors.", len(THRESHOLDS))
    shared_state.ui_log_queue.put(
        f"[bold yellow]DETECTOR[/] Started — "
        f"watching for: {', '.join(a.value for a in THRESHOLDS.keys())}"
    )

    # One counter per attack type — they are independent
    icmp_counter  = SlidingWindowCounter(window_seconds=WINDOW_SECONDS)
    syn_counter   = SlidingWindowCounter(window_seconds=WINDOW_SECONDS)
    udp_counter   = SlidingWindowCounter(window_seconds=WINDOW_SECONDS)
    frag_counter  = SlidingWindowCounter(window_seconds=WINDOW_SECONDS)
    port_tracker  = PortScanTracker(window_seconds=PORT_SCAN_WINDOW)

    # Cooldown: (ip, AttackType) → last alert timestamp
    last_alert: dict[tuple, float] = {}

    while not shared_state.shutdown_event.is_set():
        try:
            pkt: PacketMetadata = shared_state.packet_queue.get(timeout=0.5)
        except shared_state.queue.Empty:
            continue

        now = time.time()

        # Run all detectors on this packet
        # Each returns a ThreatEvent or None
        detections = [
            _check_icmp_flood   (pkt, icmp_counter, now),
            _check_syn_flood    (pkt, syn_counter,  now),
            _check_udp_flood    (pkt, udp_counter,  now),
            _check_port_scan    (pkt, port_tracker, now),
            _check_fragmentation(pkt, frag_counter, now),
        ]

        for threat in detections:
            if threat is None:
                continue

            # Check cooldown for this (ip, attack_type) pair
            cooldown_key  = (threat.attacker_ip, threat.attack_type)
            last_alert_ts = last_alert.get(cooldown_key, 0)

            if now - last_alert_ts < COOLDOWN_SECONDS:
                continue    # Still in cooldown — skip

            # New alert — record and emit
            last_alert[cooldown_key] = now

            logger.warning(
                "THREAT: %s from %s (%d packets/events)",
                threat.attack_type.value,
                threat.attacker_ip,
                threat.packet_count
            )

            try:
                shared_state.threat_queue.put_nowait(threat)
            except shared_state.queue.Full:
                logger.error("threat_queue full — dropping alert")

            with shared_state.threat_history_lock:
                shared_state.threat_history.append(threat)

            shared_state.ui_log_queue.put(
                f"[bold red]THREAT[/] "
                f"{threat.attack_type.value} from {threat.attacker_ip} — "
                f"{threat.packet_count} events | "
                f"Extra: {threat.extra_info}"
            )

    logger.info("Detector stopped.")