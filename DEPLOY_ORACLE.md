# Deploy en Oracle Cloud Free Tier

VM ARM siempre gratis: 4 cores, 24GB RAM, 200GB storage, 10TB bandwidth.

## 1. Crear cuenta en Oracle Cloud

1. Ir a **cloud.oracle.com** → Create Account
2. Necesitás tarjeta de crédito (no cobra nada)
3. Elegir región: **São Paulo** o **Santiago** (más cercana a Argentina)

## 2. Crear la VM

1. Dashboard → **Compute** → **Instances** → **Create Instance**
2. Configuración:
   - **Name**: `pdf-extractor`
   - **Image**: `Canonical Ubuntu 24.04 Minimal aarch64`
   - **Shape**: `VM.Standard.A1.Flex` (ARM, siempre gratis)
   - **CPUs**: `4` (máximo gratis)
   - **Memory**: `24` GB (máximo gratis)
   - **Boot volume**: `100` GB
3. **Networking**: Crear VCN nueva (o usar la existente)
4. **SSH Keys**: Descargar la clave privada (`ssh-key-2026-XX-XX.key`)
5. Click **Create**

## 3. Configurar Security List

1. **Networking** → **Virtual Cloud Networks** → tu VCN → **Security Lists** → Default
2. **Add Ingress Rules**:
   - Puerto `80` (HTTP): Source `0.0.0.0/0`
   - Puerto `443` (HTTPS): Source `0.0.0.0/0`
   - Puerto `22` (SSH): ya debería estar

## 4. Conectar por SSH

```bash
# Desde tu máquina local
chmod 400 ssh-key-2026-XX-XX.key
ssh -i ssh-key-2026-XX-XX.key ubuntu@IP_PUBLICA
```

## 5. Ejecutar el script de setup

```bash
# En la VM, descargar y ejecutar el script
curl -O https://raw.githubusercontent.com/TU_USUARIO/pdf-extractor/main/setup_oracle.sh
chmod +x setup_oracle.sh
sudo ./setup_oracle.sh
```

O copiar el script manualmente y ejecutarlo.

## 6. Subir el código

```bash
# Desde tu máquina local
scp -i ssh-key-2026-XX-XX.key -r . ubuntu@IP_PUBLICA:/opt/pdf-extractor/
```

O usar Git:
```bash
# En la VM
cd /opt/pdf-extractor
git clone https://github.com/TU_USUARIO/pdf-extractor.git .
```

## 7. Configurar variables de entorno

```bash
cd /opt/pdf-extractor
cp .env.example .env
nano .env
```

Variables mínimas:
```
SECRET_KEY=una-clave-larga-y-aleatoria-muy-segura
DATABASE_URL=postgresql://pdfuser:PASSWORD@localhost:5432/pdf_extractor
CELERY_BROKER_URL=redis://localhost:6379/0
CELERY_RESULT_BACKEND=redis://localhost:6379/1
MP_ACCESS_TOKEN=APP_USR-xxx
MP_PUBLIC_KEY=APP_USR-xxx
```

## 8. Arrancar

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

## 9. Configurar dominio (opcional)

1. Comprar dominio (Namecheap, Cloudflare, etc.)
2. Configurar DNS A record → IP pública de la VM
3. Ejecutar certbot para SSL:
```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d tudominio.com
```

## 10. Monitoreo

```bash
# Ver logs
docker compose -f docker-compose.prod.yml logs -f

# Ver estado
docker compose -f docker-compose.prod.yml ps

# Reiniciar
docker compose -f docker-compose.prod.yml restart

# Parar
docker compose -f docker-compose.prod.yml down
```

## Costo

**$0 USD/mes** — Todo entra en el Always Free Tier:
- VM ARM 4 cores, 24GB RAM: siempre gratis
- 200GB storage: siempre gratis
- 10TB bandwidth: siempre gratis
- Sin tarjeta de crédito después del registro

## Backup

```bash
# Backup de la base de datos
docker exec pdf-extractor-db pg_dump -U pdfuser pdf_extractor > backup_$(date +%Y%m%d).sql

# Backup de los archivos
tar czf storage_backup_$(date +%Y%m%d).tar.gz /opt/pdf-extractor/storage/
```

## Actualizar

```bash
cd /opt/pdf-extractor
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
