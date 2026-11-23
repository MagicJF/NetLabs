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
#              La vista dibuja los cables **por encima** de todo lo demás, así que un
#              rótulo colocado donde pasa un cable se queda ilegible. Por eso el nombre y
#              el bloque de cada área no van en el rótulo de su caja —que la vista pega
#              arriba a la izquierda, justo donde cruzan los cables que bajan de la red
#              troncal— sino en una caja de texto que se coloca en el primer rincón de su
#              área por el que no pase ningún cable ni se apoye ningún equipo. La
#              colocación es de este módulo, y por eso se puede comprobar por programa
#              (test_mapa) en vez de a ojo.
# VER:         docs/diseno.md §3.4 (el mapa a medida);
#              docs/decisiones/0004-el-mapa-de-la-vista-lo-coloca-el-plano.md

import json
import re

# Cómo nombra la vista a las cosas del mapa. Son los números que viajan en el JSON del
# API: el tipo de elemento y, dentro de los adornos, la caja de grupo.
ELEMENTO_OBJETO = 1        # un equipo de la vista
ELEMENTO_ADORNO = 2        # una figura del mapa, no un equipo
ADORNO_CAJA = 0            # la caja de grupo: un rectángulo con su rótulo
ELEMENTO_TEXTO = 5         # una caja de texto: un rótulo suelto

TAMANO_EQUIPO = 100        # lado del hueco de un equipo en el mapa, como la vista

# Cómo se ve el mapa. Los colores van en BGR —la vista los guarda así y los lee así— y
# son de la familia que se lee sobre un fondo claro: la vista pinta el relleno de una caja
# con el color del adorno muy rebajado y su borde entero, y el borde es lo que se ve.
BLANCO, NEGRO = 0xFFFFFF, 0x000000
GRIS_DEL_BORDE = 0x999999      # el filo del rótulo: dice dónde acaba el texto
AZUL_PIZARRA = 0x573B1F        # rgb(31, 59, 87): el cable, oscuro sobre el gris del fondo
TRAZO_CABLE = 2                # la vista pone 4 por defecto: con 2 el cable tapa menos
ESTILO_CABLE = 1               # continua, como el plano
ENRUTADO_CABLE = 1             # recto, como el plano

# Lo que el mapa pide de sí mismo: el color y el trazo de sus cables. Sin esto la vista
# los dibuja con su criterio —un gris ancho y translúcido que se pierde en el fondo— y no
# hay forma de pedirlo desde fuera.
AJUSTES_DEL_MAPA = {
    "defaultLinkColorSource": 0,          # color propio, no el del estado del enlace
    "defaultLinkColor": AZUL_PIZARRA,
    "defaultLinkWidth": TRAZO_CABLE,
    "defaultLinkStyle": ESTILO_CABLE,
    "defaultLinkRouting": ENRUTADO_CABLE,
}

# Cuánto ocupa un rótulo. La vista mide el texto con la fuente que le digo, así que aquí
# se estima —ancho por letra más su relleno— y se guarda un margen: una estimación corta
# dejaría el rótulo pisando un cable sin que nadie se enterase.
ETIQUETA_FUENTE = 9            # puntos: se lee y deja sitio en áreas de 300 de ancho
ETIQUETA_LETRA = 6.4           # ancho estimado de una letra a esa fuente
ETIQUETA_RELLENO = 20          # el aire de la caja alrededor del texto
ETIQUETA_ALTO = 24
ETIQUETA_MARGEN = 10           # aire entre el rótulo y el borde de su área
ETIQUETA_GUARDA = 6            # de sobra, al comprobar si un cable lo pisa
ETIQUETA_APOYO = 2             # aire entre el nombre de un área y su bloque, debajo
CUADRICULA = 5                 # rincones que se prueban por cada lado, si los de fuera fallan


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


def renglones(area: dict) -> list:
    """Los renglones que rotulan un área: el nombre con su prefijo y, debajo, el bloque.

    Van partidos así —y no «nombre» y «bloque entero»— porque manda el renglón más ancho:
    «10.20.55.0 - 10.20.55.255 (/24)» mide 218 px y hay cuatro áreas del repositorio —una
    por cada sede de un laboratorio, y la de un laboratorio pequeño— donde no cabe sin
    pisar un cable, mientras que sin el prefijo mide 167 y sí cabe. El prefijo se lee en el
    primer renglón, junto al nombre, que es donde no estorba.
    """
    if not area["subred"] or area["subred"] == area["titulo"]:
        return [area["titulo"]]
    rango, _, prefijo = area["subred"].partition(" (")
    if not prefijo:
        return [area["titulo"], area["subred"]]
    return [f"{area['titulo']} ({prefijo.rstrip(')')})", rango]


