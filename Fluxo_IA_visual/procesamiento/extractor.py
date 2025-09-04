from typing import Dict, Any, List
from io import BytesIO
import pdfplumber
import warnings
import fitz
import json
import re

class PDFCifradoError(Exception):
    """Excepción personalizada para PDFs protegidos por contraseña."""
    pass

def extraer_texto_pdf_con_fitz(pdf_bytes: bytes) -> str:
    """
    Extrae texto de un archivo PDF desde memoria (bytes) usando PyMuPDF (fitz).
    Convierte todo a minúsculas. Usa `with` para liberar memoria automáticamente.

    Args:
        pdf_bytes (bytes): Contenido del PDF en bytes.

    Returns:
        str: Texto extraído en minúsculas (normalizado).
    """
    texto_total = ''

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                for pagina in doc:
                    texto_pagina = pagina.get_text(sort=True)
                    if texto_pagina:
                        texto_total += texto_pagina.lower() + '\n'
        except Exception as e:
            print(f"Error al extraer texto con fitz: {e}")
            return ""

    return texto_total

# Convierte la primera página del PDF a imagen (portada)
def convertir_portada_a_imagen_bytes(pdf_bytes: bytes, paginas: List[int]) -> BytesIO:
    """
    Convierte una lista específica de números de página de un PDF a imágenes en memoria.
    """
    buffers = []
    matriz_escala = fitz.Matrix(2, 2)
    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
    
        for num_pagina in paginas:
            # Los índices de página en PyMuPDF son base 0, por eso restamos 1.
            if num_pagina - 1 < len(documento):
                pagina = documento.load_page(num_pagina - 1)
                pix = pagina.get_pixmap(matrix = matriz_escala)
                img_bytes = pix.tobytes("png")
                buffers.append(BytesIO(img_bytes))
                
        documento.close()
    
    except Exception as e:
        print(f"Error al convertir PDF a imagen con PyMuPDF: {e}")
        return [] # lista vacía en caso de error
    return buffers

def extraer_json_del_markdown(respuesta: str) -> Dict[str, Any]:
    print(respuesta)
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', respuesta, re.DOTALL)
    json_string = json_match.group(1) if json_match else respuesta
    try:
        print("Json encontrado")
        return json.loads(json_string)
    except json.JSONDecodeError:
        print(f"El modelo no devolvió un JSON válido. Respuesta: {respuesta[:200]}...")
        return {}

def extraer_texto_limitado(pdf_bytes: bytes, num_paginas: int = 2) -> str:
    """
    Extrae texto de las primeras 'num_paginas' de un PDF para una verificación rápida.
    Si el PDF está encriptado, lanza una excepción PDFCifradoError.
    """
    texto_parcial = ''
    try:
        # Abre el documento una sola vez
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            if doc.is_encrypted:
                raise PDFCifradoError("El documento está protegido por contraseña, imposible trabajar con el.")
            # Si no está encriptado, itera sobre el número de páginas que necesitamos
            for i in range(min(len(doc), num_paginas)):
                texto_parcial += doc[i].get_text(sort=True).lower() + '\n'
    except PDFCifradoError:
        raise
    except Exception as e:
        print(f"Error durante la extracción limitada de texto con fitz: {e}")
        return ""
    return texto_parcial