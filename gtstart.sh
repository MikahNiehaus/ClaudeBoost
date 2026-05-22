#!/usr/bin/env bash
#
# gtstart — Gas Town rig launcher for macOS / Linux.
#
# If the current directory is already a registered rig, jumps into its
# crew workspace and launches Claude. Otherwise sets up the rig from scratch
# (Dolt, git init if needed, gt rig add, beads init, crew workspace).

set -e

SRCDIR="$(pwd)"
RIGNAME="$(basename "$SRCDIR" | tr ' ' '-')"
GT_HOME="$HOME/gt"
USERNAME="$(id -un)"
CREW_DIR="$GT_HOME/$RIGNAME/crew/$USERNAME"


prompt_and_launch() {
    cd "$CREW_DIR"
    echo ""
    echo "========================================"
    echo "  Session Options"
    echo "========================================"
    echo "  [1] New session"
    echo "  [2] Continue most recent session"
    echo "  [3] Resume (pick from list)"
    echo "========================================"
    echo ""
    read -rp "Choose [1/2/3]: " CHOICE
    case "$CHOICE" in
        2) claude --continue "gt prime" ;;
        3) claude --resume ;;
        *) claude "gt prime" ;;
    esac
}


# ── Fast path: rig already exists ────────────────────────────────────────────
if [ -d "$CREW_DIR" ]; then
    echo "Opening crew workspace for $RIGNAME..."
    prompt_and_launch
    exit 0
fi

# ── Setup path: turn this dir into a Gas Town rig ────────────────────────────
echo "========================================"
echo "  Setting up $RIGNAME as a Gastown rig"
echo "========================================"
echo ""

# Step 1: Ensure Dolt is running FIRST
echo "[1/6] Ensuring Dolt server is running..."
cd "$GT_HOME"
gt dolt recover >/dev/null 2>&1 || true
if ! gt dolt status 2>/dev/null | grep -q "running"; then
    gt dolt start
fi

# Step 2: Back to source — git init if needed
cd "$SRCDIR"
if [ ! -d ".git" ]; then
    echo "[2/6] Initializing git repo..."
    git init
    git add -A
    git commit -m "initial commit" --allow-empty
else
    echo "[2/6] Git repo found."
fi

# Step 3: Check for remote
REMOTE="$(git remote get-url origin 2>/dev/null || true)"

# Step 4: Add rig
cd "$GT_HOME"
if [ -z "$REMOTE" ]; then
    echo "[3/6] No remote found. Adopting local project..."
    if [ ! -d "$GT_HOME/$RIGNAME" ]; then
        # Copy contents (not the source dir itself) into the rig location.
        # cp -R preserves hidden files when source ends with /.
        mkdir -p "$GT_HOME/$RIGNAME"
        cp -R "$SRCDIR/." "$GT_HOME/$RIGNAME/"
    fi
    gt rig add "$RIGNAME" --adopt --force
else
    echo "[3/6] Adding rig from remote: $REMOTE"
    gt rig add "$RIGNAME" "$REMOTE"
fi

# Step 5: Restart Dolt to pick up new database, then init beads
echo "[4/6] Restarting Dolt for new database..."
gt dolt stop 2>/dev/null || true
sleep 3
gt dolt start

echo "[5/6] Initializing beads..."
PREFIX="${RIGNAME:0:2}"
cd "$GT_HOME/$RIGNAME"
bd init --force --prefix "$PREFIX" 2>/dev/null || true

# Step 6: Create crew workspace
echo "[6/6] Creating crew workspace..."
cd "$GT_HOME"

if ! gt crew add "$USERNAME" --rig "$RIGNAME" 2>/dev/null; then
    # Local adopted rig: create crew workspace manually
    echo "Creating crew workspace manually for local rig..."
    mkdir -p "$CREW_DIR"
    cp -R "$SRCDIR/." "$CREW_DIR/"
    mkdir -p "$CREW_DIR/.claude"
fi

gt hooks sync >/dev/null 2>&1 || true
gt doctor --fix --no-start >/dev/null 2>&1 || true

echo ""
echo "========================================"
echo "  Ready! Launching Claude Code..."
echo "  Rig: $RIGNAME"
echo "  Workspace: $CREW_DIR"
echo "========================================"
echo ""
prompt_and_launch
