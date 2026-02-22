#!/bin/bash
# Build the cprm .deb package locally
# Requires: dpkg-deb (install with: sudo apt install dpkg)
#
# Usage: ./build-deb.sh
# Output: cprm_<version>_all.deb in current directory

set -e

# Extract version from package
VERSION=$(python3 -c "import re; m = re.search(r\"__version__ = '(.+)'\", open('cprm/__init__.py').read()); print(m.group(1))")
PKG="cprm_${VERSION}_all"

echo "Building ${PKG}.deb..."

# Clean previous build
rm -rf "${PKG}" "${PKG}.deb"

# Directory structure
mkdir -p "${PKG}/DEBIAN"
mkdir -p "${PKG}/usr/bin"
mkdir -p "${PKG}/usr/lib/cprm"
mkdir -p "${PKG}/etc/profile.d"

# DEBIAN/control
cat > "${PKG}/DEBIAN/control" <<EOF
Package: cprm
Version: ${VERSION}
Architecture: all
Maintainer: Carlos Andrade <carlos@perezandrade.com>
Depends: python3 (>= 3.6)
Description: Enhanced cp/rm with unified progress bar
 A lightweight wrapper for cp and rm commands that adds a beautiful
 progress bar to terminal file operations.
EOF

# Copy Python package
cp -r cprm/. "${PKG}/usr/lib/cprm/"

# /usr/bin/cprm wrapper
cat > "${PKG}/usr/bin/cprm" <<'EOF'
#!/usr/bin/env python3
import sys
sys.path.insert(0, '/usr/lib')
from cprm.core import main
if __name__ == '__main__':
    main()
EOF
chmod 755 "${PKG}/usr/bin/cprm"

# /etc/profile.d/cprm.sh — aliases loaded automatically for bash login shells
cat > "${PKG}/etc/profile.d/cprm.sh" <<'EOF'
# cprm aliases — Enhanced cp/rm with progress bars
alias cpo='/bin/cp'
alias rmo='/bin/rm'
alias cp='cprm cp'
alias rm='cprm rm'
EOF

# DEBIAN/postinst
cat > "${PKG}/DEBIAN/postinst" <<'EOF'
#!/bin/bash
set -e
echo ""
echo "✅ cprm installed successfully!"
echo ""
echo "Aliases are auto-loaded for bash login shells via /etc/profile.d/cprm.sh"
echo ""
echo "For zsh, add these lines to ~/.zshrc:"
echo "  alias cpo='/bin/cp'"
echo "  alias rmo='/bin/rm'"
echo "  alias cp='cprm cp'"
echo "  alias rm='cprm rm'"
echo ""
echo "Then reload: source ~/.zshrc"
EOF
chmod 755 "${PKG}/DEBIAN/postinst"

# Build .deb
dpkg-deb --build --root-owner-group "${PKG}"

echo ""
echo "Done: ${PKG}.deb"
ls -lh "${PKG}.deb"
