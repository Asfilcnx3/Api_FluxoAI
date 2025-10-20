# Aqui irán todas las funciones de extracción de PDF (sin IA)
from ..core.exceptions import PDFCifradoError
from ..utils.helpers_texto_nomi import PATTERNS_COMPILADOS_RFC_CURP

from typing import Dict, List, Optional, Tuple, Any
import re
from io import BytesIO
from pyzbar.pyzbar import decode
import fitz
import logging
import pytesseract
from PIL import Image

logger = logging.getLogger(__name__)

def convertir_pdf_a_imagenes(pdf_bytes: bytes, paginas: List[int] = [1]) -> List[BytesIO]:
    buffers_imagenes = []
    matriz_escala = fitz.Matrix(2, 2)  # Aumentar resolución

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as documento:
            for num_pagina in paginas:
                if 0 <= num_pagina - 1 < len(documento):
                    pagina = documento.load_page(num_pagina - 1)
                    pix = pagina.get_pixmap(matrix=matriz_escala)
                    img_bytes = pix.tobytes("png")
                    buffers_imagenes.append(BytesIO(img_bytes))
                else:
                    logger.warning(f"Advertencia: Página {num_pagina} fuera de rango.")

    except Exception as e:
        # Lanza un error estándar que será atrapado y reportado por archivo
        raise ValueError(f"No se pudo procesar el archivo como PDF: {e}")

    return buffers_imagenes

def leer_qr_de_imagenes(imagen_buffers: List[BytesIO]) -> Optional[str]:
    """
    Lee una lista de imágenes en memoria y devuelve el contenido del primer QR que encuentre.
    """
    for buffer in imagen_buffers:
        # Reiniciamos el puntero del buffer para que PIL pueda leerlo
        buffer.seek(0)
        imagen = Image.open(buffer)

        # 'decode' busca todos los códigos de barras/QR en la imagen
        codigos_encontrados = decode(imagen)

        if codigos_encontrados:
            # Devolvemos el dato del primer código encontrado, decodificado a string
            primer_codigo = codigos_encontrados[0].data.decode("utf-8")
            return primer_codigo

    logger.error("No se encontró ningún código QR en las imágenes.")
    return None # No se encontró ningún QR en ninguna imagen

# Estas funciones hacen el trabajo pesado para UN SOLO PDF.
# --- FUNCIÓN PARA EXTRACCIÓN DE TEXTO CON OCR ---

def extraer_texto_con_ocr(pdf_bytes: bytes, dpi: int = 300) -> str:
    """
    Realiza OCR en todas las páginas de un PDF (dado en bytes) y devuelve el texto concatenado.
    """
    textos_de_paginas = []
    try:
        doc_pdf = fitz.open(stream=pdf_bytes, filetype="pdf")

        for pagina in doc_pdf:
            pix = pagina.get_pixmap(dpi=dpi)
            img_bytes = pix.tobytes("png")
            imagen_pil = Image.open(BytesIO(img_bytes))

            texto_pagina = pytesseract.image_to_string(imagen_pil)
            textos_de_paginas.append(texto_pagina.lower())

        doc_pdf.close()
        return "\n".join(textos_de_paginas)
    except Exception as e:
        return f"ERROR_OCR: {e}" 
    
# --- FUNCIÓN PARA LA EXTRACCIÓN DE TEXTO CON FITZ SIN OCR ---
def extraer_texto_de_pdf(pdf_bytes: bytes, num_paginas: Optional[int] = None) -> str:
    """
    Extrae texto de un archivo PDF desde memoria (bytes) usando PyMuPDF (fitz).
    Convierte todo a minúsculas. Usa `with` para liberar memoria automáticamente.

    - Si `num_paginas` es None (por defecto), extrae todas las páginas.
    - Si `num_paginas` es un int (ej. 2), extrae las primeras 'n' páginas.
    - Lanza PDFCifradoError si el documento está protegido con contraseña.
    - Lanza RuntimeError para otros errores de extracción.

    Args:
        pdf_bytes (bytes): Contenido del PDF en bytes.

    Returns:
        str: Texto extraído en minúsculas (normalizado).
    """
    texto_extraido = ''

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            # 1. Verificación e Contraseña (se hace una sola vez)
            if doc.is_encrypted: # Si el documento está con contraseña arrojamos un error
                raise PDFCifradoError("El documento está protegido por contraseña.")
            
            # 2. Determinar el rango de páginas a procesar
            paginas_a_iterar = doc
            if num_paginas is not None and num_paginas > 0:
                # Crea un iterador solo para las primeras 'n' páginas
                paginas_a_iterar = list(doc.pages())[:num_paginas]

            # 3. Extraer el texto del rango de páginas seleccionado
            for pagina in paginas_a_iterar:
                texto_pagina = pagina.get_text(sort=True)
                if texto_pagina:
                    texto_extraido += texto_pagina.lower() + '\n'

    except PDFCifradoError:
        # Si es un error de contraseña, lo relanzamos para que la API lo maneje
        raise
    except Exception as e:
        # Para cualquier otro error, lanzamos un error genérico
        logger.warning(f"Error durante la extracción de texto con fitz: {e}")
        raise RuntimeError(f"No se pudo leer el contenido del PDF: {e}") from e
        
    return texto_extraido

