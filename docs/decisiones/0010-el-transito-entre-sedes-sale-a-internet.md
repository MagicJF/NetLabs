# 0010 — El tránsito entre sedes sale a Internet, no cruza un cable directo

Fecha: 2026-11-25

## Contexto

En `d_acme_dos_sedes`, las dos sedes compartían un tramo público (`203.0.113.0/30`) con un
cable directo entre `rte1` y `rte2`. Cada router tenía una ruta estática hacia la red de la
otra sede apuntando a la dirección del vecino, así que el tráfico entre sedes atravesaba ese
cable en un solo salto. El dibujo decía «Internet», pero el tránsito no pasaba por ningún
proveedor: era un enlace punto a punto entre los dos routers de borde.

Un `traceroute` desde un puesto de Tokio a la puerta de Ventas de Nueva York enseñaba
`rte2 → rte1` sin más, sin ninguna salida al exterior de por medio.

## Decisión

1. La nube de Internet deja de ser un cable entre los dos routers de borde. Pasa a ser la
   red del proveedor: un tramo público (`203.0.113.0/24`) con un router de proveedor,
   `rtp1`, y un conmutador de tránsito, `swc3`.
2. Cada router de borde tiene **una sola pata** en la nube y su **ruta por defecto** apunta
   al proveedor, no al otro router. No queda ninguna ruta directa entre `rte1` y `rte2`:
   lo que no sea de su sede sale a Internet.
3. El proveedor sabe volver a cada sede por su router de borde (`10.20.0.0/16` por
   `203.0.113.2`, `10.40.0.0/16` por `203.0.113.3`) y nada más. El tránsito entre sedes lo
   enruta él, en un salto visible en el `traceroute`.
4. El vocabulario de nombres de router admite una función `p` —proveedor—: un router que no
   es borde, núcleo ni acceso de la empresa, sino la puerta del exterior. El nombre sigue
   contando lo que el equipo es (`rtp1`), como todos.
5. La nube puede llevar equipos dentro. Antes el plano la dibujaba vacía y cada router se
   asomaba con una pata; ahora, si la nube tiene equipos, sus cables se dibujan como los de
   cualquier área y la nube se mide con aire suficiente para su rótulo y sus símbolos.

## Consecuencias

- El `traceroute` entre sedes enseña el salto del proveedor: el tráfico sale de la sede por
  su router de borde, pasa por Internet y entra en la otra sede por el suyo.
- Cada sede tiene su propia salida al exterior, como pedía el enunciado: no hay un cable
  entre los dos routers de borde, ni rutas estáticas que los salten.
- El proveedor es un equipo del laboratorio: vive también en Proxmox, en NetXMS y en el
  plano, y su mapa se genera como el de cualquier otro.
- Un laboratorio que quiera un tránsito directo entre sedes ya no lo tiene por defecto;
  tendría que declarar ese cable y su ruta, que es una decisión explícita, no un accidente.

Ver: `labs/d_acme_dos_sedes/d_acme_dos_sedes.yml`,
`deployment_engine/tools/identity.py` (vocabulario de funciones de router),
`deployment_engine/tools/plano.py` (nube con equipos),
`deployment_engine/tests/test_plano.py`, `deployment_engine/tests/test_mapa.py`.