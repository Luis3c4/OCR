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
    ("IMPORTE TRANSFER",   "BBVA"),   # cubre TRANSFERIDO y TRANSFERIDA
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


# ============================================================
# EXTRACCIÓN DE FECHA Y HORA DE TRANSFERENCIA
# ============================================================

# DD/MM/YY[YY] HH:MM[:SS] [AM/PM]  →  mismo renglón
_RE_FULL_SLASH_DT = re.compile(
    r"\b(\d{2}/\d{2}/\d{2,4}\s+\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP]\.?\s*[mM]\.?)?)\b",
    re.IGNORECASE,
)

# "11 marzo 2026, 15:47" | "25 Mar 2026  04:09 PM" | "23 mar., 04:42 p. m."
_RE_FULL_MONTH_DT = re.compile(
    r"(\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)[a-z\u00e1\u00e9\u00ed\u00f3\u00fa.]*"
    r"\.?\s*(?:(?:de\s+)?\d{4})?\s*,?\s*\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP]\.?\s*[mM]\.?)?)",
    re.IGNORECASE,
)

_RE_DATE_SLASH_ONLY = re.compile(r"\b(\d{2}/\d{2}/\d{2,4})\b")
_RE_TIME_ONLY = re.compile(r"\b(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP]\.?\s*[mM]\.?)?)\b")

# BBVA two-column: "24 marzo" alone on a line, then "2026, HH:MM" a few lines later
_RE_DAY_MONTH_ONLY = re.compile(
    r"^\s*(\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
    r"[a-z\u00e1\u00e9\u00ed\u00f3\u00fa.]*\.?)\s*$",
    re.IGNORECASE,
)
_RE_YEAR_TIME = re.compile(
    r"\b(\d{4})\s*,?\s*(\d{1,2}:\d{2}(?::\d{2})?(?:\s*[aApP]\.?\s*[mM]\.?)?)\b",
)

# BBVA variant: "08 mayo 2026," on one line, time on a nearby line
_RE_DATE_MONTH_YEAR_ONLY = re.compile(
    r"(\d{1,2}\s+(?:ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)"
    r"[a-z\u00e1\u00e9\u00ed\u00f3\u00fa.]*\.?\s*(?:de\s+)?\d{4}),?\s*$",
    re.IGNORECASE,
)


def _extract_fecha_transferencia(raw_text: str) -> Optional[str]:
    """Extrae fecha y hora de la transferencia preservando el formato original del comprobante.

    Soporta los formatos más comunes de la banca peruana:
    - DD/MM/YYYY HH:MM:SS           (Banco de la Nación)
    - DD/MM/YY HH:MM                (Caja Arequipa)
    - D mes YYYY, HH:MM             (BBVA / Scotiabank verde)
    - D Mes YYYY  HH:MM AM/PM       (Interbank)
    - D mes., HH:MM p. m.           (Scotiabank)
    - Fecha y Hora en líneas separadas  (Falabella)
    """
    lines = [ln.strip() for ln in raw_text.splitlines()]

    # Paso 1: fecha + hora en el mismo renglón (slash)
    for line in lines:
        m = _RE_FULL_SLASH_DT.search(line)
        if m:
            return m.group(1).strip()

    # Paso 2: fecha + hora en el mismo renglón (nombre de mes)
    for line in lines:
        m = _RE_FULL_MONTH_DT.search(line)
        if m:
            return m.group(1).strip()

    # Paso 3: texto multi-línea — concatena renglones consecutivos (ej. BBVA)
    for i in range(len(lines) - 1):
        combined = lines[i] + " " + lines[i + 1]
        m = _RE_FULL_MONTH_DT.search(combined)
        if m:
            return m.group(1).strip()

    # Paso 3b: BBVA layout — "24 marzo" solo en un renglón, "2026, HH:MM" unos renglones después
    for i, line in enumerate(lines):
        m_dm = _RE_DAY_MONTH_ONLY.search(line)
        if m_dm:
            day_month = m_dm.group(1).strip()
            for j in range(i + 1, min(i + 5, len(lines))):
                m_yt = _RE_YEAR_TIME.search(lines[j])
                if m_yt:
                    return f"{day_month} {m_yt.group(1)}, {m_yt.group(2).strip()}"

    # Paso 3c: BBVA variant — "08 mayo 2026," en un renglón, hora sola unos renglones después
    for i, line in enumerate(lines):
        m_dmy = _RE_DATE_MONTH_YEAR_ONLY.search(line)
        if m_dmy:
            date_str = m_dmy.group(1).strip()
            for j in range(i + 1, min(i + 5, len(lines))):
                m_time = _RE_TIME_ONLY.search(lines[j])
                if m_time:
                    return f"{date_str}, {m_time.group(1).strip()}"
            return date_str

    # Paso 4: fecha en un renglón, hora en un renglón cercano (ej. Falabella)
    for i, line in enumerate(lines):
        m_date = _RE_DATE_SLASH_ONLY.search(line)
        if m_date:
            date_str = m_date.group(1)
            for j in range(i + 1, min(i + 6, len(lines))):
                m_time = _RE_TIME_ONLY.search(lines[j])
                if m_time:
                    return f"{date_str} {m_time.group(1).strip()}"
            return date_str

    return None


def parse_transfer_text(raw_text: str) -> dict:
    """
    Extrae monto, número de operación, banco y fecha/hora de texto OCR crudo.

    Returns:
        {
            "monto": "4550.00" | None,
            "numero_operacion": "04349309" | None,
            "banco": "INTERBANK" | None,
            "fecha_transferencia": "24 marzo 2026, 10:24" | None,
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
        candidate = _normalize_op_number(m_ctx.group(1))
        if candidate:
            # Buscar continuación del número en las líneas siguientes al match
            # (BBVA parte el número en dos líneas con la etiqueta "operación" en medio)
            after = raw_text[m_ctx.end():]
            for next_line in after.splitlines()[:5]:
                stripped = next_line.strip()
                if not stripped:
                    continue  # línea vacía, saltar
                if re.fullmatch(r'\d{1,8}', stripped) and len(candidate) + len(stripped) <= 25:
                    # Es una cola de dígitos corta → parte del mismo número
                    candidate = candidate + stripped
                    break
                elif not any(c.isdigit() for c in stripped):
                    continue  # línea de etiqueta pura (ej. "operación"), saltar
                else:
                    break  # línea con contenido mixto → detener
            op_found = candidate
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

    # ── FECHA Y HORA DE TRANSFERENCIA ────────────────────────
    fecha_found = _extract_fecha_transferencia(raw_text)

    return {
        "monto": monto_found,
        "numero_operacion": op_found,
        "banco": banco_found,
        "fecha_transferencia": fecha_found,
    }

