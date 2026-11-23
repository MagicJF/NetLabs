# PROPÓSITO:   el mapa del laboratorio en lo que observa el sitio (NetXMS), colocado como
#              el plano. La vista tiene su propia topología automática —los equipos
#              repartidos por un algoritmo suyo, que no se parece a nada de lo que
#              dibuja el motor—: aquí se manda un mapa **a medida** en el que cada
#              equipo está donde lo puso el plano y cada red es la caja que el plano
#              dibuja. Así el mapa de la vista y el plano de la documentación son el
#              mismo dibujo, no dos parecidos.
# INVARIANTES: la geometría sale del propio plano (`plano.plano(lab, "topologia")`), que
#              ya lleva la posición de cada cosa en atributos `data-*`: no se recalcula
#              nada aquí, para que no puedan discrepar. Nada de este módulo habla con el
#              API ni escribe: deriva el contenido del mapa y dice si el que hay ya
#              coincide.
# VER:         docs/diseno.md §2.9 (el mapa a medida), §3.6;
#              docs/decisiones/0004-el-mapa-de-la-vista-lo-coloca-el-plano.md

import json
import re

# Cómo nombra la vista a las cosas del mapa. Son los números que viajan en el JSON del
# API: el tipo de elemento y, dentro de los adornos, la caja de grupo.
ELEMENTO_OBJETO = 1        # un equipo de la vista
ELEMENTO_ADORNO = 2        # una figura del mapa, no un equipo
ADORNO_CAJA = 0            # la caja de grupo: un rectángulo con su rótulo

TAMANO_EQUIPO = 100        # lado del hueco de un equipo en el mapa, como la vista


def disposicion(svg: str) -> dict:
    """Dónde queda cada cosa en el plano: el lienzo, las áreas y los equipos.

    Se lee de los atributos `data-*` que el propio plano lleva —los mismos que usan las
    pruebas del dibujo—, así que el mapa no puede colocarse en un sitio distinto del que
    el plano enseña.
    """
    lienzo = re.search(r'<svg[^>]*width="([\d.]+)"[^>]*height="([\d.]+)"', svg)
    if lienzo is None:
        raise ValueError("el plano no declara su tamaño: no hay mapa que colocar")
    areas = []
    for etiqueta in re.finditer(r"<g data-area=\"([^\"]*)\"([^>]*)/>", svg):
        atributos = dict(re.findall(r'data-([a-z]+)="([^"]*)"', etiqueta.group(2)))
        areas.append({
            "titulo": etiqueta.group(1),
            "subred": atributos.get("subred", ""),
            "x": float(atributos["x"]),
            "y": float(atributos["y"]),
            "ancho": float(atributos["ancho"]),
            "alto": float(atributos["alto"]),
            "nube": atributos.get("nube") == "1",
        })
    equipos = {}
    for etiqueta in re.finditer(r'<g data-rol="([^"]+)" data-x="([\d.]+)" data-y="([\d.]+)"', svg):
        equipos[etiqueta.group(1)] = (float(etiqueta.group(2)), float(etiqueta.group(3)))
    return {"ancho": float(lienzo.group(1)), "alto": float(lienzo.group(2)),
            "areas": areas, "equipos": equipos}


def rotulo(area: dict) -> str:
    """Lo que se lee en la caja de un área: su nombre y el bloque de direcciones que es."""
    if not area["subred"] or area["subred"] == area["titulo"]:
        return area["titulo"]
    return f"{area['titulo']} · {area['subred']}"


