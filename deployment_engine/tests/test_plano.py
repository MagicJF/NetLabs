# PROPÓSITO:   las pruebas del plano de topología. Un dibujo no se puede probar a ojo:
#              se comprueba la geometría —cada caja dentro de su caja, cada equipo dentro
#              de la suya, ninguna etiqueta encima de otra— para que el plano no vuelva a
#              salir con las áreas desbordadas ni con los nombres amontonados.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest), sin instalar nada.
# VER:         deployment_engine/tools/plano.py

import pathlib
import re
import sys
import ipaddress
import math
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import plano  # noqa: E402

LAB = "d_acme_dos_sedes"


def laboratorio(nombre=LAB):
    return yaml.safe_load((RAIZ / "labs" / nombre / f"{nombre}.yml").read_text())


def todos_los_laboratorios():
    """Cada laboratorio del repositorio que declare redes, que es donde hay plano."""
    return sorted(p.parent.name for p in (RAIZ / "labs").glob("*/*.yml")
                  if "networks" in yaml.safe_load(p.read_text()))


def montar(lab):
    """Deja el árbol medido y repartido, como lo deja el dibujo, y devuelve lo necesario.

    Se reutiliza el mismo camino que el plano de verdad: si la maqueta cambia, la prueba
    cambia con ella.
    """
    raiz = plano._arbol(lab)
    por_red = {r.nombre: r for r in plano._todas(raiz)
               if not r.nombre.startswith("espacio:")}
    plano._servicios(lab, por_red)
    casa_de, cruces, patas = {}, {}, {}
    for nodo in lab["nodes"]:
        patas[nodo["role"]] = [por_red[n] for n in nodo.get("networks") or [] if n in por_red]
        casa, grupos = plano._casa(nodo, por_red)
        if casa is None:
            continue
        casa_de[nodo["role"]] = casa
        if len(grupos) == 1:
            casa.nodos.append(nodo["role"])
            if nodo["type"] == "switch" and casa.enchufe is None:
                casa.enchufe = nodo["role"]
            continue
        cruces[nodo["role"]] = grupos
        if all(g in casa.hijas for g in grupos[:2]):
            casa.pasillos.append((grupos[0], grupos[1], nodo["role"]))
    plano._marcar_pasillos(raiz, cruces)
    plano._medir(raiz)
    plano._repartir(raiz, 0.0, 0.0)
    return raiz, casa_de, cruces, patas, por_red


def cabe(hija, madre) -> bool:
    return (hija.x >= madre.x - 0.5 and hija.y >= madre.y - 0.5
            and hija.x + hija.ancho <= madre.x + madre.ancho + 0.5
            and hija.y + hija.alto <= madre.y + madre.alto + 0.5)


def se_pisan(una, otra) -> bool:
    """Dos cajas del plano se pisan cuando sus rectángulos tienen área en común.

    Se mide la caja del símbolo —lo que ocupa el equipo en el dibujo— y no la del texto
    de su nombre: el nombre puede colocarse a cualquiera de los cuatro lados (§ la
    colocación de etiquetas), así que dos routers dibujados en el mismo punto pueden
    tener los rótulos repartidos alrededor y la comparación de textos los daría por
    buenos dejando pasar justo la superposición que se quiere evitar.
    """
    ax0, ay0, ax1, ay1 = una
    bx0, by0, bx1, by1 = otra
    return ax0 < bx1 and bx0 < ax1 and ay0 < by1 and by0 < ay1


def texto_del_svg(svg):
    """Las etiquetas del plano con la caja que ocupan, estimada por su tamaño de letra.

    El dibujo va dentro de un `g` con su traslación: sin sumarla, dos textos de
    coordenadas parecidas salen «montados» cuando en el plano están lejísimos.
    """
    trasladar = re.search(r'<g transform="translate\(([\d.-]+),([\d.-]+)\)">', svg)
    dx, dy = (float(trasladar.group(1)), float(trasladar.group(2))) if trasladar else (0, 0)
    cabeza = trasladar.start() if trasladar else len(svg)
    salida = []
    for m in re.finditer(r'<text x="([\d.-]+)" y="([\d.-]+)"([^>]*)>([^<]*)</text>', svg):
        x, y, attrs, texto = float(m.group(1)), float(m.group(2)), m.group(3), m.group(4)
        if m.start() > cabeza:
            x, y = x + dx, y + dy
        if not texto.strip():
            continue
        tam = float(re.search(r'font-size="([\d.]+)"', attrs).group(1)) \
            if "font-size" in attrs else 11.0
        ancho = len(texto) * tam * 0.52
        if 'text-anchor="middle"' in attrs:
            x0 = x - ancho / 2
        elif 'text-anchor="end"' in attrs:
            x0 = x - ancho
        else:
            x0 = x
        salida.append((x0, y - tam * 0.8, x0 + ancho, y + tam * 0.25, texto))
    return salida


