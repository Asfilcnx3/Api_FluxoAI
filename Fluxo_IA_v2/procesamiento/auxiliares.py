from typing import Tuple
from datetime import datetime
import re

BANCO_MAP = {
    "banco mercantil del norte": "Banorte",
    "banco del bajio": "BanBajío",
    "banca afirme": "Afirme",
    "grupo financiero hsbc": "Hsbc",
    "grupo financiero mifel": "Mifel",
    "scotiabank": "Scotiabank",
    "banco regional": "Banregio",
    "grupo financiero bbva": "BBVA",
    "banco multiva": "Multiva",
    "banco santander": "Santander",
    "bancosantander": "Santander",
}
BANCO_REGEX = re.compile("|".join(BANCO_MAP.keys()))

EXPRESIONES_REGEX = {
    "BanBajío": {
        "periodo": r'periodo:\s*(\d{1,2} de [a-z]+)\s+al\s+(\d{1,2} de [a-z]+)\s+de\s+(\d{4})',
        "descripcion": r"(\d{1,2} [a-z]{3}) (\d{7})(.*(?:iva |comision )?deposito negocios afiliados \(adquirente\)(?: optblue amex)?)\s\$\s*([\d,]+\.\d{2})",
        "comisiones": r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})",
        "depositos": r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})",
        "cargos": r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})",
        "saldo_promedio": r"del periodo en el año\s*\n\$\s*([\d,]+\.\d{2})",
    },
    "Banorte": {
        "periodo": r'periodo del\s*(\d{2}/[a-z]+/\d{4})\s+al\s+(\d{2}/[a-z]+/\d{4})',
        "descripcion": r'(\d{2}-[a-z]{3}-\d{2})([a-zA-Z][a-zA-Z ]*?)\s+(\d{8}[cd])\s+([\d,]+\.\d{2})',
        "comisiones": r"total de comisiones cobradas / pagadas\s*\$\s*([\d,]+\.\d{2})",
        "depositos": r"total de depósitos\s*\$\s*([\d,]+\.\d{2})",
        "cargos": r"total de retiros\s*\$\s*([\d,]+\.\d{2})",
        "saldo_promedio": r"en el periodo.*:\s*\$\s*([\d,]+\.\d{2})",
    },
    "Afirme": {
        "periodo": r'per[ií]odo\s+de\s+(\d{2}[a-z]{3}\d{4})\s*al\s*(\d{2}[a-z]{3}\d{4})',
        "descripcion": r'(\d{2}) (venta tpv(?:cr|db)) (\d{6})(?: \d{7})? \$\s*([\d,]+\.\d{2})',
        "comisiones": r'total de comisiones\s+\$\s*([\d,]+\.\d{2})',
        "depositos": r'dep[oó]sitos\s+\$\s*([\d,]+\.\d{2})',
        "cargos": r'retiros\s+\$\s*([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio diario\s+\$\s*([\d,]+\.\d{2})',
    },
    "Hsbc": {
        "periodo": r'per[ií]odo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": r'(\d{2})\.?\s+(transf rec hsbcnet dep tpv\s+\d{7})\s+([A-Za-z0-9]{8})?\s*\$\s*([\d,]+\.\d{2})',
        "comisiones": r'comisiones cobradas(?: en el mes)? \$([\d,]+\.\d{2})',
        "depositos": r'dep[éeóo]sitos/? \$ ([\d,]+\.\d{2})',
        "cargos": r'retiros/cargos \$ ([\d,]+\.\d{2})',
        "saldo_promedio": r'referencia/\s*\n(?:.*\n){3}\s*\$\s*([\d,]+\.\d{2})',
    },
    "Mifel": {
        "periodo": r'periodo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": r'(\d{2}/\d{2}/\d{4})\s+([a-zA-Z]{3}\d{6}-\d)\s+(vta\. (?:cre|deb)\s+\d{4}\s+\d{7})(?:\s+\w+)?\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*\n(.+)',
        "comisiones": r'comisiones efectivamente cobradas\s+([\d,]+\.\d{2})',
        "depositos": r'[0-9]\.\s*dep[óo]sitos\s+\$?([\d,]+(?:\.\d{2})?)',
        "cargos": r'otros retiros\s+\$?([\d,]+(?:\.\d{2})?)',
        "saldo_promedio": r'saldo promedio diario\s+([\d,]+\.\d{2})',
    },
    "Scotiabank": {
        "periodo": r'periodo\s+(\d{2}-[a-z]{3}-\d{2})/(\d{2}-[a-z]{3}-\d{2})',
        "descripcion": r'(\d{2}\s+[a-z]{3})\s+transf interbancaria spei\s+(\d{20})\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*\n((?:.*\n){6})',
        "comisiones": r'comisiones\s*cobradas\s*\$([\d,]+\.\d{2})',
        "depositos": r'\(\+\)dep[óo]sitos\s*\$([\d,]+\.\d{2})',
        "cargos": r'\(-\)retiros\s*\$([\d,]+\.\d{2})',
        "saldo_promedio": r'sdo\.?\s*prom\.\s*\(1\)\s*de la cta\. diciembre\s*\$([\d,]+\.\d{2})',
    },
    "Banregio": {
        "periodo": r'del\s+(\d{2})\s+al\s+(\d{2})\s+de\s+([a-z]+)\s+(\d{4})',
        "descripcion": r'(\d{2})\s+(tra\s+\d{7}-abono ventas\s+(?:tdd|tdc))\s+([\d,]+\.\d{2})',
        "comisiones": r'comisiones efectivamente cobradas\s*\$([\d,]+\.\d{2})',
        "depositos": r'(?:\+?\s*abonos)\s*\$([\d,]+\.\d{2})',
        "cargos": r'-(?:\s*retiros|\s*otros cargos)\s*\$([\d,]+\.\d{2})',
        "saldo_promedio": r'sdo\.?\s*prom\.\s*\(1\)\s*de la cta\. diciembre\s*\$([\d,]+\.\d{2})',
    },
    "Santander": {
        "periodo": r'periodo del (\d{2}-[a-z]{3}-\d{4}) al (\d{2}-[a-z]{3}-\d{4})',
        "descripcion": r"(\d{2}-[a-z]{3}-\d{4})\s*(?:\s*0){7}\s*(deposito ventas del dia afil)\.-(\d{9})\s+([\d,]+\.\d{2})",
        "comisiones": r'comisiones cobradas\s*\$?([\d,]+\.\d{2})',
        "depositos": r'(?:dep.{0,10}sitos)\s*\$?([\d,]+\.\d{2})',
        "cargos": r'(?:otros cargos)\s*\$?([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio\s*\$?([\d,]+\.\d{2})',
    },
    "BBVA": {
        "periodo": r'periodo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}(?:\s+[a-zA-Z]\d{2})?\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito|spei recibidobanorte|spei recibidosantander|spei recibidostp)\s+([\d,]+\.\d{2})\s*\n.*?(\d{9})',
        "comisiones": r'total comisiones\s+([\d,]+\.\d{2})',
        "depositos": r'dep[óo]sitos\s*/\s*abonos\s*\(\+\)\s*\d+\s+([\d,]+\.\d{2})',
        "cargos": r'retiros\s*/\s*cargos\s*\(-\)\s*\d+\s+([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio\s+([\d,]+\.\d{2})',
    },
    "Multiva": {
        "periodo": r'periodo del:\s*(\d{2}-[a-z]+-\d{4})\s+al\s+(\d{2}-[a-z]+-\d{4})',
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito)\s+([\d,]+\.\d{2})\s*\n(\d{9})',
        "comisiones": r'comisiones cobradas\/bonificaciones\s+([\d,]+\.\d{2})',
        "depositos": r'retiros\/depósitos\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})',
        "cargos": r'retiros\/depósitos\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}',
        "saldo_promedio": r'saldo promedio\s+([\d,]+\.\d{2})',
    },
}

