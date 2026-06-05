"""
mitigator.py

Executes the mitigation command produced by the LLM.
Schedules automatic route deletion after 60 seconds.

CRITICAL SECURITY CONSIDERATIONS:

We do NOT pass the LLM's command directly to shell=True.
That would be a command injection vulnerability.
Instead, we parse the command, extract the IP, and
construct the OS call ourselves.

The LLM is not trusted to build the final command.
It's trusted to confirm maliciousness. We build the command.

All actions are logged. The 60-second auto-revert ensures
we don't permanently break routing from a false positive.
"""

import os
import re
import time
import subprocess
import threading
import logging
import ipaddress

import shared_state
from shared_state import ThreatEvent

logger = logging.getLogger("mitigator")

BLOCK_DURATION_SECONDS = 60
BLACKHOLE_GATEWAY = "192.0.2.1"  # RFC 5737 TEST-NET — routes here go nowhere.
# This IP should not be a real gateway on your network.

# Testing mode: allows blocking loopback for local development
TESTING_MODE = os.environ.get("ALLOW_LOOPBACK_BLOCK", "false").lower() == "true"


def _validate_ip(ip_str: str) -> str:
    """
    Validates that ip_str is a legitimate IP address.
    Raises ValueError if not. This prevents command injection
    even if the LLM or detector somehow produces a malicious IP string.
    """
    try:
        addr = ipaddress.ip_address(ip_str)

        # Safety: don't block loopback in production (unless testing mode is enabled)
        if addr.is_loopback and not TESTING_MODE:
            raise ValueError(
                f"Refusing to block loopback address: {ip_str}. "
                f"This would crash the dashboard connection! "
                f"Set environment variable ALLOW_LOOPBACK_BLOCK=true for testing."
            )
        
        if addr.is_loopback and TESTING_MODE:
            logger.warning("TESTING MODE: Allowing loopback block for %s", ip_str)
        
        if addr.is_multicast:
            raise ValueError(f"Refusing to block multicast address: {ip_str}")

        return str(addr)

    except ValueError as e:
        raise ValueError(f"Invalid IP address {ip_str!r}: {e}")


