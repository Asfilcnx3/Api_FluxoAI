from fastapi import APIRouter, UploadFile, File
from typing import Union, Optional
import logging
import openai

from ...models.responses import CSF
from ...services.orchestators import procesar_constancia

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post(
        "/extraer_datos",
        response_model=Union[CSF.ResultadoConsolidado, CSF.ErrorRespuesta],
        summary="Extrae datos de diferentes tipos de documentos."
)
async def procesar_documentos_consolidados(
    constancia_situacion_fiscal: Optional[UploadFile] = File(None),
):
    """
    Sube un archivo PDF. El sistema lo procesa asincronamente y devuelve una lista de resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_lectura` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error 503.
    """
    if not constancia_situacion_fiscal:
        return CSF.ErrorRespuesta("No se proporcionó ningún archivo.")
    
    try:
        resultado = await procesar_constancia(constancia_situacion_fiscal)
        
        return resultado

    ## Manejo de errores globales
    except openai.AuthenticationError:
        # Error específico si la API Key es incorrecta
        return CSF.ErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    
    except openai.APIConnectionError:
        # Error específico si no se puede conectar a la API
        return CSF.ErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    
    except Exception as e:
        # Error genérico para cualquier otro fallo inesperado y fatal
        logger.error(f"Error global inesperado: {e}")
        return CSF.ErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")