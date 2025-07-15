from pydantic import BaseModel
from typing import List, Optional

class ArchivoPDF(BaseModel):
    usar_ocr: Optional[bool] = False 

class ErrorRespuesta(BaseModel):
    error: str

class Transaccion(BaseModel):
    fecha: str
    descripcion: str
    monto: str

class Resultado(BaseModel):
    banco: str
    periodo_inicio: Optional[str] = None
    periodo_fin: Optional[str] = None
    total_comisiones: Optional[float] = None
    total_depositos: Optional[float] = None
    total_cargos: Optional[float] = None
    saldo_promedio: Optional[float] = None
    entradas_TPV_bruto: Optional[float] = None
    entradas_TPV_neto: Optional[float] = None
    transacciones: List[Transaccion] = None