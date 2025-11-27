import os
import logging
import time
import json

logger = logging.getLogger(__name__)
DOWNLOADS_DIR = "downloads" # Carpeta local

# Aseguramos que la carpeta exista
os.makedirs(DOWNLOADS_DIR, exist_ok=True)

# 3600 segundos = 1 hora. Los archivos más viejos que esto se borrarán.
TIEMPO_VIDA_SEGUNDOS = 3600

def limpiar_archivos_antiguos():
    """
    Recorre la carpeta de descargas y elimina archivos que superen el tiempo de vida.
    Se ejecuta de manera silenciosa para no interrumpir el flujo principal.
    """
    try:
        ahora = time.time()
        archivos = os.listdir(DOWNLOADS_DIR)
        
        contador_borrados = 0
        for archivo in archivos:
            ruta_completa = os.path.join(DOWNLOADS_DIR, archivo)
            
            # Nos aseguramos de que sea un archivo y no una carpeta
            if os.path.isfile(ruta_completa):
                # Obtenemos la fecha de modificación del archivo
                tiempo_modificacion = os.path.getmtime(ruta_completa)
                
                # Si la antigüedad supera el límite, se borra
                if ahora - tiempo_modificacion > TIEMPO_VIDA_SEGUNDOS:
                    os.remove(ruta_completa)
                    contador_borrados += 1
        
        if contador_borrados > 0:
            logger.info(f"Limpieza automática: Se eliminaron {contador_borrados} reportes antiguos.")
            
    except Exception as e:
        # Solo logueamos el error, no detenemos el programa
        logger.warning(f"Error menor durante la limpieza de archivos antiguos: {e}")

def guardar_json_local(datos: dict, job_id: str):
    """Guarda el objeto de respuesta completo en JSON."""
    # Ejecutamos limpieza antes de guardar
    limpiar_archivos_antiguos()

    filename = f"data_{job_id}.json"
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(datos, f, ensure_ascii=False, indent=4)
        logger.info(f"JSON guardado localmente: {filepath}")
    except Exception as e:
        logger.error(f"Error guardando JSON local: {e}")

def obtener_datos_json(job_id: str) -> dict | None:
    """Lee el JSON del disco y lo devuelve como diccionario."""
    filename = f"data_{job_id}.json"
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    
    if os.path.exists(filepath):
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Error leyendo JSON: {e}")
            return None
    return None

def guardar_excel_local(contenido_bytes: bytes, job_id: str) -> str:
    """Guarda el archivo Excel en disco local (Modo Binario)."""
    # Limpieza previa
    limpiar_archivos_antiguos()

    filename = f"reporte_{job_id}.xlsx" # <--- Cambio extensión
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    
    try:
        # Usamos "wb" (write binary) porque openpyxl devuelve bytes
        with open(filepath, "wb") as f: 
            f.write(contenido_bytes)
        logger.info(f"Excel guardado localmente: {filepath}")
        return filepath
    except Exception as e:
        logger.error(f"Error guardando Excel local: {e}")
        return None

def obtener_ruta_archivo(job_id: str) -> str | None:
    """Busca el archivo .xlsx"""
    filename = f"reporte_{job_id}.xlsx" # <--- Cambio extensión
    filepath = os.path.join(DOWNLOADS_DIR, filename)
    
    if os.path.exists(filepath):
        return filepath
    return None