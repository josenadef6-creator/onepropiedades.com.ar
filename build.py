# -*- coding: utf-8 -*-
"""
Motor de la web de ONE Propiedades.

Lee cada propiedad de la carpeta propiedades/ (un .json por propiedad, que
se carga desde el panel onepropiedades.com.ar/admin) y arma la web completa
en la carpeta _site/, que es la que publica Netlify:

  - index.html con el catálogo de propiedades
  - una página por propiedad (ej. _site/the-point.html)
  - fotos, logos, panel de administración y demás archivos

Se corre solo en Netlify con cada cambio. Para probarlo en la compu:
  python build.py
"""
import html
import json
import os
import shutil
import urllib.parse

RAIZ = os.path.dirname(os.path.abspath(__file__))
SALIDA = os.path.join(RAIZ, "_site")
DOMINIO = "https://www.onepropiedades.com.ar/"
WHATSAPP = "5493816363940"

# Archivos y carpetas del repo que NO se publican.
NO_PUBLICAR = {
    "_site", ".git", ".github", "plantillas", "propiedades", "build.py",
    "netlify.toml", "requirements.txt", "README.md", "__pycache__",
}
# Páginas HTML sueltas del repo que sí se publican tal cual.
HTML_EXTRA = set()

ETIQUETA_TIPO = {"casa", "terreno", "comercial"}
ANCHO_MAX_FOTO = 1800  # px; las fotos más grandes se achican al publicar


def esc(texto):
    return html.escape(str(texto or ""), quote=False)


def esc_attr(texto):
    return html.escape(str(texto or ""), quote=True).replace("&#x27;", "'")


def leer(ruta):
    with open(ruta, encoding="utf-8") as f:
        return f.read()


def escribir(ruta, contenido):
    with open(ruta, "w", encoding="utf-8") as f:
        f.write(contenido)


def ruta_foto(valor):
    """Normaliza la ruta de una foto: 'fotos/x.jpg' o 'x.jpg' (sin barra inicial)."""
    return str(valor or "").strip().lstrip("/")


def link_whatsapp(texto):
    # Codifica espacios y signos, pero deja tildes y "·" tal cual (como la web original).
    cod = "".join(c if ord(c) > 127 else urllib.parse.quote(c, safe="$/") for c in texto)
    return "https://wa.me/%s?text=%s" % (WHATSAPP, cod)


def cargar_propiedades():
    carpeta = os.path.join(RAIZ, "propiedades")
    props = []
    for nombre in sorted(os.listdir(carpeta)):
        if not nombre.endswith(".json"):
            continue
        p = json.loads(leer(os.path.join(carpeta, nombre)))
        if p.get("publicada") is False:
            continue
        link = str(p.get("link") or os.path.splitext(nombre)[0]).strip().lower()
        p["link"] = link
        p["lugar"] = (p.get("lugar") or "").strip() or p.get("zona", "")
        p["fotos"] = [f for f in (p.get("fotos") or []) if f.get("foto")]
        for f in p["fotos"]:
            f["foto"] = ruta_foto(f["foto"])
        p["portada"] = ruta_foto(p.get("portada")) or (p["fotos"][0]["foto"] if p["fotos"] else "")
        if p.get("tipo") not in ETIQUETA_TIPO:
            p["tipo"] = "casa"
        props.append(p)
    props.sort(key=lambda p: (float(p.get("orden") or 999), p.get("titulo", "")))
    vistos = set()
    for p in props:
        if p["link"] in vistos:
            raise SystemExit("Hay dos propiedades con el mismo link: %s" % p["link"])
        vistos.add(p["link"])
    return props


def pagina_propiedad(p, plantilla, plantilla_galeria):
    titulo, lugar, precio = p.get("titulo", ""), p["lugar"], p.get("precio", "")
    nombre_largo = "%s en %s" % (titulo, lugar)
    descripcion = (p.get("descripcion") or "").strip() or "%s. %s. %s." % (
        nombre_largo, p.get("resumen", ""), precio)
    og_imagen = DOMINIO + (p["portada"] or "logo-cream.png")

    if p["fotos"]:
        f0 = p["fotos"][0]
        tiras = "\n".join(
            '          <img src="%s" alt="%s" data-i="%d" loading="lazy" aria-current="%s">'
            % (esc_attr(f["foto"]), esc_attr(f.get("epigrafe")), i, "true" if i == 0 else "false")
            for i, f in enumerate(p["fotos"]))
        bloque_fotos = (
            '      <div class="ficha-fotos">\n'
            '        <div class="foto-grande">\n'
            '          <img id="foto" src="%s" alt="%s">\n'
            '          <button class="foto-nav prev" id="prev" type="button" aria-label="Anterior">‹</button>\n'
            '          <button class="foto-nav next" id="next" type="button" aria-label="Siguiente">›</button>\n'
            '          <span class="foto-contador" id="contador">1 de %d</span>\n'
            '        </div>\n'
            '        <p class="foto-pie" id="pie">%s</p>\n'
            '        <div class="tiras" id="tiras">\n%s\n'
            '        </div>\n'
            '      </div>\n'
        ) % (esc_attr(f0["foto"]), esc_attr(f0.get("epigrafe")), len(p["fotos"]),
             esc(f0.get("epigrafe")), tiras)
        lista = json.dumps([[f["foto"], f.get("epigrafe") or ""] for f in p["fotos"]],
                           ensure_ascii=False).replace("</", "<\\/")
        script_fotos = plantilla_galeria.replace("[[LISTA_FOTOS]]", lista)
    else:
        bloque_fotos = (
            '      <div class="ficha-fotos sin-fotos">\n'
            '        <p>Estamos produciendo las fotos de esta propiedad. '
            'Consultanos y te las pasamos por WhatsApp.</p>\n'
            '      </div>\n')
        script_fotos = ""

    ficha = "".join(
        '        <div class="dato-fila"><dt>%s</dt><dd>%s</dd></div>\n'
        % (esc(d.get("dato")), esc(d.get("valor")))
        for d in (p.get("ficha") or []) if d.get("dato"))

    reemplazos = {
        "[[TITULO_PAGINA]]": esc("%s · %s" % (titulo, lugar)),
        "[[DESCRIPCION]]": esc_attr(descripcion),
        "[[OG_TITULO]]": esc_attr("%s · %s · %s" % (titulo, lugar, precio)),
        "[[RESUMEN_ATTR]]": esc_attr(p.get("resumen")),
        "[[OG_IMAGEN]]": esc_attr(og_imagen),
        "[[URL]]": esc_attr(DOMINIO + p["link"] + ".html"),
        "[[WHATSAPP]]": esc_attr(link_whatsapp(
            "Hola ONE, quiero consultar por %s (%s)" % (nombre_largo, precio))),
        "[[FOTOS]]": bloque_fotos,
        "[[ZONA]]": esc(p.get("zona")),
        "[[TITULO]]": esc(titulo),
        "[[PRECIO]]": esc(precio),
        "[[RESUMEN]]": esc(p.get("resumen")),
        "[[FICHA]]": ficha,
        "[[SCRIPT_FOTOS]]": script_fotos,
        "[[TEXTO_COMPARTIR]]": json.dumps("%s · %s" % (nombre_largo, precio),
                                          ensure_ascii=False).replace("</", "<\\/"),
    }
    salida = plantilla
    for clave, valor in reemplazos.items():
        salida = salida.replace(clave, valor)
    return salida