class TestPlanoAnidado(unittest.TestCase):
    def test_cada_area_cabe_dentro_de_la_suya(self):
        """Un área que se sale de su madre convierte el plano en un amasijo de cajas."""
        for lab in todos_los_laboratorios():
            raiz, _, _, _, _ = montar(laboratorio(lab))
            for region in plano._todas(raiz):
                for hija in region.hijas:
                    with self.subTest(laboratorio=lab, hija=hija.nombre, madre=region.nombre):
                        self.assertTrue(cabe(hija, region),
                                        f"{hija.nombre} se sale de {region.nombre}")

    def test_cada_equipo_cabe_dentro_de_su_area(self):
        """Un equipo dibujado fuera de su área dice que pertenece a otra red."""
        for lab in todos_los_laboratorios():
            declaracion = laboratorio(lab)
            raiz, casa_de, cruces, _, _ = montar(declaracion)
            for region in plano._todas(raiz):
                for rol, (x, y) in region.dentro.items():
                    if rol in cruces:
                        continue  # los routers van a caballo: se salen a propósito
                    # No basta con el centro: el símbolo tiene su tamaño y, si se sale, el
                    # plano dice que ese equipo está fuera de su red.
                    ancho, alto = plano.SIMBOLO.get(
                        next(n["type"] for n in declaracion["nodes"] if n["role"] == rol),
                        (40, 40))
                    with self.subTest(laboratorio=lab, equipo=rol, area=region.nombre):
                        self.assertGreaterEqual(x - ancho / 2, region.x - 0.5)
                        self.assertLessEqual(x + ancho / 2, region.x + region.ancho + 0.5)
                        self.assertGreaterEqual(y - alto / 2, region.y - 0.5)
                        self.assertLessEqual(y + alto / 2, region.y + region.alto + 0.5)

    def test_la_nube_queda_fuera_de_la_empresa(self):
        """Internet es el exterior: dentro de la caja de ACME no puede estar."""
        for lab in todos_los_laboratorios():
            raiz, _, _, _, _ = montar(laboratorio(lab))
            nubes = [r for r in plano._todas(raiz) if r.nube]
            if not nubes:
                continue  # un laboratorio sin exterior no tiene nube que comprobar
            for nube in nubes:
                for area in plano._todas(raiz):
                    if area is nube or area.sintetica or not area.hijas:
                        continue
                    solapan = (nube.x < area.x + area.ancho and area.x < nube.x + nube.ancho
                               and nube.y < area.y + area.alto and area.y < nube.y + nube.alto)
                    with self.subTest(laboratorio=lab, nube=nube.nombre, area=area.nombre):
                        self.assertFalse(solapan, f"la nube pisa el área {area.nombre}")

    def test_los_puertos_de_un_router_entre_areas_no_se_escriben_uno_sobre_otro(self):
        """Un router con pata en tres LAN saca sus cables por el mismo punto del símbolo.

        Demuestra que el rótulo del puerto se ancla donde el cable ya va por su carril y
        no en la salida compartida: anclado en la salida, los tres números caen en la
        misma coordenada y el plano deja de decir qué puerto va a qué área (Greptile lo
        vio en un laboratorio de tres LAN apiladas; ninguno del repositorio las tiene, así
        que el caso se inventa aquí).
        """
        lab = {
            "lab": "tres_lan",
            "address_spaces": ["10.0.0.0/8"],
            "networks": [
                {"name": "lan1", "address": "10.1.0.0/24", "title": "Sede uno"},
                {"name": "lan2", "address": "10.2.0.0/24", "title": "Sede dos"},
                {"name": "lan3", "address": "10.3.0.0/24", "title": "Sede tres"},
            ],
            "nodes": [
                {"role": "rte1", "type": "router", "networks": ["lan1", "lan2", "lan3"]},
                {"role": "pst1", "type": "workstation", "networks": ["lan1"]},
                {"role": "pst2", "type": "workstation", "networks": ["lan2"]},
                {"role": "pst3", "type": "workstation", "networks": ["lan3"]},
            ],
            "links": [
                {"a": {"node": "rte1", "port": 2}, "z": {"node": "pst1", "port": 1}},
                {"a": {"node": "rte1", "port": 3}, "z": {"node": "pst2", "port": 1}},
                {"a": {"node": "rte1", "port": 4}, "z": {"node": "pst3", "port": 1}},
            ],
        }
        svg = plano.plano(lab, "topologia")
        puertos = [(float(m.group(1)), float(m.group(2)), m.group(3)) for m in re.finditer(
            r'<text x="([\d.-]+)" y="([\d.-]+)"[^>]*>(p\d+)</text>', svg)]
        self.assertGreaterEqual(len(puertos), 4, "faltan rótulos de puerto")
        choques = [(uno[2], otro[2]) for i, uno in enumerate(puertos)
                   for otro in puertos[i + 1:]
                   if abs(uno[0] - otro[0]) < 8 and abs(uno[1] - otro[1]) < 8]
        self.assertEqual(choques, [], f"puertos escritos uno sobre otro: {choques}")

    def test_ninguna_etiqueta_se_monta_sobre_otra(self):
        """Dos nombres encima del mismo punto no se leen: es lo que hace ilegible un plano."""
        for lab in todos_los_laboratorios():
            cajas = texto_del_svg(plano.plano(laboratorio(lab), "topologia"))
            choques = []
            for i, uno in enumerate(cajas):
                for otro in cajas[i + 1:]:
                    if uno[0] < otro[2] and otro[0] < uno[2] and \
                            uno[1] < otro[3] and otro[1] < uno[3]:
                        choques.append(f"{uno[4]} / {otro[4]}")
            with self.subTest(laboratorio=lab):
                self.assertEqual(choques, [], f"etiquetas montadas: {choques}")

    def test_cada_sede_tiene_su_salida_a_internet(self):
        """Con dos sedes y una sola nube, los dos routers no pueden acabar apilados.

        Se comparan las cajas de los símbolos —lo que ocupa cada equipo— y no el texto de
        sus nombres: el nombre se coloca a un lado del símbolo, así que medir el rótulo
        deja pasar dos routers dibujados en el mismo punto cuyas etiquetas se reparten
        alrededor, que es justo la superposición que esta prueba debe cazar.
        """
        declaracion = laboratorio()
        svg = plano.plano(declaracion, "topologia")
        _, _, cruces, _, _ = montar(declaracion)
        bordes = [rol for rol, grupos in cruces.items() if any(g.nube for g in grupos)]
        self.assertGreaterEqual(len(bordes), 2, "faltan routers de borde")
        simbolos = cajas_de_los_simbolos(svg, declaracion)
        cajas = {}
        for rol in bordes:
            self.assertIn(rol, simbolos, f"{rol} no aparece en el plano")
            cajas[rol] = simbolos[rol]
        for i, (rol, caja) in enumerate(cajas.items()):
            for otro, otra in list(cajas.items())[i + 1:]:
                self.assertFalse(se_pisan(caja, otra),
                                 f"{rol} y {otro} se dibujan uno encima del otro")

    def test_tres_sedes_apiladas_no_tapan_sus_routers_de_borde(self):
        """Tres sedes hermanas de la misma anchura salen por la misma nube y se apilan.

        Apiladas, sus centros caen en la misma vertical y los tres routers de borde
        apuntaban al mismo punto: se dibujaban uno encima de otro y sus cables parecían
        salir de un solo equipo. Se demuestra que el plano los reparte sobre la frontera
        que comparten —el techo de la compañía bajo la nube— y que ninguno queda debajo
        de otro. Greptile lo vio con tres sedes; ningún laboratorio del repositorio las
        tiene, así que el caso se inventa aquí.
        """
        lab = {
            "lab": "tres_sedes",
            "networks": [
                {"name": "transito", "address": "203.0.113.0/24", "title": "Internet",
                 "shape": "cloud"},
                {"name": "ny", "address": "10.20.0.0/16", "title": "Nueva York"},
                {"name": "tk", "address": "10.40.0.0/16", "title": "Tokio"},
                {"name": "bs", "address": "10.60.0.0/16", "title": "Buenos Aires"},
            ],
            "nodes": [
                {"role": "rte1", "type": "router", "networks": ["transito", "ny"]},
                {"role": "rte2", "type": "router", "networks": ["transito", "tk"]},
                {"role": "rte3", "type": "router", "networks": ["transito", "bs"]},
                {"role": "pst1", "type": "workstation", "networks": ["ny"]},
                {"role": "pst2", "type": "workstation", "networks": ["tk"]},
                {"role": "pst3", "type": "workstation", "networks": ["bs"]},
            ],
            "links": [
                {"a": {"node": "rte1", "port": 2}, "z": {"node": "pst1", "port": 1}},
                {"a": {"node": "rte2", "port": 2}, "z": {"node": "pst2", "port": 1}},
                {"a": {"node": "rte3", "port": 2}, "z": {"node": "pst3", "port": 1}},
            ],
        }
        svg = plano.plano(lab, "topologia")
        simbolos = cajas_de_los_simbolos(svg, lab)
        cajas = {}
        for rol in ("rte1", "rte2", "rte3"):
            self.assertIn(rol, simbolos, f"{rol} no aparece en el plano")
            cajas[rol] = simbolos[rol]
        for i, (rol, caja) in enumerate(cajas.items()):
            for otro, otra in list(cajas.items())[i + 1:]:
                self.assertFalse(se_pisan(caja, otra),
                                 f"{rol} y {otro} se dibujan uno encima del otro")

    def test_tres_sedes_con_salidas_distintas_no_tapan_sus_routers_de_borde(self):
        """Tres sedes hermanas apiladas salen por SU propia nube y siguen sin taparse.

        Con una salida distinta por sede —tres `exit`—, agrupar los routers por la nube que
        pisan deja un grupo de uno por salida: nadie separa a los demás, los tres comparten
        el techo de la compañía y el centro horizontal de las sedes, y los tres símbolos
        acaban en el mismo punto. Se demuestra que el plano los agrupa por el techo y los
        reparte por él, aunque cada uno salga por su nube. Greptile lo vio así; ningún
        laboratorio del repositorio tiene tres sedes, así que el caso se inventa aquí.
        """
        lab = {
            "lab": "tres_sedes_salidas",
            "networks": [
                {"name": "transito", "address": "203.0.113.0/24", "title": "Transito",
                 "shape": "cloud"},
                {"name": "ny_salida", "address": "172.30.10.0/24", "title": "Salida NY",
                 "shape": "cloud", "exit": True},
                {"name": "tk_salida", "address": "172.30.20.0/24", "title": "Salida TK",
                 "shape": "cloud", "exit": True},
                {"name": "bs_salida", "address": "172.30.30.0/24", "title": "Salida BS",
                 "shape": "cloud", "exit": True},
                {"name": "ny", "address": "10.20.0.0/16", "title": "Nueva York"},
                {"name": "tk", "address": "10.40.0.0/16", "title": "Tokio"},
                {"name": "bs", "address": "10.60.0.0/16", "title": "Buenos Aires"},
            ],
            "nodes": [
                {"role": "swc3", "type": "switch", "networks": ["transito"] * 3},
                {"role": "rte1", "type": "router", "networks": ["transito", "ny", "ny_salida"]},
                {"role": "rte2", "type": "router", "networks": ["transito", "tk", "tk_salida"]},
                {"role": "rte3", "type": "router", "networks": ["transito", "bs", "bs_salida"]},
                {"role": "pst1", "type": "workstation", "networks": ["ny"]},
                {"role": "pst2", "type": "workstation", "networks": ["tk"]},
                {"role": "pst3", "type": "workstation", "networks": ["bs"]},
            ],
            "links": [
                {"a": {"node": "swc3", "port": 1}, "z": {"node": "rte1", "port": 1}},
                {"a": {"node": "swc3", "port": 2}, "z": {"node": "rte2", "port": 1}},
                {"a": {"node": "swc3", "port": 3}, "z": {"node": "rte3", "port": 1}},
                {"a": {"node": "rte1", "port": 2}, "z": {"node": "pst1", "port": 1}},
                {"a": {"node": "rte2", "port": 2}, "z": {"node": "pst2", "port": 1}},
                {"a": {"node": "rte3", "port": 2}, "z": {"node": "pst3", "port": 1}},
            ],
        }
        svg = plano.plano(lab, "topologia")
        simbolos = cajas_de_los_simbolos(svg, lab)
        cajas = {}
        for rol in ("rte1", "rte2", "rte3"):
            self.assertIn(rol, simbolos, f"{rol} no aparece en el plano")
            cajas[rol] = simbolos[rol]
        for i, (rol, caja) in enumerate(cajas.items()):
            for otro, otra in list(cajas.items())[i + 1:]:
                self.assertFalse(se_pisan(caja, otra),
                                 f"{rol} y {otro} se dibujan uno encima del otro")

    def test_ninguna_area_se_sale_del_lienzo(self):
        """Una salida anclada fuera de la raíz no puede quedar recortada por el SVG.

        El lienzo cuenta la raíz y los equipos, pero una salida se ancla sobre la vertical
        de su sede y, con la sede cerca del borde, la nube —que es más ancha— cae fuera de
        la raíz: su nombre y su nube acabarían fuera del `viewBox`. Se demuestra con dos
        sedes hoja, un puesto cada una, que cada área del plano cabe dentro del lienzo
        después de aplicar su traslación.
        """
        lab = {
            "lab": "dos_sedes_salidas",
            "networks": [
                {"name": "transito", "address": "203.0.113.0/24", "title": "Transito",
                 "shape": "cloud"},
                {"name": "izq_salida", "address": "172.30.10.0/24", "title": "Salida izquierda",
                 "shape": "cloud", "exit": True},
                {"name": "der_salida", "address": "172.30.20.0/24", "title": "Salida derecha",
                 "shape": "cloud", "exit": True},
                {"name": "izq", "address": "10.20.0.0/16", "title": "Izquierda"},
                {"name": "der", "address": "10.40.0.0/16", "title": "Derecha"},
            ],
            "nodes": [
                {"role": "swc3", "type": "switch", "networks": ["transito"] * 3},
                {"role": "rte1", "type": "router", "networks": ["transito", "izq", "izq_salida"]},
                {"role": "rte2", "type": "router", "networks": ["transito", "der", "der_salida"]},
                {"role": "pst1", "type": "workstation", "networks": ["izq"]},
                {"role": "pst2", "type": "workstation", "networks": ["der"]},
            ],
            "links": [
                {"a": {"node": "swc3", "port": 1}, "z": {"node": "rte1", "port": 1}},
                {"a": {"node": "swc3", "port": 2}, "z": {"node": "rte2", "port": 1}},
                {"a": {"node": "rte1", "port": 2}, "z": {"node": "pst1", "port": 1}},
                {"a": {"node": "rte2", "port": 2}, "z": {"node": "pst2", "port": 1}},
            ],
        }
        svg = plano.plano(lab, "topologia")
        caja = re.search(r'<svg[^>]*width="([0-9.]+)" height="([0-9.]+)"', svg)
        tr = re.search(r'<g transform="translate\(([0-9.-]+),([0-9.-]+)\)">', svg)
        self.assertIsNotNone(caja, "el SVG no declara su tamaño")
        self.assertIsNotNone(tr, "el SVG no declara su traslación")
        ancho, alto = float(caja.group(1)), float(caja.group(2))
        dx, dy = float(tr.group(1)), float(tr.group(2))
        areas, _ = cajas_y_equipos(svg)
        self.assertTrue(areas, "el plano no declara ninguna área")
        for area in areas:
            with self.subTest(area=area["titulo"]):
                self.assertGreaterEqual(area["x"] + dx, -0.5,
                                        f"«{area['titulo']}» se sale por la izquierda")
                self.assertGreaterEqual(area["y"] + dy, -0.5,
                                        f"«{area['titulo']}» se sale por arriba")
                self.assertLessEqual(area["x"] + area["ancho"] + dx, ancho + 0.5,
                                     f"«{area['titulo']}» se sale por la derecha")
                self.assertLessEqual(area["y"] + area["alto"] + dy, alto + 0.5,
                                     f"«{area['titulo']}» se sale por abajo")