def rotulos_de(area: dict) -> tuple:
    """Los rótulos de un área y lo que ocupan juntos: el nombre y, debajo, su bloque.

    Se colocan como un solo bloque —el nombre arriba, el bloque debajo— porque así se leen;
    dos búsquedas por separado acababan con el nombre arriba del área y su bloque al otro
    extremo. Y se busca una sola vez porque lo que ocupa el grupo es lo que hay que
    esquivar: si el grupo cabe en un hueco, cada renglón cabe dentro del grupo.
    """
    textos = renglones(area)
    anchos = [tamano_de_rotulo(texto)[0] for texto in textos]
    altos = [tamano_de_rotulo(texto)[1] for texto in textos]
    return textos, max(anchos), sum(altos) + ETIQUETA_APOYO * (len(textos) - 1)


def tamano_de_rotulo(texto: str) -> tuple:
    """Lo que se estima que ocupa ese rótulo en el mapa: ancho y alto."""
    return round(len(texto) * ETIQUETA_LETRA + ETIQUETA_RELLENO), ETIQUETA_ALTO


def candidatos(area: dict, ancho: float, alto: float) -> list:
    """Dónde puede ir un rótulo, por orden de preferencia: dentro de su área y, si no cabe,
    pegado a ella.

    Primero los rincones —arriba y abajo, a la izquierda antes que a la derecha, que es
    donde el plano pone sus rótulos— y luego el centro de los lados. Después una rejilla
    por toda el área: en un área grande y muy cableada —dos sedes con sus routers de borde
    y sus cables cruzando de una a otra— los rincones pueden quedar todos debajo de un
    cable. Y si ni así, justo encima y justo debajo del área, que el rótulo se lee igual y
    sigue diciendo de qué área es.
    """
    izquierda = area["x"] + ETIQUETA_MARGEN
    arriba = area["y"] + ETIQUETA_MARGEN
    derecha = max(izquierda, area["x"] + area["ancho"] - ancho - ETIQUETA_MARGEN)
    abajo = max(arriba, area["y"] + area["alto"] - alto - ETIQUETA_MARGEN)
    medio_x = max(izquierda, min(derecha, area["x"] + (area["ancho"] - ancho) / 2))
    medio_y = max(arriba, min(abajo, area["y"] + (area["alto"] - alto) / 2))

    orden = [(izquierda, arriba), (derecha, arriba)]
    for fila in range(CUADRICULA):
        for columna in range(CUADRICULA):
            orden.append((round(izquierda + (derecha - izquierda) * columna / (CUADRICULA - 1)),
                          round(arriba + (abajo - arriba) * fila / (CUADRICULA - 1))))
    orden += [(izquierda, abajo), (derecha, abajo), (izquierda, medio_y), (derecha, medio_y),
              (izquierda, max(0.0, area["y"] - alto - ETIQUETA_MARGEN)),
              (izquierda, area["y"] + area["alto"] + ETIQUETA_MARGEN)]

    sitios, vistos = [], set()
    for sitio in orden:
        if sitio not in vistos:
            vistos.add(sitio)
            sitios.append(sitio)
    return sitios


def sitio_libre(area: dict, ancho: float, alto: float, cables: list, ocupado: list) -> tuple:
    """El primer rincón del área donde el rótulo no queda tapado por un cable ni por un equipo.

    `cables` son los segmentos que dibuja la vista (`((x, y), (x, y))`) y `ocupado` los
    rectángulos que ya hay puestos. Si no queda ninguno libre se devuelve el primero: un
    rótulo tapado se ve mal, pero un rótulo fuera de su área no dice nada.
    """
    for x, y in candidatos(area, ancho, alto):
        rectangulo = (x - ETIQUETA_GUARDA, y - ETIQUETA_GUARDA,
                      ancho + 2 * ETIQUETA_GUARDA, alto + 2 * ETIQUETA_GUARDA)
        if any(solapan(rectangulo, otro) for otro in ocupado):
            continue
        if any(corta(rectangulo, uno, otro) for uno, otro in cables):
            continue
        return x, y
    return candidatos(area, ancho, alto)[0]


