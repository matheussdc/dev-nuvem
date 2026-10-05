#!/bin/bash
# Garante que o script pare em qualquer erro e loga cada comando executado
set -ex

exec > >(tee /var/log/user-data.log) 2>&1
echo "=== Iniciando setup do backend: $(date) ==="

# 1. Atualiza e instala dependências do sistema
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y \
    python3-pip \
    python3-venv \
    python3-dev \
    git \
    awscli \
    nginx \
    libpq-dev \
    build-essential

# Aguarda o RDS ficar disponível (pode levar alguns segundos)
sleep 10

# Cria o banco de dados se não existir
export PGPASSWORD="f7a901f4eab8b92f0b1b2ea6"
psql -h dspn-projeto-db-instance.cmaxzh1hz8ka.us-east-1.rds.amazonaws.com -U admin -d postgres -c "CREATE DATABASE ingressos;" 2>/dev/null || echo "Banco já existe ou erro ao criar"
unset PGPASSWORD

# 2. Prepara o diretório e clona o repositório de forma 100% segura
cd /opt
rm -rf app # Garante que a pasta está limpa para o clone
git clone https://github.com/matheussdc/dev-nuvem.git app

# 3. Cria usuário e define permissões
useradd -m -s /bin/bash appuser || true
chown -R appuser:appuser /opt/app

# 4. Cria e popula o virtual environment
sudo -u appuser python3 -m venv /opt/app/venv
sudo -u appuser /opt/app/venv/bin/pip install --upgrade pip

# Verifica se o requirements.txt existe antes de instalar (segurança extra)
if [ -f /opt/app/backend/requirements.txt ]; then
    sudo -u appuser /opt/app/venv/bin/pip install -r /opt/app/backend/requirements.txt
else
    echo "ERRO CRÍTICO: /opt/app/backend/requirements.txt não encontrado!"
    exit 1
fi

# 5. Configura o arquivo .env
cat > /opt/app/backend/.env << 'EOF'
DATABASE_URL=postgresql+psycopg://postgres:f7a901f4eab8b92f0b1b2ea6@dspn-projeto-db-instance.cmaxzh1hz8ka.us-east-1.rds.amazonaws.com:5432/ingressos
REDIS_URL=redis://master.dspn-projeto-cache.qjtido.use1.cache.amazonaws.com:6379
S3_BUCKET=backend-309843684442-us-east-1-an
SNS_TOPIC_ARN=arn:aws:sns:us-east-1:309843684442:dspn-projeto-sns
AWS_REGION=us-east-1
EOF

chown appuser:appuser /opt/app/backend/.env
chmod 600 /opt/app/backend/.env

# 6. Cria o serviço systemd
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

# 7. Configura o Nginx como Reverse Proxy
cat > /etc/nginx/sites-available/backend << 'EOF'
server {
    listen 80;
    server_name _;

    location /health {
        proxy_pass http://127.0.0.1:8000/health;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        access_log off;
    }

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

# 8. Inicia o Backend
systemctl daemon-reload
systemctl enable backend
systemctl start backend

echo "=== Setup concluído com SUCESSO: $(date) ==="
