"""
shared_state.py

All shared objects live here to avoid circular imports.
Every layer imports from this single source of truth.
"""

import queue
import threading
import collections
from enum import Enum
from dataclasses import dataclass, field
from typing import Optional


class AttackType(Enum):
    """
    Every detected attack gets one of these labels.
    Using an Enum prevents typos and makes comparisons safe.
    """
    ICMP_FLOOD       = "ICMP Flood"
    SYN_FLOOD        = "SYN Flood"
    UDP_FLOOD        = "UDP Flood"
    PORT_SCAN        = "Port Scan"
    FRAGMENTATION    = "Fragmentation Attack"
    UNKNOWN          = "Unknown"


@dataclass
class PacketMetadata:
    """
    Lightweight packet record passed through the pipeline.
    Added dst_port, src_port, flags, fragmented fields
    so the detector can identify more attack types.
    """
    source_ip:   str
    dest_ip:     str
    protocol:    str            # "ICMP", "TCP", "UDP", "OTHER"
    timestamp:   float

    # New fields — None if not applicable for this protocol
    src_port:    Optional[int]  = None
    dst_port:    Optional[int]  = None
    tcp_flags:   Optional[int]  = None    # Raw TCP flags byte
    fragmented:  bool           = False   # True if IP fragment flag set
    packet_size: int            = 0       # bytes


@dataclass
class ThreatEvent:
    """
    Produced by the detector when a threshold is crossed.
    Added attack_type so LLM and UI know what kind of attack.
    """
    attacker_ip:        str
    attack_type:        AttackType
    packet_count:       int
    detection_time:     float
    extra_info:         dict        = field(default_factory=dict)
    llm_reasoning:      Optional[str] = None
    mitigation_command: Optional[str] = None
    mitigation_status:  Optional[str] = None   # PENDING, APPLIED, FAILED, REVERTED


# --- Shared Queues ---
packet_queue:  queue.Queue = queue.Queue(maxsize=5000)
threat_queue:  queue.Queue = queue.Queue(maxsize=100)
ui_log_queue:  queue.Queue = queue.Queue(maxsize=500)

# --- Shared State ---
active_blocks:      dict = {}
active_blocks_lock       = threading.Lock()

recent_packets: collections.deque = collections.deque(maxlen=500)
recent_packets_lock       = threading.Lock()
RECENT_PACKETS_CAP        = 500

# Monotonic counter — incremented every time a packet is appended.
# The emitter reads this to know how many new packets arrived.
recent_packets_counter: int = 0

threat_history:      list = []
threat_history_lock       = threading.Lock()

shutdown_event = threading.Event()