def solapan(uno: tuple, otro: tuple) -> bool:
    """¿Se pisan dos rectángulos? (`(x, y, ancho, alto)`)."""
    return not (uno[0] + uno[2] <= otro[0] or otro[0] + otro[2] <= uno[0]
                or uno[1] + uno[3] <= otro[1] or otro[1] + otro[3] <= uno[1])


def corta(rectangulo: tuple, uno: tuple, otro: tuple) -> bool:
    """¿El segmento que va de `uno` a `otro` toca ese rectángulo?

    Recorte de Liang–Barsky: se acorta el segmento contra cada lado del rectángulo y si
    algo queda del segmento, lo toca.
    """
    x, y, ancho, alto = rectangulo
    izquierda, arriba, derecha, abajo = x, y, x + ancho, y + alto
    t0, t1 = 0.0, 1.0
    dx, dy = otro[0] - uno[0], otro[1] - uno[1]
    for avance, distancia in ((-dx, uno[0] - izquierda), (dx, derecha - uno[0]),
                              (-dy, uno[1] - arriba), (dy, abajo - uno[1])):
        if avance == 0:
            if distancia < 0:
                return False
            continue
        cruce = distancia / avance
        if avance < 0:
            if cruce > t1:
                return False
            t0 = max(t0, cruce)
        else:
            if cruce < t0:
                return False
            t1 = min(t1, cruce)
    return True


def config_de_rotulo(texto: str) -> str:
    """La caja de texto que la vista dibuja: el rótulo, con su fondo y su filo.

    La vista guarda esta configuración como un texto —un JSON dentro del JSON del mapa—,
    y es la parte del elemento que dice **qué se lee**.
    """
    return json.dumps({
        "text": texto,
        "backgroundColor": BLANCO, "textColor": NEGRO,
        "borderColor": GRIS_DEL_BORDE, "borderRequired": True,
        "fontSize": ETIQUETA_FUENTE, "drillDownObjectId": 0,
    }, ensure_ascii=False)


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
            "flags": 0, "title": "",
            "posX": round(area["x"]), "posY": round(area["y"]),
            "width": round(area["ancho"]), "height": round(area["alto"]),
        })

    en_donde = {rol: (cx, cy) for rol, (cx, cy) in donde["equipos"].items() if rol in objetos}
    for rol, (cx, cy) in sorted(en_donde.items()):
        numero += 1
        elemento_de[rol] = numero
        elementos.append({
            "id": numero, "type": ELEMENTO_OBJETO, "flags": 0,
            "objectId": int(objetos[rol]),
            "posX": round(cx - TAMANO_EQUIPO / 2), "posY": round(cy - TAMANO_EQUIPO / 2),
            "width": TAMANO_EQUIPO, "height": TAMANO_EQUIPO,
        })

    enlaces = []
    cables = []
    for cable in lab.get("links") or []:
        una, otra = cable["a"]["node"], cable["z"]["node"]
        if una not in elemento_de or otra not in elemento_de:
            continue
        cables.append((en_donde[una], en_donde[otra]))
        enlaces.append({
            "element1": elemento_de[una], "element2": elemento_de[otra],
            "interface1": 0, "interface2": 0, "type": 0, "flags": 0,
            "name": "", "connectorName1": "", "connectorName2": "",
            "colorSource": 0, "color": 0, "colorProvider": "", "config": "",
        })

    # Los equipos ocupan su hueco: un rótulo encima de uno se leería mal aunque no pasara
    # ningún cable por ahí.
    ocupado = [(round(cx - TAMANO_EQUIPO / 2), round(cy - TAMANO_EQUIPO / 2),
                TAMANO_EQUIPO, TAMANO_EQUIPO) for cx, cy in en_donde.values()]
    # Los rótulos se colocan de la zona más pequeña a la más grande: la pequeña —una sede
    # con su router y su switch, que es casi todo equipo y cable— no tiene dónde elegir, y
    # la grande que la envuelve sí. Al revés, el rótulo del laboratorio se ponía en el
    # primer hueco que encontraba —dentro de una sede— y dejaba a la sede sin sitio.
    puestos = {}
    for indice, area in sorted(enumerate(donde["areas"]), key=lambda par: par[1]["ancho"] * par[1]["alto"]):
        textos, ancho, alto = rotulos_de(area)
        x, y = sitio_libre(area, ancho, alto, cables, ocupado)
        ocupado.append((x, y, ancho, alto))
        puestos[indice] = (textos, x, y)

    for indice, area in enumerate(donde["areas"]):
        textos, x, y = puestos[indice]
        renglon = 0
        for texto in textos:
            _, alto_texto = tamano_de_rotulo(texto)
            numero += 1
            elementos.append({
                "id": numero, "type": ELEMENTO_TEXTO, "flags": 0,
                # Enteros: la vista lee la posición con `json_object_get_int32` y un decimal
                # —«70.0»— le llega como cero. La caja se queda en la esquina y vuelve a
                # estar debajo de un cable, que es justo lo que se viene a arreglar.
                "posX": round(x), "posY": round(y + renglon), "TextBox": config_de_rotulo(texto),
            })
            renglon += alto_texto + ETIQUETA_APOYO

    return {
        **AJUSTES_DEL_MAPA,
        "width": round(donde["ancho"]), "height": round(donde["alto"]),
        "elements": elementos, "links": enlaces,
    }


