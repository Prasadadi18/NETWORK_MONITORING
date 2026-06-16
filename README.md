# Network Guardian

A local network monitoring and attack mitigation dashboard built with Python.
It captures live traffic, detects five attack types, uses a local LLM (via Ollama) to reason about threats, and automatically applies temporary IP route blocks — all visible in a real-time browser dashboard.

## What this project does

- `network_sniffer.py` — captures traffic and extracts packet metadata using Scapy.
- `attack_detector.py` — detects ICMP flood, SYN flood, UDP flood, port scan, and fragmentation attacks using sliding-window counters.
- `llm_analyzer.py` — sends threat evidence to Ollama, receives a JSON verdict, and extracts the mitigation command.
- `mitigator.py` — applies a temporary IP route block (`route add` on Windows, `ip route blackhole` on Linux) and auto-reverts it after 60 seconds.
- `main.py` — Flask + Socket.IO dashboard; orchestrates all threads.
- `attack_injector.py` — injects test attacks over loopback for local testing.

## Requirements

### System dependencies

| Dependency | Why | Windows | Linux |
|------------|-----|---------|-------|
| Python 3.11+ | Runtime | [python.org](https://www.python.org/downloads/) | `sudo apt install python3` |
| Npcap | Scapy needs it to capture packets | [npcap.com](https://npcap.com/#download) — install with "WinPcap API-compatible mode" checked | `sudo apt install libpcap-dev` |
| Ollama | Local LLM backend | [ollama.com/download](https://ollama.com/download) | `curl -fsSL https://ollama.com/install.sh \| sh` |

> **Admin / root privileges are required.** Packet capture and IP route manipulation both need elevated permissions.

### Python dependencies (`requirements.txt`)

- Flask
- Flask-SocketIO
- scapy
- requests
- rich

## Setup

### 1. Install Npcap (Windows only)

Download from [npcap.com](https://npcap.com/#download) and install it.
**Check "WinPcap API-compatible mode"** during installation — Scapy requires it.

### 2. Install Ollama and pull the model

```powershell
ollama pull tinyllama
```

> Default model is `tinyllama`. You can use any model Ollama supports (e.g. `llama3`, `mistral`) by setting the `OLLAMA_MODEL` environment variable.

### 3. Navigate to the project folder

```powershell
cd path\to\cnfinal
```

### 4. Create a Python virtual environment

```powershell
python -m venv .venv
```

### 5. Activate the environment

```powershell
.venv\Scripts\activate
```

### 6. Install dependencies

```powershell
pip install -r requirements.txt
```

## Run the dashboard

#### Step 1 — Start Ollama (in a separate terminal)

```powershell
ollama serve
```

Ollama must be running at `http://localhost:11434` before the app starts. Verify it is up:

```powershell
curl http://localhost:11434/api/tags
```

If Ollama is unreachable, the system falls back to built-in rule-based analysis automatically — no crash.

#### Step 2 — (Optional) Find your network interface

If you want to sniff a specific interface instead of letting Scapy auto-detect:

```powershell
python find_interface.py
```

This prints all available interfaces with their IP addresses. Note the name of the one you want to use.

#### Step 3 — Start the application (run as Administrator)

```powershell
python main.py
```

> On Windows, right-click your terminal and choose **Run as administrator** before activating the venv — `route add` requires elevation.

Optional flags:

```
--interface   Network interface to sniff (e.g. "NPF_Loopback"). Default: auto-detect.
--threshold   Packets/sec to trigger an alert. Default: 100.
--port        Web dashboard port. Default: 5000.
```

Example with flags:

```powershell
python main.py --interface "NPF_Loopback" --threshold 50 --port 8080
```

#### Step 4 — Open the dashboard

```
http://localhost:5000
```

## How to check the project

- The dashboard shows active blocks, threat count, and live packet feed.
- Click the attack buttons (ICMP Flood, SYN Flood, UDP Flood, Port Scan, Fragmentation, or All) to trigger detections.
- Use **Flush All Blocks** to manually clear all route blocks.
- Use **Shutdown** to stop the system cleanly.
- Activity is logged to `guardian.log`.

## Command-line attack injection

You can also inject attacks manually without the browser:

```powershell
python attack_injector.py --attack icmp_flood --rate 150 --duration 10
python attack_injector.py --attack syn_flood  --rate 80  --duration 10
python attack_injector.py --attack udp_flood  --rate 150 --duration 10
python attack_injector.py --attack port_scan  --ports 100
python attack_injector.py --attack fragmentation
python attack_injector.py --attack all --duration 5
```

All attacks use `203.0.113.50` (RFC 5737 TEST-NET) as the fake source IP so the detector can block it without refusing to block a loopback address.

## Notes

- **Security**: `mitigator.py` never passes the LLM's text directly to a shell. It validates the IP and constructs the OS command itself — no command injection risk.
- **Auto-revert**: Blocks are automatically removed after 60 seconds to avoid permanently breaking routing from a false positive.
- **Windows route blocks**: Uses `route add <ip> mask 255.255.255.255 192.0.2.1` (RFC 5737 blackhole gateway).
- **Linux route blocks**: Uses `ip route add blackhole <ip>/32`.
- **Log files**: Remove or `.gitignore` `guardian.log` to avoid large log files in the repo.
- **Environment variables**:
  - `OLLAMA_BASE_URL` — Ollama endpoint, default `http://localhost:11434`
  - `OLLAMA_MODEL` — model name, default `tinyllama`
  - `ALLOW_LOOPBACK_BLOCK=true` — enables blocking loopback IPs (only needed if you override `FAKE_ATTACKER_IP` in `attack_injector.py`)

## Useful checks

- Verify `main.py` starts without errors.
- Confirm the dashboard loads at `http://localhost:5000`.
- Trigger an attack and watch the threat panel update with the Ollama verdict.
- Inspect `guardian.log` for detector, LLM analyzer, and mitigator events.
