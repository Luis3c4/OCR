"""
Preprocesamiento de imágenes para OCR de transferencias bancarias.
Optimizado para screenshots de móvil capturadas en alta resolución.
"""
import cv2
import numpy as np
from PIL import Image
import io


def preprocess_image(image_bytes: bytes) -> np.ndarray:
    """
    Preprocesa una imagen para mejorar la precisión de PaddleOCR.

    Pipeline:
    1. Decodificar bytes → array BGR de OpenCV
    2. Reescalar si la imagen es pequeña (screenshots de móvil)
    3. Convertir a escala de grises
    4. Contraste adaptativo (CLAHE)
    5. Denoising ligero

    Args:
        image_bytes: Imagen en bytes (PNG / JPEG / WEBP)

    Returns:
        Array NumPy BGR listo para PaddleOCR
    """
    # Decodificar: primero intentar con OpenCV, luego con Pillow como fallback
    nparr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

    if img is None:
        # Fallback: convertir via Pillow (maneja WEBP y otros formatos)
        pil_img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        img = cv2.cvtColor(np.array(pil_img), cv2.COLOR_RGB2BGR)

    # Reescalar imágenes pequeñas (screenshots comprimidos o de baja DPI)
    h, w = img.shape[:2]
    if max(h, w) < 1500:
        scale = 1500 / max(h, w)
        img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Convertir a escala de grises
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # CLAHE: contraste adaptativo por bloques — mejora texto en fondos con degradé
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    enhanced = clahe.apply(gray)

    # Denoising ligero para reducir artefactos de compresión JPEG
    denoised = cv2.fastNlMeansDenoising(enhanced, h=10)

    # Convertir de vuelta a BGR (PaddleOCR acepta BGR o RGB)
    result = cv2.cvtColor(denoised, cv2.COLOR_GRAY2BGR)
    return result