def texto_de(elemento: dict) -> str:
    """La configuración de una caja de texto, la haya escrito quien la haya escrito.

    Al escribirla viaja en `TextBox` y al leerla vuelve en `config`: la vista no la
    devuelve con el mismo nombre con el que se le manda.
    """
    crudo = elemento.get("config") or elemento.get("TextBox") or ""
    return str(crudo)


def _resumen_elemento(elemento: dict) -> tuple:
    """Lo que de verdad distingue un elemento de otro: dónde y qué enseña.

    El número de elemento no entra —lo reparte quien escribe— y el lienzo tampoco: lo que
    importa es que cada cosa esté en su sitio y sea la que es.
    """
    donde = (elemento.get("type"), int(elemento.get("posX") or 0), int(elemento.get("posY") or 0),
             int(elemento.get("width") or 0), int(elemento.get("height") or 0))
    if int(elemento.get("type") or 0) == ELEMENTO_OBJETO:
        return donde + ("equipo", int(elemento.get("objectId") or 0))
    if int(elemento.get("type") or 0) == ELEMENTO_TEXTO:
        return donde + ("texto", _config_ordenada(elemento))
    return donde + ("adorno", int(elemento.get("decorationType") or 0), str(elemento.get("title") or ""))


def _config_ordenada(elemento: dict) -> str:
    """La configuración de una caja de texto, ordenada: para compararla, no para leerla.

    La vista devuelve el mismo texto que se le mandó, pero con sus claves en su orden y
    sus acentos escapados; ordenada, dos configuraciones iguales se comparan igual.
    """
    crudo = texto_de(elemento)
    if not crudo:
        return ""
    try:
        return json.dumps(json.loads(crudo), sort_keys=True, ensure_ascii=False)
    except ValueError:
        return crudo


def esta_al_dia(actual: dict | None, deseado: dict) -> bool:
    """¿El mapa que hay ya es el que el plano pide?

    Los enlaces se comparan por los equipos que unen y no por su número: la vista reparte
    los suyos, así que el número de enlace cambia al escribirlos y no significa nada.
    """
    if not actual:
        return False
    if resumen_ajustes(actual) != resumen_ajustes(deseado):
        return False
    if _resumen_elemento_de(actual) != _resumen_elemento_de(deseado):
        return False
    return _resumen_cableado(actual) == _resumen_cableado(deseado)


def resumen_ajustes(mapa: dict) -> tuple:
    """El color y el trazo de los cables: el mapa también cambia cuando cambian ellos."""
    return tuple(int(mapa.get(clave) or 0) for clave in sorted(AJUSTES_DEL_MAPA))


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
            nombre[int(elemento.get("id") or 0)] = str(elemento.get("title") or "") or _config_ordenada(elemento)
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
    así que aquí sólo viajan las que definen el mapa: el lienzo, su contenido y cómo se
    dibujan sus cables.
    """
    return json.dumps({
        **{clave: contenido_mapa[clave] for clave in AJUSTES_DEL_MAPA},
        "width": contenido_mapa["width"],
        "height": contenido_mapa["height"],
        "elements": contenido_mapa["elements"],
        "links": contenido_mapa["links"],
    }, ensure_ascii=False)
