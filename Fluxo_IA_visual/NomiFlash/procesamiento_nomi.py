import fitz
import re
import asyncio
from io import BytesIO
from typing import Optional, Tuple, List, Dict
from fastapi import UploadFile
from ..procesamiento.extractor import PDFCifradoError
from .auxiliares_nomi import analizar_portada_gpt, extraer_json_del_markdown, sanitizar_datos_ia, convertir_pdf_a_imagenes, leer_qr_de_imagenes
from ..models import RespuestaComprobante, RespuestaEstado, RespuestaNomina

def extraer_texto_limitado(pdf_bytes: bytes, num_paginas: int = 2) -> str:
    """
    Extrae texto de las primeras 'num_paginas' de un PDF.
    Si está encriptado, lanza PDFCifradoError.
    """
    texto_parcial = ''
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.is_encrypted:
                raise PDFCifradoError("El documento está protegido por contraseña.")
            for i in range(min(len(doc), num_paginas)):
                texto_parcial += doc[i].get_text(sort=True).lower() + '\n'
    except PDFCifradoError:
        raise
    except Exception as e:
        print(f"Error durante la extracción limitada de texto con fitz: {e}")
        raise RuntimeError(f"No se pudo leer el contenido del PDF: {e}")
    return texto_parcial

# Diccionario de regex para RFC y CURP por tipo de documento
PATTERNS_COMPILADOS_RFC_CURP: Dict[str, Dict[str, re.Pattern]] = {
    "RFC": {
        "nomina": re.compile(r"r\.?f\.?c\.?\s+([a-zñ&]{3,4}\d{6}[a-z0-9]{3})"),
        "estado": re.compile(r"r\.?f\.?c\.?:\s+([a-zñ&]{3,4}\d{6}[a-z0-9]{3})"),
    },
    "CURP": {
        "nomina": re.compile(r"curp:\s*([a-z]{4}\d{6}[hm][a-z]{5}\d{2})"),
        "estado": re.compile(r"curp:\s*([a-z]{4}\d{6}[hm][a-z]{5}\d{2})"),  # si aplica para estado
    }
}

def extraer_rfc_curp_por_texto(texto: str, tipo_doc: str) -> Tuple[List[str], List[str]]:
    """
    Busca RFC y/o CURP en el texto probando solo los patrones 
    definidos para el tipo de documento indicado (ej: 'nomina', 'estado').
    Devuelve dos listas: [RFCs encontrados], [CURPs encontrados].
    """
    if not texto or not tipo_doc:
        return [], []

    rfcs, curps = [], []

    # Buscar RFCs para ese tipo de documento
    patron_rfc = PATTERNS_COMPILADOS_RFC_CURP["RFC"].get(tipo_doc.lower())
    if patron_rfc:
        for match in patron_rfc.finditer(texto):
            rfcs.append(match.group(1).upper())

    # Buscar CURPs para ese tipo de documento
    patron_curp = PATTERNS_COMPILADOS_RFC_CURP["CURP"].get(tipo_doc.lower())
    if patron_curp:
        for match in patron_curp.finditer(texto):
            curps.append(match.group(1).upper())

    return rfcs, curps

PROMPT_NOMINA = """
Esta imágen es de la primera página de un recibo de nómina, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- nombre
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c", los primeros 10 caracteres del rfc y curp son iguales
- curp # es un código de 4 letras, 6 números, 6 letras y 2 números
- dependencia # Secretaría o institución pública
- secretaria # (ejemplo: 'Gobierno del Estado de Puebla' o 'SNTE')
- numero_empleado # puede aparecer como  'NO. EMPLEADO'
- puesto_cargo # Puesto o cargo, puede aparecer como 'DESCRIPCIÓN DEL PUESTO'
- categoria # (ejemplo: "07", "08", "T")
- salario_neto # Normalmente aparece como 'Importe Neto'
- total_percepciones # aparece a la derecha de 'Total percepciones'
- total_deducciones # aparece a la derecha de 'Total deducciones'
- periodo_inicio # Devuelve en formato "2025-12-25"
- periodo_fin # Devuelve en formato "2025-12-25"
- fecha_pago # Devuelve en formato "2025-12-25"
- periodicidad # (es la cantidad de días entre periodo_inicio y periodo_fin pero en palabra, ejemplo: "Quincenal", "Mensual") 
- error_lectura_nomina # Null por defecto

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_nomina" un "Documento sin coincidencias" 
"""

PROMPT_ESTADO_CUENTA = """
Estas son las primeras 2 páginas de un recibo de cuenta, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- clabe # puede iniciar con 0 el número de cuenta clabe del usuario/cliente, puede aparecer como 'No. cuenta CLABE', extraelo todo
- nombre_usuario # el nombre del usuario/cliente
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c"
- numero_cuenta # el número de cuenta, puede aparecer como 'No. de Cuenta'
- error_lectura_estado # Null por defecto

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

PROMPT_COMPROBANTE = """
Esta imágen es de la primera página de un comprobante de domicilio, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- domicilio # el domicilio completo, normalmente está junto al nombre del cliente
- inicio_periodo # inicio del periodo facturado en formato "2025-12-25"
- fin_periodo # fin del periodo facturado en formato "2025-12-25"

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

