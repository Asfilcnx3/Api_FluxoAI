from typing import Tuple
from datetime import datetime
import re

# Mapeo de nombres detectados a nombre estandarizado
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
    "banco nacional de mexico": "Banamex",
}
# Compilamos el patrón regex solo una vez para eficiencia
BANCO_REGEX = re.compile("|".join(BANCO_MAP.keys()))

# Creamos la lista de palabras clave generales
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "mit", "payclip, s. de r.l. de c.v", "clip", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "american express", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "clipmx", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup"
]

# Hacemos un dict con las palabras especificas que se buscan por banco
frases_bancos = {
    "banbajío": r"(?:iva |comision )?deposito negocios afiliados \(adquirente\)(?: optblue amex)?",
    "banorte": r"[a-zA-Z][a-zA-Z ]*?\s+\d{8}[cd]",
    "afirme": r"venta tpv(?:cr|db)",
    "hsbc": r"transf rec hsbcnet dep tpv\s*\d{7}|[A-Za-z0-9]{9} ganancias clip\s*\d{7}|deposito bpu\d{10}\s*\d{7}",
    "mifel": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
    "scotiabank": "transf interbancaria spei\s*\d{20}",
    "banregio": "tra\s+\d{7}-abono ventas\s+(?:tdd|tdc)",
    "santander": "deposito ventas del dia afil",
    "bbva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito|spei recibidobanorte|spei recibidosantander|spei recibidostp",
    "multiva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
    "banamex": r"(?:deposito ventas netas(?:.|\n)*?por evopaymx)"
}

# Unimos TODAS las alternativas (expresiones especificas y genéricas) en un solo grupo usando "|" (OR)
# Así, el motor de regex busca cualquiera de estas opciones.
def construir_regex_descripcion(banco_id: str):
    """
    Construye una regex uniendo las frases específicas de un banco con las palabras clave generales.
    """
    banco_id = banco_id.lower() # Aseguramos que la clave esté en minúsculas

    # Obtenemos la frase del banco si existe
    frase_especifica = frases_bancos.get(banco_id)

    # Creamos una lista de todas las frases a buscar
    todas_las_alternativas = list(palabras_clave_generales)
    if frase_especifica:
        todas_las_alternativas.insert(0, frase_especifica)

    return "|".join(todas_las_alternativas)

