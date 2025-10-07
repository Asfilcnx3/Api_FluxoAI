from ..utils.helpers import (
    es_escaneado_o_no, extraer_datos_por_banco, extraer_json_del_markdown, construir_descripcion_optimizado, 
    limpiar_monto, sumar_lista_montos, limpiar_y_normalizar_texto, sanitizar_datos_ia, reconciliar_resultados_ia,
    detectar_tipo_contribuyente
    
)
from .ia_extractor import (
    analizar_gpt_fluxo, analizar_gemini_fluxo, analizar_gpt_nomi, _extraer_datos_con_ia
)
from ..utils.helpers_texto_fluxo import (
    REGEX_COMPILADAS, PALABRAS_EXCLUIDAS, PALABRAS_EFECTIVO, PALABRAS_TRASPASO_ENTRE_CUENTAS
)
from ..utils.helpers_texto_nomi import (
    PROMPT_COMPROBANTE, PROMPT_ESTADO_CUENTA, PROMPT_NOMINA, SEGUNDO_PROMPT_NOMINA
)
from ..utils.helpers_texto_csf import (
    PATRONES_CONSTANCIAS_COMPILADO
)

from .pdf_processor import extraer_texto_de_pdf, extraer_rfc_curp_por_texto, convertir_pdf_a_imagenes, leer_qr_de_imagenes
from ..models.responses import NomiFlash, CSF

from typing import Dict, Any, Tuple, Optional
from fastapi import UploadFile
from io import BytesIO
import logging
import fitz
import asyncio

logger = logging.getLogger(__name__)

# ----- FUNCIONES ORQUESTADORAS DE FLUXO -----

# ESTA FUNCIÓN ES PARA OBTENER Y PROCESAR LAS PORTADAS DE LOS PDF
async def obtener_y_procesar_portada(prompt:str, pdf_bytes: bytes) -> Tuple[Dict[str, Any], bool]:
    """
    Orquesta el proceso de forma secuencial siguiendo el siguiente roadmap:
    1. Extrae texto inicial.
    2. Reconoce el banco.
    3. Decide qué páginas enviar a la IA.
    4. Llama a la IA con las páginas correctas
    5. corrige su respuesta.
    """
    loop = asyncio.get_running_loop()
    # --- 1. PRIMERO: Extraer texto inicial y determinar si es digital --- La ejecutamos en un hilo separado para no bloquear el programa.
    texto_verificacion = await loop.run_in_executor(
        None,  # Usa el executor de hilos por defecto
        extraer_texto_de_pdf, 
        pdf_bytes
    )
    es_documento_digital = es_escaneado_o_no(texto_verificacion)

    # --- 2. SEGUNDO: Reconocer el banco y el RFC a partir del texto (con regex) ---
    datos_regex = extraer_datos_por_banco(texto_verificacion.lower())
    banco_estandarizado = datos_regex.get("banco")
    logger.debug(banco_estandarizado)
    rfc_estandarizado = datos_regex.get("rfc")
    logger.debug(rfc_estandarizado)
    comisiones_estanarizadas = datos_regex.get("comisiones")
    logger.debug(comisiones_estanarizadas)
    depositos_estanarizadas = datos_regex.get("depositos")
    logger.debug(depositos_estanarizadas)

    # --- 3. TERCERO: Decidir qué páginas procesar ---
    paginas_para_ia = [1, 2] # Por defecto, las primeras dos
    
    if banco_estandarizado == "BANREGIO":
        logger.debug("Banco BANREGIO detectado. Ajustando páginas para el análisis de IA.")
        try:
            # Usamos fitz de nuevo, pero solo para un rápido conteo de páginas.
            # Es muy eficiente y no procesa el contenido.
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                total_paginas = len(doc)
            
            if total_paginas > 5:
                # Creamos la lista de páginas: la primera y las últimas 5
                paginas_finales = list(range(total_paginas - 4, total_paginas + 1))
                paginas_para_ia = sorted(list(set(paginas_para_ia + paginas_finales)))
            else:
                # Si el doc es corto, tomamos todas las páginas
                paginas_para_ia = list(range(1, total_paginas + 1))

        except Exception as e:
            logger.debug(f"No se pudo determinar el total de páginas para Banregio: {e}. Usando páginas por defecto.")
            paginas_para_ia = [1, 2]
    
    # --- 4. CUARTO: Llamar a las IA de forma PARALELA con las páginas correctas ---
    tarea_gpt = analizar_gpt_fluxo(prompt, pdf_bytes, paginas_a_procesar = paginas_para_ia)
    tarea_gemini = analizar_gemini_fluxo(prompt, pdf_bytes, paginas_a_procesar = paginas_para_ia)
    
    resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_gemini, return_exceptions=True)

    res_gpt_str, res_gemini_str = resultados_ia_brutos # la respuesta de gemini tiene un error en los tokens

    datos_gpt = extraer_json_del_markdown(res_gpt_str) if not isinstance(res_gpt_str, Exception) else {}
    datos_gemini = extraer_json_del_markdown(res_gemini_str) if not isinstance(res_gemini_str, Exception) else {}

    # --- SANITIZACION ---
    datos_gpt_sanitizados = sanitizar_datos_ia(datos_gpt)
    datos_gemini_sanitizados = sanitizar_datos_ia(datos_gemini)

    # --- RECONCILIACIÓN ---
    datos_ia_reconciliados = reconciliar_resultados_ia(datos_gpt_sanitizados, datos_gemini_sanitizados)

    # --- 5. QUINTO: Corregir el resultado de la IA y devolver ---
    # Usamos el banco que reconocimos por texto, que es más fiable.
    if banco_estandarizado is not None:
        datos_ia_reconciliados["banco"] = banco_estandarizado
    if rfc_estandarizado is not None:
        datos_ia_reconciliados["rfc"] = rfc_estandarizado
    if comisiones_estanarizadas is not None:
        datos_ia_reconciliados["comisiones"] = comisiones_estanarizadas
    if depositos_estanarizadas is not None:
        datos_ia_reconciliados["depositos"] = depositos_estanarizadas
    
    return datos_ia_reconciliados, es_documento_digital, texto_verificacion

