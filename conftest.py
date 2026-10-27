import os

# Tests must never open the clean-rag console window on the desktop; see server_ctl._launch_console.
os.environ["CLEAN_RAG_CONSOLE"] = "0"
