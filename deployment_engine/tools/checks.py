# PROPÓSITO:   las comprobaciones que no necesitan hipervisor: lo que puede romperse
#              sin que nadie mire. Es la mitad barata de "lo que no se demuestra, no se
#              ha hecho", y la que se puede correr en cada commit.
# INVARIANTES: cada comprobación dice QUÉ falla y DÓNDE; un fallo no se salta.
#              Ninguna necesita credenciales: el repositorio se comprueba entero.
# LÍMITES:     no prueba el despliegue (eso es `plan`/`apply`); aquí no se habla con el
#              mundo.
# VER:         AGENTS.md §5; docs/diseno.md §2.10, §7

from __future__ import annotations

import ipaddress
import pathlib
import re
import subprocess
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import identity  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent
MOTOR = RAIZ / "deployment_engine"
IGNORAR = {".git", ".venv", "__pycache__", "node_modules", "logs"}


class _SinDuplicados(yaml.SafeLoader):
    """PyYAML se queda con el último valor de una clave repetida y no dice nada.

    Un YAML con dos `stage:` en el mismo nodo no falla: se lee como si tuviera uno,
    y el error aparece tres capas más abajo. Aquí se para en la declaración.
    """


def _constructor(loader, node, profundo=False):
    claves = set()
    for clave, _ in node.value:
        valor = loader.construct_object(clave, deep=profundo)
        if valor in claves:
            raise yaml.constructor.ConstructorError(
                None, None, f"clave duplicada: {valor!r}", clave.start_mark
            )
        claves.add(valor)
    return yaml.SafeLoader.construct_mapping(loader, node, profundo)


_SinDuplicados.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, _constructor)


def ficheros_yaml():
    for ruta in sorted(RAIZ.rglob("*")):
        if any(parte in IGNORAR for parte in ruta.parts):
            continue
        if ruta.suffix in (".yml", ".yaml") and ruta.is_file():
            yield ruta


def leer_yaml(ruta):
    with ruta.open() as fichero:
        return [(ruta, yaml.load(fichero, Loader=_SinDuplicados))]


def comprobar_yaml() -> list[str]:
    errores = []
    for ruta in ficheros_yaml():
        try:
            for _, _ in leer_yaml(ruta):
                pass
        except yaml.YAMLError as exc:
            errores.append(f"{ruta.relative_to(RAIZ)}: YAML inválido: {exc}")
    return errores


RAIZ_PERMITIDA = {
    "netlabs", "netlabs.yml", "secrets.yml", "README.md", "AGENTS.md",
    ".gitignore", ".yamllint", "deployment_engine", "labs", "docs", "logs",
}
MOTOR_PERMITIDO = {"playbooks", "tasks", "filter_plugins", "tools", "tests"}


def comprobar_estructura() -> list[str]:
    """Cada carpeta tiene un solo dueño: el motor, los laboratorios o la ejecución.

    Sin esta frontera, un fichero de configuración acaba en el sitio equivocado y
    nadie sabe si es del motor o de un laboratorio concreto. La raíz sólo guarda el
    punto de entrada, la configuración del sitio y la documentación.
    """
    errores = []
    for ruta in sorted(RAIZ.iterdir()):
        if ruta.name.startswith(".") or ruta.name in RAIZ_PERMITIDA:
            continue
        errores.append(f"{ruta.name}: no está en la estructura declarada (README.md §Estructura)")

    for ruta in sorted(MOTOR.iterdir()):
        if ruta.name.startswith(".") or ruta.name in MOTOR_PERMITIDO:
            continue
        errores.append(f"deployment_engine/{ruta.name}: el motor sólo tiene "
                       f"{', '.join(sorted(MOTOR_PERMITIDO))}")

    for carpeta in sorted((RAIZ / "labs").iterdir()):
        if not carpeta.is_dir():
            errores.append(f"labs/{carpeta.name}: no es una carpeta de laboratorio")
            continue
        permitidos = {f"{carpeta.name}.yml", f"{carpeta.name}.md"}
        for dentro in sorted(carpeta.iterdir()):
            if dentro.name not in permitidos:
                errores.append(f"labs/{carpeta.name}/{dentro.name}: un laboratorio sólo "
                               f"declara {carpeta.name}.yml y su {carpeta.name}.md; los "
                               "dibujos van dentro del .md como código Mermaid")
        if not (carpeta / f"{carpeta.name}.yml").exists():
            errores.append(f"labs/{carpeta.name}: falta {carpeta.name}.yml")

    for ruta in sorted(RAIZ.rglob("logs")):
        relativa = ruta.relative_to(RAIZ)
        if not ruta.is_dir() or any(parte.startswith(".") for parte in relativa.parts):
            continue
        if relativa.parts[:1] != ("logs",):
            errores.append(f"{relativa}: los informes van a logs/, no dentro "
                           f"del motor ni de un laboratorio")
    return errores


def cargar_entorno():
    return yaml.load((RAIZ / "netlabs.yml").open(), Loader=_SinDuplicados)


