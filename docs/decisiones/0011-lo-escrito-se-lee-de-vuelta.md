# 0011 — Un DELETE no lleva cuerpo, y lo que se escribe se lee de vuelta

Fecha: 2026-11-25

## Contexto

Al mover el tránsito entre sedes a Internet, el laboratorio `d_acme_dos_sedes` pasó de un
tramo `/30` a un `/24` y de un cable directo a un proveedor. Converger eso exigía **quitar**
la dirección vieja de `rte1`/`rte2` y las rutas viejas hacia la otra sede —no sólo añadir—.

Cada vez que tocaba borrar, el `apply` se paraba:

```
[ERROR]: Task failed: Module failed: Status code was -1 and not [200, 201, 204]:
Connection failure: timed out
```

y el borrado **no se había hecho**. Cuatro pasadas seguidas muriendo en el mismo sitio.

## La causa, medida

Con la petición delante —levantando un socket que la apunta tal cual llega— se ve qué manda
el módulo `uri` cuando la operación no lleva cuerpo pero se le pide `body_format: json`:

```
DELETE /rest/ip/route/*1 HTTP/1.1
Content-Length: 4
Content-Type: application/json
Connection: close

null
```

Manda el literal **`null`** como cuerpo. RouterOS no contesta a un DELETE con cuerpo: la
conexión se queda colgada hasta el tope del módulo (30 s), el borrado no ocurre y el `apply`
se para con un mensaje que no dice nada del laboratorio. `curl` con el mismo DELETE y sin
cuerpo contesta `204` en 0,12 s; el mismo DELETE desde el módulo, sin `body_format`, tarda
0,95 s. La diferencia es el `null`.

## Decisión

1. El formato del cuerpo se pide **sólo cuando hay cuerpo que mandar**:
   `body_format: "{{ 'json' if ros_op.body is defined else omit }}"`. Un DELETE sale sin
   cuerpo y RouterOS contesta a la primera.
2. Aun así, después de escribir el motor **relee** el interior del router y vuelve a calcular
   la diferencia (`netlabs_ros_ops`). Si queda algo —un borrado que no llegó a ocurrir, una
   escritura perdida— el `apply` se para nombrando las operaciones que faltan.
3. Una escritura que RouterOS no contesta (`status -1`) en un DELETE no se da por fallo en el
   momento, porque el error que importa lo canta la comprobación de después. Los demás fallos
   siguen parando el `apply` como antes.

## Consecuencias

- El caso que costó cuatro pasadas deja de existir: el DELETE se contesta y se aplica.
- Y si algún día vuelve a perderse una escritura, el `ok` del `apply` significa «está», no
  «se envió»: el motor no da por bueno un cambio que no puede leer de vuelta.
- La lectura de vuelta cuesta una ronda de GET por router; es el precio de que el informe no
  mienta.

Ver: `deployment_engine/tasks/ros.yml`,
`deployment_engine/filter_plugins/netlabs.py` (`netlabs_ros_ops`, `netlabs_ros_reads`).