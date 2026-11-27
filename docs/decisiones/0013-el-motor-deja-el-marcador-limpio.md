# 0013 — El motor deja el marcador limpio al converger

Fecha: 2026-11-26

## Contexto

El mapa a medida enseña el **estado** de cada equipo con el color que le pone la vista, y ese
color sale de las alarmas vivas. La vista no las resuelve sola cuando el mal ya no está: una
alarma que saltó **una vez** —la MAC de un invitado que cambió al volver a crearlo, esa misma
MAC que dos nodos compartieron mientras la vista los recolocaba— se queda viva para siempre, y
con ella el equipo en amarillo. Medido: los ocho nodos finales del laboratorio `d` llevaban
desde las 20:43 del 25 en aviso o grave por eso, y sus MAC ya eran las correctas; los tres
routers del tránsito, por una máscara `/30` que la vista recuerda de antes de que las patas
fueran `/26`. Ocho de cada once avisos del laboratorio eran eso: el dibujo enseñaba un mal que
ya no estaba.

El motor ya se ocupa de que el mapa **no mienta** en el dibujo (0004, 0005, 0007, 0012). Dejar
que mienta en el color es lo mismo, sin arreglar.

## Decisión

Al final del `apply` —**después** del registro y del mapa, que son quienes dan de alta y
dibujan— el motor lee el registro de alarmas de la vista y **da por resueltas** las de los
equipos de este laboratorio: sólo las **vivas** (`state` 0) y de **aviso para arriba**
(severidad ≥ 1). Lo hace por el API, con `POST /alarms/<id>/resolve` —lo que la vista acepta:
`DELETE` contesta 405—, desde dentro del invitado de gestión, como todo lo demás.

Tres cosas no se hacen:

- **No se toca una alarma ajena.** Cada alarma trae su `source` —el número del equipo que la
  levantó—, y sólo se mira si ese número es de los equipos que este laboratorio registró
  (los que guarda `netxms_ids`). Otro laboratorio con los mismos nombres no se ve afectado.
- **No se resuelve el ruido.** Severidad 0 es lo que la vista apunta sola —un paquete
  instalado—: no es un mal y no se le da por resuelto.
- **No se arregla ninguna causa.** El motor no comprueba si el mal sigue: da por resueltas las
  alarmas al converger, y si el mal sigue ahí **la vista vuelve a levantar la suya en su
  siguiente vuelta**. Resolver no es esconder, es dejar de repetir lo que ya pasó.

## Consecuencias

- El mapa dice la verdad al terminar un `apply`, que es cuando se lo mira. Un `apply` sin nada
  que resolver no cambia nada: la limpieza se salta entera y el informe sigue dando `changed=0`.
- La limpieza no puede tapar un problema real más de una vuelta de la vista, y no lo tapa a
  escondidas: el informe dice cuántas alarmas se dieron por resueltas y de qué.
- Sigue habiendo una alarma que el motor **no** puede quitar: la de la máscara, que sale de la
  **topología IP** de la vista (una subred `/30` que aprendió cuando las patas lo eran). El API
  no expone esa topología —`/subnets`, `/ip-addresses`, `/objects/<id>/interfaces` contestan
  404—, así que esa subred vieja sólo se retira desde su consola. Volverá a salir hasta que se
  retire. **No se toca el YML por esto**: el `/26` es el bueno —los tres routers del tránsito
  viven en el mismo `203.0.113.0/24`—.

Ver: `deployment_engine/tasks/netxms_marcador.yml`,
`deployment_engine/tools/converge.py` (`netxms_alarmas_propias`, `netxms_alarma_resolver_cmd`),
`docs/diseno.md` §3.4, `docs/decisiones/0012-los-equipos-del-mapa-son-iconos.md`.
