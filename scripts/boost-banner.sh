#!/usr/bin/env bash
# ClaudeBoost retro system boot screen

C='\033[36m'        # Cyan
G='\033[32;1m'      # Bright green bold
A='\033[33;1m'      # Amber bold
W='\033[37;1m'      # White bold
D='\033[2m'         # Dim
R='\033[0m'         # Reset
OK='\033[32;1m[  OK  ]\033[0m'

echo ""
echo -e "${C}══════════════════════════════════════════════════════${R}"
echo -e "${G}  ▄▀▀ █   ▄▀▄ █ █ █▀▄ █▀▀ ${A} ██▄ ▄▀▄ ▄▀▄ ▄▀▀ ▀█▀${R}"
echo -e "${G}  ▀▄▄ █▄▄ █▀█ ▀▄▀ █▄▀ █▄▄ ${A} █▄█ ▀▄▀ ▀▄▀ ▄▄▀  █ ${R}"
echo -e "${C}══════════════════════════════════════════════════════${R}"
echo -e "${D}  SYSTEM INIT v2.1${R}"
echo -e "${C}──────────────────────────────────────────────────────${R}"
echo -e "  ${W}KNOWLEDGE BASE${R} ${D}....${R} 36 files ${D}..${R} 392 chunks ${D}..${R} ${OK}"
echo -e "  ${W}AGENT POOL${R}     ${D}....${R} 21 specialists loaded ${D}..${R} ${OK}"
echo -e "  ${W}RAG ENGINE${R}     ${D}....${R} semantic index ready ${D}..${R} ${OK}"
echo -e "  ${W}RULES ENGINE${R}   ${D}....${R} verify gate active ${D}...${R} ${OK}"
echo -e "${C}──────────────────────────────────────────────────────${R}"
echo -e "  ${G}STATUS: ONLINE${R}  ${D}│${R}  ${A}AGENTS: 21${R}  ${D}│${R}  ${C}KB: 36${R}  ${D}│${R}  ${G}RAG: ACTIVE${R}"
echo -e "${C}══════════════════════════════════════════════════════${R}"
echo ""
