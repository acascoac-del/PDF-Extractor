#!/bin/bash
# =============================================================
#  PDF Extractor — Setup automatizado para Oracle Cloud Free Tier
#  Ejecutar como root: sudo ./setup_oracle.sh
# =============================================================
set -e

echo "=========================================="
echo "  PDF Extractor — Setup Oracle Cloud"
echo "=========================================="

# 1. Actualizar sistema
echo "[1/6] Actualizando sistema..."
apt-get update -y && apt-get upgrade -y

# 2. Instalar Docker
echo "[2/6] Instalando Docker..."
apt-get install -y ca-certificates curl gnupg
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null
apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

# 3. Habilitar Docker
echo "[3/6] Habilitando Docker..."
systemctl enable docker
systemctl start docker

# 4. Instalar Tesseract OCR (spa + eng)
echo "[4/6] Instalando Tesseract OCR..."
apt-get install -y tesseract-ocr tesseract-ocr-spa tesseract-ocr-eng

# 5. Crear directorios
echo "[5/6] Creando directorios..."
mkdir -p /opt/pdf-extractor/storage/{uploads,processed,exports}
mkdir -p /opt/pdf-extractor/nginx

# 6. Generar SECRET_KEY
echo "[6/6] Generando SECRET_KEY..."
SECRET_KEY=$(openssl rand -hex 32)
echo "SECRET_KEY generada: $SECRET_KEY"
echo "Guardala en .env"

echo ""
echo "=========================================="
echo "  Setup completado!"
echo "=========================================="
echo ""
echo "Próximos pasos:"
echo "1. Copiar el código a /opt/pdf-extractor/"
echo "2. cp /opt/pdf-extractor/.env.example /opt/pdf-extractor/.env"
echo "3. Editar /opt/pdf-extractor/.env con:"
echo "   SECRET_KEY=$SECRET_KEY"
echo "   DATABASE_URL=postgresql://pdfuser:PASSWORD@db:5432/pdf_extractor"
echo "   CELERY_BROKER_URL=redis://redis:6379/0"
echo "   CELERY_RESULT_BACKEND=redis://redis:6379/1"
echo "4. cd /opt/pdf-extractor && docker compose -f docker-compose.prod.yml up -d --build"
echo ""
echo "La app estará en http://IP_PUBLICA:8000"
echo "Para SSL: sudo certbot --nginx -d tudominio.com"
