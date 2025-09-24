from concurrent.futures import ProcessPoolExecutor
from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Union, List
import logging
import asyncio
import zipfile
import io


from ...models.responses import AnalisisTPV
from ...core.exceptions import PDFCifradoError
from ...services.orchestators import procesar_regex_generico, obtener_y_procesar_portada
from ...services.pdf_processor import extraer_texto_con_ocr
from ...utils.helpers import total_depositos_verificacion, crear_objeto_resultado
from ...utils.helpers_texto_fluxo import prompt_base_fluxo

router = APIRouter()

logger = logging.getLogger(__name__)


# Endpoint principal 
@router.post(
        "/fluxo/procesar_pdf/", 
        response_model = AnalisisTPV.ResultadoTotal,
        summary="Extrae datos estructurados de trasacciones TPV en PDF's individuales o de un archivo ZIP."
    )
async def procesar_pdf_api(
    archivos: List[UploadFile] = File(..., description="Uno o más archivos PDF o .ZIP a extraer transacciones TPV")
):
    """
    Sube uno o más archivos PDF. El sistema procesa todos en paralelo y devuelve resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_transacciones` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error y un error global `ErrorRespuesta`.
    """

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
    
    # ------- 1. ANÁLISIS DE LA PORTADA CON IA PARA DETERMINAR ENTRADAS Y SI ES DOCUMENTO ESCANEADO -------
    logger.info("Analisis de Portada Inicializado")
    for doc in archivos_en_memoria:
        tarea = obtener_y_procesar_portada(prompt_base_fluxo, doc["content"])
        tareas_analisis.append(tarea)    
    try:
        # Ejecutamos todas las llamadas a la IA al mismo tiempo
        resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
    except Exception as e:
        # En caso de que la llamada de la IA falle de forma masiva, detenemos todo.
        raise HTTPException(status_code=500, detail=f"Error crítico durante el análisis con IA: {str(e)}")

    # Suma de depósitos y decisión
    logger.debug("--- RESULTADOS PORTADA ----")
    logger.info("Resultado de la portada obtenido -- Análisis finalizado")
    total_depositos_calculado, es_mayor = total_depositos_verificacion(resultados_portada)

    # --- 2. SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS ---
    # Preparamos las listas para el siguiente paso.
    documentos_digitales = []
    documentos_escaneados = []

    # Creamos una lista final de resultados, pre-llenada para mantener el orden.
    resultados_finales: List[Union[AnalisisTPV.ResultadoExtraccion, None]] = [None] * len(archivos_en_memoria)

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
        datos_ia, es_digital, texto_inicial = resultado_bruto
        # Intenta procesar este archivo, preparado para cualquier error
        try:
            # Sea digital o escaneado se prepara para extracción
            if es_digital:
                documentos_digitales.append({"index": i, "content": archivos_en_memoria[i]["content"], "ia_data": datos_ia, "texto": texto_inicial})
            else:
                documentos_escaneados.append({"index": i, "content": archivos_en_memoria[i]["content"], "ia_data": datos_ia})

        # Red de validación
        except Exception as e:
            logger.error("La separación de documentos falló.")
            # Si algo falla en el 'try' (como una ValidationError de Pydantic), se capturamos.
            resultados_finales[i] = AnalisisTPV.ErrorRespuesta(
                error=f"Error al procesar los datos de la extracción inicial en: '{filename}'. Vuelve a mandar este archivo."
            )
    logger.info("Separación finalizada")
    
    # --- 3. PROCESAMIENTO CONCURRENTE Y CENTRALIZADO GENERAL ---
    loop = asyncio.get_running_loop()

    # se comprueba que sea mayor a 250k, que haya escaneados, y que no sean más de 15
    procesar_ocr = es_mayor and documentos_escaneados and len(documentos_escaneados) <= 15

    logger.info("Procesando documentos digitales...")
    for doc_info in documentos_digitales:
        filename = archivos_en_memoria[doc_info['index']]['filename']
        try:
            resultado_dict = procesar_regex_generico(doc_info["ia_data"], doc_info["texto"], "digital")
            resultados_finales[doc_info["index"]] = crear_objeto_resultado(resultado_dict)

        except Exception as e:
            logger.error(f"Fallo el regex en el documento digital: {filename}")
            resultados_finales[doc_info["index"]] = crear_objeto_resultado({
                **doc_info["ia_data"],
                "error_transacciones": f"Fallo Regex en '{filename}': {e}"
            })
    logger.info("Procesamiento de documentos digitales finalizado.")

    if procesar_ocr:
        logger.info("Procesamiento OCR habilitado para documentos escaneados.")
        logger.debug("Iniciando lote de procesamiento con OCR.")
        # Usamos ProcessPoolExecutor para evitar bloquear el event loop
        with ProcessPoolExecutor() as executor:
            # Creamos las tareas de OCR
            tareas_ocr = [
                loop.run_in_executor(executor, extraer_texto_con_ocr, doc["content"])
                for doc in documentos_escaneados
            ]
            # Ejecutamos todas las tareas de OCR en paralelo
            textos_ocr_brutos = await asyncio.gather(*tareas_ocr, return_exceptions=True)
        
            # Procesamos los resultados del OCR
            for i, texto_o_error in enumerate(textos_ocr_brutos):
                doc_info = documentos_escaneados[i]
                if isinstance(texto_o_error, Exception):
                    resultados_finales[doc_info["index"]] = crear_objeto_resultado({
                    **doc_info["ia_data"],
                    "error_transacciones": f"Fallo la extracción de texto en '{filename}': {texto_o_error}"
                    })
                    continue

                try:
                    resultado_dict = procesar_regex_generico(doc_info["ia_data"], texto_o_error, "ocr")
                    resultados_finales[doc_info["index"]] = crear_objeto_resultado(resultado_dict)

                except Exception as e:
                    resultados_finales[doc_info["index"]] = crear_objeto_resultado({
                    **doc_info["ia_data"],
                    "error_transacciones": f"Fallo Regex en '{filename}': {e}"
                    })
        logger.info("Procesamiento OCR finalizado.")

    # --- 4. MANEJO DE ESCANEADOS OMITIDOS ---
    if not procesar_ocr and documentos_escaneados:
        if len(documentos_escaneados) > 15:
            error_msg = "La cantidad de documentos escaneados supera el límite de 15."
        elif not es_mayor:
            error_msg = "Este documento es escaneado y el total de depósitos no supera los $250,000."
        else:
            # Caso improbable, pero es bueno tener un fallback
            error_msg = "El procesamiento OCR fue omitido por seguridad."

        # Asignamos el mismo error a todos los documentos escaneados omitidos
        for doc_info in documentos_escaneados:
            error_obj = AnalisisTPV.ErrorRespuesta(error=error_msg)
            resultados_finales[doc_info["index"]] = AnalisisTPV.ResultadoExtraccion(
                AnalisisIA=doc_info["ia_data"],
                DetalleTransacciones=error_obj
            )

    # --- 5. ENSAMBLE DE LA RESPUESTA FINAL ---
    resultados_limpios = [res for res in resultados_finales if res is not None]

    # Generamos la lista de resultados generales A PARTIR de la lista de resultados individuales con una simple y elegante comprensión de lista.
    resultados_generales = [
        res.AnalisisIA for res in resultados_limpios if res.AnalisisIA is not None
    ]

    return AnalisisTPV.ResultadoTotal(
        total_depositos = total_depositos_calculado,
        es_mayor_a_250 = es_mayor,
        resultados_generales = resultados_generales,
        resultados_individuales = resultados_limpios
    )