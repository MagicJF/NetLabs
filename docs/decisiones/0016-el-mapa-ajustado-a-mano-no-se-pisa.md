# 0016 — El mapa que alguien ajusta a mano no se pisa

Fecha: 2026-11-27

## Contexto

El motor escribe el mapa de la vista con el reparto del plano, y lo reescribe entero cada
vez que el plano cambia: el `PUT` del API reemplaza el dibujo completo. Eso está bien
mientras el dibujo sea del plano, pero el mapa también se ajusta a mano desde la consola
—mover un router que quedó mal, separar dos iconos, arrimar una caja— y cualquier `apply`
posterior borraba ese trabajo sin avisar. Y no hay forma de saber si lo que difiere lo
cambió una persona o es que el plano ha cambiado: son el mismo dato.

## Decisión

**El mapa guarda la huella de lo que el motor escribió, y con eso se distingue lo suyo de
lo de una persona.**

- Al escribir el mapa, el motor deja en el comentario del objeto —donde ya deja la marca de
  propiedad de cada equipo— `netlabs lab=<lab> plano=<huella>`, con la huella del dibujo
  (posiciones, tamaños, textos, cables y ajustes, no el texto del JSON, cuyo orden no
  significa nada).
- En la pasada siguiente se compara: si el mapa que hay **no** es el que el motor escribió
  la última vez, lo ha tocado alguien y **no se toca**. Se dice en voz alta.
- Si la huella cuadra, el mapa sigue siendo del motor y se escribe cuando el plano cambie,
  como siempre.
- Sin huella —un mapa de antes de esta regla, o de un laboratorio que aún no se ha
  desplegado— se escribe: no se puede acusar a nadie de haber tocado lo que nadie tocó.
- Para volver a entregarle el mapa al plano, se borra el mapa (o su comentario) y se lanza
  `apply`: sin huella, el motor lo rehace.

## Consecuencias

- Un ajuste a mano **prevalece** y sobrevive a todos los `apply` siguientes; a cambio, ese
  laboratorio deja de recibir los cambios de reparto del plano hasta que alguien lo
  devuelva. Es el trato que pidió quien lo ajusta: su dibujo manda.
- La huella se calcula sobre lo que se ve, así que reordenar claves o cambiar el número de
  un enlace no cuenta como cambio —el número lo reparte la vista—.
- El comentario del mapa deja de ser sólo la marca de propiedad: también dice qué escribió
  el motor. Sigue sirviendo para lo de antes (`destroy` retira lo que lleva la marca).
