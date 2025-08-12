import fitz
import base64
import json
import re
import os
from io import BytesIO
from typing import List, Dict, Any, Union
from fastapi import UploadFile, HTTPException
from openai import OpenAI
from ..models import NomiRes, NomiErrorRespuesta

client_gpt_nomi = OpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NOMI")
)


prompt_base = """
Esta imágen es de la primera páginas de un recibo de nómina, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- nombre
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c"
- curp # es un código de 4 letras, 6 números, 6 letras y 2 números
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
        response = client_gpt_nomi.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": content}],
            reasoning_effort=razonamiento
        )
        return response.choices[0].message.content  
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"El servicio de IA no está disponible: {e}")

def limpiar_monto(monto: Any) -> float:
    """
    Convierte un monto de cualquier tipo (string, int, float) a un float limpio.
    Maneja de forma segura valores como '$1,234.56', 1234, 1234.56, y None.
    """
    # Si ya es un número, simplemente lo convertimos a float y lo devolvemos.
    if isinstance(monto, (int, float)):
        return float(monto)

    # Si es un string, aplicamos la lógica de limpieza.
    if isinstance(monto, str):
        # Elimina el símbolo de moneda, comas y espacios
        monto_limpio = monto.replace('$', '').replace(',', '').strip()
        try:
            return float(monto_limpio)
        except ValueError:
            # Esto ocurre si el string está vacío o no es numérico después de limpiar
            return 0.0
        
def sanitizar_datos_ia(datos_crudos: Dict[str, Any]) -> Dict[str, Any]:
    """
    Toma el diccionario crudo de la IA y asegura que los tipos de datos
    sean los correctos para el modelo Pydantic.
    """
    if not datos_crudos:
        return {}

    datos_limpios = datos_crudos.copy()

    # --- Forzar campos a ser STRINGS ---
    # Campos que deben ser strings (incluso si la IA los devuelve como números)
    campos_str = ["nombre", "rfc", "curp", "dependencia", "secretaria", "numero_empleado", "puesto_cargo", "categoria", "periodo_inicio", "periodo_fin", "fecha_pago", "periodicidad"]
    for campo in campos_str:
        if campo in datos_limpios and datos_limpios[campo] is not None:
            datos_limpios[campo] = str(datos_limpios[campo])

    # --- Forzar campos a ser FLOATS ---
    # Campos que deben ser números limpios
    campos_float = ["salario_neto", "total_percepciones", "total_deducciones", "saldo_promedio"]
    for campo in campos_float:
        if campo in datos_limpios:
            datos_limpios[campo] = limpiar_monto(datos_limpios[campo])
            
    return datos_limpios

def _procesar_un_archivo(archivo: UploadFile) -> Union[NomiRes, NomiErrorRespuesta]:
    """
    Función auxiliar que procesa un solo archivo.
    Devuelve un objeto NomiRes en caso de éxito o NomiErrorRespuesta en caso de fallo.
    """
    try:
        # Leer contenido. Si falla, la excepción será capturada.
        pdf_bytes = archivo.file.read()
        
        # Analizar con GPT. Puede lanzar HTTPException (fatal) o ValueError (por archivo).
        respuesta_gpt = analizar_portada_gpt(prompt_base, pdf_bytes)
        
        # Extraer JSON de la respuesta.
        datos_crudos = extraer_json_del_markdown(respuesta_gpt)

        # Sanitizamos los datos para que funcione perfectamente
        datos_listos = sanitizar_datos_ia(datos_crudos)
        
        # Si todo fue exitoso, devuelve los datos.
        return NomiRes(**datos_listos)

    except Exception as e:
        # Si la excepción es HTTPException, se debe relanzar para que FastAPI la maneje como error global.
        if isinstance(e, HTTPException):
            raise
        
        # Para cualquier otro error (ValueError de conversión, etc.), lo reportamos en el campo de error del archivo.
        return NomiErrorRespuesta(
            filename=archivo.filename,
            error=f"Error procesando el archivo: {str(e)[:200]}"
        )