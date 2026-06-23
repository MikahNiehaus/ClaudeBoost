"""
debug-dotnet-tests.py

Helper for mcp-debugger sessions with .NET test projects (xUnit 2.x, NUnit, MSTest / VSTest mode).

xUnit 2.x DLLs are class libraries with no Main entry point.
VSTest spawns a child process (testhost) that loads the DLL and runs tests.
Setting VSTEST_HOST_DEBUG=1 makes testhost pause after starting and print its
PID to stdout — giving mcp-debugger time to attach before any tests run.

Usage:
  python debug-dotnet-tests.py --project-path /path/to/Tests.csproj [options]

Options:
  --project-path PATH   Path to the test .csproj file or directory containing one (required)
  --filter EXPR         dotnet test --filter expression to narrow which tests run
  --no-build            Pass --no-build to dotnet test (use after a successful build)
  --timeout SECS        Seconds to wait for testhost to print its PID (default: 30)

Output (stdout, one JSON line):
  Success:
    {"status": "waiting", "pid": 12345, "name": "testhost",
     "dotnet_test_pid": 67890,
     "message": "Attach mcp-debugger to PID 12345, then set breakpoints, then call continue_execution"}

  Failure:
    {"status": "error", "error": "..."}

Workflow after running this script:
  1. Read the JSON output and extract "pid"
  2. Call mcp__mcp-debugger__create_debug_session (language: dotnet)
  3. Call mcp__mcp-debugger__attach_to_process with that PID
  4. Set all breakpoints while testhost is still paused
  5. Call mcp__mcp-debugger__continue_execution — tests run and hit your breakpoints
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time

PID_PATTERN = re.compile(r"Process Id:\s*(\d+),\s*Name:\s*(\w+)")
TIMEOUT_DEFAULT = 30


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Start dotnet test with VSTEST_HOST_DEBUG=1 and capture testhost PID"
    )
    p.add_argument(
        "--project-path",
        required=True,
        help="Path to .csproj file or directory containing one",
    )
    p.add_argument(
        "--filter",
        default=None,
        help="dotnet test --filter expression (e.g. 'FullyQualifiedName~MyTest')",
    )
    p.add_argument(
        "--no-build",
        action="store_true",
        help="Pass --no-build to dotnet test",
    )
    p.add_argument(
        "--timeout",
        type=int,
        default=TIMEOUT_DEFAULT,
        help=f"Seconds to wait for testhost PID line (default: {TIMEOUT_DEFAULT})",
    )
    return p.parse_args()


def build_command(args: argparse.Namespace) -> list[str]:
    cmd = ["dotnet", "test", args.project_path]
    if args.no_build:
        cmd.append("--no-build")
    if args.filter:
        cmd.extend(["--filter", args.filter])
    return cmd


def main() -> None:
    args = parse_args()
    cmd = build_command(args)

    env = {**os.environ, "VSTEST_HOST_DEBUG": "1"}

    try:
        proc = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
    except FileNotFoundError:
        print(json.dumps({"status": "error", "error": "dotnet not found on PATH"}))
        sys.exit(1)

    deadline = time.monotonic() + args.timeout
    found: dict | None = None

    for line in proc.stdout:
        line = line.rstrip()
        m = PID_PATTERN.search(line)
        if m:
            found = {"pid": int(m.group(1)), "name": m.group(2)}
            break
        if time.monotonic() > deadline:
            break

    if found is None:
        proc.kill()
        proc.wait()
        print(json.dumps({
            "status": "error",
            "error": (
                f"timeout after {args.timeout}s — testhost PID line not found in dotnet test output. "
                "Ensure VSTEST_HOST_DEBUG is supported by the test adapter "
                "(xUnit.runner.visualstudio, NUnit3TestAdapter, MSTest.TestAdapter)."
            ),
        }))
        sys.exit(1)

    pid = found["pid"]
    name = found["name"]

    print(json.dumps({
        "status": "waiting",
        "pid": pid,
        "name": name,
        "dotnet_test_pid": proc.pid,
        "message": (
            f"Attach mcp-debugger to PID {pid} ({name}) now. "
            "Set all breakpoints, then call continue_execution. "
            f"The dotnet test host process (PID {proc.pid}) is alive and waiting. "
            "Tests will run only after you call continue_execution."
        ),
    }))

    # Block here — the testhost process is paused waiting for a debugger attach.
    # It will resume when the debugger calls continue_execution, run all tests,
    # then exit normally. Keeping this process alive ensures the PID stays valid.
    try:
        proc.wait()
    except KeyboardInterrupt:
        proc.kill()
        proc.wait()


if __name__ == "__main__":
    main()
