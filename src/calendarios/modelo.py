"""Cálculo del calendario anual de un grupo como programa lineal entero (scipy/HiGHS).

Funciona igual en el ordenador y en el navegador (Pyodide). Se parte de la rotación de 26 semanas
(cada persona desfasada `salto` semanas) y se buscan los mínimos cambios que cumplen todas las reglas:

* mínimos diarios de mañana / tarde / noche,
* horas anuales dentro del margen (las horas que sobran se quitan como días "F", sobre todo de mañanas),
* descansos tras la última noche (según el día de la semana), máximo de días seguidos, no pasar de tarde a mañana,
* Nochebuena / Nochevieja alternas, dos personas de mañana en las dos, y Reyes libre para las de mañana del año anterior,
* reparto lo más igualado posible de los festivos trabajados.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_array

from .datos import SEMANAS_ROTACION, Datos, Grupo, lunes_de

ESTADOS = ("M", "T", "N", "O")  # O = no trabaja
DIAS_HISTORIA = 14  # días del año anterior que se tienen en cuenta para descansos
# En festivos y alrededor de Navidad y Reyes se permite cualquier cambio de turno; el resto del año solo
# se puede quitar un turno de la rotación (convertirlo en F), que es mucho más rápido de calcular.
VENTANA_LIBRE = ((1, 1, 1, 10), (12, 15, 12, 31))

# Pesos del objetivo (cuanto más alto, más se evita)
COSTE_LIBRE_A_TRABAJO = 60
COSTE_CAMBIO_TURNO = 40
COSTE_QUITAR = {"M": 4, "T": 12, "N": 60}  # quitar un turno de la rotación (se convierte en F)
COSTE_QUITAR_EN_FESTIVO = {"M": 0, "T": 8, "N": 60}  # en festivo se prefiere librar
COSTE_DESEQUILIBRIO_FESTIVOS = 200
COSTE_F_EXTRA_MES = 3  # cada F por encima de 2 en un mismo mes (reparte las F por el año)
COSTE_REGLA_CON_ANIO_ANTERIOR = 1000


@dataclass
class Resultado:
    grupo: Grupo
    fechas: list[dt.date]
    turnos: list[list[str]]  # [persona][día] -> M/T/N/L/F
    base: list[list[str]]  # rotación sin tocar, para marcar cambios
    estado: str
    avisos: list[str] = field(default_factory=list)
    pareja_mananas: list[int] = field(default_factory=list)  # índices de las 2 de mañana en Navidad


def turno_base(grupo: Grupo, persona: int, fecha: dt.date, lunes_ref: dt.date) -> str:
    semanas = (lunes_de(fecha) - lunes_ref).days // 7
    fila = (grupo.fila_inicial - 1 + grupo.salto * persona + semanas) % SEMANAS_ROTACION
    return grupo.rotacion[fila][fecha.weekday()]


class _Milp:
    """Construcción mínima de un MILP: variables con coste y restricciones lb <= a·x <= ub."""

    def __init__(self):
        self.lb, self.ub, self.c, self.entera = [], [], [], []
        self.filas, self.cols, self.vals, self.clb, self.cub = [], [], [], [], []

    def var(self, lb=0.0, ub=1.0, coste=0.0, entera=True) -> int:
        self.lb.append(lb)
        self.ub.append(ub)
        self.c.append(coste)
        self.entera.append(1 if entera else 0)
        return len(self.c) - 1

    def add(self, terminos: list[tuple[int, float]], lb=-np.inf, ub=np.inf):
        fila = len(self.clb)
        for v, a in terminos:
            self.filas.append(fila)
            self.cols.append(v)
            self.vals.append(a)
        self.clb.append(lb)
        self.cub.append(ub)

    def resolver(self, tiempo: float):
        n = len(self.c)
        A = coo_array((self.vals, (self.filas, self.cols)), shape=(len(self.clb), n)).tocsr()
        return milp(np.array(self.c), integrality=np.array(self.entera), bounds=Bounds(self.lb, self.ub),
                    constraints=LinearConstraint(A, self.clb, self.cub),
                    options={"time_limit": tiempo, "mip_rel_gap": 1e-4, "disp": False})


def _en_ventana_libre(fecha: dt.date) -> bool:
    return any((m1, d1) <= (fecha.month, fecha.day) <= (m2, d2) for m1, d1, m2, d2 in VENTANA_LIBRE)


def calcular_grupo(datos: Datos, grupo: Grupo, *, relajar: frozenset[str] = frozenset(),
                   libre_todo_el_anio: bool = False) -> Resultado:
    p = datos.parametros
    anio = p.anio
    lunes_ref = datos.lunes_referencia
    inicio = dt.date(anio, 1, 1)
    n_anio = (dt.date(anio + 1, 1, 1) - inicio).days
    fechas_h = [inicio + dt.timedelta(days=i) for i in range(-DIAS_HISTORIA, n_anio)]
    H = DIAS_HISTORIA
    D = len(fechas_h)
    idx = {f: i for i, f in enumerate(fechas_h)}
    personas = grupo.personas
    P = range(len(personas))
    festivos_d = {idx[f] for f in datos.festivos if f in idx and idx[f] >= H}

    base = [[turno_base(grupo, k, f, lunes_ref) for f in fechas_h] for k in P]

    # Historia: lo que se sabe de Navidad del año anterior sustituye a la rotación
    historia = [list(fila[:H]) for fila in base]
    for k, pe in enumerate(personas):
        for fecha, turno in ((dt.date(anio - 1, 12, 24), pe.nochebuena_prev),
                             (dt.date(anio - 1, 12, 25), pe.nochebuena_prev),
                             (dt.date(anio - 1, 12, 31), pe.nochevieja_prev)):
            if turno:
                historia[k][idx[fecha]] = turno
            elif pe.nochebuena_prev or pe.nochevieja_prev:
                historia[k][idx[fecha]] = "L"

    m = _Milp()
    x = {}
    for k in P:
        for d in range(D):
            b = base[k][d]
            libre = libre_todo_el_anio or d in festivos_d or _en_ventana_libre(fechas_h[d])
            for s in ESTADOS:
                if d < H:  # fijado por el año anterior
                    h = historia[k][d]
                    fijo = 1.0 if s == ("O" if h == "L" else h) else 0.0
                    x[k, d, s] = m.var(fijo, fijo)
                    continue
                if b == "L":
                    coste = COSTE_LIBRE_A_TRABAJO if s != "O" else 0
                elif s == "O":
                    coste = (COSTE_QUITAR_EN_FESTIVO if d in festivos_d else COSTE_QUITAR)[b]
                else:
                    coste = COSTE_CAMBIO_TURNO if s != b else 0
                permitido = libre or s == "O" or s == b
                x[k, d, s] = m.var(0, 1 if permitido else 0, coste)
            m.add([(x[k, d, s], 1) for s in ESTADOS], 1, 1)

    avisos: list[str] = []
    blandas: list[tuple[int, str]] = []

    def regla(terminos: list[tuple[int, float]], lb: float, k: int, *ds: int):
        """Obligatoria dentro del año. Si toca días del año anterior (que se reconstruyen con la rotación
        y pueden no coincidir con lo que se trabajó de verdad) se permite incumplirla con gran coste."""
        if min(ds) >= H:
            m.add(terminos, lb=lb)
            return
        holgura = m.var(0, 1, COSTE_REGLA_CON_ANIO_ANTERIOR)
        m.add(terminos + [(holgura, 1)], lb=lb)
        blandas.append((holgura, f"{personas[k].nombre}: revisa los primeros días de enero "
                                 f"(descansos respecto a diciembre de {anio - 1})"))

    # --- Mínimos diarios
    for d in range(H, D):
        for s in ("M", "T", "N"):
            m.add([(x[k, d, s], 1) for k in P], lb=p.minimos[s])

    for k in P:
        for d in range(D - 1):
            # No pasar de tarde a mañana:  T[d] + M[d+1] <= 1   <=>  -T[d] - M[d+1] >= -1
            if d + 1 >= H:
                regla([(x[k, d, "T"], -1), (x[k, d + 1, "M"], -1)], -1, k, d, d + 1)
            # Descansos tras la última noche (depende del día de la semana de esa noche):
            # si hace noche el día d y no el d+1, libra d+1 .. d+R   <=>  O[d+j] - N[d] + N[d+1] >= 0
            R = p.descansos_noche[fechas_h[d].weekday()]
            for j in range(1, R + 1):
                if H <= d + j < D:
                    regla([(x[k, d + j, "O"], 1), (x[k, d, "N"], -1), (x[k, d + 1, "N"], 1)], 0, k, d, d + j)

    # --- Máximo de días seguidos: tras L días trabajados, libranzas.  O[d+L+j] + Σ O[d..d+L-1] >= 1
    L = p.max_dias_seguidos
    for k in P:
        for d in range(D - L):
            for j in range(p.libranzas_tras_max):
                if H <= d + L + j < D:
                    regla([(x[k, d + L + j, "O"], 1)] + [(x[k, d + i, "O"], 1) for i in range(L)], 1,
                          k, d, d + L + j)

    # --- Horas anuales
    for k in P:
        m.add([(x[k, d, s], p.duracion[s]) for d in range(H, D) for s in ("M", "T", "N")],
              p.horas_anuales - p.margen, p.horas_anuales + p.margen)

    # --- Navidad
    es_pareja: dict[int, int] = {}
    if "navidad" not in relajar:
        es_pareja = _reglas_navidad(m, x, datos, grupo, idx, avisos)

    # --- Reparto de festivos: diferencia entre quien más y quien menos trabaja
    F = len(festivos_d)
    if F:
        maxi = m.var(0, F, COSTE_DESEQUILIBRIO_FESTIVOS)
        mini = m.var(0, F, -COSTE_DESEQUILIBRIO_FESTIVOS)
        for k in P:
            libres = [(x[k, d, "O"], 1) for d in festivos_d]  # trabajados = F - libres
            m.add([(maxi, 1)] + libres, lb=F)
            m.add([(mini, 1)] + libres, ub=F)

    # --- Repartir las F (libranzas de ajuste) a lo largo del año
    for k in P:
        for mes in range(1, 13):
            dias = [d for d in range(H, D) if fechas_h[d].month == mes and base[k][d] != "L" and d not in festivos_d]
            exceso = m.var(0, len(dias), COSTE_F_EXTRA_MES, entera=False)
            m.add([(exceso, 1)] + [(x[k, d, "O"], -1) for d in dias], lb=-2)

    res = m.resolver(p.tiempo_max_s)
    fechas = fechas_h[H:]
    base_anio = [fila[H:] for fila in base]
    if res.x is None:
        if not libre_todo_el_anio and res.status == 2:  # sin solución: probar dejando cambiar todo el año
            return calcular_grupo(datos, grupo, relajar=relajar, libre_todo_el_anio=True)
        estado = "TIEMPO" if res.status == 1 else "SIN_SOLUCION"
        return Resultado(grupo, fechas, [], base_anio, estado, avisos)

    val = lambda v: res.x[v] > 0.5  # noqa: E731
    pareja = [k for k, v in es_pareja.items() if val(v)]
    avisos += sorted({texto for v, texto in blandas if val(v)})
    turnos = []
    for k in P:
        fila = []
        for d in range(H, D):
            s = next(s for s in ESTADOS if val(x[k, d, s]))
            if s == "O":
                s = "L" if base[k][d] == "L" else "F"
            fila.append(s)
        turnos.append(fila)
    estado = "OPTIMO" if res.status == 0 else "VALIDO"
    if estado == "VALIDO":
        avisos.append("Se ha encontrado un calendario válido, pero quizá no el de menos cambios "
                      "(sube el tiempo máximo de cálculo si quieres afinarlo).")
    return Resultado(grupo, fechas, turnos, base_anio, estado, avisos, pareja)


def _reglas_navidad(m: _Milp, x, datos: Datos, grupo: Grupo, idx, avisos: list[str]) -> dict[int, int]:
    anio = datos.parametros.anio
    d24, d25, d31 = (idx[dt.date(anio, 12, dia)] for dia in (24, 25, 31))
    d1 = idx[dt.date(anio, 1, 1)]
    d6 = idx[dt.date(anio, 1, 6)]
    personas = grupo.personas
    P = range(len(personas))
    fija = lambda v, valor: m.add([(v, 1)], valor, valor)  # noqa: E731

    # Pareja de mañanas de este año: las marcadas, y si faltan las elige el programa
    # (nunca repite quien ya las hizo el año anterior).
    es_pareja = {k: m.var() for k in P}
    for k, pe in enumerate(personas):
        if pe.mananas_navidad:
            fija(es_pareja[k], 1)
        elif pe.mananas_navidad_prev:
            fija(es_pareja[k], 0)
    m.add([(v, 1) for v in es_pareja.values()], 2, 2)

    for k, pe in enumerate(personas):
        # La pareja: mañana el 24, 25 y 31      M[d] - pareja >= 0
        for d in (d24, d25, d31):
            m.add([(x[k, d, "M"], 1), (es_pareja[k], -1)], lb=0)
        # El resto, exactamente una de las dos noches; la pareja, las dos:  O24 + O31 + pareja = 1
        m.add([(x[k, d24, "O"], 1), (x[k, d31, "O"], 1), (es_pareja[k], 1)], 1, 1)
        # Navidad con el mismo turno que Nochebuena
        for s in ESTADOS:
            m.add([(x[k, d25, s], 1), (x[k, d24, s], -1)], 0, 0)

        # Alternancia respecto al año anterior (no aplica a la pareja de mañanas del año anterior)
        if not pe.mananas_navidad_prev:
            if pe.nochebuena_prev and not pe.nochevieja_prev:
                fija(x[k, d31, "O"], 0)
            elif pe.nochevieja_prev and not pe.nochebuena_prev:
                fija(x[k, d24, "O"], 0)
        # Año Nuevo con el mismo turno que la Nochevieja anterior
        if pe.nochevieja_prev:
            fija(x[k, d1, pe.nochevieja_prev], 1)
        # Reyes libre para quien hizo las mañanas de Navidad el año anterior
        if pe.mananas_navidad_prev:
            fija(x[k, d6, "O"], 1)

    prev = [pe.nombre for pe in personas if pe.mananas_navidad_prev]
    if len(prev) not in (0, 2):
        avisos.append(f"Navidad {anio - 1}: se esperaban 2 personas de mañana en Nochebuena y Nochevieja "
                      f"y hay {len(prev)} ({', '.join(prev) or 'ninguna'}).")
    if not any(pe.nochebuena_prev or pe.nochevieja_prev for pe in personas):
        avisos.append(f"No hay datos de la Navidad de {anio - 1}: se reparte Nochebuena/Nochevieja libremente.")
    return es_pareja


def diagnosticar(datos: Datos, grupo: Grupo) -> str:
    """Si no hay solución, prueba a quitar las reglas de Navidad para señalar la causa."""
    r = calcular_grupo(datos, grupo, relajar=frozenset({"navidad"}))
    if r.turnos:
        return ("Las reglas de Navidad no se pueden cumplir con los datos del año anterior. Revisa quién hizo "
                "Nochebuena y Nochevieja: en cada una de las dos noches tiene que haber gente suficiente para "
                "cubrir los mínimos (contando las 2 de mañana).")
    return ("Ni siquiera sin las reglas de Navidad hay solución: revisa las horas anuales, el margen, "
            "los mínimos, los descansos y la rotación del grupo.")