def cajas_y_equipos(svg):
    """Lo que el SVG declara de sí mismo: cada área y cada equipo con su centro.

    El plano lleva estos datos para poder comprobarlo por programa: la alternativa era
    mirar el dibujo a ojo, que es como se colaron las cajas desbordadas.
    """
    areas = [
        {"titulo": m.group(1), "x": float(m.group(2)), "y": float(m.group(3)),
         "ancho": float(m.group(4)), "alto": float(m.group(5)), "subred": m.group(6),
         "lema": m.group(7), "nube": m.group(8) == "1", "hijas": int(m.group(9))}
        for m in re.finditer(
            r'<g data-area="([^"]*)" data-x="([\d.-]+)" data-y="([\d.-]+)" '
            r'data-ancho="([\d.-]+)" data-alto="([\d.-]+)" data-subred="([^"]*)" '
            r'data-lema="([^"]*)" data-nube="(\d)" data-hijas="(\d+)"/>', svg)
    ]
    equipos = [
        {"rol": m.group(1), "x": float(m.group(2)), "y": float(m.group(3))}
        for m in re.finditer(r'<g data-rol="([^"]*)" data-x="([\d.-]+)" data-y="([\d.-]+)"', svg)
    ]
    return areas, equipos


def tramos_de(svg):
    """Cada tramo recto de cada línea del plano, como sus dos puntos.

    Una línea del plano es una `polyline` en ángulo recto: sus vértices son los puntos
    por donde pasa, y cada par consecutivo es un tramo. Sirve para saber por dónde va
    una pata —si cruza una caja que no le toca— sin mirar el dibujo a ojo.
    """
    tramos = []
    for m in re.finditer(r'<polyline points="([^"]*)"', svg):
        puntos = [tuple(float(v) for v in par.split(",")) for par in m.group(1).split()]
        tramos += list(zip(puntos, puntos[1:]))
    return tramos


