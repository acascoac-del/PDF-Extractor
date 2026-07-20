# =========================================================
#  PDF Extractor — imagen de la app (web / worker / beat)
# =========================================================
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=America/Argentina/Buenos_Aires

# Dependencias del sistema: Tesseract OCR + idiomas + libjpeg/png/zlib para Pillow/PyMuPDF
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr \
        tesseract-ocr-spa \
        tesseract-ocr-eng \
        libjpeg62-turbo \
        libpng-dev \
        zlib1g \
        libglib2.0-0 \
        libgl1 \
        curl \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias primero (mejor cache de capas)
COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

# Código de la aplicación
COPY . .

# Directorio de almacenamiento
RUN mkdir -p /app/storage/uploads /app/storage/processed /app/storage/exports

EXPOSE 8000

# Por defecto arranca la web; el compose sobreescribe el comando para worker/beat
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
