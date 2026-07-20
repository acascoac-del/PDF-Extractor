# PDF Extractor

Convierte PDFs (facturas, remitos, presupuestos, contratos, informes, tablas)
a Excel (.xlsx) y Word (.docx) con **extracción inteligente y estructurada**:
no vuelca texto crudo, sino datos limpios listos para usar.

> Estado: en desarrollo. Caso prioritario = **factura AFIP (A/B/C)**.

## Características (plan)

- Carga múltiple con drag & drop — nativos y escaneados (OCR con Tesseract `spa+eng`).
- Clasificación automática del tipo de documento (reglas + LLM), confirmable por el usuario.
- Extracción de factura: CUIT/CUIL, CAE, tipo A/B/C, razón social, condición IVA,
  fecha, ítems (descripción/cantidad/PU/subtotal), impuestos, total, forma de pago.
- Exportación a `.xlsx` (detalle + hoja consolidada), `.docx`, `.csv`, `.json`, `.zip`.
- Vista previa lado a lado con edición inline y badge de confianza (verde/amarillo/rojo).
- Multiusuario con roles (admin/user) y tokens de API.
- Cola asíncrona con Celery + Redis.
- Historial con filtros y re-descarga.
- Borrado automático programable (Cumplimiento de datos).

## Stack

- **Backend**: FastAPI + SQLAlchemy 2 + Alembic + Celery + Redis.
- **PDF**: pdfplumber + PyMuPDF + pymupdf4llm + pytesseract.
- **Export**: openpyxl + python-docx.
- **IA**: LLM OpenAI-compatible (OpenAI, OpenRouter, Ollama, Groq…).
- **Frontend**: Jinja2 + HTMX + Tailwind.

## Arranque rápido (Docker)

```bash
cp .env.example .env
# Editar .env: SECRET_KEY, OPENAI_API_KEY, OPENAI_BASE_URL, LLM_MODEL
docker compose up --build
# → Web: http://localhost:8000   Docs: http://localhost:8000/docs
```

## Arranque local (sin Docker)

```bash
python -m venv .venv
source .venv/Scripts/activate   # Git Bash en Windows
pip install -r requirements.txt

# Requiere Redis corriendo (para Celery): docker run -p 6379:6379 redis:7-alpine
uvicorn app.main:app --reload
```

> En Windows, si Tesseract no está en el PATH, setear en `.env`:
> `TESSERACT_CMD=C:\Program Files\Tesseract-OCR\tesseract.exe`

## Configuración (variables clave)

| Variable            | Descripción                                       | Default                          |
| ------------------- | ------------------------------------------------- | -------------------------------- |
| `SECRET_KEY`        | Clave JWT (cambiar en prod)                       | — (generar una larga)            |
| `DATABASE_URL`      | SQLAlchemy URL                                    | `sqlite:///./storage/app.db`     |
| `OPENAI_BASE_URL`   | Endpoint del LLM                                  | `https://api.openai.com/v1`      |
| `OPENAI_API_KEY`    | Clave del LLM                                     | —                                |
| `LLM_MODEL`         | Modelo a usar                                     | `gpt-4o-mini`                    |
| `OCR_LANGUAGES`     | Lenguajes Tesseract                               | `spa+eng`                        |
| `AUTO_DELETE_DAYS`  | Días para borrado automático (0 = desactivado)    | `30`                             |

## API REST

Una vez levanto, ver `/docs` para el spec OpenAI interactivo.
Autenticación con header `Authorization: Bearer <api_token>` (tokens creados
desde la UI) o JWT.

## Licencia

Privado — © Chevi.
