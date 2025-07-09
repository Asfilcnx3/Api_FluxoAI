from .auxiliares import encontrar_banco
from typing import List, Tuple
import pdfplumber

def extraer_texto_pdf(rutas_pdf: List[str]) -> Tuple[str, str]:
    texto_total = ''
    for ruta in rutas_pdf:
        with pdfplumber.open(ruta) as pdf:
            for pagina in pdf.pages:
                texto_pagina = pagina.extract_text()
                if texto_pagina:
                    texto_total += texto_pagina.lower() + '\n'
    banco = encontrar_banco(texto_total)
    return texto_total, banco