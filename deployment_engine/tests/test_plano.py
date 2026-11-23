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
import re
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
        """Con dos sedes y una sola nube, los dos routers no pueden acabar apilados."""
        svg = plano.plano(laboratorio(), "topologia")
        raiz, casa_de, cruces, _, _ = montar(laboratorio())
        bordes = [rol for rol, grupos in cruces.items() if any(g.nube for g in grupos)]
        self.assertGreaterEqual(len(bordes), 2, "faltan routers de borde")
        puestos = {}
        for rol in bordes:
            m = re.search(rf'<text x="([\d.]+)" y="([\d.]+)"[^>]*>{rol}</text>', svg)
            self.assertIsNotNone(m, f"{rol} no aparece en el plano")
            puestos[rol] = (float(m.group(1)), float(m.group(2)))
        for i, (rol, (x, y)) in enumerate(puestos.items()):
            for otro, (ox, oy) in list(puestos.items())[i + 1:]:
                self.assertGreater(abs(x - ox) + abs(y - oy), 40,
                                   f"{rol} y {otro} se dibujan uno encima del otro")


def cajas_y_equipos(svg):
    """Lo que el SVG declara de sí mismo: cada área y cada equipo con su centro.

    El plano lleva estos datos para poder comprobarlo por programa: la alternativa era
    mirar el dibujo a ojo, que es como se colaron las cajas desbordadas.
    """
    areas = [
        {"titulo": m.group(1), "x": float(m.group(2)), "y": float(m.group(3)),
         "ancho": float(m.group(4)), "alto": float(m.group(5)), "subred": m.group(6),
         "nube": m.group(7) == "1", "hijas": int(m.group(8))}
        for m in re.finditer(
            r'<g data-area="([^"]*)" data-x="([\d.-]+)" data-y="([\d.-]+)" '
            r'data-ancho="([\d.-]+)" data-alto="([\d.-]+)" data-subred="([^"]*)" '
            r'data-nube="(\d)" data-hijas="(\d)"/>', svg)
    ]
    equipos = [
        {"rol": m.group(1), "x": float(m.group(2)), "y": float(m.group(3))}
        for m in re.finditer(r'<g data-rol="([^"]*)" data-x="([\d.-]+)" data-y="([\d.-]+)"', svg)
    ]
    return areas, equipos


def routers_de_borde(lab):
    """Los equipos con una pata en la nube: son los que van a caballo de su sede."""
    _, _, cruces, _, _ = montar(laboratorio(lab))
    salida = []
    for rol, grupos in cruces.items():
        if any(g.nube for g in grupos):
            salida.append((rol, [g for g in grupos if not g.nube][0].nombre))
    return salida


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

    def test_el_router_de_borde_cabalga_el_borde_de_su_sede(self):
        """Una pata en la sede y otra en Internet: tiene que intersecar la sede."""
        for lab in todos_los_laboratorios():
            areas, equipos = cajas_y_equipos(plano.plano(laboratorio(lab), "topologia"))
            por_rol = {e["rol"]: e for e in equipos}
            for rol, sede in routers_de_borde(lab):
                if rol not in por_rol:
                    continue
                e = por_rol[rol]
                with self.subTest(laboratorio=lab, equipo=rol):
                    abajo = [a for a in areas
                             if a["x"] - 0.5 <= e["x"] <= a["x"] + a["ancho"] + 0.5
                             and a["y"] - 0.5 <= e["y"] <= a["y"] + a["alto"] + 0.5]
                    self.assertTrue(abajo, f"{rol} no cae dentro de su caja")
                    # El borde de su sede pasa por el centro del símbolo: media pata
                    # dentro de la red y media fuera. Y no el de la caja que la envuelve.
                    cabalga = [a for a in abajo if abs(a["y"] - e["y"]) <= 1.0]
                    self.assertTrue(cabalga, f"{rol} no está a caballo del techo de su sede")
                    # Y la caja que cabalga es su sede, no la caja que envuelve la
                    # empresa: la sede tiene que estar dentro de otra caja.
                    sede_caja = cabalga[0]
                    madres = [a for a in areas if a is not sede_caja
                              and a["x"] < sede_caja["x"] + 1 and a["y"] < sede_caja["y"] - 1
                              and a["x"] + a["ancho"] > sede_caja["x"] + sede_caja["ancho"] - 1
                              and a["y"] + a["alto"] > sede_caja["y"] + sede_caja["alto"] - 1]
                    self.assertTrue(madres, f"{rol} cabalga la caja exterior, no {sede}")

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