def _visible(tramo, cajas):
    """Cuánto de un tramo queda a la vista, es decir, fuera de todo símbolo.

    El trozo de cable que va por dentro de un símbolo no se ve: lo tapa el propio
    equipo. Para saber si dos cables se dibujan como uno hay que medir sólo lo que
    asoma, o el tramo que los dos comparten bajo el switch contaría como defecto.
    """
    (x1, y1), (x2, y2) = tramo
    largo = math.hypot(x2 - x1, y2 - y1)
    if not largo:
        return 0.0
    oculto = 0.0
    for caja in cajas:
        dentro = recorte(tramo, caja)
        if dentro:
            oculto += (dentro[1] - dentro[0]) * largo
    return max(0.0, largo - oculto)


def solape_a_la_vista(uno, otro, cajas):
    """El tramo que dos cables comparten a la vista: pegados, se leen como uno solo.

    Se buscan los tramos colineales de los dos —misma recta horizontal o vertical— y
    se mide cuánto se pisan fuera de los símbolos. Dos cables que salen del mismo
    switch por el mismo punto y a la misma altura comparten su tramo de salida y el
    plano enseña un bus que no existe: donde hay un cable por cliente, una línea que
    se ramifica.
    """
    total = 0.0
    for (ax1, ay1), (ax2, ay2) in uno:
        for (bx1, by1), (bx2, by2) in otro:
            if (abs(ax1 - ax2) < 1 and abs(bx1 - bx2) < 1
                    and abs(ax1 - bx1) < 1):
                lo = max(min(ay1, ay2), min(by1, by2))
                hi = min(max(ay1, ay2), max(by1, by2))
                if hi > lo:
                    total += _visible(((ax1, lo), (ax1, hi)), cajas)
            elif (abs(ay1 - ay2) < 1 and abs(by1 - by2) < 1
                    and abs(ay1 - by1) < 1):
                lo = max(min(ax1, ax2), min(bx1, bx2))
                hi = min(max(ax1, ax2), max(bx1, bx2))
                if hi > lo:
                    total += _visible(((lo, ay1), (hi, ay1)), cajas)
    return total


