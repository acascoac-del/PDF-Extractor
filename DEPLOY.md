# Deploy en Railway.app

## Requisitos
- Cuenta en Railway.app (gratis)
- Cuenta en Stripe (para pagos)
- Repo en GitHub

## Pasos

### 1. Subir codigo a GitHub

```bash
git init
git add .
git commit -m "initial"
git remote add origin https://github.com/TU_USUARIO/pdf-extractor.git
git push -u origin main
```

### 2. Crear proyecto en Railway

1. Ir a railway.app -> New Project -> Deploy from GitHub Repo
2. Seleccionar el repo
3. Railway detecta el Dockerfile automaticamente

### 3. Agregar Redis

1. En Railway -> New -> Database -> Redis
2. Railway crea Redis y setea `REDIS_URL` automaticamente

### 4. Configurar variables de entorno

En Railway -> Variables:

```
SECRET_KEY=una-clave-larga-y-aleatoria
DATABASE_URL=sqlite:///./storage/app.db
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_API_KEY=sk-xxx (opcional)
LLM_MODEL=gpt-4o-mini
STRIPE_SECRET_KEY=sk_test_xxx
STRIPE_PUBLISHABLE_KEY=pk_test_xxx
STRIPE_PRICE_ID=price_xxx
STRIPE_WEBHOOK_SECRET=whsec_xxx
```

### 5. Configurar Stripe

1. Crear cuenta en stripe.com
2. Crear producto "PDF Extractor Pro" con precio $5/mes recurrente
3. Copiar Price ID -> `STRIPE_PRICE_ID`
4. Crear webhook endpoint: `https://TU_APP.up.railway.app/webhook/stripe`
5. Seleccionar eventos:
   - `checkout.session.completed`
   - `customer.subscription.updated`
   - `customer.subscription.deleted`
6. Copiar webhook secret -> `STRIPE_WEBHOOK_SECRET`

### 6. Ejecutar migraciones

Railway ejecuta el Dockerfile. Agrega un paso de build o un script de arranque
que corra las migraciones antes de iniciar el servidor:

```bash
alembic upgrade head
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

### 7. Deploy

Railway deploya automaticamente al hacer push.

### 8. Dominio custom (opcional)

En Railway -> Settings -> Domains -> Generate Domain
O agregar tu propio dominio.

---

## Alternativas gratuitas

### Render.com
- Free tier con Redis
- Spindea down despues de 15min de inactividad
- Deploy desde GitHub

### Fly.io
- Free tier con 3 VMs compartidas
- Mas configuracion pero siempre activo

### Oracle Cloud Free Tier
- VM ARM siempre gratis (4 cores, 24GB RAM)
- Deploy manual con Docker
