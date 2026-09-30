#!/usr/bin/env node
'use strict';

// Reuses squeez's usage.js for the 5h/7d fetch; skips buddy's duck/XP HUD.

const path = require('path');
const os = require('os');

function configDir() {
  const env = (process.env.CLAUDE_CONFIG_DIR || '').trim();
  return env || path.join(os.homedir(), '.claude');
}

const usagePath = path.join(configDir(), 'squeez', 'buddy', 'lib', 'usage.js');

let getUsage;
try {
  ({ getUsage } = require(usagePath));
} catch {
  process.exit(0);
}

const GREEN = '\x1b[32;1m';
const YELLOW = '\x1b[33;1m';
const RED = '\x1b[31;1m';
const DIM = '\x1b[2m';
const RESET = '\x1b[0m';

function color(pct) {
  if (pct <= 49) return GREEN;
  if (pct <= 79) return YELLOW;
  return RED;
}

function fmt(label, pct) {
  if (pct == null) return '';
  return `${color(pct)}${label} ${pct}%${RESET}`;
}

getUsage((usage) => {
  const parts = [fmt('5h', usage && usage.fiveHour), fmt('7d', usage && usage.sevenDay)].filter(Boolean);
  if (parts.length) process.stdout.write(parts.join(` ${DIM}|${RESET} `));
  process.exit(0);
});
