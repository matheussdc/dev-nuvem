#!/usr/bin/env python3
import os
import json
import boto3
import time
from PIL import Image
from io import BytesIO
from datetime import datetime
from dotenv import load_dotenv

# Carrega variáveis de ambiente
load_dotenv('/opt/worker/.env')

S3_BUCKET = os.environ['S3_BUCKET']
SQS_URL = os.environ['SQS_URL']
DYNAMO_TABLE = os.environ['DYNAMO_TABLE']
AWS_REGION = os.environ.get('AWS_REGION', 'us-east-1')

# Clientes AWS
s3 = boto3.client('s3', region_name=AWS_REGION)
sqs = boto3.client('sqs', region_name=AWS_REGION)
dynamodb = boto3.resource('dynamodb', region_name=AWS_REGION)
table = dynamodb.Table(DYNAMO_TABLE)

print(f"🚀 Worker iniciado. Aguardando mensagens em: {SQS_URL}")
print(f"📦 Bucket S3: {S3_BUCKET}")
print(f"📊 Tabela DynamoDB: {DYNAMO_TABLE}")

def process_image_rotation(message):
    """Processa rotação de imagem"""
    original_key = message['original_key']
    processed_key = message['processed_key']
    upload_id = message.get('upload_id', 'unknown')

    print(f"📥 Baixando: s3://{S3_BUCKET}/{original_key}")

    # 1. Baixa a imagem do S3
    s3_response = s3.get_object(Bucket=S3_BUCKET, Key=original_key)
    image_data = s3_response['Body'].read()

    # 2. Rotaciona a imagem (180 graus)
    image = Image.open(BytesIO(image_data))
    rotated_image = image.rotate(180, expand=True)

    # 3. Salva a imagem processada de volta no S3
    output_buffer = BytesIO()
    fmt = image.format or 'PNG'
    rotated_image.save(output_buffer, format=fmt)
    output_buffer.seek(0)

    s3.put_object(
        Bucket=S3_BUCKET,
        Key=processed_key,
        Body=output_buffer.getvalue(),
        ContentType=s3_response.get('ContentType', 'image/png')
    )

    print(f"📤 Salvo: s3://{S3_BUCKET}/{processed_key}")

    # 4. Log no DynamoDB
    table.put_item(Item={
        'id': f"process#{upload_id}",
        'action': 'PROCESS_IMAGE',
        'data': json.dumps({
            'original': original_key,
            'processed': processed_key,
            'transformation': 'rotate_180'
        }),
        'timestamp': datetime.utcnow().isoformat()
    })

    print(f"✅ Imagem processada com sucesso!")


def main():
    """Loop principal do worker"""
    while True:
        try:
            # 1. Lê mensagens da fila SQS (Long Polling - espera até 20s)
            response = sqs.receive_message(
                QueueUrl=SQS_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=10
            )

            messages = response.get('Messages', [])

            if not messages:
                continue

            for message in messages:
                receipt_handle = message['ReceiptHandle']
                body = json.loads(message['Body'])

                # O SNS envolve a mensagem em um formato específico
                if 'Message' in body:
                    msg_data = json.loads(body['Message'])
                else:
                    msg_data = body

                action = msg_data.get('action')
                print(f"📨 Mensagem recebida: {action}")

                if action == 'rotate_image':
                    process_image_rotation(msg_data)
                else:
                    print(f"⚠️ Ação desconhecida: {action}")

                # 2. Remove a mensagem da fila (confirmação de processamento)
                sqs.delete_message(
                    QueueUrl=SQS_URL,
                    ReceiptHandle=receipt_handle
                )
                print(f"🗑️ Mensagem removida da fila")

        except Exception as e:
            print(f"❌ Erro no worker: {e}")
            time.sleep(5)


if __name__ == '__main__':
    main()