# ESTA FUNCIÓN ES PARA OBTENER LOS RESULTADOS DEL ANALISIS DE TPV CON REGEX
def procesar_regex_generico(resultados: dict, texto:str, tipo: str) -> Dict[str, Any]:
    """
    Aplica expresiones regulares definidas por banco y retorna resultados.

    Args:
        resultados (dict): El diccionario de los datos encontrados por el modelo.
        texto (str): El texto a procesar.

    Returns:
        Dict[str, Any]: Un diccionario con los resultados.
    """
    # Detectamos el banco
    banco = resultados.get("banco")
    
    # Limpiamos los montos que vengan del json extractor por si vienen mal
    resultados["comisiones"] = limpiar_monto(resultados.get('comisiones', '0.0'))
    resultados["depositos"] = limpiar_monto(resultados.get('depositos', '0.0'))
    resultados["cargos"] = limpiar_monto(resultados.get('cargos', '0.0'))
    resultados["saldo_promedio"] = limpiar_monto(resultados.get('saldo_promedio', '0.0'))

    if not banco:
        resultados["error_transacciones"] = "El nombre del banco no fue proporcionado por el análisis inicial."
        return resultados
    logger.debug("banco encontrado")

    config_compilada = REGEX_COMPILADAS.get(banco.lower())
    if not config_compilada:
        resultados["error_transacciones"] = f"Estamos trabajando para dar soporte al banco: '{banco}'."
        return resultados
    logger.debug("config encontrada")

    datos_crudos = {}
    for clave, patron_compilado in config_compilada.items():
        datos_crudos[clave] = patron_compilado.findall(texto)

    # Creamos un for para encontrar todas las coincidencias en la lista de posibles descripciones
    regex_claves = [
        "descripcion",
        "descripcion_clip_multilinea",
        "descripcion_traspaso_multilinea",
        "descripcion_amex_multilinea",
        "descripción_jpmorgan_multilinea",
        "descripción_traspasoentrecuentas_multilinea",
        "descripción_traspasoentrecuentas_corta"
    ]

    transacciones_matches = []
    for clave in regex_claves:
        if clave in datos_crudos:
            transacciones_matches += datos_crudos[clave]


    if not transacciones_matches:
        resultados["transacciones"] = []
        resultados["depositos_en_efectivo"] = 0.0
        resultados["entradas_TPV_bruto"] = 0.0
        resultados["entradas_TPV_neto"] = 0.0
        # Probamos el nuevo campo de error
        resultados["error_transacciones"] = "Sin coincidencias, el documento no contiene transacciones TPV."

    else:
        # CASO B: Sí se encontraron transacciones, procesamos normalmente
        transacciones_filtradas = []
        # Acumuladores
        total_depositos_efectivo = 0.0
        total_traspaso_entre_cuentas = 0.0
        total_entradas_tpv = 0.0

        for transaccion in transacciones_matches:
            descripcion, monto_str = construir_descripcion_optimizado(transaccion, banco)
            descripcion_limpia = limpiar_y_normalizar_texto(descripcion.strip())

            # Convertimos el monto a float una sola vez para usarlo en las sumas
            monto_float = sumar_lista_montos([monto_str])

            # Ignoramos completamente las transacciones excluidas.
            if all(palabra not in descripcion_limpia.lower() for palabra in PALABRAS_EXCLUIDAS):
                
                # Si la transacción pasó el filtro, ahora la clasificamos.
                if any(palabra in descripcion_limpia.lower() for palabra in PALABRAS_EFECTIVO):
                    # Es un depósito en efectivo
                    total_depositos_efectivo += monto_float
                elif any(palabra in descripcion_limpia.lower() for palabra in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                    # Es un traspaso entre cuentas
                    total_traspaso_entre_cuentas += monto_float
                else:
                    # Si no es excluida, no es efectivo ni traspaso, es una entrada TPV.
                    total_entradas_tpv += monto_float
                
                # 3. AGREGAR: Solo añadimos a la lista final las transacciones que pasaron el filtro.
                transacciones_filtradas.append({
                    "fecha": transaccion[0],
                    "descripcion": descripcion_limpia,
                    "monto": monto_str
                })
        print(total_depositos_efectivo)
        
        resultados["transacciones"] = transacciones_filtradas
        resultados["depositos_en_efectivo"] = total_depositos_efectivo
        resultados["traspaso_entre_cuentas"] = total_traspaso_entre_cuentas
        resultados["entradas_TPV_bruto"] = total_entradas_tpv
        
        comisiones = resultados.get("comisiones") or 0.0
        resultados["entradas_TPV_neto"] = total_entradas_tpv - comisiones
        resultados["error_transacciones"] = None # Nos aseguramos de que no haya mensaje de error

    # El resto de los datos de la IA ya están en 'resultados', por lo que se conservan.
    return resultados

### ----- FUNCIONES ORQUESTADORAS PARA NOMIFLASH -----

# --- PROCESADOR PARA NÓMINA ---
async def procesar_nomina(archivo: UploadFile) -> NomiFlash.RespuestaNomina:
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
        texto_inicial = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)
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
        respuesta_gpt = await analizar_gpt_nomi(PROMPT_NOMINA, imagen_buffers)
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
        return NomiFlash.RespuestaNomina(**datos_listos)

    except Exception as e:
        # Error por procesamiento
        return NomiFlash.RespuestaNomina(error_lectura_nomina=f"Error procesando '{archivo.filename}': {e}")
    
