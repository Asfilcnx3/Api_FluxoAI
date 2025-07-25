from .extractor import convertir_portada_a_imagen_bytes, extraer_json_del_markdown, extraer_texto_limitado
from .auxiliares import construir_descripcion_optimizado, limpiar_monto
from .auxiliares import REGEX_COMPILADAS, PALABRAS_CLAVE_VERIFICACION
from typing import List, Dict, Any, Tuple
from dotenv import load_dotenv
from openai import AsyncOpenAI
import asyncio
import base64
import os

load_dotenv()

openai_api_key = os.getenv("OPENAI_API_KEY")
client = AsyncOpenAI(api_key=openai_api_key)

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
    print(texto_extraido)
    print(len(texto_extraido.strip()))

    texto_limpio = texto_extraido.strip()
    
    # Prueba 1: ¿Supera la longitud mínima?
    pasa_longitud = len(texto_limpio) > umbral
    
    # Prueba 2: ¿Contiene palabras clave con sentido?
    pasa_contenido = bool(PALABRAS_CLAVE_VERIFICACION.search(texto_limpio))

    return pasa_longitud and pasa_contenido

# Función para enviar el prompt + imagen a GPT-4o
async def analizar_portada_estado(prompt: str, pdf_bytes: bytes) -> str:
    imagen_buffers = convertir_portada_a_imagen_bytes(pdf_bytes)
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
    response = await client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user","content": content}],
    )

    return response.choices[0].message.content

async def obtener_y_procesar_portada(prompt:str, pdf_bytes: bytes) -> Tuple[Dict[str, Any], bool]:
    """
    Orquesta de forma concurrente la extracción de texto y el análisis con IA para un solo PDF.
    """
    loop = asyncio.get_running_loop()
    # Tarea 1: Extraer el texto de las primeras páginas (operación de CPU).
    # La ejecutamos en un hilo separado para no bloquear el programa.
    tarea_extraccion_texto = loop.run_in_executor(
        None,  # Usa el executor de hilos por defecto
        extraer_texto_limitado, 
        pdf_bytes
    )

    # Tarea 2: Analizar la portada con OpenAI (operación de I/O).
    tarea_analisis_ia = analizar_portada_estado(prompt, pdf_bytes)

    # Ejecutamos ambas tareas al mismo tiempo y esperamos sus resultados.
    # return_exceptions=True evita que una falle y cancele la otra.
    resultados_tareas = await asyncio.gather(
        tarea_extraccion_texto, 
        tarea_analisis_ia, 
        return_exceptions=True
    )
    
    texto_verificacion, respuesta_str_ia = resultados_tareas

    # Verificamos si alguna de las tareas falló
    if isinstance(texto_verificacion, Exception):
        print(f"Error en extracción de texto inicial: {texto_verificacion}")
        # Si la extracción de texto falla, asumimos que no es digital y la IA podría ser la única fuente.
        es_documento_digital = False
    else:
        es_documento_digital = es_escaneado_o_no(texto_verificacion)

    if isinstance(respuesta_str_ia, Exception):
        print(f"Error en la llamada a OpenAI: {respuesta_str_ia}")
        # Si la IA falla, devolvemos un diccionario de error y el estado del documento.
        return {"error": "Fallo en la comunicación con el servicio de IA."}, es_documento_digital

    # Si ambas tareas fueron exitosas, procesamos el JSON.
    datos_ia = extraer_json_del_markdown(respuesta_str_ia)
    
    return datos_ia, es_documento_digital


def procesar_regex_generico(resultados: dict, texto:str) -> Dict[str, Any]:
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
                    "descripcion": descripcion.strip(),
                    "monto": monto_str
                })
        
        resultados["transacciones"] = transacciones_filtradas
        resultados["entradas_TPV_bruto"] = total_entradas
        comisiones = resultados.get("comisiones") or 0.0
        resultados["entradas_TPV_neto"] = total_entradas - comisiones
        resultados["error_transacciones"] = None # Nos aseguramos de que no haya mensaje de error

    # El resto de los datos de la IA ya están en 'resultados', por lo que se conservan.
    return resultados