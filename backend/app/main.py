from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routers import upload

app = FastAPI(title="Teste de Integração AWS")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(upload.router)

@app.get("/")
async def root():
    return {"message": "Teste de Integração AWS - Backend OK"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
