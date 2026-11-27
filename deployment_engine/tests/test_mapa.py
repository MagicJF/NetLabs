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

import identity  # noqa: E402
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


def con_vista_toda(lab):
    """El laboratorio con TODOS sus equipos en la vista: también los puestos y servidores.

    Los de red no bastan para comprobar el reparto: el hueco que se comía el bloque de
    direcciones de un área era el de un puesto.
    """
    donde = mapa.disposicion(plano.plano(lab, "topologia"))
    return {rol: 300 + i for i, rol in enumerate(sorted(donde["equipos"]))}


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
        esperados = [texto for area in areas for texto in mapa.rotulos_de(area)[0]]
        self.assertEqual(sorted(leidos), sorted(esperados))
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
            ancho, alto = mapa.hueco_de(donde, rol)
            self.assertEqual((elemento["posX"], elemento["posY"]),
                             (round(cx - ancho / 2), round(cy - alto / 2)))
            # Y el hueco es el del símbolo del plano: el de 100 llegaba hasta el bloque de
            # direcciones de su área y se lo comía.
            self.assertEqual((elemento["width"], elemento["height"]), (round(ancho), round(alto)))

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
                                          "links", "objectDisplayMode", "width"])
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

    def test_los_equipos_se_dibujan_como_iconos(self):
        """Una ficha de nombre e IP por equipo tapa el dibujo y los cables que pasan debajo."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        cuerpo = json.loads(mapa.cuerpo(mapa.contenido(lab, svg, con_vista(lab))))
        self.assertEqual(cuerpo["objectDisplayMode"], mapa.MODO_ICONO)
        # Los números son los de la vista (`MapObjectDisplayMode`), no se eligen a ojo.
        self.assertEqual(mapa.MODO_ICONO, 0, "0 es el icono; 2 es la ficha grande")

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

    def test_un_mapa_ajustado_a_mano_no_se_pisa(self):
        """Manda quien lo ha movido: el reparto del plano no borra su trabajo."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        deseado = mapa.contenido(lab, svg, con_vista_toda(lab))
        sello = mapa.huella(deseado)
        movido = json.loads(json.dumps(deseado))
        movido["elements"][0]["posX"] = movido["elements"][0]["posX"] + 40
        escribir, motivo = mapa.hay_que_escribir(movido, deseado, sello)
        self.assertFalse(escribir, "el mapa ajustado a mano se ha reescrito")
        self.assertEqual(motivo, "ajustado a mano")

    def test_sin_ajuste_el_mapa_sigue_al_plano(self):
        """La huella guardada distingue «lo tocó una persona» de «cambió el plano»."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        deseado = mapa.contenido(lab, svg, con_vista_toda(lab))
        self.assertTrue(mapa.hay_que_escribir(None, deseado)[0], "sin mapa no se escribe")
        escribir, motivo = mapa.hay_que_escribir(deseado, deseado, mapa.huella(deseado))
        self.assertFalse(escribir)
        self.assertEqual(motivo, "ya es el del plano")
        otro = json.loads(json.dumps(deseado))
        otro["elements"][0]["posX"] = otro["elements"][0]["posX"] + 40
        escribir, motivo = mapa.hay_que_escribir(deseado, otro, mapa.huella(deseado))
        self.assertTrue(escribir, "el plano ha cambiado y no se escribe")
        self.assertEqual(motivo, "el plano ha cambiado")

    def test_ningun_equipo_se_queda_debajo_de_un_rotulo_de_area(self):
        """Un icono encima de la cabecera de su red la tapa: eso sí que no se lee.

        Un cable fino que cruce el texto se admite —la alternativa era arrinconar la
        cabecera al fondo del área—, pero un equipo no: tapa la letra y además miente,
        porque parece dentro de esa red y lo está de la de al lado.
        """
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            donde = mapa.disposicion(svg)
            objetos = con_vista_toda(lab)
            contenido = mapa.contenido(lab, svg, objetos)
            equipos = []
            for rol, (cx, cy) in donde["equipos"].items():
                if rol not in objetos:
                    continue
                ancho, alto = mapa.hueco_de(donde, rol)
                equipos.append((round(cx - ancho / 2), round(cy - alto / 2), round(ancho), round(alto)))
            cajas = [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_TEXTO]
            por_area, i = [], 0
            for area in donde["areas"]:
                textos = mapa.rotulos_de(area)[0]
                cajas_area = cajas[i:i + len(textos)]
                i += len(textos)
                # La cabecera es un bloque —título y rango—: sus renglones van pegados a
                # propósito, así que se compara el bloque entero contra los demás.
                x0 = min(c["posX"] for c in cajas_area)
                y0 = min(c["posY"] for c in cajas_area)
                x1 = max(c["posX"] + mapa.tamano_de_rotulo(json.loads(mapa.texto_de(c))["text"])[0]
                         for c in cajas_area)
                y1 = max(c["posY"] + mapa.ETIQUETA_ALTO for c in cajas_area)
                rect = (x0, y0, x1 - x0, y1 - y0)
                for hueco in equipos:
                    self.assertFalse(mapa.solapan(rect, hueco),
                                     f"{nombre}: un equipo tapa «{area['titulo']}»")
                for otro, quien in por_area:
                    self.assertFalse(mapa.solapan(rect, otro),
                                     f"{nombre}: «{area['titulo']}» y «{quien}» se montan")
                por_area.append((rect, area["titulo"]))

    def test_el_rotulo_cae_dentro_del_area_que_rotula(self):
        """El rótulo de un área cae siempre dentro de su área: nunca en la de al lado."""
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            areas = mapa.disposicion(svg)["areas"]
            objetos = con_vista(lab)
            contenido = mapa.contenido(lab, svg, objetos)
            etiquetas = [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_TEXTO]
            esperadas = [(area, texto) for area in areas for texto in mapa.rotulos_de(area)[0]]
            self.assertEqual(len(etiquetas), len(esperadas), nombre)
            for caja, (area, texto) in zip(etiquetas, esperadas):
                self.assertEqual(json.loads(mapa.texto_de(caja))["text"], texto, nombre)
                ancho, alto = mapa.tamano_de_rotulo(texto)
                self.assertGreaterEqual(caja["posX"], area["x"], nombre)
                self.assertLessEqual(caja["posX"] + ancho, area["x"] + area["ancho"], nombre)
                self.assertGreaterEqual(caja["posY"], area["y"], nombre)
                self.assertLessEqual(caja["posY"] + alto, area["y"] + area["alto"], nombre)

    def test_el_rotulo_de_cada_area_va_en_su_esquina(self):
        """La cabecera de un área se lee arriba a la izquierda, como la de la primera.

        Antes se probaba la rejilla entera del área y, en cuanto un cable rozaba la esquina,
        el rótulo se iba al otro extremo: la cabecera de una sede aparecía abajo y no había
        forma de saber por qué. Si la esquina está ocupada, se corre por el mismo borde.
        """
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            donde = mapa.disposicion(svg)
            cajas = [e for e in mapa.contenido(lab, svg, con_vista_toda(lab))["elements"]
                     if e["type"] == mapa.ELEMENTO_TEXTO]
            i = 0
            for area in donde["areas"]:
                ancho, _ = mapa.tamano_de_rotulo(mapa.rotulos_de(area)[0][0])
                self.assertLessEqual(cajas[i]["posY"], round(area["y"] + area["alto"] / 2),
                                     f"{nombre}: «{area['titulo']}» se fue a la mitad de abajo")
                self.assertLessEqual(cajas[i]["posX"] + ancho, area["x"] + area["ancho"],
                                     f"{nombre}: «{area['titulo']}» no cabe en su área")
                # Y en la banda de la izquierda: si un cable o un equipo tapan la esquina,
                # el rótulo baja por su borde izquierdo o se corre a lo sumo al centro del
                # área, nunca al otro lado —que es lo que hacía parecer que cada cabecera
                # se colocase donde le daba la gana.
                self.assertLessEqual(cajas[i]["posX"], round(area["x"] + area["ancho"] / 2),
                                     f"{nombre}: «{area['titulo']}» se fue al otro lado")
                i += len(mapa.rotulos_de(area)[0])

    def test_la_nube_dice_que_es_la_salida_y_no_un_bloque(self):
        """La nube de Internet no lleva bloque de direcciones: lleva lo que es.

        «Internet (/24)» con su rango se leía como un segmento más de la casa, y la nube es
        justo lo contrario: la salida a la red pública.
        """
        for nombre in todos_los_laboratorios():
            for area in [a for a in mapa.disposicion(plano.plano(laboratorio(nombre), "topologia"))["areas"]
                         if a["nube"]]:
                self.assertEqual(area["subred"], "", f"{nombre}: {area['titulo']}")
                self.assertEqual(area["lema"], "salida a la red pública", f"{nombre}")
                self.assertEqual(mapa.rotulos_de(area)[0],
                                 [area["titulo"], area["lema"]], f"{nombre}")

    def test_un_rotulo_mas_ancho_que_su_area_se_parte(self):
        """Si el texto no cabe a lo ancho, se parte y el grupo sigue cabiendo entero."""
        area = {"titulo": "Ventas", "subred": "10.44.1.0 - 10.44.1.255 (/24)",
                "x": 0.0, "y": 0.0, "ancho": 60.0, "alto": 600.0}
        textos, ancho, alto = mapa.rotulos_de(area)
        self.assertLessEqual(ancho, area["ancho"])
        self.assertLessEqual(alto, area["alto"])
        self.assertGreater(len(textos), 2)
        for texto in textos:
            self.assertLessEqual(mapa.tamano_de_rotulo(texto)[0], area["ancho"])

    def test_un_rotulo_que_no_cabe_para_el_mapa(self):
        """Si no cabe ni partido, se para y se dice: no se dibuja fuera de su área."""
        area = {"titulo": "Ventas", "subred": "10.44.1.0 - 10.44.1.255 (/24)",
                "x": 0.0, "y": 0.0, "ancho": 60.0, "alto": 100.0}
        with self.assertRaises(ValueError) as fallo:
            mapa.rotulos_de(area)
        self.assertIn("Ventas", str(fallo.exception))
        self.assertIn("no cabe", str(fallo.exception))

    def test_dos_cajas_de_texto_no_se_pisan(self):
        """Los rótulos se esquivan también entre sí: un título encima de otro no se lee.

        Cada rótulo se apartaba de los cables y de los equipos, pero no de los demás
        rótulos: el título del laboratorio caía sobre el de una sede y ninguna prueba lo
        veía, porque todas comparaban texto contra cable o contra equipo, nunca caja de
        texto contra caja de texto. Se comparan aquí todas entre sí —los títulos de las
        áreas— sobre todos los laboratorios del repositorio.
        """
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            contenido = mapa.contenido(lab, svg, con_vista(lab))
            cajas = []
            for caja in [e for e in contenido["elements"] if e["type"] == mapa.ELEMENTO_TEXTO]:
                texto = json.loads(mapa.texto_de(caja))["text"]
                ancho, alto = mapa.tamano_de_rotulo(texto)
                cajas.append((texto, (caja["posX"], caja["posY"], ancho, alto)))
            self.assertGreater(len(cajas), 1, nombre)
            for indice, (texto, rect) in enumerate(cajas):
                for otro_texto, otro_rect in cajas[indice + 1:]:
                    self.assertFalse(mapa.solapan(rect, otro_rect),
                                     f"{nombre}: «{texto}» se pisa con «{otro_texto}»")

    def test_cada_cable_se_llama_como_en_el_laboratorio_y_dice_sus_dos_puertos(self):
        """El nombre de un cable es el de su puente y sus puntas dicen su puerto.

        El nombre no se inventa aquí: lo deriva `identity`, que es quien también nombra los
        puentes del hipervisor, así que el nombre que se lee en el mapa es el del cable que
        de verdad existe. Y el plano dibuja exactamente los mismos cables, con los mismos
        puertos en las mismas puntas, que es de donde el mapa los lee.
        """
        for nombre in todos_los_laboratorios():
            lab = laboratorio(nombre)
            svg = plano.plano(lab, "topologia")
            objetos = con_vista(lab)
            contenido = mapa.contenido(lab, svg, objetos)
            nombres = identity.cables(lab)["per_port"]
            # Sólo los cables que unen dos equipos que la vista conoce: uno que salga de un
            # equipo sin objeto detrás no se puede dibujar, y el mapa lo deja fuera.
            en_la_vista = [c for c in lab["links"]
                           if c["a"]["node"] in objetos and c["z"]["node"] in objetos]
            self.assertEqual(len(contenido["links"]), len(en_la_vista), nombre)
            for enlace, cable in zip(contenido["links"], en_la_vista):
                una, punta_a = cable["a"]["node"], int(cable["a"]["port"])
                otra, punta_z = cable["z"]["node"], int(cable["z"]["port"])
                # El nombre no se dibuja —la vista lo pone en el centro y tapa el cable—
                # pero queda informado en la configuración del enlace.
                self.assertEqual(enlace["name"], "", nombre)
                self.assertEqual(json.loads(enlace["config"])["cableName"],
                                 nombres[una][punta_a], nombre)
                self.assertEqual(json.loads(enlace["config"])["cableName"],
                                 nombres[otra][punta_z], nombre)
                self.assertEqual(enlace["connectorName1"], f"p{punta_a}", nombre)
                self.assertEqual(enlace["connectorName2"], f"p{punta_z}", nombre)

    def test_el_cable_queda_atado_a_la_interfaz_de_la_que_sale(self):
        """Sin esto el cable sólo une dos iconos: no dice por dónde sale ni se puede medir."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        objetos = con_vista(lab)
        interfaces = {rol: {f"ether{n}": 900 + n for n in range(1, 9)} for rol in objetos}
        contenido = mapa.contenido(lab, svg, objetos, interfaces)
        for enlace, cable in zip(contenido["links"], lab["links"]):
            self.assertEqual(enlace["interface1"], 900 + int(cable["a"]["port"]))
            self.assertEqual(enlace["interface2"], 900 + int(cable["z"]["port"]))
        # Y sin interfaces descubiertas el mapa se dibuja igual, pero sin atar.
        sin = mapa.contenido(lab, svg, objetos)
        self.assertTrue(all(e["interface1"] == 0 for e in sin["links"]))

    def test_cambiar_el_nombre_o_la_interfaz_de_un_cable_hace_reescribir_el_mapa(self):
        """Lo que se lee en el mapa cuenta: si no, el nombre no llegaría nunca a la vista."""
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        objetos = con_vista(lab)
        interfaces = {rol: {f"ether{n}": 900 + n for n in range(1, 9)} for rol in objetos}
        contenido = mapa.contenido(lab, svg, objetos, interfaces)
        self.assertTrue(mapa.esta_al_dia(contenido, contenido))
        for clave, valor in (("name", "e_otro_cable"), ("interface1", 0), ("connectorName2", "p9")):
            otro = json.loads(json.dumps(contenido))
            otro["links"][0][clave] = valor
            self.assertFalse(mapa.esta_al_dia(otro, contenido), clave)
        # Y la vista puede devolver el cable con las puntas cambiadas: es el mismo cable.
        vuelta = json.loads(json.dumps(contenido))
        for enlace in vuelta["links"]:
            enlace["element1"], enlace["element2"] = enlace["element2"], enlace["element1"]
            enlace["interface1"], enlace["interface2"] = enlace["interface2"], enlace["interface1"]
            enlace["connectorName1"], enlace["connectorName2"] = (enlace["connectorName2"],
                                                                  enlace["connectorName1"])
        self.assertTrue(mapa.esta_al_dia(vuelta, contenido))

    def test_un_nombre_de_cable_borrado_o_cambiado_en_la_vista_hace_reescribir_el_mapa(self):
        """El nombre vive en la configuración del enlace: si la vista lo pierde, se repone.

        El nombre no viaja en `name` —va vacío a propósito, para que la vista no lo dibuje
        encima del cable— sino en la configuración. Comparar sólo `name` daba por bueno un
        cable anónimo y el nombre no volvía nunca; aquí se cambia sólo ese campo y el mapa
        tiene que reescribirse.
        """
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        contenido = mapa.contenido(lab, svg, con_vista(lab))
        for nombre_cable, caso in (("", "borrado"), ("e_otro_cable", "cambiado")):
            otro = json.loads(json.dumps(contenido))
            dentro = json.loads(otro["links"][0]["config"])
            dentro["cableName"] = nombre_cable
            otro["links"][0]["config"] = json.dumps(dentro)
            self.assertFalse(mapa.esta_al_dia(otro, contenido), caso)
        # Y la vista puede devolver la configuración con sus claves en otro orden: es la
        # misma, así que no puede hacer reescribir el mapa en cada pasada.
        vuelta = json.loads(json.dumps(contenido))
        for enlace in vuelta["links"]:
            dentro = json.loads(enlace["config"])
            enlace["config"] = json.dumps(dict(reversed(list(dentro.items()))), ensure_ascii=False)
        self.assertTrue(mapa.esta_al_dia(vuelta, contenido))

    def test_la_punta_del_cable_dice_su_puerto(self):
        """La punta dice el puerto —`p1`, `p2`— y no la interfaz: cuatro juntas se pisaban.

        La interfaz no se pierde: viaja en el número de interfaz del enlace, que es lo que
        la vista necesita para atar la punta al equipo.
        """
        lab = laboratorio()
        svg = plano.plano(lab, "topologia")
        objetos = con_vista(lab)
        interfaces = {rol: {f"ether{n}": 900 + n for n in range(1, 9)} for rol in objetos}
        contenido = mapa.contenido(lab, svg, objetos, interfaces)
        for enlace, cable in zip(contenido["links"], lab["links"]):
            self.assertEqual(enlace["connectorName1"], f"p{cable['a']['port']}")
            self.assertEqual(enlace["connectorName2"], f"p{cable['z']['port']}")
            self.assertEqual(enlace["interface1"],
                             interfaces[cable["a"]["node"]][f"ether{cable['a']['port']}"])
            self.assertEqual(enlace["interface2"],
                             interfaces[cable["z"]["node"]][f"ether{cable['z']['port']}"])

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

    def test_un_rotulo_con_ampersand_se_lee_sin_el_escape_del_plano(self):
        """El plano escapa `&`, `<` y `>` al escribir; la vista tiene que leerlos tal cual.

        Un área «Ventas & almacén» viaja en el SVG como `Ventas &amp; almacén`. Copiada
        cruda, el mapa enseñaría los caracteres del escape; leída con el lector XML de la
        biblioteca estándar, se lee el nombre de verdad. Se comprueba sobre un SVG pequeño
        hecho a mano, que es la única forma de tener un `&` en un rótulo.
        """
        svg = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100">'
               '<g data-area="Ventas &amp; almacén" data-x="10" data-y="10" '
               'data-ancho="80" data-alto="60" data-subred="10.0.0.0/24" data-nube="0"/>'
               '<g data-rol="rte1" data-x="30.0" data-y="30.0"/>'
               '<g class="cable" data-a="rte1" data-pa="1" data-z="rta1" data-pz="1"/>'
               '</svg>')
        donde = mapa.disposicion(svg)
        self.assertEqual(donde["ancho"], 200)
        self.assertEqual(donde["alto"], 100)
        self.assertEqual(donde["areas"][0]["titulo"], "Ventas & almacén")
        self.assertEqual(donde["areas"][0]["subred"], "10.0.0.0/24")
        self.assertEqual(donde["equipos"], {"rte1": (30.0, 30.0)})
        self.assertEqual(donde["cables"], [{"a": "rte1", "pa": 1, "z": "rta1", "pz": 1}])


if __name__ == "__main__":
    unittest.main()
