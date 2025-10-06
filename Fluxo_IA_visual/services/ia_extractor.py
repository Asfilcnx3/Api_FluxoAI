from .pdf_processor import convertir_pdf_a_imagenes
from ..core.config import settings

from fastapi import HTTPException
from openai import AsyncOpenAI
from typing import List, Dict
from io import BytesIO
import json
import base64


nomi_api = settings.OPENAI_API_KEY_NOMI.get_secret_value()
fluxo_api = settings.OPENAI_API_KEY_FLUXO.get_secret_value()
openrouter_api = settings.OPENROUTER_API_KEY.get_secret_value()

client_gpt_nomi = AsyncOpenAI(
    api_key=nomi_api
)

client_gpt_fluxo = AsyncOpenAI(
    api_key=fluxo_api
)

client_openrouter = AsyncOpenAI(
    api_key=openrouter_api,
    base_url=settings.OPENROUTER_BASE_URL,
    default_headers={
        "HTTP-Referer": "https://github.com/Asfilcnx3", 
        "X-Title": "Fluxo IA Test", 
    },
)
## ANALISIS DE FLUXO
# Función para enviar el prompt + imagen a GPT-5
async def analizar_gpt_fluxo(
        prompt: str, 
        pdf_bytes: bytes,
        paginas_a_procesar: List[int],
        razonamiento: str = "low", 
        detalle: str = "high"
    ) -> str:
    """
    Se hace la llamada al modelo GPT-5 con razonamiento bajo y detalle de imagen alto
    """
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": detalle
                },
            })
    response = await client_gpt_fluxo.chat.completions.create(
        model="gpt-5",
        messages=[{"role": "user","content": content}],
        reasoning_effort=razonamiento
    )

    return response.choices[0].message.content

# Función para enviar el prompt + imagen a gemini
async def analizar_gemini_fluxo(prompt: str, pdf_bytes: bytes, paginas_a_procesar: List[int]) -> str:
    """
    Se hace la llamada al modelo GEMINI 1.5 flash
    """
    imagen_buffers = convertir_pdf_a_imagenes(pdf_bytes, paginas = paginas_a_procesar)
    if not imagen_buffers:
        return # ya retorna el error que dió dentro de la función
    
    content = [{"type": "text", "text": prompt}]
    # Hacemos encode a los datos de la imagen a base64
    for buffer in imagen_buffers:
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded_image}",
                "detail": "high"
                },
            })
    response = await client_openrouter.chat.completions.create(
        model="qwen/qwen3-vl-235b-a22b-instruct", # CAMBIAR AL MODELO QUE SE QUIERA USAR
        messages=[{"role": "user","content": content}],
    )

    return response.choices[0].message.content

## ANALISIS DE NOMIFLASH
async def analizar_gpt_nomi(
        prompt: str, 
        imagen_buffers: List[BytesIO], 
        razonamiento: str = "low", 
        detalle: str = "high"
    ) -> str:
    if not imagen_buffers:
        return None

    content = [{"type": "text", "text": prompt}]
    for buffer in imagen_buffers:
        buffer.seek(0)
        encoded_image = base64.b64encode(buffer.read()).decode('utf-8')
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{encoded_image}", "detail": detalle}
        })
    try:
        response = await client_gpt_nomi.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": content}],
            reasoning_effort=razonamiento
        )
        return response.choices[0].message.content  
    
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"El servicio de IA no está disponible: {e}")
    

async def _extraer_datos_con_ia(texto: str) -> Dict:
    """
    Función de fallback que usa la IA para extraer los datos si la regex falla.
    """
    prompt_ia = f"""
    Extrae los datos de la siguiente Constancia de Situación Fiscal.
    Devuelve únicamente un JSON con las secciones: 'identificacion_contribuyente', 'domicilio_registrado'.
    Texto a analizar:
    ---
    {texto[:4000]}
    """
    try:
        response = await client_gpt_fluxo.chat.completions.create(
            model="gpt-5",
            messages=[{"role": "user", "content": prompt_ia}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
    except Exception as e:
        return e
