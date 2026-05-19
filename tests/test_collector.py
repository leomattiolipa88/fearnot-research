"""
Tests del Macro Agent Data Collector
Cubren los 4 niveles de verificación:
  Nivel 1 — Unitarios: cada función individualmente
  Nivel 2 — Integración: piezas conectadas
  Nivel 3 — Sanidad de datos: datos reales razonables
  Nivel 4 — Extremo a extremo: sistema completo
"""
 
import pytest
import sqlite3
import math
from datetime import date, datetime, timedelta
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
 
from collector import (
    init_db, guardar_dato, obtener_ultimo, registrar_alerta,
    validar, verificar_freshness, calcular_yield_curve,
    determinar_regimen_basico, obtener_snapshot, Dato
)
 
# ── Fixtures ──────────────────────────────────────────────────────────────────
@pytest.fixture
def db_test(tmp_path):
    """Base de datos en memoria para cada test — limpia y aislada."""
    db_path = str(tmp_path / "test.db")
    conn = init_db(db_path)
    yield conn, db_path
    conn.close()
 
 
def crear_dato(nombre, valor, dias_atras=0, es_valido=True):
    """Helper para crear datos de prueba rápidamente."""
    fecha = (date.today() - timedelta(days=dias_atras)).isoformat()
    return Dato(
        nombre=nombre,
        valor=valor,
        fecha_publicacion=fecha,
        fecha_descarga=fecha,
        fuente="test",
        es_valido=es_valido,
        nota="OK"
    )
 
 
# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 1 — TESTS UNITARIOS
# Cada función individualmente, sin red ni DB real
# ═══════════════════════════════════════════════════════════════════════════════
 