def _run_route_command(args: list[str]) -> tuple[bool, str]:
    """
    Executes a route command with a hardcoded argument list.
    shell=False prevents injection. args list is fully controlled by us.

    Returns (success: bool, output: str).
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=10,    # Don't hang if the OS is slow.
            shell=False    # CRITICAL: No shell expansion. Injection-safe.
        )

        output = (result.stdout + result.stderr).strip()
        success = result.returncode == 0

        if not success:
            logger.error("Route command failed (rc=%d): %s", result.returncode, output)
        else:
            logger.info("Route command succeeded: %s", output)

        return success, output

    except subprocess.TimeoutExpired:
        logger.error("Route command timed out: %s", args)
        return False, "timeout"

    except FileNotFoundError:
        logger.error("Route binary not found. Is 'route' in PATH?")
        return False, "route binary not found"

    except Exception as e:
        logger.error("Unexpected error running route command: %s", e)
        return False, str(e)


def _build_block_args(ip: str) -> list[str]:
    """
    Builds the argument list for blocking an IP on Windows.
    Modify this for Linux: ["ip", "route", "add", "blackhole", f"{ip}/32"]
    """
    import platform
    if platform.system() == "Windows":
        return ["route", "add", ip, "mask", "255.255.255.255", BLACKHOLE_GATEWAY]
    else:
        # Linux: uses ip command, more modern and reliable than route.
        return ["ip", "route", "add", "blackhole", f"{ip}/32"]


def _build_unblock_args(ip: str) -> list[str]:
    """
    Builds the argument list for removing an IP block.
    """
    import platform
    if platform.system() == "Windows":
        return ["route", "delete", ip, "mask", "255.255.255.255", BLACKHOLE_GATEWAY]
    else:
        return ["ip", "route", "del", "blackhole", f"{ip}/32"]


def _schedule_auto_revert(ip: str, delay: float):
    """
    Runs route delete in a background daemon thread after delay seconds.
    Daemon=True means this thread won't prevent program exit.
    """
    def _revert():
        logger.info("Auto-revert timer started for %s (%.0fs)", ip, delay)
        time.sleep(delay)

        if shared_state.shutdown_event.is_set():
            logger.info("Shutdown detected — skipping auto-revert for %s", ip)
            return

        logger.info("Auto-reverting block on %s...", ip)
        args = _build_unblock_args(ip)
        success, output = _run_route_command(args)

        if success:
            with shared_state.active_blocks_lock:
                shared_state.active_blocks.pop(ip, None)

            shared_state.ui_log_queue.put(
                f"[bold green]MITIGATOR[/] Block on {ip} auto-reverted after {delay:.0f}s"
            )
        else:
            shared_state.ui_log_queue.put(
                f"[bold red]MITIGATOR ERROR[/] Auto-revert FAILED for {ip}: {output}"
            )

    timer_thread = threading.Thread(target=_revert, daemon=True, name=f"revert-{ip}")
    timer_thread.start()


def apply_mitigation(threat: ThreatEvent):
    """
    Main entry point called by llm_analyzer.py.

    Validates the IP, checks for duplicate blocks,
    applies the route, and schedules auto-revert.
    """
    ip = threat.attacker_ip

    # Step 1: Validate IP (security check).
    try:
        ip = _validate_ip(ip)
    except ValueError as e:
        logger.error("IP validation failed, aborting mitigation: %s", e)
        threat.mitigation_status = "FAILED"
        shared_state.ui_log_queue.put(f"[bold red]MITIGATOR[/] Validation failed: {e}")
        return

    # Step 2: Check if already blocked.
    with shared_state.active_blocks_lock:
        if ip in shared_state.active_blocks:
            logger.info("IP %s already blocked, skipping.", ip)
            shared_state.ui_log_queue.put(f"[yellow]MITIGATOR[/] {ip} already blocked.")
            return
        # Mark as blocked immediately to prevent race conditions
        # from multiple threats for the same IP hitting simultaneously.
        shared_state.active_blocks[ip] = time.time()

    # Step 3: Apply the route block.
    args = _build_block_args(ip)
    logger.warning("Applying block: %s", " ".join(args))
    shared_state.ui_log_queue.put(f"[bold red]MITIGATOR[/] Blocking {ip}...")

    success, output = _run_route_command(args)

    if success:
        threat.mitigation_status = "APPLIED"
        shared_state.ui_log_queue.put(
            f"[bold green]MITIGATOR[/] Block APPLIED on {ip}. "
            f"Auto-revert in {BLOCK_DURATION_SECONDS}s."
        )
        # Step 4: Schedule auto-revert.
        _schedule_auto_revert(ip, BLOCK_DURATION_SECONDS)
    else:
        threat.mitigation_status = "FAILED"
        with shared_state.active_blocks_lock:
            shared_state.active_blocks.pop(ip, None)  # Undo the pre-mark.

        message = f"[bold red]MITIGATOR FAIL[/] Block failed on {ip}: {output}"
        if "requires elevation" in output.lower() or "access is denied" in output.lower():
            message += " -- restart the app with administrator privileges to apply Windows route changes."

        shared_state.ui_log_queue.put(message)


def flush_all_blocks():
    """
    Called when the user presses 'R' to manually flush all active blocks.
    Iterates a snapshot of active_blocks to avoid lock contention.
    """
    with shared_state.active_blocks_lock:
        ips_to_flush = list(shared_state.active_blocks.keys())

    if not ips_to_flush:
        shared_state.ui_log_queue.put("[yellow]MITIGATOR[/] No active blocks to flush.")
        return

    for ip in ips_to_flush:
        args = _build_unblock_args(ip)
        logger.info("Manual flush: removing block on %s", ip)
        success, output = _run_route_command(args)

        if success:
            with shared_state.active_blocks_lock:
                shared_state.active_blocks.pop(ip, None)
            shared_state.ui_log_queue.put(
                f"[bold green]MITIGATOR[/] Manual flush: unblocked {ip}"
            )
        else:
            shared_state.ui_log_queue.put(
                f"[bold red]MITIGATOR[/] Manual flush FAILED for {ip}: {output}"
            )