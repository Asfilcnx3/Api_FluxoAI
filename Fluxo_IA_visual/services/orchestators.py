from ..utils.helpers import (
    es_escaneado_o_no, extraer_datos_por_banco, extraer_json_del_markdown, limpiar_monto, sanitizar_datos_ia, 
    reconciliar_resultados_ia, detectar_tipo_contribuyente, crear_chunks_con_superposicion, crear_objeto_resultado, calcular_rangos_de_cuentas
    
)
from .ia_extractor import (
    analizar_gpt_fluxo, analizar_gemini_fluxo, analizar_gpt_nomi, _extraer_datos_con_ia, llamar_agente_tpv, llamar_agente_ocr_vision
)
from ..utils.helpers_texto_fluxo import (
    PALABRAS_BMRCASH, PALABRAS_EXCLUIDAS, PALABRAS_EFECTIVO, PALABRAS_TRASPASO_ENTRE_CUENTAS, PALABRAS_TRASPASO_FINANCIAMIENTO, prompt_base_fluxo
)
from ..utils.helpers_texto_nomi import (
    PROMPT_COMPROBANTE, PROMPT_ESTADO_CUENTA, PROMPT_NOMINA, SEGUNDO_PROMPT_NOMINA
)
from ..utils.helpers_texto_csf import (
    PATRONES_CONSTANCIAS_COMPILADO
)

from .pdf_processor import (
    extraer_movimientos_con_posiciones, extraer_texto_de_pdf, convertir_pdf_a_imagenes, leer_qr_de_imagenes
)

from ..utils.helpers import extraer_rfc_curp_por_texto
from ..models.responses import NomiFlash, CSF, AnalisisTPV

from typing import Dict, Any, Tuple, Optional, Union, List
from fastapi import UploadFile
from io import BytesIO
import logging
import fitz
import asyncio

logger = logging.getLogger(__name__)

# ----- FUNCIONES ORQUESTADORAS DE FLUXO -----
async def analizar_metadatos_rango(
    pdf_bytes: bytes, 
    paginas_a_analizar: List[int],
    prompt: str
) -> Dict[str, Any]:
    """
    Ejecuta el análisis de IA (Visión) para un conjunto específico de páginas 
    (usualmente la primera de una cuenta nueva) para obtener metadatos.
    """
    # 1. Llamadas en paralelo a las IAs
    tarea_gpt = analizar_gpt_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_a_analizar)
    tarea_gemini = analizar_gemini_fluxo(prompt, pdf_bytes, paginas_a_procesar=paginas_a_analizar)
    
    resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_gemini, return_exceptions=True)
    res_gpt_str, res_gemini_str = resultados_ia_brutos

    # 2. Extracción de JSON
    datos_gpt = extraer_json_del_markdown(res_gpt_str) if not isinstance(res_gpt_str, Exception) else {}
    datos_gemini = extraer_json_del_markdown(res_gemini_str) if not isinstance(res_gemini_str, Exception) else {}

    # 3. Sanitización
    datos_gpt_sanitizados = sanitizar_datos_ia(datos_gpt)
    datos_gemini_sanitizados = sanitizar_datos_ia(datos_gemini)

    # 4. Reconciliación
    datos_reconciliados = reconciliar_resultados_ia(datos_gpt_sanitizados, datos_gemini_sanitizados)
    
    return datos_reconciliados

# ESTA FUNCIÓN ES PARA OBTENER Y PROCESAR LAS PORTADAS DE LOS PDF
async def obtener_y_procesar_portada(prompt:str, pdf_bytes: bytes) -> Tuple[Dict[str, Any], bool, str, Dict[int, Any]]:
    """
    Orquesta el proceso de forma secuencial siguiendo el siguiente roadmap:
    1. Extrae texto por página Y movimientos con coordenadas.
    2. Reconoce el banco.
    3. Decide qué páginas enviar a la IA.
    4. Llama a la IA con las páginas correctas.
    5. Corrige su respuesta.
    """
    loop = asyncio.get_running_loop()

    # --- 1. PRIMERO: Extraer Texto Y Movimientos en una sola llamada --- La ejecutamos en un hilo separado para no bloquear el programa.
    movimientos_por_pagina, texto_por_pagina, puntos_de_corte = await loop.run_in_executor(
        None,
        extraer_movimientos_con_posiciones,
        pdf_bytes
    )

    # Construimos el texto de verificación completo a partir de las páginas
    texto_verificacion = "\n".join(texto_por_pagina.values())

    # Determinamos si es escaneado o digital
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
    
    return datos_ia_reconciliados, es_documento_digital, texto_verificacion, movimientos_por_pagina, texto_por_pagina, puntos_de_corte
    
