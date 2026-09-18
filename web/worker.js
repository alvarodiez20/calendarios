// Ejecuta el código Python (src/calendarios) en el navegador con Pyodide, fuera del hilo de la página.
/* global loadPyodide */
const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.29.3/full/";
importScripts(PYODIDE + "pyodide.js");

let api = null;

async function iniciar() {
  aviso("Descargando la herramienta de cálculo…");
  const py = await loadPyodide({ indexURL: PYODIDE });
  aviso("Preparando el cálculo…");
  await py.loadPackage(["numpy", "scipy", "micropip"]);
  aviso("Preparando Excel…");
  await py.pyimport("micropip").install(["openpyxl"]);

  const version = new URL(self.location.href).searchParams.get("v") || "";
  const archivos = await (await fetch(`py/archivos.json?v=${version}`)).json();
  py.FS.mkdirTree("/home/pyodide/calendarios");
  for (const nombre of archivos) {
    const texto = await (await fetch(`py/calendarios/${nombre}?v=${version}`)).text();
    py.FS.writeFile(`/home/pyodide/calendarios/${nombre}`, texto);
  }
  py.runPython("import sys; sys.path.insert(0, '/home/pyodide')");
  api = py.pyimport("calendarios.api");
  aviso("");
}

function aviso(texto) {
  self.postMessage({ tipo: "progreso", texto });
}

// bytes de Python -> Uint8Array
function aBytes(proxy) {
  if (!proxy) return null;
  const u8 = proxy.toJs();
  proxy.destroy?.();
  return u8;
}

// Los errores de datos (ErrorDatos) se enseñan tal cual; el resto, como error inesperado.
function mensajeError(err) {
  const texto = String(err?.message || err);
  const m = texto.match(/ErrorDatos: ([^\n]+)\s*$/);
  if (m) return { datos: true, mensaje: m[1] };
  return { datos: false, mensaje: texto.trim().split("\n").slice(-1)[0] || texto, detalle: texto };
}

const listo = iniciar();
listo.then(
  () => self.postMessage({ tipo: "listo" }),
  (err) => self.postMessage({ tipo: "fallo", error: mensajeError(err) }),
);

self.onmessage = async (e) => {
  const { id, orden, args = {} } = e.data;
  try {
    await listo;
    let res;
    switch (orden) {
      case "plantilla":
        res = aBytes(api.plantilla(args.estado ?? null, args.anio ?? 2027, !!args.vacia));
        break;
      case "importar":
        res = JSON.parse(api.importar_excel(args.bytes));
        break;
      case "siguiente":
        res = JSON.parse(api.siguiente(args.estado, args.bytes));
        break;
      case "generar": {
        const r = api.generar(args.estado, (texto) => aviso(texto));
        const [excel, resumen] = [r.get(0), r.get(1)];
        r.destroy();
        res = { excel: aBytes(excel), resumen: JSON.parse(resumen) };
        aviso("");
        break;
      }
      default:
        throw new Error(`Orden desconocida: ${orden}`);
    }
    self.postMessage({ tipo: "respuesta", id, ok: true, res });
  } catch (err) {
    aviso("");
    self.postMessage({ tipo: "respuesta", id, ok: false, error: mensajeError(err) });
  }
};
