# ClaudeBoost Animation Launcher
# Captures Claude Code window, minimizes it, launches animation at same position,
# then restores Claude Code to animation's final position when done.

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class WinAPI {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool MoveWindow(IntPtr hWnd, int X, int Y, int nWidth, int nHeight, bool bRepaint);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [DllImport("user32.dll")]
    public static extern bool SetForegroundWindow(IntPtr hWnd);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    public const int SW_MINIMIZE = 6;
    public const int SW_RESTORE = 9;
}
"@

$tmpDir = "$env:LOCALAPPDATA\Temp"
$windowFile = "$tmpDir\claudeboost_window.txt"

# Capture the current foreground window (Claude Code terminal)
$claudeHwnd = [WinAPI]::GetForegroundWindow()
$rect = New-Object WinAPI+RECT
[WinAPI]::GetWindowRect($claudeHwnd, [ref]$rect) | Out-Null

$x = $rect.Left
$y = $rect.Top
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top

# Save Claude Code hwnd and geometry for the Python script
"$($claudeHwnd.ToInt64()),$x,$y,$w,$h" | Set-Content -Path $windowFile -NoNewline

# Minimize Claude Code
[WinAPI]::ShowWindow($claudeHwnd, [WinAPI]::SW_MINIMIZE) | Out-Null

# Launch animation and wait for it to finish
$proc = Start-Process python -ArgumentList "C:/Development/ClaudeBoost/scripts/matrix-boost.py" -PassThru
$proc.WaitForExit()

# Read final position from the animation (it saves before exiting)
$finalFile = "$tmpDir\claudeboost_window_final.txt"
if (Test-Path $finalFile) {
    $parts = (Get-Content $finalFile).Split(',')
    $fx = [int]$parts[0]
    $fy = [int]$parts[1]
    $fw = [int]$parts[2]
    $fh = [int]$parts[3]

    # Move Claude Code to the animation's final position/size
    [WinAPI]::MoveWindow($claudeHwnd, $fx, $fy, $fw, $fh, $true) | Out-Null
    Remove-Item $finalFile -ErrorAction SilentlyContinue
}

# Restore and bring Claude Code to front
[WinAPI]::ShowWindow($claudeHwnd, [WinAPI]::SW_RESTORE) | Out-Null
[WinAPI]::SetForegroundWindow($claudeHwnd) | Out-Null

# Cleanup
Remove-Item $windowFile -ErrorAction SilentlyContinue
