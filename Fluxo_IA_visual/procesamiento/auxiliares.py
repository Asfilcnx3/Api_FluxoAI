from typing import Tuple, List, Any, Dict, Optional, Union
from ..models import ResultadoExtraccion, ErrorRespuesta, ResultadoAnalisisIA, ResultadoTPV
import re

PALABRAS_CLAVE_VERIFICACION = re.compile(
    r"banco|banca|cliente|estado de cuenta|rfc|periodo"
)

# Creamos la lista e palabras excluidas
PALABRAS_EXCLUIDAS = ["comision", "iva", "com.", "-com x", "cliente stripe"]

# Creamos la lista de palabras clave generales (quitamos mit y american express)
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "payclip, s. de r.l. de c.v", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup"
]

CONFIGURACION_BANCOS = {
    "banorte": {
        "alias": ["banco mercantil del norte"],
        "rfc_pattern": [r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total de comisiones cobradas / pagadas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"total de depósitos\s*\$\s*([\d,]+\.\d{2})"]
    },
    "banbajío": {
        "alias": ["banco del bajio"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"saldo anterior \(\+\) depositos \(\-\) cargos saldo actual\s*\n\$\s*[\d,.]+\s+\$\s*([\d,]+\.\d{2})"]
    },
    "afirme": {
        "alias": ["banca afirme"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total de comisiones\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s+\$\s*([\d,]+\.\d{2})"]
    },
    "hsbc": {
        "alias": ["grupo financiero hsbc"],
        "rfc_pattern": [r"rfc[^\n]*\n\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"], # Versión multilínea
        "comisiones_pattern": [r"comisiones cobradas(?: en el mes)? \$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[éeóo]sitos/? \$ ([\d,]+\.\d{2})"]
    },
    "mifel": {
        "alias": ["grupo financiero mifel"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"[0-9]\.\s*dep[óo]sitos\s+\$?([\d,]+(?:\.\d{2})?)"]
    },
    "scotiabank": {
        "alias": ["scotiabank inverlat"],
        "rfc_pattern": [r"r\.f\.c\.cliente\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones\s*cobradas\s*\$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"\(\+\)dep[óo]sitos\s*\$([\d,]+\.\d{2})"]
    },
    "banregio": {
        "alias": ["banco regional"],
        "rfc_pattern": [r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$([\d,]+\.\d{2})"],
        "depositos_pattern": [r"(?:\+?\s*abonos)\s*\$([\d,]+\.\d{2})"]
    },
    "bbva": {
        "alias": ["grupo financiero bbva"],
        "rfc_pattern": [r"r\.f\.c\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"total comisiones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[óo]sitos\s*/\s*abonos\s*\(\+\)\s*\d+\s+([\d,]+\.\d{2})"]
    },
    "multiva": {
        "alias": ["banco multiva"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas\/bonificaciones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"retiros\/depósitos\s+[\d,]+\.\d{2}\s+([\d,]+\.\d{2})"]
    },
    "santander": {
        "alias": ["banco santander", "bancosantander"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas\s*.+?\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"(?:dep.{0,10}sitos)\s*\$?([\d,]+\.\d{2})"]
    },
    "banamex": {
        "alias": ["banco nacional de mexico", "banco nacional de méxico"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "citibanamex":{
        "alias": ["citibanamex"],
        "rfc_pattern": [r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente cobradas\s*\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "bancrea": {
        "alias": ["banco bancrea"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas en el per[ií]odo\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos\s*([\d,]+\.\d{2})"]
    },
    "inbursa": {
        "alias": ["banco inbursa"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"en el periodo\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"abonos\s*([\d,]+\.\d{2})"]
    },
    "monex": {
        "alias": ["banco monex"],
        "rfc_pattern": [r"rfc titular:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones\s+([\d,]+\.\d{2})"],
        "depositos_pattern": [r"total abonos:\s*([\d,]+\.\d{2})"]
    },
    "azteca": {
        "alias": ["banco azteca"],
        "rfc_pattern": [r"rfc:\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones[\s\S]*?\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos[\s\S]*?\$\s*([\d,]+\.\d{2})"]
    },
    "bankaool": {
        "alias": ["bankaool"],
        "rfc_pattern": [r"rfc\s+([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones cobradas[\s\S]*?\$\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[oó]sitos[\s\S]*?\$\s*([\d,]+\.\d{2})"]
    },
    "intercam": {
        "alias": ["intercuenta enlace intercam"],
        "rfc_pattern": [r"r\.f\.c\.\s*([a-zA-ZÑ&]{3,4}\d{6}[a-zA-Z0-9]{2,3})"],
        "comisiones_pattern": [r"comisiones efectivamente\s*([\d,]+\.\d{2})"],
        "depositos_pattern": [r"dep[éeóo]sitos\s*([\d,]+\.\d{2})"]
    },
}

ALIAS_A_BANCO_MAP = {}

# Crear un mapa de alias a nombre estándar ("banco del bajio" -> "banbajío")
for nombre_std, config in CONFIGURACION_BANCOS.items():
    # Añadimos el Alias
    for alias in config["alias"]:
        ALIAS_A_BANCO_MAP[alias] = nombre_std

# Compilar la regex para detectar CUALQUIER nombre de banco
BANCO_DETECTION_REGEX = re.compile("|".join(ALIAS_A_BANCO_MAP.keys()))

PATRONES_COMPILADOS = {}
for nombre_str, config in CONFIGURACION_BANCOS.items():
    PATRONES_COMPILADOS[nombre_str] = {} # Inicializa el diccionario para el banco
    
    # Itera dinámicamente sobre todas las claves de patrones (rfc_pattern, comisiones_pattern, etc.)
    for key, pattern_list in config.items():
        if key.endswith("_pattern"):
            if not pattern_list:
                continue
            
            # UNIMOS LA LISTA ED PATRONES EN UNA SOLA REGEX "|" y lo envolvimos en (?:...)
            patron_combinado = "|".join(f"(?:{p})" for p in pattern_list)

            # Guardamos el patrón compilado con un nombre de clave limpio (sin '_pattern')
            nombre_clave = key.replace("_pattern", "")
            PATRONES_COMPILADOS[nombre_str][nombre_clave] = re.compile(patron_combinado)

def extraer_unico(d: dict, clave: str):
    lista = d.get(clave, [])
    return lista[0] if lista else None

def extraer_datos_por_banco(texto: str) -> Dict[str, Any]:
    """
    Analiza el texto para identificar el banco y luego extrae datos específicos
    (como RFC, comisiones, depósitos, etc.) usando la configuración para ese banco.
    """
    resultados = {
        "banco": None,
        "rfc": None,
        "comisiones": None,
        "depositos": None, 
    }

    if not texto:
        return resultados

    # --- 1. Identificar el banco ---
    match_banco = BANCO_DETECTION_REGEX.search(texto)
    if not match_banco:
        return resultados

    banco_estandarizado = ALIAS_A_BANCO_MAP.get(match_banco.group(0))
    resultados["banco"] = banco_estandarizado.upper()

    patrones_del_banco = PATRONES_COMPILADOS.get(banco_estandarizado)
    if not patrones_del_banco:
        return resultados

    # --- 2. Extraer datos crudos con findall ---
    datos_crudos = {}
    for clave, patron in patrones_del_banco.items():
        datos_crudos[clave] = re.findall(patron, texto)

    # --- 3. Procesar resultados con extraer_unico ---
    for nombre_clave in patrones_del_banco.keys():
        valor_capturado = extraer_unico(datos_crudos, nombre_clave)

        if valor_capturado:
            # Si el campo es numérico
            if nombre_clave in ["comisiones", "depositos", "cargos", "saldo_promedio"]:
                try:
                    monto_limpio = str(valor_capturado).replace(",", "").replace("$", "").strip()
                    resultados[nombre_clave] = float(monto_limpio)
                except (ValueError, TypeError):
                    resultados[nombre_clave] = None
            else:  
                resultados[nombre_clave] = str(valor_capturado).upper()

    return resultados

# Creamos el prompt del modelo a utilizar
prompt_base = """
Estas imágenes son de las primeras páginas de un estado de cuenta bancario, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- banco # debe ser el nombre corto, por ejemplo, "banco del bajío" es banbajío
- nombre_cliente
- clabe_interbancaria # puede aparecer como clabe
- rfc # estructura válida del RFC o "Registro Federal de Contribuyentes": 3 o 4 letras, seguido de 6 números y 3 caracteres alfanuméricos (por ejemplo: ABC950422QA9 o ABCD950422QA9). Asegúrate de que sea exactamente igual al que aparece visualmente junto a la palabra "RFC".
- periodo_inicio # Devuelve en formato "2025-12-25"
- periodo_fin # Devuelve en formato "2025-12-25"
- comisiones # aparece como comisiones o comisiones efectivamente cobradas, toma el más grande solamente
- cargos # aparece como "cargos", "retiros" u "otros retiros", toma el más grande solamente
- depositos # aparece como "depositos" o "abonos", toma el más grande solamente
- saldo_promedio

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
"""

# Hacemos un dict con las palabras especificas que se buscan por banco
frases_bancos = {
    "banbajío": r"(?:iva |comision )?deposito negocios afiliados \(adquirente\)(?: optblue amex)?",
    "banorte": r".*?\d{8}[cd]",
    #          r"[a-zA-Z][a-zA-Z ]*?\s+\d{8}[cd]",
    "afirme": r"venta tpv(?:cr|db)",
    "hsbc": r"transf[\s~]*rec[\s~]*hsbcnet[\s~]*tpv[\s~]*(?:db|cr)?|transf[\s~]*rec[\s~]*hsbcnet[\s~]*dep[\s~]*tpv|deposito[\s~]*bpu\d{10}",
    "mifel": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
    # Scotiabank no tiene una para una línea
    "scotiabank": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
    "banregio": r"tra\s+\d{7}-abono ventas\s+(?:tdd|tdc)",
    "santander": "deposito ventas del dia afil",
    "bbva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
    "multiva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
    "citibanamex": r"(?:deposito ventas netas(?:.|\n)*?por evopaymx)",
    "banamex": r"(?:deposito ventas netas(?:.|\n)*?por evopaymx)",
    # Azteca no tiene una para una línea
    "azteca": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
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
    "banbajío": {
        "descripcion": (
            r"(\d{1,2} [a-z]{3})\s*"  # Grupo 1: Fecha (ej: "15 jul")
            r"(\d{7})\s*"             # Grupo 2: ID (ej: "1234567")
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("BanBajío") + # Grupo 3: La descripción completa. Captura todo el texto que contenga alguna palabra clave y que se encuentre entre el ID y el signo de dólar del monto.
            r"\$\s*([\d,]+\.\d{2})"    # Grupo 4: El monto
        ), # r"(\d{1,2} [a-z]{3}) (\d{7})(.*(?:iva |comision )?deposito negocios afiliados \(adquirente\)(?: optblue amex)?)\s\$\s*([\d,]+\.\d{2})"
    },
    "banorte": {
        "descripcion": (
            r"(\d{2}-[a-z]{3}-\d{2})\s*" # Grupo 1: Fecha ("ej: ")
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("Banorte") + # Grupo 3: Descripción completa
            r"\s*([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r'(\d{2}-[a-z]{3}-\d{2})([a-zA-Z][a-zA-Z ]*?)\s+(\d{8}[cd])\s+([\d,]+\.\d{2})',
        "descripcion_clip_multilinea": ( # spei recibido ganancias clip
            r'(\d{2}-[a-z]{3}-\d{2}).*?((spei recibido.*?([\d,]+\.\d{2}).*?\n(?:.*\n){1}.*?ganancias clip(?:.*\n){1}.*))'
        ),
        "descripcion_traspaso_multilinea": ( # traspaso de cta clip
            r'(\d{2}-[a-z]{3}-\d{2}).*?((traspaso de cta.*?([\d,]+\.\d{2}).*\n.*?clip.*))'
        ),
        "descripcion_amex_multilinea": ( # spei recibido amexco
            r'(\d{2}-[a-z]{3}-\d{2}).*?((spei recibido.*?([\d,]+\.\d{2})(?:.*\n){2}.*?amexco(?:.*\n){1}.*))'
        ),
    },
    "afirme": {
        "descripcion": (
            r"(\d{2})" # Grupo 1: Fecha
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("Afirme") + # Grupo 2: Descripción completa
            r"(\d{6})(?: \d{7})?\s*" # Grupo 3: ID
            r"\$\s*([\d,]+\.\d{2})" # Grupo 4: Monto
        ), # r'(\d{2}) (venta tpv(?:cr|db)) (\d{6})(?: \d{7})? \$\s*([\d,]+\.\d{2})',
        "descripcion_clip_multilinea": ( # venta tdd / venta tdc (una línea pero diferente forma de arquitectura)
            r"(venta tpv(?:cr|db)\s*\d{8})\s+(\d{2}/\d{2}/\d{2})\s+\d{7,8}\s+\$\d{1,3}(?:,\d{3})*\.\d{2}\s+\$([\d,]+\.\d{2})"
        ),
    },
    "hsbc": {
        "descripcion": (
            r"([0-9a-zA-Z]{1,2})\.?\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("hsbc") + # Grupo 2: Expresión exacta y genericas
            r"(\d{6,8})\s+([a-zA-Z0-9]{4,10})\s*" # Grupo 3: ID de la transacción
            r"\$?\s*([\d,]+\.\d{2})" # Grupo 4: Monto
        ), # r'(\d{2})\.?\s+(transf rec hsbcnet dep tpv\s+\d{7})\s+([A-Za-z0-9]{8})?\s*\$\s*([\d,]+\.\d{2})',
    },
    "mifel": {
        "descripcion": ( # esta descripción no funciona
            r"(\d{2}/\d{2}/\d{4})\s*" # Grupo 1: Fecha
            r"([a-zA-Z]{3}\d{6}-\d)\s*" # Grupo 2: Referencia
            r"(%s)\s+" % construir_regex_descripcion("mifel") + # Grupo 3: Palabras exactas a encontrar
            r"(?:\s+\w+)?\s*" # Grupo 4: todo lo que está en las multiples lineas
            r"([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*\n(.+)" # Grupo 5: Monto
        ), # r'(\d{2}/\d{2}/\d{4})\s+([a-zA-Z]{3}\d{6}-\d)\s+(vta\. (?:cre|deb)\s+\d{4}\s+\d{7})(?:\s+\w+)?\s+([\d,]+\.\d{2})\s+[\d,]+\.\d{2}\s*\n(.+)',
        "descripcion_clip_multilinea": ( # es vta. deb o cre
            r"(?m)^(\d{2}/\d{2}/\d{4})\s+(smf\d{6}-\d)\s+(vta\. (?:deb|cre).*?)(\d{1,3}(?:,\d{3})*\.\d{2}).*\n(.*)"
        ),
        "descripcion_traspaso_multilinea": ( # es transferencia spei bn
            r"(\d{2}/\d{2}/\d{4})\s*(smf\d{6}-\d)\s*(transferencia spei bn)\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*[\d,]+\.\d{2}\s*\n(.*)"
        ),
    },
    "scotiabank": {
        "descripcion": (
            r"(\d{2}\s+[a-z]{3})\s*" # Grupo 1: Fecha que estamos buscando
            r"(%s)\s+" % construir_regex_descripcion("scotiabank") + # Grupo 2: Descipción que estamos buscando
            r"\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*" # Grupo 3: Monto a encontrar y monto a ignorar
            r"\n((?:.*\n){6})" # Grupo 4: Lineas despues
        ), #r'(\d{2}\s+[a-z]{3})\s+transf interbancaria spei\s+(\d{20})\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*\n((?:.*\n){6})',
        "descripcion_clip_multilinea": ( # spei pocket deposito bpu
            r"(\d{2}\s+[a-z]{3})\s*(transf interbancaria spei\s*\d{20}\s*\$\s*([\d,]+\.\d{2})\s*\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,9}.*?deposito bpu.*?\n(?:.*?\n){1,5}.*?pocket de latinoamerica sapi.*?\n.*?\n)"
        # r"(\d{2}\s+[a-z]{3})\s*(transf interbancaria spei\s+.*?\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2})"
        ),
        "descripcion_traspaso_multilinea": ( # spei first data dep
            r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\n\s*transf interbancaria spei(?:.*?\n){1,3}.*?dep.*?\n(?:.*?\n)*?.*?first data merchant services m)"
        # r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,10}.*?dep.*?\n(?:.*?\n){1,5}.*?first data merchant services m.*?\n.*?\n)"
        ),
        "descripcion_amex_multilinea": ( # spei american express amexco
            r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\n\s*transf interbancaria spei(?:.*?\n){1,3}.*?.*?amexco se.*?\n(?:.*?\n)*?.*?american express company mexic)"
        ),
    },
    "banregio": {
        "descripcion": (
            r"(\d{2})" # Grupo 1: Fecha
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("banregio") + # Grupo 2: Regex a buscar junto con las genericas
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r'(\d{2})\s+(tra\s+\d{7}-abono ventas\s+(?:tdd|tdc))\s+([\d,]+\.\d{2})',
    },
    "santander": {
        "descripcion": (
            r"(\d{2}-[a-z]{3}-\d{4})\s*" # Grupo 1: Fecha
            r"(?:\s*0){7}\s*" # Grupo 2: ID
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("santander") + # Grupo 3: Busqueda con regex
            r"\.-(\d{9})\s*" # Grupo 4: Referencia
            r"([\d,]+\.\d{2})" # Grupo 5: Monto
        ),
        "descripcion_clip_multilinea": ( # Deposito BPU
            r"(\d{2}-[a-z]{3}-\d{4})\s*(\d{7})\s*(abono transferencia spei hora\s+\d{2}:\d{2}:\d{2}\s*([\d,]+\.\d{2}).*?\n\s*recibido de stp.*?\n[\s\S]*?deposito bpu)"
        ),
    },
    "bbva": {
        "descripcion": (
            r"(\d{2}/[a-z]{3})\s*\d{2}/[a-z]{3}" # Grupo 1: Fecha
            r"(?:\s+[a-zA-Z]\d{2})?" # Grupo 2: Referencia
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("bbva") + # Grupo 3: Regex especifica
            r"([\d,]+\.\d{2})\s*\n.*?(\d{9})" # Grupo 4 y 5: monto y ID
        ), # r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}(?:\s+[a-zA-Z]\d{2})?\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito|spei recibidobanorte|spei recibidosantander|spei recibidostp)\s+([\d,]+\.\d{2})\s*\n.*?(\d{9})',
        "descripcion_clip_multilinea": ( # es payclip, getnet o netpay (recibido santander y recibido banorte)
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibido(?:santander|banorte|stp|afirme))\s*([\d,]+\.\d{2})([\s\S]*?(?:gana|0000001af|0000001sq|deposito bpu|trans sr pago|dispersion sihay ref)[\s\S]*?(?:net pay sapi de cv|getnet mexico servicios de adquirencia s|payclip s de rl de cv|pocket de latinoamerica sapi de cv|cobra online sapi de cv|kiwi bop sa de cv))"
        ),
        "descripcion_traspaso_multilinea": ( # es billpocket
            r"(\d{2}/[a-z]{3})\s*(spei recibidobanorte)\s*([\d,]+\.\d{2})([\s\S]*?00072180012119359724[\s\S]*?kiwi international payment technologies)"
        ),
        "descripcion_amex_multilinea": ( # bmrcash
            r"(\d{2}/[a-z]{3})\s*((?:w41|w02)\s*(?:traspaso entre cuentas|deposito de tercero))\s*([\d,]+\.\d{2})([\s\S]*?bmrcash ref)"
        ),
        "descripción_jpmorgan_multilinea": (
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibidojp morgan)\s*([\d,]+\.\d{2})((?:.*?\n){1,18}.*?zettle by paypal(?:.*?\n){1,5}.*?)"
        )
    },
    "multiva": {
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito)\s+([\d,]+\.\d{2})\s*\n(\d{9})',
        "descripcion_clip_multilinea": ( # venta tdd / venta tdc
            # grupo 1: referencia, grupo 2: concepto, grupo 3: monto, grupo 4: fecha
            r"(\d{2}(?:/\d{2}/\d{4})?)\s*"         # fecha
            r"(ft\d{14})\s*"                       # referencia
            r"(ventas tpvs \d{7} venta t(?:dd|dc))\s*" # concepto
            r"[\d,]+\.\d{2}\s*"                    # Primer monto (ignorado)
            r"([\d,]+\.\d{2})\s*"                  # Segundo monto (capturado)
            r"\d{1,3}(?:,\d{3})*\.\d{2}\s*"        # Tercer monto (ignorado)
            r"\n\s*(\d{4}-\d{2}-\d{2})"               # fecha para descripción
        ),
        "descripcion_traspaso_multilinea": ( # spei recibido stp
        r"(\d{2}(?:/\d{2}/\d{4})?)\s*(ft\d{14})\s*(spei recibido stp)\s*[\d,]+\.\d{2}\s*([\d,]+\.\d{2})(.*?\n.*?\n.*?latinoamerica sapi de cv[\s\S]*?bpu2437419281)"
        ),
    },
    "citibanamex": {
        "descripcion": (
            r"(\d{2}\s*[a-z]{3})\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("banamex") + # Grupo 2: Descripción exacta
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r"(\d{2}\s+[a-z]{3})\s*(deposito ventas netas(?:.|\n)*?por evopaymx)\s*([\d,]+\.\d{2})",
        "descripcion_clip_multilinea": ( # evopay (ventas netas amex y d tar)
            r"(\d{2}\s*[a-z]{3})\s*(deposito ventas netas (?:d tar|amex)[\s\S]*?por evopay[\s\S]*?suc\s*\d{4})\s*([\d,]+\.\d{2})"
        ),
    },
    "banamex": {
        "descripcion": (
            r"(\d{2}\s*[a-z]{3})\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("banamex") + # Grupo 2: Descripción exacta
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r"(\d{2}\s+[a-z]{3})\s*(deposito ventas netas(?:.|\n)*?por evopaymx)\s*([\d,]+\.\d{2})",
        "descripcion_clip_multilinea": ( # evopay (ventas netas amex y d tar)
            r"(\d{2}\s*[a-z]{3})\s*(deposito ventas netas (?:d tar|amex)[\s\S]*?por evopay[\s\S]*?suc\s*\d{4})\s*([\d,]+\.\d{2})"
        ),
    },
    "azteca": {
        "descripcion": (
            r"([0-9a-zA-Z]{1,2})\.?\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("azteca") + # Grupo 2: Expresión exacta y genericas
            r"(\d{6,8})\s+([a-zA-Z0-9]{4,10})\s*" # Grupo 3: ID de la transacción
            r"\$?\s*([\d,]+\.\d{2})" # Grupo 4: Monto
        ),
        "descripcion_clip_multilinea": ( # monto, descr 1, monto, descr 2
            r"(\d{2}/\d{2}/\d{4})\s+(transferencia spei a su favor)\s+\(\+\)\s*\$([\d,]+\.\d{2})\s*spei(\n\s*emisor:\s*(?:banorte|santander)\n.+?\n.+?payclip s de rl decv[\s\S]*?gananciasclip)"
        ),
    },
    "inbursa": {
        "descripcion_clip_multilinea": ( # spei recibido stp
        r"([a-z]{3}\.?\s*(?:\d{2})?)\s*(\d{10}\s*deposito spei)\s*([\d,]+\.\d{2}).*?\n(.*?(?:kiwi international payment technologies|cobra online sapi de cv|operadora paypal de mexico s de rl)[\s\S]*?clave de rastreo.*)"
        ),
    },
    "intercam": {
        "descripcion_clip_multilinea": ( # spei recibido stp
        r"(\d{1,2})\s+(\d{9}\s+recepcion spei\s*\|\s*(?:jp morgan|santander|banorte)\s*\|[\s\S]*?)(\d{1,3}(?:,\d{3})*\.\d{2})([\s\S]*?136180018635900157)"
        ),
    }
}

# Creamos un nuevo diccionario para guardar los patrones compilados.
REGEX_COMPILADAS = {}

# Iteramos sobre el diccionario original de bancos y patrones.
for banco, patrones_banco in EXPRESIONES_REGEX.items():
    REGEX_COMPILADAS[banco] = {}
    for clave, patron_texto in patrones_banco.items():
        # sin flags
        flags = 0
        # Compilamos el patrón. Asumimos que el patrón está escrito para texto en minúsculas.
        REGEX_COMPILADAS[banco][clave] = re.compile(patron_texto, flags)

# Funciones para procesar las descripciones de los bancos
# fecha, descripción o parte de esta, monto
def _procesar_banorte(t): return " ".join(t[1:-1]), t[-1]
def _procesar_afirme(t): return " ".join(t[1:-1]), t[-1]
def _procesar_hsbc(t): return " ".join(t[1:-1]), t[-1]
def _procesar_santander(t): return " ".join(t[1:-1]), t[-1]

# fecha, descripción, monto, final de la descripción
def _procesar_bbva(t): return " ".join([t[1], t[-1]]), t[-2]
def _procesar_multiva(t): return " ".join([t[1], t[2], t[-1]]), t[-2]
def _procesar_intercam(t): return " ".join([t[1], t[2], t[-1]]), t[-2]

# fecha, transacción, monto
def _procesar_banregio(t): return " ".join([t[1]]), t[-1]
def _procesar_banamex(t): return " ".join([t[1]]), t[-1]

# fecha, transaccion, monto
def _procesar_scotiabank(t): return " ".join([t[1]]), t[-1]

# Monto, final de transacción, inicio de transacción, monto, mitad de transacción
def _procesar_mifel(t): return " ".join([t[2], t[-1], t[1]]), t[-2]

# monto, final de transacción, inicio de transacción, monto
def _procesar_bajio(t): return " ".join([t[2], t[1]]), t[-1]

# monto, final de transacción, inicio de transacción, monto
def _procesar_azteca(t): return " ".join([t[1], t[-1]]), t[-2]
def _procesar_inbursa(t): return " ".join([t[1], t[-1]]), t[-2]

DESPACHADOR_DESCRIPCION = {
    "banbajío": _procesar_bajio,
    "banorte": _procesar_banorte,
    "afirme": _procesar_afirme,
    "hsbc": _procesar_hsbc,
    "mifel": _procesar_mifel,
    "scotiabank": _procesar_scotiabank,
    "banregio": _procesar_banregio,
    "santander": _procesar_santander,
    "bbva": _procesar_bbva,
    "multiva": _procesar_multiva,
    "citibanamex": _procesar_banamex,
    "banamex": _procesar_banamex,
    "intercam": _procesar_intercam,
    "azteca": _procesar_azteca,
    "inbursa": _procesar_inbursa
}

def construir_descripcion_optimizado(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    # Busca la función correcta en el diccionario y la ejecuta.
    # Proporciona una función por defecto si el banco no se encuentra.
    funcion_procesadora = DESPACHADOR_DESCRIPCION.get(banco.lower(), lambda t: ("", "0.0"))
    return funcion_procesadora(transaccion)

def reconciliar_resultados_ia(res_gpt: dict, res_gemini:dict) -> dict:
    """
    Compara dos diccionarios de resultados de la IA y devuelve el mejor consolidado.
    """
    resultado_final = {}
    # Una forma más limpia de obtener todos los campos únicos de ambos diccionarios
    todos_los_campos = set(res_gpt.keys()) | set(res_gemini.keys())

    # Define qué campos deben ser tratados como números
    CAMPOS_NUMERICOS = {"comisiones", "depositos", "cargos", "saldo_promedio"}

    for campo in todos_los_campos:
        valor_gpt = res_gpt.get(campo)
        valor_gemini = res_gemini.get(campo)

        # --- LÓGICA PARA TOMAR EL MAYOR ---
        
        if campo in CAMPOS_NUMERICOS:
            # Aseguramos que los valores sean numéricos, convirtiendo None a 0.0 para la comparación.
            num_gpt = valor_gpt if valor_gpt is not None else 0.0
            num_gemini = valor_gemini if valor_gemini is not None else 0.0
            
            resultado_final[campo] = max(num_gpt, num_gemini)
        else:
            # Lógica original para campos de texto y otros tipos: priorizar el que no sea nulo.
            # Damos preferencia a GPT si ambos modelos devuelven un valor.
            if valor_gpt is not None:
                resultado_final[campo] = valor_gpt
            elif valor_gemini is not None:
                resultado_final[campo] = valor_gemini
            else:
                resultado_final[campo] = None
    
    return resultado_final

def sanitizar_datos_ia(datos_crudos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toma el diccionario crudo de la IA y asegura que los tipos de datos
    sean los correctos para el modelo Pydantic.
    """
    if not datos_crudos:
        return {}

    datos_limpios = datos_crudos.copy()

    # --- Forzar campos a ser STRINGS ---
    # Campos que deben ser strings (incluso si la IA los devuelve como números)
    campos_str = ["banco", "nombre_cliente", "rfc", "clabe_interbancaria", "periodo_inicio", "periodo_fin"]
    for campo in campos_str:
        if campo in datos_limpios and datos_limpios[campo] is not None:
            datos_limpios[campo] = str(datos_limpios[campo])

    # --- Forzar campos a ser FLOATS ---
    # Campos que deben ser números limpios
    campos_float = ["comisiones", "depositos", "cargos", "saldo_promedio"]
    for campo in campos_float:
        if campo in datos_limpios:
            datos_limpios[campo] = limpiar_monto(datos_limpios[campo])
            
    return datos_limpios

def total_depositos_verificacion(
    resultados_portada: List[Union[Tuple[Dict, bool], Exception]]
) -> Tuple[float, bool]:
    """
    Suma los depósitos de una lista de resultados de análisis con IA.
    """
    total_depositos = 0.0
    for resultado in resultados_portada:
        if not isinstance(resultado, Exception):
            datos_ia, _ = resultado
            if datos_ia:
                depo = datos_ia.get("depositos") or 0.0
                total_depositos += float(depo)
    es_mayor = total_depositos >= 250_000
    return total_depositos, es_mayor

def limpiar_monto(monto: Any) -> float:
    """
    Convierte un monto de cualquier tipo (string, int, float) a un float limpio.
    Maneja de forma segura valores como '$1,234.56', 1234, 1234.56, y None.
    """
    # Si ya es un número, simplemente lo convertimos a float y lo devolvemos.
    if isinstance(monto, (int, float)):
        return float(monto)

    # Si es un string, aplicamos la lógica de limpieza.
    if isinstance(monto, str):
        # Elimina el símbolo de moneda, comas y espacios
        monto_limpio = monto.replace('$', '').replace(',', '').strip()
        try:
            return float(monto_limpio)
        except ValueError:
            # Esto ocurre si el string está vacío o no es numérico después de limpiar
            return 0.0
            
    # Si no es ni número ni string (ej. None), devolvemos 0.0
    return 0.0

def limpiar_y_normalizar_texto(texto: str) -> str:
    """
    Limpia y normaliza el texto extraído de un PDF.
    1. Colapsa múltiples espacios o saltos de línea entre palabras a un solo espacio.
    """
    if not texto:
        return ""

    # Reemplaza secuencias de 2 o más espacios/tabs con un solo espacio.
    texto_normalizado = re.sub(r'[ \t]{2,}', ' ', texto)
    return texto_normalizado.strip()

def crear_objeto_resultado(datos_dict: dict) -> ResultadoExtraccion:
    """
    Transforma un diccionario plano de resultados en un objeto Pydantic
    ResultadoExtraccion completamente estructurado y anidado.
    """
    try:
        # 1. Creamos el sub-objeto AnalisisIA
        analisis_ia = ResultadoAnalisisIA(
            banco=datos_dict.get("banco"),
            rfc=datos_dict.get("rfc"),
            nombre_cliente=datos_dict.get("nombre_cliente"),
            clabe_interbancaria=datos_dict.get("clabe_interbancaria"),
            periodo_inicio=datos_dict.get("periodo_inicio"),
            periodo_fin=datos_dict.get("periodo_fin"),
            comisiones=datos_dict.get("comisiones"),
            depositos=datos_dict.get("depositos"),
            cargos=datos_dict.get("cargos"),
            saldo_promedio=datos_dict.get("saldo_promedio"),
            entradas_TPV_bruto=datos_dict.get("entradas_TPV_bruto"),
            entradas_TPV_neto=datos_dict.get("entradas_TPV_neto"),
        )

        # 2. Creamos el sub-objeto DetalleTransacciones
        detalle_transacciones = ResultadoTPV(
            transacciones=datos_dict.get("transacciones", []),
            error_transacciones=datos_dict.get("error_transacciones")
        )

        # 3. Ensamblamos y devolvemos el objeto principal
        return ResultadoExtraccion(
            AnalisisIA=analisis_ia,
            DetalleTransacciones=detalle_transacciones
        )
    except Exception as e:
        # Si algo falla en la creación del modelo, devolvemos un objeto de error
        return ResultadoExtraccion(
            AnalisisIA=None,
            DetalleTransacciones=ErrorRespuesta(error=f"Error al estructurar el diccionario de respuesta: {e}")
        )