def tramos_de_los_cables(svg):
    """Cada cable del plano con sus dos puntas y los tramos rectos que dibuja.

    Un cable se escribe con `polyline` cuando dobla y con `line` cuando va recto, así
    que leer sólo uno de los dos deja cables sin mirar, y un cable que no se lee es un
    cable que puede tachar cualquier cosa sin que nadie se entere.
    """
    salida = []
    for m in re.finditer(r'<g class="cable" data-a="([^"]*)" data-pa="[^"]*" '
                         r'data-z="([^"]*)" data-pz="[^"]*">(.*?)</g>', svg):
        tramos = []
        for recorrido in re.findall(r'points="([^"]*)"', m.group(3)):
            puntos = [tuple(float(v) for v in par.split(",")) for par in recorrido.split()]
            tramos += list(zip(puntos, puntos[1:]))
        for x1, y1, x2, y2 in re.findall(
                r'x1="([\d.-]+)" y1="([\d.-]+)" x2="([\d.-]+)" y2="([\d.-]+)"', m.group(3)):
            tramos.append(((float(x1), float(y1)), (float(x2), float(y2))))
        salida.append(((m.group(1), m.group(2)), tramos))
    return salida


def recorte(tramo, caja):
    """La parte del tramo que cae dentro de una caja, como intervalo de sus parámetros.

    Se recorta la recta contra el rectángulo en vez de muestrear puntos: un cable que
    roza una esquina también es un cable que tacha lo que hay en ella, y el muestreo se
    lo salta cuando el cruce es corto.
    """
    (ax, ay), (bx, by) = tramo
    x0, y0, x1, y1 = caja
    t0, t1 = 0.0, 1.0
    for p, q in ((-(bx - ax), ax - x0), (bx - ax, x1 - ax),
                 (-(by - ay), ay - y0), (by - ay, y1 - ay)):
        if p == 0:
            if q < 0:
                return None
            continue
        corte = q / p
        if p < 0:
            t0 = max(t0, corte)
        else:
            t1 = min(t1, corte)
        if t0 > t1:
            return None
    return t0, t1


def cajas_de_los_simbolos(svg, lab):
    """La caja que ocupa el símbolo de cada equipo, por rol."""
    tipos = {n["role"]: n["type"] for n in lab["nodes"]}
    salida = {}
    for m in re.finditer(r'<g data-rol="([^"]*)" data-x="([\d.-]+)" data-y="([\d.-]+)"', svg):
        ancho, alto = plano.SIMBOLO[tipos[m.group(1)]]
        x, y = float(m.group(2)), float(m.group(3))
        salida[m.group(1)] = (x - ancho / 2, y - alto / 2, x + ancho / 2, y + alto / 2)
    return salida


