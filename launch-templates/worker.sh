#!/bin/bash
# /scripts/user-data-worker.sh

set -ex
exec > >(tee /var/log/user-data.log) 2>&1
echo "=== Iniciando setup do worker: $(date) ==="

# Atualiza pacotes
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y

# Instala dependências
apt-get install -y python3-pip python3-venv git awscli fonts-dejavu-core

# Cria diretório da aplicação
cd /opt
rm -rf worker
git clone https://github.com/matheussdc/dev-nuvem.git worker-tmp
mv worker-tmp/worker /opt/worker
rm -rf worker-tmp

# Cria virtual environment
python3 -m venv /opt/worker/venv
/opt/worker/venv/bin/pip install --upgrade pip
/opt/worker/venv/bin/pip install -r /opt/worker/requirements.txt

# Cria arquivo de ambiente
cat > /opt/worker/.env << EOF
S3_BUCKET=backend-309843684442-us-east-1-an
SQS_URL=https://sqs.us-east-1.amazonaws.com/309843684442/dspn-projeto-queue
DYNAMO_TABLE=dspn-projeto-dynamo-logs
AWS_REGION=us-east-1
EOF

# Configura systemd service para o worker
cat > /etc/systemd/system/worker.service << 'EOF'
[Unit]
Description=Worker de Processamento Assíncrono (SQS)
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/opt/worker
EnvironmentFile=/opt/worker/.env
ExecStart=/opt/worker/venv/bin/python worker.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Habilita e inicia o serviço
systemctl daemon-reload
systemctl enable worker
systemctl start worker

echo "✅ Worker configurado e iniciado!"
