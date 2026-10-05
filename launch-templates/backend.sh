#!/bin/bash
set -e

# ============================================
# User Data - Backend FastAPI (Sistema Ingressos)
# ============================================

# Log para debug
exec > >(tee /var/log/user-data.log) 2>&1
echo "=== Iniciando setup do backend: $(date) ==="

# Atualiza pacotes
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Instala dependências
apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    awscli \
    nginx \
    libpq-dev \
    build-essential

# Cria usuário da aplicação
useradd -m -s /bin/bash appuser || true

# Cria diretório da aplicação
mkdir -p /opt/app
cd /opt/app

# Clona o repositório (ajuste a URL)
git clone https://github.com/matheussdc/dev-nuvem.git . || echo "Repo já existe"
chown -R appuser:appuser /opt/app

# Cria virtual environment
sudo -u appuser python3 -m venv /opt/app/venv

# Instala dependências do backend
sudo -u appuser /opt/app/venv/bin/pip install --upgrade pip
sudo -u appuser /opt/app/venv/bin/pip install -r /opt/app/backend/requirements.txt

# ============================================
# Configuração de Variáveis de Ambiente
# ============================================
# ⚠️ SUBSTITUA OS VALORES ABAIXO PELOS SEUS ENDPOINTS REAIS!

cat > /opt/app/backend/.env << 'EOF'
DATABASE_URL=
REDIS_URL=
S3_BUCKET=
SNS_TOPIC_ARN=
AWS_REGION=us-east-1
ENVIRONMENT=production
EOF

chown appuser:appuser /opt/app/backend/.env
chmod 600 /opt/app/backend/.env

# ============================================
# Systemd Service para o FastAPI
# ============================================
cat > /etc/systemd/system/backend.service << 'EOF'
[Unit]
Description=Backend FastAPI - Sistema de Ingressos
After=network.target

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/app/backend
EnvironmentFile=/opt/app/backend/.env
ExecStart=/opt/app/venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ============================================
# Nginx como Reverse Proxy (porta 80 → 8000)
# ============================================
cat > /etc/nginx/sites-available/backend << 'EOF'
server {
    listen 80;
    server_name _;

    # Health check para ALB
    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        access_log off;
    }

    # API
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        client_max_body_size 20M;
    }
}
EOF

ln -sf /etc/nginx/sites-available/backend /etc/nginx/sites-enabled/backend
rm -f /etc/nginx/sites-enabled/default
nginx -t
systemctl restart nginx
systemctl enable nginx

# ============================================
# Inicia o Backend
# ============================================
systemctl daemon-reload
systemctl enable backend
systemctl start backend

echo "=== Setup concluído: $(date) ==="
echo "Backend rodando em http://localhost:8000"
echo "Health check: http://localhost:8000/health"