# --- FUNCIÓN PARA EXTRAER MOVIMIENTOS CON POSICIONES ---
def extraer_movimientos_con_posiciones(pdf_bytes: bytes) -> Dict[int, List[Dict[str, Any]]]:
    """
    Extrae todos los movimientos del PDF. Para cada página, intenta identificar las
    columnas de 'cargos' y 'abonos' primero por encabezados y, si falla,
    mediante un análisis estadístico de los grupos de montos.
    """
    resultados_por_pagina = {}
    CARGOS_KEYWORDS = ["cargos", "retiros", "retiros/cargos"]
    ABONOS_KEYWORDS = ["abonos", "depositos", "depósitos", "depósitos/abonos"]

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                resultados_por_pagina[page_num] = []
                words = page.get_text("words")

                zona_cargos, zona_abonos = None, None

                # --- PASO 1: INTENTAR UBICAR POR ENCABEZADOS ---
                cargos_header_x, abonos_header_x = None, None
                for w in words:
                    word_text = w[4].lower().strip()
                    if word_text in CARGOS_KEYWORDS:
                        cargos_header_x = (w[0] + w[2]) / 2 # Centro del encabezado
                    elif word_text in ABONOS_KEYWORDS:
                        abonos_header_x = (w[0] + w[2]) / 2 # Centro del encabezado

                if cargos_header_x and abonos_header_x:
                    logging.info(f"Página {page_num}: Columnas identificadas por encabezados.")
                    # Define las zonas como un rango alrededor del centro del encabezado
                    zona_cargos = (cargos_header_x - 50, cargos_header_x + 50)
                    zona_abonos = (abonos_header_x - 50, abonos_header_x + 50)

                # --- PASO 2: SI FALLA, USAR ESTADÍSTICA DE GRUPOS ---
                if not (zona_cargos and zona_abonos):
                    logging.info(f"Página {page_num}: No se encontraron encabezados. Usando análisis estadístico.")

                    montos_con_coords = [
                        {"centro_x": (w[0] + w[2]) / 2, "monto": float(w[4].replace(',', '')), "coords": w[:4]}
                        for w in words if re.fullmatch(r'[\d,]+\.\d{2}', w[4].strip())
                    ]

                    if len(montos_con_coords) > 1:
                        # Ordenar los montos por su posición X
                        montos_con_coords.sort(key=lambda item: item['centro_x'])

                        # Encontrar la brecha más grande para separar los grupos
                        brechas = [montos_con_coords[i+1]['centro_x'] - montos_con_coords[i]['centro_x'] for i in range(len(montos_con_coords)-1)]

                        if brechas:
                            brecha_maxima = max(brechas)
                            umbral_columna = brecha_maxima * 0.7 # Un umbral para definir qué es un "salto de columna"

                            columnas = []
                            columna_actual = [montos_con_coords[0]]
                            for i in range(len(brechas)):
                                if brechas[i] > umbral_columna:
                                    columnas.append(columna_actual)
                                    columna_actual = []
                                columna_actual.append(montos_con_coords[i+1])
                            columnas.append(columna_actual)

                            logging.info(f"Página {page_num}: Se detectaron {len(columnas)} columnas de montos.")

                            if len(columnas) >= 2:
                                # Tomar las dos columnas más a la izquierda
                                columna_cargos = columnas[0]
                                columna_abonos = columnas[1]
                                # Definir las zonas basadas en el rango de cada columna
                                zona_cargos = (min(m['centro_x'] for m in columna_cargos) - 10, max(m['centro_x'] for m in columna_cargos) + 10)
                                zona_abonos = (min(m['centro_x'] for m in columna_abonos) - 10, max(m['centro_x'] for m in columna_abonos) + 10)

                # --- CLASIFICACIÓN FINAL ---
                if not (zona_cargos and zona_abonos):
                    logging.warning(f"Página {page_num}: No se pudieron definir las zonas. Clasificación podría ser incorrecta.")
                    continue

                all_montos_on_page = [
                    {"monto": float(w[4].replace(',', '')), "centro_x": (w[0]+w[2])/2, "coords": w[:4]}
                    for w in words if re.fullmatch(r'[\d,]+\.\d{2}', w[4].strip())
                ]

                for monto_info in all_montos_on_page:
                    tipo = "indefinido"
                    if zona_cargos[0] <= monto_info["centro_x"] <= zona_cargos[1]:
                        tipo = "cargo"
                    elif zona_abonos[0] <= monto_info["centro_x"] <= zona_abonos[1]:
                        tipo = "abono"

                    resultados_por_pagina[page_num].append({
                        "monto": monto_info["monto"], "tipo": tipo, "coords": monto_info["coords"]
                    })

    except Exception as e:
        logging.error(f"Error al procesar posiciones en documento: {e}", exc_info=True)

    return resultados_por_pagina

# --- FUNCIÓN PARA EXTRAER RFC Y CURP DE TEXTO ---
def extraer_rfc_curp_por_texto(texto: str, tipo_doc: str) -> Tuple[List[str], List[str]]:
    """
    Busca RFC y/o CURP en el texto probando solo los patrones 
    definidos para el tipo de documento indicado (ej: 'nomina', 'estado').
    Devuelve dos listas: [RFCs encontrados], [CURPs encontrados].
    """
    if not texto or not tipo_doc:
        return [], []

    rfcs, curps = [], []

    # Buscar RFCs para ese tipo de documento
    patron_rfc = PATTERNS_COMPILADOS_RFC_CURP["RFC"].get(tipo_doc.lower())
    if patron_rfc:
        for match in patron_rfc.finditer(texto):
            rfcs.append(match.group(1).upper())

    # Buscar CURPs para ese tipo de documento
    patron_curp = PATTERNS_COMPILADOS_RFC_CURP["CURP"].get(tipo_doc.lower())
    if patron_curp:
        for match in patron_curp.finditer(texto):
            curps.append(match.group(1).upper())

    return rfcs, curps