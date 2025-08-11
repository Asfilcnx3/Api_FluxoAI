from fastapi import APIRouter, UploadFile, File
from typing import List
from ..models import NomiRes
import asyncio
from .procesamiento_nomi import _procesar_un_archivo

router = APIRouter(
    prefix="/nomi_flash",
    tags=["Procesamiento de Nóminas (NomiFlash)"]
)

@router.post(
        "/extraer_datos",
        response_model=List[NomiRes],
        summary="(Demo de Prueba) Extrae datos de uno o más recibos de nómina en PDF."
)
async def procesar_nomina(
    archivos: List[UploadFile] = File(..., description="Uno o más archivos PDF de nóminas a procesar")
):
    """
    Sube uno o más archivos PDF. El sistema procesa cada uno y devuelve una lista de resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_nomina_transaccion` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error 503.
    """
    # Crear una tarea de procesamiento para cada archivo subido
    tasks = [_procesar_un_archivo(archivo) for archivo in archivos]
    
    # Ejecutar todas las tareas en paralelo y esperar a que terminen
    resultados = await asyncio.gather(*tasks)
    
    return resultados