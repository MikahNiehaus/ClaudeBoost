# Turn off xterm mouse and focus reporting.
#
# A TUI (Claude Code, vim, lazygit) enables these on start and disables them on
# exit. A process that is terminated rather than exited runs no cleanup, so the
# modes stay on. The terminal then keeps sending mouse position reports, and the
# shell reads them as typed input: bursts like
#     [I[555;113;1M[555;112;2M...
# and PSReadLine interpreting ESC-then-digit as its own binding, which surfaces
# as "digit-argument: 3" at the prompt.
#
# No hook can fix this reliably, because the process that should have cleaned up
# is already gone. The shell is the only thing still running, so the reset
# belongs here.
#
# Sequences, all "reset" (l) forms:
#   ?1000l  normal mouse tracking (click)
#   ?1002l  button event tracking (drag)
#   ?1003l  any event tracking (every movement, the loudest one)
#   ?1006l  SGR extended coordinates
#   ?1015l  urxvt extended coordinates  <- the [555;113;1M shape
#   ?1004l  focus in/out reporting      <- the [I / [O shape

function Reset-TerminalModes {
    try {
        [Console]::Write("$([char]27)[?1000l$([char]27)[?1002l$([char]27)[?1003l$([char]27)[?1006l$([char]27)[?1015l$([char]27)[?1004l")
    } catch {
        # A redirected or non interactive host has no console to write to.
        # Nothing to reset in that case, and throwing from a prompt function
        # would break the shell.
    }
}

Reset-TerminalModes
