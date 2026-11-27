# 0017 — El mapa enseña el estado por defecto

Fecha: 2026-11-27

## Contexto

El marco de estado y el fondo de estado de un mapa vienen apagados de fábrica, y son justo
lo que hace útil una vista viva: el marco rodea cada equipo con su color —verde, amarillo,
rojo— y el fondo tiñe la caja. Sin ellos, un mapa es un dibujo bonito que no dice si algo
está caído, que es lo único que se le pide.

Encenderlos es cosa del objeto del mapa, no de su dibujo, y el API los llamaba por su
número de bit. Al mirarlo contra el servicio en pie resultó que también los acepta por su
nombre (`showStatusFrame`, `showStatusBackground`), que es como hay que escribirlos.

Y de paso salió un fallo que valía la pena cazar: el API **documenta** el `PUT` para tocar
un objeto, pero el servicio contesta **405** y no escribe nada. Lo que acepta es `PATCH`.
La huella del motor (ADR 0016) iba con `PUT`: cualquier `apply` con el mapa por escribir
habría terminado en rojo, sin escribir el mapa y sin dejar la huella.

## Decisión

- **El mapa del laboratorio nace y se queda con el marco y el fondo de estado encendidos.**
  El motor lee las banderas del objeto, y si alguna de las tres —el icono, el marco y el
  fondo— está apagada, manda un `PATCH` con **todas** las que el mapa tiene y esas tres
  encendidas: el `PATCH` reemplaza el objeto entero, así que devolver las demás es lo que
  evita pisar una que alguien hubiera encendido por su cuenta. Si ya están, no manda nada:
  el `apply` sigue sin tocar lo que ya está.
- **Las banderas se escriben por su nombre**, no por su bit.
- **Para tocar un objeto se usa `PATCH`**, nunca `PUT`: es lo que acepta el servicio, y
  queda dicho aquí porque su propio API dice lo contrario.

## Consecuencias

- Un mapa nuevo se ve con el estado desde el primer `apply`, y uno viejo —de antes de esta
  regla— lo recibe en el siguiente: la comprobación se hace siempre.
- Las banderas no mueven nada: se encienden también en un mapa ajustado a mano, que sigue
  sin ser reescrito (ADR 0016). Lo que se respeta es la disposición, no el marco.
- Si el servicio aceptara el `PUT` en otra versión, seguiría funcionando el `PATCH`.
