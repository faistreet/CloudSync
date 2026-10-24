#!/bin/bash
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
echo "=== Instalando CloudSync para Fedora KDE ==="
python3 "$DIR/integration/install_desktop.py"
echo "=== Listo ==="
