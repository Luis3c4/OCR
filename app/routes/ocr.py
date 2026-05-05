"""
Ruta principal del servicio OCR.
POST /ocr/extract — recibe imagen de transferencia, retorna campos extraídos.
"""
import os
import logging
from fastapi import APIRouter, UploadFile, File, HTTPException, Security
from fastapi.security.api_key import APIKeyHeader

from app.services.image_preprocessor import preprocess_image
from app.services.paddle_ocr_service import extract_text
from app.services.transfer_parser import parse_transfer_text

logger = logging.getLogger(__name__)

router = APIRouter()

# ============================================================
# AUTENTICACIÓN POR API KEY (header X-OCR-API-Key)
# El cliente (backend IMEI) debe enviar este header en cada request.
# ============================================================
_api_key_header = APIKeyHeader(name="X-OCR-API-Key", auto_error=True)
_VALID_API_KEY = os.getenv("OCR_API_KEY", "")

ALLOWED_CONTENT_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp"}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def _verify_api_key(api_key: str = Security(_api_key_header)) -> str:
    if not _VALID_API_KEY:
        raise HTTPException(status_code=500, detail="OCR_API_KEY no configurada en el servidor")
    if api_key != _VALID_API_KEY:
        raise HTTPException(status_code=403, detail="API Key inválida")
    return api_key


@router.post("/extract")
def extract_transfer_data(
    image: UploadFile = File(..., description="Captura de pantalla de la transferencia bancaria"),
    _key: str = Security(_verify_api_key),
):
    """
    Extrae datos de una transferencia bancaria desde una imagen.

    Retorna monto, número de operación, fecha y banco detectados,
    junto con su nivel de confianza individual (0.0 – 1.0).

    El handler es `def` (síncrono) para que FastAPI lo ejecute en el
    thread pool de anyio, evitando bloquear el event loop durante el
    procesamiento pesado de PaddleOCR.
    """
    # Validar content type
    content_type = image.content_type or ""
    if content_type not in ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=422,
            detail=f"Tipo de archivo no soportado: '{content_type}'. Use PNG, JPEG o WEBP.",
        )

    # Leer y validar tamaño
    image_bytes = image.file.read()
    if len(image_bytes) == 0:
        raise HTTPException(status_code=422, detail="La imagen está vacía.")
    if len(image_bytes) > MAX_FILE_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="La imagen excede el límite de 10 MB.")

    try:
        # 1. Preprocesar imagen para mejorar OCR
        processed = preprocess_image(image_bytes)

        # 2. Extraer texto con PaddleOCR
        raw_text, avg_ocr_confidence = extract_text(processed)

        if not raw_text.strip():
            return {
                "success": False,
                "error": "No se pudo extraer texto de la imagen. Verifica que sea una captura clara.",
                "data": None,
            }

        # 3. Parsear campos específicos del comprobante
        parsed = parse_transfer_text(raw_text)

        logger.info(
            "OCR completado | monto=%s | op=%s | banco=%s | ocr_conf=%.2f",
            parsed["monto"],
            parsed["numero_operacion"],
            parsed["banco"],
            avg_ocr_confidence,
        )

        return {
            "success": True,
            "data": {
                "monto": parsed["monto"],
                "numero_operacion": parsed["numero_operacion"],
                "banco": parsed["banco"],
                "raw_text": raw_text,
            },
        }

    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Error procesando imagen OCR: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error interno al procesar la imagen: {str(exc)}")
