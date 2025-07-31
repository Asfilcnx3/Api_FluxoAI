from .extractor import convertir_portada_a_imagen_bytes, extraer_json_del_markdown, extraer_texto_limitado
from .auxiliares import construir_descripcion_optimizado, limpiar_monto, reconocer_banco_por_texto, reconciliar_resultados_ia, sanitizar_datos_ia, extraer_rfc_por_texto, limpiar_y_normalizar_texto
from .auxiliares import REGEX_COMPILADAS, PALABRAS_CLAVE_VERIFICACION
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI
import asyncio
import base64
import fitz
import os

load_dotenv()

client_gpt = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY")
)

client_openrouter = AsyncOpenAI(
    api_key=os.getenv("OPENROUTER_API_KEY"),
    base_url=os.getenv("OPENROUTER_BASE_URL"),
    default_headers={
        "HTTP-Referer": "https://github.com/Asfilcnx3", 
        "X-Title": "Fluxo IA Test", 
    },
)

def sumar_lista_montos(montos: List[str]) -> float:
    """
    Convierte una lista de montos en formato de cadena a float y los suma.

    Args:
        montos (List[str]): Lista de montos a sumar.

    Returns:
        float: La suma de los montos.
    """
    total = 0.0
    for monto in montos:
        monto_limpio = monto.replace(',', '').strip()
        try:
            total += float(monto_limpio)
        except ValueError:
            continue
    return total

def es_escaneado_o_no(texto_extraido: str, umbral: int = 50) -> bool:
    """
    Extrae el texto dado en Bytes y verifica si el texto extraído es válido usando una prueba de dos factores:
    1. Debe tener una longitud mínima.
    2. Debe contener palabras clave relevantes de un estado de cuenta.
    
    Esto previene falsos positivos con PDFs escaneados que generan texto basura.
    """
    if not texto_extraido:
        return False
    print(len(texto_extraido.strip()))

    texto_limpio = texto_extraido.strip()
    
    # Prueba 1: ¿Supera la longitud mínima?
    pasa_longitud = len(texto_limpio) > umbral
    
    # Prueba 2: ¿Contiene palabras clave con sentido?
    pasa_contenido = bool(PALABRAS_CLAVE_VERIFICACION.search(texto_limpio))

    return pasa_longitud and pasa_contenido

# Función para enviar el prompt + imagen a GPT-4o
async def analizar_portada_gpt(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int]) -> str:
    """
    Se hace la llamada al modelo GPT-4o
    """
    imagen_buffers = convertir_portada_a_imagen_bytes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": "auto"
                },
            })
    response = await client_gpt.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user","content": content}],
    )

    return response.choices[0].message.content

