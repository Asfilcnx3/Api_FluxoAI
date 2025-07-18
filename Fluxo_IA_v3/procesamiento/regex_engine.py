from .auxiliares import construir_descripcion, normalizar_fecha_es
from .auxiliares import EXPRESIONES_REGEX
from typing import List, Dict, Any
import re

def sumar_lista_montos(montos: List[str]) -> float:
    """
    Convierte una lista de montos en formato de cadena a float y los suma.

    Args:
        montos (List[str]): Lista de montos a sumar.

    Returns:
        float: La suma de los montos.
    """
    total = 0.0
    for monto in montos:
        monto_limpio = monto.replace(',', '').strip()
        try:
            total += float(monto_limpio)
        except ValueError:
            continue
    return total

def promediar_lista_montos(montos: List[str]) -> float:
    """
    Convierte una lista de montos en formato de cadena a float y los promedia.

    Args:
        montos (List[str]): Lista de montos a promediar.

    Returns:
        float: El promedio de los montos.
    """
    total = 0.0
    count = 0
    for monto in montos:
        monto_limpio = monto.replace(',', '').strip()
        try:
            total += float(monto_limpio)
            count += 1
        except ValueError:
            continue
    return total / count

def extraer_unico(d: dict, clave: str):
    """
    Busca las claves dentro del diccionario de encontradas y devuelve el primero en forma única

    Args:
        d (dict): diccionario de regex encontradas 
        clave (str): clave a encontrar

    returns:
        str: primer coincidencia encontrada

    """
    lista = d.get(clave, [])
    return lista[0] if lista else None


def procesar_regex_generico(banco: str, texto:str) -> Dict[str, Any]:
    """
    Aplica expresiones regulares definidas por banco y retorna resultados.

    Args:
        banco (str): El nombre del banco.
        texto (str): El texto a procesar.

    Returns:
        Dict[str, Any]: Un diccionario con los resultados.
    """
    config = EXPRESIONES_REGEX.get(banco)
    if not config:
        return {"error": f"No hay configuración para el banco '{banco}'."}

    datos_crudos = {}
    for clave, patron in config.items():
        datos_crudos[clave] = re.findall(patron, texto)

    resultados = {"banco": banco}

    # Extraemos las coincidencias únicas
    resultados["rfc"] = extraer_unico(datos_crudos, "rfc")
    resultados["nombre_cliente"] = extraer_unico(datos_crudos, "nombre_cliente")
    resultados["clabe_inter"] = extraer_unico(datos_crudos, "clabe_inter")

    # Procesar periodos
    periodo_matches = datos_crudos.get("periodo", [])
    if periodo_matches:
        if banco in ["Banregio", "Banamex"]:
            # Formato: ('01', '28', 'febrero', '2025')
            inicio, _, mes1, anio1 = periodo_matches[0]
            _, fin, mes2, anio2 = periodo_matches[-1]
            resultados["periodo_inicio"] = normalizar_fecha_es(f"{inicio} de {mes1} de {anio1}")
            resultados["periodo_fin"] = normalizar_fecha_es(f"{fin} de {mes2} de {anio2}")
            
        elif banco == "BanBajío":
            # Formato: ('1 de febrero', '28 de febrero', '2025')
            inicio, _, anio1 = periodo_matches[0]
            _, fin, anio2 = periodo_matches[-1]
            resultados["periodo_inicio"] = normalizar_fecha_es(f"{inicio} de {anio1}")
            resultados["periodo_fin"] = normalizar_fecha_es(f"{fin} de {anio2}")

        else:
            # Formato ('1/feb/2025', '28/feb/2025') o similares
            resultados["periodo_inicio"] = normalizar_fecha_es(periodo_matches[0][0])
            resultados["periodo_fin"] = normalizar_fecha_es(periodo_matches[-1][1])


    resultados['total_comisiones'] = sumar_lista_montos(datos_crudos.get('comisiones', []))
    resultados['total_depositos'] = sumar_lista_montos(datos_crudos.get('depositos', []))
    resultados['total_cargos'] = sumar_lista_montos(datos_crudos.get('cargos', []))
    resultados['saldo_promedio'] = promediar_lista_montos(datos_crudos.get('saldo_promedio', []))

    # Creamos un for para encontrar todas las coincidencias en la lista de posibles descripciones
    regex_claves = [
        "descripcion",
        "descripcion_clip_multilinea",
        "descripcion_clip_traspaso",
        "descripcion_amex_multilinea"
    ]

    transacciones_matches = []
    for clave in regex_claves:
        if clave in datos_crudos:
            transacciones_matches += datos_crudos[clave]

    transacciones_filtradas = []
    total_entradas = 0

    if transacciones_matches:
        for transaccion in transacciones_matches:
            # Función auxiliar
            descripcion, monto_str = construir_descripcion(transaccion, banco)

            if "comision" not in descripcion and "iva" not in descripcion:
                total_entradas += sumar_lista_montos([monto_str])
                transacciones_filtradas.append({
                    "fecha": transaccion[0],
                    "descripcion": descripcion.strip(),
                    "monto": monto_str
                })

    resultados["entradas_TPV_bruto"] = total_entradas
    resultados["entradas_TPV_neto"] = total_entradas - resultados["total_comisiones"]
    resultados["transacciones"] = transacciones_filtradas

    return resultados