async def procesar_segunda_nomina(archivo: UploadFile) -> NomiFlash.SegundaRespuestaNomina:
    """
    Función auxiliar que procesa los archivos de la segunda nómina siguiendo lógica de negocio interna.
    Tiene comprobación interna con regex para más precisión (RFC Y CURP)
    Devuelve un objeto SegundaRespuestaNomina en caso de éxito o error_lectura_nomina en caso de fallo.
    """
    try:
        # Leer contenido. Si falla, la excepción será capturada.
        pdf_bytes = await archivo.read()

        # --- Lógica de negocio específica para Nómina ---
        # 1. Extraemos texto para la validación con regex
        texto_inicial = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)
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
        respuesta_gpt = await analizar_gpt_nomi(SEGUNDO_PROMPT_NOMINA, imagen_buffers)
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
        return NomiFlash.SegundaRespuestaNomina(**datos_listos)

    except Exception as e:
        # Error por procesamiento
        return NomiFlash.SegundaRespuestaNomina(error_lectura_nomina=f"Error procesando '{archivo.filename}': {e}")
    
# --- PROCESADOR PARA ESTADO DE CUENTA ---
async def procesar_estado_cuenta(archivo: UploadFile) -> NomiFlash.RespuestaEstado:
    """
    Procesa un estado de cuenta, analizando la primera, segunda y última página.
    Ejecuta la lectura de QR y el análisis de IA en paralelo para mayor eficiencia.
    """
    try:
        pdf_bytes = await archivo.read()

        # --- Lógica de negocio específica para Nómina ---
        # 0. Extraemos texto para la validación con regex
        texto_inicial = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)
        rfc, _ = extraer_rfc_curp_por_texto(texto_inicial, "estado")

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
            logger.info(f"Procesando páginas {paginas_a_procesar} para '{archivo.filename}'")
            
        except Exception as e:
            # Si falla, usamos un valor seguro por defecto
            logger.warning(f"No se pudo determinar el total de páginas para '{archivo.filename}': {e}. Usando páginas [1, 2].")
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
        respuesta_gpt = await analizar_gpt_nomi(PROMPT_ESTADO_CUENTA, imagen_buffers)
        datos_crudos = extraer_json_del_markdown(respuesta_gpt)
        datos_listos = sanitizar_datos_ia(datos_crudos)

        # --- Lógica de corrección específica para Nómina ---
        if datos_qr:
            datos_listos["datos_qr"] = datos_qr
        if rfc:
            datos_listos["rfc"] = rfc[-1]

        logger.debug(datos_listos)
        return NomiFlash.RespuestaEstado(**datos_listos)

    except Exception as e:
        return NomiFlash.RespuestaEstado(error_lectura_estado=f"Error procesando '{archivo.filename}': {e}")

