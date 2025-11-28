import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
from typing import Dict, Any, List

from ..utils.helpers_texto_fluxo import (
    PALABRAS_EXCLUIDAS, PALABRAS_EFECTIVO, PALABRAS_TRASPASO_ENTRE_CUENTAS, 
    PALABRAS_TRASPASO_FINANCIAMIENTO, PALABRAS_BMRCASH
)

def generar_excel_reporte(data_json: Dict[str, Any]) -> bytes:
    """
    Genera un archivo Excel (.xlsx) reorganizado según requerimientos del cliente.
    """
    wb = Workbook()
    
    # --- ESTILOS ---
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    currency_style = NamedStyle(name='currency_style', number_format='$#,##0.00')

    def aplicar_estilo_header(ws):
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

    resultados = data_json.get("resultados_individuales", [])

    # ==========================================
    # 1. PESTAÑA: RESUMEN POR CUENTA (Antes la 4, ahora la 1)
    # ==========================================
    ws1 = wb.active
    ws1.title = "Resumen por Cuenta"
    
    encabezados_resumen = [
        "Mes", "Cuenta", "Depósitos", "Cargos", "TPV Bruto", 
        "Financiamientos", "Efectivo", "Traspaso entre cuentas", "BMR CASH"
    ]
    ws1.append(encabezados_resumen)
    
    for res in resultados:
        ia = res.get("AnalisisIA") or {}
        if not ia: continue
        
        periodo = ia.get("periodo_fin") or ia.get("periodo_inicio") or "Desc."
        banco = ia.get("banco", "BANCO")
        clabe = ia.get("clabe_interbancaria", "")
        cuenta_str = f"{banco}-{clabe[-4:]}" if len(clabe) >= 4 else banco
        
        ws1.append([
            periodo,
            cuenta_str,
            ia.get("depositos", 0.0),
            ia.get("cargos", 0.0),
            ia.get("entradas_TPV_bruto", 0.0),
            ia.get("total_entradas_financiamiento", 0.0),
            ia.get("depositos_en_efectivo", 0.0),
            ia.get("traspaso_entre_cuentas", 0.0),
            ia.get("entradas_bmrcash", 0.0)
        ])

    aplicar_estilo_header(ws1)
    ws1.column_dimensions['B'].width = 25
    for row in ws1.iter_rows(min_row=2, min_col=3, max_col=9):
        for cell in row:
            cell.style = currency_style

    # ==========================================
    # 2. PESTAÑA: RESUMEN PORTADAS
    # ==========================================
    ws2 = wb.create_sheet("Resumen Portadas")
    headers_portadas = [
        "Banco", "RFC", "Cliente", "CLABE / Cuenta", 
        "Periodo Inicio", "Periodo Fin", 
        "Depósitos", "Cargos", "Saldo Promedio", "Comisiones"
    ]
    ws2.append(headers_portadas)
    
    for res in resultados:
        ia = res.get("AnalisisIA") or {}
        ws2.append([
            ia.get("banco", "Desconocido"),
            ia.get("rfc", ""),
            ia.get("nombre_cliente", ""),
            ia.get("clabe_interbancaria", ""),
            ia.get("periodo_inicio", ""),
            ia.get("periodo_fin", ""),
            ia.get("depositos", 0.0),
            ia.get("cargos", 0.0),
            ia.get("saldo_promedio", 0.0),
            ia.get("comisiones", 0.0)
        ])
    
    aplicar_estilo_header(ws2)
    for col in ['A', 'B', 'C', 'D']: ws2.column_dimensions[col].width = 25
    for row in ws2.iter_rows(min_row=2, min_col=7, max_col=10):
        for cell in row: cell.style = currency_style

    # ==========================================
    # HELPER PARA PESTAÑAS DE DETALLE
    # ==========================================
    def crear_hoja_detalle(nombre_hoja, criterio_filtro_func):
        ws = wb.create_sheet(nombre_hoja)
        ws.append(["Banco", "Fecha", "Descripción", "Monto", "Tipo"])
        
        for res in resultados:
            ia = res.get("AnalisisIA") or {}
            banco_nom = ia.get("banco", "Desconocido")
            detalle = res.get("DetalleTransacciones", {})
            transacciones = detalle.get("transacciones", [])
            
            if isinstance(transacciones, list):
                for tx in transacciones:
                    descripcion = str(tx.get("descripcion", "")).lower()
                    
                    # Aplicamos el filtro específico para esta hoja
                    if criterio_filtro_func(descripcion):
                        try:
                            monto_val = float(str(tx.get("monto", "0")).replace(",", ""))
                        except:
                            monto_val = 0.0

                        ws.append([
                            banco_nom,
                            tx.get("fecha", ""),
                            tx.get("descripcion", ""),
                            monto_val,
                            tx.get("tipo", "")
                        ])
        
        aplicar_estilo_header(ws)
        ws.column_dimensions['C'].width = 60
        for row in ws.iter_rows(min_row=2, min_col=4, max_col=4):
            for cell in row: cell.style = currency_style

    # ==========================================
    # PESTAÑAS 3-7: DETALLES DESGLOSADOS
    # ==========================================
    
    # 3. Transacciones TPV (Todo lo que NO sea efectivo, traspaso, financiamiento o bmr)
    def filtro_tpv(desc):
        return not (
            any(p in desc for p in PALABRAS_EFECTIVO) or
            any(p in desc for p in PALABRAS_TRASPASO_ENTRE_CUENTAS) or
            any(p in desc for p in PALABRAS_TRASPASO_FINANCIAMIENTO) or
            any(p in desc for p in PALABRAS_BMRCASH)
        )
    crear_hoja_detalle("Transacciones TPV", filtro_tpv)

    # 4. Efectivo
    crear_hoja_detalle("Efectivo", lambda desc: any(p in desc for p in PALABRAS_EFECTIVO))

    # 5. Financiamientos
    crear_hoja_detalle("Financiamientos", lambda desc: any(p in desc for p in PALABRAS_TRASPASO_FINANCIAMIENTO))

    # 6. Traspaso entre Cuentas
    crear_hoja_detalle("Traspaso entre Cuentas", lambda desc: any(p in desc for p in PALABRAS_TRASPASO_ENTRE_CUENTAS))

    # 7. BMRCASH
    crear_hoja_detalle("BMRCASH", lambda desc: any(p in desc for p in PALABRAS_BMRCASH))

    # ==========================================
    # 8. PESTAÑA: RESUMEN GENERAL (Ahora la última)
    # ==========================================
    ws_final = wb.create_sheet("Resumen General")
    ws_final.append(["Métrica", "Valor"])
    
    total_dep = data_json.get("total_depositos", 0.0)
    es_mayor = "SÍ" if data_json.get("es_mayor_a_250") else "NO"
    num_docs = len(data_json.get("resultados_individuales", []))
    
    ws_final.append(["Total Depósitos Calculados", total_dep])
    ws_final.append(["¿Es Mayor a 250k?", es_mayor])
    ws_final.append(["Documentos Procesados", num_docs])
    
    ws_final['B2'].style = currency_style
    aplicar_estilo_header(ws_final)
    ws_final.column_dimensions['A'].width = 30
    ws_final.column_dimensions['B'].width = 25

    # --- GUARDAR ---
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()