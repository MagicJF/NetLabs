# Laboratorio `uno`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## uno

Slot: `0`
Address spaces: `10.44.0.0/16`

### Networks

| network | address |
| --- | --- |
| `lan1` | `10.44.1.0/24` |
| `lan2` | `10.44.2.0/24` |

### Nodes

| role | type | stage | interfaces | address | resources |
| --- | --- | --- | --- | --- | --- |
| `edge` | router | 1 | `lan1`, `lan2` | management (derived) | cores=1, disk=1, memory=256 |
| `pc-1` | workstation | 2 | `lan1` | from router (DHCP) | cores=1, disk=2, memory=256 |
| `pc-2` | workstation | 2 | `lan2` | from router (DHCP) | cores=1, disk=2, memory=256 |

### Cables

| bridge | a | z | network |
| --- | --- | --- | --- |
| `rt01p01_ws01p01` | `rt01p01` | `ws01p01` | `10.44.1.0/24` |
| `rt01p02_ws02p01` | `rt01p02` | `ws02p01` | `10.44.2.0/24` |

Configured areas: `addresses`, `dhcp_server`, `identity`, `services`, `users`.

<!-- netlabs:end -->


