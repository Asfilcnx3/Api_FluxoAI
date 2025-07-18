from fastapi import FastAPI, File, UploadFile, HTTPException
from typing import List, Union
import shutil
import os
from .procesamiento.extractor import extraer_texto_pdf
from .procesamiento.regex_engine import procesar_regex_generico
from .models import Resultado, ErrorRespuesta

app = FastAPI() 

os.makedirs("static", exist_ok=True)

@app.get("/")
async def home():
    return "Hola, te equivocaste al momento de consumir la API, pero no te preocupes, para consumirla ve a con '/procesar_pdf/' o ve a '/docs/'"

@app.post("/procesar_pdf/", response_model=List[Union[Resultado, ErrorRespuesta]])
async def procesar_pdf_api(
    archivos: List[UploadFile] = File(...)
):
    rutas_temporales = []
    resultados: List[Union[Resultado, ErrorRespuesta]] = []

    try:
        for archivo in archivos:
            temp_path = f"static/{archivo.filename}"
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(archivo.file, f)
            rutas_temporales.append(temp_path)

            texto, banco = extraer_texto_pdf([temp_path])

            if banco == "Banco no identificado":
                resultados.append({"error": f"No se pudo identificar el banco en {archivo.filename}, sin soporte para documentos escaneados. Sube un documento no escaneado y vuelve a intentarlo."})
                continue

            resultado = procesar_regex_generico(banco, texto)
            resultados.append(resultado)

        return resultados
    except Exception:
        raise HTTPException(status_code=500, detail="Error inesperado, vuelve a cargar tus archivos")

    finally:
        for ruta in rutas_temporales:
            if os.path.exists(ruta):
                os.remove(ruta)