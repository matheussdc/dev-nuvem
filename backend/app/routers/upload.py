import json
import uuid
from datetime import datetime
from fastapi import APIRouter, UploadFile, File, Depends, HTTPException
from sqlalchemy.orm import Session
import boto3
import redis
from app.config import settings
from app.database import get_db, Upload

router = APIRouter()

s3_client = boto3.client('s3', region_name=settings.AWS_REGION)
sns_client = boto3.client('sns', region_name=settings.AWS_REGION)
dynamo_client = boto3.resource('dynamodb', region_name=settings.AWS_REGION)
redis_client = redis.from_url(settings.REDIS_URL)

dynamo_table = dynamo_client.Table('dspn-projeto-dynamo-logs')

@router.post("/upload")
async def upload_image(file: UploadFile = File(...), db: Session = Depends(get_db)):
    # 1. Validação
    if not file.content_type.startswith('image/'):
        raise HTTPException(status_code=400, detail="Apenas imagens são permitidas")

    # 2. Gera chave única
    file_id = str(uuid.uuid4())
    original_key = f"originals/{file_id}_{file.filename}"
    processed_key = f"processed/{file_id}_rotated_{file.filename}"

    # 3. Salva no S3
    file_content = await file.read()
    s3_client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=original_key,
        Body=file_content,
        ContentType=file.content_type
    )

    # 4. Salva no RDS
    upload_record = Upload(
        original_key=original_key,
        processed_key=processed_key,
        status="pending"
    )
    db.add(upload_record)
    db.commit()
    db.refresh(upload_record)

    # 5. Log no DynamoDB
    dynamo_table.put_item(Item={
        'id': f"upload#{upload_record.id}",
        'action': 'CREATE',
        'data': json.dumps({
            'original_key': original_key,
            'filename': file.filename,
            'content_type': file.content_type
        }),
        'timestamp': datetime.utcnow().isoformat()
    })

    # 6. Invalida cache da lista de uploads
    redis_client.delete('uploads:list')

    # 7. Publica no SNS (Lambda vai processar)
    message = {
        'action': 'rotate_image',
        'original_key': original_key,
        'processed_key': processed_key,
        'upload_id': upload_record.id
    }

    sns_response = sns_client.publish(
        TopicArn=settings.SNS_TOPIC_ARN,
        Message=json.dumps(message),
        Subject='Processamento de Imagem'
    )

    # 8. URL pública da imagem original
    original_url = f"https://{settings.S3_BUCKET}.s3.amazonaws.com/{original_key}"

    return {
        "message": "Imagem enviada! Lambda irá processar.",
        "original_url": original_url,
        "original_key": original_key,
        "processed_key": processed_key,
        "upload_id": upload_record.id,
        "sns_message_id": sns_response['MessageId']
    }


@router.get("/image/{processed_key:path}")
async def get_processed_image(processed_key: str, db: Session = Depends(get_db)):
    # Verifica se o arquivo já existe no S3
    try:
        s3_client.head_object(Bucket=settings.S3_BUCKET, Key=processed_key)
    except Exception:
        raise HTTPException(status_code=404, detail="Imagem ainda não processada")

    url = f"https://{settings.S3_BUCKET}.s3.amazonaws.com/{processed_key}"
    return {"url": url, "status": "processed"}


@router.get("/uploads")
async def list_uploads(db: Session = Depends(get_db)):
    # Tenta pegar do cache
    cached = redis_client.get('uploads:list')
    if cached:
        return json.loads(cached)

    # Busca no RDS
    uploads = db.query(Upload).order_by(Upload.created_at.desc()).limit(10).all()
    result = [
        {
            "id": u.id,
            "original_key": u.original_key,
            "processed_key": u.processed_key,
            "status": u.status,
            "created_at": u.created_at.isoformat()
        }
        for u in uploads
    ]

    # Salva no cache (60s)
    redis_client.setex('uploads:list', 60, json.dumps(result))

    return result

@router.get("/test-redis")
def test_redis():
    redis_client.set("teste_trabalho", "Funcionou!")
    valor = redis_client.get("teste_trabalho")
    return {"mensagem": f"Cache respondendo: {valor}"}