# --- PROCESADOR PARA NÓMINA ---
async def procesar_nomina(archivo: UploadFile) -> RespuestaNomina:
    """
    Función auxiliar que procesa los archivos de nómina siguiendo lógica de negocio interna.
    Tiene comprobación interna con regex para más precisión (RFC Y CURP)
    Devuelve un objeto RespuestaNomina en caso de éxito o error_lectura_nomina en caso de fallo.
    """
    try:
        # Leer contenido. Si falla, la excepción será capturada.
        pdf_bytes = await archivo.read()

        # --- Lógica de negocio específica para Nómina ---
        # 1. Extraemos texto para la validación con regex
        texto_inicial = extraer_texto_limitado(pdf_bytes)
        rfc, curp = extraer_rfc_curp_por_texto(texto_inicial, "nomina")

        # 2. Leemos el QR de las imagenes (con loop executor para no bloquear el servidor)
        loop = asyncio.get_running_loop()

        imagen_buffers = await loop.run_in_executor(
            None, convertir_pdf_a_imagenes, pdf_bytes
        )

        if not imagen_buffers:
            raise ValueError("No se pudieron generar imágenes del PDF.")

        # 2.5 Leemos el QR de las imágenes (lógica condicional aquí)
        datos_qr = await loop.run_in_executor(
            None, leer_qr_de_imagenes, imagen_buffers
        )
        
        # 3. Analizamos con la IA usando el prompt de nómina y las mismas imagenes
        respuesta_gpt = await analizar_portada_gpt(PROMPT_NOMINA, imagen_buffers)
        datos_crudos = extraer_json_del_markdown(respuesta_gpt)
        datos_listos = sanitizar_datos_ia(datos_crudos)

        # --- Lógica de corrección específica para Nómina ---
        # 3. Sobrescribimos los datos de la IA con los de la regex (más fiables)
        if datos_qr:
            datos_listos["datos_qr"] = datos_qr
        if rfc:
            datos_listos["rfc"] = rfc[-1]
        if curp:
            datos_listos["curp"] = curp[-1]
        
        # Si todo fue exitoso, devuelve los datos.
        return RespuestaNomina(**datos_listos)

    except Exception as e:
        # Error por procesamiento
        return RespuestaNomina(error_lectura_nomina=f"Error procesando '{archivo.filename}': {e}")
    
# --- PROCESADOR PARA ESTADO DE CUENTA ---
async def procesar_estado_cuenta(archivo: UploadFile) -> RespuestaEstado:
    """
    Procesa un estado de cuenta, analizando la primera, segunda y última página.
    Ejecuta la lectura de QR y el análisis de IA en paralelo para mayor eficiencia.
    """
    try:
        pdf_bytes = await archivo.read()

        # --- Lógica de negocio específica para Nómina ---
        # 0. Extraemos texto para la validación con regex
        texto_inicial = extraer_texto_limitado(pdf_bytes)
        rfc, curp = extraer_rfc_curp_por_texto(texto_inicial, "estado")

        loop = asyncio.get_running_loop()

        # --- 1. Determinar dinámicamente las páginas a procesar ---
        paginas_a_procesar = []
        try:
            # Abrimos el PDF brevemente solo para contar las páginas
            with fitz.open(stream=BytesIO(pdf_bytes), filetype="pdf") as doc:
                total_paginas = len(doc)
            
            # Creamos la lista: [1, 2, ultima_pagina]
            # Usamos set para manejar PDFs cortos (ej. de 1 o 2 páginas) sin duplicados.
            paginas_a_procesar = sorted(list(set([1, 2, total_paginas])))
            print(f"Procesando páginas {paginas_a_procesar} para '{archivo.filename}'")
            
        except Exception as e:
            # Si falla, usamos un valor seguro por defecto
            print(f"No se pudo determinar el total de páginas para '{archivo.filename}': {e}. Usando páginas [1, 2].")
            paginas_a_procesar = [1, 2]

        # --- 2. Convertir solo las páginas necesarias a imágenes ---
        imagen_buffers = await loop.run_in_executor(
            None, convertir_pdf_a_imagenes, pdf_bytes, paginas_a_procesar
        )
        if not imagen_buffers:
            raise ValueError("No se pudieron generar imágenes del PDF.")

        # 2.5 Leemos el QR de las imágenes (lógica condicional aquí)
        datos_qr = await loop.run_in_executor(
            None, leer_qr_de_imagenes, imagen_buffers
        )
        
        # 3. Analizamos con la IA usando el prompt de nómina y las mismas imagenes
        respuesta_gpt = await analizar_portada_gpt(PROMPT_ESTADO_CUENTA, imagen_buffers)
        datos_crudos = extraer_json_del_markdown(respuesta_gpt)
        datos_listos = sanitizar_datos_ia(datos_crudos)

        # --- Lógica de corrección específica para Nómina ---
        if datos_qr:
            datos_listos["datos_qr"] = datos_qr
        if rfc:
            datos_listos["rfc"] = rfc[-1]

        print(datos_listos)
        return RespuestaEstado(**datos_listos)

    except Exception as e:
        return RespuestaEstado(error_lectura_estado=f"Error procesando '{archivo.filename}': {e}")

# --- PROCESADOR PARA COMPROBANTE DE DOMICILIO ---
async def procesar_comprobante(archivo: UploadFile) -> RespuestaComprobante:
    """
    Procesa un archivo de comprobante de domicilio.
    Devuelve un objeto RespuestaComprobante en caso de éxito o error_lectura_comprobante en caso de fallo.
    """
    try:
        pdf_bytes = await archivo.read()

        # 1. Leemos el QR de las imagenes (con loop executor para no bloquear el servidor)
        loop = asyncio.get_running_loop()

        imagen_buffers = await loop.run_in_executor(
            None, convertir_pdf_a_imagenes, pdf_bytes
        )

        respuesta_ia = await analizar_portada_gpt(PROMPT_COMPROBANTE, imagen_buffers)
        datos_crudos = extraer_json_del_markdown(respuesta_ia)
        datos_listos = sanitizar_datos_ia(datos_crudos)
        return RespuestaComprobante(**datos_listos)
    
    except Exception as e:
        return RespuestaComprobante(error_lectura_comprobante=f"Error procesando '{archivo.filename}': {e}")