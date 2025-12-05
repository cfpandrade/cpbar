#!/bin/bash
# Installation script for cprm

set -e

INSTALL_DIR="$HOME/.local/bin"
SCRIPT_NAME="cprm"

echo "🚀 Installing cprm..."

# Create install directory if it doesn't exist
mkdir -p "$INSTALL_DIR"

# Copy the script (use command to bypass any aliases)
command cp -f cprm.py "$INSTALL_DIR/$SCRIPT_NAME"
command chmod +x "$INSTALL_DIR/$SCRIPT_NAME"

echo "✅ Script installed to $INSTALL_DIR/$SCRIPT_NAME"

# Alias block to add
ALIAS_BLOCK='
# cprm aliases - Enhanced cp/rm with progress bars
# Original commands (use these to bypass progress bars)
alias cpo="cp"
alias rmo="rm"
# Replace cp/rm with enhanced versions
alias cp="cprm cp"
alias rm="cprm rm"
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
        echo "# Added by cprm installer" >> "$rc_file"
        echo "$PATH_EXPORT" >> "$rc_file"
        echo "   ✅ PATH added"
    else
        echo "   ℹ️  PATH already configured"
    fi
    
    # Check if aliases already exist
    if ! grep -q "cprm aliases" "$rc_file" 2>/dev/null; then
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
    echo "  ℹ️  Skipped. You can run it later with: cprm benchmark"
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
echo "  cprm benchmark    Detect optimal parallel workers for your system"
echo ""
echo "Original commands (no progress bar):"
echo "  cpo file.txt /destination/         # Original cp"
echo "  rmo file.txt                       # Original rm"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"