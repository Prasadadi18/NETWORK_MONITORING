"""
main.py

Orchestration layer. Manages:
  1. Thread lifecycle for all five layers.
  2. Flask web dashboard with real-time Socket.IO panels.
  3. Attack injection from the browser UI.

Run with: python main.py
Open:     http://localhost:5000

Dashboard controls replace keyboard shortcuts:
  - "Flush All Blocks" button replaces [R]
  - "Shutdown" button replaces [Q]
  - Attack buttons replace running attack_injector.py separately
"""

import time
import logging
import argparse
import threading
import os

from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO

import shared_state
import network_sniffer
import attack_detector
import llm_analyzer
import mitigator
import attack_injector

# --- Logging Setup ---
# Log to file only -- the terminal stays clean for Flask startup info.
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    handlers=[logging.FileHandler("guardian.log")],
    force=True
)
logger = logging.getLogger("main")

# Suppress noisy Flask/Werkzeug/SocketIO logs
logging.getLogger("werkzeug").setLevel(logging.WARNING)
logging.getLogger("engineio").setLevel(logging.WARNING)
logging.getLogger("socketio").setLevel(logging.WARNING)

# --- Flask App ---
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'network-guardian-secret')
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

connected_clients = 0
connected_clients_lock = threading.Lock()

# Module-level log buffer -- persists between render cycles.
_ui_log_buffer: list = []
_ui_log_buffer_lock = threading.Lock()

# Track whether attack injection is currently running
_attack_running = threading.Event()


# ==============================================================================
# Routes -- Web UI replaces the Rich terminal panels
# ==============================================================================

@app.route('/')
def index():
    """Serve the main dashboard page."""
    return render_template('index.html')


@app.route('/api/status')
def api_status():
    """Return current system state as JSON."""
    with shared_state.active_blocks_lock:
        blocks = dict(shared_state.active_blocks)

    with shared_state.threat_history_lock:
        threat_count = len(shared_state.threat_history)

    return jsonify({
        'active_blocks': len(blocks),
        'blocked_ips': list(blocks.keys()),
        'threat_count': threat_count,
        'packet_queue_size': shared_state.packet_queue.qsize(),
    })


@app.route('/api/attack', methods=['POST'])
def api_attack():
    """
    Launch a test attack from the web UI.
    Replaces: python attack_injector.py --attack <type>
    Runs in a background thread so it doesn't block the response.
    """
    if _attack_running.is_set():
        return jsonify({'status': 'error', 'message': 'An attack is already running'}), 429

    data = request.get_json() or {}
    attack_type = data.get('attack', 'icmp_flood')
    rate = min(int(data.get('rate', 150)), 1000)
    duration = min(int(data.get('duration', 10)), 120)

    valid_attacks = ['icmp_flood', 'syn_flood', 'udp_flood', 'port_scan', 'fragmentation', 'all']
    if attack_type not in valid_attacks:
        return jsonify({'status': 'error', 'message': f'Invalid attack type: {attack_type}'}), 400

    def _run_attack():
        _attack_running.set()
        try:
            shared_state.ui_log_queue.put(
                f"[bold yellow]INJECTOR[/] Starting {attack_type} "
                f"(rate={rate}, duration={duration}s)"
            )

            if attack_type == 'icmp_flood':
                attack_injector.inject_icmp_flood(rate=rate, duration=duration)
            elif attack_type == 'syn_flood':
                attack_injector.inject_syn_flood(rate=rate, duration=duration)
            elif attack_type == 'udp_flood':
                attack_injector.inject_udp_flood(rate=rate, duration=duration)
            elif attack_type == 'port_scan':
                attack_injector.inject_port_scan(num_ports=min(rate, 500))
            elif attack_type == 'fragmentation':
                attack_injector.inject_fragmentation_attack(rate=rate, duration=duration)
            elif attack_type == 'all':
                attack_injector.inject_all(duration_each=duration)

            shared_state.ui_log_queue.put(
                f"[bold green]INJECTOR[/] {attack_type} completed."
            )
        except Exception as e:
            logger.error("Attack injection error: %s", e)
            shared_state.ui_log_queue.put(
                f"[bold red]INJECTOR ERROR[/] {attack_type} failed: {e}"
            )
        finally:
            _attack_running.clear()

    thread = threading.Thread(target=_run_attack, daemon=True, name="attack-injector")
    thread.start()

    return jsonify({
        'status': 'started',
        'attack': attack_type,
        'rate': rate,
        'duration': duration
    })


