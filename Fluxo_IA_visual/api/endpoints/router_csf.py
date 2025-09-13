from fastapi import APIRouter, File, UploadFile
from typing import Union

from ...models.responses import CSF 
from ...services.orchestators import procesar_constancia

router = APIRouter()

@router.post(
    "/extraer_datos",
    response_model=Union[CSF.ResultadoConsolidado, CSF.ErrorRespuesta],
    summary="Extrae datos de una Constancia de Situación Fiscal."
)
async def procesar_csf_api(
    archivo_csf: UploadFile = File(...)
):
    """
    Sube un archivo PDF de una Constancia de Situación Fiscal.
    El sistema intentará extraer los datos usando Regex como método principal.
    Si falla, utilizará un modelo de IA como respaldo.
    """
    if not archivo_csf:
            return CSF.ErrorRespuesta(error="No se proporcionó ningún archivo.")

    resultado = await procesar_constancia(archivo_csf)
    return resultado