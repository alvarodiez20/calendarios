# Calendarios de turnos · Residencia (Burgos)

Genera en Excel el calendario anual de turnos de cada grupo a partir de su rotación de 26 semanas.

**Web:** https://alvarodiez20.github.io/calendarios/ (PIN `1010`)

La web funciona entera en el navegador: el mismo código Python se ejecuta con
[Pyodide](https://pyodide.org), sin servidor. Los datos se guardan en el propio navegador y
también se pueden descargar y subir como Excel.

> El PIN solo evita entradas por despiste: el repositorio es público y el PIN está en el código.
> No hay datos en ningún servidor.

## Cómo se usa (web)

1. **Tus datos**: se puede trabajar directamente en la web, o bien descargar la plantilla de Excel, rellenarla y subirla.
2. **Grupos**: nombre, semana de arranque (por defecto la 18), rotación de 26 semanas (se pinta con el ratón) y
   personas, con el turno que hizo cada una en Nochebuena y Nochevieja del año anterior.
3. **Festivos** del año, que hay que revisar.
4. **Ajustes** (horas, turnos, mínimos, descansos…), que normalmente no se tocan.
5. **Generar calendario**: descarga `calendario_AAAA.xlsx`. En el Excel se pueden retocar turnos con el
   desplegable, y las horas, los mínimos y los colores se recalculan solos.
6. **Año siguiente**: al subir el calendario terminado se apunta quién hizo Nochebuena y Nochevieja y se pasa al año siguiente.

## Reglas

- Se parte de la rotación de 26 semanas, con cada persona desfasada 2 semanas. Se hacen **los mínimos
  cambios posibles**, que salen **subrayados** en el Excel.
- Cada día hay al menos 3 personas de mañana, 3 de tarde y 1 de noche en cada grupo.
- **En festivo trabaja justo el mínimo** y el resto libra. Si algún festivo no puede cumplirlo (por ejemplo
  porque la alternancia de Nochebuena/Nochevieja obliga a trabajar a más gente), se avisa.
- Cada persona suma 1715 h (± 3:30). Mañana y tarde son 7:00 y la noche 11:22. Las horas que sobran
  se quitan como días **F**, sobre todo en mañanas y festivos.
- Descansos tras la última noche, según el día de esa noche: **viernes y sábado 2 L**, el resto **3 L**.
  Siempre salen como **L**: una **F nunca va pegada a las noches**, ni dentro del descanso ni justo después.
- Después de 7 días seguidos hay 2 libranzas. No se pasa de tarde a mañana.
- Los días van en **bloques**: nunca una libranza suelta (solo un festivo puede librarse solo), nunca más
  días libres seguidos de los que ya da la rotación, y nunca se va a trabajar un día suelto entre dos
  libranzas. Así no salen cosas como «7 días, 1 libranza y otros 7», ni «libro, trabajo un día y libro».
- Diciembre se calcula con los primeros días de enero del año siguiente por delante, para no cortar
  el descanso de las noches en el cambio de año.
- **Navidad**:
  - Quien hizo Nochebuena hace Nochevieja al año siguiente, y al revés. Nadie trabaja las dos (salvo la
    pareja de mañanas), y con 13 personas siempre hay alguien que libra las dos: es lo que hace que
    los dos días salgan justo con el mínimo.
  - El 25 se trabaja con el mismo turno que el 24, y el 1 de enero con el mismo turno que el 31.
  - Cada año, 2 personas por grupo hacen el 24 y el 31 de mañana. Al año siguiente libran Reyes y quedan
    fuera de la alternancia.
- Los festivos (incluidos Jueves y Viernes Santo) se reparten lo más igualado posible.

## Desarrollo

```bash
uv run pytest                                                       # tests
uv run calendarios plantilla 2027 [--vacia]                         # datos_2027.xlsx
uv run calendarios generar datos_2027.xlsx                          # calendario_2027.xlsx
uv run calendarios siguiente datos_2027.xlsx calendario_2027.xlsx   # datos_2028.xlsx
uv run python scripts/construir_web.py && python3 -m http.server -d _site 8000   # web en local
```

Cada `push` a `main` pasa los tests y publica la web en GitHub Pages (`.github/workflows/web.yml`).

| Fichero | Qué hace |
|---|---|
| `src/calendarios/modelo.py` | cálculo (programa lineal entero con `scipy.optimize.milp` / HiGHS) |
| `src/calendarios/datos.py` | modelo de datos, festivos por defecto y lectura del Excel de datos |
| `src/calendarios/plantilla.py` | Excel de datos (plantilla) |
| `src/calendarios/excel_salida.py` | Excel del calendario |
| `src/calendarios/siguiente.py` | paso de un año al siguiente |
| `src/calendarios/validar.py` | comprobación independiente del resultado |
| `src/calendarios/api.py` | funciones que usan la web y el terminal |
| `web/` | página (HTML/CSS/JS) y `worker.js`, que carga Pyodide |

Los `.xlsx` no se versionan porque llevan datos personales.
