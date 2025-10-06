import re
from typing import  Dict


# ---- PROMPTS PARA LAS ENTRADAS DE NOMIFLASH ----
PROMPT_NOMINA = """
Esta imágen es de la primera página de un recibo de nómina, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- nombre # unicamente el nombre del empleado
- apellido_paterno # unicamente el primer apellido
- apellido_materno # unicamente el segundo apellido
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c", los primeros 10 caracteres del rfc y curp son iguales
- curp # es un código de 4 letras, 6 números, 6 letras y 2 números
- dependencia # Secretaría o institución pública
- secretaria # (ejemplo: 'Gobierno del Estado de Puebla' o 'SNTE')
- numero_empleado # puede aparecer como  'NO. EMPLEADO'
- puesto_cargo # Puesto o cargo, puede aparecer como 'DESCRIPCIÓN DEL PUESTO'
- categoria # (ejemplo: "07", "08", "T")
- salario_neto # Normalmente aparece como 'Importe Neto'
- total_percepciones # aparece a la derecha de 'Total percepciones'
- total_deducciones # aparece a la derecha de 'Total deducciones'
- periodo_inicio # Devuelve en formato "2025-12-25"
- periodo_fin # Devuelve en formato "2025-12-25"
- fecha_pago # Devuelve en formato "2025-12-25"
- periodicidad # (es la cantidad de días entre periodo_inicio y periodo_fin pero en palabra, ejemplo: "Quincenal", "Mensual") 
- error_lectura_nomina # Null por defecto

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_nomina" un "Documento sin coincidencias" 
"""

SEGUNDO_PROMPT_NOMINA = """
Esta imágen es de la primera página de un recibo de nómina, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- nombre # unicamente el nombre del empleado
- apellido_paterno # unicamente el primer apellido
- apellido_materno # unicamente el segundo apellido
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c", los primeros 10 caracteres del rfc y curp son iguales
- curp # es un código de 4 letras, 6 números, 6 letras y 2 números
- error_lectura_nomina # Null por defecto

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_nomina" un "Documento sin coincidencias" 
"""

PROMPT_ESTADO_CUENTA = """
Estas son las primeras 2 páginas de un recibo de cuenta, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- clabe # puede iniciar con 0 el número de cuenta clabe del usuario/cliente, puede aparecer como 'No. cuenta CLABE', extraelo todo
- nombre_usuario # el nombre del usuario/cliente
- rfc # captura el que esté cerca del nombre, normalmente aparece como "r.f.c"
- numero_cuenta # el número de cuenta, puede aparecer como 'No. de Cuenta'
- error_lectura_estado # Null por defecto

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

PROMPT_COMPROBANTE = """
Esta imágen es de la primera página de un comprobante de domicilio, pueden venir gráficos o tablas.

En caso de que reconozcas gráficos, extrae únicamente los valores que aparecen en la leyenda numerada.

Extrae los siguientes campos si los ves y devuelve únicamente un JSON, cumpliendo estas reglas:

- Los valores tipo string deben estar completamente en MAYÚSCULAS.
- Los valores numéricos deben devolverse como número sin símbolos ni comas (por ejemplo, "$31,001.00" debe devolverse como 31001.00).
- Si hay varios RFC, el válido es el que aparece junto al nombre y dirección del cliente.

Campos a extraer:

- domicilio # el domicilio completo, normalmente está junto al nombre del cliente
- inicio_periodo # inicio del periodo facturado en formato "2025-12-25"
- fin_periodo # fin del periodo facturado en formato "2025-12-25"

Ignora cualquier otra parte del documento. No infieras ni estimes valores.
En caso de no encontrar ninguna similitud, coloca Null en todas y al final retorna en "error_lectura_estado" un "Documento sin coincidencias" 
"""

# ---- PATRONES REGEX ----
# Diccionario de regex para RFC y CURP por tipo de documento
PATTERNS_COMPILADOS_RFC_CURP: Dict[str, Dict[str, re.Pattern]] = {
    "RFC": {
        "nomina": re.compile(r"r\.?f\.?c\.?\s+([a-zñ&]{3,4}\d{6}[a-z0-9]{3})"),
        "estado": re.compile(r"r\.?f\.?c\.?:\s+([a-zñ&]{3,4}\d{6}[a-z0-9]{3})"),
    },
    "CURP": {
        "nomina": re.compile(r"curp:\s*([a-z]{4}\d{6}[hm][a-z]{5}\d{2})"),
        "estado": re.compile(r"curp:\s*([a-z]{4}\d{6}[hm][a-z]{5}\d{2})"),  # si aplica para estado
    }
}

CAMPOS_STR = [
    "nombre", "rfc", "curp", "dependencia", "secretaria", "numero_empleado", "puesto_cargo", "categoria", "periodo_inicio", "periodo_fin",
    "fecha_pago", "periodicidad", "clabe", "nombre_usuario", "numero_cuenta", "domicilio", "inicio_periodo", "fin_periodo", "banco",
    "nombre_cliente", "clabe_interbancaria", "apellido_paterno", "apellido_materno"
]

CAMPOS_FLOAT = [
    "salario_neto", "total_percepciones", "total_deducciones", "saldo_promedio", "comisiones", "depositos", "cargos", "depositos_en_efectivo", "entradas_TPV_bruto", "entradas_TPV_neto"
]