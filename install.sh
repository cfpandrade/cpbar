#!/bin/bash
# Installation script for cpbar
# Author: Carlos Andrade <carlos@perezandrade.com>

set -e

INSTALL_DIR="$HOME/.local/bin"
LIB_DIR="$HOME/.local/lib"
SCRIPT_NAME="cpbar"

echo "🚀 Installing cpbar..."

# Create install directories if they don't exist
mkdir -p "$INSTALL_DIR"
mkdir -p "$LIB_DIR"

# Clean up any existing installation to avoid conflicts
if [ -e "$INSTALL_DIR/$SCRIPT_NAME" ]; then
    echo "   🧹 Removing previous installation..."
    command rm -rf "$INSTALL_DIR/$SCRIPT_NAME"
fi
if [ -d "$INSTALL_DIR/cpbar" ]; then
    command rm -rf "$INSTALL_DIR/cpbar"
fi
if [ -d "$LIB_DIR/cpbar" ]; then
    command rm -rf "$LIB_DIR/cpbar"
fi

# Copy the entire project to lib directory
echo "   📦 Installing cpbar package..."
mkdir -p "$LIB_DIR/cpbar"
if [ -d "cpbar" ]; then
    command cp -r cpbar/* "$LIB_DIR/cpbar/"
else
    echo "   ⚠️  Warning: cpbar package directory not found"
    exit 1
fi
echo "   ✅ Package installed to $LIB_DIR/cpbar/"

# Create wrapper script in bin
cat > "$INSTALL_DIR/$SCRIPT_NAME" << 'EOF'
#!/usr/bin/env python3
import sys
import os

# Add the library path to Python's module search path
lib_path = os.path.join(os.path.expanduser('~'), '.local', 'lib')
sys.path.insert(0, lib_path)

# Import and run the main module
from cpbar.core import main

if __name__ == '__main__':
    main()
EOF

command chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "✅ Script installed to $INSTALL_DIR/$SCRIPT_NAME"

# Alias block to add
ALIAS_BLOCK='
# cpbar aliases - Enhanced cp/rm with progress bars
# Original commands (use these to bypass progress bars)
alias cpo="cp"
alias rmo="rm"
# Replace cp/rm with enhanced versions
alias cp="cpbar cp"
alias rm="cpbar rm"
'

PATH_EXPORT='export PATH="$HOME/.local/bin:$PATH"'

# Function to configure a shell rc file
configure_rc_file() {
    local rc_file="$1"
    local shell_name="$2"
    
    if [ ! -f "$rc_file" ]; then
        return 1
    fi
    
    echo ""
    echo "📝 Configuring $shell_name ($rc_file)..."
    
    # Check if PATH includes install dir
    if ! grep -q '.local/bin' "$rc_file" 2>/dev/null; then
        echo "" >> "$rc_file"
        echo "# Added by cpbar installer" >> "$rc_file"
        echo "$PATH_EXPORT" >> "$rc_file"
        echo "   ✅ PATH added"
    else
        echo "   ℹ️  PATH already configured"
    fi
    
    # Check if aliases already exist
    if ! grep -q "cpbar aliases" "$rc_file" 2>/dev/null; then
        echo "$ALIAS_BLOCK" >> "$rc_file"
        echo "   ✅ Aliases added"
    else
        echo "   ℹ️  Aliases already exist"
    fi
    
    return 0
}

# Configure all available shell rc files
CONFIGURED_SHELLS=""

# Always try zsh first
if [ -f "$HOME/.zshrc" ]; then
    configure_rc_file "$HOME/.zshrc" "zsh"
    CONFIGURED_SHELLS="$HOME/.zshrc"
fi

# Also configure bash if it exists
if [ -f "$HOME/.bashrc" ]; then
    configure_rc_file "$HOME/.bashrc" "bash"
    if [ -n "$CONFIGURED_SHELLS" ]; then
        CONFIGURED_SHELLS="$CONFIGURED_SHELLS, $HOME/.bashrc"
    else
        CONFIGURED_SHELLS="$HOME/.bashrc"
    fi
fi

# If neither exists, create .zshrc
if [ -z "$CONFIGURED_SHELLS" ]; then
    echo ""
    echo "📝 No .zshrc or .bashrc found, creating .zshrc..."
    touch "$HOME/.zshrc"
    configure_rc_file "$HOME/.zshrc" "zsh"
    CONFIGURED_SHELLS="$HOME/.zshrc"
fi

# Detect current shell for reload instructions
CURRENT_SHELL=$(basename "$SHELL")
if [ "$CURRENT_SHELL" = "zsh" ]; then
    RELOAD_CMD="source ~/.zshrc"
elif [ "$CURRENT_SHELL" = "bash" ]; then
    RELOAD_CMD="source ~/.bashrc"
else
    RELOAD_CMD="source ~/.zshrc  # or ~/.bashrc"
fi

echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✨ Installation complete!"
echo ""
echo "Configured files: $CONFIGURED_SHELLS"
echo ""

# Ask if user wants to run benchmark
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "🔬 Optimize parallel copy performance?"
echo ""
echo "  The benchmark will test your system to determine the optimal"
echo "  number of parallel workers for fast file copying (takes ~30s)."
echo ""
printf "  Run benchmark now? [Y/n]: "
read -r RUN_BENCHMARK

if [ -z "$RUN_BENCHMARK" ] || [ "$RUN_BENCHMARK" = "y" ] || [ "$RUN_BENCHMARK" = "Y" ]; then
    echo ""
    "$INSTALL_DIR/$SCRIPT_NAME" benchmark
    echo ""
else
    echo "  ℹ️  Skipped. You can run it later with: cpbar benchmark"
    echo ""
fi

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "To activate changes, run:"
echo "  $RELOAD_CMD"
echo ""
echo "Usage:"
echo "  cp file.txt /destination/          # Copy with progress bar"
echo "  cp -r folder/ /destination/        # Copy folder with progress"
echo "  cp -n file.txt /destination/       # Dry-run: preview without copying"
echo "  cp -P large.iso /backup/           # Parallel copy (uses benchmark result)"
echo ""
echo "  rm file.txt                        # Delete with confirmation + progress"
echo "  rm -r folder/                      # Delete folder with progress"
echo "  rm -rf folder/                     # Delete without confirmation"
echo "  rm -n folder/                      # Dry-run: preview without deleting"
echo ""
echo "Advanced options:"
echo "  -P, --parallel=N  Use N workers for large files"
echo "  -n, --dry-run     Preview operations before executing"
echo "  cpbar benchmark    Detect optimal parallel workers for your system"
echo ""
echo "Original commands (no progress bar):"
echo "  cpo file.txt /destination/         # Original cp"
echo "  rmo file.txt                       # Original rm"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"