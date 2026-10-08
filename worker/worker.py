#!/usr/bin/env python3
"""Lê a fila SQS (assinada no tópico SNS) e gera thumbnails dos pôsteres."""
import json
import os
import time
import uuid
from datetime import datetime, timezone
from io import BytesIO

import boto3
from dotenv import load_dotenv
from PIL import Image

load_dotenv('/opt/worker/.env')

S3_BUCKET = os.environ['S3_BUCKET']
SQS_URL = os.environ['SQS_URL']
DYNAMO_TABLE = os.environ['DYNAMO_TABLE']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

s3 = boto3.client('s3', region_name=AWS_REGION)
sqs = boto3.client('sqs', region_name=AWS_REGION)
table = boto3.resource('dynamodb', region_name=AWS_REGION).Table(DYNAMO_TABLE)


def gerar_thumbnail(msg):
    original = s3.get_object(Bucket=S3_BUCKET, Key=msg['key'])['Body'].read()
    img = Image.open(BytesIO(original)).convert('RGB')
    tamanho = img.size
    img.thumbnail((300, 450))
    buf = BytesIO()
    img.save(buf, 'JPEG', quality=85)
    s3.put_object(Bucket=S3_BUCKET, Key=msg['thumb_key'], Body=buf.getvalue(), ContentType='image/jpeg')
    table.put_item(Item={
        'id': str(uuid.uuid4()),
        'acao': 'PROCESS',
        'entidade': 'poster',
        'dados': json.dumps({'original': msg['key'], 'thumbnail': msg['thumb_key'],
                             'de': tamanho, 'para': img.size}),
        'timestamp': datetime.now(timezone.utc).isoformat(),
    })
    print(f"thumbnail {msg['thumb_key']} {tamanho} -> {img.size}", flush=True)


def main():
    print(f"Worker aguardando mensagens em {SQS_URL}", flush=True)
    while True:
        try:
            resp = sqs.receive_message(QueueUrl=SQS_URL, MaxNumberOfMessages=10, WaitTimeSeconds=20)
            for m in resp.get('Messages', []):
                body = json.loads(m['Body'])
                msg = json.loads(body['Message']) if 'Message' in body else body  # envelope do SNS
                if msg.get('action') == 'thumbnail':
                    gerar_thumbnail(msg)
                else:
                    print(f"ação desconhecida: {msg.get('action')}", flush=True)
                # ponytail: mensagem com erro volta para a fila sem limite; configure uma DLQ no SQS
                sqs.delete_message(QueueUrl=SQS_URL, ReceiptHandle=m['ReceiptHandle'])
        except Exception as e:
            print(f"erro no worker: {e}", flush=True)
            time.sleep(5)


if __name__ == '__main__':
    main()