def laboratorios():
    resultado = {}
    for ruta in sorted((RAIZ / "labs").glob("*/*.yml")):
        with ruta.open() as fichero:
            resultado[ruta.parent.name] = (ruta, yaml.load(fichero, Loader=_SinDuplicados))
    return resultado


def comprobar_declaraciones(env) -> list[str]:
    errores = []
    labs = laboratorios()
    for nombre, (ruta, lab) in labs.items():
        if lab.get("lab") != nombre:
            errores.append(f"{ruta.relative_to(RAIZ)}: el fichero está en labs/{nombre}/ "
                           f"pero declara lab: {lab.get('lab')!r}")
            continue
        try:
            identity.validate(lab, env)
        except identity.LabError as exc:
            errores.append(f"{ruta.relative_to(RAIZ)}: {exc}")
    return errores


def comprobar_espacios(env) -> list[str]:
    """Dos laboratorios no pueden declarar el mismo espacio de direcciones."""
    errores = []
    vistos = {}
    gestion = ipaddress.ip_network(env["management"]["address_space"])
    for nombre, (ruta, lab) in laboratorios().items():
        for espacio in lab.get("address_spaces") or []:
            red = ipaddress.ip_network(espacio, strict=False)
            if red.overlaps(gestion):
                errores.append(f"{ruta.relative_to(RAIZ)}: {red} pisa la red de gestión {gestion}")
            for otro, otra_red in vistos.items():
                if otro != nombre and red.overlaps(otra_red):
                    errores.append(f"{ruta.relative_to(RAIZ)}: {red} se pisa con el de '{otro}' ({otra_red})")
            vistos[nombre] = red
    return errores


def comprobar_letras(env) -> list[str]:
    """Dos laboratorios no pueden compartir letra: la letra va dentro del nombre de cada cable.

    Un cable se llama por la letra del laboratorio y sus dos puntas (`c_rte1p1_swc1p1`),
    y el pool de Proxmox se llama como el laboratorio. Si dos laboratorios comparten
    letra comparten nombre de cable y de pool, y el segundo `apply` se encuentra
    puentes ajenos con el suyo. La letra es la única defensa contra eso, así que se
    comprueba aquí.
    """
    errores = []
    vistos = {}
    for nombre, (ruta, lab) in laboratorios().items():
        letra = (lab.get("lab") or "")[:1]
        if not re.fullmatch(r"[a-z]", letra):
            errores.append(f"{ruta.relative_to(RAIZ)}: el nombre del laboratorio "
                           f"{lab.get('lab')!r} no empieza por una letra de la a a la z")
            continue
        if letra in vistos:
            errores.append(
                f"{ruta.relative_to(RAIZ)}: la letra {letra!r} ya la usa '{vistos[letra]}'; "
                "dos laboratorios con la misma letra comparten nombres de cable y de pool"
            )
        else:
            vistos[letra] = nombre
    return errores


def comprobar_documentacion(env) -> list[str]:
    errores = []
    for nombre, (ruta, lab) in laboratorios().items():
        pagina = ruta.parent / f"{nombre}.md"
        if not pagina.exists():
            errores.append(f"labs/{nombre}/: falta {pagina.relative_to(RAIZ)}")
            continue
        texto = pagina.read_text()
        if identity.DOC_BEGIN not in texto or identity.DOC_END not in texto:
            errores.append(f"{pagina.relative_to(RAIZ)}: faltan las marcas de la región generada")
            continue
        generado = identity.render_docs(lab, env)
        dentro = texto.split(identity.DOC_BEGIN, 1)[1].split(identity.DOC_END, 1)[0]
        esperado = generado.split(identity.DOC_BEGIN, 1)[1].split(identity.DOC_END, 1)[0]
        if dentro.strip() != esperado.strip():
            errores.append(f"{pagina.relative_to(RAIZ)}: la tabla generada no coincide con la "
                           "declaración (ejecuta `./netlabs docs`)")
    return errores


