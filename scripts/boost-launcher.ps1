# Launches the Matrix animation at Claude Code's exact position,
# tracks it, and restores Claude Code when animation completes.
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

    [DllImport("kernel32.dll")]
    public static extern uint WaitForSingleObject(IntPtr hHandle, uint dwMilliseconds);

    [DllImport("kernel32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    public static extern bool CreateProcess(
        string lpApplicationName,
        string lpCommandLine,
        IntPtr lpProcessAttributes,
        IntPtr lpThreadAttributes,
        bool bInheritHandles,
        uint dwCreationFlags,
        IntPtr lpEnvironment,
        string lpCurrentDirectory,
        ref STARTUPINFO lpStartupInfo,
        out PROCESS_INFORMATION lpProcessInformation
    );

    [DllImport("kernel32.dll")]
    public static extern bool CloseHandle(IntPtr hObject);

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    public struct STARTUPINFO {
        public int cb;
        public string lpReserved;
        public string lpDesktop;
        public string lpTitle;
        public int dwX;
        public int dwY;
        public int dwXSize;
        public int dwYSize;
        public int dwXCountChars;
        public int dwYCountChars;
        public int dwFillAttribute;
        public int dwFlags;
        public short wShowWindow;
        public short cbReserved2;
        public IntPtr lpReserved2;
        public IntPtr hStdInput;
        public IntPtr hStdOutput;
        public IntPtr hStdError;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct PROCESS_INFORMATION {
        public IntPtr hProcess;
        public IntPtr hThread;
        public int dwProcessId;
        public int dwThreadId;
    }

    [StructLayout(LayoutKind.Sequential)]
    public struct RECT {
        public int Left;
        public int Top;
        public int Right;
        public int Bottom;
    }

    // STARTUPINFO flags
    public const int STARTF_USEPOSITION = 0x04;
    public const int STARTF_USESIZE = 0x02;
    public const int STARTF_USESHOWWINDOW = 0x01;

    // CreateProcess flags
    public const uint CREATE_NEW_CONSOLE = 0x00000010;

    // ShowWindow commands
    public const short SW_SHOWMINNOACTIVE = 7;
    public const int SW_RESTORE = 9;

    public const uint INFINITE = 0xFFFFFFFF;
}
"@

$tmpDir = "$env:LOCALAPPDATA\Temp"
$windowFile = "$tmpDir\claudeboost_window.txt"

# Read Claude Code's saved window info (written by boost-capture.ps1)
if (-not (Test-Path $windowFile)) { exit 1 }
$info = (Get-Content $windowFile).Split(',')
$claudeHwnd = [IntPtr]::new([long]$info[0])
$cx = [int]$info[1]; $cy = [int]$info[2]; $cw = [int]$info[3]; $ch = [int]$info[4]

# Find python.exe path
$pythonPath = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $pythonPath) { $pythonPath = "python" }

# Launch animation using CreateProcess with STARTUPINFO to set initial position.
# This places the window at Claude Code's exact position FROM THE START,
# avoiding any flash on the wrong monitor.
$si = New-Object WinAPI+STARTUPINFO
$si.cb = [System.Runtime.InteropServices.Marshal]::SizeOf([type][WinAPI+STARTUPINFO])
$si.dwFlags = [WinAPI]::STARTF_USEPOSITION -bor [WinAPI]::STARTF_USESIZE -bor [WinAPI]::STARTF_USESHOWWINDOW
$si.dwX = $cx
$si.dwY = $cy
$si.dwXSize = $cw
$si.dwYSize = $ch
$si.wShowWindow = [WinAPI]::SW_SHOWMINNOACTIVE  # Start minimized (no flash)

$pi = New-Object WinAPI+PROCESS_INFORMATION
$cmdLine = "`"$pythonPath`" `"C:/Development/ClaudeBoost/scripts/matrix-boost.py`""

$created = [WinAPI]::CreateProcess(
    $null,
    $cmdLine,
    [IntPtr]::Zero,
    [IntPtr]::Zero,
    $false,
    [WinAPI]::CREATE_NEW_CONSOLE,
    [IntPtr]::Zero,
    $null,
    [ref]$si,
    [ref]$pi
)

if (-not $created) {
    # Fallback: use Start-Process if CreateProcess fails
    $proc = Start-Process python -ArgumentList "C:/Development/ClaudeBoost/scripts/matrix-boost.py" -PassThru -WindowStyle Minimized
    $processHandle = $null
    $fallback = $true
} else {
    $processHandle = $pi.hProcess
    [WinAPI]::CloseHandle($pi.hThread) | Out-Null
    $fallback = $false
}

# Find the animation window by title and position it correctly
$animHwnd = [IntPtr]::Zero
for ($i = 0; $i -lt 30; $i++) {
    Start-Sleep -Milliseconds 200
    $animHwnd = [WinAPI]::FindWindow($null, "CLAUDE BOOST")
    if ($animHwnd -ne [IntPtr]::Zero) { break }
}

if ($animHwnd -ne [IntPtr]::Zero) {
    # Move to exact position while still minimized
    [WinAPI]::MoveWindow($animHwnd, $cx, $cy, $cw, $ch, $true) | Out-Null
    # Now restore — window appears at correct position, no flash
    [WinAPI]::ShowWindow($animHwnd, [WinAPI]::SW_RESTORE) | Out-Null
    [WinAPI]::SetForegroundWindow($animHwnd) | Out-Null
}

# Track the animation window's position while it runs (poll every 500ms)
$lastRect = New-Object WinAPI+RECT
$lastRect.Left = $cx; $lastRect.Top = $cy
$lastRect.Right = $cx + $cw; $lastRect.Bottom = $cy + $ch

if ($fallback) {
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
} else {
    # Poll position while waiting for process to exit
    while ($true) {
        $wait = [WinAPI]::WaitForSingleObject($processHandle, 500)
        if ($animHwnd -ne [IntPtr]::Zero) {
            $pollRect = New-Object WinAPI+RECT
            $ok = [WinAPI]::GetWindowRect($animHwnd, [ref]$pollRect)
            if ($ok -and ($pollRect.Right - $pollRect.Left) -gt 0) {
                $lastRect = $pollRect
            }
        }
        if ($wait -ne 258) { break }  # 258 = WAIT_TIMEOUT, anything else = signaled/error
    }
    [WinAPI]::CloseHandle($processHandle) | Out-Null
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