def cajas_de_los_rotulos(svg):
    """La caja del nombre de cada equipo y de cada área: el cuerpo grande del plano.

    Sólo el nombre. Es lo que se usa para saber qué se está mirando, y una línea que lo
    tacha deja el equipo sin identificar; las direcciones van en cuerpo menor y taparlas
    estrecha el dato, no el nombre.
    """
    salida = []
    for m in re.finditer(r'<text x="([\d.-]+)" y="([\d.-]+)"([^>]*)>([^<]*)</text>', svg):
        x, y, attrs, texto = float(m.group(1)), float(m.group(2)), m.group(3), m.group(4)
        tam = re.search(r'font-size="([\d.]+)"', attrs)
        if not texto.strip() or tam is None or float(tam.group(1)) != 12.5:
            continue
        ancho = len(texto) * 12.5 * 0.52
        if 'text-anchor="middle"' in attrs:
            x0 = x - ancho / 2
        elif 'text-anchor="end"' in attrs:
            x0 = x - ancho
        else:
            x0 = x
        salida.append((x0, y - 12.5 * 0.8, x0 + ancho, y + 12.5 * 0.25, texto))
    return salida


def routers_de_borde(lab):
    """Los equipos con una pata en la nube, con el título de la caja de su sede.

    El título —y no el nombre interno— es lo que el plano escribe en su SVG, y la sede es
    la red de la pata terrestre: la única caja que ese router puede cabalgar.
    """
    # La pata terrestre es la red que declara el laboratorio, no el área que el reparto
    # acaba envolviendo al router: el plano lo apoya en el borde de la red que conecta.
    _, _, _, patas, _ = montar(laboratorio(lab))
    salida = []
    for nodo in laboratorio(lab)["nodes"]:
        redes = patas.get(nodo["role"]) or []
        tierra = [r for r in redes if not r.nube]
        if any(r.nube for r in redes) and tierra:
            salida.append((nodo["role"], tierra[0].titulo))
    return salida


class TestLoQueElPlanoDeclara(unittest.TestCase):
    def test_una_caja_con_diez_hijas_se_lee_igual_que_una_con_una(self):
        """El patrón pedía una sola cifra, y un área con diez hijas se caía de la lista.

        Demuestra que la lectura no pierde ninguna caja: lo que no se lee no existe para
        las pruebas que recorren las áreas, así que la que se perdía no fallaba —se
        esfumaba— y su geometría dejaba de comprobarse.
        """
        svg = ('<g data-area="sede" data-x="1.0" data-y="2.0" data-ancho="3.0" '
               'data-alto="4.0" data-subred="" data-lema="" data-nube="0" data-hijas="10"/>')
        areas, _ = cajas_y_equipos(svg)
        self.assertEqual([a["hijas"] for a in areas], [10])


class TestConvenciones(unittest.TestCase):
    def test_toda_area_escribe_su_red_igual(self):
        """Misma notación en todas: `10.20.55.0 - 10.20.55.255 (/24)`.

        El bloque se lee de un golpe —de dónde a dónde llega— y el prefijo va al
        final. Antes se escribía `10.20.55.x/24`: dos áreas con prefijos distintos
        había que compararlas contando octetos, y el `x` no dice dónde acaba la red.
        """
        for lab in todos_los_laboratorios():
            areas, _ = cajas_y_equipos(plano.plano(laboratorio(lab), "topologia"))
            for area in areas:
                if not area["subred"]:
                    continue
                with self.subTest(laboratorio=lab, area=area["titulo"]):
                    detalle = f"{area['titulo']}: {area['subred']!r}"
                    if "/" not in area["subred"]:
                        # Una sola dirección: sin prefijo, que no dice nada.
                        ipaddress.ip_address(area["subred"])
                        continue
                    m = re.match(r"^(\d+\.\d+\.\d+\.\d+) - (\d+\.\d+\.\d+\.\d+) "
                                 r"\(/(\d+)\)$", area["subred"])
                    self.assertIsNotNone(m, f"no es el bloque de una red: {detalle}")
                    inicio, fin, prefijo = m.group(1), m.group(2), int(m.group(3))
                    red = ipaddress.ip_network(f"{inicio}/{prefijo}", strict=False)
                    self.assertEqual(str(red.network_address), inicio, detalle)
                    self.assertEqual(str(red.broadcast_address), fin, detalle)

    def test_el_router_de_borde_cabalga_la_frontera_de_la_empresa(self):
        """Una pata en la sede y otra en Internet: se apoya en el techo de la caja que
        envuelve a su sede —la frontera por la que se sale— y asoma bajo su nube.

        Metido dentro de la caja parecía un equipo más de la red privada, que es justo lo
        que no es; y puesto en el techo de la sede, sin más, no se veía que fuese la salida.
        """
        for lab in todos_los_laboratorios():
            areas, equipos = cajas_y_equipos(plano.plano(laboratorio(lab), "topologia"))
            por_rol = {e["rol"]: e for e in equipos}
            nubes = [a for a in areas if a["nube"]]
            for rol, sede in routers_de_borde(lab):
                with self.subTest(laboratorio=lab, equipo=rol):
                    # Sin símbolo no hay nada que comprobar, y saltárselo dejaba la prueba
                    # pasando por un router de borde que el plano no dibuja.
                    self.assertIn(rol, por_rol, f"{rol} no tiene símbolo en el plano")
                    e = por_rol[rol]
                    sede_caja = next((a for a in areas if a["titulo"] == sede), None)
                    self.assertIsNotNone(sede_caja, f"{sede} no es una caja del plano")
                    # Las cajas que envuelven a su sede: la empresa, y lo que la envuelva.
                    madres = [a for a in areas if a is not sede_caja
                              and a["x"] < sede_caja["x"] + 1
                              and a["y"] < sede_caja["y"] - 1
                              and a["x"] + a["ancho"] > sede_caja["x"] + sede_caja["ancho"] - 1
                              and a["y"] + a["alto"] > sede_caja["y"] + sede_caja["alto"] - 1]
                    # La frontera es el techo de la caja más exterior: media pata dentro de
                    # la empresa y media fuera, que es donde está la salida a Internet.
                    techo = min([m["y"] for m in madres], default=sede_caja["y"])
                    self.assertAlmostEqual(e["y"], techo, delta=1.0,
                                           msg=f"{rol} no cabalga la frontera con Internet")
                    # Y asoma bajo su nube: lejos de ella no se lee como su salida.
                    self.assertTrue(any(n["x"] <= e["x"] <= n["x"] + n["ancho"] for n in nubes),
                                    f"{rol} no está bajo la nube de Internet")

    def test_el_pie_del_plano_queda_a_plomo(self):
        """Las redes de un mismo plano miden lo mismo: con altos distintos, el pie se descose."""
        for lab in todos_los_laboratorios():
            areas, _ = cajas_y_equipos(plano.plano(laboratorio(lab), "topologia"))
            hojas = [a for a in areas if not a["hijas"] and not a["nube"]]
            if len(hojas) < 2:
                continue
            altos = {round(a["alto"], 1) for a in hojas}
            anchos = {round(a["ancho"], 1) for a in hojas}
            with self.subTest(laboratorio=lab):
                self.assertEqual(len(altos), 1, f"redes de altos distintos: {sorted(altos)}")
                self.assertEqual(len(anchos), 1, f"redes de anchos distintos: {sorted(anchos)}")


