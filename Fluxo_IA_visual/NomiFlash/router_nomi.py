from fastapi import APIRouter, UploadFile, File
from typing import List, Union
from ..models import NomiRes, NomiErrorRespuesta
import asyncio
from .procesamiento_nomi import _procesar_un_archivo

router = APIRouter(
    prefix="/nomi_flash",
    tags=["Procesamiento de Nóminas (NomiFlash)"]
)

@router.post(
        "/extraer_datos",
        response_model=Union[NomiRes, NomiErrorRespuesta],
        summary="(Demo de Prueba) Extrae datos de uno o más recibos de nómina en PDF."
)
async def procesar_nomina(
    archivo: UploadFile = File(..., description="Uno o más archivos PDF de nóminas a procesar")
):
    """
    Sube uno o más archivos PDF. El sistema procesa cada uno y devuelve una lista de resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_nomina_transaccion` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error 503.
    """
    resultado = _procesar_un_archivo(archivo)
    
    return resultado