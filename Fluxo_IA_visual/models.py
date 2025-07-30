from typing import List, Optional
from pydantic import BaseModel

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
    rfc: Optional[str] = None
    nombre_cliente: Optional[str] = None
    clabe_interbancaria: Optional[str] = None
    periodo_inicio: Optional[str] = None
    periodo_fin: Optional[str] = None
    comisiones: Optional[float] = None
    depositos: Optional[float] = None
    cargos: Optional[float] = None
    saldo_promedio: Optional[float] = None
    entradas_TPV_bruto: Optional[float] = None
    entradas_TPV_neto: Optional[float] = None
    transacciones: List[Transaccion] = []
    error_transacciones: Optional[str] = None