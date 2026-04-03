# Launches the Matrix animation, positions it at Claude Code's saved location,
# tracks its position, and restores Claude Code when animation completes.
# Window capture is handled by boost-capture.ps1 (runs inline before this).

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class WinAPI {
    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [DllImport("user32.dll", CharSet = CharSet.Unicode)]
    public static extern IntPtr FindWindow(string lpClassName, string lpWindowName);

    [DllImport("user32.dll")]
    public static extern bool IsWindowVisible(IntPtr hWnd);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public const int SW_RESTORE = 9;
}
"@

$tmpDir = "$env:LOCALAPPDATA\Temp"
$windowFile = "$tmpDir\claudeboost_window.txt"

# Read Claude Code's saved window info (written by boost-capture.ps1)
if (-not (Test-Path $windowFile)) { exit 1 }
$info = (Get-Content $windowFile).Split(',')
$claudeHwnd = [IntPtr]::new([long]$info[0])
$cx = [int]$info[1]; $cy = [int]$info[2]; $cw = [int]$info[3]; $ch = [int]$info[4]

# Launch the animation
$proc = Start-Process python -ArgumentList "C:/Development/ClaudeBoost/scripts/matrix-boost.py" -PassThru

# Find the animation window by its title ("CLAUDE BOOST" set by os.system('title ...'))
# Works for both conhost and Windows Terminal (WT sets window title from active tab)
$animHwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    $animHwnd = [WinAPI]::FindWindow($null, "CLAUDE BOOST")
    if ($animHwnd -ne [IntPtr]::Zero -and [WinAPI]::IsWindowVisible($animHwnd)) {
        break
    }
    $animHwnd = [IntPtr]::Zero
}

# Move animation window to Claude Code's position
if ($animHwnd -ne [IntPtr]::Zero) {
    [WinAPI]::MoveWindow($animHwnd, $cx, $cy, $cw, $ch, $true) | Out-Null
    [WinAPI]::SetForegroundWindow($animHwnd) | Out-Null
}

# Track the animation window's position while it runs (poll every 500ms)
# so we can restore Claude Code to wherever the user moved/resized it
$lastRect = New-Object WinAPI+RECT
$lastRect.Left = $cx; $lastRect.Top = $cy
$lastRect.Right = $cx + $cw; $lastRect.Bottom = $cy + $ch

while (-not $proc.HasExited) {
    if ($animHwnd -ne [IntPtr]::Zero) {
        $pollRect = New-Object WinAPI+RECT
        $ok = [WinAPI]::GetWindowRect($animHwnd, [ref]$pollRect)
        if ($ok -and ($pollRect.Right - $pollRect.Left) -gt 0) {
            $lastRect = $pollRect
        }
    }
    Start-Sleep -Milliseconds 500
}

# Restore Claude Code to the animation's final position/size
$fx = $lastRect.Left; $fy = $lastRect.Top
$fw = $lastRect.Right - $lastRect.Left; $fh = $lastRect.Bottom - $lastRect.Top
[WinAPI]::MoveWindow($claudeHwnd, $fx, $fy, $fw, $fh, $true) | Out-Null

# Bring Claude Code back
[WinAPI]::ShowWindow($claudeHwnd, [WinAPI]::SW_RESTORE) | Out-Null
[WinAPI]::SetForegroundWindow($claudeHwnd) | Out-Null

# Cleanup
Remove-Item $windowFile -ErrorAction SilentlyContinue
