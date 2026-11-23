# PROPÓSITO:   las pruebas del mapa de la vista. Un mapa no se puede probar a ojo: se
#              comprueba que cada equipo queda donde el plano lo dibuja, que cada red es
#              la caja que el plano enseña y que los cables son los del laboratorio; y que
#              un mapa ya escrito no se vuelve a escribir.
# INVARIANTES: ninguna prueba habla con el API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest), sin instalar nada.
# VER:         deployment_engine/tools/mapa.py

import json
import pathlib
import sys
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import mapa  # noqa: E402
import plano  # noqa: E402

LAB = "e_tres_routers"


def laboratorio(nombre=LAB):
    return yaml.safe_load((RAIZ / "labs" / nombre / f"{nombre}.yml").read_text())


def todos_los_laboratorios():
    return sorted(p.parent.name for p in (RAIZ / "labs").glob("*/*.yml")
                  if "networks" in yaml.safe_load(p.read_text()))


def con_vista(lab, cuantos=None):
    """El laboratorio con los equipos de red ya en la vista: rol → número de objeto."""
    donde = mapa.disposicion(plano.plano(lab, "topologia"))
    equipos = [rol for rol in sorted(donde["equipos"])
               if any(n["role"] == rol and n["type"] in ("router", "switch", "firewall")
                      for n in lab["nodes"])]
    return {rol: 300 + i for i, rol in enumerate(equipos[:cuantos])}


class ElMapaDelLaboratorio(unittest.TestCase):
    def test_cada_area_del_plano_es_una_caja_del_mapa(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        donde = mapa.disposicion(svg)
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        cajas = [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_ADORNO]
        self.assertEqual(len(cajas), len(donde["areas"]))
        for caja, area in zip(cajas, donde["areas"]):
            self.assertEqual(caja["decorationType"], mapa.ADORNO_CAJA)
            self.assertEqual((caja["posX"], caja["posY"]),
                             (round(area["x"]), round(area["y"])))
            self.assertEqual((caja["width"], caja["height"]),
                             (round(area["ancho"]), round(area["alto"])))
            self.assertIn(area["titulo"], caja["title"])

    def test_cada_equipo_de_la_vista_queda_donde_el_plano_lo_pone(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        donde = mapa.disposicion(svg)
        objetos = con_vista(lab)
        contenido = mapa.contenido(lab, svg, objetos)
        equipos = [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_OBJETO]
        self.assertEqual(len(equipos), len(objetos))
        for elemento in equipos:
            rol = [r for r, i in objetos.items() if i == elemento["objectId"]][0]
            cx, cy = donde["equipos"][rol]
            self.assertEqual((elemento["posX"], elemento["posY"]),
                             (round(cx - mapa.TAMANO_EQUIPO / 2), round(cy - mapa.TAMANO_EQUIPO / 2)))

    def test_un_equipo_sin_vista_no_se_dibuja_y_sus_cables_tampoco(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        completo = mapa.contenido(lab, svg, con_vista(lab))
        corto = mapa.contenido(lab, svg, con_vista(lab, cuantos=1))
        self.assertLess(len(corto["elements"]), len(completo["elements"]))
        self.assertLess(len(corto["links"]), len(completo["links"]))
        self.assertNotIn("wsp1", [e.get("title") for e in corto["elements"] if e["type"] == mapa.ELEMENTO_ADORNO])

    def test_los_cables_del_mapa_son_los_del_laboratorio(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        objetos = con_vista(lab)
        contenido = mapa.contenido(lab, svg, objetos)
        # Cada cable del laboratorio cuyos dos extremos están en la vista sale una vez.
        elemento_de = {e["objectId"]: e["id"] for e in contenido["elements"]
                       if e["type"] == mapa.ELEMENTO_OBJETO}
        esperados = set()
        for cable in lab["links"]:
            una, otra = cable["a"]["node"], cable["z"]["node"]
            if una in objetos and otra in objetos:
                esperados.add(tuple(sorted((elemento_de[objetos[una]], elemento_de[objetos[otra]]))))
        vistos = {tuple(sorted((l["element1"], l["element2"]))) for l in contenido["links"]}
        self.assertEqual(vistos, esperados)
        self.assertGreater(len(vistos), 0)

    def test_un_mapa_ya_escrito_no_se_vuelve_a_escribir(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        self.assertTrue(mapa.esta_al_dia(contenido, contenido))

    def test_el_mapa_se_reescribe_si_algo_se_movio_o_falta(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))

        movido = json.loads(json.dumps(contenido))
        movido["elements"][0]["posX"] += 40
        self.assertFalse(mapa.esta_al_dia(movido, contenido))

        sin_cable = json.loads(json.dumps(contenido))
        sin_cable["links"] = sin_cable["links"][1:]
        self.assertFalse(mapa.esta_al_dia(sin_cable, contenido))

        sin_equipo = json.loads(json.dumps(contenido))
        sin_equipo["elements"] = [e for e in sin_equipo["elements"] if e["id"] != 6]
        self.assertFalse(mapa.esta_al_dia(sin_equipo, contenido))

    def test_el_mapa_ya_esta_al_dia_aunque_la_vista_numere_a_su_manera(self):
        """La vista reparte los números de enlace: eso no puede hacer reescribir el mapa."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        suyo = json.loads(json.dumps(contenido))
        for desplazamiento, enlace in enumerate(suyo["links"], start=1):
            enlace["element1"] += 0  # los elementos son los mismos
            enlace["element2"] += 0
        suyo["elements"] = list(reversed(suyo["elements"]))
        for elemento in suyo["elements"]:
            elemento["id"] += 1000
        for enlace in suyo["links"]:
            enlace["element1"] += 1000
            enlace["element2"] += 1000
        self.assertTrue(mapa.esta_al_dia(suyo, contenido))

    def test_el_cuerpo_lleva_solo_lo_que_la_vista_acepta_escribir(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        cuerpo = json.loads(mapa.cuerpo(mapa.contenido(lab, svg, con_vista(lab))))
        self.assertEqual(sorted(cuerpo), ["elements", "height", "links", "width"])
        for prohibida in ("filter", "linkScript", "background", "mapType", "layout"):
            self.assertNotIn(prohibida, cuerpo)
        self.assertTrue(all(v is not None for v in cuerpo.values()))

    def test_todos_los_laboratorios_del_repositorio_tienen_mapa(self):
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            contenido = mapa.contenido(lab, svg, con_vista(lab))
            self.assertTrue(contenido["elements"], f"{nombre} no da ni un elemento de mapa")
            self.assertTrue(mapa.esta_al_dia(contenido, contenido), nombre)


if __name__ == "__main__":
    unittest.main()
