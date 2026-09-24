#!/usr/bin/env bash
# Construye la imagen de las apps internas: base (Dockerfile de la raíz) + capa de OCR.
#   deploy/oficios/build.sh [etiqueta]      (por defecto: latest)
set -euo pipefail

TAG="${1:-latest}"
RAIZ="$(git -C "$(dirname "$0")" rev-parse --show-toplevel)"
IMAGEN="localhost/axentra-ops-internal"

podman build -t "$IMAGEN:base" "$RAIZ"
podman build -f "$RAIZ/deploy/oficios/Containerfile" --build-arg "BASE=$IMAGEN:base" -t "$IMAGEN:$TAG" "$RAIZ"
echo "Imagen lista: $IMAGEN:$TAG"
