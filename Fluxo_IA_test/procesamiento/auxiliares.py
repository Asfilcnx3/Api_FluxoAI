from typing import Tuple, List, Any, Dict
import re

PALABRAS_CLAVE_VERIFICACION = re.compile(
    r"banco|banca|cliente|estado de cuenta|rfc|periodo"
)

# Creamos la lista de palabras clave generales (quitamos mit y american express)
palabras_clave_generales = [
    "evopay", "evopayments", "psm payment services mexico sa de cv", "deposito bpu3057970600", "cobra online s.a.p.i. de c.v.", "sr. pago", "por favor paguen a tiempo, s.a. de c.v.", "por favor paguen a tiempo", "pagofácil", "netpay s.a.p.i. de c.v.", "netpay", "deremate.com de méxico, s. de r.l. de  c.v.", "mercadolibre s de rl de cv", "mercado lending, s.a de c.v", "deremate.com de méxico, s. de r.l de c.v", "first data merchant services méxico s. de r.l. de c.v", "adquira méxico, s.a. de c.v", "flap", "mercadotecnia ideas y tecnología, sociedad anónima de capital variable", "mit s.a. de c.v.", "payclip, s. de r.l. de c.v", "clip", "grupo conektame s.a de c.v.", "conekta", "conektame", "pocket de latinoamérica, s.a.p.i de c.v.", "billpocket", "pocketgroup", "banxol de méxico, s.a. de c.v.", "banwire", "promoción y operación, s.a. de c.v.", "evo payments", "prosa", "net pay sa de cv", "net pay sapi de cv", "izettle méxico, s. de r.l. de c.v.", "izettle mexico s de rl de cv", "pocket de latinoamerica sapi de cv", "bn-nts", "izettle mexico s de rl", "first data merc", "cobra online sapi de cv", "payclip s de rl de cv", "clipmx", "evopaymx", "izettle", "refbntc00017051", "pocket de", "sofimex", "actnet", "exce cca", "venta nal. amex", "pocketgroup"
]

# Creamos el prompt del modelo a utilizar
prompt_base = """
Estas imágenes son de las primeras 2 páginas de un estado de cuenta bancario, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).

Campos a extraer:

- banco # debe ser el nombre corto, por ejemplo, "banco del bajío" es banbajío
- nombre_cliente
- clabe_interbancaria
- rfc # debe ser el del cliente y su estructura son 12 o 13 caracteres que conforman 3 letras, 6 dígitos y una homoclave
- periodo_inicio # Devuelve en formato "2025-12-25"
- periodo_fin # Devuelve en formato "2025-12-25"
- comisiones
- cargos # aparece como "cargos", "retiros" u "otros retiros", toma el más grande solamente
- depositos
- saldo_promedio

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
"""

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
    "bbva": r"ventas tarjetas|ventas tdc inter|ventas credito|ventas debito",
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
            r"(\d{2})\.?\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("hsbc") + # Grupo 2: Expresión exacta y genericas
            r"([A-Za-z0-9]{8})?\s*" # Grupo 3: ID de la transacción
            r"\$\s*([\d,]+\.\d{2})" # Grupo 4: Monto
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
        "descripcion_clip_traspaso": ( # es transferencia spei bn
            r"(?m)^(\d{2}/\d{2}/\d{4})\s+(smf\d{6}-\d)\s+(transferencia spei bn.*?)\s+(\d{1,3}(?:,\d{3})*\.\d{2}).*\n(.*)"
        ),
    },
    "scotiabank": {
        "descripcion": (
            r"(\d{2}\s+[a-z]{3})\s*" # Grupo 1: Fecha que estamos buscando
            r"(%s)\s+" % construir_regex_descripcion("scotiabank") + # Grupo 2: Descipción que estamos buscando
            r"\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*" # Grupo 3: Monto a encontrar y monto a ignorar
            r"\n((?:.*\n){6})" # Grupo 4: Lineas despues
        ), #r'(\d{2}\s+[a-z]{3})\s+transf interbancaria spei\s+(\d{20})\s+\$([\d,]+\.\d{2})\s+\$[\d,]+\.\d{2}\s*\n((?:.*\n){6})',
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
        "descripcion_clip_multilinea": ( # es payclip
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibidosantander)\s*([\d,]+\.\d{2})([\s\S]*?payclip s de rl de cv)"
        ),
        "descripcion_clip_traspaso": ( # es billpocket
            r"(\d{2}/[a-z]{3})\s*(t20\s*spei recibidostp)\s*([\d,]+\.\d{2})\n.*?(deposito bpu[\s\S]*?pocket de latinoamerica sapi de cv)"
        ),
    },
    "multiva": {
        # Multiva no tiene conceptos claros aún
        "descripcion": r'(\d{2}/[a-z]{3})\s+\d{2}/[a-z]{3}\s+(ventas tarjetas|ventas tdc inter|ventas credito|ventas debito)\s+([\d,]+\.\d{2})\s*\n(\d{9})',
    },
    "banamex": {
        "descripcion": (
            r"(\d{2}\s*[a-z]{3})\s*" # Grupo 1: Fecha
            r"(%s)\s*" % construir_regex_descripcion("banamex") + # Grupo 2: Descripción exacta
            r"([\d,]+\.\d{2})" # Grupo 3: Monto
        ), # r"(\d{2}\s+[a-z]{3})\s*(deposito ventas netas(?:.|\n)*?por evopaymx)\s*([\d,]+\.\d{2})",
    }
}

# Creamos un nuevo diccionario para guardar los patrones compilados.
REGEX_COMPILADAS = {}

# Iteramos sobre el diccionario original de bancos y patrones.
for banco, patrones_banco in EXPRESIONES_REGEX.items():
    REGEX_COMPILADAS[banco] = {}
    for clave, patron_texto in patrones_banco.items():
        # La única flag que nos importa es DOTALL para los casos multilínea.
        # flags = re.DOTALL if "multilinea" in clave else 0
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
def _procesar_multiva(t): return " ".join([t[1], t[-1]]), t[-2]

# fecha, transacción, monto
def _procesar_banregio(t): return " ".join([t[1]]), t[-1]
def _procesar_banamex(t): return " ".join([t[1]]), t[-1]

# fecha, final de transacción, monto, inicio de transacción
def _procesar_scotiabank(t): return " ".join([t[-1], t[1]]), t[-2]

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
    "banamex": _procesar_banamex
}

def construir_descripcion_optimizado(transaccion: Tuple, banco: str) -> Tuple[str, str]:
    # Busca la función correcta en el diccionario y la ejecuta.
    # Proporciona una función por defecto si el banco no se encuentra.
    funcion_procesadora = DESPACHADOR_DESCRIPCION.get(banco.lower(), lambda t: ("", "0.0"))
    return funcion_procesadora(transaccion)


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