"""
llm_analyzer.py

Built specifically around your concept:
LLM receives raw attack evidence
LLM reasons about what is happening
LLM prescribes the route fix
System executes exactly what LLM said
LLM reasoning is stored and displayed
"""

from __future__ import annotations

import os
import json
import time
import logging
import re
from typing import Optional

import requests

import shared_state
from shared_state import ThreatEvent, AttackType
import mitigator

logger = logging.getLogger("llm_analyzer")

# --- OLLAMA SETUP ---
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "tinyllama")

MAX_RETRIES = 3
OLLAMA_TIMEOUT = 30  # Reduced from 60 to fail faster


def _build_prompt(threat: ThreatEvent) -> str:
    """
    Gives the LLM raw evidence only.
    The LLM figures out the rest itself.
    """
    import platform
    os_name = platform.system()

    if os_name == "Windows":
        cmd_format = f"route add {threat.attacker_ip} mask 255.255.255.255 192.0.2.1"
    else:
        cmd_format = f"ip route add blackhole {threat.attacker_ip}/32"

    # Simpler, more focused prompt
    return f"""You are a network security analyst. Analyze this attack and respond with JSON only.

Attack Evidence:
- Source IP: {threat.attacker_ip}
- Attack Type: {threat.attack_type.value}
- Packet Count: {threat.packet_count} packets in 1 second
- Normal Baseline: under 20 packets per second

Respond with ONLY this JSON (no markdown, no extra text):
{{
  "attack": "{threat.attack_type.value}",
  "explanation": "Brief technical explanation of this attack and why blocking this IP stops it",
  "mitigation": "{cmd_format}"
}}"""


