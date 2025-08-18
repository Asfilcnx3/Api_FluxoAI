from io import BytesIO
from typing import List, Dict, Any, Optional
from fastapi import HTTPException
import base64
import fitz
import json
import os
import re
from openai import AsyncOpenAI
from ..models import ResultadoConsolidado
from pyzbar.pyzbar import decode
from PIL import Image

client_gpt_nomi = AsyncOpenAI(
    api_key=os.getenv("OPENAI_API_KEY_NOMI")
)

CAMPOS_STR = ["nombre", "rfc", "curp", "dependencia", "secretaria", "numero_empleado", "puesto_cargo", "categoria", "periodo_inicio", "periodo_fin", "fecha_pago", "periodicidad", "clabe", "nombre_usuario", "numero_cuenta", "domicilio", "inicio_periodo", "fin_periodo"]
CAMPOS_FLOAT = ["salario_neto", "total_percepciones", "total_deducciones", "saldo_promedio"]

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

    print("No se encontró ningún código QR en las imágenes.")
    return None # No se encontró ningún QR en ninguna imagen

def extraer_json_del_markdown(respuesta: str) -> Dict[str, Any]:
    json_match = re.search(r'```json\s*(\{.*?\})\s*```', respuesta, re.DOTALL)
    json_string = json_match.group(1) if json_match else respuesta
    try:
        return json.loads(json_string)
    except json.JSONDecodeError:
        raise ValueError(f"El modelo no devolvió un JSON válido. Respuesta: {respuesta[:200]}...")

async def analizar_portada_gpt(
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
    for campo in CAMPOS_STR:
        if campo in datos_limpios and datos_limpios[campo] is not None:
            datos_limpios[campo] = str(datos_limpios[campo])

    # --- Forzar campos a ser FLOATS ---
    # Campos que deben ser números limpios
    for campo in CAMPOS_FLOAT:
        if campo in datos_limpios:
            datos_limpios[campo] = limpiar_monto(datos_limpios[campo])
            
    return datos_limpios

from datetime import datetime
from dateutil.relativedelta import relativedelta
from typing import Optional

def verificar_fecha_comprobante(fecha_str: Optional[str]) -> Optional[bool]:
    """
    Verifica si una fecha en formato 'AAAA-MM-DD' es de los últimos 3 meses.
    """
    if not fecha_str:
        return None
    
    try:
        # Convertimos el string a un objeto de fecha
        fecha_comprobante = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        
        # Obtenemos la fecha de hoy y la de hace 3 meses
        fecha_hoy = datetime.now().date()
        fecha_limite = fecha_hoy - relativedelta(months=3)
        
        # Comparamos
        return fecha_comprobante >= fecha_limite
        
    except (ValueError, TypeError):
        # Si la fecha tiene un formato incorrecto, no podemos validarla
        return None
    
def aplicar_reglas_de_negocio(resultado: ResultadoConsolidado) -> ResultadoConsolidado:
    """
    Aplica las reglas de negocio finales a un objeto ResultadoConsolidado.
    """
    # Si no hay objetos que procesar, devuelve el resultado tal cual
    if not resultado:
        return resultado

    # --- Regla 1: Verificación de la fecha del comprobante ---
    if resultado.Comprobante and resultado.Comprobante.fin_periodo:
        resultado.es_menor_a_3_meses = verificar_fecha_comprobante(resultado.Comprobante.fin_periodo)

    # --- Regla 2: Verificación de coincidencia de RFC ---
    # Se ejecuta solo si tenemos los datos de Nómina y Estado, y ambos tienen un RFC.
    if (resultado.Nomina and resultado.Nomina.rfc and resultado.Estado and resultado.Estado.rfc):
        resultado.el_rfc_es_igual = (resultado.Nomina.rfc.upper() == resultado.Estado.rfc.upper())

    # # --- Regla X: Verificación de coincidencia de CURP ---
    # # Se ejecuta solo si tenemos los datos de Nómina y Estado, y ambos tienen un CURP.
    # if (resultado.Nomina and resultado.Nomina.curp and resultado.Estado and resultado.Estado.curp):
    #     resultado.el_curp_es_igual = (resultado.Nomina.curp.upper() == resultado.Estado.curp.upper())
            
    return resultado