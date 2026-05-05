"""
Parser de texto OCR para comprobantes de transferencia bancaria peruana.
Extrae monto, número de operación y banco usando regex.
"""
import re
from typing import Optional


# ============================================================
# BANCOS PERUANOS — keyword en texto OCR
# ============================================================
_BANCOS = [
    "INTERBANK",
    "BCP",
    "BBVA",
    "SCOTIABANK",
    "BANBIF",
    "PICHINCHA",
    "CREDISCOTIA",
    "MIBANCO",
    "GNB",
    "FALABELLA",
    "RIPLEY",
    "ALFIN",
    "CENCOSUD",
    "YAPE",
    "PLIN",
    "TUNKI",
    "LUKITA",
    "CAJA AREQUIPA",
]

# Frases propias de cada app bancaria que aparecen en la UI del comprobante
_APP_PHRASES: list[tuple[str, str]] = [
    ("TRANSFERISTE",        "INTERBANK"),
    ("YAPEASTE",            "YAPE"),
    ("PLIN",                "PLIN"),
    ("IMPORTE TRANSFERIDO", "BBVA"),
    ("DE LA NACION",        "BANCO DE LA NACION"),
    ("DE LA NACIÓN",        "BANCO DE LA NACION"),
    ("EL BANCO DE TODOS",   "BANCO DE LA NACION"),
    ("TRANSF.CCE",          "CAJA AREQUIPA"),
]

# ============================================================
# PATRONES REGEX
# ============================================================

# Monto: S/ 4,550.00 | S/1500.00 | S/4.200.00 (OCR lee ',' como '.')
_RE_MONTO = re.compile(
    r"(?:S/\.?\s*)([\d,.]+\d)",
    re.IGNORECASE,
)

# Número de operación: dígitos (continuos o separados por puntos) tras keyword de contexto (alta confianza)
# Soporta formatos: 123456789, 784.465.199.1918
# [^0-9] en lugar de [^0-9\n] para cruzar saltos de línea entre la etiqueta y el número
_RE_OPERACION_CTX = re.compile(
    r"(?:operaci[oó6]n|op\.?|n[uúü]mero|nro\.?|c[oó6]digo(?:\s+de\s+operaci[oó6]n)?|cod\.?|transacci[oó6]n)"
    r"[^0-9]{0,30}(\d[\d.]{4,30}\d|\d{6,14})",
    re.IGNORECASE,
)
# Fallback: 6-14 dígitos aislados, sin espacios intermedios (excluye números de cuenta con espacios)
_RE_OPERACION_BARE = re.compile(r"(?<!\d)(\d{6,14})(?!\d)")


def _normalize_op_number(raw: str) -> Optional[str]:
    """Normaliza número de operación: elimina puntos separadores y valida que queden 6-25 dígitos.
    Rechaza si el raw termina en .XX (indicador de decimal → es un monto, no un número de op).
    """
    if re.search(r'\.\d{2}$', raw):
        return None
    digits_only = raw.replace(".", "")
    if digits_only.isdigit() and 6 <= len(digits_only) <= 25:
        return digits_only
    return None


def _normalize_monto(raw: str) -> Optional[str]:
    """Normaliza el monto extraído a formato '4550.00'.
    Maneja:
      - Separador de miles coma:  4,200.00  → 4200.00
      - Separador de miles punto: 4.200.00  → 4200.00  (OCR lee ',' como '.')
      - Sin separador:            4200.00   → 4200.00
    Estrategia: el último separador (. o ,) es el decimal;
    todo lo anterior se elimina.
    """
    # Encontrar el último separador (. o ,)
    last_dot = raw.rfind(".")
    last_comma = raw.rfind(",")
    last_sep = max(last_dot, last_comma)

    if last_sep == -1:
        # Sin separador decimal → número entero
        integer_part, decimal_part = raw, "00"
    else:
        integer_part = raw[:last_sep]
        decimal_part = raw[last_sep + 1:]

    # Validar que la parte decimal sea exactamente 2 dígitos
    if not decimal_part.isdigit() or len(decimal_part) != 2:
        return None

    # Limpiar separadores de miles de la parte entera
    integer_clean = re.sub(r"[.,]", "", integer_part)
    if not integer_clean.isdigit():
        return None

    try:
        value = float(f"{integer_clean}.{decimal_part}")
        if value < 1 or value > 999_999:
            return None
        return f"{value:.2f}"
    except ValueError:
        return None


