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
import plano  # noqa: E402


def entorno():
    return yaml.safe_load((RAIZ / "netlabs.yml").read_text())


def laboratorio(nombre="b_router_dos_puestos"):
    return yaml.safe_load((RAIZ / "labs" / nombre / f"{nombre}.yml").read_text())


def mundo(invitados=None, bridges=None, pools=None, used=None):
    return {
        "node": "Proxmox",
        "used_vmids": used if used is not None else [g["vmid"] for g in (invitados or [])],
        "invitados": invitados or [],
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

    def test_un_vmid_que_no_cabe_en_el_plano_no_tiene_direccion(self):
        """Un invitado ajeno al motor no puede tumbar la lectura de las direcciones.

        Demuestra que se sabe de antemano qué vmids caben en el /16 antes de derivar: un
        invitado con `vmid` 70000 no tiene dirección de gestión del motor, y preguntársela
        lanzaba y dejaba el laboratorio sin registrar en la vista.
        """
        self.assertTrue(identity.cabe_management(identity.VMID_MAXIMO_MANAGEMENT, "10.30.0.0/16"))
        self.assertFalse(identity.cabe_management(70000, "10.30.0.0/16"))
        self.assertFalse(identity.cabe_management(0, "10.30.0.0/16"))

    def test_un_plano_mal_declarado_se_sigue_diciendo(self):
        with self.assertRaisesRegex(identity.LabError, "/16"):
            identity.cabe_management(100, "10.30.0.0/24")


class ElPlan(unittest.TestCase):
    def test_plan_reparte_los_vmids_libres_mas_bajos(self):
        plan = identity.plan(mundo(used=[100, 101, 105]), laboratorio(), entorno())
        self.assertEqual({n["role"]: n["vmid"] for n in plan["nodes"]},
                         {"rte1": 102, "wsp1": 103, "wsp2": 104})

    def test_plan_conserva_el_vmid_de_un_rol_que_ya_vive_en_el_pool(self):
        viejos = [{"vmid": 200, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                   "description": "netlabs lab=b_router_dos_puestos role=rte1", "status": "running"}]
        plan = identity.plan(mundo(invitados=viejos), laboratorio(), entorno())
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
        segundo = identity.plan(mundo(invitados=creados, bridges=puentes, pools=["b_router_dos_puestos"]),
                                laboratorio(), entorno())
        self.assertEqual([s for s in segundo["steps"]
                          if s["op"] in ("guest_create", "pool_ensure", "bridge_ensure", "guest_start")], [])

    def test_plan_reconoce_sus_invitados_por_su_nombre(self):
        # El invitado se reconoce por su nombre —que es el del equipo— dentro del pool
        # del laboratorio. No hace falta ninguna marca más: el pool ya dice de quién es.
        viejos = [{"vmid": 210, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                   "status": "running"}]
        plan = identity.plan(mundo(invitados=viejos), laboratorio(), entorno())
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
        invitados = [{"vmid": n["vmid"], "name": n["name"], "type": n["guest"],
                   "pool": pool, "status": "running"}
                  for n in primero["nodes"]]
        bridges = [{"iface": s["bridge"], "comments": s["comment"]}
                   for s in primero["steps"] if s["op"] == "bridge_ensure"]
        plan = identity.plan(mundo(invitados=invitados, bridges=bridges, pools=[pool]), lab, env)
        # Lo único que queda son las tres cosas que viven FUERA del hipervisor —las
        # rutas, dentro del invitado de gestión; el registro de los equipos en lo que
        # observa el sitio; y el mapa de la red en esa vista—: el plan no puede leerlas
        # sin entrar, así que no puede callarlas. Decir "nada que hacer" con una ruta sin
        # poner o un equipo sin registrar sería la mentira que este caso evita.
        self.assertEqual(
            [s for s in plan["steps"]
             if s["op"] not in ("rutas_converge", "netxms_registro", "netxms_mapa")], []
        )
        # El paso dice qué equipos son: los de red, con su dirección de gestión.
        registro = next(s for s in plan["steps"] if s["op"] == "netxms_registro")
        self.assertEqual(registro["equipos"], [{"role": "rte1", "address": "10.30.0.101"}])
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

    def test_un_puesto_estatico_lleva_su_direccion_a_la_vista(self):
        # Un nodo final no tiene pata de gestión, pero sí una dirección estática: esa
        # es la que se registra y la que permite dibujarlo en el mapa.
        lab = laboratorio()
        for node in lab["nodes"]:
            if node["type"] == "workstation":
                node["address"] = "10.44.1.50/24"
                break
        plan = identity.plan(mundo(), lab, entorno())
        puesto = next(n for n in plan["nodes"] if n["type"] == "workstation" and n["address"] != "dhcp")
        self.assertEqual(puesto["netxms_address"], "10.44.1.50")
        registro = next(s for s in plan["steps"] if s["op"] == "netxms_registro")
        self.assertIn({"role": puesto["role"], "address": "10.44.1.50"}, registro["equipos"])

    def test_un_puesto_con_reserva_sigue_pidiendo_dhcp_pero_tiene_direccion(self):
        # La reserva no convierte al puesto en estático: sigue pidiendo por DHCP, pero
        # el router siempre le da la misma dirección. Esa dirección es la que la vista
        # puede registrar y la que el mapa puede dibujar.
        lab = laboratorio()
        puesto = next(n for n in lab["nodes"] if n["type"] == "workstation")
        puesto["reserve"] = "10.44.1.50"
        plan = identity.plan(mundo(), lab, entorno())
        built = next(n for n in plan["nodes"] if n["role"] == puesto["role"])
        self.assertEqual(built["address"], "dhcp")
        self.assertEqual(built["reserve"], "10.44.1.50")
        self.assertEqual(built["netxms_address"], "10.44.1.50")
        router = next(n for n in plan["nodes"] if n["role"] == "rte1")
        reserva = next(l for d in router["configure"]["dhcp_server"] for l in d.get("leases", []))
        self.assertEqual(reserva["address"], "10.44.1.50")
        self.assertEqual(reserva["role"], puesto["role"])
        self.assertEqual(reserva["mac"], built["interfaces"][0]["mac"])
        registro = next(s for s in plan["steps"] if s["op"] == "netxms_registro")
        self.assertIn({"role": puesto["role"], "address": "10.44.1.50"}, registro["equipos"])

    def test_una_reserva_fuera_de_su_red_se_rechaza(self):
        lab = laboratorio()
        puesto = next(n for n in lab["nodes"] if n["type"] == "workstation")
        puesto["reserve"] = "10.99.1.50"
        with self.assertRaisesRegex(identity.LabError, "no cae en ninguna red"):
            identity.plan(mundo(), lab, entorno())

    def test_una_reserva_sin_dhcp_se_rechaza(self):
        lab = laboratorio()
        puesto = next(n for n in lab["nodes"] if n["type"] == "workstation")
        puesto["address"] = "10.44.1.60/24"
        puesto["reserve"] = "10.44.1.50"
        with self.assertRaisesRegex(identity.LabError, "sólo acompaña a 'address: dhcp'"):
            identity.plan(mundo(), lab, entorno())

    def test_los_recursos_se_ajustan_en_el_sitio_y_no_tirando_el_invitado(self):
        # Un invitado con otra memoria no se destruye: se le reescribe el config. Tirar
        # los veinticuatro equipos para cambiar ocho memorias era el precio de antes.
        vivos = [{"vmid": 210, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                  "status": "running", "cores": 1, "memory_bytes": 128 * 1024 * 1024,
                  # Lo ESCRITO en su config, que es lo que compara el plan: los valores del
                  # clúster son los de en marcha y no ven el cambio que aún no se aplicó.
                  "config_cores": 1, "config_memory": 128}]
        plan = identity.plan(mundo(invitados=vivos), laboratorio(), entorno())
        pasos = [s for s in plan["steps"] if s["op"] in ("guest_set", "guest_recreate", "guest_destroy")]
        self.assertEqual([(s["op"], s["vmid"]) for s in pasos], [("guest_set", 210)])
        declarado = next(n for n in plan["nodes"] if n["vmid"] == 210)["memory"]
        self.assertEqual(pasos[0]["memory"], declarado)
        self.assertEqual(pasos[0]["tenia"]["memory"], 128)
        # Los demás no aparecen: un plan que toca a todos cuando cambia uno es el que
        # obligaba a un destroy del laboratorio entero.
        self.assertFalse([s for s in plan["steps"]
                          if s["op"] == "guest_create" and s["guest"]["vmid"] == 210])
        self.assertTrue(any(f"memoria 128 -> {declarado} MB" in e for e in plan["effects"]),
                        plan["effects"])

        # Con la memoria ya convergida y los cores cortos: el arreglo va por los cores, y
        # por eso la memoria del config se pone en lo declarado —si el paso saliera por ella,
        # la prueba no estaría demostrando el caso de los cores.
        vivos[0]["cores"] = 0
        vivos[0]["config_cores"] = 0
        vivos[0]["config_memory"] = declarado
        plan = identity.plan(mundo(invitados=vivos), laboratorio(), entorno())
        declarado_cores = next(n for n in plan["nodes"] if n["vmid"] == 210)["cores"]
        paso = next(s for s in plan["steps"] if s["op"] == "guest_set")
        self.assertEqual(paso["cores"], declarado_cores)
        self.assertEqual(paso["tenia"]["cores"], 0)
        # El paso lleva siempre el estado deseado entero —cores y memoria—, que es lo
        # que se escribe en el config: mandar sólo la mitad deja la otra a expensas de
        # lo que hubiera, y el plan dejaría de decir a qué se converge.
        self.assertEqual(paso["memory"], declarado)

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
        # Dos áreas con el mismo bloque se anidan la una en la otra y el plano se queda
        # sin raíz: se rechaza antes de dibujar nada.
        (lambda l: l["networks"][1].update(address=l["networks"][0]["address"]), "repite el CIDR"),
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

    def test_rechaza_una_ruta_ipv6_con_el_limite_del_area(self):
        """El área escribe en la tabla IPv4 y una ruta IPv6 no tiene operación que la ponga.

        Demuestra que el límite se dice al validar, con el área y la ruta delante, en vez
        de pasar la validación y llegar a `apply` sin camino para instalarla.
        """
        lab = copy.deepcopy(laboratorio("d_acme_dos_sedes"))
        router = next(n for n in lab["nodes"] if "routes" in (n.get("configure") or {}))
        router["configure"]["routes"][0]["destination"] = "2001:db8:2::/64"
        with self.assertRaisesRegex(identity.LabError, "no es IPv4"):
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

    def test_manda_lo_escrito_en_el_config_no_lo_que_esta_en_marcha(self):
        # `/cluster/resources` da la memoria viva: una máquina encendida a la que se le
        # cambia la memoria en el config sigue con la vieja hasta reiniciar. Si el plan
        # comparase contra la viva, no vería esa diferencia justo cuando existe.
        vivos = [{"vmid": 210, "name": "rte1", "type": "qemu", "pool": "b_router_dos_puestos",
                  "status": "running", "cores": 1, "memory_bytes": 256 * 1024 * 1024,
                  "config_cores": 1, "config_memory": 200}]
        plan = identity.plan(mundo(invitados=vivos), laboratorio(), entorno())
        paso = next(s for s in plan["steps"] if s["op"] == "guest_set")
        self.assertEqual(paso["tenia"]["memory"], 200)
        self.assertTrue(any("memoria 200 ->" in e for e in plan["effects"]), plan["effects"])

    def test_cambiar_de_contenedor_a_maquina_rehace_solo_ese_invitado(self):
        # Lo que no se cambia en caliente se rehace, pero rehacer no es destruir el
        # laboratorio: el paso lleva el vmid exacto y no arrastra a ningún otro.
        viejos = [{"vmid": 200, "name": "rte1", "type": "lxc", "pool": "b_router_dos_puestos",
                   "description": "netlabs lab=b_router_dos_puestos role=rte1", "status": "running"}]
        plan = identity.plan(mundo(invitados=viejos), laboratorio(), entorno())
        rehacer = [s for s in plan["steps"] if s["op"] == "guest_recreate"]
        self.assertEqual([s["vmid"] for s in rehacer], [200])
        self.assertIn("lxc", rehacer[0]["motivo"])
        self.assertEqual(rehacer[0]["built"]["vmid"], 200)


class ElPlanDeControl(unittest.TestCase):
    """Un laboratorio de control adopta un invitado que ya existía; no lo crea."""

    def test_control_adopta_el_invitado_por_su_nombre_y_su_pool(self):
        viejos = [{"vmid": 102, "name": "netxms", "type": "lxc", "pool": "a_bootstrap",
                   "description": "netlabs lab=a_bootstrap role=netxms", "status": "running"}]
        plan = identity.plan(mundo(invitados=viejos, pools=["a_bootstrap"]),
                             laboratorio("a_bootstrap"), entorno())
        self.assertEqual(plan["pool"], "a_bootstrap")
        self.assertEqual([n["vmid"] for n in plan["nodes"]], [102])
        # Adoptar no es crear: ningún paso de creación ni de arranque.
        self.assertEqual([s["op"] for s in plan["steps"]], ["interior_converge"])

    def test_control_usa_los_recursos_que_declara_el_sitio(self):
        # El invitado de control ES el de gestión, que se declara en `netlabs.yml`: si el
        # laboratorio no dice otra cosa, sus recursos son los del sitio. Sin esto, el plan
        # pedía 1 core contra los 2 del invitado vivo y `plan`/`apply a_bootstrap` se paraba
        # diciendo que hacía falta destroy —un desacuerdo que no existe en la realidad—.
        env = entorno()
        vivos = [{"vmid": 102, "name": "netxms", "type": "lxc", "pool": "a_bootstrap",
                  "description": "netlabs lab=a_bootstrap role=netxms", "status": "running",
                  "cores": env["management"]["cores"],
                  "memory_bytes": env["management"]["memory"] * 1024 * 1024}]
        plan = identity.plan(mundo(invitados=vivos, pools=["a_bootstrap"]),
                             laboratorio("a_bootstrap"), entorno())
        self.assertEqual(plan["nodes"][0]["cores"], env["management"]["cores"])
        self.assertEqual(plan["nodes"][0]["memory"], env["management"]["memory"])

    def test_control_puede_sobreescribir_los_recursos_del_sitio(self):
        lab = laboratorio("a_bootstrap")
        lab["nodes"][0]["resources"] = {"cores": 4}
        plan = identity.plan(mundo(), lab, entorno())
        self.assertEqual(plan["nodes"][0]["cores"], 4)

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
                           "role": "rte1", "prueba": "10.44.1.1", "alcance": "salto"}])
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

    def test_un_router_de_varias_patas_cuenta_por_cualquiera_de_ellas(self):
        # Un router que enruta entre varias redes declara sus direcciones en
        # `configure.addresses`. Mirando sólo `address` quedaría fuera de su propio
        # espacio —su primera pata está en otra red— y ese espacio se quedaría sin
        # ruta. El salto de prueba es la primera pata que cae dentro.
        lab = {"address_spaces": ["10.44.0.0/16"]}
        router = self.nodo("rte1", "router", "10.55.0.1/24", "10.30.0.104")
        router["configure"] = {"addresses": [
            {"address": "10.55.0.1/24"},
            {"address": "10.44.1.1/24"},
        ]}
        self.assertEqual(identity._rutas(lab, [router]),
                         [{"space": "10.44.0.0/16", "via": "10.30.0.104",
                           "role": "rte1", "prueba": "10.44.1.1", "alcance": "salto"}])

    def test_se_sondea_una_direccion_detras_del_router_cuando_se_declara(self):
        # El router contesta a su propia pata aunque no reenvíe hacia atrás. Si el
        # laboratorio declara una dirección **detrás** de él —otra pata, dentro del mismo
        # espacio—, esa es la que se sondea: es lo único que demuestra que reenvía.
        lab = {"address_spaces": ["10.44.0.0/16"]}
        router = self.nodo("rte1", "router", "10.44.1.1/24", "10.30.0.104")
        puesto = self.nodo("wsp1", "workstation", "10.44.1.50/24", None, management=False)
        self.assertEqual(identity._rutas(lab, [router, puesto]),
                         [{"space": "10.44.0.0/16", "via": "10.30.0.104", "role": "rte1",
                           "prueba": "10.44.1.50", "alcance": "red"}])

    def test_un_espacio_sin_router_no_inventa_salto(self):
        lab = {"address_spaces": ["10.44.0.0/16", "10.99.0.0/16"]}
        nodes = [self.nodo("rte1", "router", "10.44.1.1/24", "10.30.0.104")]
        self.assertEqual([r["space"] for r in identity._rutas(lab, nodes)], ["10.44.0.0/16"])

    def test_el_plan_del_laboratorio_lleva_sus_rutas_y_lo_dice(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        rte1 = next(n for n in plan["nodes"] if n["role"] == "rte1")
        self.assertEqual(plan["rutas"],
                         [{"space": "10.44.0.0/16", "via": rte1["mgmt_address"],
                           "role": "rte1", "prueba": "10.44.1.1", "alcance": "salto"}])
        self.assertTrue([e for e in plan["effects"] if "vista desde la gestión" in e])
        # El plan dice hasta dónde llega la comprobación: sin dirección detrás del
        # router, lo que se comprueba es el salto, no la red.
        self.assertTrue([e for e in plan["effects"] if "se comprueba el salto" in e])
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
        sitio = identity.site(mundo(invitados=viejos), entorno())
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

    def test_la_pagina_lleva_el_plano_dentro(self):
        """El plano va dentro de la página, como SVG en texto, y no al lado.

        Es código generado: entra en el mismo diff que la declaración y no deja ficheros
        de imagen que se puedan quedar viejos junto al `.md` (la carpeta de un
        laboratorio sólo declara su `.yml` y su `.md`).
        """
        lab = laboratorio()
        texto = identity.render_docs(lab, entorno())
        # El dibujo está en la página, entero y sacado de la declaración.
        self.assertIn(plano.plano(lab, "topologia"), texto)
        # Uno, y sólo uno: la página lleva su plano y ningún otro dibujo.
        self.assertEqual(texto.count("<svg"), 1)
        # Y no hay ningún fichero de imagen al que apuntar.
        self.assertNotIn("-topologia.svg", texto)
        self.assertNotIn("-topologia.png", texto)
        self.assertIn(">Topología<", texto.replace("### Topología", ">Topología<"))
        # Un solo dibujo: dos planos del mismo dato acababan discrepando entre sí.
        self.assertNotIn("Cableado (L2)", texto)
        # Nada de bloques de otro lenguaje de dibujo: una sola verdad, la del motor.
        self.assertNotIn("```mermaid", texto)
        self.assertNotIn("```", texto)
        self.assertNotIn("mermaid", texto)

    def test_los_planos_salen_enteros_de_la_declaracion(self):
        """Ni un equipo inventado ni uno olvidado: lo que no está en el YAML no se dibuja."""
        lab = laboratorio()
        topologia = plano.plano(lab, "topologia")
        cableado = plano.plano(lab, "cableado")

        # Cada equipo aparece con su nombre, y cada red con el suyo y su subred.
        for nodo in lab["nodes"]:
            self.assertIn(f">{nodo["role"]}<", topologia + cableado)
        for net in lab["networks"]:
            self.assertIn(plano._bloque(net["address"]), topologia)
            self.assertIn(f">{net["name"]}<", topologia)

        # La topología dibuja la jerarquía: la pata del equipo que cruza de un área a
        # otra, una por área que toca, más los cables entre equipos de la misma área.
        # El cableado dibuja los cables declarados, uno por línea. `after` sólo ordena
        # el arranque y la colocación, no dibuja líneas.
        def conexiones(svg):
            # El gris de línea es el de una conexión: los símbolos no lo usan.
            return svg.count('stroke="#94a3b8"')

        self.assertEqual(conexiones(topologia), 2)  # rte1: una pata a lan1 y otra a lan2
        self.assertEqual(conexiones(cableado), len(lab["links"]))

        # La clase la dice el símbolo, plano y de línea: el router es el círculo con las
        # cuatro flechas y el switch la caja con las flechas cruzadas. Un laboratorio sin
        # switches no puede acabar con un símbolo de switch.
        self.assertIn('<circle r="15.5"', topologia)
        self.assertNotIn('<rect x="-24" y="-10" width="48" height="20"', topologia)

        # Y un laboratorio con switches los dibuja, con su clase en la clave.
        lab_c = laboratorio("c_enrutar_y_conmutar")
        svg_c = plano.plano(lab_c, "topologia")
        self.assertIn('<rect x="-24" y="-10" width="48" height="20"', svg_c)

    def test_el_plano_escribe_lo_que_no_cambia(self):
        """La dirección estática va en su equipo y el rango servido, en su red.

        Un plano que sólo dice «dhcp» esconde justo lo que hay que apuntar en un papel:
        qué dirección tiene cada equipo y qué rango reparte la red.
        """
        svg = plano.plano(laboratorio(), "topologia")

        # El router enseña una dirección por pata, no una sola ni ninguna.
        self.assertIn(">10.44.1.1/24<", svg)
        self.assertIn(">10.44.2.1/24<", svg)
        # El rango que sirve cada red, en la cabecera de su área y sin repetir la subred.
        self.assertIn(">dhcp 10.44.1.100-199<", svg)
        self.assertIn(">dhcp 10.44.2.100-199<", svg)
        # Un puesto que sale por DHCP lo dice, que también es un dato fijo del plano.
        self.assertIn(">dhcp<", svg)

    def test_un_equipo_en_tres_redes_se_rodea_de_ellas(self):
        """Un espacio de direcciones es una caja, y las redes que contiene van dentro.

        Las áreas hermanas no se pisan —dos redes solapadas se leen como una—, pero
        un área SÍ contiene a las suyas: eso es lo que dice la numeración.
        """
        lab = {"lab": "tres_redes", "address_spaces": ["10.70.0.0/16"],
               "networks": [{"name": "lan", "address": "10.70.1.0/24"},
                            {"name": "dmz", "address": "10.70.2.0/24"},
                            {"name": "wan", "address": "10.70.3.0/24"}],
               "nodes": [
                   {"role": "fwl1", "type": "firewall", "stage": 1,
                    "networks": ["wan", "dmz", "lan"], "address": "dhcp"},
                   {"role": "srv1", "type": "server", "stage": 2, "after": ["fwl1"],
                    "networks": ["dmz"], "address": "10.70.2.10/24"},
                   {"role": "swa1", "type": "switch", "stage": 2, "after": ["fwl1"],
                    "networks": ["lan"]},
                   {"role": "wsp1", "type": "workstation", "stage": 3, "after": ["swa1"],
                    "networks": ["lan"], "address": "dhcp"}],
               "links": []}
        svg = plano.plano(lab, "topologia")

        cajas = [tuple(float(v) for v in c) for c in re.findall(
            r'<rect x="(-?[\d.]+)" y="(-?[\d.]+)" width="([\d.]+)" height="([\d.]+)" rx="14"',
            svg)]
        # Tres redes declaradas y el espacio que las contiene: 10.70.x.x.
        self.assertEqual(len(cajas), 4)

        def dentro(pequena, grande):
            x1, y1, w1, h1 = pequena
            x2, y2, w2, h2 = grande
            return (x2 <= x1 and y2 <= y1 and x1 + w1 <= x2 + w2
                    and y1 + h1 <= y2 + h2)

        madres = [c for c in cajas if all(dentro(o, c) for o in cajas if o is not c)]
        self.assertEqual(len(madres), 1, "el espacio tiene que envolver a sus tres redes")
        redes = [c for c in cajas if c is not madres[0]]
        for i, (x1, y1, w1, h1) in enumerate(redes):
            for x2, y2, w2, h2 in redes[i + 1:]:
                # Dos redes hermanas que se solapan en el dibujo se leen como una sola.
                self.assertFalse(x1 < x2 + w2 and x2 < x1 + w1
                                 and y1 < y2 + h2 and y2 < y1 + h1,
                                 "dos áreas de red se solapan")
        for net in lab["networks"]:
            self.assertIn(f'>{net["name"]}<', svg)
        # Cada clase deja su forma: el muro del cortafuegos y la torre del servidor.
        self.assertIn('<rect x="-23" y="-13" width="46" height="26"', svg)
        self.assertIn('<rect x="-12" y="-18" width="24" height="36"', svg)

    def test_el_cableado_dice_los_puertos_de_cada_cable(self):
        lab = {"lab": "x", "address_spaces": ["10.9.0.0/16"],
               "networks": [{"name": "lan", "address": "10.9.0.0/24"}],
               "nodes": [{"role": "r", "type": "router", "stage": 1, "networks": ["lan"],
                          "address": "10.9.0.1/24"},
                         {"role": "s", "type": "switch", "stage": 2, "after": ["r"],
                          "networks": ["lan", "lan"]},
                         {"role": "h", "type": "workstation", "stage": 3, "after": ["s"],
                          "networks": ["lan"], "address": "dhcp"}],
               "links": [{"a": {"node": "r", "port": 1}, "z": {"node": "s", "port": 1}},
                         {"a": {"node": "s", "port": 2}, "z": {"node": "h", "port": 1}}]}
        svg = plano.plano(lab, "cableado")
        # Un cable, una línea; y cada punta con su puerto, junto al equipo que lo ocupa.
        self.assertEqual(svg.count('stroke="#94a3b8"'), 2)
        self.assertEqual(re.findall(r">(p\d)<", svg), ["p1", "p1", "p2", "p1"])
        # El puerto va al costado del cable, no debajo del símbolo: ahí vive el nombre.
        self.assertIn(">s<", svg)
        # El cableado no dibuja la salida a Internet: no hay cable declarado que la una.
        self.assertNotIn("Internet", svg)


class ElRegistroDeLosEquipos(unittest.TestCase):
    """El plan declara el registro de los equipos de red en lo que observa el sitio.

    Es una de las dos cosas que viven fuera del hipervisor, así que el plan no puede
    saber si falta: la declara como trabajo y el apply escribe sólo la diferencia.
    """

    def test_el_plan_declara_el_registro_de_los_equipos_de_red(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        paso = next(s for s in plan["steps"] if s["op"] == "netxms_registro")
        # Sólo los equipos de red: los puestos no tienen credencial que registrar.
        self.assertEqual([e["role"] for e in paso["equipos"]], ["rte1"])
        self.assertTrue([e for e in plan["effects"] if "registrar en lo que observa" in e])

    def test_los_puestos_no_se_registran(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        registrados = {n["role"] for n in plan["nodes"] if n["management"]}
        declarados = {e["role"] for s in plan["steps"]
                      if s["op"] == "netxms_registro" for e in s["equipos"]}
        self.assertEqual(declarados, registrados)
        self.assertNotIn("wsp1", declarados)

    def test_un_laboratorio_de_control_no_registra_nada(self):
        # El nodo de control ES el servicio que observa: no se registra a sí mismo.
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        self.assertEqual([s for s in plan["steps"] if s["op"] == "netxms_registro"], [])
        self.assertEqual([s for s in plan["steps"] if s["op"] == "netxms_mapa"], [])


class ElMapaDeLaRedEnLaVista(unittest.TestCase):
    """El plan declara el mapa de la red en lo que observa el sitio, tras el registro.

    La vista dibuja su topología sola, y ese dibujo no se parece al plano: el mapa se
    coloca donde el plano lo pone, y para eso hacen falta los equipos ya registrados —
    un elemento del mapa se apoya en un equipo de la vista—, así que va después.
    """

    def test_el_plan_declara_el_mapa_tras_el_registro(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        ops = [s["op"] for s in plan["steps"]]
        self.assertIn("netxms_mapa", ops)
        self.assertLess(ops.index("netxms_registro"), ops.index("netxms_mapa"))
        self.assertTrue([e for e in plan["effects"] if "el mapa de la red" in e])

    def test_sin_equipos_de_red_no_hay_mapa(self):
        plan = identity.plan(mundo(), laboratorio("a_bootstrap"), entorno())
        self.assertEqual([s for s in plan["steps"] if s["op"] == "netxms_mapa"], [])


class ElReinicioDeUnFichero(unittest.TestCase):
    """`restart` en un fichero: la configuración de un servicio se relee al cambiarla."""

    def laboratorio_base(self):
        lab = laboratorio("a_bootstrap")
        return copy.deepcopy(lab)

    def test_un_fichero_puede_decir_qué_servicio_lo_relee(self):
        lab = self.laboratorio_base()
        lab["nodes"][0]["configure"]["files"][0]["restart"] = "netxms-server"
        identity.validate(lab, entorno())  # no levanta: la clave es válida

    def test_un_reinicio_que_no_es_un_nombre_de_unidad_se_rechaza(self):
        lab = self.laboratorio_base()
        lab["nodes"][0]["configure"]["files"][0]["restart"] = 7
        with self.assertRaises(identity.LabError):
            identity.validate(lab, entorno())

    def test_una_clave_de_mas_en_un_fichero_se_rechaza(self):
        lab = self.laboratorio_base()
        lab["nodes"][0]["configure"]["files"][0]["reiniciar"] = "netxms-server"
        with self.assertRaisesRegex(identity.LabError, "mode\\?, restart\\?"):
            identity.validate(lab, entorno())


if __name__ == "__main__":
    unittest.main(verbosity=2)
