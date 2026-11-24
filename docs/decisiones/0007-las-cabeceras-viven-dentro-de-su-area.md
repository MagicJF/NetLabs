# 0007 — Las cabeceras viven dentro de su área y los equipos no llevan cartel

Fecha: 2026-11-24

## Contexto

El mapa a medida colocaba el nombre y el bloque de cada área en la primera caja de texto
libre, y cuando dentro no encontraba hueco los ponía **pegados por fuera** de la caja. En
un laboratorio con varias sedes, eso hacía que el rótulo de una red apareciera dentro de
la caja de otra red —o entre dos—, y el mapa mentía sobre a quién pertenecía cada bloque.

Además, cada equipo de red llevaba una **ficha** de texto con sus patas, interfaces,
direcciones y reparto DHCP. En los laboratorios con muchos equipos esa ficha competía por
el espacio con las cabeceras, y en la práctica no aportaba: la etiqueta grande de NetXMS
ya enseña el nombre y la IP del equipo.

## Decisión

1. El rótulo de un área se coloca **siempre dentro de su propia área**. Se prefiere la
   esquina de arriba a la izquierda —donde el plano pone sus cabeceras— y, si un cable o
   un equipo la ocupan, se prueba una rejilla dentro del área. Si el rótulo casi llena el
   área, se centra; nunca se prueba fuera de la caja.
2. Los equipos **no llevan ficha de texto**. Se quedan con la etiqueta grande de la vista
   (nombre e IP) y su icono en la posición del plano. Los cables conservan sus dos puntas
   (`p1 ether1`) y su nombre en la configuración del enlace.
3. Las pruebas comprueban que cada rótulo cae dentro de los límites de su área, que no
   pisa a otro rótulo y que no queda debajo de un cable o de un equipo.

## Consecuencias

- El mapa de la vista y el plano cuentan la misma historia: cada bloque de direcciones
  aparece dentro de la red que representa.
- Se libera el espacio que ocupaban las fichas; las cabeceras vuelven a leerse en su
  sitio natural y dejan de solaparse.
- La información de patas e interfaces sigue disponible en el cable (`p1 ether1`) y en
  la ficha del equipo dentro de NetXMS, aunque no se dibuje en el mapa.
- Los puestos de trabajo y servidores siguen sin dibujarse: no son equipos de red
  registrados en la vista. Para incluirlos hará falta darles una dirección que NetXMS
  pueda alcanzar y registrarlos como nodos; es una decisión aparte.

Ver: `docs/diseno.md` §3.4, `deployment_engine/tools/mapa.py`,
`deployment_engine/tests/test_mapa.py`.