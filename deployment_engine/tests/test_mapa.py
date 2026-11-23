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
            # La caja va sin rótulo: el nombre y el bloque van en una caja de texto, que es
            # la única que se puede poner donde no pasen los cables.
            self.assertEqual(caja["title"], "")

    def test_cada_area_lleva_su_nombre_y_su_bloque_en_una_caja_de_texto(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        leidos = [json.loads(mapa.texto_de(e))["text"] for e in contenido["elements"]
                  if e["type"] == mapa.ELEMENTO_TEXTO]
        areas = mapa.disposicion(svg)["areas"]
        esperados = [texto for area in areas for texto in mapa.renglones(area)]
        self.assertEqual(leidos, esperados)
        # Cada área enseña su nombre y el bloque de direcciones entero, con su prefijo: era
        # lo que no se leía por culpa de los cables.
        for area in areas:
            textos = " · ".join(mapa.renglones(area))
            self.assertIn(area["titulo"], textos)
            if area["subred"] and area["subred"] != area["titulo"]:
                rango, _, prefijo = area["subred"].partition(" (")
                self.assertIn(rango, textos)
                self.assertIn(prefijo.rstrip(")"), textos)

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

    def test_las_posiciones_y_tamanos_viajan_como_enteros(self):
        """La vista lee la posición con `json_object_get_int32`: un decimal le llega como cero.

        Costó verlo: el mapa se escribía con las cajas de texto en «70.0» y la vista las
        dejaba todas en la esquina (0,0), otra vez debajo de los cables. `json.dumps` escribe
        los enteros como enteros, así que basta con que el contenido no lleve decimales.
        """
        for nombre in todos_los_laboratorios():
            contenido = mapa.contenido(laboratorio(nombre),
                                       plano.plano(laboratorio(nombre), "topologia"),
                                       con_vista(laboratorio(nombre)))
            cuerpo = mapa.cuerpo(contenido)
            for entero in (contenido["width"], contenido["height"]):
                self.assertIsInstance(entero, int)
            for elemento in contenido["elements"]:
                for clave in ("id", "type", "flags", "posX", "posY", "width", "height"):
                    if clave in elemento:
                        self.assertIsInstance(elemento[clave], int, f"{nombre}: {clave} de {elemento}")
            # Y el JSON que se escribe tampoco lleva un solo decimal en esas claves.
            for elemento in json.loads(cuerpo)["elements"]:
                for clave in ("posX", "posY", "width", "height"):
                    if clave in elemento:
                        self.assertNotIn(".", repr(elemento[clave]), f"{nombre}: {clave} decimal")

    def test_el_cuerpo_lleva_solo_lo_que_la_vista_acepta_escribir(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        cuerpo = json.loads(mapa.cuerpo(mapa.contenido(lab, svg, con_vista(lab))))
        self.assertEqual(sorted(cuerpo), ["defaultLinkColor", "defaultLinkColorSource",
                                          "defaultLinkRouting", "defaultLinkStyle",
                                          "defaultLinkWidth", "elements", "height",
                                          "links", "width"])
        for prohibida in ("filter", "linkScript", "background", "mapType", "layout"):
            self.assertNotIn(prohibida, cuerpo)
        self.assertTrue(all(v is not None for v in cuerpo.values()))

    def test_el_mapa_dice_como_quiere_sus_cables(self):
        """Sin esto la vista dibuja los cables a su criterio y se pierden en el fondo."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        cuerpo = json.loads(mapa.cuerpo(contenido))
        self.assertEqual(cuerpo["defaultLinkColor"], mapa.AZUL_PIZARRA)
        self.assertEqual(cuerpo["defaultLinkColorSource"], 0)
        self.assertEqual(cuerpo["defaultLinkWidth"], mapa.TRAZO_CABLE)
        self.assertEqual(cuerpo["defaultLinkStyle"], mapa.ESTILO_CABLE)
        self.assertEqual(cuerpo["defaultLinkRouting"], mapa.ENRUTADO_CABLE)
        # El trazo es más fino que el que la vista pone por defecto (0 = el suyo).
        self.assertLess(mapa.TRAZO_CABLE, 4)

    def test_el_mapa_se_reescribe_si_cambia_el_color_o_el_trazo_de_los_cables(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        for clave, valor in (("defaultLinkColor", 0x111111), ("defaultLinkWidth", 9),
                             ("defaultLinkStyle", 3), ("defaultLinkRouting", 2)):
            otro = json.loads(json.dumps(contenido))
            otro[clave] = valor
            self.assertFalse(mapa.esta_al_dia(otro, contenido), clave)

    def test_un_rotulo_que_cambia_de_texto_hace_reescribir_el_mapa(self):
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        otro = json.loads(json.dumps(contenido))
        caja = [e for e in otro["elements"] if e["type"] == mapa.ELEMENTO_TEXTO][0]
        dentro = json.loads(caja["TextBox"])
        dentro["text"] += " (y algo más)"
        caja["TextBox"] = json.dumps(dentro)
        self.assertFalse(mapa.esta_al_dia(otro, contenido))

    def test_el_rotulo_de_cada_area_no_lo_tapa_ningun_cable_ni_ningun_equipo(self):
        """El motivo de que los rótulos no vayan en la caja: los cables pasan por encima."""
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            donde = mapa.disposicion(svg)
            objetos = con_vista(lab)
            contenido = mapa.contenido(lab, svg, objetos)
            dentro = {rol: sitio for rol, sitio in donde["equipos"].items() if rol in objetos}
            cables = [(dentro[c["a"]["node"]], dentro[c["z"]["node"]]) for c in lab["links"]
                      if c["a"]["node"] in dentro and c["z"]["node"] in dentro]
            equipos = [(round(cx - mapa.TAMANO_EQUIPO / 2), round(cy - mapa.TAMANO_EQUIPO / 2),
                        mapa.TAMANO_EQUIPO, mapa.TAMANO_EQUIPO) for cx, cy in dentro.values()]
            for caja in [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_TEXTO]:
                texto = json.loads(mapa.texto_de(caja))["text"]
                ancho, alto = mapa.tamano_de_rotulo(texto)
                rect = (caja["posX"] - mapa.ETIQUETA_GUARDA, caja["posY"] - mapa.ETIQUETA_GUARDA,
                        ancho + 2 * mapa.ETIQUETA_GUARDA, alto + 2 * mapa.ETIQUETA_GUARDA)
                for uno, otro in cables:
                    self.assertFalse(mapa.corta(rect, uno, otro),
                                     f"{nombre}: un cable tapa «{texto}»")
                for hueco in equipos:
                    self.assertFalse(mapa.solapan(rect, hueco),
                                     f"{nombre}: un equipo queda debajo de «{texto}»")

    def test_el_rotulo_cae_dentro_del_area_que_rotula(self):
        """Dentro del área o pegado a ella: en un área diminuta no cabe de otra forma."""
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            areas = mapa.disposicion(svg)["areas"]
            contenido = mapa.contenido(lab, svg, con_vista(lab))
            cajas = [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_TEXTO]
            esperadas = [(area, texto) for area in areas for texto in mapa.renglones(area)]
            self.assertEqual(len(cajas), len(esperadas), nombre)
            for caja, (area, texto) in zip(cajas, esperadas):
                # El rótulo cae dentro del área o, como mucho, justo encima o justo debajo
                # —lo que ocupa su grupo entero, que es lo que se coloca—.
                margen = mapa.rotulos_de(area)[2] + 2 * mapa.ETIQUETA_MARGEN
                self.assertGreaterEqual(caja["posX"], area["x"])
                self.assertLessEqual(caja["posX"], area["x"] + area["ancho"])
                self.assertGreaterEqual(caja["posY"], area["y"] - margen)
                self.assertLessEqual(caja["posY"], area["y"] + area["alto"] + margen)

    def test_la_vista_devuelve_el_rotulo_con_otro_nombre_y_no_por_eso_reescribe(self):
        """Al escribirla viaja en `TextBox`; al leerla vuelve en `config`, como un texto."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        suyo = json.loads(json.dumps(contenido))
        for elemento in suyo["elements"]:
            if elemento["type"] == mapa.ELEMENTO_TEXTO:
                elemento["config"] = elemento.pop("TextBox")
                elemento.pop("width", None)
                elemento.pop("height", None)
        self.assertTrue(mapa.esta_al_dia(suyo, contenido))

    def test_un_cable_que_pasa_por_al_lado_no_cuenta_como_que_la_tapa(self):
        rect = (100, 100, 200, 24)
        self.assertTrue(mapa.corta(rect, (0, 112), (400, 112)))       # lo cruza
        self.assertTrue(mapa.corta(rect, (150, 0), (150, 400)))       # lo cruza de arriba abajo
        self.assertTrue(mapa.corta(rect, (120, 110), (180, 118)))     # nace dentro
        self.assertFalse(mapa.corta(rect, (0, 40), (400, 40)))        # pasa por encima
        self.assertFalse(mapa.corta(rect, (0, 300), (400, 300)))      # pasa por debajo
        self.assertFalse(mapa.corta(rect, (0, 0), (60, 200)))         # pasa por fuera

    def test_dos_rectangulos_se_solapan(self):
        self.assertTrue(mapa.solapan((0, 0, 10, 10), (5, 5, 10, 10)))
        self.assertTrue(mapa.solapan((0, 0, 10, 10), (0, 0, 10, 10)))
        self.assertFalse(mapa.solapan((0, 0, 10, 10), (10, 0, 10, 10)))   # se tocan, no se pisan
        self.assertFalse(mapa.solapan((0, 0, 10, 10), (0, 20, 10, 10)))

    def test_todos_los_laboratorios_del_repositorio_tienen_mapa(self):
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            contenido = mapa.contenido(lab, svg, con_vista(lab))
            self.assertTrue(contenido["elements"], f"{nombre} no da ni un elemento de mapa")
            self.assertTrue(mapa.esta_al_dia(contenido, contenido), nombre)


if __name__ == "__main__":
    unittest.main()
