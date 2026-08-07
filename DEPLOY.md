# Deploy en Render (todo-en-uno, gratis)

## Arquitectura

```
Request → Render Web Service → FastAPI app
                                    |
                                    +→ PostgreSQL (Render, gratis 1GB)
                                    +→ Cloudflare R2 (storage PDFs, gratis 10GB)
                                    +→ OpenAI (extracción IA + OCR)
                                    +→ Mercado Pago (pagos, opcional)
```

## Requisitos
- Cuenta en Render (render.com) - gratis
- Cuenta en Cloudflare (cloudflare.com) - R2 gratis (10GB)
- API key de OpenAI (para extracción IA + OCR)
- (Opcional) Cuenta en Mercado Pago

## Pasos

### 1. Crear bucket en Cloudflare R2
1. Ir a Cloudflare → R2 → Create Bucket → nombre: "pdf-extractor"
2. Crear API Token:
   - Ir a R2 → Manage R2 API Tokens → Create API Token
   - Permisos: Object Read & Write
   - Copiar Access Key ID y Secret Access Key
3. (Opcional) Habilitar acceso público:
   - Ir al bucket → Settings → Public Access → Allow Access
   - Copiar la URL pública (https://pub-xxx.r2.dev)

### 2. Subir a GitHub
```bash
git init
git add .
git commit -m "deploy render"
git remote add origin https://github.com/TU_USUARIO/pdf-extractor.git
git push -u origin main
```

### 3. Deploy en Render
1. Ir a render.com → **New** → **Blueprint**
2. Conectar el repo de GitHub
3. Render detecta `render.yaml` automáticamente:
   - Crea **Web Service** (FastAPI)
   - Crea **PostgreSQL** (gratis, 1GB)
4. Hacer clic en **Apply**

### 4. Configurar variables de entorno
En el Dashboard de Render → pdf-extractor → Environment:

| Variable | Descripción | Ejemplo |
|---|---|---|
| `R2_ENDPOINT_URL` | Endpoint de R2 | `https://xxx.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | Access Key de R2 | `xxx` |
| `R2_SECRET_ACCESS_KEY` | Secret Key de R2 | `xxx` |
| `R2_PUBLIC_URL` | URL pública de R2 (opcional) | `https://pub-xxx.r2.dev` |
| `OPENAI_API_KEY` | API key de OpenAI | `sk-xxx` |
| `INITIAL_ADMIN_EMAIL` | Email del admin | `admin@tu-dominio.com` |
| `INITIAL_ADMIN_PASSWORD` | Password del admin | `tu-password` |
| `MP_ACCESS_TOKEN` | Mercado Pago (opcional) | `APP_USR-xxx` |
| `MP_PUBLIC_KEY` | Mercado Pago (opcional) | `APP_USR-xxx` |

5. Hacer clic en **Save Changes** → Render hace redeploy automático

### 5. Verificar
1. Ir a la URL de tu app: `https://pdf-extractor.onrender.com`
2. Health check: `https://pdf-extractor.onrender.com/health`
3. Login con el admin configurado

## Limitaciones del plan gratis de Render

| Limitación | Detalle | Solución |
|---|---|---|
| **Duerme después de 15min** | Cold start ~30s al despertar | Los usuarios esperan 30s la primera vez |
| **512MB RAM** | Suficiente para PDFs normales | PDFs muy grandes (>50MB) pueden fallar |
| **PostgreSQL: 90 días** | Los datos se borran después de 90 días | Hacer backup periódico o subir a plan pago ($7/mes) |
| **750 horas/mes** | ~31 días, suficiente para 1 web | No alcanza para múltiples servicios |
| **Sin Tesseract** | OCR no disponible localmente | Ya implementado: usa OpenAI Vision API |

## Optimizaciones ya implementadas

1. **PyMuPDF como extractor primario** (3-5x más rápido que pdfplumber)
2. **OCR con OpenAI Vision** (reemplaza Tesseract en producción)
3. **Fallback graceful** (si falla la extracción completa, devuelve parcial)
4. **Tablas con timeout** (si pdfplumber falla, continúa sin tablas)

## Backup de PostgreSQL (importante en free tier)

Render borra la DB después de 90 días. Para hacer backup:

```bash
# Desde tu máquina local (con la DATABASE_URL de Render)
pg_dump $DATABASE_URL > backup_$(date +%Y%m%d).sql

# Para restaurar
psql $DATABASE_URL < backup_20260101.sql
```

## Migrar desde Vercel + Neon

Si ya tenés datos en Neon:
1. Exportar datos de Neon: `pg_dump $NEON_URL > neon_backup.sql`
2. Importar a Render: `psql $RENDER_URL < neon_backup.sql`
3. Los archivos en R2 no cambian (mismo bucket)

## Desarrollo local

```bash
# .env para desarrollo local
DATABASE_URL=sqlite:///./storage/app.db
SECRET_KEY=dev-secret-key
# No configurar R2_* para usar almacenamiento local

# Ejecutar
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Producción con Docker (alternativa a Render)

Si preferís tu propio servidor (Oracle Cloud Free Tier, etc.):
```bash
docker compose -f docker-compose.prod.yml up -d
```
