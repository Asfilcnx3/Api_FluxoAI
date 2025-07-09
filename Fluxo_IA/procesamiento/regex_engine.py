from .auxiliares import construir_descripcion, normalizar_fecha_es
from .auxiliares import EXPRESIONES_REGEX
from typing import List, Dict, Any
import re

def sumar_lista_montos(montos: List[str]) -> float:
    total = 0.0
    for monto in montos:
        monto_limpio = monto.replace(',', '').strip()
        try:
            total += float(monto_limpio)
        except ValueError:
            continue
    return total

def procesar_regex_generico(banco: str, texto:str) -> Dict[str, Any]:
    config = EXPRESIONES_REGEX.get(banco)
    if not config:
        return {"error": f"No hay configuración de regex para el banco '{banco}'."}

    datos_crudos = {}
    for clave, patron in config.items():
        datos_crudos[clave] = re.findall(patron, texto)

    resultados = {"banco": banco}

    periodo_matches = datos_crudos.get("periodo", [])
    if periodo_matches:
        if banco == "BanBajío":
            inicio, _, anio1 = periodo_matches[0]
            _, fin, anio2 = periodo_matches[-1]
            resultados["periodo_inicio"] = normalizar_fecha_es(f"{inicio} de {anio1}")
            resultados["periodo_fin"] = normalizar_fecha_es(f"{fin} de {anio2}")

        elif banco == "Banregio":
            inicio, _, mes1, anio1 = periodo_matches[0]
            _, fin, mes2, anio2 = periodo_matches[-1]
            resultados["periodo_inicio"] = normalizar_fecha_es(f"{inicio} de {mes1} de {anio1}")
            resultados["periodo_fin"] = normalizar_fecha_es(f"{fin} de {mes2} de {anio2}")

        else:
            resultados["periodo_inicio"] = normalizar_fecha_es(periodo_matches[0][0])
            resultados["periodo_fin"] = normalizar_fecha_es(periodo_matches[-1][1])

    resultados['total_comisiones'] = sumar_lista_montos(datos_crudos.get('comisiones', []))
    resultados['total_depositos'] = sumar_lista_montos(datos_crudos.get('depositos', []))
    resultados['total_cargos'] = sumar_lista_montos(datos_crudos.get('cargos', []))
    resultados['saldo_promedio'] = sumar_lista_montos(datos_crudos.get('saldo_promedio', []))

    transacciones_matches = datos_crudos.get("descripcion", [])
    transacciones_filtradas = []
    total_entradas = 0

    if transacciones_matches:
        for transaccion in transacciones_matches:
            descripcion, monto_str = construir_descripcion(transaccion, banco)

            if "comision" not in descripcion:
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