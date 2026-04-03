#!/usr/bin/env python3
"""Matrix rain with live system status — reads checks from a status file."""
import sys, time, random, shutil, os, traceback

# Enable ANSI on Windows
if os.name == 'nt':
    os.system('')
    os.system('title CLAUDE BOOST')

# Use tempfile to get the canonical temp dir — avoids Git Bash /tmp vs Windows path mismatches
import tempfile
STATUS_FILE = os.path.join(tempfile.gettempdir(), 'claudeboost_status.txt')
WINDOW_FILE = os.path.join(tempfile.gettempdir(), 'claudeboost_window.txt')
WINDOW_FINAL_FILE = os.path.join(tempfile.gettempdir(), 'claudeboost_window_final.txt')

# Windows window management — position animation at Claude Code's location
_own_hwnd = None
if os.name == 'nt':
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        _GetConsoleWindow = kernel32.GetConsoleWindow
        _GetConsoleWindow.restype = wintypes.HWND

        _MoveWindow = user32.MoveWindow
        _MoveWindow.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                ctypes.c_int, ctypes.c_int, wintypes.BOOL]

        class RECT(ctypes.Structure):
            _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                         ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

        _GetWindowRect = user32.GetWindowRect
        _GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(RECT)]

        _own_hwnd = _GetConsoleWindow()

        # Read Claude Code's position and move ourselves there
        if os.path.exists(WINDOW_FILE):
            with open(WINDOW_FILE, 'r') as f:
                parts = f.read().strip().split(',')
            if len(parts) == 5:
                _, x, y, w, h = int(parts[0]), int(parts[1]), int(parts[2]), int(parts[3]), int(parts[4])
                _MoveWindow(_own_hwnd, x, y, w, h, True)
    except Exception:
        _own_hwnd = None


def _save_final_position():
    """Save this window's final position so the launcher can restore Claude Code there."""
    if _own_hwnd and os.name == 'nt':
        try:
            rect = RECT()
            _GetWindowRect(_own_hwnd, ctypes.byref(rect))
            with open(WINDOW_FINAL_FILE, 'w') as f:
                f.write(f'{rect.left},{rect.top},{rect.right - rect.left},{rect.bottom - rect.top}')
        except Exception:
            pass

cols, rows = shutil.get_terminal_size()
# Safety clamp
cols = max(cols, 40)
rows = max(rows, 15)

# ANSI codes
HIDE = '\033[?25l'
SHOW = '\033[?25h'
HOME = '\033[H'
CLEAR = '\033[2J'
RESET = '\033[0m'
BG = '\033[92;1m'    # Bright green bold
G = '\033[32m'       # Green
DG = '\033[32;2m'    # Dim green
AMBER = '\033[33;1m' # Amber/yellow bold
RED = '\033[91;1m'   # Red bold
BLACK_BG = '\033[40m'

# Text to reveal
title = 'C L A U D E   B O O S T'
sub = 'multi-agent orchestration toolkit'

