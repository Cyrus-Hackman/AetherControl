#!/usr/bin/env bash
# AetherControl Desktop Server - Installation Script
# Tested on Deepin OS 23/25, Ubuntu 22.04+
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$HOME/.local/share/aethercontrol/venv"
BIN_DIR="$HOME/.local/bin"
DESKTOP_DIR="$HOME/.local/share/applications"

echo "═══════════════════════════════════════════════════"
echo "  AetherControl Desktop Server - Installer"
echo "═══════════════════════════════════════════════════"
echo ""

# Check Python version
PYTHON=$(which python3 || which python)
PY_VERSION=$($PYTHON --version 2>&1 | awk '{print $2}')
echo "✓ Python: $PY_VERSION"

# Check for uinput access
echo ""
echo "Checking uinput access..."
if [ -w /dev/uinput ]; then
    echo "✓ /dev/uinput is accessible"
elif groups | grep -q "input"; then
    echo "✓ User is in 'input' group"
else
    echo "⚠ /dev/uinput not accessible. Installing udev rule..."
    cat > /tmp/99-aethercontrol.rules << 'EOF'
# AetherControl - allow input group to access uinput
KERNEL=="uinput", MODE="0660", GROUP="input", OPTIONS+="static_node=uinput"
EOF
    sudo install -m 644 /tmp/99-aethercontrol.rules /etc/udev/rules.d/
    sudo udevadm control --reload-rules
    sudo udevadm trigger
    sudo usermod -aG input "$USER"
    echo "✓ udev rule installed. You will need to LOG OUT and back in for group membership to take effect."
fi

# Create virtual environment
echo ""
echo "Creating Python virtual environment..."
$PYTHON -m venv --system-site-packages "$VENV_DIR"
source "$VENV_DIR/bin/activate"
pip install --upgrade pip --quiet

# Install dependencies
echo "Installing dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" --quiet

# Optional Wayland support
if command -v pipewire &> /dev/null; then
    echo "PipeWire detected — installing Wayland capture support..."
    pip install pipewire-capture --quiet || echo "  (pipewire-capture not available; Wayland capture may be limited)"
fi

# Optional D-Bus (media control)
echo "Checking D-Bus..."
pip install dbus-python --quiet || echo "  (dbus-python not installed; using pactl fallback for volume control)"

# Install package
echo "Installing aether-server package..."
pip install -e "$SCRIPT_DIR" --quiet

# Create launcher script
mkdir -p "$BIN_DIR"
cat > "$BIN_DIR/aethercontrol" << EOF
#!/bin/bash
source "$VENV_DIR/bin/activate"
exec python -m aether_server.main "\$@"
EOF
chmod +x "$BIN_DIR/aethercontrol"
echo "✓ Launcher installed: $BIN_DIR/aethercontrol"

# Create desktop entry
mkdir -p "$DESKTOP_DIR"
cat > "$DESKTOP_DIR/aethercontrol.desktop" << EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=AetherControl
GenericName=Remote Control Server
Comment=Android-to-Deepin remote control server
Exec=$BIN_DIR/aethercontrol
Icon=network-wireless
Terminal=false
Categories=Network;RemoteAccess;
Keywords=remote;control;android;phone;tablet;
StartupNotify=true
EOF
update-desktop-database "$DESKTOP_DIR" 2>/dev/null || true
echo "✓ Desktop entry installed"

echo ""
echo "═══════════════════════════════════════════════════"
echo "  Installation complete!"
echo ""
echo "  Start server: aethercontrol"
echo "  Or find it in your application menu."
echo ""
echo "  IMPORTANT: If uinput access was just configured,"
echo "  you must LOG OUT and back in before mouse/keyboard"
echo "  control will work."
echo "═══════════════════════════════════════════════════"