# Mejoramos el diccionario de expresiones
EXPRESIONES_REGEX = {
    "BanBajío": {
        "nombre_cliente": r"(.*?)\s+banco del bajio",
        "clabe_inter": r"clabe interbancaria1\s+(\d{18})\s+gat",
        "rfc": r"r\.f\.c\.\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo:\s*(\d{1,2} de [a-z]+)\s+al\s+(\d{1,2} de [a-z]+)\s+de\s+(\d{4})',
        "descripcion": (
            r"(\d{1,2} [a-z]{3})\s*"  # Grupo 1: Fecha (ej: "15 jul")
            r"(\d{7})\s*"             # Grupo 2: ID (ej: "1234567")
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("BanBajío") + # Grupo 3: La descripción completa. Captura todo el texto que contenga alguna palabra clave y que se encuentre entre el ID y el signo de dólar del monto.
            r"\$\s*([\d,]+\.\d{2})"    # Grupo 4: El monto
        ), # r"(\d{1,2} [a-z]{3}) (\d{7})(.*(?:iva |comision )?deposito negocios afiliados \(adquirente\)(?: optblue amex)?)\s\$\s*([\d,]+\.\d{2})"
        "comisiones": r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})",
        "depositos": r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})",
        "cargos": r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})",
        "saldo_promedio": r"del periodo en el año\s*\n\$\s*([\d,]+\.\d{2})",
    },
    "Banorte": {
        "nombre_cliente": r"estado de cuenta / enlace negocios (?:avanzada|basica)\s*\n\s*(.*)",
        "clabe_inter": r"(\d{3}\s+\d{3}\s+\d{11}\s+\d{1})",
        "rfc": r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo del\s*(\d{2}/[a-z]+/\d{4})\s+al\s+(\d{2}/[a-z]+/\d{4})',
        "descripcion": (
            r"(\d{2}-[a-z]{3}-\d{2})\s*" # Grupo 1: Fecha ("ej: ")
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("Banorte") + # Grupo 3: Descripción completa
            r"\s*([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r'(\d{2}-[a-z]{3}-\d{2})([a-zA-Z][a-zA-Z ]*?)\s+(\d{8}[cd])\s+([\d,]+\.\d{2})',
        "descripcion_clip_multilinea": (
            r'(\d{2}-[a-z]{3}-\d{2}).*?((spei recibido.*?([\d,]+\.\d{2}).*?\n(?:.*\n){1}.*?ganancias clip(?:.*\n){1}.*))'
        ),
        "descripcion_clip_traspaso": (
            r'(\d{2}-[a-z]{3}-\d{2}).*?((traspaso de cta.*?([\d,]+\.\d{2}).*\n.*?clip.*))'
        ),
        "descripcion_amex_multilinea": (
            r'(\d{2}-[a-z]{3}-\d{2}).*?((spei recibido.*?([\d,]+\.\d{2})(?:.*\n){2}.*?amexco(?:.*\n){1}.*))'
        ),
        "comisiones": r"total de comisiones cobradas / pagadas\s*\$\s*([\d,]+\.\d{2})",
        "depositos": r"total de depósitos\s*\$\s*([\d,]+\.\d{2})",
        "cargos": r"total de retiros\s*\$\s*([\d,]+\.\d{2})",
        "saldo_promedio": r"en el periodo.*:\s*\$\s*([\d,]+\.\d{2})",
    },
    "Afirme": {
        "nombre_cliente": r"fecha de emision\s+(.*?)\s+\d{20}\s+\d{4}-\d{2}-\d{2}",
        "clabe_inter": r"se indica:?\s+(\d{18})\s+clave bancaria",
        "rfc": r"r\.f\.c\.\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo\s+de\s+(\d{2}[a-z]{3}\d{4})\s*al\s*(\d{2}[a-z]{3}\d{4})',
        "descripcion": (
            r"(\d{2})" # Grupo 1: Fecha
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("Afirme") + # Grupo 2: Descripción completa
            r"(\d{6})(?: \d{7})?\s*" # Grupo 3: ID
            r"\$\s*([\d,]+\.\d{2})" # Grupo 4: Monto
        ), # r'(\d{2}) (venta tpv(?:cr|db)) (\d{6})(?: \d{7})? \$\s*([\d,]+\.\d{2})',
        "comisiones": r'total de comisiones\s+\$\s*([\d,]+\.\d{2})',
        "depositos": r'dep[oó]sitos\s+\$\s*([\d,]+\.\d{2})',
        "cargos": r'retiros\s+\$\s*([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio diario\s+\$\s*([\d,]+\.\d{2})',
    },
    # Es documento escaneado
    "Hsbc": {
        "nombre_cliente": r"\n\s*€.*?\n\s*([\w\s.,&áéíóúüñÁÉÍÓÚÜÑ\-]+s\.?a\.? de c\.?v\.?)\s*\n\s*-?\d{2}",
        "clabe_inter": r"(\d{18})\s+>\s+saldo final",
        "rfc": r"rfc.*?\n\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3}).*?d[ií]as transcurridos",
        "periodo": r'per[ií]odo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": (
            r"(\d{2})\.?\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("hsbc") + # Grupo 2: Expresión exacta y genericas
            r"([A-Za-z0-9]{8})?\s*" # Grupo 3: ID de la transacción
            r"\$\s*([\d,]+\.\d{2})" # Grupo 4: Monto
        ), # r'(\d{2})\.?\s+(transf rec hsbcnet dep tpv\s+\d{7})\s+([A-Za-z0-9]{8})?\s*\$\s*([\d,]+\.\d{2})',
        "comisiones": r'comisiones cobradas(?: en el mes)? \$([\d,]+\.\d{2})',
        "depositos": r'dep[éeóo]sitos/? \$ ([\d,]+\.\d{2})',
        "cargos": r'retiros/cargos \$ ([\d,]+\.\d{2})',
        "saldo_promedio": r'referencia/\s*\n(?:.*\n){3}\s*\$\s*([\d,]+\.\d{2})',
    },
    # Es multilinea -- Pendiente
    "Mifel": {
        "nombre_cliente": r"p[áa]gina\s+\{c:p\}\s+de\s+\{t:p\}\s*\n\s*.*?\s*\n\s*(.*?)\s+n[úu]mero de cliente",
        "clabe_inter": r"clabe\s+(\d{18})",
        "rfc": r"rfc\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": (
            r"(\d{2}/\d{2}/\d{4})\s*" # Grupo 1: Fecha
            r"([a-zA-Z]{3}\d{6}-\d)\s*" # Grupo 2: ID
            r"(%s)\s+" % construir_regex_descripcion("mifel") + # Grupo 3: Palabras exactas a encontrar
            r"(?:\s+\w+)?\s*" # Grupo 4: todo lo que está en las multiples lineas
            r"([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*\n(.+)" # Grupo 5: Monto
        ), # r'(\d{2}/\d{2}/\d{4})\s+([a-zA-Z]{3}\d{6}-\d)\s+(vta\. (?:cre|deb)\s+\d{4}\s+\d{7})(?:\s+\w+)?\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*\n(.+)',
        "comisiones": r'comisiones efectivamente cobradas\s+([\d,]+\.\d{2})',
        "depositos": r'[0-9]\.\s*dep[óo]sitos\s+\$?([\d,]+(?:\.\d{2})?)',
        "cargos": r'otros retiros\s+\$?([\d,]+(?:\.\d{2})?)',
        "saldo_promedio": r'saldo promedio diario\s+([\d,]+\.\d{2})',
    },
    # Scotiabank tiene un formato diferente -- multilinea pendiente
    "Scotiabank": {
        "nombre_cliente": r"(?:estado\s+de\s+cuenta|estadodecuenta).*\n(.*)",
        "clabe_inter": r"clabe\s+(\d{18})",
        "rfc": r"r\.f\.c\.cliente\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo\s+(\d{2}-[a-z]{3}-\d{2})/(\d{2}-[a-z]{3}-\d{2})',
        "descripcion": (
            r"(\d{2}\s+[a-z]{3})\s*" # Grupo 1: Fecha que estamos buscando
            r"(%s)\s+" % construir_regex_descripcion("scotiabank") + # Grupo 2: Descipción que estamos buscando
            r"\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*" # Grupo 3: Monto a encontrar y monto a ignorar
            r"\n((?:.*\n){6})" # Grupo 4: Lineas despues
        ), #r'(\d{2}\s+[a-z]{3})\s+transf interbancaria spei\s+(\d{20})\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*\n((?:.*\n){6})',
        "comisiones": r'comisiones\s*cobradas\s*\$([\d,]+\.\d{2})',
        "depositos": r'\(\+\)dep[óo]sitos\s*\$([\d,]+\.\d{2})',
        "cargos": r'\(-\)retiros\s*\$([\d,]+\.\d{2})',
        "saldo_promedio": r'sdo\.?\s*prom\.\s*\(1\)\s*de la cta\. diciembre\s*\$([\d,]+\.\d{2})',
    },
    "Banregio": {
        "nombre_cliente": r"\*\d{15,}\*\s*\n\s*(.+)",
        "clabe_inter": r"clabe\s+(\d{18})",
        "rfc": r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'del\s+(\d{2})\s+al\s+(\d{2})\s+de\s+([a-z]+)\s+(\d{4})',
        "descripcion": (
            r"(\d{2})" # Grupo 1: Fecha
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("banregio") + # Grupo 2: Regex a buscar junto con las genericas
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r'(\d{2})\s+(tra\s+\d{7}-abono ventas\s+(?:tdd|tdc))\s+([\d,]+\.\d{2})',
        "comisiones": r'comisiones efectivamente cobradas\s*\$([\d,]+\.\d{2})',
        "depositos": r'(?:\+?\s*abonos)\s*\$([\d,]+\.\d{2})',
        "cargos": r'-(?:\s*retiros|\s*otros cargos)\s*\$([\d,]+\.\d{2})',
        # banregio no tiene saldo promedio
        "saldo_promedio": r'sdo\.?\s*prom\.\s*\(1\)\s*de la cta\. diciembre\s*\$([\d,]+\.\d{2})',
    },
    # Santander es documento escaneado
    "Santander": {
        "nombre_cliente": r"grupofinancierosantander.*\n\s*(.*?)\s+codigo de cliente",
        "clabe_inter": r"cuenta clabe:\s+(\d{18})",
        "rfc": r"r\.f\.c\.\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo del (\d{2}-[a-z]{3}-\d{4}) al (\d{2}-[a-z]{3}-\d{4})',
        "descripcion": (
            r"(\d{2}-[a-z]{3}-\d{4})\s*" # Grupo 1: Fecha
            r"(?:\s*0){7}\s*" # Grupo 2: ID
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("santander") + # Grupo 3: Busqueda con regex
            r"\.-(\d{9})\s*" # Grupo 4: Referencia
            r"([\d,]+\.\d{2})" # Grupo 5: Monto
        ), # r"(\d{2}-[a-z]{3}-\d{4})\s*(?:\s*0){7}\s*(deposito ventas del dia afil)\.-(\d{9})\s+([\d,]+\.\d{2})",
        "comisiones": r'comisiones cobradas\s*\$?([\d,]+\.\d{2})',
        "depositos": r'(?:dep.{0,10}sitos)\s*\$?([\d,]+\.\d{2})',
        "cargos": r'(?:otros cargos)\s*\$?([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio\s*\$?([\d,]+\.\d{2})',
    },
    "BBVA": {
        "nombre_cliente": r"no\. de cliente.*\n\s*(.*?)\s*\n.*?r\.f\.c",
        "clabe_inter": r"cuenta clabe\s+(\d{18})",
        "rfc": r"r\.f\.c\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo del (\d{2}/\d{2}/\d{4}) al (\d{2}/\d{2}/\d{4})',
        "descripcion": (
            r"(\d{2}/[a-z]{3})\s*\d{2}/[a-z]{3}" # Grupo 1: Fecha
            r"(?:\s+[a-zA-Z]\d{2})?" # Grupo 2: Referencia
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("bbva") + # Grupo 3: Regex especifica
            r"([\d,]+\.\d{2})\s*\n.*?(\d{9})" # Grupo 4 y 5: ID y monto
        ), # r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}(?:\s+[a-zA-Z]\d{2})?\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito|spei recibidobanorte|spei recibidosantander|spei recibidostp)\s+([\d,]+\.\d{2})\s*\n.*?(\d{9})',
        "comisiones": r'total comisiones\s+([\d,]+\.\d{2})',
        "depositos": r'dep[óo]sitos\s*/\s*abonos\s*\(\+\)\s*\d+\s+([\d,]+\.\d{2})',
        "cargos": r'retiros\s*/\s*cargos\s*\(-\)\s*\d+\s+([\d,]+\.\d{2})',
        "saldo_promedio": r'saldo promedio\s+([\d,]+\.\d{2})',
    },
    "Multiva": {
        "nombre_cliente": r"comprobante fiscal\s+([\w\s.,&áéíóúüñÁÉÍÓÚÜÑ\-]+?)\s+fecha de expedici[oó]n",
        "clabe_inter": r"clabe\s+(\d{18})",
        "rfc": r"rfc\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r'per[ií]odo del:\s*(\d{2}-[a-z]+-\d{4})\s+al\s+(\d{2}-[a-z]+-\d{4})',
        # Multiva no tiene conceptos claros aún
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito)\s+([\d,]+\.\d{2})\s*\n(\d{9})',
        "comisiones": r'comisiones cobradas\/bonificaciones\s+([\d,]+\.\d{2})',
        "depositos": r'retiros\/depósitos\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})',
        "cargos": r'retiros\/depósitos\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}',
        "saldo_promedio": r'saldo promedio\s+([\d,]+\.\d{2})',
    },
    "Banamex": {
        "nombre_cliente": r"cuenta priority\s+([\w\s.,&áéíóúüñÁÉÍÓÚÜÑ\-]+?)\s+detalle",
        "clabe_inter": r"clabe interbancaria\s+(\d{18})",
        "rfc": r"rfc\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})",
        "periodo": r"per[ií]odo del (\d{1,2}) al (\d{1,2}) de ([a-z]+) del (\d{4})",
        "descripcion": (
            r"(\d{2}\s*[a-z]{3})\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("banamex") + # Grupo 2: Descripción exacta
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r"(\d{2}\s+[a-z]{3})\s*(deposito ventas netas(?:.|\n)*?por evopaymx)\s*([\d,]+\.\d{2})",
        "comisiones": r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})",
        "depositos": r"dep[oó]sitos\s*([\d,]+\.\d{2})",
        "cargos": r"otros cargos\s*([\d,]+\.\d{2})",
        "saldo_promedio": r"saldo promedio mensual\s*([\d,]+\.\d{2})",
    }
}

