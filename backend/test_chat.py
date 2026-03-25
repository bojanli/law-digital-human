import urllib.request as request
import json
import time

url = "http://127.0.0.1:8000/api/chat"
headers = {"Content-Type": "application/json"}
session_id = "test-session-123"

def ask(text):
    data = json.dumps({"session_id": session_id, "text": text, "mode": "chat"}).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            print(f"\nUser: {text}")
            print(f"Assistant: {body['answer_json']['conclusion']}")
            print(f"(Rewritten or context used internally)")
    except Exception as e:
        print(f"Error: {e}")

print("--- Test Multi-turn RAG ---")
ask("租房押金不退怎么办")
time.sleep(1)
ask("没签合同他也不退呢？")