def comprobar_pureza(env) -> list[str]:
    """El motor no puede mencionar nada de un laboratorio concreto: si lo hace, es un bug
    aunque funcione, porque el siguiente laboratorio lo hereda.

    La excepción es el vocabulario del **sitio**: el invitado de gestión y su pool se
    declaran en `netlabs.yml`, no en un laboratorio, y el motor sí habla con el servicio
    que observa el sitio (la quinta vía, `tasks/netxms.yml`). Que el laboratorio de control
    adopte ese invitado como su nodo no lo convierte en palabra de ese laboratorio; si un
    laboratorio lo reusara para otra cosa, su declaración y la del sitio discreparían y lo
    diría `comprobar_declaraciones`, no esto.
    """
    del_sitio = {env["management"]["guest"], env["management"]["pool"]}
    errores = []
    for nombre, (ruta, lab) in laboratorios().items():
        vocabulario = {nombre}
        vocabulario |= {n["role"] for n in lab.get("nodes") or []}
        vocabulario |= {n["name"] for n in lab.get("networks") or []}
        vocabulario |= set(lab.get("address_spaces") or [])
        vocabulario |= {n["address"] for n in lab.get("networks") or []}
        vocabulario -= del_sitio
        for fichero in sorted(MOTOR.rglob("*")):
            if not fichero.is_file() or fichero.suffix not in (".py", ".yml", ".yaml", ".j2"):
                continue
            # Las pruebas se inventan un laboratorio a propósito: su vocabulario es
            # un fixture, no una referencia. La pureza se mide en el motor.
            if "tests" in fichero.relative_to(MOTOR).parts:
                continue
            texto = fichero.read_text(errors="replace")
            # El nombre del laboratorio puede ser una palabra corriente (la palabra uno
            # es un artículo): se busca donde de verdad aparecería una referencia —
            # una ruta, una marca o un valor entrecomillado —, no como palabra suelta.
            nombre_del_lab = nombre
            for patron in (rf"labs/{re.escape(nombre_del_lab)}\b",
                           rf"lab={re.escape(nombre_del_lab)}\b",
                           rf"lab:\s*{re.escape(nombre_del_lab)}\b",
                           rf"['\"]{re.escape(nombre_del_lab)}['\"]"):
                if re.search(patron, texto):
                    errores.append(f"{fichero.relative_to(RAIZ)}: menciona {nombre_del_lab!r}, que es "
                                   f"de un laboratorio concreto (labs/{nombre})")
                    break
            for palabra in sorted(vocabulario - {nombre_del_lab}):
                # Un nombre de dos letras coincide con media lengua castellana (la palabra uno es un artículo). Los CIDR y las direcciones, que son lo que de verdad
                # distingue, se comprueban siempre.
                if len(palabra) < 3:
                    continue
                if re.search(rf"(?<![\w.-]){re.escape(palabra)}(?![\w-])", texto):
                    errores.append(f"{fichero.relative_to(RAIZ)}: menciona {palabra!r}, que es "
                                   f"de un laboratorio concreto (labs/{nombre})")
    return errores


def comprobar_enlaces() -> list[str]:
    errores = []
    patron = re.compile(r"\[[^\]]*\]\(([^)]+)\)")
    for ruta in sorted(RAIZ.rglob("*.md")):
        if any(parte in IGNORAR for parte in ruta.parts):
            continue
        for destino in patron.findall(ruta.read_text()):
            if destino.startswith(("http://", "https://", "#", "mailto:")):
                continue
            limpio = destino.split("#", 1)[0]
            if not (ruta.parent / limpio).exists():
                errores.append(f"{ruta.relative_to(RAIZ)}: el enlace {destino!r} no lleva a ningún sitio")
    return errores


def comprobar_pruebas() -> list[str]:
    carga = unittest.defaultTestLoader.discover(str(RAIZ / "deployment_engine" / "tests"))
    resultado = unittest.TextTestRunner(verbosity=0, stream=open("/dev/null", "w")).run(carga)
    if resultado.wasSuccessful():
        return []
    fallos = [str(t[0]) for t in resultado.failures + resultado.errors]
    return [f"pruebas: {f}" for f in fallos]


def comprobar_yamllint() -> list[str]:
    """Si yamllint está instalado, sus reglas también cuentan. Si no, se dice y se sigue:
    la comprobación que no depende de él ya se hizo arriba."""
    if not _hay("yamllint"):
        print("nota: yamllint no está instalado; se omite el estilo (el YAML ya se validó).")
        return []
    proceso = subprocess.run(
        ["yamllint", "-f", "parsable", str(RAIZ / "netlabs.yml"),
         str(RAIZ / "deployment_engine"), str(RAIZ / "labs")],
        capture_output=True, text=True,
    )
    return [linea for linea in proceso.stdout.splitlines() if linea.strip()]


def _hay(programa: str) -> bool:
    from shutil import which

    return which(programa) is not None


def ejecutar() -> int:
    env = cargar_entorno()
    comprobaciones = [
        ("estructura del repositorio", comprobar_estructura),
        ("YAML válido y sin claves duplicadas", lambda: comprobar_yaml()),
        ("declaraciones del vocabulario cerrado", lambda: comprobar_declaraciones(env)),
        ("espacios de direcciones disjuntos", lambda: comprobar_espacios(env)),
        ("letras de laboratorio distintas", lambda: comprobar_letras(env)),
        ("documentación generada al día", lambda: comprobar_documentacion(env)),
        ("el motor no conoce ningún laboratorio", lambda: comprobar_pureza(env)),
        ("enlaces de la documentación", comprobar_enlaces),
        ("pruebas de la capa pura", comprobar_pruebas),
        ("estilo YAML (yamllint, si está)", comprobar_yamllint),
    ]
    errores = []
    for nombre, comprobacion in comprobaciones:
        fallos = comprobacion()
        if fallos:
            print(f"FALLA  {nombre}")
            errores += fallos
        else:
            print(f"ok     {nombre}")
    if errores:
        print("\n" + "\n".join(f"  - {error}" for error in errores))
        return 1
    print("\nnetlabs check: en verde")
    return 0


if __name__ == "__main__":
    sys.exit(ejecutar())
