# test_ollama.py — run this standalone to verify your setup
import requests
import json

OLLAMA_BASE_URL = "http://localhost:11434"
MODEL = "llama3.2"

def test_connection():
    try:
        r = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        models = [m["name"] for m in r.json().get("models", [])]
        print(f"✓ Ollama running. Available models: {models}")
        return True
    except Exception as e:
        print(f"✗ Cannot connect to Ollama: {e}")
        print("  Fix: run 'ollama serve' in another terminal")
        return False

def test_json_response():
    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": "Respond with JSON only. No markdown. No explanation."
            },
            {
                "role": "user",
                "content": (
                    "IP 10.0.0.99 sent 150 ICMP packets in 1 second. "
                    "Respond with JSON: "
                    '{"threat": "description", "command": "route add 10.0.0.99 mask 255.255.255.255 192.0.2.1"}'
                )
            }
        ],
        "stream": False,
        "options": {"temperature": 0.1}
    }

    print(f"\nTesting model: {MODEL}")
    r = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=60)
    raw = r.json()["message"]["content"]
    print(f"Raw response:\n{raw}")

    try:
        parsed = json.loads(raw.strip())
        print(f"\n✓ JSON parsed successfully: {parsed}")
    except json.JSONDecodeError:
        print(f"\n✗ Response is not clean JSON — extractor will handle this")

if __name__ == "__main__":
    if test_connection():
        test_json_response()
        