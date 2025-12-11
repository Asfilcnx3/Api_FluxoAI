# Aqui irán todas las funciones de extracción de PDF (sin IA)
from ..core.exceptions import PDFCifradoError
from ..utils.helpers_texto_fluxo import TRIGGERS_CONFIG

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
def extraer_movimientos_con_posiciones(pdf_bytes: bytes) -> Tuple[Dict[int, List[Dict[str, Any]]], Dict[int, str], List[Tuple[int, int]]]:
    """
    Extrae movimientos y detecta RANGOS EXACTOS de cuentas (Inicio -> Fin).
    Si no encuentra rangos, devuelve el documento completo como un solo rango.
    """
    resultados_por_pagina = {}
    texto_por_pagina = {}
    
    # Ahora almacenamos TUPLAS (inicio, fin)
    rangos_detectados: List[Tuple[int, int]] = [] 
    
    # Variables de control de estado
    inicio_actual: Optional[int] = None
    
    # Regex y Mappings (Igual que antes)
    KEYWORDS_MAPPING = {
        "cargo": ["cargos", "retiros", "retiro", "debitos", "débitos", "cargo", "debe", "signo"],
        "abono": ["abonos", "depositos", "depósito", "depósitos", "creditos", "créditos", "abono"]
    }
    MONTO_REGEX = re.compile(r'^\d{1,3}(?:,\d{3})*\.\d{2}$')

    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
            total_paginas = len(doc)
            
            for page_index, page in enumerate(doc):
                page_num = page_index + 1
                
                # Extracción de texto
                page_text = page.get_text("text").lower()
                words = page.get_text("words") 
                
                texto_por_pagina[page_num] = page_text
                resultados_por_pagina[page_num] = []
                
                # --- LÓGICA DE DETECCIÓN DE RANGOS ---
                
                # 1. Si NO tenemos un inicio activo, buscamos palabras de INICIO
                if inicio_actual is None:
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        logging.info(f"Página {page_num}: Inicio de cuenta detectado.")
                        inicio_actual = page_num
                        # OJO: No hacemos 'continue', porque la cuenta podría empezar y acabar en esta misma página.

                # 2. Si TENEMOS un inicio activo, buscamos palabras de FIN o un NUEVO INICIO (cascada)
                if inicio_actual is not None:
                    encontrado_fin = False
                    
                    # A. ¿Hay palabra de fin?
                    if any(trig in page_text for trig in TRIGGERS_CONFIG["fin"]):
                        logging.info(f"Página {page_num}: Fin de cuenta detectado (Cierre normal).")
                        rangos_detectados.append((inicio_actual, page_num))
                        inicio_actual = None # Reseteamos para buscar la siguiente cuenta
                        encontrado_fin = True
                    
                    # B. Seguridad: ¿Aparece un NUEVO INICIO sin haber cerrado el anterior?
                    # Esto pasa si el banco no pone footer legal entre cuentas pegadas.
                    elif page_num > inicio_actual and any(trig in page_text for trig in TRIGGERS_CONFIG["inicio"]):
                        logging.info(f"Página {page_num}: Nuevo inicio detectado. Cerrando cuenta anterior en pág {page_num - 1}.")
                        rangos_detectados.append((inicio_actual, page_num - 1))
                        inicio_actual = page_num # El inicio actual es esta página
                    
                    # C. Si estamos en la última página y sigue abierta, cerramos a la fuerza
                    if not encontrado_fin and inicio_actual is not None and page_num == total_paginas:
                        logging.info(f"Página {page_num}: Fin de documento. Cerrando cuenta abierta.")
                        rangos_detectados.append((inicio_actual, total_paginas))
                        inicio_actual = None

                # --- LÓGICA DE EXTRACCIÓN DE COLUMNAS (Solo si estamos dentro de una posible cuenta) ---
                # (Optimizacion: Si inicio_actual es None, técnicamente no deberíamos extraer, 
                # pero lo dejamos correr por si el fallback se activa al final).
                
                # --- PASO 1: DETECTAR UBICACIÓN DE ENCABEZADOS ---
                headers_found = {"cargo": [], "abono": []}
                for w in words:
                    text_clean = w[4].lower().strip().replace(":", "").replace(".", "")
                    if text_clean in KEYWORDS_MAPPING["cargo"]:
                        headers_found["cargo"].append((w[0] + w[2]) / 2)
                    elif text_clean in KEYWORDS_MAPPING["abono"]:
                        headers_found["abono"].append((w[0] + w[2]) / 2)

                if not headers_found["cargo"] and not headers_found["abono"]:
                    continue

                # --- PASO 2: AGRUPAR NÚMEROS EN COLUMNAS ---
                candidatos_montos = [
                    {"centro_x": (w[0] + w[2]) / 2, "monto": float(w[4].replace(',', '')), "coords": w[:4], "x0": w[0], "x1": w[2]}
                    for w in words if MONTO_REGEX.fullmatch(w[4].strip())
                ]

                if len(candidatos_montos) < 3: continue 

                candidatos_montos.sort(key=lambda x: x['centro_x'])
                columnas = []
                if candidatos_montos:
                    columna_actual = [candidatos_montos[0]]
                    for i in range(len(candidatos_montos)-1):
                        diff = candidatos_montos[i+1]['centro_x'] - candidatos_montos[i]['centro_x']
                        if diff < 20: 
                            columna_actual.append(candidatos_montos[i+1])
                        else:
                            columnas.append(columna_actual)
                            columna_actual = [candidatos_montos[i+1]]
                    columnas.append(columna_actual)

                columnas_validas = [col for col in columnas if len(col) >= 3]
                
                # --- PASO 3: VINCULAR COLUMNAS ---
                for columna in columnas_validas:
                    col_min_x = min(m['x0'] for m in columna)
                    col_max_x = max(m['x1'] for m in columna)
                    tipo_asignado = "indefinido"
                    margin = 15
                    
                    for header_x in headers_found["cargo"]:
                        if (col_min_x - margin) <= header_x <= (col_max_x + margin):
                            tipo_asignado = "cargo"; break
                    
                    if tipo_asignado == "indefinido":
                        for header_x in headers_found["abono"]:
                            if (col_min_x - margin) <= header_x <= (col_max_x + margin):
                                tipo_asignado = "abono"; break
                    
                    if tipo_asignado != "indefinido":
                        for item in columna:
                            resultados_por_pagina[page_num].append({
                                "monto": item["monto"], "tipo": tipo_asignado, "coords": item["coords"]
                            })

    except Exception as e:
        logging.error(f"Error al procesar posiciones: {e}", exc_info=True)
    
    # --- FALLBACK ---
    # Si no detectamos ningún rango (ni inicio ni fin), asumimos que TODO el PDF es una cuenta
    if not rangos_detectados:
        logging.warning("No se detectaron triggers de inicio/fin. Usando fallback (Todo el documento).")
        rangos_detectados = [(1, len(texto_por_pagina))]

    # Retornamos los RANGOS ya calculados
    return resultados_por_pagina, texto_por_pagina, rangos_detectados