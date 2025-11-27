from concurrent.futures import ProcessPoolExecutor
from fastapi.encoders import jsonable_encoder
from fastapi import APIRouter, Query, UploadFile, File, HTTPException, BackgroundTasks
from typing import Union, List
import logging
import asyncio
import zipfile
import uuid
import io

from fastapi.responses import FileResponse

from ...models.responses import AnalisisTPV, RespuestaProcesamientoIniciado
from ...core.exceptions import PDFCifradoError
from ...services.storage_service import obtener_ruta_archivo, guardar_excel_local, guardar_json_local, obtener_datos_json
from ...utils.xlsx_converter import generar_excel_reporte
from ...services.orchestators import obtener_y_procesar_portada, procesar_digital_worker_sync, procesar_ocr_worker_sync
from ...utils.helpers import total_depositos_verificacion
from ...utils.helpers_texto_fluxo import prompt_base_fluxo

router = APIRouter()

logger = logging.getLogger(__name__)


# Endpoint principal 
@router.post(
        "/fluxo/procesar_pdf/", 
        response_model = RespuestaProcesamientoIniciado,
        summary="Extrae datos estructurados de trasacciones TPV en PDF's individuales o de un archivo ZIP."
    )
async def procesar_pdf_api(
    background_tasks: BackgroundTasks, # Inyección necesaria
    archivos: List[UploadFile] = File(..., description="Uno o más archivos PDF o .ZIP a extraer transacciones TPV")
):
    """
    Sube uno o más archivos PDF. El sistema procesa todos en paralelo y devuelve resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_transacciones` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error y un error global `ErrorRespuesta`.
    """
    # ----- Generar un ID único para este trabajo -----
    job_id = str(uuid.uuid4())

    # ------- listas a usar más adelante -------
    tareas_analisis = []
    archivos_en_memoria = []

    # --- 0. Lógica para manejar los archivos individuales y .zip ---
    for archivo in archivos:
        logger.info("Se ha empezado la extracción")
        # --- Lógica para manejar archivos ZIP ---
        if archivo.content_type in ["application/zip", "application/x-zip-compressed"] or archivo.filename.lower().endswith('.zip'):
            # Leemos el contenido del ZIP en memoria
            contenido_zip = await archivo.read()
            zip_buffer = io.BytesIO(contenido_zip)

            # Usamos zipfile para leer del buffer en memoria
            with zipfile.ZipFile(zip_buffer) as zf:
                for nombre_archivo_en_zip in zf.namelist():
                    # Filtramos para procesar solo archivos PDF y evitar carpetas o archivos del sistema
                    if nombre_archivo_en_zip.lower().endswith('.pdf') and not nombre_archivo_en_zip.startswith('__MACOSX'):
                        # Leemos el contenido del PDF desde el ZIP
                        contenido_pdf = zf.read(nombre_archivo_en_zip)
                        # Añadimos el PDF extraído a nuestra lista de procesamiento
                        archivos_en_memoria.append({"filename": nombre_archivo_en_zip, "content": contenido_pdf})

            logger.info("Extracción de Archivos '.zip' finalizada")
        # --- Lógica para manejar archivos PDF individuales ---
        elif archivo.content_type == "application/pdf":
            # usamos await para leer el archivo en paralelo
            contenido_pdf = await archivo.read()
            archivos_en_memoria.append({"filename": archivo.filename, "content": contenido_pdf})
            logger.info("Extracción de archivos '.pdf' finalizada")
        
        else:
            # Si el archivo no es ni PDF ni ZIP, lo ignoramos (o podríamos devolver un error)
            logger.error(f"Archivo '{archivo.filename}' ignorado. No es un PDF o ZIP válido.")
            # Para devolver un error, tendrías que manejarlo de forma más compleja. Por ahora, simplemente lo saltamos.

    # Si después de extraer los ZIPs no queda ningún PDF, devolvemos un error.
    if not archivos_en_memoria:
        raise HTTPException(
            status_code=400,
            detail="No subiste ningun archivo PDF válido."
        )
    async def tarea_pesada_background(job_id: str, docs: list):
        logger.info(f"Iniciando Job {job_id}")

        # --- 1. ANÁLISIS DE LA PORTADA CON IA PARA DETERMINAR ENTRADAS Y SI ES DOCUMENTO ESCANEADO ---
        logger.info("Analisis de Portada Inicializado para todos los documentos")
        for doc in archivos_en_memoria:
            # 'obtener_y_procesar_portada' solo hace el análisis inicial de IA y extracción de texto/posiciones
            tarea = obtener_y_procesar_portada(prompt_base_fluxo, doc["content"])
            tareas_analisis.append(tarea)    

        try:
            resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error crítico durante la Etapa 1 (Análisis IA): {str(e)}")

        logger.info("Etapa 1: Análisis de portada finalizado.")

        # --- 2. SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS (Y CALCULOS TOTALES) ---
        # Preparamos las listas para el siguiente paso.
        documentos_digitales = []
        documentos_escaneados = []

        # Creamos una lista final de resultados, pre-llenada para mantener el orden.
        resultados_finales: List[Union[AnalisisTPV.ResultadoExtraccion, None]] = [None] * len(archivos_en_memoria)

        # Obtenemos el total de depósitos para la decisión de OCR
        total_depositos_calculado, es_mayor = total_depositos_verificacion(resultados_portada) # la primer variable puede ser usada en el futuro

        logger.info("Empezando la separación de documentos")
        for i, resultado_bruto in enumerate(resultados_portada):
            filename = archivos_en_memoria[i]["filename"]
            # VERIFICACIÓN 1: ¿La tarea falló por completo?
            if isinstance(resultado_bruto, Exception):
                # Verificamos si es nuestro error de contraseña
                if isinstance(resultado_bruto, PDFCifradoError):
                    logger.warning(f"Documento número {i} con contraseña")
                    error_msg = "Documento con contraseña, imposible trabajar con este documento."
                    resultados_finales[i] = AnalisisTPV.ResultadoExtraccion(
                        AnalisisIA=None,
                        DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=error_msg))
                else:
                    logger.error(f"Fallo en el procesamiento inicial de {filename}")
                    # Para cualquier otro error inesperado en la etapa inicial
                    error_msg = f"Fallo el procesamiento inicial de '{filename}': {str(resultado_bruto)}"
                    resultados_finales[i] = AnalisisTPV.ResultadoExtraccion(
                        AnalisisIA=None,
                        DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=error_msg)
                    )
                continue # Pasamos al siguiente archivo
            
            # Si no hubo error, desempacamos los resultados
            datos_ia, es_digital, texto_inicial, movimientos_pagina, texto_por_pagina = resultado_bruto
            # Intenta procesar este archivo, preparado para cualquier error
            try:
                # Sea digital o escaneado se prepara para extracción
                if es_digital:
                    documentos_digitales.append({
                        "index": i, 
                        "filename": filename,
                        "ia_data": datos_ia, 
                        "texto_por_pagina": texto_por_pagina, 
                        "movimientos": movimientos_pagina
                    })
                else:
                    documentos_escaneados.append({
                        "index": i, 
                        "filename": filename,
                        "content": archivos_en_memoria[i]["content"], 
                        "ia_data": datos_ia
                    })

            # Red de validación
            except Exception as e:
                logger.error("La separación de documentos falló durante la etapa 2.")
                # Si algo falla en el 'try' (como una ValidationError de Pydantic), se capturamos.
                resultados_finales[i] = AnalisisTPV.ErrorRespuesta(
                    error=f"Error al procesar los datos de la extracción inicial en: '{filename}'. Vuelve a mandar este archivo."
                )
        logger.info(f"Separación finalizada. Digitales: {len(documentos_digitales)}, Escaneados: {len(documentos_escaneados)}")

        # --- ETAPA 3: PROCESAMIENTO PRINCIPAL (CPU PESADO) ---
        loop = asyncio.get_running_loop()

        # Listas para guardar las tareas y sus índices originales
        tareas_digitales = [] # (index, task)
        tareas_ocr = []       # (index, task)

        # Decisión de OCR
        procesar_ocr = es_mayor and documentos_escaneados and len(documentos_escaneados) <= 15

        logger.info(f"Etapa 3: Iniciando ProcessPoolExecutor. (Procesar OCR: {procesar_ocr})")

        with ProcessPoolExecutor() as executor:
            # 3.A - Despachar tareas de Agentes LLM (Digitales)
            for doc_info in documentos_digitales:
                tarea = loop.run_in_executor(
                    executor,
                    procesar_digital_worker_sync, # Worker para digitales
                    doc_info["ia_data"],
                    doc_info["texto_por_pagina"],
                    doc_info["movimientos"],
                    doc_info["filename"] 
                )
                tareas_digitales.append((doc_info["index"], tarea))

            # 3.B - Despachar tareas de OCR (Escaneados)
            if procesar_ocr:
                for doc_info in documentos_escaneados:
                    tarea = loop.run_in_executor(
                        executor,
                        procesar_ocr_worker_sync, # Worker para OCR
                        doc_info["ia_data"],
                        doc_info["content"],
                        doc_info["filename"]
                    )
                    tareas_ocr.append((doc_info["index"], tarea))
            else:
                # 3.C - Manejo de OCR Omitidos (Tu lógica anterior)
                if documentos_escaneados:
                    if len(documentos_escaneados) > 15:
                        error_msg = "La cantidad de documentos escaneados supera el límite de 15."
                    elif not es_mayor:
                        error_msg = "Este documento es escaneado y el total de depósitos no supera los $250,000."
                    else:
                        error_msg = "El procesamiento OCR fue omitido por seguridad."

                    for doc_info in documentos_escaneados:
                        error_obj = AnalisisTPV.ErrorRespuesta(error=error_msg)
                        resultados_finales[doc_info["index"]] = AnalisisTPV.ResultadoExtraccion(
                            AnalisisIA=doc_info["ia_data"],
                            DetalleTransacciones=error_obj
                        )

            # 3.D - Esperar a que los workers terminen (EN DOS GRUPOS SEPARADOS)

            # Grupo 1: Digitales (sin timeout)
            resultados_brutos_digitales = []
            if tareas_digitales:
                logger.info(f"Esperando que {len(tareas_digitales)} tareas digitales terminen...")
                resultados_brutos_digitales = await asyncio.gather(*[t[1] for t in tareas_digitales], return_exceptions=True)
                logger.info("Tareas digitales finalizadas.")

            # Grupo 2: OCR (CON timeout)
            resultados_brutos_ocr = []
            ocr_timed_out = False
            if tareas_ocr:
                OCR_TIMEOUT_SECONDS = 13 * 60  # 13 minutos
                logger.info(f"Iniciando {len(tareas_ocr)} tareas de OCR con un límite de {OCR_TIMEOUT_SECONDS}s.")
                try:
                    # Ejecutamos las tareas de OCR en paralelo CON TIMEOUT
                    resultados_brutos_ocr = await asyncio.wait_for(
                        asyncio.gather(*[t[1] for t in tareas_ocr], return_exceptions=True),
                        timeout=OCR_TIMEOUT_SECONDS
                    )
                    logger.info("Tareas OCR finalizadas.")

                except asyncio.TimeoutError:
                    ocr_timed_out = True
                    logger.warning(f"El procesamiento OCR superó el límite de {OCR_TIMEOUT_SECONDS}s y fue cancelado.")

                    error_msg = f"El procesamiento OCR fue cancelado por exceder el límite de {OCR_TIMEOUT_SECONDS} segundos."
                    error_obj = AnalisisTPV.ErrorRespuesta(error=error_msg)

                    # Llenamos los resultados finales con los datos iniciales de la IA y el error de timeout
                    for index, _ in tareas_ocr:
                        # Buscamos el doc_info original que corresponde a esta tarea
                        doc_info = next(doc for doc in documentos_escaneados if doc["index"] == index)
                        resultados_finales[index] = AnalisisTPV.ResultadoExtraccion(
                            AnalisisIA=doc_info["ia_data"],
                            DetalleTransacciones=error_obj
                        )
        logger.info("Etapa 3: Todos los procesos han terminado.")

        # --- 4. RECOLECTAR Y ENSAMBLAR RESULTADOS ---
        logger.info("Etapa 4: Ensamblando respuesta final.")

        # Recolectar resultados digitales
        for i, (index, _) in enumerate(tareas_digitales):
            resultado = resultados_brutos_digitales[i]
            filename = archivos_en_memoria[index]["filename"]

            if isinstance(resultado, Exception):
                error_msg = f"Fallo el procesamiento completo (Digital) de '{filename}': {str(resultado)}"
                resultados_finales[index] = AnalisisTPV.ResultadoExtraccion(
                    AnalisisIA=None, # Asumimos que si el worker falla, no hay datos fiables
                    DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=error_msg)
                )
            else:
                resultados_finales[index] = resultado

        # Recolectar resultados OCR (solo si no hubo timeout)
        if not ocr_timed_out:
            for i, (index, _) in enumerate(tareas_ocr):
                resultado = resultados_brutos_ocr[i]
                filename = archivos_en_memoria[index]["filename"]

                if isinstance(resultado, Exception):
                    error_msg = f"Fallo el procesamiento completo (OCR) de '{filename}': {str(resultado)}"
                    resultados_finales[index] = AnalisisTPV.ResultadoExtraccion(
                        AnalisisIA=None,
                        DetalleTransacciones=AnalisisTPV.ErrorRespuesta(error=error_msg)
                    )
                else:
                    resultados_finales[index] = resultado

        # --- 5. ENSAMBLE DE LA RESPUESTA FINAL ---
        resultados_limpios = [res for res in resultados_finales if res is not None]
        resultados_generales = [res.AnalisisIA for res in resultados_limpios if res.AnalisisIA is not None]

        # Recalculamos el total de depósitos basado en los resultados exitosos
        total_depositos_final = sum(
            res.AnalisisIA.depositos for res in resultados_limpios 
            if res.AnalisisIA and res.AnalisisIA.depositos
        )
        es_mayor_final = total_depositos_final > 250000

        # Creamos el objeto final
        respuesta_final = AnalisisTPV.ResultadoTotal(
            total_depositos = total_depositos_final,
            es_mayor_a_250 = es_mayor_final,
            resultados_generales = resultados_generales,
            resultados_individuales = resultados_limpios
        )

        # 1. Convertir a Excel (Bytes)
        datos_dict = jsonable_encoder(respuesta_final)
        excel_bytes = generar_excel_reporte(datos_dict)
        
        # 2. Guardar JSON (Opcional, útil para debug/frontend)
        guardar_json_local(datos_dict, job_id)

        # 3. Guardar Excel
        guardar_excel_local(excel_bytes, job_id)
        
        logger.info(f"Job {job_id} finalizado. Excel generado.")

    # 4. LANZAR AL FONDO Y RESPONDER INMEDIATAMENTE
    background_tasks.add_task(tarea_pesada_background, job_id, archivos_en_memoria)

    return RespuestaProcesamientoIniciado(
        mensaje="El procesamiento ha comenzado. Usa el job_id para descargar el resultado en unos minutos.",
        job_id=job_id,
        estatus="procesando"
    )

