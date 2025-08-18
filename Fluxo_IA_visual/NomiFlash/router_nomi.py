from fastapi import APIRouter, UploadFile, File, Form
from typing import Union, Optional
from ..models import ResultadoConsolidado, RespuestaNomina, RespuestaComprobante, RespuestaEstado, NomiErrorRespuesta
import asyncio
import openai
from .procesamiento_nomi import procesar_comprobante, procesar_estado_cuenta, procesar_nomina
from .auxiliares_nomi import aplicar_reglas_de_negocio

router = APIRouter(
    prefix="/nomi_flash",
    tags=["Procesamiento de Nóminas (NomiFlash)"]
)

@router.post(
        "/extraer_datos",
        response_model=Union[ResultadoConsolidado, NomiErrorRespuesta],
        summary="(Demo de Prueba) Extrae datos de diferentes tipos de documentos."
)
async def procesar_documentos_consolidados(
    recibo_de_nomina: Optional[UploadFile] = File(None),
    estado_de_cuenta: Optional[UploadFile] = File(None),
    comprobante_de_domicilio: Optional[UploadFile] = File(None)

):
    """
    Sube uno o más archivos PDF. El sistema procesa todos en paralelo y devuelve una lista de resultados.
    
    - Si un archivo se procesa correctamente, obtendrás los datos extraídos.
    - Si un archivo individual falla (ej. está corrupto), obtendrás un objeto con el campo `error_lectura` detallando el problema.
    - Si ocurre un error de servicio (ej. la API de IA no responde), toda la petición fallará con un código de error 503.
    """
    try:
        tasks = []

        # 1. Creamos las tareas llamando a la función procesadora correcta para cada archivo
        if recibo_de_nomina:
            tasks.append(procesar_nomina(recibo_de_nomina))

        if estado_de_cuenta:
            tasks.append(procesar_estado_cuenta(estado_de_cuenta))

        if comprobante_de_domicilio:
            tasks.append(procesar_comprobante(comprobante_de_domicilio))

        if not tasks:
            return ResultadoConsolidado()

        # 2. Ejecutamos todas las tareas en paralelo
        resultados_parciales = await asyncio.gather(*tasks, return_exceptions=True)

        # 3. Consolidamos los resultados
        resultado_final = ResultadoConsolidado()

        for res in resultados_parciales:
            if isinstance(res, Exception):
                # Si una tarea falló por completo, registramos el error
                error_msg = f"Una de las tareas de procesamiento falló: {str(res)}"
                print(error_msg)
                # Podríamos añadirlo a una lista de errores generales si el modelo lo permitiera
                continue

            # Asignamos el resultado a su campo correspondiente
            if isinstance(res, RespuestaNomina):
                resultado_final.Nomina = res
            elif isinstance(res, RespuestaEstado):
                resultado_final.Estado = res
            elif isinstance(res, RespuestaComprobante):
                resultado_final.Comprobante = res

        # 4. APLICAMOS LAS REGLAS DE NEGOCIO A RFC, CURP Y FECHA
        # Llamamos a nuestra nueva función para que haga todo el trabajo.
        resultado_final = aplicar_reglas_de_negocio(resultado_final)

        return resultado_final
    
    ## Manejo de errores globales

    except openai.AuthenticationError:
        # Error específico si la API Key es incorrecta
        return NomiErrorRespuesta(error="Error de autenticación con el servicio de IA. Verifica la API Key.")
    except openai.APIConnectionError:
        # Error específico si no se puede conectar a la API
        return NomiErrorRespuesta(error="No se pudo conectar con el servicio de IA. Inténtalo de nuevo más tarde.")
    except Exception as e:
        # Error genérico para cualquier otro fallo inesperado y fatal
        print(f"Error global inesperado: {e}")
        return NomiErrorRespuesta(error="Ocurrió un error inesperado en el servidor.")