def encontrar_banco(texto):
    """
    Busca el nombre del banco en el texto normalizado y retorna su versión estandarizada. Si no lo encuentra, devuelve "Banco no identificado".

    Args:
        texto (str): El texto normalizado.

    Returns:
        str: El nombre del banco estandarizado o "Banco no identificado".
    """
    coincidencia = BANCO_REGEX.search(texto)
    if coincidencia:
        banco_raw = coincidencia.group(0)
        return BANCO_MAP.get(banco_raw, banco_raw)
    return "Banco no identificado"

def construir_descripcion(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    """
    Esta función construye la descripción que será presentada en la API a futuro, cada banco tiene su forma de construcción

    Args:
        Transacciones (Tupla): Transacciones de un banco.
        Banco (str): Banco.

    Returns:
        Tuple[str, str]: La descripción y el monto de la transacción.
    """
    if banco in ['Banorte', 'Afirme', 'Hsbc', 'Santander']:
        # fecha, descripción o parte de esta, monto
        return " ".join(transaccion[1:-1]), transaccion[-1]
    elif banco in ['BBVA', 'Multiva']:
        # fecha, descripción, monto, final de la descripción
        return " ".join([transaccion[1], transaccion[-1]]), transaccion[-2]
    elif banco in ['Banregio', "Banamex"]:
        # fecha, transacción, monto
        return " ".join([transaccion[1]]), transaccion[-1]
    elif banco == 'Scotiabank':
        # fecha, final de transacción, monto, inicio de transacción
        return " ".join([transaccion[-1], transaccion[1]]), transaccion[-2]
    elif banco == 'Mifel':
        # Monto, final de transacción, inicio de transacción, monto, mitad de transacción
        return " ".join([transaccion[2], transaccion[-1], transaccion[1]]), transaccion[-2]
    elif banco == 'BanBajío':
        # monto, final de transacción, inicio de transacción, monto
        return " ".join([transaccion[2], transaccion[1]]), transaccion[-1]
    return "", "0.0"

def normalizar_fecha_es(fecha_str: str) -> str:
    """
    Parsea todas las fechas en forma de str en varios formatos diferentes para entregar un formato único normalizado "dd-mes-YYYY".
    """
    fecha_str = fecha_str.lower().strip()

    # Diccionarios de meses
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

    # Reemplaza el mes en español por inglés para que strptime lo entienda
    for esp, eng in meses_largos_es_a_en.items():
        fecha_str = fecha_str.replace(esp, eng)
    # Reemplaza los meses abreviados en español por inglés para que strptime lo entienda
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
            # strptime ahora puede entender la fecha traducida
            fecha = datetime.strptime(fecha_str, fmt)
            # Devuelve el formato "2025-12-25"
            return fecha.strftime("%Y-%m-%d")
        except ValueError:
            # Si el formato no es el correcto, simplemente continúa con el siguiente
            continue

    # Si después de probar todos los formatos no se pudo parsear, lanza un error.
    raise ValueError(f"No se pudo parsear la fecha en ninguno de los formatos conocidos: {fecha_str}")