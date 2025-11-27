import io
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, NamedStyle
from typing import Dict, Any

def generar_excel_reporte(data_json: Dict[str, Any]) -> bytes:
    """
    Genera un archivo Excel (.xlsx) con 4 pestañas:
    1. Resumen General
    2. Resumen Portadas (Datos de carátula)
    3. Transacciones TPV (Detalle)
    4. Resumen por Cuenta (Formato CSV)
    """
    wb = Workbook()
    
    # --- ESTILOS ---
    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill(start_color="4F81BD", end_color="4F81BD", fill_type="solid")
    
    # Estilo de moneda para celdas numéricas
    currency_style = NamedStyle(name='currency_style', number_format='$#,##0.00')

    def aplicar_estilo_header(ws):
        for cell in ws[1]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal='center')

    # ==========================================
    # 1. PESTAÑA: RESUMEN GENERAL
    # ==========================================
    ws1 = wb.active
    ws1.title = "Resumen General"
    
    ws1.append(["Métrica", "Valor"])
    
    total_dep = data_json.get("total_depositos", 0.0)
    es_mayor = "SÍ" if data_json.get("es_mayor_a_250") else "NO"
    num_docs = len(data_json.get("resultados_individuales", []))
    
    ws1.append(["Total Depósitos Calculados", total_dep])
    ws1.append(["¿Es Mayor a 250k?", es_mayor])
    ws1.append(["Documentos Procesados", num_docs])
    
    # Formato moneda a la celda B2
    ws1['B2'].style = currency_style
    
    aplicar_estilo_header(ws1)
    ws1.column_dimensions['A'].width = 30
    ws1.column_dimensions['B'].width = 25

    # ==========================================
    # 2. PESTAÑA: RESUMEN PORTADAS (NUEVA)
    # ==========================================
    ws2 = wb.create_sheet("Resumen Portadas")
    
    headers_portadas = [
        "Banco", "RFC", "Cliente", "CLABE / Cuenta", 
        "Periodo Inicio", "Periodo Fin", 
        "Depósitos", "Cargos", "Saldo Promedio", "Comisiones"
    ]
    ws2.append(headers_portadas)
    
    resultados = data_json.get("resultados_individuales", [])
    
    for res in resultados:
        ia = res.get("AnalisisIA") or {}
        
        # Validación segura de datos
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
    
    # Ajustar anchos y formato de moneda
    for col in ['A', 'B', 'C', 'D']:
        ws2.column_dimensions[col].width = 25
    
    # Aplicar formato de moneda a las columnas de montos (G, H, I, J)
    for row in ws2.iter_rows(min_row=2, min_col=7, max_col=10):
        for cell in row:
            cell.style = currency_style

    # ==========================================
    # 3. PESTAÑA: DETALLE TRANSACCIONES TPV
    # ==========================================
    ws3 = wb.create_sheet("Transacciones TPV")
    ws3.append(["Banco", "Fecha", "Descripción", "Monto", "Tipo"])
    
    for res in resultados:
        ia = res.get("AnalisisIA") or {}
        banco_nom = ia.get("banco", "Desconocido")
        
        detalle = res.get("DetalleTransacciones", {})
        transacciones = detalle.get("transacciones", [])
        
        if isinstance(transacciones, list):
            for tx in transacciones:
                try:
                    monto_val = float(str(tx.get("monto", "0")).replace(",", ""))
                except:
                    monto_val = 0.0

                ws3.append([
                    banco_nom,
                    tx.get("fecha", ""),
                    tx.get("descripcion", ""),
                    monto_val,
                    tx.get("tipo", "")
                ])
                
    aplicar_estilo_header(ws3)
    ws3.column_dimensions['C'].width = 60
    
    # Formato moneda a columna D (Monto)
    for row in ws3.iter_rows(min_row=2, min_col=4, max_col=4):
        for cell in row:
            cell.style = currency_style

    # ==========================================
    # 4. PESTAÑA: RESUMEN POR CUENTA
    # ==========================================
    ws4 = wb.create_sheet("Resumen por Cuenta")
    encabezados_resumen = [
        "Mes", "Cuenta", "Depósitos", "Cargos", "TPV Bruto", 
        "Financiamientos", "Efectivo", "Traspaso entre cuentas", "BMR CASH"
    ]
    ws4.append(encabezados_resumen)
    
    for res in resultados:
        ia = res.get("AnalisisIA") or {}
        if not ia: continue
        
        periodo = ia.get("periodo_fin") or ia.get("periodo_inicio") or "Desc."
        banco = ia.get("banco", "BANCO")
        clabe = ia.get("clabe_interbancaria", "")
        cuenta_str = f"{banco}-{clabe[-4:]}" if len(clabe) >= 4 else banco
        
        ws4.append([
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

    aplicar_estilo_header(ws4)
    ws4.column_dimensions['B'].width = 25
    
    # Formato moneda a columnas C a I
    for row in ws4.iter_rows(min_row=2, min_col=3, max_col=9):
        for cell in row:
            cell.style = currency_style

    # --- GUARDAR EN BYTES ---
    output = io.BytesIO()
    wb.save(output)
    return output.getvalue()