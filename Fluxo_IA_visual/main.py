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
import asyncio

load_dotenv()

app = FastAPI(
    title="Procesamiento de entradas (TPV o Nómina)",
    version="1.1.3"
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
        summary="(API principal) Extrae estructurados de trasacciones TPV en PDF."
    )
async def procesar_pdf_api(
    archivos: List[UploadFile] = File(..., description="Uno o más archivos PDF a extraer transacciones TPV")
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

    # ------- 1. ANÁLISIS DE LA PORTADA CON IA PARA DETERMINAR ENTRADAS Y SI ES DOCUMENTO ESCANEADO -------
    for archivo in archivos:
        # usamos await para leer el archivo en paralelo
        contenido_pdf = await archivo.read()
        archivos_en_memoria.append({"filename": archivo.filename, "content": contenido_pdf})
        # ejecutamos en diferentes nucleos del procesador
        tarea = obtener_y_procesar_portada(prompt, contenido_pdf) # esta función es wrapper
        tareas_analisis.append(tarea)

    try:
        # Ejecutamos todas las llamadas a la IA al mismo tiempo
        resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
    except Exception as e:
        # En caso de que la llamada de la IA falle de forma masiva, detenemos todo.
        raise HTTPException(status_code=500, detail=f"Error crítico durante el análisis con IA: {str(e)}")
    
    # --- 2. SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS ---
    # Preparamos las listas para el siguiente paso.
    documentos_digitales = []
    documentos_escaneados = []
    # Creamos una lista final de resultados, pre-llenada para mantener el orden.
    resultados_finales: List[Union[ResultadoExtraccion, None]] = [None] * len(archivos)

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
    if documentos_digitales:
        # Extracción de texto en paralelo ()
        loop = asyncio.get_running_loop()

        # Usamos ProcessPoolExecutor para paralelismo en la CPU
        with ProcessPoolExecutor() as executor:
            # Añadimos las tareas de extracción digital
            tareas_extraccion_digital = [
                loop.run_in_executor(executor, extraer_texto_pdf_con_fitz, doc["content"])
                for doc in documentos_digitales
            ]
            textos_digitales_extraidos = await asyncio.gather(*tareas_extraccion_digital, return_exceptions=True)
        
        for i, texto in enumerate(textos_digitales_extraidos):
            doc_info = documentos_digitales[i]
            try:
                # Obtenemos el diccionario plano de la regex
                resultado_dict = procesar_regex_generico(doc_info["ia_data"], texto, "digital")

                # *** CAMBIO CLAVE: Convertimos el dict a un objeto Pydantic estructurado ***
                resultado_estructurado = crear_objeto_resultado(resultado_dict)
                
                # Guardamos el objeto correcto en nuestra lista de resultados
                resultados_finales[doc_info["index"]] = resultado_estructurado
            
            except Exception as e:
                # Manejo de error si la regex falla para un archivo digital
                resultados_finales[doc_info["index"]] = ResultadoExtraccion(
                    AnalisisIA=doc_info["ia_data"],
                    DetalleTransacciones=ErrorRespuesta(error=f"Fallo Regex en '{filename}': {e}")
                )

    # --- 4. CÁLCULO DE DEPÓSITOS Y DECISIÓN ---
    total_depositos_calculado, es_mayor = total_depositos_verificacion(resultados_finales)

    print(total_depositos_calculado)
    print(es_mayor)

    # --- 5. PROCESAMIENTO CONDICIONAL DE DOCUMENTOS ESCANEADOS ---
    if documentos_escaneados:
        if es_mayor:
            loop = asyncio.get_running_loop()
            with ProcessPoolExecutor() as executor:
                tareas_ocr = [
                    loop.run_in_executor(executor, extraer_texto_con_ocr, doc["content"])
                    for doc in documentos_escaneados
                ]
                textos_ocr_brutos = await asyncio.gather(*tareas_ocr, return_exceptions=True)

            for i, texto in enumerate(textos_ocr_brutos):
                doc_info = documentos_escaneados[i]
                try:
                    resultado_dict_ocr = procesar_regex_generico(doc_info["ia_data"], texto, "ocr")

                    # *** (también para el flujo de OCR) ***
                    resultado_estructurado_ocr = crear_objeto_resultado(resultado_dict_ocr)
                    
                    resultados_finales[doc_info["index"]] = resultado_estructurado_ocr
                except Exception as e:
                    resultados_finales[doc_info["index"]] = ResultadoExtraccion(
                        AnalisisIA=doc_info["ia_data"],
                        DetalleTransacciones=ErrorRespuesta(error=f"Fallo Regex en OCR para '{filename}': {e}")
                    )
        else:
            for doc_info in documentos_escaneados:
                error_ocr = ErrorRespuesta(
                    error="Este documento es escaneado y el total de depósitos no supera los $250,000."
                )
                resultados_finales[doc_info["index"]] = ResultadoExtraccion(
                    AnalisisIA=doc_info["ia_data"],
                    DetalleTransacciones=error_ocr
                )

    # --- 6. ENSAMBLE DE LA RESPUESTA FINAL ---
    resultados_limpios = [res for res in resultados_finales if res is not None]

    return ResultadoTotal(
        total_depositos = total_depositos_calculado,
        es_mayor_a_250 = es_mayor,
        resultados_individuales = resultados_limpios
    )