class TestValidacion:
    """Verifica que la función validar() rechaza datos incorrectos."""
 
    def test_vix_normal_es_valido(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("vix", 18.5, anterior=17.0, conn=conn)
        assert es_valido is True
        assert nota == "OK"
 
    def test_vix_negativo_es_invalido(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("vix", -5.0, anterior=None, conn=conn)
        assert es_valido is False
        assert "rango" in nota.lower()
 
    def test_vix_imposiblemente_alto_es_invalido(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("vix", 150.0, anterior=None, conn=conn)
        assert es_valido is False
 
    def test_yield_10y_normal(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("yield_10y", 4.28, anterior=4.20, conn=conn)
        assert es_valido is True
 
    def test_yield_10y_negativo_invalido(self, db_test):
        """Los yields negativos son posibles en Europa pero no en USA históricamente."""
        conn, _ = db_test
        # 0.01 es el mínimo en nuestro rango — por debajo es sospechoso
        es_valido, nota = validar("yield_10y", -0.5, anterior=None, conn=conn)
        assert es_valido is False
 
    def test_dxy_rango_valido(self, db_test):
        conn, _ = db_test
        es_valido, _ = validar("dxy", 104.5, anterior=104.0, conn=conn)
        assert es_valido is True
 
    def test_dxy_fuera_de_historia(self, db_test):
        """DXY nunca estuvo en 200 ni en 10 — ambos deben fallar."""
        conn, _ = db_test
        es_valido_alto, _ = validar("dxy", 200.0, anterior=None, conn=conn)
        es_valido_bajo, _ = validar("dxy", 10.0, anterior=None, conn=conn)
        assert es_valido_alto is False
        assert es_valido_bajo is False
 
    def test_usdjpy_carry_trade_range(self, db_test):
        conn, _ = db_test
        # Valores realistas para USD/JPY
        for val in [100.0, 130.0, 155.0]:
            es_valido, _ = validar("usdjpy", val, anterior=None, conn=conn)
            assert es_valido is True, f"USD/JPY={val} debería ser válido"
 
    def test_pmi_sobre_50_expansion(self, db_test):
        conn, _ = db_test
        es_valido, _ = validar("pmi_manuf", 52.3, anterior=50.5, conn=conn)
        assert es_valido is True
 
    def test_pmi_imposible(self, db_test):
        """PMI nunca fue 0 ni 100 en la historia."""
        conn, _ = db_test
        es_valido, _ = validar("pmi_manuf", 0.0, anterior=None, conn=conn)
        assert es_valido is False
 
    def test_none_es_invalido(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("vix", None, anterior=None, conn=conn)
        assert es_valido is False
 
    def test_nan_es_invalido(self, db_test):
        conn, _ = db_test
        es_valido, nota = validar("vix", float('nan'), anterior=None, conn=conn)
        assert es_valido is False
 
 
class TestBaseDeDatos:
    """Verifica que la DB guarda y recupera datos correctamente."""
 
    def test_init_crea_tablas(self, db_test):
        conn, _ = db_test
        tablas = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        nombres = [t[0] for t in tablas]
        assert "indicadores" in nombres
        assert "alertas" in nombres
 
    def test_guardar_y_recuperar(self, db_test):
        conn, _ = db_test
        dato = crear_dato("vix", 18.5)
        guardar_dato(conn, dato)
 
        recuperado = obtener_ultimo(conn, "vix")
        assert recuperado is not None
        assert recuperado.valor == 18.5
        assert recuperado.nombre == "vix"
 
    def test_obtener_ultimo_toma_el_mas_reciente(self, db_test):
        """Si hay dos VIX, debe devolver el más reciente."""
        conn, _ = db_test
        # Dato viejo
        dato_viejo = Dato("vix", 25.0, "2026-01-01", "2026-01-01",
                          "test", True, "OK")
        # Dato nuevo
        dato_nuevo = Dato("vix", 18.5, "2026-03-28", "2026-03-28",
                          "test", True, "OK")
        guardar_dato(conn, dato_viejo)
        guardar_dato(conn, dato_nuevo)
 
        ultimo = obtener_ultimo(conn, "vix")
        assert ultimo.valor == 18.5
 
    def test_no_duplica_mismo_dato(self, db_test):
        """El mismo dato (nombre + fecha) no se guarda dos veces."""
        conn, _ = db_test
        dato = crear_dato("vix", 18.5)
        guardar_dato(conn, dato)
        guardar_dato(conn, dato)  # segundo intento
 
        count = conn.execute(
            "SELECT COUNT(*) FROM indicadores WHERE nombre='vix'"
        ).fetchone()[0]
        assert count == 1
 
    def test_registrar_alerta_guarda_en_db(self, db_test):
        conn, _ = db_test
        registrar_alerta(conn, "ERROR", "vix", "Valor fuera de rango")
 
        alert = conn.execute(
            "SELECT * FROM alertas WHERE nombre_dato='vix'"
        ).fetchone()
        assert alert is not None
        assert alert[2] == "ERROR"
 
    def test_obtener_ultimo_retorna_none_si_no_existe(self, db_test):
        conn, _ = db_test
        resultado = obtener_ultimo(conn, "indicador_que_no_existe")
        assert resultado is None
 
 
class TestFreshness:
    """Verifica que detectamos datos rancios."""
 
    def test_dato_de_hoy_es_fresco(self, db_test):
        conn, _ = db_test
        guardar_dato(conn, crear_dato("vix", 18.5, dias_atras=0))
        es_fresco, dias = verificar_freshness(conn, "vix")
        assert es_fresco is True
        assert dias == 0
 
    def test_dato_de_ayer_es_fresco_para_vix(self, db_test):
        conn, _ = db_test
        guardar_dato(conn, crear_dato("vix", 18.5, dias_atras=1))
        es_fresco, dias = verificar_freshness(conn, "vix")
        assert es_fresco is True
 
    def test_dato_de_5_dias_es_rancio_para_vix(self, db_test):
        """VIX tiene máximo 1 día permitido."""
        conn, _ = db_test
        guardar_dato(conn, crear_dato("vix", 18.5, dias_atras=5))
        es_fresco, dias = verificar_freshness(conn, "vix")
        assert es_fresco is False
        assert dias == 5
 
    def test_pmi_mensual_acepta_35_dias(self, db_test):
        """PMI es mensual — aceptar hasta 35 días."""
        conn, _ = db_test
        guardar_dato(conn, crear_dato("pmi_manuf", 51.0, dias_atras=30))
        es_fresco, _ = verificar_freshness(conn, "pmi_manuf")
        assert es_fresco is True
 
    def test_indicador_inexistente_no_es_fresco(self, db_test):
        conn, _ = db_test
        es_fresco, dias = verificar_freshness(conn, "no_existe")
        assert es_fresco is False
        assert dias == 999
 
 
# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 2 — TESTS DE INTEGRACIÓN
# Piezas conectadas entre sí
# ═══════════════════════════════════════════════════════════════════════════════
 
class TestYieldCurve:
    """Verifica que el cálculo derivado de la yield curve funciona."""
 
    def test_curva_normal_positiva(self, db_test):
        """10Y = 4.5%, 3M = 4.0% → spread = +0.5% (curva normal)"""
        conn, _ = db_test
        guardar_dato(conn, crear_dato("yield_10y", 4.50))
        guardar_dato(conn, crear_dato("yield_3m",  4.00))
 
        vc = calcular_yield_curve(conn)
        assert vc is not None
        assert abs(vc.valor - 0.50) < 0.001
        assert vc.es_valido is True
 
    def test_curva_invertida_negativa(self, db_test):
        """10Y = 4.0%, 3M = 5.2% → spread = -1.2% (invertida, señal de recesión)"""
        conn, _ = db_test
        guardar_dato(conn, crear_dato("yield_10y", 4.00))
        guardar_dato(conn, crear_dato("yield_3m",  5.20))
 
        vc = calcular_yield_curve(conn)
        assert vc is not None
        assert vc.valor < 0
        assert abs(vc.valor - (-1.20)) < 0.001
 
    def test_curva_falla_si_faltan_datos(self, db_test):
        """Sin datos de yields, la curva no se puede calcular."""
        conn, _ = db_test
        vc = calcular_yield_curve(conn)
        assert vc is None
 
 
class TestRegimenMacro:
    """Verifica que la clasificación de régimen es correcta."""
 
    def _setup_goldilocks(self, conn):
        """Curva normal, spreads bajos, VIX calmo, breakevens normales."""
        guardar_dato(conn, crear_dato("yield_10y",      4.50))
        guardar_dato(conn, crear_dato("yield_3m",       4.00))
        guardar_dato(conn, crear_dato("hy_spread",      3.5))
        guardar_dato(conn, crear_dato("vix",            14.0))
        guardar_dato(conn, crear_dato("breakeven_5y5y", 2.2))
        guardar_dato(conn, crear_dato("sahm_rule",      0.1))
        calcular_yield_curve(conn)
 
    def _setup_recesion(self, conn):
        """Curva muy invertida, spreads altos, regla Sahm activada."""
        guardar_dato(conn, crear_dato("yield_10y",      3.80))
        guardar_dato(conn, crear_dato("yield_3m",       5.50))
        guardar_dato(conn, crear_dato("hy_spread",      7.0))
        guardar_dato(conn, crear_dato("vix",            35.0))
        guardar_dato(conn, crear_dato("breakeven_5y5y", 1.8))
        guardar_dato(conn, crear_dato("sahm_rule",      0.6))
        calcular_yield_curve(conn)
 
    def _setup_stagflation(self, conn):
        """Curva invertida + inflación alta — el peor régimen."""
        guardar_dato(conn, crear_dato("yield_10y",      4.00))
        guardar_dato(conn, crear_dato("yield_3m",       5.50))
        guardar_dato(conn, crear_dato("hy_spread",      6.5))
        guardar_dato(conn, crear_dato("vix",            30.0))
        guardar_dato(conn, crear_dato("breakeven_5y5y", 3.2))
        guardar_dato(conn, crear_dato("sahm_rule",      0.5))
        calcular_yield_curve(conn)
 
    def test_goldilocks_detectado(self, db_test):
        conn, _ = db_test
        self._setup_goldilocks(conn)
        regimen = determinar_regimen_basico(conn)
        assert regimen["regimen"] == "GOLDILOCKS"
        assert regimen["color"] == "green"
 
    def test_recesion_detectada(self, db_test):
        conn, _ = db_test
        self._setup_recesion(conn)
        regimen = determinar_regimen_basico(conn)
        assert regimen["regimen"] == "DESACELERACION"
        assert regimen["senales_riesgo"] >= 3
 
    def test_stagflation_detectada(self, db_test):
        conn, _ = db_test
        self._setup_stagflation(conn)
        regimen = determinar_regimen_basico(conn)
        assert regimen["regimen"] == "STAGFLATION"
 
    def test_regimen_incluye_detalle(self, db_test):
        conn, _ = db_test
        self._setup_recesion(conn)
        regimen = determinar_regimen_basico(conn)
        assert len(regimen["detalle"]) > 0
        assert "timestamp" in regimen
 
 
class TestSnapshot:
    """Verifica que el snapshot para el agente es correcto y completo."""
 
    def test_snapshot_incluye_todos_los_campos(self, db_test):
        conn, db_path = db_test
        guardar_dato(conn, crear_dato("vix", 18.5))
        guardar_dato(conn, crear_dato("yield_10y", 4.28))
        conn.close()
 
        snapshot = obtener_snapshot(db_path)
 
        assert "timestamp_snapshot" in snapshot
        assert "indicadores" in snapshot
        assert "regimen" in snapshot
        assert "datos_confiables" in snapshot
        assert "datos_totales" in snapshot
 
    def test_snapshot_marca_datos_rancios(self, db_test):
        conn, db_path = db_test
        # VIX de hace 10 días — rancio
        guardar_dato(conn, crear_dato("vix", 18.5, dias_atras=10))
        conn.close()
 
        snapshot = obtener_snapshot(db_path)
        vix_snap = snapshot["indicadores"].get("vix")
 
        assert vix_snap is not None
        assert vix_snap["es_fresco"] is False
        assert vix_snap["dias_antiguedad"] == 10
 
    def test_snapshot_cuenta_datos_confiables(self, db_test):
        conn, db_path = db_test
        guardar_dato(conn, crear_dato("vix",       18.5, dias_atras=0))
        guardar_dato(conn, crear_dato("yield_10y", 4.28, dias_atras=0))
        guardar_dato(conn, crear_dato("dxy",       104.5, dias_atras=10))  # rancio
        conn.close()
 
        snapshot = obtener_snapshot(db_path)
        # vix y yield_10y son frescos y válidos (2), dxy es rancio (no cuenta)
        assert snapshot["datos_confiables"] == 2
        assert snapshot["datos_totales"] == 3
 
 
# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 3 — TESTS DE SANIDAD
# Verifican que los datos del mundo real tienen sentido
# ═══════════════════════════════════════════════════════════════════════════════
 
class TestSanidadDatosReales:
    """
    Estos tests corren con yfinance para verificar que los datos reales
    están dentro de rangos razonables para el contexto de marzo 2026.
    Requieren internet. Se marcan como 'sanity' para correrlos por separado.
    """
 
    @pytest.mark.sanity
    def test_vix_actual_es_razonable(self):
        """El VIX real debe estar entre 10 y 60 en condiciones normales."""
        import yfinance as yf
        vix = yf.Ticker("^VIX").history(period="1d")
        if vix.empty:
            pytest.skip("No hay datos de yfinance disponibles")
        valor = float(vix["Close"].iloc[-1])
        assert 10 <= valor <= 60, f"VIX={valor} fuera de rango de sanidad"
 
    @pytest.mark.sanity
    def test_spy_precio_razonable(self):
        """SPY debe estar entre 300 y 800 en el entorno actual."""
        import yfinance as yf
        spy = yf.Ticker("SPY").history(period="1d")
        if spy.empty:
            pytest.skip("No hay datos de yfinance disponibles")
        valor = float(spy["Close"].iloc[-1])
        assert 300 <= valor <= 800, f"SPY={valor} fuera de rango de sanidad"
 
    @pytest.mark.sanity
    def test_usdjpy_rango_actual(self):
        """USD/JPY debería estar entre 130 y 165 en el contexto actual."""
        import yfinance as yf
        fx = yf.Ticker("USDJPY=X").history(period="1d")
        if fx.empty:
            pytest.skip("No hay datos de yfinance disponibles")
        valor = float(fx["Close"].iloc[-1])
        assert 130 <= valor <= 165, f"USDJPY={valor} fuera de rango de sanidad"
 
 
# ═══════════════════════════════════════════════════════════════════════════════
# NIVEL 4 — TEST EXTREMO A EXTREMO (sin red)
# Simula todo el flujo con datos hardcodeados
# ═══════════════════════════════════════════════════════════════════════════════
 
class TestEndToEnd:
    """Simula el flujo completo del colector sin llamadas a APIs externas."""
 
    def test_flujo_completo_con_datos_simulados(self, db_test):
        """
        Simula un día completo de datos: ingesta → validación → régimen → snapshot.
        Verifica que el output final tiene todo lo que el agente necesita.
        """
        conn, db_path = db_test
 
        # Simular datos de un día típico (Goldilocks moderado)
        datos_simulados = [
            ("yield_10y",      4.28,  True),
            ("yield_3m",       4.35,  True),
            ("vix",            22.0,  True),
            ("dxy",            104.2, True),
            ("usdjpy",         151.5, True),
            ("eurusd",         1.082, True),
            ("usdcny",         7.23,  True),
            ("usdbrl",         5.15,  True),
            ("hy_spread",      3.8,   True),
            ("breakeven_5y5y", 2.35,  True),
            ("sahm_rule",      0.15,  True),
            ("gold",           3100.0,True),
            ("spy",            565.0, True),
            ("unemployment",   4.2,   True),
            ("jobless_claims", 215000, True),
        ]
 
        for nombre, valor, es_valido in datos_simulados:
            guardar_dato(conn, crear_dato(nombre, valor, es_valido=es_valido))
 
        # Calcular derivados
        vc = calcular_yield_curve(conn)
        assert vc is not None
        assert abs(vc.valor - (4.28 - 4.35)) < 0.001  # -0.07 (levemente invertida)
 
        # Detectar régimen
        regimen = determinar_regimen_basico(conn)
        assert regimen["regimen"] in ["GOLDILOCKS", "DESACELERACION", "STAGFLATION", "REFLACION"]
 
        conn.close()
 
        # Obtener snapshot para el agente
        snapshot = obtener_snapshot(db_path)
 
        # Verificar estructura completa del snapshot
        assert snapshot["datos_totales"] >= 15
        assert snapshot["datos_confiables"] >= 10
        assert "vix" in snapshot["indicadores"]
        assert "yield_curve" in snapshot["indicadores"]
        assert snapshot["indicadores"]["vix"]["valor"] == 22.0
        assert snapshot["regimen"]["regimen"] in [
            "GOLDILOCKS", "DESACELERACION", "STAGFLATION", "REFLACION"
        ]
 
        # Verificar que el snapshot tiene la info que el agente necesita
        for ind in snapshot["indicadores"].values():
            assert "valor" in ind
            assert "es_valido" in ind
            assert "es_fresco" in ind
            assert "fuente" in ind
 
 
# ═══════════════════════════════════════════════════════════════════════════════
# RUNNER
# ═══════════════════════════════════════════════════════════════════════════════
 
if __name__ == "__main__":
    # Correr todos los tests excepto los de sanidad (que requieren internet)
    pytest.main([
        __file__,
        "-v",
        "-m", "not sanity",
        "--tb=short"
    ])