# 0004 — El mapa de la vista lo coloca el plano, rótulo a rótulo

**Fecha:** 23 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `deployment_engine/tools/mapa.py`, `tasks/netxms_mapa.yml`, `converge.netxms_mapa_*`
y `labs/*/<lab>*.md`. Es el **mapa a medida** de la quinta vía (`docs/diseno.md` §3.4).

## El problema

El mapa a medida ya estaba: la vista dibujaba las áreas del plano como cajas, cada equipo donde
el plano lo pone y cada cable entre sus dos puntas (ADR 0003 abrió la vía; `mapa.py` lo escribe).
Al mirarlo en la consola se vieron **dos defectos que no se ven en el JSON**:

- **Las líneas apenas se distinguen.** La vista dibuja los enlaces con su criterio —un gris
  ancho y translúcido— sobre el relleno gris de las cajas de grupo, que es del mismo tono.
- **Las líneas tapan las direcciones.** El rótulo de cada caja lo pega la vista **arriba a la
  izquierda** de la caja, que es justo por donde entran los cables que bajan del núcleo a cada
  sede: la línea pasa por encima de «10.20.55.0 - 10.20.55.255 (/24)» y no se lee.

## Lo que se midió contra la vista (7.0.4, API v1)

- Los cables se dibujan **por encima de todo** lo demás, rótulos incluidos: cualquier texto que
  quede debajo de un cable es ilegible, y no hay ajuste que lo cambie.
- El mapa **acepta ajustes propios** —`defaultLinkColor`, `defaultLinkColorSource`,
  `defaultLinkWidth`, `defaultLinkStyle`, `defaultLinkRouting`— y los conserva al releerlos: con
  `colorSource: 0` el cable usa el color del mapa, no el del estado del enlace.
- Un **elemento de texto** (`type: 5`) se escribe en `TextBox` (un JSON dentro del JSON, con
  `text`, `fontSize`, `backgroundColor`, `borderColor`, `borderRequired`) y se **lee de vuelta en
  `config`**: el mismo dato con otro nombre, y con los acentos escapados. Se coloca en
  `posX`/`posY` libres y no ocupa el hueco de un equipo, así que puede ir donde no pase un cable.
- Una caja de grupo **puede ir sin rótulo** (`title: ""`) y el área se sigue viendo: el nombre y el
  bloque dejan de estar pegados a su esquina.

Lo que se midió de tamaños —con la fuente que se le pide (9 pt), que es la que hace legible el
bloque sin comerse el área—: «Engineering · 10.20.66.0 - 10.20.66.255 (/24)» mide **308 px** y el
área de una sede **300**: no cabe en ningún rincón sin pisar un cable. Partido en «Engineering
(/24)» y «10.20.66.0 - 10.20.66.255», el renglón más ancho mide **167 px** y sí cabe.

## Las opciones (y las descartadas)

- **Rotular la caja desde dentro del plano** —lo que hace el SVG— y aceptar que la línea tape el
  texto: es el defecto que se quiere corregir, así que no.
- **Encoger la letra hasta que el rótulo quepa**: con 6 pt entraba, pero el bloque —que es el dato
  que se viene a leer— deja de leerse. Se descarta por el motivo contrario al que se busca.
- **Nombrar las áreas con una rejilla y dejar que la vista reparta**: la vista no reparte rótulos;
  el que se dibuja donde su caja lo pone siempre es uno.
- **Elegida: dos cajas de texto por área, colocadas por programa** —el nombre con su prefijo y,
  debajo, el bloque—, en el primer hueco del área por el que no pase ningún cable ni se apoye
  ningún equipo, y las cajas de grupo **sin rótulo**.

## La decisión

1. **La caja no lleva rótulo; el texto va aparte.** Cada área del plano se rotula con **dos cajas
   de texto** —«Ventas (/24)» y «10.48.11.0 - 10.48.11.255»— colocadas en el primer rincón libre.
   Se buscan primero los rincones de dentro, luego una rejilla por toda el área y, sólo si no hay
   ninguno, justo encima o justo debajo: un rótulo fuera dice de qué área es; uno tapado, no dice
   nada. La búsqueda va **de la zona más pequeña a la más grande** (medido: al revés, el rótulo del
   laboratorio caía dentro de una sede y dejaba a la sede sin sitio).
2. **El mapa dice cómo quiere sus cables**: azul pizarra de color propio, trazo 2 —la mitad del que
   pone la vista—, continuo y recto. Los ajustes viajan con el mapa, así que un cambio de color
   cuenta como cambio y hace reescribirlo, igual que mover un equipo.
3. **El prefijo se lee junto al nombre.** «Ventas (/24)» arriba y el bloque debajo; el bloque
   entero con su prefijo no cabe, y el prefijo es lo que menos sitio necesita donde más falta hace.

Lo que **no** cambia: el mapa se escribe **sólo si no es ya el que el plano pide** —y ahora la
comparación incluye los ajustes, las cajas de texto y su contenido—, y la geometría sigue
leyéndose del propio plano.

## Consecuencia que hay que recordar

La colocación **no se comprueba a ojo**: `test_mapa` recorre **todos los laboratorios del
repositorio** y exige que ningún cable y ningún equipo pisen el rótulo de ninguna área. Es una
prueba con dientes: al escribirla encontró los cuatro rincones del repositorio donde un rótulo no
cabe, y de ahí salieron el reparto en dos renglones y el orden de la búsqueda.

El día que un laboratorio nuevo tenga un área más apretada que las de hoy, **la prueba lo dice**.
Si el hueco no existe, el rótulo sale justo fuera de su área —se lee igual— y no se queda debajo de
un cable en silencio.
