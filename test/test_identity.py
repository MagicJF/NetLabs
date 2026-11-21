# PROPÓSITO:   las pruebas de la capa pura. Se inventan el mundo y la declaración y se
#              comprueba la identidad y la diferencia sin hipervisor: es lo que permite
#              saber que la derivación es una función y no una costumbre.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest), sin instalar nada.
#              Cada rechazo probado comprueba el MOTIVO, no sólo que falle.
# VER:         deployment_engine/tools/identity.py

import copy
import pathlib
import sys
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import identity  # noqa: E402


def entorno():
    return yaml.safe_load((RAIZ / "netlabs.yml").read_text())


def laboratorio(nombre="uno"):
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
                         {"edge": 102, "pc-1": 103, "pc-2": 104})

    def test_plan_conserva_el_vmid_de_un_rol_que_ya_vive_en_el_pool(self):
        viejos = [{"vmid": 200, "name": "rt-edge", "type": "qemu", "pool": "netlabs-lab-uno",
                   "description": "netlabs lab=uno role=edge", "status": "running"}]
        plan = identity.plan(mundo(guests=viejos), laboratorio(), entorno())
        self.assertEqual({n["role"]: n["vmid"] for n in plan["nodes"]}["edge"], 200)
        self.assertEqual(len({n["vmid"] for n in plan["nodes"]}), 3)

    def test_plan_es_idempotente_cuando_el_mundo_ya_es_lo_declarado(self):
        primero = identity.plan(mundo(), laboratorio(), entorno())
        creados = [{"vmid": n["vmid"], "name": n["name"],
                    "type": "qemu" if n["guest"] == "qemu" else "lxc",
                    "pool": "netlabs-lab-uno", "description": n["description"], "status": "running"}
                   for n in primero["nodes"]]
        puentes = [{"iface": s["bridge"], "type": "bridge", "cidr": None, "comments": s["comment"]}
                   for s in primero["steps"] if s["op"] == "bridge_ensure"]
        segundo = identity.plan(mundo(guests=creados, bridges=puentes, pools=["netlabs-lab-uno"]),
                                laboratorio(), entorno())
        self.assertEqual([s for s in segundo["steps"]
                          if s["op"] in ("guest_create", "pool_ensure", "bridge_ensure", "guest_start")], [])

    def test_plan_es_determinista(self):
        self.assertEqual(identity.plan(mundo(used=[100]), laboratorio(), entorno()),
                         identity.plan(mundo(used=[100]), laboratorio(), entorno()))

    def test_plan_marca_los_puentes_con_el_laboratorio(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        self.assertEqual({s["bridge"]: s["comment"] for s in plan["steps"] if s["op"] == "bridge_ensure"},
                         {"vmb_uno_lan1": "netlabs lab=uno network=lan1",
                          "vmb_uno_lan2": "netlabs lab=uno network=lan2"})

    def test_el_router_nace_con_la_pata_de_gestion_la_ultima(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        edge = next(n for n in plan["nodes"] if n["role"] == "edge")
        self.assertEqual([i["network"] for i in edge["interfaces"]], ["lan1", "lan2", None])
        self.assertEqual(edge["interfaces"][-1]["bridge"], "vmbr30")
        self.assertTrue(edge["mgmt_address"].startswith("10.30."))

    def test_los_puestos_no_tienen_pata_de_gestion(self):
        plan = identity.plan(mundo(), laboratorio(), entorno())
        for node in plan["nodes"]:
            if node["type"] == "workstation":
                self.assertIsNone(node["mgmt_address"])
                self.assertTrue(all(i["network"] is not None for i in node["interfaces"]))


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
        lab["nodes"][1]["after"] = ["pc-2"]
        lab["nodes"][2]["after"] = ["pc-1"]
        with self.assertRaisesRegex(identity.LabError, "ciclo"):
            identity.plan(mundo(), lab, entorno())

    def test_rechaza_pisar_el_espacio_de_otro_laboratorio_vivo(self):
        puentes = [{"iface": "vmb_otro_lan1", "type": "bridge", "cidr": "10.44.1.1/24",
                    "comments": "netlabs lab=otro network=lan1"}]
        with self.assertRaisesRegex(identity.LabError, "se pisa con el de 'otro'"):
            identity.plan(mundo(bridges=puentes), laboratorio(), entorno())

    def test_rechaza_un_puente_ajeno_con_el_mismo_nombre(self):
        puentes = [{"iface": "vmb_uno_lan1", "type": "bridge", "cidr": None, "comments": ""}]
        with self.assertRaisesRegex(identity.LabError, "no es suyo"):
            identity.plan(mundo(bridges=puentes), laboratorio(), entorno())

    def test_rechaza_un_nombre_de_puente_que_no_cabe(self):
        lab = {
            "lab": "uno",
            "address_spaces": ["10.44.0.0/16"],
            "networks": [{"name": "larguisima", "address": "10.44.1.0/24"}],
            "nodes": [{"role": "srv", "type": "server", "stage": 1,
                       "networks": ["larguisima"], "address": "dhcp",
                       "resources": {"cores": 1, "memory": 256, "disk": 2}}],
        }
        with self.assertRaisesRegex(identity.LabError, "15 caracteres"):
            identity.plan(mundo(), lab, entorno())

    def test_rechaza_cambiar_de_contenedor_a_maquina(self):
        viejos = [{"vmid": 200, "name": "rt-edge", "type": "lxc", "pool": "netlabs-lab-uno",
                   "description": "netlabs lab=uno role=edge", "status": "running"}]
        with self.assertRaisesRegex(identity.LabError, "contenedor a máquina"):
            identity.plan(mundo(guests=viejos), laboratorio(), entorno())


class Documentacion(unittest.TestCase):
    def test_la_documentacion_generada_no_lleva_nada_derivado(self):
        texto = identity.render_docs(laboratorio(), entorno())
        self.assertIn("edge", texto)
        self.assertIn("10.44.2.0/24", texto)
        self.assertNotIn("vmid", texto.lower())
        self.assertNotIn("BC:24:11", texto)

    def test_la_documentacion_generada_es_estable(self):
        self.assertEqual(identity.render_docs(laboratorio(), entorno()),
                         identity.render_docs(laboratorio(), entorno()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
