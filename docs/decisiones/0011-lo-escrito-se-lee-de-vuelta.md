# 0011 — Lo que se escribe se lee de vuelta antes de darlo por bueno

Fecha: 2026-11-25

## Contexto

Al mover el tránsito entre sedes a Internet, el laboratorio `d_acme_dos_sedes` pasó de un
tramo `/30` a un `/24` y de un cable directo a un proveedor. Converger eso exigía **quitar**
la dirección vieja de `rte1`/`rte2` y la ruta vieja hacia la otra sede —no sólo añadir—.

RouterOS aplicaba el borrado, pero su respuesta no volvía: la petición DELETE se quedaba
esperando hasta el tope del módulo `uri` (30 s) y el `apply` se paraba con un «Connection
failure: timed out» que no decía nada del laboratorio. Releído a mano, el borrado **sí
estaba hecho**: lo que se perdía era la contestación, no el cambio.

## Decisión

1. Una escritura que RoutersOS no contesta —`status -1`— en un **DELETE** no se da por
   fallo en el momento: el borrado ocurre igual, y el error que importa lo canta la
   comprobación de después. Los demás fallos siguen parando el `apply` como antes.
2. Después de escribir, el motor **relee** el interior del router y vuelve a calcular la
   diferencia (`netlabs_ros_ops`). Si queda algo —un borrado que no llegó a ocurrir, una
   escritura perdida— el `apply` se para nombrando las operaciones que faltan.
3. La comprobación existente de direcciones se mantiene; la nueva la engloba: cubre
   direcciones, rutas, usuarios, servicios, SNMP y puentes.

## Consecuencias

- Un cambio que no puede leerse de vuelta no se declara hecho: el `ok` del `apply` significa
  «está», no «se envió».
- El caso raro de RouterOS —aplicar el borrado y no contestar— deja de romper la pasada.
- La lectura de vuelta cuesta una ronda de GET por router; es el precio de que el informe no
  mienta.

Ver: `deployment_engine/tasks/ros.yml`,
`deployment_engine/filter_plugins/netlabs.py` (`netlabs_ros_ops`, `netlabs_ros_reads`).