@app.route('/api/flush', methods=['POST'])
def api_flush():
    """Flush all active blocks. Replaces the [R] key."""
    logger.info("Manual flush triggered from web UI.")
    shared_state.ui_log_queue.put(
        "[bold yellow]USER ACTION[/] Manual flush of all blocks triggered."
    )
    mitigator.flush_all_blocks()
    return jsonify({'status': 'ok', 'message': 'All blocks flushed'})


@app.route('/api/shutdown', methods=['POST'])
def api_shutdown():
    """Clean shutdown. Replaces the [Q] key."""
    logger.info("Shutdown requested from web UI.")
    shared_state.ui_log_queue.put("[bold white]SYSTEM[/] Shutdown requested...")
    shared_state.shutdown_event.set()

    def _delayed_exit():
        time.sleep(2)
        mitigator.flush_all_blocks()
        logger.info("Network Guardian stopped cleanly.")
        import os
        os._exit(0)

    threading.Thread(target=_delayed_exit, daemon=True).start()
    return jsonify({'status': 'ok', 'message': 'Shutting down...'})


@socketio.on('connect')
def handle_connect():
    global connected_clients
    with connected_clients_lock:
        connected_clients += 1
        logger.info("Client connected, active clients=%d", connected_clients)


@socketio.on('disconnect')
def handle_disconnect():
    global connected_clients
    with connected_clients_lock:
        connected_clients = max(0, connected_clients - 1)
        logger.info("Client disconnected, active clients=%d", connected_clients)

        if connected_clients == 0:
            with shared_state.threat_history_lock:
                shared_state.threat_history.clear()
            with shared_state.recent_packets_lock:
                shared_state.recent_packets.clear()
                shared_state.recent_packets_counter = 0
            while not shared_state.ui_log_queue.empty():
                try:
                    shared_state.ui_log_queue.get_nowait()
                except Exception:
                    break
            logger.info("All clients disconnected: cleared threat history, recent packets, and pending logs.")


# ==============================================================================
# Real-time WebSocket Emitter
# Replaces the Rich Live refresh loop that polled shared_state every 0.5s.
# Same idea: read from shared_state, push to the UI.
# ==============================================================================

def _background_emitter():
    """
    Background thread that pushes real-time data to all connected
    browser clients every 500ms via Socket.IO.

    This replaces _update_layout() from the Rich UI --
    same data, same 0.5s cycle, different output target.
    """
    last_counter = 0

    while not shared_state.shutdown_event.is_set():
        time.sleep(0.5)

        try:
            # --- Packet Feed (replaces _render_packet_feed) ---
            with shared_state.recent_packets_lock:
                current_counter = shared_state.recent_packets_counter
                if current_counter > last_counter:
                    # How many new packets arrived since last tick
                    new_count = current_counter - last_counter
                    # Grab the latest ones from the deque
                    # (deque keeps at most maxlen items, so cap our slice)
                    all_packets = list(shared_state.recent_packets)
                    new_packets = all_packets[-min(new_count, len(all_packets)):]
                    last_counter = current_counter
                else:
                    new_packets = []

            if new_packets:
                packet_data = [
                    {
                        'source_ip': p.source_ip,
                        'dest_ip': p.dest_ip,
                        'protocol': p.protocol,
                        'dst_port': p.dst_port,
                        'timestamp': p.timestamp,
                    }
                    for p in new_packets[-50:]
                ]
                socketio.emit('packet_feed', {'packets': packet_data})

            # --- Threat History (replaces _render_threat_panel) ---
            with shared_state.threat_history_lock:
                threats = list(shared_state.threat_history[-10:])

            if threats:
                threat_data = [
                    {
                        'attacker_ip': t.attacker_ip,
                        'attack_type': t.attack_type.value,
                        'packet_count': t.packet_count,
                        'detection_time': t.detection_time,
                        'llm_reasoning': t.llm_reasoning,
                        'mitigation_status': t.mitigation_status or 'PENDING',
                    }
                    for t in threats
                ]
                socketio.emit('threat_feed', {'threats': threat_data})

            # --- System Logs (replaces _render_log_panel) ---
            new_logs = []
            while not shared_state.ui_log_queue.empty():
                try:
                    msg = shared_state.ui_log_queue.get_nowait()
                    new_logs.append(msg)
                    with _ui_log_buffer_lock:
                        _ui_log_buffer.append(msg)
                        if len(_ui_log_buffer) > 200:
                            _ui_log_buffer[:] = _ui_log_buffer[-100:]
                except Exception:
                    break

            if new_logs:
                socketio.emit('log_feed', {'logs': new_logs})

            # --- Status (replaces _render_header) ---
            with shared_state.active_blocks_lock:
                blocks = dict(shared_state.active_blocks)

            socketio.emit('status_update', {
                'active_blocks': len(blocks),
                'blocked_ips': list(blocks.keys()),
            })

        except Exception as e:
            logger.error("Emitter error: %s", e)



