#!/bin/bash
set -e

echo "🚀 Deploy do Lambda..."
cd worker

# Limpa pasta anterior
rm -rf package lambda_function.zip

# Cria pasta e instala dependências
mkdir package
pip install -r requirements.txt -t package

# Copia código
cp lambda_function.py package/

# Cria ZIP
cd package
zip -r ../lambda_function.zip . > /dev/null
cd ..

# Atualiza Lambda (ou cria se não existir)
aws lambda update-function-code \
  --function-name dspn-projeto-worker \
  --zip-file fileb://lambda_function.zip \
  --publish > /dev/null

echo "✅ Lambda atualizado!"
rm -rf package lambda_function.zip
