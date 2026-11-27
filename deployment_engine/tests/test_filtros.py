# PROPÓSITO:   las pruebas de los filtros que unen Ansible con la capa pura. Se prueban
#              con datos inventados, sin hipervisor: lo que se demuestra es que un
#              invitado ajeno al motor no puede tumbar la lectura del clúster.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest).
# VER:         deployment_engine/filter_plugins/netlabs.py, tools/identity.py

import importlib.util
import json
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "netlabs_filtros", RAIZ / "deployment_engine" / "filter_plugins" / "netlabs.py")
filtros = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filtros)

sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))
import converge  # noqa: E402
import identity  # noqa: E402
import mapa  # noqa: E402


class LasDireccionesVivas(unittest.TestCase):
    def test_deriva_las_de_los_invitados_del_motor(self):
        invitados = [{"vmid": 100}, {"vmid": 200}]
        self.assertEqual(
            filtros.netlabs_direcciones_vivas(invitados, "10.30.0.0/16"),
            [str(identity.derive_management(100, "10.30.0.0/16")),
             str(identity.derive_management(200, "10.30.0.0/16"))])

    def test_un_invitado_ajeno_que_no_cabe_en_el_plano_se_salta(self):
        """Un invitado con un vmid que no cabe no puede bloquear el registro.

        Demuestra que sólo se derivan las direcciones de los invitados que pueden tener
        una del motor: un `vmid` 70000 en el clúster lanzaba `LabError` y dejaba el
        laboratorio sin registrar en la vista.
        """
        invitados = [{"vmid": 100}, {"vmid": 70000}]
        self.assertEqual(filtros.netlabs_direcciones_vivas(invitados, "10.30.0.0/16"),
                         [str(identity.derive_management(100, "10.30.0.0/16"))])

    def test_un_plano_mal_declarado_se_sigue_diciendo(self):
        with self.assertRaisesRegex(identity.LabError, "/16"):
            filtros.netlabs_direcciones_vivas([{"vmid": 100}], "10.30.0.0/24")


class LosRecursosEscritos(unittest.TestCase):
    def test_pega_el_config_leido_y_respeta_el_que_no_lo_tiene(self):
        mundo = {"invitados": [{"vmid": 100, "cores": 1}, {"vmid": 101, "cores": 4}]}
        salida = filtros.netlabs_con_config(mundo, {"100": {"cores": 2, "memory": 2048}})
        self.assertEqual(salida["invitados"][0]["config_cores"], 2)
        self.assertEqual(salida["invitados"][0]["config_memory"], 2048)
        # El que no tiene config leído se queda con lo que dijo el clúster.
        self.assertNotIn("config_cores", salida["invitados"][1])
        self.assertNotIn("config_memory", salida["invitados"][1])


class LaHuellaDelMapaPorElFiltro(unittest.TestCase):
    """El comentario del mapa llega entero al motor: ahí viaja la huella de lo que escribió.

    Demuestra que el filtro no se queda el argumento: con la huella del dibujo que el plano
    pide, el mapa no se toca; con otra, se le vuelve a dejar la suya. Si el filtro se quedara
    el comentario, los dos casos saldrían iguales y un `apply` borraría el dibujo que alguien
    hubiera ajustado a mano, que es justo lo que la huella evita.
    """

    API = "http://127.0.0.1:8000/v1"
    LAB = {
        "lab": "z_prueba",
        "networks": [{"name": "lan1", "address": "10.20.0.0/24"}],
        "nodes": [{"role": "rte1", "name": "rte1", "type": "router",
                   "mgmt_address": "10.20.0.11", "networks": ["lan1"]}],
        "links": [],
    }
    NODOS = LAB["nodes"]
    CENSO = [{"id": 100, "name": "rte1", "ipAddress": {"address": "10.20.0.11"}}]
    SVG = ('<svg xmlns="http://www.w3.org/2000/svg" width="400" height="300">'
           '<g data-area="Núcleo" data-x="10" data-y="10" data-ancho="180" data-alto="120" '
           'data-subred="10.20.0.0/24" data-nube="0"/>'
           '<g data-rol="rte1" data-x="60.0" data-y="60.0"/></svg>')

    def plan(self, actual, comentarios="", objeto=None):
        # El filtro, tal y como Ansible lo ve: lo que se comprueba es que el comentario del
        # mapa llega al motor y no se queda en el camino. El objeto va con sus banderas ya
        # encendidas —como el de un mapa que ya pasó por el motor— porque lo que se mira
        # aquí es la huella, no el marco de estado.
        if objeto is None:
            objeto = {"flags": {b: True for b in converge.BANDERAS_QUE_EL_MAPA_ENSENA}}
        cual = filtros.FilterModule().filters()["netlabs_netxms_mapa_ops"]
        return cual(self.LAB, self.NODOS, self.CENSO, actual,
                    self.API, "7", [], [], comentarios, objeto)

    def test_la_huella_del_dibujo_que_ya_esta_deja_el_mapa_quieto(self):
        dibujo = json.loads(self.plan(None)["ops"][0]["cuerpo"])
        comentario = f"netlabs lab=z_prueba plano={mapa.huella(dibujo)}"
        plan = self.plan(dibujo, comentario)
        self.assertEqual(plan["ops"], [], "el filtro no ha reenviado el comentario del mapa")
        self.assertEqual(plan["motivo"], "ya es el del plano")

    def test_una_huella_que_no_cuadra_hace_volver_a_dejarla(self):
        dibujo = json.loads(self.plan(None)["ops"][0]["cuerpo"])
        plan = self.plan(dibujo, f"netlabs lab=z_prueba plano={'0' * 40}")
        self.assertEqual(len(plan["ops"]), 1, "la huella vieja se ha quedado sin corregir")
        self.assertEqual(plan["motivo"], "la huella no cuadraba")


if __name__ == "__main__":
    unittest.main()