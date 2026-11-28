# 0018 — La salida de cada sede la pone el entorno, y por ella no se vuelve a casa

**Fecha:** 28 de noviembre de 2026
**Estado:** aceptada
**Ámbito:** `netlabs.yml` → `salida`; las redes con `exit: true` de un laboratorio; el bloque de `vmbr0` del nodo Proxmox.

## El problema

Un laboratorio tiene que poder salir de verdad —resolver un nombre, abrir una página— y no sólo
simular que sale con una nube dibujada. Para eso hace falta una pata del router en una red que el
nodo Proxmox traduzca hacia su enlace público.

El nodo ya traduce un espacio para su red de gestión (`10.30.0.0/16`, ADR 0001), y la tentación es
reutilizarlo. No vale: ese espacio es donde el motor entra a los invitados por SSH, y meter los
laboratorios dentro es mezclar el tráfico de los alumnos con el de la casa y romper el plan de
direcciones de la gestión, que el motor reparte por *vmid*.

La nube del proveedor del laboratorio `f_acme_cuatro_departamentos` tampoco es la salida: por ella
va el tránsito **entre sedes**, que no tiene cable directo. Son dos cosas distintas, y el usuario
pidió verlas separadas:

> «rte1 y rte2 cada uno con su salida»

## La decisión

Un espacio de salida propio, declarado una vez en `netlabs.yml` y ajeno a todo lo demás:

```yaml
salida:
  address_space: 172.30.0.0/16
```

Un laboratorio que quiera salir marca la red por la que se asoma con `exit: true` y la dibuja como
nube (es su frontera, no una red de dentro). Cada sede tiene la suya: `ny_salida` y `tk_salida` para
Nueva York y Tokio, un tramo cada una.

Y el motor la trata como lo que es —**una frontera, no un cable**—:

- **No lleva cable.** Tiene una sola punta, así que no une dos puertos y `links` no la ve. Ocupa su
  puerto igual que cualquier otra pata, pero su puente no sale del par de puntas: sale del
  laboratorio y de la red (`<letra>_<red>`), para que dos laboratorios con la misma red no compartan
  la salida.
- **Su puente lo pone el entorno, y lleva dirección.** El motor crea el puente por la API con la
  **primera dirección de su tramo** (`172.30.10.1`), que es la puerta que ve el router desde su pata
  —comprobado contra la API: `POST /nodes/<nodo>/network` acepta `address` y `netmask` en un puente—.
  Si el tramo de una salida cambia, el puente no se rehace: se reapunta (`bridge_set`) y se reaplica.
- **No cuenta en el plan de direcciones del laboratorio.** Cae dentro del espacio del entorno, que es
  justo lo que se le pide. `./netlabs check` lo sabe y no lo cuenta como red del laboratorio.
- **El router sale por ahí.** Declara su pata en la salida, su ruta por defecto hacia esa puerta y su
  traducción (`nat: [{out: <salida>}]`, sólo `masquerade`) y su resolutor (`dns`), que atiende a los
  suyos para que los puestos que lo tienen de servidor resuelvan también.

## Lo que hay que hacer una vez en el nodo

La API da dirección al puente, pero el NAT y el cortafuegos viven en el nodo. Va en el bloque de
`vmbr0`, con la misma forma idempotente (`-C ... || -A ...`) que el resto del fichero:

- **Traducir** el espacio de salida por el enlace público (`MASQUERADE`).
- **No dejarlo volver**: desde `172.30.0.0/16` no se llega a la red de gestión, ni a las LAN del
  nodo, ni al propio hipervisor, ni a otro laboratorio. Al gateway de su propio tramo sólo se le
  puede hacer ping.

Se comprobó de extremo a extremo con un espacio de nombres de red de usar y tirar: desde la salida
se llega a internet y no se llega ni a `10.30.0.1` ni a `10.10.10.1`.

## Alternativa descartada

**Salir todos por la nube del proveedor.** Es lo que había: una sola nube y el tránsito entre sedes
por ella. Se descartó porque deja la salida a internet y el tránsito en la misma pieza, y porque el
usuario pidió explícitamente una salida por sede. El tránsito sigue siendo del proveedor; la salida
es de cada router.

## Lo que cuesta

Una configuración del nodo que no vive en el repositorio —igual que el NAT de `vmbr30`— y que se
paga con este ADR. El motor, por su parte, no sabe nada del nodo: crea el puente que el laboratorio
declara y lo retira con él.
