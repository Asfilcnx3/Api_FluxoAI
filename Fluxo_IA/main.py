from fastapi import FastAPI, File, UploadFile
from typing import List
import shutil
import os
from .procesamiento.extractor import extraer_texto_pdf
from .procesamiento.regex_engine import procesar_regex_generico
from .models import Resultado

app = FastAPI() 

os.makedirs("static", exist_ok=True)

@app.post("/procesar_pdf/", response_model=List[Resultado])
async def procesar_pdf_api(
    archivos: List[UploadFile] = File(...)
):
    rutas_temporales = []
    resultados = []

    try:
        for archivo in archivos:
            temp_path = f"static/{archivo.filename}"
            with open(temp_path, "wb") as f:
                shutil.copyfileobj(archivo.file, f)
            rutas_temporales.append(temp_path)

            texto, banco = extraer_texto_pdf([temp_path])

            if banco == "Banco no identificado":
                resultados.append({"error": f"No se pudo identificar el banco en {archivo.filename}"})
                continue

            resultado = procesar_regex_generico(banco, texto)
            resultados.append(resultado)

        return resultados

    finally:
        for ruta in rutas_temporales:
            if os.path.exists(ruta):
                os.remove(ruta)