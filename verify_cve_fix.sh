#!/bin/sh
# Verification script to check CVE-2025-60876 fix
# This script verifies that GNU wget is installed instead of BusyBox wget

set -e

echo "=== Verifying CVE-2025-60876 Fix ==="
echo ""

# Check wget binary location
echo "1. Checking wget binary location:"
WGET_PATH=$(which wget)
echo "   wget is located at: $WGET_PATH"
echo ""

# Check wget version
echo "2. Checking wget version:"
WGET_VERSION=$(wget --version 2>&1 | head -1)
echo "   $WGET_VERSION"
echo ""

# Verify it's GNU wget, not BusyBox wget
if echo "$WGET_VERSION" | grep -q "GNU Wget"; then
    echo "✓ SUCCESS: GNU wget is installed (not vulnerable to CVE-2025-60876)"
    echo ""
    echo "GNU wget is not affected by CVE-2025-60876, which only affects BusyBox wget."
    exit 0
elif echo "$WGET_VERSION" | grep -q "BusyBox"; then
    echo "✗ FAILURE: BusyBox wget is still in use (vulnerable to CVE-2025-60876)"
    echo ""
    echo "BusyBox wget through version 1.37.0 is vulnerable to CVE-2025-60876."
    echo "Please ensure GNU wget is installed to replace BusyBox wget."
    exit 1
else
    echo "⚠ WARNING: Could not determine wget implementation"
    echo ""
    echo "Full version output:"
    wget --version 2>&1
    exit 1
fi
