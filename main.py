"""
IMEI-OCR Service — FastAPI entry point
Microservicio OCR para comprobantes de transferencia bancaria.
"""
import logging
import os
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI

load_dotenv()
from fastapi.middleware.cors import CORSMiddleware

from app.routes import ocr

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("IMEI-OCR Service iniciando...")
    yield
    logger.info("IMEI-OCR Service apagándose...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="IMEI OCR Service",
        description="Servicio de extracción de datos de comprobantes de transferencia bancaria",
        version="1.0.0",
        # Deshabilitar docs en producción si se prefiere
        docs_url="/docs" if os.getenv("ENV", "production") != "production" else None,
        redoc_url=None,
        lifespan=lifespan,
    )

    # CORS restringido: solo el backend IMEI debe llamar a este servicio
    # En producción, reemplazar "*" con la URL exacta del servicio IMEI en Railway
    allowed_origins = os.getenv("OCR_ALLOWED_ORIGINS", "").split(",")
    allowed_origins = [o.strip() for o in allowed_origins if o.strip()] or ["*"]

    app.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["POST"],
        allow_headers=["X-OCR-API-Key", "Content-Type"],
    )

    app.include_router(ocr.router, prefix="/ocr", tags=["ocr"])

    @app.get("/health", tags=["health"])
    def health():
        return {"status": "ok", "service": "imei-ocr"}

    return app


app = create_app()
