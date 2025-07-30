from typing import Tuple, List, Any, Dict, Optional
import re

PALABRAS_CLAVE_VERIFICACION = re.compile(
    r"banco|banca|cliente|estado de cuenta|rfc|periodo"
)

# Creamos la lista de palabras clave generales (quitamos mit y american express)
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "payclip, s. de r.l. de c.v", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "clipmx", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup"
]

BANCO_MAP = {
    "banco mercantil del norte": "banorte",
    "banco del bajio": "banbajío",
    "banca afirme": "afirme",
    "grupo financiero hsbc": "hsbc",
    "grupo financiero mifel": "mifel",
    "scotiabank": "scotiabank",
    "banco regional": "banregio",
    "grupo financiero bbva": "bbva",
    "banco multiva": "multiva",
    "banco santander": "santander",
    "bancosantander": "santander",
    "banco nacional de mexico": "banamex",
    "banco nacional de méxico": "banamex",
    "banco bancrea": "bancrea",
    "banco inbursa": "inbursa",
    "banco monex": "monex",
    "banco azteca": "azteca",
    "bankaool": "bankaool",
}
# compilamos los bancos
BANCO_REGEX = re.compile("|".join(BANCO_MAP.keys()))

# Diccionario con los patrones de RFC por banco
RFC_PATTERNS = {
    "banbajío": r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "banorte": r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "afirme": r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "hsbc": r"rfc[^\n]*\n\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})", # Versión multilínea
    "mifel": r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "scotiabank": r"r\.f\.c\.cliente\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "banregio": r"rfc:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "santander": r"r\.f\.c\.\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "bbva": r"r\.f\.c\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "multiva": r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "banamex": r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "banamex": r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "citibanamex": r"rfc\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
    "citibanamex": r"registro federal de contribuyentes:\s*([a-zñ&]{3,4}\d{6}[a-z0-9]{2,3})",
}

# Creamos el diccionario de patrones compilados
RFC_PATTERNS_COMPILADOS = {
    banco: re.compile(patron, re.IGNORECASE) 
    for banco, patron in RFC_PATTERNS.items()
}

