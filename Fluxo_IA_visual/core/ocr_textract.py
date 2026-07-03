# core/ocr_textract.py

import os
import json
import logging
import cv2
import numpy as np
import boto3
import re
from typing import List, Dict, Any

from .config import settings

logger = logging.getLogger("MotorTextract")

class MotorTextractOCR:
    # --- FLAGS DE DEPURACIÓN ---
    LOG_AWS = 1                 # Logs de llamadas a API y Caché
    LOG_STITCHING = 2           # Logs de unión de bloques (Pasada 1)
    LOG_CARRILES = 3            # Logs de detección geométrica (Pasada 2)
    LOG_TRANSACCIONES = 4       # Logs de extracción y reglas (Pasada 3)

    def __init__(self, debug_flags: List[int] = None, banco: str = "ESTANDAR", cache_dir: str = None):
        """
        :param debug_flags: Lista de enteros con las secciones a detallar.
        :param banco: Nombre del banco para bifurcar reglas deterministas.
        :param cache_dir: Ruta de la carpeta donde se guardarán/leerán los JSON de AWS (solo para el auditor).
        """
        self.debug_flags = debug_flags or []
        self.banco = banco.upper()
        self.cache_dir = cache_dir
        self._textract_client = None

        if self.cache_dir:
            os.makedirs(self.cache_dir, exist_ok=True)

        # ==========================================
        # BIFURCACIÓN DE REGLAS POR BANCO (REGEX)
        # ==========================================
        if self.banco == "BANORTE":
            self.rx_fecha = re.compile(
                r'^(\d{2}/\d{2}/\d{4}|\d{2}-[a-zA-Z]{3}-\d{2,4})|^(0[1-9]|[12]\d|3[01])(?=\s|$)', 
                re.IGNORECASE
            )
        elif self.banco == "SANTANDER":
            self.rx_fecha = re.compile(
                r'^(\d{2}-[a-zA-Z]{3}-\d{2,4})|^(0[1-9]|[12]\d|3[01])(?=\s|$)', 
                re.IGNORECASE
            )
        else:
            self.rx_fecha = re.compile(
                r'^(\d{2}/\d{2}/\d{4}|0[1-9]|[12]\d|3[01])(?=\s|$)'
            )
        
        # FIX: Permite espacios erróneos en los miles que a veces AWS Textract lee
        self.rx_monto = re.compile(r'[+-]?\$?\s*\d{1,3}(?:[,\s]\d{3})*\.\d{2}')
        
        # FIX: Añadimos cabeceras de tabla para que las evapore
        self.triggers_basura = [
            "ESTE DOCUMENTO ES UNA REPRESENTACIÓN", "SELLO DIGITAL", "CADENA ORIGINAL", 
            "IPAB", "FONDOS DE INVERSION", "SUMA DE RETIROS", "DETALLES DEL CRÉDITO", 
            "SALDO A FECHA DE CORTE", "COMPROBANTE FISCAL", "FOLIO FISCAL",
            "BANCA MIFEL, S.A", "WWW.MIFEL.COM.MX", "RÉGIMEN FISCAL", "ESTADO DE CUENTA", 
            "CUENTA A LA VISTA", "PÁGINA", "PAGINA", "RFC:", "PROTECCIÓN PARA LA",
            "INSTITUTO AL AHORRO", "REFERENCIA DE ABREVIATURAS", "MENSAJES IMPORTANTES",
            "ACLARACIONES", "CONDUSEF", "INFORMACION IMPORTANTE",
            "RETIRO/CARGO", "DEPÓSITO/ABONO", "SALDO PROMEDIO",
            
            # PALABRAS PARA DESTRUIR RESÚMENES Y TABLAS CODI <---
            "SALDO FINAL", "SALDO INICIAL", "OTROS CARGOS", "OTROS ABONOS", 
            "OPERACIÓN PROCESADA POR CODI", "CONCEPTO DEL MONTO"
        ]

    def _log_debug(self, flag: int, message: str):
        """Imprime logs internos SOLO si el flag está activo."""
        if flag in self.debug_flags:
            logger.info(f"[OCR-DEBUG-{flag}] {message}")

    def _get_aws_client(self):
        if not self._textract_client:
            self._textract_client = boto3.client(
                'textract',
                aws_access_key_id=settings.AWS_ACCESS_KEY_ID.get_secret_value(),
                aws_secret_access_key=settings.AWS_SECRET_ACCESS_KEY.get_secret_value(),
                region_name=settings.AWS_REGION_TEXTRACT
            )
        return self._textract_client

    def _limpiar_imagen_para_ocr(self, imagen_pil) -> np.ndarray:
        """Aplica filtros de OpenCV (Tomado directo de tu POC)."""
        img_np = np.array(imagen_pil)
        img_cv = cv2.cvtColor(img_np, cv2.COLOR_RGB2BGR)
        gris = cv2.cvtColor(img_cv, cv2.COLOR_BGR2GRAY)
        limpia = cv2.adaptiveThreshold(
            gris, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 21, 15
        )
        kernel = np.ones((1, 1), np.uint8)
        limpia = cv2.morphologyEx(limpia, cv2.MORPH_CLOSE, kernel)
        return limpia

    # =========================================================================
    # AWS Y CACHÉ (El salvavidas del presupuesto)
    # =========================================================================
    def fetch_aws_data(self, imagen_pil, doc_id: str, page_num: int) -> dict:
        """
        Intenta leer de la caché local. Si no existe o no hay cache_dir, llama a AWS.
        """
        cache_file = None
        if self.cache_dir:
            # Creamos un nombre de archivo único por documento y página
            cache_file = os.path.join(self.cache_dir, f"aws_cache_{doc_id}_p{page_num}.json")
            if os.path.exists(cache_file):
                self._log_debug(self.LOG_AWS, f"Pág {page_num}: Recuperando JSON crudo de CACHÉ LOCAL.")
                with open(cache_file, 'r', encoding='utf-8') as f:
                    return json.load(f)

        self._log_debug(self.LOG_AWS, f"Pág {page_num}: Llamando a API de AWS Textract...")
        img_procesada = self._limpiar_imagen_para_ocr(imagen_pil)
        
        exito, buffer = cv2.imencode('.jpg', img_procesada)
        if not exito:
            raise ValueError(f"Pág {page_num}: Error al codificar imagen a JPG en memoria.")
        
        client = self._get_aws_client()
        respuesta_aws = client.detect_document_text(Document={'Bytes': buffer.tobytes()})

        # Guardar en caché si está habilitado
        if cache_file:
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(respuesta_aws, f, ensure_ascii=False)
                self._log_debug(self.LOG_AWS, f"Pág {page_num}: Respuesta de AWS guardada en caché.")

        return respuesta_aws

    # =========================================================================
    # PASADA 1: PARSEO Y STITCHING (CON ESCUDO ANTI-CAJAS VERTICALES)
    # =========================================================================
    def pass_1_parse_and_stitch(self, respuesta_aws: dict, umbral_interseccion: float = 0.4) -> List[Dict]:
        self._log_debug(self.LOG_STITCHING, "Iniciando Pasada 1: Parseo sin efecto bola de nieve y sin cajas verticales.")
        
        lineas_extraidas = []
        for bloque in respuesta_aws.get('Blocks', []):
            if bloque['BlockType'] == 'LINE':
                geo = bloque['Geometry']['BoundingBox']
                
                # --- FIX: EL ESCUDO ANTI-CAJAS GIGANTES/VERTICALES ---
                # Si la caja mide más del 3.5% del alto de la página (aprox 1cm de alto), 
                # o si es más alta que ancha, es texto vertical en el margen. ¡Afuera!
                if geo['Height'] > 0.035 or geo['Height'] > (geo['Width'] * 1.5):
                    self._log_debug(self.LOG_STITCHING, f"Ignorando texto vertical/gigante: '{bloque['Text']}' (Height: {geo['Height']:.4f})")
                    continue
                    
                lineas_extraidas.append({
                    'texto': bloque['Text'],
                    'confianza': bloque['Confidence'],
                    'top': geo['Top'],
                    'bottom': geo['Top'] + geo['Height'],
                    'left': geo['Left'],
                    'right': geo['Left'] + geo['Width']
                })
                
        lineas_extraidas.sort(key=lambda x: x['top'])
        
        filas_reconstruidas = []
        fila_actual = []
        ancla_top = None
        ancla_bottom = None
        
        for linea in lineas_extraidas:
            if not fila_actual:
                fila_actual.append(linea)
                ancla_top = linea['top']
                ancla_bottom = linea['bottom']
                continue
                
            overlap_top = max(ancla_top, linea['top'])
            overlap_bottom = min(ancla_bottom, linea['bottom'])
            overlap_height = max(0, overlap_bottom - overlap_top)
            altura_linea = linea['bottom'] - linea['top']
            
            # Evitar división por cero por si AWS manda una caja con altura 0
            ratio = overlap_height / altura_linea if altura_linea > 0 else 0
            
            if ratio >= umbral_interseccion:
                fila_actual.append(linea)
            else:
                fila_actual.sort(key=lambda x: x['left'])
                texto_unido = " | ".join([item['texto'] for item in fila_actual])
                self._log_debug(self.LOG_STITCHING, f"Fila armada: {texto_unido[:60]}...")
                
                filas_reconstruidas.append({
                    "texto_unido": texto_unido,
                    "bloques": fila_actual
                })
                
                fila_actual = [linea]
                ancla_top = linea['top']
                ancla_bottom = linea['bottom']
                
        if fila_actual:
            fila_actual.sort(key=lambda x: x['left'])
            filas_reconstruidas.append({
                "texto_unido": " | ".join([item['texto'] for item in fila_actual]),
                "bloques": fila_actual
            })
            
        self._log_debug(self.LOG_STITCHING, f"Pasada 1 terminada. Total de filas: {len(filas_reconstruidas)}")
        return filas_reconstruidas

    # =========================================================================
    # MÉTODOS AUXILIARES (DETERMINISTAS)
    # =========================================================================
    def _limpiar_monto(self, texto: str) -> float:
        match = self.rx_monto.search(texto)
        if match:
            try:
                limpio = match.group(0).replace('$', '').replace(',', '').strip()
                return float(limpio)
            except ValueError:
                return 0.0
        return 0.0

    def _asignar_columna_monto(self, x_obj: float, carriles: Dict[str, float], margen: float = 0.08) -> str:
        distancias = {
            "retiro": abs(x_obj - carriles.get("retiro", 999)),
            "deposito": abs(x_obj - carriles.get("deposito", 999)),
            "saldo": abs(x_obj - carriles.get("saldo", 999))
        }
        mejor_columna = min(distancias, key=distancias.get)
        if distancias[mejor_columna] <= margen:
            return mejor_columna
        return None

    def _evaluar_estado_tabla(self, texto_limpio: str, indice_fila: int, filas_estructuradas: List[Dict]) -> str:
        score_enviados = 0
        score_recibidos = 0
        
        if any(k in texto_limpio for k in ["SPEI", "SPEL", "TRANSFERENCIA", "TRASPASO"]):
            score_enviados += 1
            score_recibidos += 1
            
        if any(k in texto_limpio for k in ["ENVIAD", "SALIDA", "RETIRO", "EMITID"]):
            score_enviados += 2
        if any(k in texto_limpio for k in ["RECIBID", "ENTRADA", "DEPOSITO", "COBRANZA"]):
            score_recibidos += 2
            
        if "DETALLEDEMOVIMIENTOS" in texto_limpio and "SPEI" not in texto_limpio:
            return "PRINCIPAL"
        if any(k in texto_limpio for k in ["DETALLESDELCREDITO", "DETALLESDELCRÉDITO", "INVERSIONES", "POSICIÓN", "RESUMENFISCAL", "CREDITO"]):
            return "OTRAS_TABLAS"

        if score_enviados == 0 and score_recibidos == 0:
            return None

        montos_por_fila = []
        filas_futuras = filas_estructuradas[indice_fila + 1 : indice_fila + 6]
        
        for f in filas_futuras:
            montos = [b for b in f["bloques"] if self.rx_monto.search(b['texto'].strip())]
            if len(montos) > 0:
                montos_por_fila.append(len(montos))
                
        if montos_por_fila:
            if all(cantidad == 1 for cantidad in montos_por_fila):
                score_enviados += 2
                score_recibidos += 2
            elif any(cantidad >= 2 for cantidad in montos_por_fila):
                score_enviados -= 3
                score_recibidos -= 3

        UMBRAL = 3
        if score_enviados >= UMBRAL and score_enviados > score_recibidos:
            return "SPEI_ENVIADOS"
        elif score_recibidos >= UMBRAL and score_recibidos > score_enviados:
            return "SPEI_RECIBIDOS"
            
        return None
    
    # =========================================================================
    # PASADA 2: DETECCIÓN DE CARRILES (Clustering 1D Blindado)
    # =========================================================================
    def pass_2_detect_lanes(self, filas_estructuradas: List[Dict]) -> Dict[str, float]:
        self._log_debug(self.LOG_CARRILES, "Iniciando Pasada 2: Detección de Carriles...")
        coordenadas_dinero = []
        
        for fila in filas_estructuradas[:150]: 
            for bloque in fila["bloques"]:
                txt_limpio = bloque['texto'].strip()
                # FIX 1: Ignorar la mitad izquierda de la página (left < 0.35)
                # El dinero siempre está de la mitad hacia la derecha.
                if self.rx_monto.search(txt_limpio) and bloque['left'] > 0.35:
                    coordenadas_dinero.append(bloque['left'])
                    
        if len(coordenadas_dinero) < 10:
            self._log_debug(self.LOG_CARRILES, "Pocos montos. Aplicando carriles por defecto.")
            return {"retiro": 0.595, "deposito": 0.710, "saldo": 0.825}
            
        coordenadas_dinero.sort()
        
        grupos = []
        grupo_actual = [coordenadas_dinero[0]]
        
        # FIX 2: Anti-Chaining. Comparamos contra el inicio de la columna (grupo_actual[0])
        # Una columna de números no suele variar más de 0.06 en su justificación izquierda.
        for x in coordenadas_dinero[1:]:
            if x - grupo_actual[0] < 0.06: 
                grupo_actual.append(x)
            else:
                grupos.append(grupo_actual)
                grupo_actual = [x]
        grupos.append(grupo_actual)
        
        grupos.sort(key=len, reverse=True)
        top_grupos = grupos[:3]
        centros = sorted([sum(g) / len(g) for g in top_grupos])
        
        carriles = {}
        
        if self.banco in ["BANORTE", "SANTANDER"]:
            if len(centros) == 3:
                carriles["deposito"], carriles["retiro"], carriles["saldo"] = centros[0], centros[1], centros[2]
            elif len(centros) == 2:
                if centros[1] > 0.78: 
                    carriles["saldo"] = centros[1]
                    if centros[0] < 0.65: carriles["deposito"] = centros[0]
                    else: carriles["retiro"] = centros[0]
                else:
                    carriles["deposito"], carriles["retiro"] = centros[0], centros[1]
            
            carriles.setdefault("deposito", 0.595)
            carriles.setdefault("retiro", 0.710)
            carriles.setdefault("saldo", 0.825)
        else:
            if len(centros) == 3:
                carriles["retiro"], carriles["deposito"], carriles["saldo"] = centros[0], centros[1], centros[2]
            elif len(centros) == 2:
                if centros[1] > 0.78: 
                    carriles["saldo"] = centros[1]
                    if centros[0] < 0.65: carriles["retiro"] = centros[0]
                    else: carriles["deposito"] = centros[0]
                else:
                    carriles["retiro"], carriles["deposito"] = centros[0], centros[1]
            
            carriles.setdefault("retiro", 0.595)
            carriles.setdefault("deposito", 0.710)
            carriles.setdefault("saldo", 0.825)
                
        self._log_debug(self.LOG_CARRILES, f"Carriles adaptativos detectados ({self.banco}): {carriles}")
        return carriles

    # =========================================================================
    # PASADA 3: EXTRACCIÓN DETERMINISTA
    # =========================================================================
    def pass_3_extract_transactions(self, filas_estructuradas: List[Dict], carriles: Dict[str, float], saldo_inicial: float) -> List[Dict]:
        self._log_debug(self.LOG_TRANSACCIONES, f"Iniciando Pasada 3 con Saldo Inicial: ${saldo_inicial}")
        transacciones = []
        slice_actual = None
        saldo_arrastre = saldo_inicial
        seccion_actual = "PRINCIPAL"

        for i, fila in enumerate(filas_estructuradas):
            texto_unido_clean = fila["texto_unido"].upper().replace(" ", "").replace("_", "")
            
            if self.banco != "BANORTE":
                if any(k in texto_unido_clean for k in ["SPEI", "SPEL"]) and "RECIBID" in texto_unido_clean:
                    seccion_actual = "SPEI_RECIBIDOS"
                    continue
                elif any(k in texto_unido_clean for k in ["SPEI", "SPEL"]) and "ENVIAD" in texto_unido_clean:
                    seccion_actual = "SPEI_ENVIADOS"
                    continue
                elif "DETALLEDEMOVIMIENTOS" in texto_unido_clean and "SPEI" not in texto_unido_clean:
                    seccion_actual = "PRINCIPAL"
                    continue
            
            if any(basura.replace(" ", "") in texto_unido_clean for basura in [t.replace(" ", "") for t in self.triggers_basura]):
                continue 

            bloques = fila["bloques"]
            if not bloques: continue

            # DEBUG Opcional para las primeras filas
            if i < 20 and self.LOG_TRANSACCIONES in self.debug_flags:
                textos_bloques = [b['texto'].strip() for b in bloques[:4]]
                logger.debug(f"[TEXTRACT Fila {i}] Primeros bloques: {textos_bloques}")

            fecha_encontrada = None
            tiene_dinero = any(self.rx_monto.search(b['texto']) for b in bloques)
            
            # Buscamos en TODOS los bloques de la fila por si la fecha se desplazó
            for b in bloques: 
                txt_b = b['texto'].strip()
                match_fecha = self.rx_fecha.match(txt_b)
                if match_fecha:
                    fecha_encontrada = match_fecha.group(1) or match_fecha.group(2)
                    break
            
            if fecha_encontrada and tiene_dinero:
                if slice_actual:
                    tx_val, saldo_arrastre = self._consolidar_y_validar(slice_actual, carriles, saldo_arrastre)
                    if tx_val: transacciones.append(tx_val)
                
                slice_actual = {
                    "fecha": fecha_encontrada,
                    "seccion": seccion_actual,
                    "elementos": [b for b in bloques if b['texto'].strip() != fecha_encontrada] 
                }
            elif slice_actual:
                if len(slice_actual["elementos"]) < 40: 
                    slice_actual["elementos"].extend(bloques)

        if slice_actual:
            tx_val, saldo_arrastre = self._consolidar_y_validar(slice_actual, carriles, saldo_arrastre)
            if tx_val: transacciones.append(tx_val)

        self._log_debug(self.LOG_TRANSACCIONES, f"Pasada 3 completada. Transacciones crudas: {len(transacciones)}")
        return transacciones

    def _consolidar_y_validar(self, slice_data, carriles, saldo_arrastre):
        seccion = slice_data["seccion"]
        retiro_val = 0.0
        deposito_val = 0.0
        saldo_leido = None
        importe_generico = 0.0
        descripcion_tokens = []
        
        requiere_revision = False
        saldo_inferido = None

        for item in slice_data["elementos"]:
            txt = item['texto'].strip()
            if self.rx_monto.search(txt):
                monto_val = self._limpiar_monto(txt)
                
                if seccion == "PRINCIPAL":
                    columna = self._asignar_columna_monto(item['left'], carriles)
                    
                    # --- NUEVO LOG: RASTREO ESPACIAL DE TIPO ---
                    self._log_debug(self.LOG_TRANSACCIONES, f"[TRACK-TIPO-P3] Monto: ${monto_val} | X_Left: {item['left']:.4f} | Carriles: {carriles} -> Asignado a: {columna}")
                    
                    if columna == "retiro": retiro_val = monto_val
                    elif columna == "deposito": deposito_val = monto_val
                    elif columna == "saldo": saldo_leido = monto_val
                    else: descripcion_tokens.append(txt)
                else:
                    if monto_val > importe_generico:
                        importe_generico = monto_val
                    
                    # --- NUEVO LOG: RASTREO SPEI DE TIPO ---
                    self._log_debug(self.LOG_TRANSACCIONES, f"[TRACK-TIPO-P3] Monto: ${monto_val} en Zona SPEI -> Asignado a: {seccion}")
            else:
                descripcion_tokens.append(txt)

        importe_final = 0.0
        tipo_final = "IMPORTE"

        if seccion == "PRINCIPAL":
            if retiro_val > 0:
                importe_final = retiro_val
                tipo_final = "CARGO"
            elif deposito_val > 0:
                importe_final = deposito_val
                tipo_final = "ABONO"
                
            if saldo_leido is not None:
                saldo_esperado = round(saldo_arrastre - retiro_val + deposito_val, 2)
                if abs(saldo_esperado - saldo_leido) > 0.01:
                    requiere_revision = True
                    saldo_inferido = saldo_esperado
                    saldo_arrastre = saldo_esperado
                else:
                    saldo_arrastre = saldo_leido
            else:
                requiere_revision = True
                saldo_inferido = round(saldo_arrastre - retiro_val + deposito_val, 2)
                saldo_arrastre = saldo_inferido
        else:
            importe_final = importe_generico
            if seccion == "SPEI_RECIBIDOS": tipo_final = "ABONO"
            elif seccion == "SPEI_ENVIADOS": tipo_final = "CARGO"

        if importe_final == 0.0:
            return None, saldo_arrastre

        tx = {
            "fecha": slice_data["fecha"],
            "descripcion": " ".join(descripcion_tokens),
            "importe": importe_final,
            "tipo": tipo_final,
            "seccion": seccion
        }

        if requiere_revision:
            tx["requiere_revision"] = True
            tx["saldo_inferido"] = saldo_inferido

        # --- NUEVO LOG: RESUMEN ANTES DE PASAR A DEDUPLICACIÓN ---
        self._log_debug(self.LOG_TRANSACCIONES, f"[RESUMEN-P3] Fecha: {tx['fecha']} | Tipo: {tx['tipo']} | Monto: ${tx['importe']} | Desc: {tx['descripcion'][:30]}...")

        return tx, saldo_arrastre

    # =========================================================================
    # PASADA 4: DEDUPLICACIÓN
    # =========================================================================
    def pass_4_deduplicate(self, todas_las_transacciones: List[Dict]) -> List[Dict]:
        self._log_debug(self.LOG_TRANSACCIONES, "Iniciando Pasada 4: Deduplicación...")
        
        if self.banco == "BANORTE":
            for tx in todas_las_transacciones:
                tx.pop("seccion", None)
            todas_las_transacciones.sort(key=lambda x: x["fecha"])
            return todas_las_transacciones

        # Quitamos "pago" de ignoradas por si está suelto
        PALABRAS_IGNORADAS = {"de", "la", "el", "en", "por", "para", "un", "una", "spei", "envio", "transferencia", "cv", "sa", "banco"}

        def obtener_palabras_clave(texto: str) -> set:
            limpio = re.sub(r'[^\w\s]', ' ', str(texto).lower())
            return set(p for p in limpio.split() if len(p) > 2 and p not in PALABRAS_IGNORADAS)

        def extraer_dia(fecha_str: str) -> int:
            # Extrae el primer número que encuentre (ej. "17/04" -> 17, "Día 08" -> 8)
            match = re.search(r'\d+', str(fecha_str))
            return int(match.group()) if match else -99

        # --- FIX 1: Agregamos CGO y fragmentos de OCR a las keywords ---
        kw_transferencias = ["SPEI", "SPEL", "TRASPASO", "TRANSF", "TRANSFERENCIA", "PAGO", "PAGI", "PAGS", "CGO", "NETNM", "SOBRANTE"]
        
        padres_candidatos = [
            tx for tx in todas_las_transacciones 
            if tx.get("seccion") == "PRINCIPAL" 
            and any(k in tx.get("descripcion", "").upper() for k in kw_transferencias)
        ]
        
        padres_intocables = [
            tx for tx in todas_las_transacciones 
            if tx.get("seccion") == "PRINCIPAL" 
            and not any(k in tx.get("descripcion", "").upper() for k in kw_transferencias)
        ]
        
        hijos_recibidos = [tx for tx in todas_las_transacciones if tx.get("seccion") == "SPEI_RECIBIDOS"]
        hijos_enviados = [tx for tx in todas_las_transacciones if tx.get("seccion") == "SPEI_ENVIADOS"]
        hijos = hijos_recibidos + hijos_enviados
        
        self._log_debug(self.LOG_TRANSACCIONES, f"Padres Candidatos: {len(padres_candidatos)} | Hijos: {len(hijos)}")

        ids_hijos_fusionados = set()

        for hijo in hijos:
            dia_hijo = extraer_dia(hijo["fecha"])
            importe_hijo = float(hijo["importe"])
            palabras_hijo = obtener_palabras_clave(hijo["descripcion"])

            # --- FIX 2: Relajamos la fecha a +/- 2 días por desfase bancario ---
            candidatos = [
                p for p in padres_candidatos 
                if abs(extraer_dia(p["fecha"]) - dia_hijo) <= 2 
                and abs(float(p["importe"]) - importe_hijo) < 0.01 
            ]

            if len(candidatos) == 1:
                padre = candidatos[0]
                padre["descripcion"] = f"{padre['descripcion']} | DETALLE: {hijo['descripcion']}"
                ids_hijos_fusionados.add(id(hijo))
                continue

            if len(candidatos) > 1:
                for padre in candidatos:
                    palabras_padre = obtener_palabras_clave(padre["descripcion"])
                    coincidencias = palabras_hijo.intersection(palabras_padre)
                    
                    if len(coincidencias) >= 1:
                        padre["descripcion"] = f"{padre['descripcion']} | DETALLE: {hijo['descripcion']}"
                        ids_hijos_fusionados.add(id(hijo))
                        break

        hijos_restantes = [h for h in hijos if id(h) not in ids_hijos_fusionados]
        
        if hijos_restantes:
            self._log_debug(self.LOG_TRANSACCIONES, f"ALERTA: {len(hijos_restantes)} Transacciones SPEI Huérfanas.")

        lista_final = padres_candidatos + padres_intocables + hijos_restantes

        for tx in lista_final:
            tx.pop("seccion", None)

        lista_final.sort(key=lambda x: x["fecha"])
        return lista_final