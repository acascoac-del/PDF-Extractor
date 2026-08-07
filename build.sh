#!/usr/bin/env bash
# Build script para Render
set -o errexit

echo "==> Instalando dependencias de Python..."
pip install --upgrade pip
pip install -r requirements.txt

echo "==> Ejecutando migraciones de base de datos..."
alembic upgrade head

echo "==> Build completado."
