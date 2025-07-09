from .auxiliares import encontrar_banco
from typing import List, Tuple
from PIL import Image
import pytesseract
import pdfplumber
import fitz
import io

def extraer_texto_ocr(ruta_pdf, dpi=200):
    """
    Extrae texto de todas las páginas de un PDF y devuelve una sola cadena de texto usando PyMuPDF y Pytesseract para ser eficiente con la memoria.

    Args:
        ruta_pdf (str): La ruta al archivo PDF.
        dpi (int): La resolución en puntos por pulgada para la conversión a imagen.

    Returns:
        str: El texto completo extraído de todas las páginas del PDF.
    """
    textos_de_paginas = []
    doc_pdf = fitz.open(ruta_pdf)

    for i, pagina in enumerate(doc_pdf):
        print(f"Procesando página {i + 1}/{len(doc_pdf)}...")
        pix = pagina.get_pixmap(dpi=dpi)
        img_bytes = pix.tobytes("png")
        imagen_pil = Image.open(io.BytesIO(img_bytes))
        texto_pagina = pytesseract.image_to_string(imagen_pil)
        textos_de_paginas.append(texto_pagina.lower())
    doc_pdf.close()
    texto_total = "\n".join(textos_de_paginas)
    banco = encontrar_banco(texto_total)
    return texto_total, banco

def extraer_texto_pdf(rutas_pdf: List[str]) -> Tuple[str, str]:
    """
    Extrae todo el texto de uno o varios archivos PDF y los convierte a minúsculas, usamos with para no cargar el documento en memoria RAM y que se cierre cuando termine de ejecutarse.

    Args:
        ruta_pdf (str): La ruta o lista de rutas a los archivos PDF.

    Returns:
        str: El texto extraído en minúsculas (normalizado).
    """
    texto_total = ''
    for ruta in rutas_pdf:
        with pdfplumber.open(ruta) as pdf:
            for pagina in pdf.pages:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_total += texto_pagina.lower() + '\n'
    banco = encontrar_banco(texto_total)
    return texto_total, banco