class TestLosCablesNoTachanElPlano(unittest.TestCase):
    def test_ningun_cable_atraviesa_un_simbolo_ajeno_ni_un_nombre(self):
        """Un cable que cruza un símbolo o un nombre dibuja un enlace que no existe.

        Demuestra que ningún cable pasa por encima del equipo de al lado ni tacha ningún
        nombre. Lo segundo es lo que hacía la pata de la nube: al no tener borde propio
        por arriba subía hasta el final del lienzo, atravesaba el switch que la sacaba y
        su rótulo, y bajaba luego por la misma coordenada —una línea encima del nombre y
        el plano deja de decir qué equipo es cuál—. El símbolo de la propia punta es el
        único sitio por donde un cable pasa por dentro, y va tapado por el símbolo.
        """
        for lab in todos_los_laboratorios():
            declaracion = laboratorio(lab)
            svg = plano.plano(declaracion, "topologia")
            simbolos = cajas_de_los_simbolos(svg, declaracion)
            rotulos = cajas_de_los_rotulos(svg)
            for (a, z), tramos in tramos_de_los_cables(svg):
                with self.subTest(laboratorio=lab, cable=f"{a}-{z}"):
                    for tramo in tramos:
                        for rol, caja in simbolos.items():
                            if rol in (a, z):
                                continue
                            self.assertIsNone(recorte(tramo, caja),
                                              f"el cable {a}-{z} pasa por el símbolo de {rol}")
                        for x0, y0, x1, y1, texto in rotulos:
                            self.assertIsNone(recorte(tramo, (x0, y0, x1, y1)),
                                              f"el cable {a}-{z} tacha el nombre {texto!r}")

    def test_los_cables_de_un_mismo_equipo_no_se_dibujan_como_uno(self):
        """Los cables que salen de un switch salen cada uno por su sitio.

        El switch de un departamento lleva un cable por cliente. Si todos salen del
        mismo punto y a la misma altura, el trozo que asoma se dibuja una sola vez y
        el plano enseña una línea que se ramifica donde hay tres cables. Se mide lo
        que queda a la vista: el tramo que va por dentro del símbolo no cuenta, que
        lo tapa el propio equipo.
        """
        for lab in todos_los_laboratorios():
            declaracion = laboratorio(lab)
            svg = plano.plano(declaracion, "topologia")
            cajas = list(cajas_de_los_simbolos(svg, declaracion).values())
            por_equipo: dict[str, list] = {}
            for (a, z), tramos in tramos_de_los_cables(svg):
                por_equipo.setdefault(a, []).append(((a, z), tramos))
                if z != a:
                    por_equipo.setdefault(z, []).append(((a, z), tramos))
            for rol, suyos in por_equipo.items():
                for i, ((a, z), unos) in enumerate(suyos):
                    for (b, w), otros in suyos[i + 1:]:
                        if (a, z) == (b, w):
                            continue          # el mismo cable, contado por su otra punta
                        solape = solape_a_la_vista(unos, otros, cajas)
                        with self.subTest(laboratorio=lab, cables=f"{a}-{z} y {b}-{w}"):
                            self.assertLess(
                                solape, 12,
                                f"los cables {a}-{z} y {b}-{w} salen de {rol} pegados: "
                                f"{solape:.1f} px dibujados como una sola línea")


if __name__ == "__main__":
    unittest.main()

class ElPlanoSueltoAlLadoDeLaPagina(unittest.TestCase):
    """El plano va, además, como fichero `.svg` al lado de la página del laboratorio.

    Los dos salen del mismo dibujo —el que produce `plano.plano(lab, "topologia")`— en la
    misma pasada de `./netlabs docs`, así que un fichero distinto del dibujo de hoy es un
    plano viejo, y eso se ve aquí sin abrir la página.
    """

    def test_el_fichero_de_cada_laboratorio_es_su_plano(self):
        for nombre in todos_los_laboratorios():
            fichero = RAIZ / "labs" / nombre / f"{nombre}-topologia.svg"
            esperado = plano.plano(laboratorio(nombre), "topologia").rstrip("\n") + "\n"
            self.assertTrue(fichero.exists(), f"{nombre}: no tiene plano suelto")
            self.assertEqual(fichero.read_text(), esperado, f"{nombre}: plano viejo")

    def test_un_laboratorio_sin_redes_no_tiene_plano_suelto(self):
        # El de control no declara redes: no hay nada que dibujar, y un `.svg` vacío al
        # lado sería un fichero que dice que hay un plano que no existe.
        for carpeta in (RAIZ / "labs").iterdir():
            if carpeta.name in todos_los_laboratorios():
                continue
            self.assertFalse((carpeta / f"{carpeta.name}-topologia.svg").exists())

    def test_el_fichero_lleva_el_mismo_dibujo_que_la_pagina(self):
        for nombre in todos_los_laboratorios():
            pagina = (RAIZ / "labs" / nombre / f"{nombre}.md").read_text()
            dentro = pagina.split("<svg", 1)[1].split("</svg>", 1)[0]
            fichero = (RAIZ / "labs" / nombre / f"{nombre}-topologia.svg").read_text()
            self.assertEqual("<svg" + dentro + "</svg>", fichero.rstrip("\n"), nombre)