# --- PROCESADOR PARA COMPROBANTE DE DOMICILIO ---
def extraer_datos_con_regex(texto: str, tipo_persona: str) -> Optional[Dict]:
    """
    Aplica los patrones de regex compilados, distinguiendo entre campos
    únicos (con search) y listas de campos (con findall).
    """
    patrones_a_usar = PATRONES_CONSTANCIAS_COMPILADO.get(tipo_persona)
    if not patrones_a_usar:
        return None

    datos_extraidos = {}

    # --- Procesamiento de Secciones ---
    for seccion_nombre, campos_compilados in patrones_a_usar.items():
        
        # Lógica para secciones que son LISTAS (Actividades y Regímenes)
        if seccion_nombre in ["actividades_economicas", "regimenes"]:
            lista_resultados = []
            # Asumimos que estas secciones tienen un solo patrón para findall
            # La clave es el singular de la sección (ej. 'actividad' o 'regimen')
            clave_patron = list(campos_compilados.keys())[0]
            logger.debug(f"Usando patrón {clave_patron}")

            patron = campos_compilados[clave_patron]
            logger.debug(f"Patrón: {patron.pattern}")
            
            matches = patron.findall(texto)
            logger.debug(f"Matches encontrados para {seccion_nombre}: {matches}")

            for match_tuple in matches:
                if seccion_nombre == "actividades_economicas":
                    # Mapea la tupla de la regex al diccionario del modelo
                    actividad_principal = match_tuple[1].strip()
                    if tipo_persona == "persona_moral":
                        continuacion_actividad = match_tuple[5].strip() if match_tuple[5] else ""
                        descripcion_completa = f"{actividad_principal} {continuacion_actividad}".strip()
                    
                    lista_resultados.append({
                        "orden": int(match_tuple[0]),
                        "act_economica": descripcion_completa if tipo_persona == "persona_moral" else actividad_principal,
                        "porcentaje": float(match_tuple[2]),
                        "fecha_inicio": match_tuple[3],
                        "fecha_final": match_tuple[4] if match_tuple[4] else None
                    })
                    logger.debug(f"Actividad añadida: {lista_resultados[-1]}")

                elif seccion_nombre == "regimenes":
                    nombre_regimen = match_tuple[0].strip()
                    if not any(char.isdigit() for char in nombre_regimen):
                        lista_resultados.append({
                            "nombre_regimen": nombre_regimen,
                            "fecha_inicio": match_tuple[1],
                            "fecha_fin": match_tuple[2] if match_tuple[2] else None
                        })
            datos_extraidos[seccion_nombre] = lista_resultados
        
        # Lógica para secciones que son DICCIONARIOS (Identificación y Domicilio)
        else:
            datos_seccion = {}
            for nombre_campo, patron in campos_compilados.items():
                match = patron.search(texto)
                logger.debug(f"Match para {nombre_campo}: {match}")
                if match:
                    # Usamos el primer grupo que no sea nulo
                    datos_seccion[nombre_campo] = match.group(1).strip()
            datos_extraidos[seccion_nombre] = datos_seccion

    # Verificación final: si no se extrajo el RFC, la operación no fue exitosa.
    if not datos_extraidos.get("identificacion_contribuyente", {}).get("rfc"):
        return None
        
    return datos_extraidos

