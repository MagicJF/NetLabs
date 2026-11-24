# 0005 — El mapa de la vista dice lo que dice el YAML

**Fecha:** 23 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `deployment_engine/tools/mapa.py`, `converge.netxms_interfaces_de`,
`tools/plano.py` (los `data-*` del SVG) y `tasks/netxms_mapa.yml`.
Es la letra pequeña del **mapa a medida** (ADR 0003 abrió la vía, ADR 0004 lo colocó).

## El problema

El mapa ya ponía cada equipo y cada cable donde el plano, pero ahí se acababa: un cable en la
vista unía dos iconos y **no decía de qué equipo sale, por qué puerto ni por qué interfaz va**,
y al pasar por encima de un equipo la vista no decía **cuántas patas tiene ni a qué red va cada
una**. Todo eso está escrito en el YAML del laboratorio —el cableado, las interfaces, las
direcciones, quién reparte DHCP— y el plano ya lo sabía; la vista, no.

## Lo que se midió contra la vista (7.0.4, API v1)

- Un **enlace admite** `name`, `connectorName1`, `connectorName2`, `interface1` e `interface2`,
  y los conserva al releerlo. Comprobado sobre los 6 cables del laboratorio `e_tres_routers`:
  cada uno lleva su nombre de puente en el despliegue (`e_swc1p1_rta1p1`, el mismo que compone
  `identity.cables`), su puerto en cada punta (`p1 ether1`) y el número de objeto de la
  interfaz (`437`), que es distinto en cada punta.
- Las **interfaces son objetos** de la vista —117 en el censo— y se llaman como las llama su
  equipo: `lo`, `ether1`, `ether2`… Es el mismo nombre con el que el motor conecta cada pata:
  el puerto `p3` del plano es la `ether3` del equipo, así que el mapa puede atarlas por nombre.
- El **censo de interfaces no dice de quién es cada una**: no trae el padre, y filtrar por él lo
  ignora. La ruta de hijos de un equipo contesta de forma intermitente, así que no se puede
  apoyar nada en ella. La **ficha del equipo** —que ya se leía para registrar los equipos— sí
  trae la lista de sus hijos, que son justo sus interfaces.

## La decisión

1. **Cada cable dice por dónde va.** El nombre del cable es el del puente que lo tiende el
   despliegue, y cada punta lleva su puerto y su interfaz (`p1 ether1`), atada al objeto de la
   vista por su número. Se **cruzan las dos lecturas que ya se hacían** —el censo de interfaces
   pone el nombre de cada número, la ficha de cada equipo dice cuáles son suyos—, así que el
   mapa no pregunta nada de más a la vista.
2. **Cada equipo lleva su ficha** como caja de texto, derivada del YAML y no escrita a mano:
   su papel, sus patas (interfaz y dirección) y, si reparte direcciones, que reparte DHCP.
3. **El mapa dice lo que escribió**, para poder comprobarlo de un vistazo en la salida de
   `apply`: equipos, cables, áreas, etiquetas e interfaces atadas a sus puntas. Y sigue
   escribiéndose **sólo si el de la vista no es ya el que el plano pide**, fichas y cables
   incluidos.

## Consecuencia que hay que recordar

Los atributos `data-*` que `plano.py` deja en el SVG de los cables y los puertos son el puente
entre el YAML y la vista: quien los toque, toca el mapa. Y el nombre de una interfaz **lo pone
el equipo**: si un día un equipo nombra sus patas de otra forma, el atado deja de encontrarlas.
Por eso el censo y la ficha se cruzan, y por eso `test_converge` fija el caso del equipo que no
está en la vista y el de la interfaz que es de otro laboratorio: lo que no se encuentra no se
ata, y el cable se dibuja igual pero sin decir por dónde va.
