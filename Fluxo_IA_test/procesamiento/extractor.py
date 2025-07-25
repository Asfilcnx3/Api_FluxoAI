from pdf2image import convert_from_bytes
from typing import Dict, Any
from io import BytesIO
import pdfplumber
import warnings
import json
import re


def extraer_texto_pdf(pdf_bytes: bytes) -> str:
    """
    Extrae todo el texto de uno o varios archivos PDF y los convierte a minúsculas, usamos with para no cargar el documento en memoria RAM y que se cierre cuando termine de ejecutarse.

    Args:
        ruta_pdf (str): La ruta o lista de rutas a los archivos PDF.

    Returns:
        str: El texto extraído en minúsculas (normalizado).
    """
    texto_total = ''

    # Creamos un contexto para atrapar un posible warning
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=r"Could get FontBBox from font descriptor"
        )
        try:
            # Abre el PDF desde los bytes en memoria
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                for pagina in pdf.pages:
                    texto_pagina = pagina.extract_text()
                    if texto_pagina:
                        texto_total += texto_pagina.lower() + '\n'
        except Warning as e:
            print(f"Error al extraer texto del PDF, fuente mal formada: {e}")
            return ""
    
    return texto_total

# Convierte la primera página del PDF a imagen (portada)
def convertir_portada_a_imagen_bytes(pdf_bytes: bytes) -> BytesIO:
    imagenes = convert_from_bytes(pdf_bytes, first_page=1, last_page=2)
    buffers = []
    for img in imagenes:
        buffer = BytesIO()
        img.save(buffer, format="PNG")
        buffer.seek(0)
        buffers.append(buffer)
    return buffers

# Extraer el JSON del markdown que nos da el modelo
def extraer_json_del_markdown(respuesta: str) -> Dict[str, Any]:
    json_string_match = re.search(r'```json\s*(.*?)\s*```', respuesta, re.DOTALL)
    if json_string_match:
        json_string = json_string_match.group(1)
        datos_crudos = json.loads(json_string)
    else:
        # Esto es para cuando el output no tiene el formato markdown esperado
        print("No pude encontrar un JSON debajo del markdown.")
        try:
            datos_crudos = json.loads(respuesta)
        except json.JSONDecodeError as e:
            print(f"Fallo en crear los datos crudos del json: {e}")
            datos_crudos = {} # Assign an empty dict or handle as appropriate
    return datos_crudos

def extraer_texto_limitado(pdf_bytes: bytes, num_paginas: int = 2) -> str:
    """
    Extrae texto de las primeras 'num_paginas' de un PDF para una verificación rápida.
    """
    texto_parcial = ''
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "error",
            message=r"Could get FontBBox from font descriptor"
        )
        try:
            with pdfplumber.open(BytesIO(pdf_bytes)) as pdf:
                # Itera solo sobre el número de páginas que necesitamos
                for i, pagina in enumerate(pdf.pages):
                    if i >= num_paginas:
                        break
                    texto_pagina = pagina.extract_text()
                    if texto_pagina:
                        texto_parcial += texto_pagina.lower() + '\n'
        except Warning as e:
            print(f"Error al extraer texto del PDF, fuente mal formada: {e}")
            return ""    
    return texto_parcial