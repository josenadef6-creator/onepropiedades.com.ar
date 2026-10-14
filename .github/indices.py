# -*- coding: utf-8 -*-
"""
Baja los índices oficiales para la calculadora de alquileres de ONE
(onepropiedades.com.ar/alquileres) y los guarda en alquileres/indices.json.

  - ICL: Banco Central (api.bcra.gob.ar)
  - IPC: INDEC, vía la API de series de tiempo (apis.datos.gob.ar)

Lo corre GitHub Actions todos los días (.github/workflows/indices.yml).
Si una fuente falla, se conservan los datos que ya había de ese índice.
"""
import datetime as dt
import json
import os
import ssl
import time
import urllib.parse
import urllib.request

RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SALIDA = os.path.join(RAIZ, "alquileres", "indices.json")

BCRA = "https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/%d"
BCRA_IDS = {"icl": 40}
DESDE_DIARIOS = "2020-07-01"  # inicio de la Ley 27.551

IPC_URL = "https://apis.datos.gob.ar/series/api/series/"
IPC_ID = "148.3_INIVELNAL_DICI_M_26"  # IPC Nivel General Nacional, base dic-2016
DESDE_IPC = "2017-01-01"

MINIMO_FILAS = {"icl": 500, "ipc": 60}


def pedir_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "ONE-Propiedades-indices/1.0", "Accept": "application/json"})
    ultimo_error = None
    for intento in range(3):
        for verificar in (True, False):
            try:
                ctx = ssl.create_default_context() if verificar else ssl._create_unverified_context()
                with urllib.request.urlopen(req, timeout=60, context=ctx) as r:
                    if not verificar:
                        print("  aviso: certificado no verificado en", url.split("/")[2])
                    return json.loads(r.read().decode("utf-8"))
            except ssl.SSLError as e:
                ultimo_error = e
                continue  # reintenta sin verificar (algunos servidores públicos tienen la cadena incompleta)
            except Exception as e:
                ultimo_error = e
                break
        time.sleep(3 * (intento + 1))
    raise RuntimeError("no pude bajar %s (%s)" % (url, ultimo_error))


def bajar_bcra(id_variable):
    hoy = dt.date.today() + dt.timedelta(days=60)  # el ICL se publica con días de anticipo
    filas, offset = {}, 0
    while True:
        q = urllib.parse.urlencode({"desde": DESDE_DIARIOS, "hasta": hoy.isoformat(), "limit": 3000, "offset": offset})
        datos = pedir_json((BCRA % id_variable) + "?" + q)
        resultados = datos.get("results") or []
        detalle = []
        for r in resultados:
            if isinstance(r, dict) and "detalle" in r:   # formato v4.0
                detalle.extend(r["detalle"] or [])
            elif isinstance(r, dict) and "fecha" in r:   # formato v3.0
                detalle.append(r)
        for d in detalle:
            try:
                filas[str(d["fecha"])[:10]] = round(float(d["valor"]), 6)
            except (KeyError, TypeError, ValueError):
                pass
        total = ((datos.get("metadata") or {}).get("resultset") or {}).get("count") or 0
        offset += 3000
        if not detalle or offset >= total:
            break
    return sorted(filas.items())


def bajar_ipc():
    q = urllib.parse.urlencode({"ids": IPC_ID, "start_date": DESDE_IPC, "limit": 1000, "format": "json"})
    datos = pedir_json(IPC_URL + "?" + q)
    filas = []
    for fecha, valor in datos.get("data") or []:
        if valor is not None:
            filas.append((str(fecha)[:7], round(float(valor), 4)))  # "AAAA-MM"
    return filas


def main():
    previo = {}
    if os.path.exists(SALIDA):
        try:
            with open(SALIDA, encoding="utf-8") as f:
                previo = json.load(f)
        except Exception:
            previo = {}

    salida = {"fuentes": {"icl": "BCRA", "ipc": "INDEC"}}
    trabajos = [(k, (lambda i=i: bajar_bcra(i))) for k, i in BCRA_IDS.items()] + [("ipc", bajar_ipc)]
    for clave, bajar in trabajos:
        try:
            filas = bajar()
            if len(filas) < MINIMO_FILAS[clave]:
                raise RuntimeError("llegaron pocas filas (%d)" % len(filas))
            salida[clave] = [list(f) for f in filas]
            print("  %s: %d datos, último %s = %s" % (clave, len(filas), filas[-1][0], filas[-1][1]))
        except Exception as e:
            print("  ERROR %s: %s — se conserva lo anterior" % (clave, e))
            if previo.get(clave):
                salida[clave] = previo[clave]

    if not any(salida.get(k) for k in ("icl", "ipc")):
        raise SystemExit("No se pudo bajar ningún índice.")

    ultimos = [salida[k][-1][0] for k in ("icl",) if salida.get(k)]
    hoy = dt.date.today().isoformat()
    salida["actualizado"] = hoy
    salida = {k: salida[k] for k in ["actualizado", "fuentes", "icl", "ipc"] if k in salida}

    os.makedirs(os.path.dirname(SALIDA), exist_ok=True)
    nuevo = json.dumps(salida, ensure_ascii=False, separators=(",", ":"))
    viejo = json.dumps({k: v for k, v in previo.items()}, ensure_ascii=False, separators=(",", ":")) if previo else ""
    # Si los datos no cambiaron, no se toca el archivo (evita publicar la web de gusto).
    sin_fecha = lambda s: json.loads(s) if s else {}
    a, b = sin_fecha(nuevo), sin_fecha(viejo)
    a.pop("actualizado", None); b.pop("actualizado", None)
    if a == b:
        print("Sin cambios en los índices.")
        return
    with open(SALIDA, "w", encoding="utf-8") as f:
        f.write(nuevo)
    print("Guardado alquileres/indices.json (último dato diario: %s)" % (max(ultimos) if ultimos else "-"))


if __name__ == "__main__":
    main()
