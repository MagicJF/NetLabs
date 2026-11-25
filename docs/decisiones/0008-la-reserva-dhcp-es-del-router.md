# 0008 — La reserva DHCP es del router, no del invitado

Fecha: 2026-11-25

## Contexto

Un nodo final que pide dirección por DHCP no tenía forma de aparecer en la vista: su
dirección no existe hasta que el router se la concede, y esa concesión puede cambiar. La
alternativa de leer la tabla de leases y registrar lo que hubiera en cada momento haría que
NetXMS apuntara a direcciones que ya no son del equipo, y el mapa mentiría. La otra
alternativa —convertir el puesto en estático— resuelve la vista pero elimina el ejercicio de
DHCP del laboratorio.

## Decisión

1. Un nodo final puede declarar `reserve: <ip>` junto a `address: dhcp`. Sigue siendo un
   cliente DHCP; lo que cambia es que el servidor siempre le da esa dirección.
2. El motor deriva la MAC del vmid, localiza el router que sirve esa red y crea en su
   servidor DHCP una concesión fija con esa MAC y esa dirección. La reserva vive en el
   `configure.dhcp_server` del router, no en el invitado.
3. La dirección reservada es la `netxms_address` del nodo final: se registra en la vista y
   el mapa lo dibuja como cualquier otro nodo, sin credenciales de RouterOS.
4. Si se retira la declaración, el motor retira la concesión. Si la dirección no coincide
   con la reserva, el `apply` reinicia el puesto una vez para que vuelva a pedirla y falla
   si aun así no la obtiene.
5. El motor no lee leases dinámicos para adivinar direcciones: una concesión dinámica no es
   una identidad estable.

## Consecuencias

- Los puestos DHCP aparecen en NetXMS y en el mapa conservando su cliente DHCP.
- La reserva es reproducible: nace de la definición del laboratorio, no de una intervención
  manual en el router.
- Cambiar la dirección de un puesto es cambiar su `reserve`; el motor actualiza la concesión
  y, si hace falta, reinicia el invitado para que la tome.
- Un nodo DHCP sin reserva sigue fuera de la vista: no hay dirección estable que registrar.

Ver: `docs/diseno.md` §3.4, `deployment_engine/tools/identity.py`,
`deployment_engine/tools/converge.py`, `deployment_engine/tasks/check_lease.yml`,
`deployment_engine/tests/test_identity.py`, `deployment_engine/tests/test_converge.py`.