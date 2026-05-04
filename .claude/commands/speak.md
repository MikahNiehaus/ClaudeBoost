---
argument-hint: [on|off|voice <name>|voices|status]
description: Toggle text-to-speech — Claude speaks responses aloud
allowed-tools: Read, Write, Bash
---

# TTS Control: $ARGUMENTS

Toggle text-to-speech so Claude's responses are spoken aloud via edge-tts (free Microsoft Neural TTS).

## Instructions

1. **Read current state**: `Read $CLAUDEBOOST_HOME/state/speak-state.json`

2. **Parse `$ARGUMENTS`**:

   - **Empty or `status`**: Display current state — enabled/disabled, voice name, max chars. Done.

   - **`on`**: Write updated state with `"enabled": true`. Then **adopt concise mode for the rest of this session**: your responses will be spoken aloud, so write short — 1-3 sentences max, no lists, no tables, no headers, no filler. Say what matters, skip the rest. The user can still read the full text. Confirm briefly:
     > TTS on. Keeping responses short for voice.

   - **`off`**: Write updated state with `"enabled": false`. **Drop concise mode** — return to normal response length. Confirm:
     > TTS off. Back to normal responses.

   - **`voice <name>`**: Write updated state with the new voice name (e.g. `en-US-AndrewNeural`). Confirm:
     > Voice changed to **<name>**. Next response will use the new voice.

   - **`voices`**: Run `Bash: python -m edge_tts --list-voices 2>/dev/null | grep "en-US"` and display the results as a table. If edge-tts is not installed, tell the user to run `pip install edge-tts`.

3. **When writing state**, use this format:
   ```json
   {
     "enabled": <true|false>,
     "voice": "<voice name>",
     "maxChars": 500,
     "setAt": "<current ISO 8601 timestamp>",
     "setBy": "user /speak <arg>"
   }
   ```

4. **Verify edge-tts** (only on `on`): Run `Bash: python -c "import edge_tts; print('ok')"`. If it fails, tell the user:
   > edge-tts is not installed. Run `pip install edge-tts` first.

5. **Pair with /voice**: Mention that `/voice` enables speech-to-text input (built into Claude Code). Together `/voice` + `/speak` give two-way voice conversation.