def _split_source_dest(raw_text: str) -> tuple[str, str]:
    """
    Divide el texto en dos partes:
    - source_text: antes de 'Cuenta destino' / 'Cuenta abono' (contexto del banco origen)
    - dest_text:   a partir de 'Cuenta destino' (banco destino, se ignora para el banco)
    """
    split_marker = re.search(
        r"(?:cuenta\s+(?:destino|abono|beneficiario|receptor)|nro\.?\s*cc[il]\s+destino|nombre\s+de\s+banco\s+destino)",
        raw_text,
        re.IGNORECASE,
    )
    if split_marker:
        return raw_text[:split_marker.start()], raw_text[split_marker.start():]
    return raw_text, ""


def parse_transfer_text(raw_text: str) -> dict:
    """
    Extrae monto, número de operación y banco de texto OCR crudo.

    Returns:
        {
            "monto": "4550.00" | None,
            "numero_operacion": "04349309" | None,
            "banco": "INTERBANK" | None,
            "confidence": { "monto": float, "numero_operacion": float, "banco": float }
        }
    """
    text_upper = raw_text.upper()
    source_text, dest_text = _split_source_dest(raw_text)
    source_upper = source_text.upper()

    # ── BANCO ────────────────────────────────────────────────
    # Prioridad 1: frases propias de la app bancaria (muy alta confianza)
    banco_found: Optional[str] = None
    for phrase, banco in _APP_PHRASES:
        if phrase in source_upper:
            banco_found = banco
            break

    # Prioridad 2: nombre del banco en el contexto de cuenta cargo (ANTES de destino)
    if not banco_found:
        for banco in _BANCOS:
            if banco in source_upper:
                banco_found = banco
                break

    # ── NÚMERO DE OPERACIÓN ──────────────────────────────────
    op_found: Optional[str] = None

    # Alta confianza: keyword explícito cerca — itera todos los matches hasta encontrar uno válido
    for m_ctx in _RE_OPERACION_CTX.finditer(raw_text):
        op_found = _normalize_op_number(m_ctx.group(1))
        if op_found:
            break

    # Fallback: dígito aislado de 6-14 cifras que no sea parte de un número de cuenta
    # (excluimos números que aparecen pegados a espacios con más dígitos → cuentas bancarias)
    if not op_found:
        for m in _RE_OPERACION_BARE.finditer(raw_text):
            candidate = m.group(1)
            # Saltar si el número aparece rodeado en la misma línea de más dígitos (cuenta bancaria)
            line = next((l for l in raw_text.splitlines() if candidate in l), "")
            digits_in_line = re.findall(r"\d+", line)
            total_digits_in_line = sum(len(d) for d in digits_in_line)
            if total_digits_in_line > len(candidate) + 4:
                continue  # La línea tiene muchos más dígitos → probablemente cuenta
            op_found = candidate
            break

    # ── MONTO ────────────────────────────────────────────────
    monto_found: Optional[str] = None

    for line in raw_text.splitlines():
        if re.search(r"S/\.?\s*\d", line, re.IGNORECASE):
            m = _RE_MONTO.search(line)
            if m:
                normalized = _normalize_monto(m.group(1))
                if normalized:
                    monto_found = normalized
                    break

    return {
        "monto": monto_found,
        "numero_operacion": op_found,
        "banco": banco_found,
    }