tr = max(2, rows // 2 - 4)
tc = max(0, (cols - len(title)) // 2)
sr = tr + 2
sc = max(0, (cols - len(sub)) // 2)
status_start_row = sr + 2

systems = ['PRIVACY', 'RAG', 'GT', 'RULES', 'AGENTS']


def read_status():
    """Read status file. Uses LAST value per key so append-only works."""
    result = {s: 'waiting' for s in systems}
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
            for line in content.splitlines():
                line = line.strip()
                if ':' in line:
                    key, val = line.split(':', 1)
                    key = key.strip().upper()
                    if key in result:
                        result[key] = val.strip()
    except Exception:
        pass
    return result


def format_status_line(name, state, width):
    """Format: NAME ......... [STATUS]"""
    if state == 'waiting':
        tag = f'{DG}[  ----  ]{RESET}{BLACK_BG}'
    elif state == 'checking':
        tag = f'{AMBER}[CHECKING]{RESET}{BLACK_BG}'
    elif state.startswith('fail'):
        tag = f'{RED}[ FAILED ]{RESET}{BLACK_BG}'
    else:
        tag = f'{BG}[ ONLINE ]{RESET}{BLACK_BG}'

    # Name padding
    padded_name = name.ljust(8)
    dots_count = max(3, width - len(padded_name) - 14)
    dots = DG + '.' * dots_count + RESET + BLACK_BG
    return f'  {G}{padded_name}{RESET}{BLACK_BG}{dots} {tag}'


class Drop:
    __slots__ = ['x', 'y', 'speed', 'length']
    def __init__(self, x, max_rows):
        self.x = x
        self.y = random.randint(-max_rows, 0)
        self.speed = random.randint(1, 3)
        self.length = random.randint(4, 14)

    def update(self, max_rows):
        self.y += self.speed
        if self.y - self.length > max_rows:
            self.y = random.randint(-8, 0)
            self.speed = random.randint(1, 3)
            self.length = random.randint(4, 14)


drops = [Drop(x, rows) for x in range(0, cols)]

# DO NOT clear the status file here — boost.md already creates it fresh.
# Clearing here causes a race condition where we overwrite statuses that
# Claude has already written.

sys.stdout.write(BLACK_BG + HIDE + CLEAR)
sys.stdout.flush()

try:
    frame = 0
    all_online_since = None

    while True:
        frame += 1

        # Read status every 5 frames to reduce file I/O
        if frame % 5 == 1:
            status = read_status()

        all_online = all(
            v not in ('waiting', 'checking') and not v.startswith('fail')
            for v in status.values()
        )

        if all_online and all_online_since is None:
            all_online_since = frame
        if all_online_since and (frame - all_online_since) > 50:
            break
        if frame > 1200:  # 60 second timeout
            break

        # Build rain grid
        grid = {}
        for d in drops:
            for i in range(d.length):
                ry = d.y - i
                if 0 <= ry < rows and 0 <= d.x < cols:
                    if i == 0:
                        grid[(ry, d.x)] = (BG, random.choice('01'))
                    elif i < 3:
                        grid[(ry, d.x)] = (G, random.choice('01'))
                    else:
                        grid[(ry, d.x)] = (DG, random.choice('01'))
            d.update(rows)

        # Protected rows
        protected = set()
        if frame > 15:
            protected.add(tr)
        if frame > 25:
            protected.add(sr)
        if frame > 20:
            for i in range(len(systems)):
                protected.add(status_start_row + i)
        if all_online:
            protected.add(status_start_row + len(systems) + 1)

        # Render
        output = [HOME]
        for r in range(rows - 1):
            if r in protected:
                # Title row
                if r == tr:
                    n = min(len(title), (frame - 15) * 2)
                    pad = ' ' * tc
                    txt = title[:n]
                    output.append(f'{BLACK_BG}{pad}{BG}{txt}{" " * (cols - tc - len(txt))}{RESET}{BLACK_BG}')
                    continue

                # Subtitle row
                if r == sr and frame > 25:
                    n = min(len(sub), (frame - 25) * 3)
                    pad = ' ' * sc
                    txt = sub[:n]
                    output.append(f'{BLACK_BG}{pad}{DG}{txt}{" " * (cols - sc - len(txt))}{RESET}{BLACK_BG}')
                    continue

                # Status lines
                idx = r - status_start_row
                if 0 <= idx < len(systems):
                    name = systems[idx]
                    line = format_status_line(name, status[name], min(cols - 4, 50))
                    remaining = max(0, cols - 54)
                    output.append(f'{BLACK_BG}{line}{" " * remaining}{RESET}{BLACK_BG}')
                    continue

                # All-online banner
                if all_online and r == status_start_row + len(systems) + 1:
                    banner = '[ ALL SYSTEMS ONLINE ]'
                    pad = max(0, (cols - len(banner)) // 2)
                    output.append(f'{BLACK_BG}{" " * pad}{BG}{banner}{" " * max(0, cols - pad - len(banner))}{RESET}{BLACK_BG}')
                    continue

            # Rain row
            row_buf = []
            for c in range(cols):
                if (r, c) in grid:
                    color, ch = grid[(r, c)]
                    row_buf.append(f'{color}{ch}')
                else:
                    row_buf.append(' ')
            output.append(f'{BLACK_BG}{"".join(row_buf)}{RESET}{BLACK_BG}')

        sys.stdout.write('\n'.join(output))
        sys.stdout.flush()
        time.sleep(0.05)

except KeyboardInterrupt:
    pass
except Exception:
    # Log crash for debugging
    with open(STATUS_FILE + '.error', 'w') as f:
        traceback.print_exc(file=f)
finally:
    _save_final_position()
    sys.stdout.write(SHOW + RESET + CLEAR)
    sys.stdout.flush()
    try:
        os.remove(STATUS_FILE)
    except Exception:
        pass
