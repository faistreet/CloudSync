#!/usr/bin/env bash
set -e

# Directorios de trabajo
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/.." >/dev/null 2>&1 && pwd )"
BUILD_DIR="$PROJECT_ROOT/build/rpmbuild"
DIST_DIR="$PROJECT_ROOT/dist"

VERSION="${1:-1.0.0}"
VERSION="${VERSION#v}" # Quita la 'v' inicial si viene de un git tag (ej. v1.0.0 -> 1.0.0)

echo "=== Construyendo paquete RPM para CloudSync v${VERSION} ==="

if ! command -v rpmbuild &> /dev/null; then
    echo "ERROR: 'rpmbuild' no está instalado."
    exit 1
fi

# Limpiar y preparar estructura de rpmbuild
rm -rf "$BUILD_DIR"
mkdir -p "$BUILD_DIR"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
mkdir -p "$DIST_DIR"

# Preparar el directorio de fuentes esperado por rpmbuild
SRC_STAGE="$BUILD_DIR/BUILD/cloudsync-$VERSION"
mkdir -p "$SRC_STAGE"
cp -a "$PROJECT_ROOT"/main.py \
      "$PROJECT_ROOT"/cloudsync_cli.py \
      "$PROJECT_ROOT"/core \
      "$PROJECT_ROOT"/gui \
      "$PROJECT_ROOT"/assets \
      "$PROJECT_ROOT"/integration \
      "$SRC_STAGE"/

cd "$PROJECT_ROOT"

# Ejecutar rpmbuild
echo "-> Ejecutando rpmbuild..."
rpmbuild -bb \
    --define "_topdir $BUILD_DIR" \
    --define "version $VERSION" \
    "$SCRIPT_DIR/cloudsync.spec"

# Mover RPM generado a dist/
echo "-> Copiando paquetes generados a $DIST_DIR..."
find "$BUILD_DIR/RPMS" -name "*.rpm" -exec cp -v {} "$DIST_DIR/" \;

echo "=== ¡Construcción exitosa! ==="
echo "Los paquetes RPM se encuentran en:"
ls -lh "$DIST_DIR"/*.rpm
