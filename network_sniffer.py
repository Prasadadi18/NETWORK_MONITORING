"""
network_sniffer.py

Updated to capture the extra fields (ports, flags,
fragmentation) that the new detectors need.
"""

import time
import logging
from scapy.all import sniff, IP, ICMP, TCP, UDP

import shared_state
from shared_state import PacketMetadata

logger = logging.getLogger("sniffer")


def _classify_protocol(packet) -> str:
    if packet.haslayer(ICMP):
        return "ICMP"
    elif packet.haslayer(TCP):
        return "TCP"
    elif packet.haslayer(UDP):
        return "UDP"
    else:
        return "OTHER"


def _is_fragmented(packet) -> bool:
    """
    IP fragmentation check.

    The IP header has a flags field and a fragment offset field.
    MF (More Fragments) flag = 0x1  → more fragments coming
    Fragment offset > 0             → this IS a fragment (not the first)

    Either condition means this packet is part of a fragmented stream.
    """
    if not packet.haslayer(IP):
        return False

    ip = packet[IP]
    more_fragments = bool(ip.flags & 0x1)   # MF flag
    has_offset     = ip.frag > 0            # Non-zero offset = fragment

    return more_fragments or has_offset


def _packet_callback(packet):
    if not packet.haslayer(IP):
        return

    ip_layer = packet[IP]

    # --- Extract TCP/UDP port and flag info ---
    src_port  = None
    dst_port  = None
    tcp_flags = None

    if packet.haslayer(TCP):
        src_port  = packet[TCP].sport
        dst_port  = packet[TCP].dport
        tcp_flags = int(packet[TCP].flags)

    elif packet.haslayer(UDP):
        src_port = packet[UDP].sport
        dst_port = packet[UDP].dport

    metadata = PacketMetadata(
        source_ip   = ip_layer.src,
        dest_ip     = ip_layer.dst,
        protocol    = _classify_protocol(packet),
        timestamp   = time.time(),
        src_port    = src_port,
        dst_port    = dst_port,
        tcp_flags   = tcp_flags,
        fragmented  = _is_fragmented(packet),
        packet_size = len(packet)
    )

    try:
        shared_state.packet_queue.put_nowait(metadata)
    except shared_state.queue.Full:
        logger.warning("packet_queue full — dropping packet from %s", metadata.source_ip)

    with shared_state.recent_packets_lock:
        shared_state.recent_packets.append(metadata)
        shared_state.recent_packets_counter += 1


def run_sniffer(interface: str = None):
    logger.info("Sniffer starting on interface: %s", interface or "default")
    shared_state.ui_log_queue.put(
        f"[bold cyan]SNIFFER[/] Started on interface: {interface or 'default'}"
    )

    sniff(
        iface     = interface,
        filter    = "ip",
        prn       = _packet_callback,
        store     = False,
        stop_filter = lambda _: shared_state.shutdown_event.is_set()
    )
    logger.info("Sniffer stopped.")