class LasSalidasDeCadaSede(unittest.TestCase):
    """Cada sede sale por su nube, y la línea lo dice sin cruzar la de la otra.

    Las redes con `exit: true` no llevan cable declarado (tienen una sola punta, ADR
    0018), así que su pata la dibuja el plano desde la interfaz del router. Si el plano
    no la dibujara, la nube quedaría suelta y parecería que la sede no sale; y si la
    dibujara subiendo en vertical con las nubes apiladas, cruzaría por dentro de la
    nube de otra sede y el plano diría que sale por la que no es.
    """

    def test_cada_salida_tiene_su_pata_y_no_cruza_la_nube_de_otra(self):
        lab = laboratorio("f_acme_cuatro_departamentos")
        svg = plano.plano(lab, "topologia")
        areas, _ = cajas_y_equipos(svg)
        salidas = [a for a in areas if a["nube"] and a["lema"]]
        self.assertGreaterEqual(len(salidas), 2, "el laboratorio no tiene dos salidas")
        for salida in salidas:
            base = salida["y"] + salida["alto"] - 8
            suyos = [t for t in tramos_de(svg)
                     if any(abs(y - base) < 1.0
                            and salida["x"] <= x <= salida["x"] + salida["ancho"]
                            for x, y in t)]
            with self.subTest(salida=salida["titulo"]):
                self.assertTrue(suyos, "la nube de la salida no tiene ninguna pata")
                for otro in salidas:
                    if otro is salida:
                        continue
                    caja = (otro["x"], otro["y"], otro["x"] + otro["ancho"],
                            otro["y"] + otro["alto"])
                    for tramo in suyos:
                        self.assertFalse(
                            plano._cruza(tramo, caja),
                            f"la pata de «{salida['titulo']}» cruza «{otro['titulo']}»")

    def test_cada_salida_se_dibuja_sobre_el_router_de_su_sede(self):
        """La salida de una sede no cuelga del centro: cuelga de ESA sede.

        El router de borde que se asoma a la salida tiene también una pata en su sede, y
        eso es lo que ata una nube a su sitio. Se demuestra que el centro de la nube cae
        sobre la vertical de su router de borde —dentro de un píxel—, que las dos salidas
        no comparten x (o se leerían como una sola apilada, sin saber cuál es de quién) y
        que el tránsito del proveedor sigue siendo una banda centrada por encima de la
        empresa, por donde pasan las dos sedes. La salida es de su sede; el tránsito, del
        centro.
        """
        lab = laboratorio("f_acme_cuatro_departamentos")
        svg = plano.plano(lab, "topologia")
        areas, equipos = cajas_y_equipos(svg)
        # Qué router se asoma a cada salida: el que tiene una pata en la red de la salida
        # y otra en su sede. Es dato del laboratorio, no una suposición.
        _, _, _, patas, _ = montar(lab)
        router_de_salida: dict[str, str] = {}
        nombre_de_titulo: dict[str, str] = {}
        for clave, suyas in patas.items():
            for red in suyas:
                nombre_de_titulo[red.titulo] = red.nombre
            salida = next((r for r in suyas if r.exit), None)
            if salida is not None:
                router_de_salida[salida.nombre] = clave
        xy = {e["rol"]: (e["x"], e["y"]) for e in equipos}

        salidas = [a for a in areas if a["nube"] and a["lema"]]
        self.assertEqual(len(salidas), 2, "el laboratorio no tiene dos salidas")
        centros = []
        for salida in salidas:
            rol = router_de_salida[nombre_de_titulo[salida["titulo"]]]
            cx = salida["x"] + salida["ancho"] / 2
            centros.append(round(cx, 1))
            with self.subTest(salida=salida["titulo"]):
                self.assertIn(rol, xy, f"{rol} no tiene símbolo en el plano")
                self.assertAlmostEqual(
                    cx, xy[rol][0], delta=1.0,
                    msg=f"«{salida['titulo']}» no cae sobre la vertical de {rol}")
        self.assertEqual(len(set(centros)), len(centros),
                         f"las dos salidas comparten x: {centros}")

        # El tránsito (la nube sin `exit`) sigue centrado y por encima de la empresa: la
        # banda del techo, por donde se cruzan las dos sedes.
        transito = next(a for a in areas if a["nube"] and not a["lema"])
        empresa = min((a for a in areas if not a["nube"] and a["hijas"]),
                      key=lambda a: a["y"])
        self.assertAlmostEqual(transito["x"] + transito["ancho"] / 2,
                               empresa["x"] + empresa["ancho"] / 2, delta=1.0,
                               msg="el tránsito ya no está centrado sobre la empresa")
        self.assertLessEqual(transito["y"] + transito["alto"], empresa["y"] + 0.5,
                             "el tránsito ya no es una banda por encima de la empresa")
