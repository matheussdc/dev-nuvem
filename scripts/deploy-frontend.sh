#!/bin/bash
# Uso: ./scripts/deploy-frontend.sh <DNS-DO-ALB> <BUCKET-FRONTEND>
set -e
ALB=$1
BUCKET=$2
if [ -z "$ALB" ] || [ -z "$BUCKET" ]; then
    echo "Uso: $0 <DNS-DO-ALB> <BUCKET-FRONTEND>"
    exit 1
fi

cd "$(dirname "$0")/../frontend"
npm ci
VITE_API_URL="http://$ALB" npm run build
aws s3 sync dist/ "s3://$BUCKET/" --delete
echo "Acesse: http://$BUCKET.s3-website-us-east-1.amazonaws.com"
