---
description: Generate an interactive step by step tutorial with annotated screenshots for any feature or workflow. Drives a live app through Playwright, injects visual annotations (highlights, numbered callouts, arrows, popovers), captures screenshots, and assembles a polished markdown document.
allowed-tools: Read, Write, Edit, Bash, Glob, Grep, Agent, mcp__playwright__browser_navigate, mcp__playwright__browser_snapshot, mcp__playwright__browser_click, mcp__playwright__browser_type, mcp__playwright__browser_take_screenshot, mcp__playwright__browser_evaluate, mcp__playwright__browser_fill_form, mcp__playwright__browser_select_option, mcp__playwright__browser_wait_for, mcp__playwright__browser_press_key, mcp__playwright__browser_console_messages, mcp__playwright__browser_resize, mcp__playwright__browser_close, mcp__playwright__browser_hover, mcp__playwright__browser_find
argument-hint: <url> <feature description> [--output <dir>]
---

# /walkthrough -- Interactive Tutorial Generator

Arguments: **$ARGUMENTS**

Load the `walkthrough` skill and follow its full workflow.

Parse `$ARGUMENTS` for:
- A URL (required, must be local: localhost, 127.0.0.1, 0.0.0.0, *.local, *.test)
- A feature or workflow description
- Optional `--output <dir>` to override the default output directory

If no URL is provided, ask the user for one.

Follow all phases in the walkthrough skill: plan the steps, get user
approval, navigate and annotate each step with Playwright MCP, capture
annotated screenshots, assemble the markdown document, and verify the
output.