@router.get("/fluxo/descargar-resultado/{job_id}")
async def descargar_resultado(
    job_id: str,
    formato: str = Query("excel", enum=["excel", "json"], description="El formato de respuesta deseado: 'excel' para descargar archivo, 'json' para ver datos.")
):
    """
    Consulta el estado del trabajo. Si terminó, devuelve:
    1. El objeto JSON completo del análisis.
    2. El contenido del CSV en formato string para descarga en frontend.
    """
    if formato == "json":
        datos = obtener_datos_json(job_id)
        if datos:
            return datos # FastAPI lo convierte a JSON response automáticamente
        else:
            # Si no hay JSON, revisamos si sigue procesando o falló
            raise HTTPException(
                status_code=404, 
                detail="Los datos no están listos aún o el ID es incorrecto."
            )
    else:
        ruta_archivo = obtener_ruta_archivo(job_id)
        if ruta_archivo:
            return FileResponse(
                path=ruta_archivo, 
                filename=f"Reporte_Analisis_{job_id}.xlsx", # Extensión .xlsx
                # MIME type oficial para Excel .xlsx
                media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )

        else:
            # Si no existe aún, asumimos que sigue procesando (o falló/no existe)
            # En un sistema real usaríamos una DB para diferenciar "procesando" de "falló",
            # pero para esto, un 404 o 202 es suficiente.
            raise HTTPException(
                status_code=404, 
                detail="El archivo no está listo aún o el ID es incorrecto. Intenta de nuevo en unos momentos."
            )