from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import models
from app.api import data_stream, efficiency, ranking, tests
from app.config import settings
from app.database import engine

models.Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.app_name,
    description="锂电池化成工序充放电效率分析后端系统",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", tags=["系统"], summary="系统信息")
def root():
    return {
        "name": settings.app_name,
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "api_prefix": settings.api_prefix,
    }


@app.get("/health", tags=["系统"], summary="健康检查")
def health_check():
    return {"status": "ok"}


api_prefix = settings.api_prefix
app.include_router(tests.router, prefix=api_prefix)
app.include_router(data_stream.router, prefix=api_prefix)
app.include_router(efficiency.router, prefix=api_prefix)
app.include_router(ranking.router, prefix=api_prefix)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
