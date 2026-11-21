# Laboratorio `dos`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## dos
Slot: 1
Address spaces: `10.46.0.0/16`

### Topología

```mermaid
architecture-beta
    service red_lan(cloud)[lan 10.46.1.0/24]
    service n_borde(server)[borde router 10.46.1.1/24]
    service n_nucleo(server)[nucleo switch]
    service n_acceso(server)[acceso switch]
    service n_pc_1(server)[pc-1 workstation dhcp]
    service n_pc_2(server)[pc-2 workstation dhcp]
    n_borde:R -- L:red_lan
    n_nucleo:R -- L:red_lan
    n_acceso:R -- L:red_lan
    n_pc_1:R -- L:red_lan
    n_pc_2:R -- L:red_lan
```

### Cableado (L2)

```mermaid
architecture-beta
    service n_borde(server)[borde (p1)]
    service n_nucleo(server)[nucleo (p1, p2)]
    service n_acceso(server)[acceso (p1, p2, p3)]
    service n_pc_1(server)[pc-1 (p1)]
    service n_pc_2(server)[pc-2 (p1)]
    n_borde:R -- L:n_nucleo
    n_nucleo:R -- L:n_acceso
    n_acceso:R -- L:n_pc_1
    n_acceso:R -- L:n_pc_2
```

### Networks

| network | address |
| --- | --- |
| `lan` | `10.46.1.0/24` |

### Nodes

| role | type | stage | interfaces | address | resources |
| --- | --- | --- | --- | --- | --- |
| `borde` | router | 1 | `lan` | management (derived) | cores=1, disk=1, memory=256 |
| `acceso` | switch | 2 | `lan`, `lan`, `lan` | management (derived) | cores=1, disk=1, memory=256 |
| `nucleo` | switch | 2 | `lan`, `lan` | management (derived) | cores=1, disk=1, memory=256 |
| `pc-1` | workstation | 3 | `lan` | from router (DHCP) | cores=1, disk=2, memory=256 |
| `pc-2` | workstation | 3 | `lan` | from router (DHCP) | cores=1, disk=2, memory=256 |

### Cables

| bridge | a | z | network |
| --- | --- | --- | --- |
| `rt11p01_sw11p01` | `rt11p01` | `sw11p01` | `10.46.1.0/24` |
| `sw11p02_sw12p01` | `sw11p02` | `sw12p01` | `10.46.1.0/24` |
| `sw12p02_ws11p01` | `sw12p02` | `ws11p01` | `10.46.1.0/24` |
| `sw12p03_ws12p01` | `sw12p03` | `ws12p01` | `10.46.1.0/24` |

Configured areas: `addresses`, `dhcp_server`, `identity`, `services`, `snmp`, `users`.

<!-- netlabs:end -->
