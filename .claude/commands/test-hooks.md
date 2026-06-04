# /test-hooks — Run Hook Test Suite

Run the ClaudeBoost hook test harness to verify all hook scripts behave correctly.

## Steps

1. Run the test suite:
   ```bash
   python -c "import os,subprocess,sys; h=os.environ['CLAUDEBOOST_HOME']; sys.exit(subprocess.run([sys.executable,h+'/scripts/test-hooks.py','-v']).returncode)"
   ```

2. Report results:
   - Pass: all tests green — hooks are healthy
   - Fail: show which tests failed and what was expected vs. actual
   - If any hook test fails after a hook change, fix the hook (or update the test if the behavior change was intentional) before proceeding

## When to run

- After any change to a hook script in `scripts/`
- After running `/setup` to verify hook installs didn't break anything
- Before implementing Phase B (mechanical evaluator routing) to confirm green baseline
- As a sanity check after pulling changes from remote
