import fitz
import base64
import json
import re
from io import BytesIO
from typing import List, Dict, Any
from fastapi import UploadFile, HTTPException
from ..procesamiento.regex_engine import client_gpt
from ..models import NomiRes

prompt_base = """
Esta imágen es de la primera páginas de un recibo de nómina, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- dependencia # (ejemplo: 'Gobierno del Estado de Puebla' o 'SNTE')
- secretaria # Secretaría o institución pública
- numero_empleado # puede aparecer como  'NO. EMPLEADO'
- puesto_cargo # Puesto o cargo, puede aparecer como 'DESCRIPCIÓN DEL PUESTO'
- categoria # (ejemplo: "07", "08", "T")
- salario_neto # Puede aparecer como 'SUELDOS DEL PERSONAL DE BASE'
- total_percepciones # aparece a la derecha de 'Total percepciones'
- total_deducciones # aparece a la derecha de 'Total deducciones'
- periodo_inicio # Devuelve en formato "2025-12-25"
- periodo_fin # Devuelve en formato "2025-12-25"
- fecha_pago # Devuelve en formato "2025-12-25"
- periodicidad # (ejemplo: "Quincenal", "Mensual") es la cantidad de días entre periodo_inicio y periodo_fin

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
"""

# --- FUNCIONES AUXILIARES ---
def convertir_pdf_a_imagenes(pdf_bytes: bytes, paginas: List[int] = [1]) -> List[BytesIO]:
    buffers_imagenes = []
    matriz_escala = fitz.Matrix(2, 2)  # Aumentar resolución

    try:
        documento = fitz.open(stream=pdf_bytes, filetype="pdf")
        for num_pagina in paginas:
            if 0 <= num_pagina - 1 < len(documento):
                pagina = documento.load_page(num_pagina - 1)
                pix = pagina.get_pixmap(matrix=matriz_escala)
                img_bytes = pix.tobytes("png")
                buffers_imagenes.append(BytesIO(img_bytes))
            else:
                print(f"Advertencia: Página {num_pagina} fuera de rango.")
        documento.close()
    except Exception as e:
        # Lanza un error estándar que será atrapado y reportado por archivo
        raise ValueError(f"No se pudo procesar el archivo como PDF: {e}")

    return buffers_imagenes

def extraer_json_del_markdown(respuesta: str) -> Dict[str, Any]:
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', respuesta, re.DOTALL)
    json_string = json_match.group(1) if json_match else respuesta
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        raise ValueError(f"El modelo no devolvió un JSON válido. Respuesta: {respuesta[:200]}...")

def analizar_portada_gpt(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int] = [1], razonamiento: str = "low", detalle: str = "high") -> str:
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas=paginas_a_procesar)
    if not imagen_buffers:
        return None

    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded_image}", "detail": detalle}
        })
    try:
        response = client_gpt.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": content}],
            reasoning_effort=razonamiento
        )
        return response.choices[0].message.content  
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"El servicio de IA no está disponible: {e}")


async def _procesar_un_archivo(archivo: UploadFile) -> NomiRes:
    """
    Función auxiliar que procesa un solo archivo.
    Devuelve un objeto NomiRes, ya sea con datos o con un mensaje de error.
    """
    try:
        # Leer contenido. Si falla, la excepción será capturada.
        pdf_bytes = await archivo.read()
        
        # Analizar con GPT. Puede lanzar HTTPException (fatal) o ValueError (por archivo).
        respuesta_gpt = analizar_portada_gpt(prompt_base, pdf_bytes)
        
        # Extraer JSON de la respuesta.
        datos_crudos = extraer_json_del_markdown(respuesta_gpt)
        
        # Si todo fue exitoso, devuelve los datos.
        return NomiRes(**datos_crudos)

    except Exception as e:
        # Si la excepción es HTTPException, se debe relanzar para que FastAPI la maneje como error global.
        if isinstance(e, HTTPException):
            raise
        
        # Para cualquier otro error (ValueError de conversión, etc.), lo reportamos en el campo de error del archivo.
        return NomiRes(error_nomina_transaccion=f"Error procesando '{archivo.filename}': {e}")