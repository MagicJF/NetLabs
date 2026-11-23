# PROPÓSITO:   las pruebas de los filtros que unen Ansible con la capa pura. Se prueban
#              con datos inventados, sin hipervisor: lo que se demuestra es que un
#              invitado ajeno al motor no puede tumbar la lectura del clúster.
# INVARIANTES: ninguna prueba habla con la API ni escribe en el repositorio; corren con
#              la biblioteca estándar (unittest).
# VER:         deployment_engine/filter_plugins/netlabs.py, tools/identity.py

import importlib.util
import pathlib
import sys
import unittest

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
_spec = importlib.util.spec_from_file_location(
    "netlabs_filtros", RAIZ / "deployment_engine" / "filter_plugins" / "netlabs.py")
filtros = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(filtros)

sys.path.insert(0, str(RAIZ / "deployment_engine" / "tools"))
import identity  # noqa: E402


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
        mundo = {"guests": [{"vmid": 100, "cores": 1}, {"vmid": 101, "cores": 4}]}
        salida = filtros.netlabs_con_config(mundo, {"100": {"cores": 2, "memory": 2048}})
        self.assertEqual(salida["guests"][0]["config_cores"], 2)
        self.assertEqual(salida["guests"][0]["config_memory"], 2048)
        # El que no tiene config leído se queda con lo que dijo el clúster.
        self.assertNotIn("config_cores", salida["guests"][1])
        self.assertNotIn("config_memory", salida["guests"][1])


if __name__ == "__main__":
    unittest.main()