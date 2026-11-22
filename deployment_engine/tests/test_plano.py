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
         with self.subTest(laboratorio=lab):
          raiz, _, _, _, _ = montar(laboratorio(lab))
        for region in plano._todas(raiz):
            for hija in region.hijas:
                with self.subTest(hija=hija.nombre, madre=region.nombre):
                    self.assertTrue(cabe(hija, region),
                                    f"{hija.nombre} se sale de {region.nombre}")

    def test_cada_equipo_cabe_dentro_de_su_area(self):
        """Un equipo dibujado fuera de su área dice que pertenece a otra red."""
        for lab in todos_los_laboratorios():
         with self.subTest(laboratorio=lab):
          raiz, casa_de, cruces, _, _ = montar(laboratorio(lab))
        for region in plano._todas(raiz):
            for rol, (x, y) in region.dentro.items():
                if rol in cruces:
                    continue  # los routers van a caballo: se salen a propósito
                # No basta con el centro: el símbolo tiene su tamaño y, si se sale, el
                # plano dice que ese equipo está fuera de su red.
                ancho, alto = plano.SIMBOLO.get(
                    next(n["type"] for n in laboratorio(lab)["nodes"] if n["role"] == rol),
                    (40, 40))
                with self.subTest(equipo=rol, area=region.nombre):
                    self.assertGreaterEqual(x - ancho / 2, region.x - 0.5)
                    self.assertLessEqual(x + ancho / 2, region.x + region.ancho + 0.5)
                    self.assertGreaterEqual(y - alto / 2, region.y - 0.5)
                    self.assertLessEqual(y + alto / 2, region.y + region.alto + 0.5)

    def test_la_nube_queda_fuera_de_la_empresa(self):
        """Internet es el exterior: dentro de la caja de ACME no puede estar."""
        for lab in todos_los_laboratorios():
         with self.subTest(laboratorio=lab):
          raiz, _, _, _, _ = montar(laboratorio(lab))
        nubes = [r for r in plano._todas(raiz) if r.nube]
        self.assertTrue(nubes, "el laboratorio no declara ninguna nube")
        for nube in nubes:
            for area in plano._todas(raiz):
                if area is nube or area.sintetica or not area.hijas:
                    continue
                solapan = (nube.x < area.x + area.ancho and area.x < nube.x + nube.ancho
                           and nube.y < area.y + area.alto and area.y < nube.y + nube.alto)
                with self.subTest(nube=nube.nombre, area=area.nombre):
                    self.assertFalse(solapan, f"la nube pisa el área {area.nombre}")

    def test_ninguna_etiqueta_se_monta_sobre_otra(self):
        """Dos nombres encima del mismo punto no se leen: es lo que hace ilegible un plano."""
        for lab in todos_los_laboratorios():
         with self.subTest(laboratorio=lab):
          svg = plano.plano(laboratorio(lab), "topologia")
        cajas = texto_del_svg(svg)
        choques = []
        for i, uno in enumerate(cajas):
            for otro in cajas[i + 1:]:
                if uno[0] < otro[2] and otro[0] < uno[2] and \
                        uno[1] < otro[3] and otro[1] < uno[3]:
                    choques.append(f"{uno[4]} / {otro[4]}")
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


if __name__ == "__main__":
    unittest.main()