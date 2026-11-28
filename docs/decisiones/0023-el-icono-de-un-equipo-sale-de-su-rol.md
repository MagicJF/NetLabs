# 0023 — El icono de un equipo sale de su rol, no de lo que la vista adivine

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** con qué dibujo aparece cada equipo en el mapa a medida de la vista; de dónde sale
ese dato y quién lo fija.

## El problema

El mapa a medida no elige el icono de un equipo: sólo **pide el icono** de cada objeto
(`objectDisplayMode: 0`, `mapa.py`), y la vista lo resuelve por dentro. La pregunta era por qué
un router y un switch ya salían distintos —sin que nadie lo pidiera— y un **servidor** y una
**estación de trabajo** no: los dos aparecían con el mismo dibujo.

Se leyó el código de la vista para saber de dónde sale el icono. No sale del mapa ni de un campo
del objeto elegido a mano: `MapLabelProvider.getImage()` lo resuelve en este orden —

1. la **imagen del propio objeto** (`object.getMapImage()`), si la tiene;
2. la de su **categoría**, si el objeto no trae imagen y tiene una;
3. proveedores de imagen registrados, y por último
4. la imagen que la vista da **por la clase** del objeto.

Y en ese último escalón está la explicación: un router y un switch se separan porque sus
**capacidades SNMP** son distintas (`isRouter`, `isBridge`), que la vista aprende al sondearlos; un
servidor y un puesto de trabajo son los dos un `Node` genérico de Linux, **sin ninguna capacidad
que los distinga** —medido en la instalación: `wsp1` y `svs1` salen los dos con `isRouter=false`,
`isBridge=false` y todos los focos apagados—, así que caen en el mismo dibujo genérico. No era un
fallo del mapa: era que el mapa nunca eligió icono.

## La Decisión

**1. El motor fija la imagen del objeto, por el tipo del equipo.** Al registrar un equipo, el motor
le pone su `mapImage` —una propiedad **del objeto**, que es de donde la vista la lee—. El tipo sale
del **rol** (las dos letras del nombre), no de una lista de equipos de un laboratorio: vale para
cualquier laboratorio y para cualquier rol del vocabulario.

**2. La tabla de imágenes es la biblioteca que la vista ya trae, no una inventada.** Los
identificadores son los que siembra el administrador de base de datos de la vista (su biblioteca de
imágenes trae `Server`, `Router`, `Switch`, `Node`, …). Un UUID que no exista dejaría al equipo sin
dibujar, así que no se inventa ninguno:

- router y cortafuegos → `Router`. El cortafuegos comparte el dibujo del router a propósito: la
  biblioteca **no trae** una imagen de cortafuegos, y no se finge que la traiga.
- switch → `Switch`; servidor → `Server`; puesto de trabajo → `Node` (el dibujo de un ordenador de
  escritorio, que es un puesto).
- un **tipo que no esté en la tabla** —uno que se añada mañana— cae en el nodo genérico: un rol
  desconocido no deja al equipo sin dibujar.

**3. Se fija en el alta y se corrige en los que ya estaban.** Un equipo registrado antes de esta
decisión no lleva imagen; sale con el dibujo genérico hasta que el motor se la pone. La corrección
es un `PATCH` del objeto que va **aparte** de las credenciales —es una propiedad independiente— y
que **sólo se aplica a un equipo que consta de este laboratorio** (lleva su marca `netlabs lab=…` en
el comentario). Es la misma prueba de propiedad que gobierna el borrado: un objeto con el nombre y la
dirección de un equipo pero sin la marca —uno escrito a mano, o el resto de otro laboratorio que
ocupa esa dirección— no se toca, ni para dibujarlo. Un equipo que ya lleva su imagen no escribe nada,
así que `apply` sigue siendo idempotente.

## Por qué no se deja que la vista adivine

Se podría haber «arreglado» dándole a los servidores una capacidad SNMP falsa o un nombre de clase
distinto para que la heurística de la vista los separase. Se descarta: sería mentirle a la vista
sobre lo que el equipo **es** para conseguir un dibujo. La imagen es un dato del inventario —qué
tipo de aparato es— y se declara como tal, en el objeto, por el rol; no se deduce de una capacidad
que el equipo no tiene.

## Consecuencias

- Un servidor deja de confundirse con un puesto en el mapa: los dos son nodos genéricos, pero el
  motor les pone imágenes distintas.
- Un router y un switch siguen saliendo distintos —ahora de forma **explícita**, no porque la vista
  los descubra—, y un laboratorio que no sea éste recibe el mismo trato sin tocar nada.
- Un tipo nuevo que mañana no esté en la tabla no rompe el alta: sale con el nodo genérico, que es
  el estado de hoy, y añadirlo es añadir una línea.
- El cortafuegos se dibuja como un router. Se acepta a cambio de no inventar una imagen que la
  biblioteca no tiene.

Ver: `deployment_engine/tools/converge.py` (`NETXMS_ICONO_POR_TIPO`, `netxms_icono_de`,
`netxms_imagen_cmd`, `netxms_ops`); `deployment_engine/tools/mapa.py` (cabecera);
`deployment_engine/tests/test_converge.py` (`ElIconoQueLaVistaDibuja`); `docs/diseno.md` §3.4.
