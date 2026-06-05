# Network Guardian

This repository provides a local network monitoring and attack mitigation dashboard built with Python.
It includes packet sniffing, attack detection, LLM-enhanced analysis, and mitigation logic with a browser-based UI.

## What this project does

- Uses `network_sniffer.py` to capture traffic and extract packet metadata.
- Runs `attack_detector.py` to detect common network attack patterns like ICMP flood, SYN flood, UDP flood, port scans, and fragmentation attacks.
- Uses `llm_analyzer.py` to evaluate threats and determine mitigation actions.
- Applies temporary network route blocks in `mitigator.py` while keeping the system safe from command injection.
- Provides a real-time dashboard via `main.py` and `templates/index.html`.
- Supports attack injection through `attack_injector.py` for local testing.

## Requirements

- Python 3.11+ recommended
- Admin/root privileges may be required for packet capture and IP route manipulation.

Dependencies are listed in `requirements.txt`:

- Flask
- Flask-SocketIO
- scapy
- requests
- rich

## Setup

1. Open a terminal and navigate to the project folder:

```powershell
cd "C:\Users\adina\OneDrive\Desktop\cnfinal"
```

2. Create a Python virtual environment:

```powershell
python -m venv .venv
```

3. Activate the environment:

```powershell
.venv\Scripts\activate
```

4. Install dependencies:

```powershell
pip install -r requirements.txt
```

## Run the dashboard

1. Start the application:

```powershell
python main.py
```

2. Open your browser and go to:

```
http://localhost:5000
```

## How to check the project

- The web dashboard shows current active blocks, threat count, and packet queue size.
- Use the dashboard attack buttons to launch test attacks such as ICMP flood, SYN flood, UDP flood, port scan, fragmentation, or all.
- Use the dashboard controls to `Flush All Blocks` or `Shutdown` the system.
- The app logs activity to `guardian.log`.

## Command-line testing

You can also run attack injections manually:

```powershell
python attack_injector.py --attack icmp_flood --rate 150 --duration 10
```

## Notes

- The mitigation layer is designed for safety: it validates IP addresses and uses explicit command arguments instead of shell command strings.
- On Windows, the project uses `route add`/`route delete` to apply temporary blocks.
- On Linux, it uses `ip route add/delete blackhole`.
- If you want to avoid very large log files, remove or ignore `guardian.log` from your repository.

## Useful checks

- Verify that `main.py` starts without errors.
- Confirm the browser dashboard loads at `http://localhost:5000`.
- Trigger an attack and watch the dashboard update.
- Inspect `guardian.log` for detector and mitigator events.
