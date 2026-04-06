"""Watch the changes chat file for new questions. Exits when one is found."""
import json
import sys
import time
from pathlib import Path

CHAT_FILE = Path.home() / "AppData" / "Local" / "Temp" / "claudeboost" / "changes_chat.json"
POLL_INTERVAL = 3  # seconds
MAX_DURATION = 15 * 60  # 15 minutes

start = time.time()
last_question = ""

while time.time() - start < MAX_DURATION:
    try:
        if CHAT_FILE.exists():
            data = json.loads(CHAT_FILE.read_text(encoding="utf-8"))
            question = data.get("question", "")
            answer = data.get("answer", "")
            if question and not answer and question != last_question:
                # New unanswered question found
                print(f"QUESTION: {question}")
                print(f"FILE: {data.get('context_file', '')}")
                print(f"CODE: {data.get('context_code', '')[:200]}")
                sys.exit(0)
            last_question = question if answer else ""
    except (json.JSONDecodeError, OSError):
        pass
    time.sleep(POLL_INTERVAL)

print("TIMEOUT: 15 minutes elapsed, no new questions")
sys.exit(0)
