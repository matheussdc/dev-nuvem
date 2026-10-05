from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    S3_BUCKET: str
    SNS_TOPIC_ARN: str
    AWS_REGION: str = "us-east-1"

    class Config:
        env_file = ".env"

settings = Settings()