async def procesar_documento_con_agentes_async(
    ia_data_inicial: dict, 
    texto_por_pagina: Dict[int, str], 
    movimientos_por_pagina: Dict[int, Any],
    filename: str,
    pdf_bytes: bytes, 
    puntos_de_corte: List[int] = None
) -> List[Dict[str, Any]]:
    
    logger.info(f"Iniciando procesamiento multicuenta para: {filename}")
    banco = ia_data_inicial.get("banco", "generico").lower()
    
    # 1. Definir Rangos
    rangos_a_procesar = []
    if banco == "banbajío" and puntos_de_corte:
        rangos_a_procesar = calcular_rangos_de_cuentas(len(texto_por_pagina), puntos_de_corte)
        # LOG IMPORTANTE
        logger.info(f"MULTICUENTA DETECTADA: Se procesarán {len(rangos_a_procesar)} cuentas separadas.")
    else:
        rangos_a_procesar = [sorted(list(texto_por_pagina.keys()))]

    resultados_multiples_cuentas = []

    # 2. Procesar cada "Sub-Cuenta"
    for i, rango_paginas in enumerate(rangos_a_procesar):
        if not rango_paginas: continue 

        pagina_inicio_rango = rango_paginas[0]
        # Nombre virtual para identificar en el Excel
        nombre_subcuenta = f"{filename} (Cuenta {i+1})" if len(rangos_a_procesar) > 1 else filename
        logger.info(f"Procesando: {nombre_subcuenta} (Págs {rango_paginas[0]}-{rango_paginas[-1]})")
        
        # --- A. LÓGICA DE METADATOS (PORTADA) ---
        if i == 0:
            ia_data_seccion = ia_data_inicial
        else:
            # Lógica: Página del corte + Página anterior
            paginas_para_metadata = [pagina_inicio_rango - 1, pagina_inicio_rango]
            # Aseguramos no pedir página 0 si el corte es en la 1 (aunque el helper ya maneja cortes >1)
            paginas_para_metadata = [p for p in paginas_para_metadata if p > 0]
            
            logger.info(f"Re-analizando metadatos para {nombre_subcuenta} en páginas {paginas_para_metadata}...")
            try:
                ia_data_seccion = await analizar_metadatos_rango(
                    pdf_bytes, paginas_para_metadata, prompt_base_fluxo
                )
                ia_data_seccion["banco"] = ia_data_inicial.get("banco") 
            except Exception as e:
                logger.error(f"Fallo al re-analizar portada para {nombre_subcuenta}: {e}")
                ia_data_seccion = ia_data_inicial.copy()

        # --- B. FILTRAR INPUTS ---
        texto_subset = {k: v for k, v in texto_por_pagina.items() if k in rango_paginas}
        movimientos_subset = {k: v for k, v in movimientos_por_pagina.items() if k in rango_paginas}
        paginas_con_movimientos = [p for p, m in movimientos_subset.items() if m]
        
        if not paginas_con_movimientos:
            logger.warning(f"La cuenta {nombre_subcuenta} no tiene movimientos. Generando reporte vacío.")
            # ERROR CORREGIDO: No hacer continue sin guardar un resultado vacío
            resultado_vacio = {
                **ia_data_seccion,
                "nombre_archivo_virtual": nombre_subcuenta,
                "transacciones": [],
                "depositos_en_efectivo": 0.0, "traspaso_entre_cuentas": 0.0,
                "total_entradas_financiamiento": 0.0, "entradas_bmrcash": 0.0,
                "entradas_TPV_bruto": 0.0, "entradas_TPV_neto": 0.0,
                "error_transacciones": "Sin movimientos detectados en esta sección."
            }
            resultados_multiples_cuentas.append(resultado_vacio)
            continue

        # --- C. CHUNKING Y AGENTES ---
        chunks = crear_chunks_con_superposicion(
            texto_por_pagina=texto_subset,
            paginas_con_movimientos=paginas_con_movimientos,
            tamano_chunk=5, superposicion=1
        )
        
        tareas = [llamar_agente_tpv(banco, txt, pags) for txt, pags in chunks]
        res_chunks = await asyncio.gather(*tareas, return_exceptions=True)
        
        # --- D. CONSOLIDACIÓN ---
        transacciones_totales = []
        ids_unicos = set()
        for res in res_chunks:
            if not isinstance(res, Exception):
                for trx in res:
                    id_trx = f"{trx.get('fecha')}-{trx.get('monto')}-{trx.get('descripcion', '')[:15]}"
                    if id_trx not in ids_unicos:
                        transacciones_totales.append(trx)
                        ids_unicos.add(id_trx)
        
        # --- ERROR ANTERIOR CORREGIDO AQUI ---
        if not transacciones_totales:
            logger.warning(f"Agentes no encontraron transacciones en {nombre_subcuenta}.")
            resultado_sin_trx = {
                **ia_data_seccion,
                "nombre_archivo_virtual": nombre_subcuenta,
                "transacciones": [],
                "depositos_en_efectivo": 0.0, "traspaso_entre_cuentas": 0.0,
                "total_entradas_financiamiento": 0.0, "entradas_bmrcash": 0.0,
                "entradas_TPV_bruto": 0.0, "entradas_TPV_neto": 0.0,
                "error_transacciones": "Agentes LLM no encontraron transacciones TPV."
            }
            resultados_multiples_cuentas.append(resultado_sin_trx)
            continue # ¡CONTINUAR, NO RETORNAR!
        
        # --- E. CLASIFICACIÓN DE NEGOCIO ---
        total_depositos_efectivo = 0.0
        total_traspaso_entre_cuentas = 0.0
        total_entradas_financiamiento = 0.0
        total_entradas_bmrcash = 0.0
        total_entradas_tpv = 0.0
        transacciones_clasificadas = []

        for trx in transacciones_totales:
            monto_float = trx.get("monto", 0.0)
            if not isinstance(monto_float, (int, float)):
                monto_float = limpiar_monto(str(monto_float))

            descripcion_limpia = trx.get("descripcion", "").lower()

            if all(palabra not in descripcion_limpia for palabra in PALABRAS_EXCLUIDAS):
                if any(palabra in descripcion_limpia for palabra in PALABRAS_EFECTIVO):
                    total_depositos_efectivo += monto_float
                elif any(palabra in descripcion_limpia for palabra in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                    total_traspaso_entre_cuentas += monto_float
                elif any(palabra in descripcion_limpia for palabra in PALABRAS_TRASPASO_FINANCIAMIENTO):
                    total_entradas_financiamiento += monto_float
                elif any(palabra in descripcion_limpia for palabra in PALABRAS_BMRCASH):
                    total_entradas_bmrcash += monto_float
                else:
                    total_entradas_tpv += monto_float
                
                transacciones_clasificadas.append({
                    "fecha": trx.get("fecha"),
                    "descripcion": trx.get("descripcion"),
                    "monto": f"{monto_float:,.2f}",
                    "tipo": trx.get("tipo", "abono") 
                })

        # --- F. ENSAMBLE FINAL ---
        comisiones_str = ia_data_seccion.get("comisiones", "0.0")
        comisiones = limpiar_monto(comisiones_str)
        entradas_TPV_neto = total_entradas_tpv - comisiones

        resultado_cuenta = {
            **ia_data_seccion,
            "nombre_archivo_virtual": nombre_subcuenta,
            "transacciones": transacciones_clasificadas,
            "depositos_en_efectivo": total_depositos_efectivo,
            "traspaso_entre_cuentas": total_traspaso_entre_cuentas,
            "total_entradas_financiamiento": total_entradas_financiamiento,
            "entradas_bmrcash": total_entradas_bmrcash,
            "entradas_TPV_bruto": total_entradas_tpv,
            "entradas_TPV_neto": entradas_TPV_neto,
            "error_transacciones": None
        }
        resultados_multiples_cuentas.append(resultado_cuenta)

    return resultados_multiples_cuentas

async def procesar_documento_escaneado_con_agentes_async(
    ia_data: dict, 
    pdf_bytes: bytes, 
    filename: str
) -> List[Dict[str, Any]]: 
    
    logger.info(f"Iniciando procesamiento OCR-Visión para: {filename}")
    banco = ia_data.get("banco", "generico")
    
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total_paginas = len(doc)
    except Exception:
        return [{**ia_data, "error_transacciones": "No se pudo leer el PDF (corrupto)."}]

    # Chunking por páginas
    TAMANO_CHUNK, SUPERPOSICION = 2, 1
    chunks_paginas = []
    i = 0
    while i < total_paginas:
        paginas = list(range(i + 1, min(i + TAMANO_CHUNK, total_paginas) + 1))
        if not paginas: break
        chunks_paginas.append(paginas)
        i += (TAMANO_CHUNK - SUPERPOSICION)

    # Llamadas a Agente
    tareas = [llamar_agente_ocr_vision(banco, pdf_bytes, pags) for pags in chunks_paginas]
    res_chunks = await asyncio.gather(*tareas, return_exceptions=True)

    # Consolidación
    transacciones_totales = []
    ids_unicos = set()
    for res in res_chunks:
        if not isinstance(res, Exception):
            for trx in res:
                id_trx = f"{trx.get('fecha')}-{trx.get('monto')}-{trx.get('descripcion', '')[:15]}"
                if id_trx not in ids_unicos:
                    transacciones_totales.append(trx)
                    ids_unicos.add(id_trx)

    # --- E. CLASIFICACIÓN DE NEGOCIO (AHORA FUERA DEL BUCLE) ---
    total_depositos_efectivo = 0.0
    total_traspaso_entre_cuentas = 0.0
    total_entradas_financiamiento = 0.0
    total_entradas_bmrcash = 0.0
    total_entradas_tpv = 0.0
    transacciones_clasificadas = []

    for trx in transacciones_totales:
        monto_float = trx.get("monto", 0.0)
        if not isinstance(monto_float, (int, float)):
            monto_float = limpiar_monto(str(monto_float))

        descripcion_limpia = trx.get("descripcion", "").lower()

        if all(palabra not in descripcion_limpia for palabra in PALABRAS_EXCLUIDAS):
            if any(palabra in descripcion_limpia for palabra in PALABRAS_EFECTIVO):
                total_depositos_efectivo += monto_float
            elif any(palabra in descripcion_limpia for palabra in PALABRAS_TRASPASO_ENTRE_CUENTAS):
                total_traspaso_entre_cuentas += monto_float
            elif any(palabra in descripcion_limpia for palabra in PALABRAS_TRASPASO_FINANCIAMIENTO):
                total_entradas_financiamiento += monto_float
            elif any(palabra in descripcion_limpia for palabra in PALABRAS_BMRCASH):
                total_entradas_bmrcash += monto_float
            else:
                total_entradas_tpv += monto_float
            
            transacciones_clasificadas.append({
                "fecha": trx.get("fecha"),
                "descripcion": trx.get("descripcion"),
                "monto": f"{monto_float:,.2f}",
                "tipo": trx.get("tipo", "abono") 
            })

    # --- F. ENSAMBLE FINAL DE LA CUENTA ---
    comisiones_str = ia_data.get("comisiones", "0.0")
    comisiones = limpiar_monto(comisiones_str)
    entradas_TPV_neto = total_entradas_tpv - comisiones

    # Retorno (Envuelto en lista)
    return [{
        **ia_data, 
        "nombre_archivo_virtual": filename,
        "transacciones": transacciones_clasificadas,
        "depositos_en_efectivo": total_depositos_efectivo,
        "traspaso_entre_cuentas": total_traspaso_entre_cuentas,
        "total_entradas_financiamiento": total_entradas_financiamiento,
        "entradas_bmrcash": total_entradas_bmrcash,
        "entradas_TPV_bruto": total_entradas_tpv,
        "entradas_TPV_neto": entradas_TPV_neto,
        "error_transacciones": None
    }]

def procesar_digital_worker_sync(
    ia_data_inicial: dict, 
    texto_por_pagina: Dict[int, str], 
    movimientos_por_pagina: Dict[int, Any], 
    filename: str,
    pdf_bytes: bytes, 
    puntos_de_corte: List[int] = None
) -> Union[List[AnalisisTPV.ResultadoExtraccion], Exception]:
    try:
        lista_dicts = asyncio.run(
            procesar_documento_con_agentes_async(
                ia_data_inicial, texto_por_pagina, movimientos_por_pagina, 
                filename, pdf_bytes, puntos_de_corte
            )
        )
        return [crear_objeto_resultado(d) for d in lista_dicts]
    except Exception as e:
        logger.error(f"Error Worker Digital ({filename}): {e}", exc_info=True)
        return e

def procesar_ocr_worker_sync(
    ia_data: dict, 
    pdf_content: bytes, 
    filename: str
) -> Union[List[AnalisisTPV.ResultadoExtraccion], Exception]:
    try:
        lista_dicts = asyncio.run(
            procesar_documento_escaneado_con_agentes_async(
                ia_data, pdf_content, filename
            )
        )
        return [crear_objeto_resultado(d) for d in lista_dicts]
    except Exception as e:
        logger.error(f"Error Worker OCR ({filename}): {e}", exc_info=True)
        return e

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
        # 2.5 Log de RFC y CURP extraídos
        logger.info(f"Se extrajo el RFC: {rfc[-1] if rfc else None}")
        logger.info(f"Se extrajo el CURP: {curp[-1] if curp else None}")

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
        logger.info(f"Se extrajo el RFC: {rfc[0] if rfc else None}")

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
            logger.info(f"RFC extraído: {rfc[0]}")
            datos_listos["rfc"] = rfc[0]

        logger.debug(datos_listos)
        return NomiFlash.RespuestaEstado(**datos_listos)

    except Exception as e:
        return NomiFlash.RespuestaEstado(error_lectura_estado=f"Error procesando '{archivo.filename}': {e}")

# --- PROCESADOR PARA COMPROBANTE DE DOMICILIO ---
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