# Creamos la función para reconocer el banco en las primeras 2 páginas
def reconocer_banco_por_texto(texto: str) -> Optional[str]:
    """
    Busca en el texto un nombre de banco conocido y devuelve su nombre estandarizado.
    
    Args:
        texto: El texto extraído de las primeras páginas del PDF.
        
    Returns:
        El nombre del banco estandarizado si se encuentra, o None si no hay coincidencia.
    """
    if not texto:
        return None
        
    match = BANCO_REGEX.search(texto.lower())
    
    if match:
        nombre_encontrado = match.group(0)
        # Devuelve el nombre estandarizado del diccionario
        return BANCO_MAP.get(nombre_encontrado)
        
    return None

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
    #          r"[a-zA-Z][a-zA-Z ]*?\s*\d{8}[cd]",
    "afirme": r"venta tpv(?:cr|db)",
    "hsbc": r"transf[\s~]*rec[\s~]*hsbcnet[\s~]*tpv[\s~]*(?:db|cr)?|transf[\s~]*rec[\s~]*hsbcnet[\s~]*dep[\s~]*tpv|deposito[\s~]*bpu\d{10}",
    "mifel": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
    # Scotiabank no tiene una para una línea
    "scotiabank": r"vta\. (?:cre|deb)\s+\d{4}\s*\d{7}",
    "banregio": "tra\s+\d{7}-abono ventas\s+(?:tdd|tdc)",
    "santander": "deposito ventas del dia afil",
    "bbva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
    "multiva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
    "citibanamex": r"(?:deposito ventas netas(?:.|\n)*?por evopaymx)",
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
            r"(\d{2}-[a-z]{3}-\d{2})\s*" # Grupo 1: Fecha ("ej:  05-may-25")
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("Banorte") + # Grupo 3: Descripción completa
            r"\s*([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r'(\d{2}-[a-z]{3}-\d{2})([a-zA-Z][a-zA-Z ]*?)\s+(\d{8}[cd])\s+([\d,]+\.\d{2})',
        "descripcion_clip_multilinea": (
            r'(\d{2}-[a-z]{3}-\d{2}).*?((spei recibido.*?([\d,]+\.\d{2}).*?\n(?:.*\n){1}.*?ganancias clip(?:.*\n){1}.*))'
        ),
        "descripcion_traspaso_multilinea": (
            r'(\d{2}-[a-z]{3}-\d{2}).*?((traspaso de cta.*?([\d,]+\.\d{2}).*\n.*?clip.*))'
        ),
        "descripcion_amex_multilinea": (
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
            r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,6}.*?deposito bpu.*?\n(?:.*?\n){0,10}.*?pocket de latinoamerica sapi.*?\n.*?\n)"
            # r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,6}.*?(?:deposito bpu|amexco se|dep).*?\n(?:.*?\n){0,10}.*?(?:american express company mexic|first data merchant services m|pocket de latinoamerica sapi).*?\n.*?\n)"
        ),
        "descripcion_traspaso_multilinea": ( # spei first data dep
            r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,6}.*?dep.*?\n(?:.*?\n){0,10}.*?first data merchant services m.*?\n.*?\n)"
        ),
        "descripcion_amex_multilinea": ( # spei american express amexco
            r"(\d{2}\s+[a-z]{3})\s+(transf interbancaria spei\s+\d{20}\s+\$\s*([\d,]+\.\d{2})\s+\$\s*[\d,]+\.\d{2}\s*\n(?:.*?\n){1,6}.*?amexco se.*?\n(?:.*?\n){0,10}.*?american express company mexic.*?\n.*?\n)"
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
            r"(\d{2}-[a-z]{3}-\d{4})(\d{7})(abono transferencia spei hora\s+\d{2}:\d{2}:\d{2}\s+([\d,]+\.\d{2}).*?\n[\s\S]*?deposito bpu)"
        ),
    },
    "bbva": {
        "descripcion": (
            r"(\d{2}/[a-z]{3})\s*\d{2}/[a-z]{3}" # Grupo 1: Fecha
            r"(?:\s+[a-zA-Z]\d{2})?" # Grupo 2: Referencia
            r"((?:.*?)(?:%s)(?:.*?))\s*" % construir_regex_descripcion("bbva") + # Grupo 3: Regex especifica
            r"([\d,]+\.\d{2})\s*\n.*?(\d{9})" # Grupo 4 y 5: monto y ID
        ), # r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}(?:\s+[a-zA-Z]\d{2})?\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito|spei recibidobanorte|spei recibidosantander|spei recibidostp)\s+([\d,]+\.\d{2})\s*\n.*?(\d{9})',
        "descripcion_clip_multilinea": ( # es payclip (recibido santander y recibido banorte)
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibido(?:santander|banorte))\s*([\d,]+\.\d{2}).*(\n.*gana[\s\S]*?payclip s de rl de cv)"
        ),
        "descripcion_traspaso_multilinea": ( # es billpocket
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibidostp)\s*([\d,]+\.\d{2})\n.*?(deposito bpu[\s\S]*?pocket de latinoamerica sapi de cv)"
        ),
        "descripcion_amex_multilinea": ( # es recibidobanorte o recibidosantander de net pay o getnet
            r"(\d{2}/[a-z]{3})\s*(spei recibido(?:santander|banorte))\s*([\d,]+\.\d{2}).*(\n.*(?:sq|af)[\s\S]*?(?:net pay sapi de cv|getnet mexico servicios de adquirencia s))"
        ),
    },
    "multiva": {
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito)\s+([\d,]+\.\d{2})\s*\n(\d{9})',
        "descripcion_clip_multilinea": ( # venta tdd / venta tdc
            # grupo 1: referencia, grupo 2: concepto, grupo 3: monto, grupo 4: fecha
            r"(\d{2}(?:/\d{2}/\d{4})?)\s*"         # fecha
            r"(ft\d{14})\s*"                       # referencia
            r"(ventas tpvs \d{7} venta t(?:dd|dc))\s*" # concepto
            r"[\d,]+\.\d{2}\s+"                    # Primer monto (ignorado)
            r"([\d,]+\.\d{2})\s+"                  # Segundo monto (capturado)
            r"\d{1,3}(?:,\d{3})*\.\d{2}\s*"        # Tercer monto (ignorado)
            r"\n(\d{4}-\d{2}-\d{2})"               # fecha para descripción
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

# fecha, transacción, monto
def _procesar_banregio(t): return " ".join([t[1]]), t[-1]
def _procesar_banamex(t): return " ".join([t[1]]), t[-1]

# fecha, transaccion, monto
def _procesar_scotiabank(t): return " ".join([t[1]]), t[-1]

# Monto, final de transacción, inicio de transacción, monto, mitad de transacción
def _procesar_mifel(t): return " ".join([t[2], t[-1], t[1]]), t[-2]

# monto, final de transacción, inicio de transacción, monto
def _procesar_bajio(t): return " ".join([t[2], t[1]]), t[-1]

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
}

def construir_descripcion_optimizado(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    # Busca la función correcta en el diccionario y la ejecuta.
    # Proporciona una función por defecto si el banco no se encuentra.
    funcion_procesadora = DESPACHADOR_DESCRIPCION.get(banco.lower(), lambda t: ("", "0.0"))
    return funcion_procesadora(transaccion)

def extraer_rfc_por_texto(texto: str, banco: str) -> Optional[str]:
    """
    Busca el RFC en el texto usando la regex específica para el banco detectado.
    """
    if not texto or not banco:
        return None

    # Busca el patrón compilado para el banco correspondiente
    patron = RFC_PATTERNS_COMPILADOS.get(banco.lower())
    if not patron:
        return None # No hay un patrón definido para este banco

    match = patron.search(texto)
    
    # Si encuentra una coincidencia, devuelve el grupo capturado (el RFC) en mayúsculas
    if match:
        return match.group(1)
        
    return None

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

def verificar_total_depositos(datos_extraidos: List[Dict[str, Any]]) -> bool:
    """
    Suma el campo 'depositos' de una lista de diccionarios y verifica 
    si el total es mayor a 250,000.

    Args:
        lista_datos_ia: La lista de diccionarios extraídos por la IA.

    Returns:
        True si la suma es mayor a 250,000, False en caso contrario.
    """
    total_depositos = 0
    for datos_de_un_pdf in datos_extraidos:
        depo = datos_de_un_pdf.get("depositos", 0.0)

        if depo is not None:
            total_depositos += float(depo)
    return total_depositos > 250_000

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