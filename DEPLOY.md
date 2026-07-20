# Deploy en Vercel

## Requisitos
- Cuenta en Vercel (vercel.com) - gratis
- Cuenta en Neon (neon.tech) - PostgreSQL gratis
- Cuenta en Cloudflare (cloudflare.com) - R2 gratis (10GB)
- Cuenta en Mercado Pago (mercadopago.com.ar)

## Pasos

### 1. Crear base de datos en Neon
1. Ir a neon.tech -> Create Project
2. Copiar la connection string -> `DATABASE_URL`
3. El formato es: `postgresql://user:pass@host/dbname?sslmode=require`

### 2. Crear bucket en Cloudflare R2
1. Ir a Cloudflare -> R2 -> Create Bucket -> nombre: "pdf-extractor"
2. Crear API Token:
   - Ir a R2 -> Manage R2 API Tokens -> Create API Token
   - Permisos: Object Read & Write
   - Copiar Access Key ID y Secret Access Key
3. (Opcional) Habilitar acceso publico:
   - Ir al bucket -> Settings -> Public Access -> Allow Access
   - Copiar la URL publica (https://pub-xxx.r2.dev)

### 3. Configurar Mercado Pago
1. Ir a mercadopago.com.ar -> Developers -> Your Integrations
2. Crear aplicacion o usar la existente
3. Copiar:
   - Access Token (credenciales de produccion)
   - Public Key
4. Configurar IPN webhook:
   - Ir a Developers -> Webhooks
   - URL: `https://TU_APP.vercel.app/webhook/mercadopago`
   - Eventos: pagos, suscripciones

### 4. Subir a GitHub
```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/TU_USUARIO/pdf-extractor.git
git push -u origin main
```

### 5. Deploy en Vercel
1. Ir a vercel.com -> New Project -> Import Git Repository
2. Seleccionar el repo
3. Framework Preset: Other
4. Root Directory: ./
5. Configurar variables de entorno (Settings -> Environment Variables):

| Variable | Descripcion | Ejemplo |
|----------|-------------|---------|
| `DATABASE_URL` | Connection string de Neon | `postgresql://...` |
| `SECRET_KEY` | Clave secreta para JWT | `una-clave-larga-y-aleatoria` |
| `R2_ENDPOINT_URL` | Endpoint de R2 | `https://xxx.r2.cloudflarestorage.com` |
| `R2_ACCESS_KEY_ID` | Access Key de R2 | `xxx` |
| `R2_SECRET_ACCESS_KEY` | Secret Key de R2 | `xxx` |
| `R2_BUCKET_NAME` | Nombre del bucket | `pdf-extractor` |
| `R2_PUBLIC_URL` | URL publica de R2 (opcional) | `https://pub-xxx.r2.dev` |
| `MP_ACCESS_TOKEN` | Access Token de MP | `APP_USR-xxx` |
| `MP_PUBLIC_KEY` | Public Key de MP | `APP_USR-xxx` |
| `MP_WEBHOOK_SECRET` | Secret del webhook (opcional) | `xxx` |
| `OPENAI_API_KEY` | API key de OpenAI (opcional) | `sk-xxx` |
| `APP_URL` | URL de la app en Vercel | `https://tu-app.vercel.app` |

6. Deploy

### 6. Ejecutar migraciones
Despues del primer deploy, ejecutar las migraciones de Alembic:
```bash
# Desde la terminal, con la DATABASE_URL configurada
alembic upgrade head
```

O crear las tablas automaticamente (el init_db() en main.py lo hace al arrancar).

### 7. Configurar dominio (opcional)
En Vercel -> Settings -> Domains -> Add Domain

## Limitaciones de Vercel
- **Timeout**: 10s en plan gratuito, 50s en Pro ($20/mes)
- **Sin Celery**: procesamiento de PDFs es sincrono
- **Cold starts**: la primera request puede tardar mas
- **PDFs grandes**: pueden exceder el timeout; considerar Vercel Pro
- **OCR (Tesseract)**: no disponible en Vercel; los PDFs escaneados no tendran OCR

## Desarrollo local

Para desarrollo local, el sistema cae automaticamente en:
- **SQLite**: si `DATABASE_URL` no esta configurada o empieza con `sqlite://`
- **Almacenamiento local**: si `R2_ACCESS_KEY_ID` no esta configurada
- **Sin Celery**: si `CELERY_BROKER_URL` no esta configurada

```bash
# .env para desarrollo local
DATABASE_URL=sqlite:///./storage/app.db
SECRET_KEY=dev-secret-key
# No configurar R2_* ni MP_* para usar almacenamiento local y sin pagos
```

```bash
# Instalar dependencias
pip install -r requirements.txt

# Ejecutar
uvicorn app.main:app --reload
```

## Arquitectura en Vercel

```
Request -> Vercel Edge -> api/index.py -> FastAPI app
                                           |
                                           +-> Neon PostgreSQL (datos)
                                           +-> Cloudflare R2 (archivos PDF)
                                           +-> Mercado Pago (pagos)
                                           +-> OpenAI (extraccion LLM, opcional)
```
