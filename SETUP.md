# IMEI-OCR — Guía de Inicialización

Microservicio OCR para extracción de datos de comprobantes de transferencia bancaria, construido con **FastAPI** y **PaddleOCR**.

---

## Requisitos previos

- Python 3.12
- pip

> **Nota:** PaddleOCR requiere dependencias de sistema para OpenCV. En producción se usa Docker (ver más abajo).

---

## Configuración local

### 1. Crear y activar entorno virtual

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Instalar dependencias

```bash
pip install -r requirements.txt
```

> La primera instalación tarda varios minutos por el peso de `paddlepaddle` y `opencv`.

### 3. Variables de entorno

Crea un archivo `.env` en la raíz del proyecto:

```env
# Clave compartida entre este servicio y el backend IMEI
OCR_API_KEY=tu_clave_secreta_aqui

# Orígenes permitidos (URL del backend IMEI). Separar por comas.
# Dejar vacío o "*" solo en desarrollo local.
OCR_ALLOWED_ORIGINS=http://localhost:8000

# "development" activa /docs; cualquier otro valor la desactiva
ENV=development
```

### 4. Levantar el servidor

```bash
uvicorn main:app --reload --port 8001
```

El servicio queda disponible en `http://localhost:8001`.

- **Docs interactivos:** `http://localhost:8001/docs` (solo en `ENV=development`)
- **Health check:** `http://localhost:8001/health`

---

## Endpoints

| Método | Ruta | Auth | Descripción |
|--------|------|------|-------------|
| `GET` | `/health` | — | Estado del servicio |
| `POST` | `/ocr/extract` | `X-OCR-API-Key` | Extrae datos de una imagen de transferencia |

### Ejemplo de request

```bash
curl -X POST http://localhost:8001/ocr/extract \
  -H "X-OCR-API-Key: tu_clave_secreta_aqui" \
  -F "image=@comprobante.png"
```

### Respuesta esperada

```json
{
  "monto": "1500.00",
  "numero_operacion": "123456789",
  "fecha": "2026-05-05",
  "banco": "BCP",
}
```

Formatos de imagen aceptados: `PNG`, `JPEG`, `WEBP` (máx. 10 MB).

---

## Docker (recomendado para producción)

### Build

```bash
docker build -t imei-ocr .
```

> El build descarga los modelos de PaddleOCR (`use_angle_cls`, `lang='es'`) para evitar cold starts.

### Run

```bash
docker run -p 8001:8001 \
  -e OCR_API_KEY=tu_clave_secreta_aqui \
  -e OCR_ALLOWED_ORIGINS=https://tu-backend-imei.railway.app \
  -e PORT=8001 \
  imei-ocr
```

---

## Despliegue en Railway

El proyecto incluye `railway.json` configurado para build con Dockerfile:

```json
{
  "build": { "builder": "DOCKERFILE" },
  "deploy": {
    "startCommand": "uvicorn main:app --host 0.0.0.0 --port $PORT"
  }
}
```

Variables de entorno a configurar en Railway:

| Variable | Descripción |
|----------|-------------|
| `OCR_API_KEY` | Clave compartida con el backend IMEI |
| `OCR_ALLOWED_ORIGINS` | URL del backend IMEI en Railway |
| `ENV` | `production` (deshabilita `/docs`) |

---

## Estructura del proyecto

```
IMEI-ocr/
├── main.py                        # Entry point FastAPI
├── requirements.txt
├── Dockerfile
├── railway.json
└── app/
    ├── routes/
    │   └── ocr.py                 # POST /ocr/extract
    └── services/
        ├── image_preprocessor.py  # Preprocesado de imagen (OpenCV)
        ├── paddle_ocr_service.py  # Extracción de texto (PaddleOCR)
        └── transfer_parser.py     # Parseo de campos del comprobante
```
