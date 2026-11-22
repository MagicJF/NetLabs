# PROPÓSITO:   las pruebas de la capa pura. Se inventan el mundo y la declaración y se
#              comprueba la identidad y la diferencia sin hipervisor: es lo que permite
#              saber que la derivación es una función y no una costumbre.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest), sin instalar nada.
#              Cada rechazo probado comprueba el MOTIVO, no sólo que falle.
# VER:         deployment_engine/tools/identity.py

import copy
import pathlib
import re
import sys
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import identity  # noqa: E402


def entorno():
    return yaml.safe_load((RAIZ / "netlabs.yml").read_text())


def laboratorio(nombre="b_router_dos_puestos"):
    return yaml.safe_load((RAIZ / "labs" / nombre / f"{nombre}.yml").read_text())


def mundo(guests=None, bridges=None, pools=None, used=None):
    return {
        "node": "Proxmox",
        "used_vmids": used if used is not None else [g["vmid"] for g in (guests or [])],
        "guests": guests or [],
        "bridges": bridges or [],
        "pools": pools or [],
    }


class Identidad(unittest.TestCase):
    def test_mac_es_estable_y_distingue_interfaces(self):
        self.assertEqual(identity.derive_mac(100), identity.derive_mac(100))
        self.assertNotEqual(identity.derive_mac(100), identity.derive_mac(100, 1))
        self.assertNotEqual(identity.derive_mac(100), identity.derive_mac(101))

    def test_mac_no_colisiona_en_un_rango_amplio(self):
        vistas = {identity.derive_mac(vmid, i) for vmid in range(100, 600) for i in range(16)}
        self.assertEqual(len(vistas), 500 * 16)

    def test_mac_invalida_se_rechaza(self):
        for malo in (0, -1, "100", 1.5, True):
            with self.assertRaises(identity.LabError):
                identity.derive_mac(malo)

    def test_gestion_es_inyectiva_y_no_da_red_ni_broadcast(self):
        direcciones = [identity.derive_management(v, "10.30.0.0/16") for v in range(100, 3000)]
        self.assertEqual(len(set(direcciones)), len(direcciones))
        self.assertFalse([d for d in direcciones if str(d).split(".")[-1] in ("0", "255")])
        self.assertTrue(all(str(d).startswith("10.30.") for d in direcciones))

    def test_gestion_exige_un_slash_16(self):
        with self.assertRaisesRegex(identity.LabError, "/16"):
            identity.derive_management(100, "10.30.0.0/24")


