# PROPÓSITO:   las pruebas de la capa pura del arranque: qué interfaz se llama qué
#              cuando el router nace. Se inventan el nodo y el entorno, sin hipervisor.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio.
#              Cada caso fija el MOTIVO: la pata de gestión es la que no tiene red.
# VER:         deployment_engine/tools/converge.py

import pathlib
import sys
import unittest

import yaml

RAIZ = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))

import converge  # noqa: E402


def entorno():
    return yaml.safe_load((RAIZ / "netlabs.yml").read_text())


def router(dos_redes=True):
    """Un nodo de red con sus patas: las de laboratorio y la de gestión, la última."""
    interfaces = []
    if dos_redes:
        interfaces = [
            {"index": 0, "network": "lan1", "bridge": "vmb_uno_lan1"},
            {"index": 1, "network": "lan2", "bridge": "vmb_uno_lan2"},
        ]
    interfaces.append({"index": len(interfaces), "network": None, "bridge": "vmbr30"})
    return {
        "role": "edge",
        "type": "router",
        "mgmt_address": "10.30.0.111",
        "interfaces": interfaces,
        "networks": [i["network"] for i in interfaces if i["network"] is not None],
    }


class Interfaces(unittest.TestCase):
    def test_la_pata_de_gestion_es_la_ultima_creada(self):
        # Con dos redes de laboratorio el motor crea net0, net1 y net2; la de
        # gestión es net2, o sea ether3. Contar `networks` daría ether2 y la
        # dirección acabaría en una red de laboratorio.
        self.assertEqual(converge.management_interface(router()), "ether3")

    def test_una_sola_red_de_laboratorio_da_ether2(self):
        self.assertEqual(converge.management_interface(router(dos_redes=False)), "ether1")

    def test_sin_pata_de_gestion_se_para(self):
        nodo = router()
        nodo["interfaces"] = [i for i in nodo["interfaces"] if i["network"] is not None]
        with self.assertRaises(converge.LabError):
            converge.management_interface(nodo)

    def test_el_script_pone_la_direccion_en_la_pata_de_gestion(self):
        script = converge.bootstrap_script(router(), entorno(), "clave")
        self.assertIn("interface=ether3", script)
        self.assertNotIn("interface=ether2", script)

    def test_una_red_de_laboratorio_se_nombra_desde_uno(self):
        # `net0` de la API es `ether1` del router. Contar desde cero daría ether0,
        # que no existe y hace que la dirección se escriba en ninguna interfaz.
        self.assertEqual(converge.interface_of(router(), "lan1"), "ether1")
        self.assertEqual(converge.interface_of(router(), "lan2"), "ether2")

    def test_una_red_que_el_nodo_no_tiene_no_inventa_pata(self):
        self.assertIsNone(converge.interface_of(router(), "lan3"))


def nodo_router(dos_redes=True):
    return router(dos_redes)


class LaDiferencia(unittest.TestCase):
    def test_una_direccion_que_falta_se_escribe_en_su_pata(self):
        nodo = nodo_router()
        nodo["configure"] = {"addresses": [{"network": "lan1", "address": "10.44.1.1/24"}]}
        ops = converge.ros_ops(nodo, {"addresses": []}, "clave")
        direcciones = [o for o in ops if o["path"] == "/rest/ip/address"]
        self.assertEqual(len(direcciones), 1)
        self.assertEqual(direcciones[0]["method"], "PUT")
        self.assertEqual(direcciones[0]["body"]["interface"], "ether1")

    def test_un_servicio_que_no_existe_se_dice_y_no_se_inventa(self):
        nodo = nodo_router()
        nodo["configure"] = {"services": {"wsss": True}}
        with self.assertRaisesRegex(converge.LabError, "wsss"):
            converge.ros_ops(nodo, {"services": [{"name": "www", ".id": "*1"}]}, "clave")

    def test_un_servicio_apagado_se_enciende_por_su_id(self):
        nodo = nodo_router()
        nodo["configure"] = {"services": {"www": True}}
        ops = converge.ros_ops(nodo, {"services": [{"name": "www", ".id": "*2", "disabled": "true"}]}, "clave")
        self.assertEqual(len(ops), 1)
        self.assertEqual(ops[0]["method"], "PATCH")
        self.assertEqual(ops[0]["path"], "/rest/ip/service/*2")


if __name__ == "__main__":
    unittest.main()
