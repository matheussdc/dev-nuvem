from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    DATABASE_URL: str
    REDIS_URL: str
    S3_BUCKET: str
    SNS_TOPIC_ARN: str
    ADMIN_TOKEN: str
    DYNAMO_TABLE: str = "dspn-projeto-dynamo-logs"
    AWS_REGION: str = "us-east-1"

    class Config:
        env_file = ".env"


settings = Settings()