class ElPlan(unittest.TestCase):
    def test_plan_reparte_los_vmids_libres_mas_bajos(self):
        plan = identity.plan(mundo(used=[100, 101, 105]), laboratorio(), entorno())
        self.assertEqual({n["role"]: n["vmid"] for n in plan["nodes"]},
                         {"rte1": 102, "wsp1": 103, "wsp2": 104})

    def test_plan_conserva_el_vmid_de_un_rol_que_ya_vive_en_el_pool(self):
        viejos = [{"vmid": 200, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                   "description": "netlabs lab=b_router_dos_puestos role=rte1", "status": "running"}]
        plan = identity.plan(mundo(guests=viejos), laboratorio(), entorno())
        self.assertEqual({n["role"]: n["vmid"] for n in plan["nodes"]}["rte1"], 200)
        self.assertEqual(len({n["vmid"] for n in plan["nodes"]}), 3)

    def test_plan_es_idempotente_cuando_el_mundo_ya_es_lo_declarado(self):
        primero = identity.plan(mundo(), laboratorio(), entorno())
        creados = [{"vmid": n["vmid"], "name": n["name"],
                    "type": "qemu" if n["guest"] == "qemu" else "lxc",
                    "pool": "b_router_dos_puestos", "description": n["description"], "status": "running"}
                   for n in primero["nodes"]]
        puentes = [{"iface": s["bridge"], "type": "bridge", "cidr": None, "comments": s["comment"]}
                   for s in primero["steps"] if s["op"] == "bridge_ensure"]
        segundo = identity.plan(mundo(guests=creados, bridges=puentes, pools=["b_router_dos_puestos"]),
                                laboratorio(), entorno())
        self.assertEqual([s for s in segundo["steps"]
                          if s["op"] in ("guest_create", "pool_ensure", "bridge_ensure", "guest_start")], [])

    def test_plan_reconoce_sus_invitados_por_su_nombre(self):
        # El invitado se reconoce por su nombre —que es el del equipo— dentro del pool
        # del laboratorio. No hace falta ninguna marca más: el pool ya dice de quién es.
        viejos = [{"vmid": 210, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                   "status": "running"}]
        plan = identity.plan(mundo(guests=viejos), laboratorio(), entorno())
        self.assertEqual({n["role"]: n["vmid"] for n in plan["nodes"]}["rte1"], 210)
        # El router que ya vive no se vuelve a crear; los puestos que faltan, sí.
        self.assertEqual([s["guest"]["role"] for s in plan["steps"] if s["op"] == "guest_create"],
                         ["wsp1", "wsp2"])

    def test_un_mundo_ya_convergido_no_da_ningun_paso(self):
        # Si el plan emite "asegurar" para lo que ya está, el segundo apply nunca
        # puede decir "nada que hacer" y la cuenta deja de ser honesta. El mundo se
        # construye con la salida del propio motor: lo que el plan pide, ya hecho.
        lab, env = laboratorio(), entorno()
        primero = identity.plan(mundo(), lab, env)
        pool = primero["pool"]
        guests = [{"vmid": n["vmid"], "name": n["name"], "type": n["guest"],
                   "pool": pool, "status": "running"}
                  for n in primero["nodes"]]
        bridges = [{"iface": s["bridge"], "comments": s["comment"]}
                   for s in primero["steps"] if s["op"] == "bridge_ensure"]
        plan = identity.plan(mundo(guests=guests, bridges=bridges, pools=[pool]), lab, env)
        # Lo único que queda son las rutas: viven dentro del invitado de gestión, así
        # que el plan no puede leerlas sin entrar y no puede callarlas —decir "nada
        # que hacer" con una ruta sin poner sería la mentira que este caso evita—.
        self.assertEqual([s for s in plan["steps"] if s["op"] != "rutas_converge"], [])
        self.assertEqual([e for e in plan["effects"] if e not in primero["effects"]], [])

    def test_plan_es_determinista(self):
        self.assertEqual(identity.plan(mundo(used=[100]), laboratorio(), entorno()),
                         identity.plan(mundo(used=[100]), laboratorio(), entorno()))

    def test_plan_marca_los_puentes_con_el_laboratorio(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        self.assertEqual({s["bridge"]: s["comment"] for s in plan["steps"] if s["op"] == "bridge_ensure"},
                         {"b_rte1p1_wsp1p1": "netlabs lab=b_router_dos_puestos space=10.44.1.0/24 cable=b_rte1p1_wsp1p1",
                          "b_rte1p2_wsp2p1": "netlabs lab=b_router_dos_puestos space=10.44.2.0/24 cable=b_rte1p2_wsp2p1"})

    def test_un_puente_es_un_cable_entre_dos_puntas_y_nada_mas(self):
        # El nombre del puente son sus dos puntas, y el puente no lleva ni CIDR,
        # ni puerta, ni MAC: es un cable tonto. Un puente con dirección sería un
        # switch, y el motor no crea switches.
        plan = identity.plan(mundo(), laboratorio(), entorno())
        puentes = [s for s in plan["steps"] if s["op"] == "bridge_ensure"]
        self.assertEqual([s["bridge"] for s in puentes], ["b_rte1p1_wsp1p1", "b_rte1p2_wsp2p1"])
        for step in puentes:
            # Ni `cidr`, ni `gateway`, ni `mac`: el puente es el cable y nada más.
            self.assertEqual(set(step), {"op", "bridge", "comment"})
        for node in plan["nodes"]:
            for iface in node["interfaces"]:
                if iface["network"] is not None:
                    self.assertLessEqual(len(iface["bridge"]), 15)
                    self.assertIn("_", iface["bridge"])

    def test_la_letra_separa_los_nombres_de_dos_laboratorios(self):
        # Dos laboratorios con la misma topología en el mismo hipervisor no comparten
        # un nombre de cable: la letra del laboratorio es la cabeza de cada puente.
        primero = identity.plan(mundo(), laboratorio(), entorno())
        otro = copy.deepcopy(laboratorio())
        otro["lab"] = "d_otra_cosa"
        segundo = identity.plan(mundo(), otro, entorno())
        cables_uno = {s["bridge"] for s in primero["steps"] if s["op"] == "bridge_ensure"}
        cables_otros = {s["bridge"] for s in segundo["steps"] if s["op"] == "bridge_ensure"}
        self.assertEqual(cables_uno & cables_otros, set())
        self.assertIn("d_rte1p1_wsp1p1", cables_otros)

    def test_el_router_nace_con_la_pata_de_gestion_la_ultima(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        rte1 = next(n for n in plan["nodes"] if n["role"] == "rte1")
        self.assertEqual([i["network"] for i in rte1["interfaces"]], ["lan1", "lan2", None])
        self.assertEqual(rte1["interfaces"][-1]["bridge"], "vmbr30")
        self.assertTrue(rte1["mgmt_address"].startswith("10.30."))

    def test_los_puestos_no_tienen_pata_de_gestion(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        for node in plan["nodes"]:
            if node["type"] == "workstation":
                self.assertIsNone(node["mgmt_address"])
                self.assertTrue(all(i["network"] is not None for i in node["interfaces"]))

    def test_rechaza_cambiar_los_recursos_de_un_invitado_vivo(self):
        # Los recursos no se cambian en caliente. Sin esta comprobación, subir los cores en
        # la declaración dejaría al invitado con los viejos y el plan diría que no hay nada
        # que hacer: la mentira que este fichero evita.
        vivos = [{"vmid": 210, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                  "status": "running", "cores": 1, "memory_bytes": 256 * 1024 * 1024}]
        with self.assertRaisesRegex(identity.LabError, "core"):
            identity.plan(mundo(guests=vivos), laboratorio(), entorno())
        # Y con los cores bien y la memoria corta, lo dice por la memoria.
        vivos[0]["cores"] = 2
        with self.assertRaisesRegex(identity.LabError, "256 MB"):
            identity.plan(mundo(guests=vivos), laboratorio(), entorno())

    def test_un_equipo_se_llama_igual_en_el_plan_y_en_sus_cables(self):
        # El nombre del equipo es el rol declarado: el mismo en el invitado, en su
        # descripción y en la punta de cada cable que lo toca. Uno, no tres.
        plan = identity.plan(mundo(), laboratorio(), entorno())
        rte1 = next(n for n in plan["nodes"] if n["role"] == "rte1")
        self.assertEqual(rte1["name"], "rte1")
        self.assertEqual(rte1["description"], "netlabs lab=b_router_dos_puestos role=rte1")
        self.assertEqual([i["bridge"] for i in rte1["interfaces"] if i["network"]],
                         ["b_rte1p1_wsp1p1", "b_rte1p2_wsp2p1"])


class ElSwitch(unittest.TestCase):
    """Un switch reparte el cable dentro de UN dominio; no enruta ni lleva IP de laboratorio."""

    def test_sus_patas_de_laboratorio_van_a_un_solo_dominio(self):
        plan = identity.plan(mundo(), laboratorio("c_enrutar_y_conmutar"), entorno())
        switch = next(n for n in plan["nodes"] if n["role"] == "swc1")
        self.assertEqual([i["network"] for i in switch["interfaces"]], ["lan", "lan", None])
        self.assertIsNone(switch["address"])
        self.assertIsNone(switch["interfaces"][0]["address"])
        # La pata de gestión queda fuera del puente, pero se deriva como la del router.
        self.assertEqual(switch["interfaces"][-1]["bridge"], "vmbr30")
        self.assertTrue(switch["mgmt_address"].startswith("10.30."))


class Rechazos(unittest.TestCase):
    CASOS = [
        (lambda l: l.update(extra=1), "clave desconocida"),
        (lambda l: l["nodes"][0].update(type="hypervisor"), "no existe"),
        (lambda l: l["nodes"].append(copy.deepcopy(l["nodes"][1])), "dos veces"),
        (lambda l: l.update(address_spaces=["10.44.0.0/16", "10.44.1.0/24"]), "se pisan"),
        (lambda l: l.update(address_spaces=["10.30.1.0/24"]), "red de gestión"),
        (lambda l: l["networks"][0].update(address="10.99.1.0/24"), "no cabe en ningún espacio"),
        (lambda l: l["nodes"][1].update(networks=["lan9"]), "no está declarada"),
        (lambda l: l["nodes"][0].update(address="dhcp"), "no puede pedir dirección"),
        (lambda l: l["nodes"][0].update(address="10.77.1.1/24"), "no cae en ninguna red"),
        (lambda l: l["nodes"][1].update(stage=0), "entero >= 1"),
        (lambda l: l["nodes"][1].update(after=["fantasma"]), "no está declarado"),
        (lambda l: l["nodes"][1].update(configure={"routing": {}}), "no existe para su tipo"),
        (lambda l: l["nodes"][0]["configure"]["dhcp_server"][0].update(
            pool="10.44.1.250-10.44.1.10"), "no cae dentro"),
        (lambda l: l["nodes"][0]["configure"]["users"][0].update(
            password_from="secrets.otra"), "solo puede tomar la clave"),
        (lambda l: l["nodes"][0]["configure"]["addresses"][0].update(
            network="lan9"), "que no existe"),
        # Un router con dos patas en la misma red estaría conmutando; eso es un switch.
        (lambda l: l["nodes"][0].update(networks=["lan1", "lan1"]), "no conmuta"),
        (lambda l: l["nodes"][1].update(role="swa2", type="switch", networks=["lan1", "lan2"]),
         "un solo dominio de difusión"),
        (lambda l: l["nodes"][1].update(address=None), "no declara 'address'"),
        # El nombre del equipo lo dice todo, y el motor no admite uno que no encaje:
        # un nombre que no sigue el patrón, uno que dice un tipo que no es el suyo, una
        # función que no existe para su tipo y un ordinal fuera de 1-9.
        (lambda l: l["nodes"][0].update(role="rt1"), "dos letras de tipo, una de función"),
        (lambda l: l["nodes"][0].update(role="swc1"), "tienen que contar lo mismo"),
        (lambda l: l["nodes"][0].update(role="rtx1"), "no existe para un router"),
        (lambda l: l["nodes"][0].update(role="rte0"), "dos letras de tipo, una de función"),
        # El nombre del laboratorio es una letra y un título; la letra es la cabeza de
        # cada cable, así que no se admite un nombre sin ella.
        (lambda l: l.update(lab="router_dos_puestos"), "una letra y un título"),
        # Un puerto de dos cifras no cabe en los 15 caracteres del nombre del cable.
        (lambda l: l["links"][0]["a"].update(port=10), "un entero de 1 a 9"),
    ]

    def test_rechaza_lo_que_no_entiende(self):
        for cambio, motivo in self.CASOS:
            with self.subTest(motivo=motivo):
                lab = copy.deepcopy(laboratorio())
                cambio(lab)
                with self.assertRaisesRegex(identity.LabError, motivo):
                    identity.plan(mundo(), lab, entorno())

    def test_rechaza_un_ciclo_en_after(self):
        lab = copy.deepcopy(laboratorio())
        lab["nodes"][1]["after"] = ["wsp2"]
        lab["nodes"][2]["after"] = ["wsp1"]
        with self.assertRaisesRegex(identity.LabError, "ciclo"):
            identity.plan(mundo(), lab, entorno())

    def test_rechaza_pisar_el_espacio_de_otro_laboratorio_vivo(self):
        # El cable del otro laboratorio no lleva CIDR en el puente: el espacio
        # viaja en el comentario, que es lo único que se puede leer de un cable.
        puentes = [{"iface": "b_rte1p1_wsp1p1", "type": "bridge", "cidr": None,
                    "comments": "netlabs lab=otro space=10.44.1.0/24 cable=b_rte1p1_wsp1p1"}]
        with self.assertRaisesRegex(identity.LabError, "se pisa con el de 'otro'"):
            identity.plan(mundo(bridges=puentes), laboratorio(), entorno())

    def test_retira_un_cable_marcado_que_ya_no_se_declara(self):
        # La diferencia va en los dos sentidos también para los cables: un puente
        # con la marca de este laboratorio que ya no une nada es basura suya.
        puentes = [{"iface": "b_rte1p9_wsp1p9", "type": "bridge", "cidr": None,
                    "comments": "netlabs lab=b_router_dos_puestos space=10.44.9.0/24 cable=b_rte1p9_wsp1p9"}]
        plan = identity.plan(mundo(bridges=puentes), laboratorio(), entorno())
        retiros = [s for s in plan["steps"] if s["op"] == "bridge_destroy"]
        self.assertEqual([s["bridge"] for s in retiros], ["b_rte1p9_wsp1p9"])

    def test_no_toca_un_puente_sin_marca_aunque_sobre(self):
        # Un puente sin marca no es de este laboratorio: puede ser del hipervisor
        # o de otro. Retirarlo sería borrar lo que no está declarado.
        puentes = [{"iface": "vmbr30", "type": "bridge", "cidr": None, "comments": ""}]
        plan = identity.plan(mundo(bridges=puentes), laboratorio(), entorno())
        self.assertEqual([s for s in plan["steps"] if s["op"] == "bridge_destroy"], [])

    def test_rechaza_un_puente_ajeno_con_el_mismo_nombre(self):
        puentes = [{"iface": "b_rte1p1_wsp1p1", "type": "bridge", "cidr": None, "comments": ""}]
        with self.assertRaisesRegex(identity.LabError, "no es suyo"):
            identity.plan(mundo(bridges=puentes), laboratorio(), entorno())

    def test_rechaza_un_puerto_sin_cable(self):
        # Un puerto declarado sin cable no es una red: es un olvido. El plan lo
        # dice en vez de dejar la interfaz colgando de un puente que no existe.
        lab = copy.deepcopy(laboratorio())
        lab["links"] = lab["links"][:1]
        with self.assertRaisesRegex(identity.LabError, "no está en ningún cable"):
            identity.plan(mundo(), lab, entorno())

    def test_rechaza_un_cable_que_mezcla_dos_redes(self):
        lab = copy.deepcopy(laboratorio())
        lab["links"][0]["z"] = {"node": "wsp2", "port": 1}
        with self.assertRaisesRegex(identity.LabError, "misma red"):
            identity.plan(mundo(), lab, entorno())

    def test_rechaza_cambiar_de_contenedor_a_maquina(self):
        viejos = [{"vmid": 200, "name": "rte1", "type": "lxc", "pool": "b_router_dos_puestos",
                   "description": "netlabs lab=b_router_dos_puestos role=rte1", "status": "running"}]
        with self.assertRaisesRegex(identity.LabError, "contenedor a máquina"):
            identity.plan(mundo(guests=viejos), laboratorio(), entorno())


class ElPlanDeControl(unittest.TestCase):
    """Un laboratorio de control adopta un invitado que ya existía; no lo crea."""

    def test_control_adopta_el_invitado_por_su_nombre_y_su_pool(self):
        viejos = [{"vmid": 102, "name": "netxms", "type": "lxc", "pool": "a_bootstrap",
                   "description": "netlabs lab=a_bootstrap role=netxms", "status": "running"}]
        plan = identity.plan(mundo(guests=viejos, pools=["a_bootstrap"]),
                             laboratorio("a_bootstrap"), entorno())
        self.assertEqual(plan["pool"], "a_bootstrap")
        self.assertEqual([n["vmid"] for n in plan["nodes"]], [102])
        # Adoptar no es crear: ningún paso de creación ni de arranque.
        self.assertEqual([s["op"] for s in plan["steps"]], ["interior_converge"])

    def test_control_sin_pool_ni_invitado_crea_el_que_falta(self):
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        self.assertEqual([s["op"] for s in plan["steps"]],
                         ["pool_ensure", "guest_create", "interior_converge"])

    def test_control_declara_la_convergencia_de_su_interior(self):
        # El plan no puede leer el interior sin entrar, así que lo declara como
        # paso pendiente: decir "nada que hacer" con un interior sin converger
        # sería una mentira, y el segundo apply no podría distinguirse del primero.
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        paso = next(s for s in plan["steps"] if s["op"] == "interior_converge")
        self.assertEqual(paso["role"], "netxms")
        # Mundo vacío: el menor vmid libre es el 100 y su dirección se deriva de él.
        self.assertEqual(paso["address"], "10.30.0.101")
        self.assertTrue([e for e in plan["effects"] if "converger el interior" in e])

    def test_control_no_dibuja_cables_ni_redes(self):
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        self.assertEqual(plan["tunnel_forwards"], [])
        self.assertFalse([s for s in plan["steps"] if s["op"].startswith("bridge")])
        self.assertEqual(plan["nodes"][0]["networks"], [])


class LasRutas(unittest.TestCase):
    """Una ruta por espacio declarado, con el router del laboratorio como salto.

    Las pone el invitado de gestión —por donde entra el SSH del motor y donde vive
    lo que observa—: sin ellas el laboratorio se despliega y no se ve.
    """

    @staticmethod
    def nodo(role, tipo, address, mgmt, management=True):
        return {"role": role, "type": tipo, "address": address,
                "mgmt_address": mgmt, "management": management}

    def test_una_ruta_por_espacio_con_el_router_como_salto(self):
        lab = {"address_spaces": ["10.44.0.0/16"]}
        nodes = [self.nodo("rte1", "router", "10.44.1.1/24", "10.30.0.104")]
        self.assertEqual(identity._rutas(lab, nodes),
                         [{"space": "10.44.0.0/16", "via": "10.30.0.104",
                           "role": "rte1", "prueba": "10.44.1.1"}])
        # El salto es la dirección de gestión: por la del laboratorio no se llega
        # desde la red de gestión, que es de donde sale todo lo que observa.
        self.assertNotEqual(identity._rutas(lab, nodes)[0]["via"], "10.44.1.1")

    def test_el_salto_es_el_primer_router_declarado_dentro_del_espacio(self):
        lab = {"address_spaces": ["10.44.0.0/16"]}
        nodes = [self.nodo("swc1", "switch", None, "10.30.0.109"),
                 self.nodo("rte2", "router", "10.44.9.1/24", "10.30.0.108"),
                 self.nodo("rte1", "router", "10.44.1.1/24", "10.30.0.104")]
        # Un switch no enruta; entre dos routers decide el orden de la declaración.
        self.assertEqual(identity._rutas(lab, nodes)[0]["role"], "rte2")

    def test_un_router_sin_pata_de_gestion_no_puede_ser_el_salto(self):
        lab = {"address_spaces": ["10.44.0.0/16"]}
        nodes = [self.nodo("rte1", "router", "10.44.1.1/24", None, management=False)]
        self.assertEqual(identity._rutas(lab, nodes), [])

    def test_un_espacio_sin_router_no_inventa_salto(self):
        lab = {"address_spaces": ["10.44.0.0/16", "10.99.0.0/16"]}
        nodes = [self.nodo("rte1", "router", "10.44.1.1/24", "10.30.0.104")]
        self.assertEqual([r["space"] for r in identity._rutas(lab, nodes)], ["10.44.0.0/16"])

    def test_el_plan_del_laboratorio_lleva_sus_rutas_y_lo_dice(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        rte1 = next(n for n in plan["nodes"] if n["role"] == "rte1")
        self.assertEqual(plan["rutas"],
                         [{"space": "10.44.0.0/16", "via": rte1["mgmt_address"],
                           "role": "rte1", "prueba": "10.44.1.1"}])
        self.assertTrue([e for e in plan["effects"] if "vista desde la gestión" in e])
        # Las rutas viven dentro del invitado de gestión: el plan no las puede leer
        # sin entrar, así que las declara como trabajo pendiente.
        self.assertEqual([s["op"] for s in plan["steps"] if s["op"] == "rutas_converge"],
                         ["rutas_converge"])

    def test_un_espacio_sin_router_se_dice_en_el_plan(self):
        lab = laboratorio()
        lab["address_spaces"].append("10.99.0.0/16")
        plan = identity.plan(mundo(), lab, entorno())
        self.assertEqual([r["space"] for r in plan["rutas"]], ["10.44.0.0/16"])
        self.assertTrue([e for e in plan["effects"]
                         if "10.99.0.0/16 no tiene ningún router dentro" in e])

    def test_el_plan_de_control_no_tiene_rutas(self):
        # El invitado de gestión no se observa a sí mismo: no declara espacios.
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        self.assertEqual(plan["rutas"], [])


class ElSitio(unittest.TestCase):
    """El invitado de gestión: se adopta el que ya corre, no se crea otro al lado."""

    def test_reconoce_al_invitado_por_su_nombre_aunque_cambie_el_pool(self):
        # Renombrar el laboratorio de control cambia el nombre de su pool: si el motor
        # reconociera su invitado por el pool, lo daría por ausente y crearía un segundo
        # servicio de observación junto al que ya está en pie.
        viejos = [{"vmid": 102, "name": "netxms", "type": "lxc", "pool": "lab-00_bootstrap",
                   "status": "running"}]
        sitio = identity.site(mundo(guests=viejos), entorno())
        self.assertEqual(sitio["vmid"], 102)
        self.assertTrue(sitio["exists"])
        self.assertEqual(sitio["pool"], "a_bootstrap")
        self.assertEqual(sitio["pool_actual"], "lab-00_bootstrap")
        self.assertTrue(sitio["mover"])

    def test_sin_invitado_de_gestion_no_lo_da_por_existente(self):
        sitio = identity.site(mundo(), entorno())
        self.assertFalse(sitio["exists"])
        self.assertFalse(sitio["mover"])
        self.assertIsNone(sitio["pool_actual"])


class Documentacion(unittest.TestCase):
    def test_la_documentacion_generada_no_lleva_nada_derivado(self):
        texto = identity.render_docs(laboratorio(), entorno())
        self.assertIn("rte1", texto)
        self.assertIn("10.44.2.0/24", texto)
        self.assertNotIn("vmid", texto.lower())
        self.assertNotIn("BC:24:11", texto)

    def test_la_documentacion_generada_es_estable(self):
        self.assertEqual(identity.render_docs(laboratorio(), entorno()),
                         identity.render_docs(laboratorio(), entorno()))

    def test_la_documentacion_dibuja_la_topologia_y_el_cableado(self):
        texto = identity.render_docs(laboratorio(), entorno())
        # Dos dibujos sacados de la declaración: quién está en qué red (topología, con
        # las redes como áreas translúcidas) y qué puerto va con qué puerto (cableado,
        # con texto en la arista). Los dos en `flowchart TB`: N-S arriba-abajo.
        self.assertEqual(texto.count("```mermaid\nflowchart TB"), 2)
        self.assertIn('n_rte1["📡 rte1<br/>p1, p2"]', texto)
        # El cable dice sus dos puntas sin haber que mirar la tabla.
        self.assertIn("rte1p1 ↔ wsp1p1", texto)
        # El diagrama es código dentro de la página: ni imagen enlazada ni fichero aparte.
        self.assertNotIn("![", texto)
        self.assertNotIn(".svg", texto)
        self.assertNotIn(".png", texto)

    def test_los_dibujos_salen_enteros_de_la_declaracion(self):
        """Ni un servicio inventado ni uno olvidado: lo que no está en el YAML no se dibuja."""
        lab = laboratorio()
        texto = identity.render_docs(lab, entorno())
        bloques = re.findall(r"```mermaid\nflowchart TB\n(.*?)```", texto, re.S)
        self.assertEqual(len(bloques), 2)
        topologia, cableado = bloques

        nodos = {identity._id(n["role"]) for n in lab["nodes"]}
        # Cada red es un área: subgraph con su nombre y su subred en `x`.
        self.assertEqual(len(re.findall(r"subgraph red\d+\[", topologia)), len(lab["networks"]))
        for net in lab["networks"]:
            self.assertIn(identity._subred(net["address"]), topologia)
        # Todos los equipos aparecen en el plano; ninguno inventado.
        dibujados = set(re.findall(r"(?m)^\s+(\w+)[\[(]", topologia))
        self.assertEqual(dibujados, nodos)
        self.assertEqual(set(re.findall(r"(?m)^\s+(\w+)\[", cableado)), nodos)

        # Topología: una arista por `after`. Cableado: una por cable.
        patas = sum(len(n.get("after") or []) for n in lab["nodes"])
        self.assertEqual(len(re.findall(r"-->", topologia)), patas)
        aristas = re.findall(r"(\w+) -->\|([^|]+)\| (\w+)", cableado)
        self.assertEqual(len(aristas), len(lab["links"]))
        # El cableado baja: la punta de arriba es la menos profunda.
        profundidad = {identity._id(rol): d for rol, d in identity._profundidad(lab).items()}
        for (a, _, z), cable in zip(aristas, lab["links"]):
            self.assertLessEqual(profundidad[a], profundidad[z])
            self.assertEqual({a, z},
                             {identity._id(cable["a"]["node"]), identity._id(cable["z"]["node"])})
        # Y cada arista dice las dos puntas que une, que es lo que la hace útil.
        for (_, etiqueta, _), cable in zip(aristas, lab["links"]):
            self.assertEqual(etiqueta.split(" ↔ "),
                             [identity._endpoint(cable["a"]["node"], cable["a"]["port"]),
                              identity._endpoint(cable["z"]["node"], cable["z"]["port"])])

    def test_el_dibujo_del_cableado_no_inventa_ni_omite(self):
        lab = {"networks": [{"name": "lan", "address": "10.9.0.0/24"}],
               "nodes": [{"role": "r", "type": "router", "networks": ["lan"],
                          "address": "10.9.0.1/24"},
                         {"role": "s", "type": "switch", "networks": ["lan", "lan"]},
                         {"role": "h", "type": "workstation", "networks": ["lan"],
                          "address": "dhcp"}],
               "links": [{"a": {"node": "r", "port": 1}, "z": {"node": "s", "port": 1}},
                         {"a": {"node": "s", "port": 2}, "z": {"node": "h", "port": 1}}]}
        lineas = identity._mermaid_cableado(lab)
        self.assertIn('    n_s["🔀 s<br/>p1, p2"]', lineas)
        self.assertEqual([l.strip() for l in lineas if " -->|" in l],
                         ["n_r -->|rp1 ↔ sp1| n_s", "n_s -->|sp2 ↔ hp1| n_h"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
