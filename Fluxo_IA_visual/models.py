from typing import List, Optional, Union
from pydantic import BaseModel

class ArchivoPDF(BaseModel):
    usar_ocr: Optional[bool] = False 

class ErrorRespuesta(BaseModel):
    error: str

class NomiErrorRespuesta(BaseModel):
    error: str

class Transaccion(BaseModel):
    fecha: str
    descripcion: str
    monto: str

class ResultadoAnalisisIA(BaseModel):
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

class ResultadoTPV(BaseModel):
    transacciones: List[Transaccion] = []
    error_transacciones: Optional[str] = None

class ResultadoExtraccion(BaseModel):
    AnalisisIA: Optional[ResultadoAnalisisIA] = None
    DetalleTransacciones: Optional[Union[ResultadoTPV, ErrorRespuesta]] = None

class ResultadoTotal(BaseModel):
    total_depositos: Optional[float] = None
    es_mayor_a_250: Optional[bool] = None
    resultados_generales: List[ResultadoAnalisisIA]
    resultados_individuales: List[ResultadoExtraccion]

class RespuestaNomina(BaseModel):
    datos_qr: Optional[str] = None
    nombre: Optional[str] = None
    rfc: Optional[str] = None
    curp: Optional[str] = None
    dependencia: Optional[str] = None
    secretaria: Optional[str] = None
    numero_empleado: Optional[str] = None
    puesto_cargo: Optional[str] = None
    categoria: Optional[str] = None
    total_percepciones: Optional[float] = None
    total_deducciones: Optional[float] = None
    salario_neto: Optional[float] = None
    periodo_inicio: Optional[str] = None
    periodo_fin: Optional[str] = None
    fecha_pago: Optional[str] = None
    periodicidad: Optional[str] = None
    error_lectura_nomina: Optional[str] = None

class RespuestaEstado(BaseModel):
    datos_qr: Optional[str] = None
    clabe: Optional[str] = None
    nombre_usuario: Optional[str] = None
    rfc: Optional[str] = None
    numero_cuenta: Optional[str] = None
    error_lectura_estado: Optional[str] = None

class RespuestaComprobante(BaseModel):
    domicilio: Optional[str] = None
    inicio_periodo: Optional[str] = None
    fin_periodo: Optional[str] = None
    error_lectura_comprobante: Optional[str] = None

class ResultadoConsolidado(BaseModel):
    Nomina: Optional[RespuestaNomina] = None
    Estado: Optional[RespuestaEstado] = None
    Comprobante: Optional[RespuestaComprobante] = None
    es_menor_a_3_meses: Optional[bool] = None
    el_rfc_es_igual: Optional[bool] = None    