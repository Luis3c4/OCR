"""
Wrapper de PaddleOCR para extracción de texto de imágenes.
Instancia única (singleton) para evitar recargar el modelo en cada request.
"""
import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# Instancia lazy del modelo OCR (se carga solo la primera vez que se usa)
_paddle_ocr = None


def _get_ocr():
    """Retorna la instancia singleton de PaddleOCR, cargándola si es necesario."""
    global _paddle_ocr
    if _paddle_ocr is None:
        from paddleocr import PaddleOCR
        logger.info("Cargando modelo PaddleOCR...")
        _paddle_ocr = PaddleOCR(
            use_angle_cls=True,   # Detectar texto rotado (capturas inclinadas)
            lang="es",            # Modelo optimizado para español/latín
            show_log=False,       # Silenciar logs verbosos de Paddle
            use_gpu=False,        # CPU-only (Railway no tiene GPU)
        )
        logger.info("Modelo PaddleOCR cargado.")
    return _paddle_ocr


def extract_text(image_array: np.ndarray) -> tuple[str, float]:
    """
    Ejecuta OCR sobre un array de imagen preprocesado.

    Args:
        image_array: Array NumPy BGR (salida de image_preprocessor.preprocess_image)

    Returns:
        Tuple (raw_text, avg_confidence):
        - raw_text: Texto completo extraído, líneas separadas por \\n
        - avg_confidence: Confianza promedio de todas las detecciones (0.0 – 1.0)
    """
    ocr = _get_ocr()

    result = ocr.ocr(image_array, cls=True)

    if not result or not result[0]:
        return "", 0.0

    lines = []
    confidences = []

    for line in result[0]:
        if line is None:
            continue
        # Estructura de PaddleOCR: [[box], (text, confidence)]
        text_info = line[1]
        if not text_info:
            continue
        text, conf = text_info
        if text and text.strip():
            lines.append(text.strip())
            confidences.append(float(conf))

    raw_text = "\n".join(lines)
    avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

    return raw_text, avg_confidence