# Función para enviar el prompt + imagen a GPT-4o
async def analizar_portada_gemini(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int]) -> str:
    """
    Se hace la llamada al modelo GEMINI 1.5 flash
    """
    imagen_buffers = convertir_portada_a_imagen_bytes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": "auto"
                },
            })
    response = await client_openrouter.chat.completions.create(
        model="google/gemini-flash-1.5",
        messages=[{"role": "user","content": content}],
    )

    return response.choices[0].message.content

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
        extraer_texto_limitado, 
        pdf_bytes
    )
    es_documento_digital = es_escaneado_o_no(texto_verificacion)

    # --- 2. SEGUNDO: Reconocer el banco y el RFC a partir del texto (con regex) ---
    banco_por_texto = reconocer_banco_por_texto(texto_verificacion)
    banco_estandarizado = banco_por_texto.upper() if banco_por_texto else ""

    rfc_por_texto = extraer_rfc_por_texto(texto_verificacion, banco_estandarizado)
    rfc_estandarizado = rfc_por_texto.upper() if rfc_por_texto else ""
    print(rfc_estandarizado)

    # --- 3. TERCERO: Decidir qué páginas procesar ---
    paginas_para_ia = [1, 2] # Por defecto, las primeras dos
    
    if banco_estandarizado == "BANREGIO":
        print("Banco BANREGIO detectado. Ajustando páginas para el análisis de IA.")
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
            print(f"No se pudo determinar el total de páginas para Banregio: {e}. Usando páginas por defecto.")
            paginas_para_ia = [1, 2]
    
    # --- 4. CUARTO: Llamar a las IA de forma PARALELA con las páginas correctas ---
    tarea_gpt = analizar_portada_gpt(prompt, pdf_bytes, paginas_a_procesar = paginas_para_ia)
    tarea_gemini = analizar_portada_gemini(prompt, pdf_bytes, paginas_a_procesar = paginas_para_ia)
    
    resultados_ia_brutos = await asyncio.gather(tarea_gpt, tarea_gemini, return_exceptions=True)

    res_gpt_str, res_gemini_str = resultados_ia_brutos

    datos_gpt = extraer_json_del_markdown(res_gpt_str) if not isinstance(res_gpt_str, Exception) else {}
    datos_gemini = extraer_json_del_markdown(res_gemini_str) if not isinstance(res_gemini_str, Exception) else {}

    # --- SANITIZACION ---
    datos_gpt_sanitizados = sanitizar_datos_ia(datos_gpt)
    datos_gemini_sanitizados = sanitizar_datos_ia(datos_gemini)

    # --- RECONCILIACIÓN ---
    datos_ia_reconciliados = reconciliar_resultados_ia(datos_gpt_sanitizados, datos_gemini_sanitizados)

    # --- 5. QUINTO: Corregir el resultado de la IA y devolver ---
    # Usamos el banco que reconocimos por texto, que es más fiable.
    if banco_estandarizado:
        datos_ia_reconciliados["banco"] = banco_estandarizado
    if rfc_estandarizado:
        datos_ia_reconciliados["rfc"] = rfc_estandarizado
    
    return datos_ia_reconciliados, es_documento_digital


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
    print("banco encontrado")

    config_compilada = REGEX_COMPILADAS.get(banco.lower())
    if not config_compilada:
        resultados["error_transacciones"] = f"Estamos trabajando para dar soporte al banco: '{banco}'."
        return resultados
    print("config encontrada")

    datos_crudos = {}
    for clave, patron_compilado in config_compilada.items():
        datos_crudos[clave] = patron_compilado.findall(texto)

    # Creamos un for para encontrar todas las coincidencias en la lista de posibles descripciones
    regex_claves = [
        "descripcion",
        "descripcion_clip_multilinea",
        "descripcion_traspaso_multilinea",
        "descripcion_amex_multilinea"
    ]

    transacciones_matches = []
    for clave in regex_claves:
        if clave in datos_crudos:
            transacciones_matches += datos_crudos[clave]


    if not transacciones_matches:
        resultados["transacciones"] = []
        resultados["entradas_TPV_bruto"] = 0.0
        resultados["entradas_TPV_neto"] = 0.0
        # Probamos el nuevo campo de error
        resultados["error_transacciones"] = "Sin coincidencias, el documento no contiene transacciones TPV."

    else:
        # CASO B: Sí se encontraron transacciones, procesamos normalmente
        transacciones_filtradas = []
        total_entradas = 0
        for transaccion in transacciones_matches:
            descripcion, monto_str = construir_descripcion_optimizado(transaccion, banco)
            if "comision" not in descripcion and "iva" not in descripcion and "com." not in descripcion:
                total_entradas += sumar_lista_montos([monto_str])
                transacciones_filtradas.append({
                    "fecha": transaccion[0],
                    "descripcion": limpiar_y_normalizar_texto(descripcion.strip()),
                    "monto": monto_str
                })
        
        resultados["transacciones"] = transacciones_filtradas
        resultados["entradas_TPV_bruto"] = total_entradas
        comisiones = resultados.get("comisiones") or 0.0
        resultados["entradas_TPV_neto"] = total_entradas - comisiones
        resultados["error_transacciones"] = None # Nos aseguramos de que no haya mensaje de error

    # El resto de los datos de la IA ya están en 'resultados', por lo que se conservan.
    return resultados