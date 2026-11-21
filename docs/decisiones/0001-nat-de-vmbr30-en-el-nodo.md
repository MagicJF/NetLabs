# 0001 — La salida de la OOB se configura en el nodo, no por la API

**Fecha:** 21 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `netlabs.yml` → `management`, y el puente `vmbr30` del nodo Proxmox.

## El problema

El invitado persistente de gestión (`netxms`) vive en la red de gestión `vmbr30` (`10.30.0.0/16`).
Su túnel es **inverso**: el invitado llama hacia fuera, al `443` del nodo de control, y desde allí
se abre el camino `127.0.0.1:2210` que usa Ansible. Para eso necesita **salida a internet**.

`vmbr30` no tenía dirección ni NAT. La API de Proxmox puede crear un puente (`POST /nodes/<nodo>/network`),
pero **no puede darle dirección, gateway ni reglas de NAT**: eso vive en
`/etc/network/interfaces`, que no se escribe por la API. Con el puente a `manual`, el invitado no
sale y el túnel no levanta.

## Las dos opciones

- **A. Dos patas en el invitado.** `eth0` en `vmbr1` (que ya tiene `10.10.10.1/24` y `MASQUERADE`
  puestas a mano de antes) para la salida, `eth1` en `vmbr30` para la OOB. Todo por API, sin tocar
  el nodo. Coste: `derive_management` pasa a dos espacios de direcciones, con sus pruebas; y el
  plano de gestión comparte capa 2 con invitados ajenos (`hermesagent`, `caddy`, `netbox`).
- **B. Dar dirección y NAT a `vmbr30` en el nodo, una vez.** Una sola tarjeta, cero cambios en el
  motor, `netlabs.yml` intacto. Coste: una configuración que no vive en el repositorio y que el
  motor no puede reproducir; si el nodo se reconstruye, no vuelve sola.

## La decisión

**B.** El puente de gestión conserva su `/16` limpio y su forma de un solo plano, que es lo que
`docs/diseno.md` §3.4 describe. Se acepta que esta pieza queda fuera del repositorio y se paga con
este ADR en vez de con una invención del motor.

## Qué se hizo en el nodo (y por qué no por la API)

En `/etc/network/interfaces`, sobre `vmbr30`:

```
auto vmbr30
iface vmbr30 inet static
    address 10.30.0.1/16
    bridge_ports none
    bridge_stp off
    bridge_fd 0
    post-up echo 1 > /proc/sys/net/ipv4/ip_forward
    post-up iptables -t nat -C POSTROUTING -s 10.30.0.0/16 -o vmbr0 -j MASQUERADE 2>/dev/null || \
            iptables -t nat -A POSTROUTING -s 10.30.0.0/16 -o vmbr0 -j MASQUERADE
    post-down iptables -t nat -D POSTROUTING -s 10.30.0.0/16 -o vmbr0 -j MASQUERADE || true
```

El `-C || -A` es deliberado: un `ifup` repetido no debe duplicar la regla. Es la misma trampa que
ya se pagó en `vmbr1` y cuyo comentario en el nodo la recuerda.

Antes de esto, la dirección y la regla estaban puestas **en caliente** y se perdían al reiniciar.
Ahora están en el fichero y sobreviven.

## Alternativa descartada

**A** era la opción sin deuda invisible. Se descartó porque el usuario prefirió no tocar el motor
y mantener el plano de gestión en un solo puente. Queda anotada aquí por si el nodo se reconstruye:
entonces habrá que repetir esta configuración o, mejor, reconsiderar A.

## Consecuencia que hay que recordar

`./netlabs check` **no puede comprobar** esta pieza: no hay forma de leer `/etc/network/interfaces`
por la API. Si el túnel no levanta, la primera pregunta es si `vmbr30` sigue teniendo dirección y
NAT en el nodo. El motor lo detecta —`apply` para y dice que el camino no responde— pero no puede
arreglarlo.