# ==============================================================================
# Thread Management (unchanged from original main.py)
# ==============================================================================

def _auto_detect_interface(requested: str = None) -> str:
    """
    On Windows, Scapy's default interface is usually the primary
    Ethernet/Wi-Fi adapter, which CANNOT see loopback traffic.
    Since our attack simulator sends to 127.0.0.1, we need the
    Npcap Loopback Adapter to capture those packets.

    Priority:
      1. User-specified interface (--interface)
      2. NPF_Loopback (Windows Npcap loopback adapter)
      3. Scapy default (conf.iface)
    """
    if requested:
        return requested

    try:
        from scapy.all import get_if_list, conf
        interfaces = get_if_list()

        # Look for the Npcap loopback adapter
        for iface in interfaces:
            if 'Loopback' in iface or 'loopback' in iface:
                logger.info("Auto-detected loopback interface: %s", iface)
                return iface

        # Fallback to default
        logger.info("No loopback adapter found, using default: %s", conf.iface)
        return None
    except Exception as e:
        logger.warning("Interface detection failed: %s", e)
        return None


def _start_thread(target, name: str, **kwargs) -> threading.Thread:
    """Helper: creates, names, and starts a daemon thread."""
    t = threading.Thread(target=target, name=name, daemon=True, kwargs=kwargs)
    t.start()
    logger.info("Thread started: %s", name)
    return t


# ==============================================================================
# Entry Point
# ==============================================================================

def main():
    parser = argparse.ArgumentParser(description="Network Guardian")
    parser.add_argument(
        "--interface", "-i",
        default=None,
        help="Network interface to sniff (e.g., eth0, lo). Default: Scapy auto-select."
    )
    parser.add_argument(
        "--threshold",
        type=int,
        default=100,
        help="Packets per second threshold for threat detection."
    )
    parser.add_argument(
        "--port",
        type=int,
        default=5000,
        help="Web dashboard port (default: 5000)."
    )
    args = parser.parse_args()

    # Apply threshold override if specified.
    if args.threshold != 100:
        for key in attack_detector.THRESHOLDS:
            attack_detector.THRESHOLDS[key] = args.threshold

    print("")
    print("  NETWORK GUARDIAN - Web Dashboard")
    print("  AI-Powered Autonomous Defense System")
    print("  ------------------------------------")
    print(f"  Dashboard:  http://localhost:{args.port}")
    print(f"  Interface:  {args.interface or 'auto-detect'}")
    print(f"  Threshold:  {args.threshold}")
    print("")

    # --- Start all background threads ---
    active_interface = _auto_detect_interface(args.interface)
    threads = [
        _start_thread(
            network_sniffer.run_sniffer,
            name="sniffer",
            interface=active_interface
        ),
        _start_thread(
            attack_detector.run_detector,
            name="detector"
        ),
        _start_thread(
            llm_analyzer.run_analyzer,
            name="llm-analyzer"
        ),
        _start_thread(
            _background_emitter,
            name="ws-emitter"
        ),
    ]

    shared_state.ui_log_queue.put(
        "[bold green]SYSTEM[/] Network Guardian started. "
        f"Dashboard at http://localhost:{args.port}"
    )

    # --- Flask + Socket.IO (replaces Rich Live display loop) ---
    try:
        socketio.run(
            app,
            host="::",
            port=args.port,
            debug=False,
            use_reloader=False,
            log_output=False,
            allow_unsafe_werkzeug=True
        )
    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received.")
        shared_state.shutdown_event.set()

    # --- Cleanup ---
    print("\nShutting down...")

    # Wait briefly for threads to notice the shutdown event.
    for t in threads:
        t.join(timeout=3.0)

    # Flush remaining active blocks on clean exit.
    # This is a safety measure -- don't leave orphaned routes.
    print("Flushing remaining blocks...")
    mitigator.flush_all_blocks()

    print("Network Guardian stopped cleanly.")


if __name__ == "__main__":
    main()