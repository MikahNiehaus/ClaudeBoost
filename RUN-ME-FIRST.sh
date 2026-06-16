#!/usr/bin/env bash
# Deprecated — replaced by install.sh
echo ""
echo " This script has been replaced by install.sh"
echo " Starting install.sh..."
echo ""
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/install.sh" "$@"
