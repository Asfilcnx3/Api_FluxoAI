from .procesamiento.regex_engine import procesar_regex_generico, obtener_y_procesar_portada
from .procesamiento.auxiliares import prompt_base, verificar_total_depositos
from fastapi import FastAPI, File, UploadFile, HTTPException
from .procesamiento.extractor import extraer_texto_pdf_con_fitz, PDFCifradoError
from .procesamiento_ocr.extractor_ocr import extraer_texto_con_ocr
from concurrent.futures import ProcessPoolExecutor
from .models import Resultado, ErrorRespuesta
from dotenv import load_dotenv
from typing import List, Union
import asyncio

load_dotenv()

app = FastAPI() 
prompt = prompt_base

@app.get("/")
async def home():
    return "Hola, te equivocaste al momento de consumir la API, pero no te preocupes, para consumirla ve a con '/procesar_pdf/' o ve a '/docs/'"

# Endpoint principal 
@app.post("/procesar_pdf/", response_model=List[Union[Resultado, ErrorRespuesta]])
async def procesar_pdf_api(
    archivos: List[UploadFile] = File(...)
):
    # ------- listas a usar más adelante -------
    tareas_analisis = []
    archivos_en_memoria = []

    # ------- 1. ANÁLISIS DE LA PORTADA CON IA PARA DETERMINAR ENTRADAS Y SI ES DOCUMENTO ESCANEADO -------
    for archivo in archivos:
        contenido_pdf = await archivo.read()
        archivos_en_memoria.append({"filename": archivo.filename, "content": contenido_pdf})
        tarea = obtener_y_procesar_portada(prompt, contenido_pdf) # esta función es wrapper
        tareas_analisis.append(tarea)

    try:
        # Ejecutamos todas las llamadas a la IA al mismo tiempo
        resultados_portada = await asyncio.gather(*tareas_analisis, return_exceptions=True)
    except Exception as e:
        # En caso de que la llamada de la IA falle de forma masiva, detenemos todo.
        raise HTTPException(status_code=500, detail=f"Error crítico durante el análisis con IA: {str(e)}")
    
    # ------- Verificamos de forma general los depósitos -------
    # Extraemos solo los datos de la IA para la verificación
    lista_datos_ia = [res[0] for res in resultados_portada if not isinstance(res, Exception)]

    # Verificación si es mayor a 250_000
    if not verificar_total_depositos(lista_datos_ia):
        raise HTTPException(
            status_code=400,
            detail= "El total de los depositos no supera los 250,000. No podemos continuar con el análisis."
        )
    
    # --- 2. SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS ---
    # Preparamos las listas para el siguiente paso.
    documentos_digitales = []
    documentos_escaneados = []
    # Creamos una lista final de resultados, pre-llenada para mantener el orden.
    resultados_finales = [None] * len(archivos)

    for i, resultado_bruto in enumerate(resultados_portada):
        filename = archivos_en_memoria[i]["filename"]
        # VERIFICACIÓN 1: ¿La tarea falló por completo?
        if isinstance(resultado_bruto, Exception):
            # Verificamos si es nuestro error de contraseña
            if isinstance(resultado_bruto, PDFCifradoError):
                resultados_finales[i] = ErrorRespuesta(error="Documento con contraseña, imposible trabajar con este documento.")
            else:
                # Para cualquier otro error inesperado en la etapa inicial
                resultados_finales[i] = ErrorRespuesta(error=f"Fallo el procesamiento inicial de '{filename}': {str(resultado_bruto)}")
            continue # Pasamos al siguiente archivo

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

    # --- 3. EXTRACCIÓN PARA DOCUMENTO DIGITALES Y ESCANEADOS CON OCR ---
    textos_extraidos = []
    if documentos_digitales or documentos_escaneados:
        # Extracción de texto en paralelo ()
        loop = asyncio.get_running_loop()
        tareas_extraccion = []
        # Usamos ProcessPoolExecutor para paralelismo en la CPU
        with ProcessPoolExecutor() as executor:
            # Añadimos las tareas de extracción digital
            for doc in documentos_digitales:
                tareas_extraccion.append(loop.run_in_executor(executor, extraer_texto_pdf_con_fitz, doc["content"]))

            # Añadimos las tareas de extracción con OCR
            for doc in documentos_escaneados:
                tareas_extraccion.append(loop.run_in_executor(executor, extraer_texto_con_ocr, doc["content"]))
        
        # Esperamos a que todas las tareas de extracción terminen
        textos_extraidos = await asyncio.gather(*tareas_extraccion)

    # --- 4. PROCESAMIENTO FINAL CON REGEX (con manejo de errores individual) ---
    # Separamos los textos extraidos para cada flujo
    textos_digitales_extraidos = textos_extraidos[:len(documentos_digitales)]
    textos_ocr_extraidos = textos_extraidos[len(documentos_digitales):]

    # PROCESAMOS LOS RESULTADOS DE LOS DOCUMENTOS DIGITALES
    for i, texto in enumerate(textos_digitales_extraidos):
        doc_info = documentos_digitales[i]
        try:
            # Colocamos tipo digital por si necesitamos modificar en el futuro las regex
            resultado_procesado = procesar_regex_generico(doc_info["ia_data"], texto, "digital")
            resultados_finales[doc_info["index"]] = resultado_procesado
        except Exception as e:
            resultados_finales[doc_info["index"]] = ErrorRespuesta(error=f"Fallo el procesamiento de Regex en el archivo digital '{archivos_en_memoria[doc_info['index']]['filename']}'. Causa: {e}")

    # PROCESAMOS LOS RESULTADOS DE LOS DOCUMENTOS ESCANEADOS CON OCR
    for i, texto in enumerate(textos_ocr_extraidos):
        doc_info = documentos_escaneados[i]
        try:
            # Colocamos tipo OCR por si necesitamos modificar en el futuro las regex
            resultado_procesado = procesar_regex_generico(doc_info["ia_data"], texto, "ocr")
            if isinstance(resultado_procesado, dict):
                resultado_procesado["origen_extraccion"] = "OCR"
            resultados_finales[doc_info["index"]] = resultado_procesado

        except Exception as e:
            resultados_finales[doc_info["index"]] = ErrorRespuesta(error=f"Fallo el procesamiento de Regex en el archivo escaneado '{archivos_en_memoria[doc_info['index']]['filename']}'. Causa: {e}")

    return resultados_finales