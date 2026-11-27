# 0015 — El mapa legible manda sobre el dibujo

Fecha: 2026-11-27

## Contexto

El mapa de una sede salía ilegible por seis motivos distintos, y los seis tenían la misma raíz:
el motor copiaba el dibujo del plano casi a ciegas. La vista no es el plano. El plano es un
documento: se lee de cerca, tiene el detalle del cableado y no cambia. La vista es un tablero
que se mira de lejos, donde cada equipo es un icono y cada cable es una línea fina.

Medido sobre `d_acme_dos_sedes` y `f_acme_cuatro_departamentos`: el hueco reservado para cada
equipo era de 100×100 fijo, así que el icono de un puesto se comía el bloque de direcciones de
su área; las puntas del cable decían `p2 ether2` y con cuatro puertos juntos no se leían; los
routers de borde aparecían enteros dentro de una sede y no en la frontera que unen; la cabecera
de un área acababa al fondo de la caja en cuanto un cable rozaba su esquina; la nube de Internet
llevaba bloque de direcciones, como si fuese una red más de la casa.

## Decisión

**La legibilidad de la vista manda sobre la fidelidad al plano, y el espacio que ocupa cada cosa
se declara en vez de suponerse.**

1. **El hueco es el del símbolo.** El plano escribe en cada equipo `data-ancho` y `data-alto` con
   lo que ocupa su símbolo, y la vista reserva exactamente eso (con un mínimo). Un icono no puede
   tapar la cabecera de su propia red: era lo que pasaba cuando todos medían 100×100.
2. **La punta del cable dice el puerto, no la interfaz.** `p1`, `p2`, `p3`. La interfaz no se
   pierde: viaja en el número de interfaz del enlace, que es lo que la vista necesita para atar
   la punta a su equipo.
3. **El router de borde va a caballo.** Se coloca sobre la frontera de las redes que une —el
   techo de la caja de su compañía—, no dentro de una de ellas. Es lo que representa su papel
   y lo que el plano ya dibujaba así.
4. **La cabecera busca su esquina.** Primero arriba a la izquierda; si un equipo o un cable la
   tapan, baja por **el mismo borde izquierdo** antes de cruzar el área. Los cables finos ya no
   destierran una cabecera al fondo de la caja: una cabecera arrinconada no la lee nadie, y un
   cable por debajo del texto se lee igual. Un **equipo** encima del rótulo sí es un no: tapa la
   letra y además miente, porque parece estar en la red que no es.
5. **La nube dice lo que es.** La salida a Internet no lleva bloque de direcciones —no es una red
   de la casa—: lleva el lema «salida a la red pública».
6. **El plano reparte con aire.** No hace falta ceñirse al dibujo del SVG: si hace falta más
   anchura para que se entienda, se toma.

## Consecuencias

- Un rótulo puede quedar cruzado por un cable. Es deliberado: la alternativa medía peor (cabecera
  al fondo del área). Lo que no puede pasar —y hay prueba— es que un equipo lo tape o que dos
  cabeceras se monten.
- El mapa y el plano dejan de coincidir al píxel. La regla anterior —«el mapa lo coloca el
  plano» (ADR 0004)— sigue valiendo para el **reparto** (qué caja contiene a qué), pero la
  vista ajusta el detalle por legibilidad.
- Las pruebas que exigían «ningún cable tapa un rótulo» se sustituyen por «ningún equipo tapa un
  rótulo y dos cabeceras no se montan». Una prueba que mide lo que ya no se quiere es una
  trampa.