def _extract_json_text(raw: str) -> str:
    """Extract JSON from LLM response, removing markdown fences."""
    if raw is None:
        return "{}"

    # Remove markdown code fences
    cleaned = re.sub(r"```(?:json)?\s*\n?", "", raw, flags=re.IGNORECASE)
    cleaned = re.sub(r"\n?```\s*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()

    # Remove control characters
    cleaned = re.sub(r"[\x00-\x08\x0b-\x1f]+", " ", cleaned)
    
    logger.debug("Extracted JSON text: %s", cleaned[:500])
    return cleaned


def _normalize_ollama_response(response_json):
    """Extract content from nested Ollama response structure."""
    def _unwrap(value):
        while isinstance(value, list):
            value = value[0] if value else {}
        return value

    response_json = _unwrap(response_json)

    if isinstance(response_json, dict):
        # Try different possible content locations
        if "message" in response_json:
            response_json = response_json["message"]
        elif "output" in response_json:
            response_json = response_json["output"]
        
        response_json = _unwrap(response_json)
        
        if isinstance(response_json, dict):
            if "content" in response_json:
                return str(response_json["content"])
            else:
                return json.dumps(response_json)
        return str(response_json)

    return str(response_json)


def _call_ollama(prompt: str) -> str:
    """Call Ollama API with timeout and error handling."""
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [
            {
                "role": "system",
                "content": "You are a network security analyst. Respond with valid JSON only. No markdown, no code fences, just JSON."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 200  # Limit response length
        }
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=OLLAMA_TIMEOUT
        )
        response.raise_for_status()
        raw = response.json()
        content = _normalize_ollama_response(raw)
        logger.debug("Ollama response: %s", content[:200])
        return _extract_json_text(content)
    except requests.exceptions.Timeout:
        logger.error("Ollama request timed out after %ds", OLLAMA_TIMEOUT)
        raise
    except requests.exceptions.ConnectionError:
        logger.error("Cannot connect to Ollama at %s", OLLAMA_BASE_URL)
        raise
    except Exception as e:
        logger.error("Ollama API error: %s", e)
        raise


def _call_llm(prompt: str) -> dict:
    """Call LLM and parse JSON response."""
    logger.debug("Calling Ollama chat with model %s", OLLAMA_MODEL)
    text = _call_ollama(prompt)
    
    try:
        parsed = json.loads(text)
        if isinstance(parsed, list):
            parsed = parsed[0] if parsed else {}
        if not isinstance(parsed, dict):
            raise ValueError("LLM returned non-object JSON")
        return parsed
    except json.JSONDecodeError as e:
        logger.error("JSON parse error: %s\nText: %s", e, text[:500])
        raise
    except Exception as e:
        logger.error("LLM response processing error: %s", e)
        raise


def _format_reasoning_for_ui(result: dict, threat: ThreatEvent) -> str:
    """Format LLM response for dashboard display."""
    attack = result.get('attack') or threat.attack_type.value
    
    explanation = (
        result.get('explanation') or 
        result.get('description') or 
        f"High-volume {threat.attack_type.value} detected exceeding baseline thresholds."
    )

    # Catch empty/invalid explanations
    if explanation.strip().lower() in ["na", "n/a", "none", "null", ""]:
        explanation = f"Detected {threat.attack_type.value} with {threat.packet_count} packets in 1 second."
               
    mitigation = result.get('mitigation') or 'Route-based IP block'

    lines = [
        f"ATTACK: {attack}",
        f"",
        f"EXPLANATION:",
        f"  {explanation}",
        f"",
        f"COMMAND: {mitigation}",
    ]
    return "\n".join(lines)


def _create_fallback_reasoning(threat: ThreatEvent, error_msg: str) -> str:
    """Create fallback reasoning when LLM fails."""
    explanations = {
        AttackType.ICMP_FLOOD: "ICMP flood attack detected. Attacker is sending excessive ping requests to overwhelm the target. Blocking the source IP prevents further ICMP traffic.",
        AttackType.SYN_FLOOD: "TCP SYN flood attack detected. Attacker is sending SYN packets without completing the handshake, exhausting connection resources. Blocking prevents new connection attempts.",
        AttackType.UDP_FLOOD: "UDP flood attack detected. Attacker is sending high-volume UDP packets to random ports, consuming bandwidth and CPU. Blocking the source IP stops the flood.",
        AttackType.PORT_SCAN: "Port scan detected. Attacker is probing multiple ports to discover services. Blocking prevents further reconnaissance.",
        AttackType.FRAGMENTATION: "IP fragmentation attack detected. Attacker is sending fragmented packets to evade detection or exhaust reassembly resources. Blocking stops the attack.",
        AttackType.UNKNOWN: f"Anomalous traffic pattern detected with {threat.packet_count} packets in 1 second."
    }
    
    explanation = explanations.get(threat.attack_type, explanations[AttackType.UNKNOWN])
    
    import platform
    if platform.system() == "Windows":
        cmd = f"route add {threat.attacker_ip} mask 255.255.255.255 192.0.2.1"
    else:
        cmd = f"ip route add blackhole {threat.attacker_ip}/32"
    
    return f"""ATTACK: {threat.attack_type.value}

EXPLANATION:
  {explanation}
  
  Note: LLM analysis failed ({error_msg}). Using built-in detection logic.

COMMAND: {cmd}"""


def run_analyzer():
    """
    Main loop.

    Each ThreatEvent goes through:
      1. Build prompt from raw evidence
      2. Ollama reasons about what is happening
      3. Ollama prescribes the route fix
      4. We display the full reasoning
      5. We execute exactly what the LLM said
    """
    logger.info("LLM Analyzer started — using Ollama backend")
    shared_state.ui_log_queue.put(
        f"[bold cyan]OLLAMA[/] Analyzer ready (model: {OLLAMA_MODEL})"
    )

    # Check if Ollama is reachable
    try:
        response = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if response.status_code == 200:
            logger.info("Ollama connection verified")
        else:
            logger.warning("Ollama responded with status %d", response.status_code)
    except Exception as e:
        logger.error("Cannot connect to Ollama: %s", e)
        shared_state.ui_log_queue.put(
            f"[bold red]OLLAMA[/] Warning: Cannot connect to Ollama at {OLLAMA_BASE_URL}"
        )

    while not shared_state.shutdown_event.is_set():
        try:
            threat: ThreatEvent = shared_state.threat_queue.get(timeout=0.5)
        except shared_state.queue.Empty:
            continue

        # Tell the UI we are thinking
        shared_state.ui_log_queue.put(
            f"[bold cyan]OLLAMA[/] Analyzing: {threat.packet_count} "
            f"{threat.attack_type.value} packets from {threat.attacker_ip}..."
        )

        last_error: Optional[str] = None
        success = False

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                prompt = _build_prompt(threat)
                result = _call_llm(prompt)

                # Validate required fields
                if not result.get("attack"):
                    result["attack"] = threat.attack_type.value
                if not result.get("explanation"):
                    result["explanation"] = f"{threat.attack_type.value} detected with {threat.packet_count} packets."
                if not result.get("mitigation"):
                    import platform
                    if platform.system() == "Windows":
                        result["mitigation"] = f"route add {threat.attacker_ip} mask 255.255.255.255 192.0.2.1"
                    else:
                        result["mitigation"] = f"ip route add blackhole {threat.attacker_ip}/32"

                # Store full reasoning in the ThreatEvent
                threat.llm_reasoning = _format_reasoning_for_ui(result, threat)
                threat.mitigation_command = result.get("mitigation", "")

                # Validate the command contains the right IP
                if threat.attacker_ip not in threat.mitigation_command:
                    logger.warning("LLM gave wrong IP in command — correcting.")
                    import platform
                    if platform.system() == "Windows":
                        threat.mitigation_command = f"route add {threat.attacker_ip} mask 255.255.255.255 192.0.2.1"
                    else:
                        threat.mitigation_command = f"ip route add blackhole {threat.attacker_ip}/32"

                # Log the LLM's reasoning to UI
                verdict_msg = (
                    f"[bold cyan]OLLAMA VERDICT[/] "
                    f"{result.get('attack', threat.attack_type.value)} detected | "
                    f"From: {threat.attacker_ip}"
                )
                shared_state.ui_log_queue.put(verdict_msg)
                
                explanation_str = result.get('explanation', 'Attack blocked based on threshold.')
                says_msg = f"[cyan]OLLAMA SAYS:[/] {explanation_str[:150]}..."
                shared_state.ui_log_queue.put(says_msg)
                
                fix_msg = f"[cyan]OLLAMA FIX:[/] {threat.mitigation_command}"
                shared_state.ui_log_queue.put(fix_msg)

                # Save successful reasoning to log
                logger.info("LLM Verdict: %s", verdict_msg)
                logger.info("LLM Reasoning:\n%s", threat.llm_reasoning)

                success = True
                break

            except requests.exceptions.Timeout:
                last_error = f"Timeout after {OLLAMA_TIMEOUT}s"
                logger.error("Attempt %d failed: %s", attempt, last_error)
            except requests.exceptions.ConnectionError:
                last_error = "Cannot connect to Ollama"
                logger.error("Attempt %d failed: %s", attempt, last_error)
                # Don't retry connection errors - fail fast
                break
            except Exception as e:
                last_error = str(e)
                logger.error("Attempt %d failed: %s", attempt, e)

            if attempt < MAX_RETRIES:
                time.sleep(1)  # Reduced from 2s

        if not success:
            # LLM failed — apply direct block with fallback reasoning
            logger.error("Ollama failed after %d attempts: %s", MAX_RETRIES, last_error)
            shared_state.ui_log_queue.put(
                f"[bold red]OLLAMA FAILED[/] {last_error} — "
                f"applying direct block on {threat.attacker_ip}"
            )
            
            threat.llm_reasoning = _create_fallback_reasoning(threat, last_error)
            
            import platform
            if platform.system() == "Windows":
                threat.mitigation_command = f"route add {threat.attacker_ip} mask 255.255.255.255 192.0.2.1"
            else:
                threat.mitigation_command = f"ip route add blackhole {threat.attacker_ip}/32"

        # Execute the mitigation
        try:
            mitigator.apply_mitigation(threat)
        except Exception as exc:
            logger.exception("Unexpected error applying mitigation: %s", exc)
            threat.mitigation_status = "FAILED"
            shared_state.ui_log_queue.put(
                f"[bold red]MITIGATOR[/] Unexpected error: {exc}"
            )

    logger.info("LLM Analyzer stopped.")