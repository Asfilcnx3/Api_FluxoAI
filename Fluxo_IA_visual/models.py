from typing import List, Optional
from pydantic import BaseModel

class ArchivoPDF(BaseModel):
    usar_ocr: Optional[bool] = False 

class ErrorRespuesta(BaseModel):
    error: str

class NomiErrorRespuesta(BaseModel):
    filename: str
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

class NomiRes(BaseModel):
    nombre: Optional[str] = None
    rfc: Optional[str] = None
    curp: Optional[str] = None
    dependencia: Optional[str] = None
    secretaria: Optional[str] = None
    numero_empleado: Optional[str] = None
    puesto_cargo: Optional[str] = None
    categoria: Optional[str] = None
    salario_neto: Optional[float] = None
    total_percepciones: Optional[float] = None
    total_deducciones: Optional[float] = None
    periodo_inicio: Optional[str] = None
    periodo_fin: Optional[str] = None
    fecha_pago: Optional[str] = None
    periodicidad: Optional[str] = None