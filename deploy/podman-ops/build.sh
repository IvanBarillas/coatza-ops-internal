#!/usr/bin/env bash
# Construye la imagen del Core con los satélites, en el host donde se ejecuta (podman rootless).
#
#   deploy/podman-ops/build.sh [etiqueta]        (por defecto: dev)
#
# Requiere los cuatro repositorios clonados como hermanos (o indicados por variable) y usa
# `git archive`, es decir SOLO archivos versionados de la referencia pedida: ningún .env,
# .venv ni base local puede colarse en la imagen.
#
#   AXENTRA_SRC_BASE   carpeta que contiene los clones            (por defecto: ~/axentra)
#   REF_CORE / REF_TRAMITES / REF_SITUACIONES / REF_CIUDADANIA     (por defecto: main)
set -euo pipefail

TAG="${1:-dev}"
BASE="${AXENTRA_SRC_BASE:-$HOME/axentra}"
IMAGEN="localhost/axentra-core"

declare -A DIR=(
  [core]="${DIR_CORE:-$BASE/axentra-core-django}"
  [tramites]="${DIR_TRAMITES:-$BASE/axentra-mod-tramites}"
  [situaciones]="${DIR_SITUACIONES:-$BASE/axentra-mod-situaciones-de-vida}"
  [ciudadania]="${DIR_CIUDADANIA:-$BASE/ciudadania}"
)
declare -A REF=(
  [core]="${REF_CORE:-main}" [tramites]="${REF_TRAMITES:-main}"
  [situaciones]="${REF_SITUACIONES:-main}" [ciudadania]="${REF_CIUDADANIA:-main}"
)

CONTEXTO="$(mktemp -d)"
trap 'rm -rf "$CONTEXTO"' EXIT

versiones=()
for nombre in core tramites situaciones ciudadania; do
  [ -d "${DIR[$nombre]}/.git" ] || { echo "No existe el clon de $nombre: ${DIR[$nombre]}" >&2; exit 1; }
  sha="$(git -C "${DIR[$nombre]}" rev-parse --short "${REF[$nombre]}")"
  mkdir -p "$CONTEXTO/$nombre"
  git -C "${DIR[$nombre]}" archive --format=tar "${REF[$nombre]}" | tar -x -C "$CONTEXTO/$nombre"
  versiones+=("$nombre=${REF[$nombre]}@$sha")
  echo ">> $nombre: ${REF[$nombre]} ($sha)"
done

podman build \
  --file "$CONTEXTO/core/deploy/podman-ops/Containerfile" \
  --build-context tramites="$CONTEXTO/tramites" \
  --build-context situaciones="$CONTEXTO/situaciones" \
  --build-context ciudadania="$CONTEXTO/ciudadania" \
  --label "org.opencontainers.image.title=axentra-core+satelites" \
  --label "mx.axentra.versiones=${versiones[*]}" \
  --tag "$IMAGEN:$TAG" \
  "$CONTEXTO/core"

echo "Imagen lista: $IMAGEN:$TAG  (${versiones[*]})"
