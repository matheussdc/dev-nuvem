#!/bin/bash
set -e

EC2_IP=$1
if [ -z "$EC2_IP" ]; then
    echo "Uso: ./deploy-backend.sh <EC2_IP>"
    exit 1
fi

echo "🚀 Deploy do Backend na EC2 $EC2_IP..."
ssh -i ~/.ssh/dspn-projeto-key.pem ubuntu@$EC2_IP << 'EOF'
  cd /opt/app
  git pull origin main
  source venv/bin/activate
  cd backend
  pip install -r requirements.txt -q
  sudo systemctl restart backend
  echo "✅ Backend reiniciado!"
EOF
