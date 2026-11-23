# 0003 — El motor registra los equipos de red en el servicio que observa el sitio

**Fecha:** 22 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `deployment_engine/tasks/netxms.yml`, `converge.netxms_*`, `identity.plan`, y
`netlabs.yml` → `management.api`. Es la **quinta vía** del motor (AGENTS.md §2, `docs/diseno.md` §2.8).

## El problema

La consola web de NetXMS puede abrir una **shell a un equipo desde el navegador** (§3.4), y es útil
justo para los equipos de red, que se alcanzan por su dirección de gestión. Para abrirla necesita las
**credenciales del equipo** (usuario, clave y puerto SSH) guardadas en sus propiedades. Hoy NetXMS
descubre los equipos por SNMP —y les pone su nombre— pero **no tiene sus credenciales**, así que la
terminal no funciona sin teclearlas a mano en cada sesión.

El motor ya conoce esas credenciales: es él quien crea el usuario del router y le pone la clave. Lo
que falta es que las **registre en la vista**, y eso no lo hace ninguna de las cuatro vías actuales.

## Lo que se midió contra el NetXMS 7.0.4 (la última publicada)

- El módulo `webapi` del servidor **no estaba cargado**: el puerto 8000 contestaba 404 a todo. Cargado
  (`Module = webapi` en `/etc/netxmsd.conf`), el API vive en `/v1/...` escuchando **sólo dentro** del
  invitado.
- `POST /v1/login` devuelve un testigo; `POST /v1/objects/search` busca por clase e IP;
  `POST /v1/objects/details` da la ficha de hasta 500 objetos de una vez, y la ficha **sí trae**
  `sshLogin` / `sshPassword` / `sshPort`.
- **`PATCH /v1/objects/{id}` ignora `sshLogin` / `sshPassword`**: responde 200 y la base no cambia
  (no hay sub-recurso `/ssh` hasta la rama `master`). Tampoco con `{"ssh": {...}}`.
- **Al crear sí los acepta**: `POST /v1/objects {class: Node, name, ipAddress, sshLogin, sshPassword,
  sshPort}` → 201 y la fila queda con login y clave (probado con un nodo de prueba, ya borrado).
- El agente necesita el **subagente SSH** (`SubAgent=ssh`) para abrir la sesión hacia el equipo: sin
  él la consola contesta «Unknown command» al abrir la terminal. Va en un drop-in
  (`/etc/nxagentd.conf.d/`), que el agente sí lee —medido—.

## Las dos opciones (y la descartada)

- **Rehacer los nodos ya descubiertos.** Como el API sólo acepta las credenciales al **crear**, la
  única vía por API sería **borrar** el nodo y volver a crearlo con ellas. Coste: se pierde lo
  recolectado del nodo (interfaces, histórico), que se repuebla solo en el siguiente sondeo.
- **Sólo aprovisionar.** El motor **crea con credenciales los que faltan** y a los ya descubiertos
  con otras credenciales los **reporta como pendientes** para que los cambie una persona en la
  consola. Coste: los equipos que ya existían antes de esta vía quedan a mano una vez.
- **Descartada: escribir la base del invitado con el servidor parado** (como hace `nxdbmgr`). No
  pierde nada y no borra nada, pero **no es el API**: el motor escribiría por dentro un fichero de
  otro, que es justo lo que `AGENTS.md` §3.1 prohíbe.

## La decisión

**Sólo aprovisionar**, y por eso es una **diferencia** como las demás: el motor da de alta lo que
falta y **dice en voz alta** lo que no se puede corregir por el API, en vez de fingir que lo arregló.
Un equipo ya registrado con las credenciales puestas no produce ninguna llamada, así que el segundo
`apply` no escribe (§2.7).

Se abre una **quinta vía** (`tasks/netxms.yml`), porque el motor habla con un servicio que hasta
ahora no hablaba, y `AGENTS.md` §2 exige plantear una vía nueva antes de abrirla. La vía escribe por
`curl` **desde dentro** del invitado de gestión —donde escucha el API y donde aterriza el túnel del
motor—, por la puerta de siempre (`interior_ssh.yml`); ni la clave ni el testigo de la sesión viajan
en la línea de órdenes, donde los vería `ps` dentro del invitado.

## El servicio es del sitio, no de un laboratorio

El motor nombra a NetXMS —la vía se llama `tasks/netxms.yml`—, pero **eso no rompe la pureza**: el
servicio está declarado en `netlabs.yml` (`management`) y su credencial en `secrets.yml`, es decir,
es vocabulario del **sitio**. Que el laboratorio de control lo adopte como su nodo no lo convierte en
palabra de ese laboratorio; la comprobación de pureza lo excluye por eso. Si mañana el servicio
cambiara de nombre, cambian `netlabs.yml` y `secrets.yml`, no el motor.

## Consecuencia que hay que recordar

Un equipo que ya estaba en la vista con otras credenciales **no se arregla solo**: sale en la lista de
`pendientes` de cada `apply` hasta que alguien lo cambie a mano en la consola de NetXMS. Es a
propósito —borrarlo para rehacerlo perdería lo recolectado— y está dicho en el propio informe.