async def procesar_comprobante(archivo: UploadFile) -> NomiFlash.RespuestaComprobante:
    """
    Procesa un archivo de comprobante de domicilio.
    Devuelve un objeto RespuestaComprobante en caso de éxito o error_lectura_comprobante en caso de fallo.
    """
    try:
        pdf_bytes = await archivo.read()

        # 1. Convertimos los PDF a imagenes (con loop executor para no bloquear el servidor)
        loop = asyncio.get_running_loop()

        imagen_buffers = await loop.run_in_executor(
            None, convertir_pdf_a_imagenes, pdf_bytes
        )

        respuesta_ia = await analizar_gpt_nomi(PROMPT_COMPROBANTE, imagen_buffers)
        datos_crudos = extraer_json_del_markdown(respuesta_ia)
        datos_listos = sanitizar_datos_ia(datos_crudos)
        return NomiFlash.RespuestaComprobante(**datos_listos)
    
    except Exception as e: 
        return NomiFlash.RespuestaComprobante(error_lectura_comprobante=f"Error procesando '{archivo.filename}': {e}")
    

# --- PROCESADOR PARA CONTANCIA DE SITUACIÓN FISCAL ---
async def procesar_constancia(archivo: UploadFile) -> CSF.ResultadoConsolidado:
    """
    Procesa un archivo de constancia de situación fiscal priorizando regex y usando la IA como fallback.
    Devuelve un objeto RestuladoConsolidado en caso de éxito o error_lectura_csf en caso de fallo.

    args:
        archivo (UploadFile) = Archivo de entrada proveniente del endpoint (en memoria).
    returns:
        RestuladoConsolidado = Objeto de la clase CSF con el formato a seguir para el json en respuesta del archivo.
    """
    resultado_final = CSF.ResultadoConsolidado()

    try:
        # 1. Extraemos el texto del pdf
        pdf_bytes = await archivo.read()
        texto = extraer_texto_de_pdf(pdf_bytes, num_paginas=2)

        if not texto:
            # Aqui se va a empezar la lógica por si es una iamgen
            raise ValueError("No se pudo extraer texto del PDF. Puede estar dañado o ser una imagen.")

        # 2. Definimos el tipo de persona
        tipo_persona = detectar_tipo_contribuyente(texto)
        logger.debug(f"Tipo de persona detectada: {tipo_persona}")

        if tipo_persona == "desconocido":
            return CSF.ResultadoConsolidado(
                error_lectura_csf=f"No se pudo determinar si '{archivo.filename}' es de una persona física o moral. Por favor, suba una CSF válida."
            )

        # Si es válido, continuamos con el flujo normal
        resultado_final = CSF.ResultadoConsolidado(
            tipo_persona=tipo_persona.replace("_", " ".title())
        )

        # Intento 1: Extracción con Regex
        datos_extraidos = extraer_datos_con_regex(texto, tipo_persona)
        logger.debug(f"Datos extraídos con Regex: {datos_extraidos}")
        
        # Intento 2: Fallback con IA si la Regex falló
        if not datos_extraidos:
            try:
                logger.info("--- Fallback a la IA activado ---")
                logger.warning("Se empezará la extracción de datos con IA.")
                datos_extraidos = await _extraer_datos_con_ia(texto)
            except Exception as e:
                logger.error(f"Error en el fallback de IA: {e}")
                return CSF.ErrorRespuesta("No se pudo extraer los datos de su archivo, intentelo más tarde.")

        # Mapeo de los datos extraídos a los modelos Pydantic
        if datos_extraidos:
            if tipo_persona == "persona_fisica":
                resultado_final.identificacion_contribuyente = CSF.DatosIdentificacionPersonaFisica(
                    **datos_extraidos.get("identificacion_contribuyente", {})
                )
            else:
                resultado_final.identificacion_contribuyente = CSF.DatosIdentificacionPersonaMoral(
                    **datos_extraidos.get("identificacion_contribuyente", {})
                )
            
            resultado_final.domicilio_registrado = CSF.DatosDomicilioRegistrado(
                **datos_extraidos.get("domicilio_registrado", {})
            )

            # Iteramos sobre la lista de actividades y creamos un objeto para cada una.
            actividades_data = datos_extraidos.get("actividades_economicas", [])
            if actividades_data:
                resultado_final.actividad_economica = [
                    CSF.ActividadEconomica(**actividad) for actividad in actividades_data
                ]

            # Hacemos lo mismo para la lista de regímenes.
            regimenes_data = datos_extraidos.get("regimenes", [])
            if regimenes_data:
                resultado_final.regimen_fiscal = [
                    CSF.Regimen(**regimen) for regimen in regimenes_data
                ]
    except Exception as e:
        resultado_final.error_lectura_csf = f"Error procesando '{archivo.filename}': {e}"

    return resultado_final