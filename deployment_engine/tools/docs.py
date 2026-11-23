# PROPÓSITO:   escribir la región generada de la página de cada laboratorio. La tabla
#              sale de la declaración, nunca del hipervisor: un documento que clavara
#              vmids o direcciones de gestión mentiría en el siguiente despliegue.
# INVARIANTES: sólo toca lo que está entre las marcas; la prosa de alrededor es del
#              humano y no se pisa.
# VER:         deployment_engine/tools/identity.py (render_docs)

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

    return codigo
