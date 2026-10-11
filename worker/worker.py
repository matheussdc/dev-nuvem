#!/usr/bin/env python3
"""Lê a fila SQS (assinada no tópico SNS) e processa mensagens assíncronas."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO
import boto3
from dotenv import load_dotenv

load_dotenv('/opt/worker/.env')

S3_BUCKET = os.environ['S3_BUCKET']
SQS_URL = os.environ['SQS_URL']
DYNAMO_TABLE = os.environ['DYNAMO_TABLE']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

s3 = boto3.client('s3', region_name=AWS_REGION)
sqs = boto3.client('sqs', region_name=AWS_REGION)
table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(DYNAMO_TABLE)

# Importa os processadores
from processors.thumbnail import gerar_thumbnail
from processors.pdf import gerar_pdf


def log_dynamo(acao, entidade, dados):
    table.put_item(Item={
        'id': str(uuid.uuid4()),
        'acao': acao,
        'entidade': entidade,
        'dados': json.dumps(dados, default=str, ensure_ascii=False),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })


def processar_mensagem(msg):
    action = msg.get('action')

    if action == 'thumbnail':
        # Baixa pôster original, gera thumbnail, salva no S3
        original = s3.get_object(Bucket=S3_BUCKET, Key=msg['key'])['Body'].read()
        tamanho_original, tamanho_final = gerar_thumbnail(original)

        # Salva thumbnail
        thumb_bytes = gerar_thumbnail.__wrapped__(original) if hasattr(gerar_thumbnail, '__wrapped__') else None
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=msg['thumb_key'],
            Body=gerar_thumbnail(original, return_bytes=True),
            ContentType='image/jpeg'
        )

        log_dynamo('PROCESS', 'poster', {
            'original': msg['key'],
            'thumbnail': msg['thumb_key'],
            'de': tamanho_original,
            'para': tamanho_final,
        })
        print(f"✓ thumbnail {msg['thumb_key']}", flush=True)

    elif action == 'generate_pdf':
        # Busca pôster do S3 (se existir)
        poster_bytes = None
        poster_key = msg.get('poster_key')
        if poster_key:
            try:
                poster_bytes = s3.get_object(Bucket=S3_BUCKET, Key=poster_key)['Body'].read()
            except Exception as e:
                print(f"⚠ pôster não encontrado: {poster_key} ({e})", flush=True)

        # Gera PDF
        pdf_bytes = gerar_pdf(poster_bytes, msg['linhas'])

        # Salva no S3
        s3.put_object(
            Bucket=S3_BUCKET,
            Key=msg['pdf_key'],
            Body=pdf_bytes,
            ContentType='application/pdf',
            ContentDisposition=f'attachment; filename="ingresso-cinematix.pdf"'
        )

        log_dynamo('PROCESS', 'ingresso_pdf', {
            'pdf_key': msg['pdf_key'],
            'ingressos_ids': [l['ingresso']['id'] for l in msg['linhas']],
            'tamanho_bytes': len(pdf_bytes),
        })
        print(f"✓ pdf {msg['pdf_key']} ({len(pdf_bytes)} bytes)", flush=True)

    else:
        print(f"⚠ ação desconhecida: {action}", flush=True)


def main():
    print(f"🚀 Worker aguardando mensagens em {SQS_URL}", flush=True)
    while True:
        try:
            resp = sqs.receive_message(
                QueueUrl=SQS_URL,
                MaxNumberOfMessages=10,
                WaitTimeSeconds=20
            )
            for m in resp.get('Messages', []):
                body = json.loads(m['Body'])
                # Desenrola o envelope do SNS
                msg = json.loads(body['Message']) if 'Message' in body else body

                try:
                    processar_mensagem(msg)
                except Exception as e:
                    print(f"❌ erro processando mensagem: {e}", flush=True)
                    # Não deleta a mensagem → volta para a fila (retry)
                    continue

                sqs.delete_message(QueueUrl=SQS_URL, ReceiptHandle=m['ReceiptHandle'])

        except Exception as e:
            print(f"❌ erro no loop principal: {e}", flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
