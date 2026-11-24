# PROPÓSITO:   escribir la región generada de la página de cada laboratorio, y su plano
#              como fichero suelto. La tabla sale de la declaración, nunca del hipervisor:
#              un documento que clavara vmids o direcciones de gestión mentiría en el
#              siguiente despliegue.
# INVARIANTES: sólo toca lo que está entre las marcas; la prosa de alrededor es del
#              humano y no se pisa (`AGENTS.md`). El plano va en los dos sitios —en la
#              página, para leerlo y verlo en el diff, y en su `.svg`, para abrirlo y
#              compartirlo— y los dos salen del MISMO dibujo en la misma pasada, así que
#              no pueden discrepar: `docs --check` los comprueba los dos.
# VER:         deployment_engine/tools/identity.py (render_docs), (plano.py)

from __future__ import annotations

import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import identity  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent


def cabecera(nombre: str) -> str:
    return (
        f"# Laboratorio `{nombre}`\n\n"
        "Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con\n"
        "`./netlabs docs` y no se edita a mano: sale de la declaración.\n\n"
    )


def plano_de(lab: dict) -> str | None:
    """El plano del laboratorio, o nada si su declaración no dibuja ninguno.

    Un laboratorio de control no declara redes: no hay nada que dibujar. Se dice con
    `None` en vez de devolver un dibujo vacío, para que quien escriba el fichero pueda
    distinguir «no hay plano» de «el plano está en blanco».
    """
    if not lab.get("networks"):
        return None
    import plano  # noqa: PLC0415  (los módulos viven en tools/)

    return plano.plano(lab, "topologia")


def escribir_plano(carpeta: pathlib.Path, nombre: str, lab: dict, comprobar: bool) -> int:
    """El plano, además, como fichero suelto al lado de la página.

    Va escrito **desde el mismo dibujo** que lleva la página —la misma llamada, en la
    misma pasada—, así que no pueden discrepar: es el mismo SVG, en texto, en un fichero
    que se puede abrir y compartir por sí solo. Sirve además de fondo para el mapa de la
    vista, que dibuja la misma colocación.
    """
    svg = plano_de(lab)
    if svg is None:
        return 0
    destino = carpeta / f"{nombre}-topologia.svg"
    contenido = svg.rstrip("\n") + "\n"
    if comprobar:
        if not destino.exists():
            print(f"falta {destino.relative_to(RAIZ)} (ejecuta `./netlabs docs`)")
            return 1
        if destino.read_text() != contenido:
            print(f"{destino.relative_to(RAIZ)}: el plano no coincide con la declaración")
            return 1
        print(f"ok     {destino.relative_to(RAIZ)}")
        return 0
    if destino.exists() and destino.read_text() == contenido:
        print(f"sin cambios {destino.relative_to(RAIZ)}")
        return 0
    destino.write_text(contenido)
    print(f"escrito {destino.relative_to(RAIZ)}")
    return 0


def escribir(nombre: str, env: dict, comprobar: bool = False) -> int:
    ruta = RAIZ / "labs" / nombre / f"{nombre}.yml"
    if not ruta.exists():
        print(f"no existe el laboratorio {nombre!r}: {ruta}")
        return 2
    lab = yaml.safe_load(ruta.read_text())
    generado = identity.render_docs(lab, env)
    pagina = ruta.with_suffix(".md")
    codigo = 0

    if not pagina.exists():
        if comprobar:
            print(f"falta {pagina.relative_to(RAIZ)} (ejecuta `./netlabs docs`)")
            codigo = 1
        else:
            pagina.write_text(cabecera(nombre) + generado)
            print(f"creado {pagina.relative_to(RAIZ)}")
    else:
        texto = pagina.read_text()
        if identity.DOC_BEGIN in texto and identity.DOC_END in texto:
            antes, resto = texto.split(identity.DOC_BEGIN, 1)
            _, despues = resto.split(identity.DOC_END, 1)
            # Entre la marca y la prosa va UNA línea en blanco: si se deja lo que hubiera,
            # cada pasada de `docs` añade una más y la página engorda sin que se note.
            despues = despues.lstrip("\n")
            nuevo = antes + generado + ("\n" + despues if despues else "")
        else:
            nuevo = texto.rstrip() + "\n\n" + generado

        # La página termina en un solo salto de línea: si no, cada pasada de `docs` deja
        # una línea en blanco más al final y el fichero crece sin que nadie lo note.
        nuevo = nuevo.rstrip("\n") + "\n"

        if comprobar:
            if nuevo != texto:
                print(f"{pagina.relative_to(RAIZ)}: la tabla no coincide con la declaración")
                codigo = 1
            else:
                print(f"ok     {pagina.relative_to(RAIZ)}")
        elif nuevo != texto:
            pagina.write_text(nuevo)
            print(f"escrito {pagina.relative_to(RAIZ)}")
        else:
            print(f"sin cambios {pagina.relative_to(RAIZ)}")

    # Y el plano, además, como fichero suelto: se puede abrir y compartir por sí solo, y
    # es el fondo que usa el mapa de la vista. Va escrito en la misma pasada, así que no
    # puede quedarse viejo sin que el de la página también lo esté.
    codigo = max(codigo, escribir_plano(ruta.parent, nombre, lab, comprobar))
    return codigo