def tarjeta(p):
    cant = len(p["fotos"])
    if p["portada"]:
        pos = (p.get("portada_posicion") or "").strip()
        extra = ' style="object-position:%s"' % esc_attr(pos) if pos else ""
        foto = '<img src="%s" alt="%s" loading="lazy"%s>' % (
            esc_attr(p["portada"]), esc_attr("%s en %s" % (p.get("titulo", ""), p["lugar"])), extra)
    else:
        foto = "<span>Próximamente</span>"
    ver = "Ver propiedad" + (" · %d foto%s" % (cant, "" if cant == 1 else "s") if cant else "")
    etiqueta = (p.get("etiqueta") or "").strip()
    tags = '<span class="tag">%s</span>' % esc(etiqueta) if etiqueta else ""
    return (
        '      <a class="prop" href="%s.html" data-tipo="%s">\n'
        '        <div class="foto">%s<span class="badge">En venta</span></div>\n'
        '        <div class="body">\n'
        '          <p class="zona">%s</p>\n'
        '          <h3>%s</h3>\n'
        '          <p class="datos">%s</p>\n'
        '          <p class="precio">%s</p>\n'
        '          <div class="tags">%s</div>\n'
        '          <span class="ver-fotos">%s</span>\n'
        '        </div>\n'
        '      </a>\n'
    ) % (esc_attr(p["link"]), p["tipo"], foto, esc(p.get("zona")), esc(p.get("titulo")),
         esc(p.get("datos_tarjeta")), esc(p.get("precio")), tags, ver)


def copiar_estaticos():
    try:
        from PIL import Image, ImageOps
    except ImportError:
        Image = None
    for actual, carpetas, archivos in os.walk(RAIZ):
        rel = os.path.relpath(actual, RAIZ)
        if rel == ".":
            carpetas[:] = [c for c in carpetas if c not in NO_PUBLICAR and not c.startswith(".")]
        for nombre in archivos:
            if rel == "." and (nombre in NO_PUBLICAR or nombre.startswith(".")):
                continue
            if rel == "." and nombre.endswith(".html") and nombre not in HTML_EXTRA:
                continue  # las páginas viejas se reemplazan por las generadas
            origen = os.path.join(actual, nombre)
            destino = os.path.join(SALIDA, rel, nombre)
            os.makedirs(os.path.dirname(destino), exist_ok=True)
            if Image and nombre.lower().endswith((".jpg", ".jpeg")):
                try:
                    with Image.open(origen) as im:
                        if im.width > ANCHO_MAX_FOTO or os.path.getsize(origen) > 700_000:
                            im = ImageOps.exif_transpose(im).convert("RGB")
                            im.thumbnail((ANCHO_MAX_FOTO, ANCHO_MAX_FOTO * 2))
                            im.save(destino, "JPEG", quality=82, optimize=True, progressive=True)
                            continue
                except Exception as e:
                    print("  aviso: no pude achicar %s (%s)" % (nombre, e))
            shutil.copy2(origen, destino)


def main():
    props = cargar_propiedades()
    if os.path.isdir(SALIDA):
        shutil.rmtree(SALIDA)
    os.makedirs(SALIDA)
    copiar_estaticos()

    plantilla = leer(os.path.join(RAIZ, "plantillas", "propiedad.html"))
    galeria = leer(os.path.join(RAIZ, "plantillas", "galeria.js.html"))
    for p in props:
        escribir(os.path.join(SALIDA, p["link"] + ".html"), pagina_propiedad(p, plantilla, galeria))

    index = leer(os.path.join(RAIZ, "plantillas", "index.html"))
    escribir(os.path.join(SALIDA, "index.html"),
             index.replace("[[TARJETAS]]", "".join(tarjeta(p) for p in props)))

    print("Listo: %d propiedades publicadas en _site/" % len(props))
    for p in props:
        print("  - %s.html  (%d fotos)" % (p["link"], len(p["fotos"])))


if __name__ == "__main__":
    main()
