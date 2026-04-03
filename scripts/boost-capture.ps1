# Captures the current foreground window (Claude Code) and minimizes it.
# Must run INLINE from Claude Code's terminal for accurate window detection.

Add-Type @"
using System;
using System.Runtime.InteropServices;

public class WinCapture {
    [DllImport("user32.dll")]
    public static extern IntPtr GetForegroundWindow();

    [DllImport("user32.dll")]
    public static extern bool GetWindowRect(IntPtr hWnd, out RECT lpRect);

    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }
}
"@

$hwnd = [WinCapture]::GetForegroundWindow()
$rect = New-Object WinCapture+RECT
[WinCapture]::GetWindowRect($hwnd, [ref]$rect) | Out-Null

$x = $rect.Left
$y = $rect.Top
$w = $rect.Right - $rect.Left
$h = $rect.Bottom - $rect.Top

"$($hwnd.ToInt64()),$x,$y,$w,$h" | Set-Content -Path "$env:LOCALAPPDATA\Temp\claudeboost_window.txt" -NoNewline

# Minimize Claude Code
[WinCapture]::ShowWindow($hwnd, 6) | Out-Null
