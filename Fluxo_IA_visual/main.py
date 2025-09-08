from .procesamiento.regex_engine import procesar_regex_generico, obtener_y_procesar_portada
from .procesamiento.auxiliares import prompt_base, total_depositos_verificacion, crear_objeto_resultado
from fastapi import FastAPI, File, UploadFile, HTTPException
from .procesamiento.extractor import extraer_texto_pdf_con_fitz, PDFCifradoError
from .procesamiento_ocr.extractor_ocr import extraer_texto_con_ocr
from concurrent.futures import ProcessPoolExecutor
from .models import ResultadoTotal, ErrorRespuesta, ResultadoExtraccion
from .NomiFlash import router_nomi
from dotenv import load_dotenv
from typing import List, Union
import zipfile
import asyncio
import io

load_dotenv()

app = FastAPI(
    title="Procesamiento de entradas (TPV o Nómina)",
    version="1.1.4"
) 
prompt = prompt_base

app.include_router(router_nomi.router)

@app.get("/")
async def home():
    return "Hola, te equivocaste al momento de consumir la API, pero no te preocupes, para consumirla ve a con '/procesar_pdf/' o ve a '/docs/'"

# Endpoint principal 
@app.post(
        "/fluxo/procesar_pdf/", 
        response_model = ResultadoTotal,
        summary="(API principal) Extrae datos estructurados de trasacciones TPV en PDF's individuales o de un archivo ZIP."
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

        # --- Lógica para manejar archivos PDF individuales ---
        elif archivo.content_type == "application/pdf":
            # usamos await para leer el archivo en paralelo
            contenido_pdf = await archivo.read()
            archivos_en_memoria.append({"filename": archivo.filename, "content": contenido_pdf})
        
        else:
            # Si el archivo no es ni PDF ni ZIP, lo ignoramos (o podríamos devolver un error)
            print(f"Archivo '{archivo.filename}' ignorado. No es un PDF o ZIP válido.")
            # Para devolver un error, tendrías que manejarlo de forma más compleja. Por ahora, simplemente lo saltamos.

    # Si después de extraer los ZIPs no queda ningún PDF, devolvemos un error.
    if not archivos_en_memoria:
        raise HTTPException(
            status_code=400,
            detail="No subiste ningun archivo PDF válido."
        )
    
    # ------- 1. ANÁLISIS DE LA PORTADA CON IA PARA DETERMINAR ENTRADAS Y SI ES DOCUMENTO ESCANEADO -------
    for doc in archivos_en_memoria:
        tarea = obtener_y_procesar_portada(prompt, doc["content"])
        tareas_analisis.append(tarea)    
    try:
        # Ejecutamos todas las llamadas a la IA al mismo tiempo
        resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
    except Exception as e:
        # En caso de que la llamada de la IA falle de forma masiva, detenemos todo.
        raise HTTPException(status_code=500, detail=f"Error crítico durante el análisis con IA: {str(e)}")

    # Suma de depósitos y decisión
    print("--- RESULTADOS PORTADA ----")
    print(resultados_portada)
    total_depositos_calculado, es_mayor = total_depositos_verificacion(resultados_portada)

    # --- 2. SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS ---
    # Preparamos las listas para el siguiente paso.
    documentos_digitales = []
    documentos_escaneados = []

    # Creamos una lista final de resultados, pre-llenada para mantener el orden.
    resultados_finales: List[Union[ResultadoExtraccion, None]] = [None] * len(archivos_en_memoria)

    for i, resultado_bruto in enumerate(resultados_portada):
        filename = archivos_en_memoria[i]["filename"]
        # VERIFICACIÓN 1: ¿La tarea falló por completo?
        if isinstance(resultado_bruto, Exception):
            # Verificamos si es nuestro error de contraseña
            if isinstance(resultado_bruto, PDFCifradoError):
                error_msg = "Documento con contraseña, imposible trabajar con este documento."
                resultados_finales[i] = ResultadoExtraccion(
                    AnalisisIA=None,
                    DetalleTransacciones=ErrorRespuesta(error=error_msg))
            else:
                # Para cualquier otro error inesperado en la etapa inicial
                error_msg = f"Fallo el procesamiento inicial de '{filename}': {str(resultado_bruto)}"
                resultados_finales[i] = ResultadoExtraccion(
                    AnalisisIA=None,
                    DetalleTransacciones=ErrorRespuesta(error=error_msg)
                )
            continue # Pasamos al siguiente archivo
        
        print(resultado_bruto)
        # Si no hubo error, desempacamos los resultados
        datos_ia, es_digital = resultado_bruto
        # Intenta procesar este archivo, preparado para cualquier error
        try:
            # Sea digital o escaneado se prepara para extracción
            if es_digital:
                documentos_digitales.append({"index": i, "content": archivos_en_memoria[i]["content"], "ia_data": datos_ia})
            else:
                documentos_escaneados.append({"index": i, "content": archivos_en_memoria[i]["content"], "ia_data": datos_ia})

        # Red de validación
        except Exception as e:
            # Si algo falla en el 'try' (como una ValidationError de Pydantic), se capturamos.
            resultados_finales[i] = ErrorRespuesta(
                error=f"Error al procesar los datos de la extracción inicial en: '{filename}'. Vuelve a mandar este archivo."
            )

    # --- 3. PROCESAMIENTO OBLIGATORIO DE DOCUMENTOS DIGITALES ---
    loop = asyncio.get_running_loop()
    tareas_extraccion = []
    documentos_a_procesar_regex = []
    procesar_ocr = es_mayor and len(documentos_escaneados) <= 15

    # Añadir tareas de extracción digital
    with ProcessPoolExecutor() as executor:
        for doc in documentos_digitales:
            tareas_extraccion.append(loop.run_in_executor(executor, extraer_texto_pdf_con_fitz, doc["content"]))
            documentos_a_procesar_regex.append(doc) # Mantenemos el orden

    # Añadir tareas de OCR condicionalmente
        if procesar_ocr:
            for doc in documentos_escaneados:
                tareas_extraccion.append(loop.run_in_executor(executor, extraer_texto_con_ocr, doc["content"]))
                documentos_a_procesar_regex.append(doc) # Mantenemos el orden

    # --- 4. EJECUCIÓN CONCURRENTE Y PROCESAMIENTO DE RESULTADOS ---
    textos_extraidos_brutos = [] 
    if tareas_extraccion:
        # Ejecutamos todas las tareas pesadas en un solo lote
        textos_extraidos_brutos = await asyncio.gather(*tareas_extraccion, return_exceptions=True)

        # *** El bucle de procesamiento ahora está DENTRO del 'if' ***
        # Esto garantiza que solo se ejecute si 'textos_extraidos_brutos' tiene contenido.
        for i, texto_o_error in enumerate(textos_extraidos_brutos):
            doc_info = documentos_a_procesar_regex[i]
            filename = archivos_en_memoria[doc_info['index']]['filename']

            if isinstance(texto_o_error, Exception):
                resultados_finales[doc_info["index"]] = crear_objeto_resultado({
                    **doc_info["ia_data"],
                    "error_transacciones": f"Fallo la extracción de texto en '{filename}': {texto_o_error}"
                })
                continue

            try:
                resultado_dict = procesar_regex_generico(doc_info["ia_data"], texto_o_error, "digital" if doc_info in documentos_digitales else "ocr")
                resultados_finales[doc_info["index"]] = crear_objeto_resultado(resultado_dict)
            
            except Exception as e:
                resultados_finales[doc_info["index"]] = crear_objeto_resultado({
                    **doc_info["ia_data"],
                    "error_transacciones": f"Fallo Regex en '{filename}': {e}"
                })

    # --- 5. MANEJO DE ESCANEADOS OMITIDOS ---
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
            error_obj = ErrorRespuesta(error=error_msg)
            resultados_finales[doc_info["index"]] = ResultadoExtraccion(
                AnalisisIA=doc_info["ia_data"],
                DetalleTransacciones=error_obj
            )

    # --- 6. ENSAMBLE DE LA RESPUESTA FINAL ---
    resultados_limpios = [res for res in resultados_finales if res is not None]

    # Generamos la lista de resultados generales A PARTIR de la lista de resultados individuales con una simple y elegante comprensión de lista.
    resultados_generales = [
        res.AnalisisIA for res in resultados_limpios if res.AnalisisIA is not None
    ]

    return ResultadoTotal(
        total_depositos = total_depositos_calculado,
        es_mayor_a_250 = es_mayor,
        resultados_generales = resultados_generales,
        resultados_individuales = resultados_limpios
    )