def contenido(lab: dict, svg: str, objetos: dict) -> dict:
    """El contenido del mapa: las áreas, los equipos y los cables, donde los pone el plano.

    `objetos` traduce el rol de cada equipo al número con el que la vista lo conoce. Un
    equipo del plano que no esté en la vista no se dibuja —y los cables que salen de él
    tampoco—, porque un elemento del mapa sin objeto detrás no lo acepta la vista.
    """
    donde = disposicion(svg)
    elementos, numero, elemento_de = [], 0, {}
    for area in donde["areas"]:
        numero += 1
        elementos.append({
            "id": numero, "type": ELEMENTO_ADORNO, "decorationType": ADORNO_CAJA,
            "flags": 0, "title": rotulo(area),
            "posX": round(area["x"]), "posY": round(area["y"]),
            "width": round(area["ancho"]), "height": round(area["alto"]),
        })
    for rol, (cx, cy) in sorted(donde["equipos"].items()):
        if rol not in objetos:
            continue
        numero += 1
        elemento_de[rol] = numero
        elementos.append({
            "id": numero, "type": ELEMENTO_OBJETO, "flags": 0,
            "objectId": int(objetos[rol]),
            "posX": round(cx - TAMANO_EQUIPO / 2), "posY": round(cy - TAMANO_EQUIPO / 2),
            "width": TAMANO_EQUIPO, "height": TAMANO_EQUIPO,
        })

    enlaces = []
    for cable in lab.get("links") or []:
        una, otra = cable["a"]["node"], cable["z"]["node"]
        if una not in elemento_de or otra not in elemento_de:
            continue
        enlaces.append({
            "element1": elemento_de[una], "element2": elemento_de[otra],
            "interface1": 0, "interface2": 0, "type": 0, "flags": 0,
            "name": "", "connectorName1": "", "connectorName2": "",
            "colorSource": 0, "color": 0, "colorProvider": "", "config": "",
        })
    return {
        "width": round(donde["ancho"]), "height": round(donde["alto"]),
        "elements": elementos, "links": enlaces,
    }


def _resumen_elemento(elemento: dict) -> tuple:
    """Lo que de verdad distingue un elemento de otro: dónde y qué enseña.

    El número de elemento no entra —lo reparte quien escribe— y el lienzo tampoco: lo que
    importa es que cada cosa esté en su sitio y sea la que es.
    """
    donde = (elemento.get("type"), int(elemento.get("posX") or 0), int(elemento.get("posY") or 0),
             int(elemento.get("width") or 0), int(elemento.get("height") or 0))
    if int(elemento.get("type") or 0) == ELEMENTO_OBJETO:
        return donde + ("equipo", int(elemento.get("objectId") or 0))
    return donde + ("adorno", int(elemento.get("decorationType") or 0), str(elemento.get("title") or ""))


def esta_al_dia(actual: dict | None, deseado: dict) -> bool:
    """¿El mapa que hay ya es el que el plano pide?

    Los enlaces se comparan por los equipos que unen y no por su número: la vista reparte
    los suyos, así que el número de enlace cambia al escribirlos y no significa nada.
    """
    if not actual:
        return False
    if _resumen_elemento_de(actual) != _resumen_elemento_de(deseado):
        return False
    return _resumen_cableado(actual) == _resumen_cableado(deseado)


def _resumen_elemento_de(mapa: dict) -> list:
    return sorted(_resumen_elemento(e) for e in mapa.get("elements") or [])


def _resumen_cableado(mapa: dict) -> list:
    """Los cables por los equipos que unen: `(objeto_a, objeto_b)`, sin repetir ni ordenar."""
    elementos = mapa.get("elements") or []
    nombre = {}
    for elemento in elementos:
        if int(elemento.get("type") or 0) == ELEMENTO_OBJETO:
            nombre[int(elemento.get("id") or 0)] = int(elemento.get("objectId") or 0)
        else:
            nombre[int(elemento.get("id") or 0)] = str(elemento.get("title") or "")
    lazos = set()
    for enlace in mapa.get("links") or []:
        una = nombre.get(int(enlace.get("element1") or 0))
        otra = nombre.get(int(enlace.get("element2") or 0))
        if una is None or otra is None:
            continue
        lazos.add(tuple(sorted((str(una), str(otra)))))
    return sorted(lazos)


def cuerpo(contenido_mapa: dict) -> str:
    """El cuerpo que se le manda a la vista: sólo lo que el API acepta escribir.

    La lectura devuelve claves que la escritura rechaza —`filter` y `linkScript` con nulo—,
    así que aquí sólo viajan las que definen el mapa: el lienzo y su contenido.
    """
    return json.dumps({
        "width": contenido_mapa["width"],
        "height": contenido_mapa["height"],
        "elements": contenido_mapa["elements"],
        "links": contenido_mapa["links"],
    })
