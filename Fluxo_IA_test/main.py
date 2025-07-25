from .procesamiento.regex_engine import procesar_regex_generico, obtener_y_procesar_portada
from .procesamiento.auxiliares import prompt_base, verificar_total_depositos
from fastapi import FastAPI, File, UploadFile, HTTPException
from .procesamiento.extractor import extraer_texto_pdf
from concurrent.futures import ThreadPoolExecutor
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

    # ------- Analisis de la portada con IA para determinar las entradas y si el documento es digital o no -------
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
    lista_datos_ia = [resultado[0] for resultado in resultados_portada]

    # Verificación si es mayor a 250_000
    if not verificar_total_depositos(lista_datos_ia):
        raise HTTPException(
            status_code=400,
            detail= "El total de los depositos no supera los 250,000. No podemos continuar con el análisis."
        )
    
    # --- SEPARACIÓN DE DOCUMENTOS DIGITALES Y ESCANEADOS ---
    # Preparamos las listas para el siguiente paso.
    documentos_para_extraccion = []
    indices_digitales = []
    # Creamos una lista final de resultados, pre-llenada para mantener el orden.
    resultados_finales = [None] * len(archivos)

    for i, (datos_ia, es_digital) in enumerate(resultados_portada):
        filename = archivos_en_memoria[i]["filename"]

        # Verificación - La tarea falló?
        # Intenta procesar este archivo, preparado para cualquier error
        try:
            if es_digital:
                # Si es digital, lo preparamos para el siguiente paso
                documentos_para_extraccion.append(archivos_en_memoria[i]["content"])
                indices_digitales.append(i)
            else:
                # Si es escaneado...
                if datos_ia and datos_ia.get("banco"):
                    # Intentamos crear el objeto Resultado. Aquí podría ocurrir la ValidationError.
                    resultado_parcial = Resultado(**datos_ia)
                    resultado_parcial.error_transacciones = "El documento es escaneado, se mandará a OCR."
                    resultados_finales[i] = resultado_parcial
                else:
                    resultados_finales[i] = ErrorRespuesta(error=f"El documento '{filename}' es escaneado y no se pudo leer la portada, verifica que sea un estado de cuentas válido.")

        except Exception as e:
            # ¡LA RED DE SEGURIDAD!
            # Si algo falla en el 'try' (como una ValidationError de Pydantic), lo capturamos.
            print(f"ERROR de validación o procesamiento para '{filename}': {str(e)}")
            resultados_finales[i] = ErrorRespuesta(
                error=f"Error al procesar los datos de la extracción inicial en: '{filename}'. Vuelve a mandar este archivo."
            )

    
    textos_completos = []
    if documentos_para_extraccion:
        # Extracción de texto en paralelo
        loop = asyncio.get_running_loop()
        tareas_extraccion = []

        # Creamos un pool de hilos para ejecutar las tareas del CPU
        with ThreadPoolExecutor() as executor:
            for contenido_pdf in documentos_para_extraccion:
                tarea = loop.run_in_executor(
                    executor, # Pool de hilos a usar
                    extraer_texto_pdf, # La función síncrona y pesada
                    contenido_pdf # El argumento para la función
                )
                tareas_extraccion.append(tarea)
            
            textos_completos = await asyncio.gather(*tareas_extraccion)


    # --- EXTRACCIÓN Y PROCESAMIENTO FINAL (SOLO PARA DIGITALES) ---
    # Esta parte solo se ejecuta si encontramos al menos un documento digital.
    if documentos_para_extraccion:
        # Extracción de texto en paralelo (sin cambios)
        loop = asyncio.get_running_loop()
        tareas_extraccion = []
        with ThreadPoolExecutor() as executor:
            for contenido_pdf in documentos_para_extraccion:
                tareas_extraccion.append(loop.run_in_executor(executor, extraer_texto_pdf, contenido_pdf))
        textos_completos = await asyncio.gather(*tareas_extraccion)

        # Procesamiento final con regex (con manejo de errores individual, como lo tenías)
        for i, texto_extraido in enumerate(textos_completos):
            indice_original = indices_digitales[i]
            
            try:
                datos_ia_original = resultados_portada[indice_original][0]
                if not texto_extraido:
                    raise ValueError("La extracción de texto devolvió un resultado vacío.")
                
                resultado_procesado = procesar_regex_generico(datos_ia_original, texto_extraido)
                resultados_finales[indice_original] = resultado_procesado
            except Exception as e:
                filename = archivos_en_memoria[indice_original]["filename"]
                print(f"ERROR CRÍTICO procesando el archivo '{filename}': {str(e)}")
                resultados_finales[indice_original] = ErrorRespuesta(error=f"Fallo el procesamiento del archivo '{filename}'.")

    return resultados_finales