def encontrar_banco(texto):
    coincidencia = BANCO_REGEX.search(texto)
    if coincidencia:
        banco_raw = coincidencia.group(0)
        return BANCO_MAP.get(banco_raw, banco_raw)
    return "Banco no identificado"

def construir_descripcion(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    if banco in ['Banorte', 'Afirme', 'Hsbc', 'Santander']:
        return " ".join(transaccion[1:-1]), transaccion[-1]
    elif banco in ['BBVA', 'Multiva']:
        return " ".join([transaccion[1], transaccion[-1]]), transaccion[-2]
    elif banco == 'Scotiabank':
        return " ".join([transaccion[-1], transaccion[1]]), transaccion[-2]
    elif banco == 'Banregio':
        return " ".join([transaccion[1]]), transaccion[-1]
    elif banco == 'Mifel':
        return " ".join([transaccion[2], transaccion[-1], transaccion[1]]), transaccion[-2]
    elif banco == 'BanBajío':
        return " ".join([transaccion[2], transaccion[1]]), transaccion[-1]
    return "", "0.0"

def normalizar_fecha_es(fecha_str: str) -> str:
    fecha_str = fecha_str.lower().strip()

    meses_abreviado_es_a_en = {
        "ene": "jan", "feb": "feb", "mar": "mar", "abr": "apr", "may": "may",
        "jun": "jun", "jul": "jul", "ago": "aug", "sep": "sep", "oct": "oct",
        "nov": "nov", "dic": "dec"
    }

    meses_largos_es_a_en = {
        "enero": "january", "febrero": "february", "marzo": "march",
        "abril": "april", "mayo": "may", "junio": "june",
        "julio": "july", "agosto": "august", "septiembre": "september",
        "octubre": "october", "noviembre": "november", "diciembre": "december"
    }

    for esp, eng in meses_largos_es_a_en.items():
        fecha_str = fecha_str.replace(esp, eng)
    for esp, eng in meses_abreviado_es_a_en.items():
        fecha_str = fecha_str.replace(esp, eng)

    formatos = [
        "%d%b%Y",
        "%d%B%Y",
        "%d/%m/%Y",
        "%d-%B-%Y",
        "%d/%B/%Y",
        "%d-%b-%y",
        "%d-%B-%y",
        "%d-%b-%Y",
        "%d %B %Y",
        "%d de %B de %Y"
    ]

    for fmt in formatos:
        try:
            fecha = datetime.strptime(fecha_str, fmt)
            return fecha.strftime("%Y-%m-%d")
        except ValueError:
            continue

    raise ValueError(f"No se pudo parsear la fecha en ninguno de los formatos conocidos: {fecha_str}")