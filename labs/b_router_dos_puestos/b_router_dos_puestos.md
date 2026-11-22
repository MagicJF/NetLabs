# Laboratorio `b_router_dos_puestos`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## b_router_dos_puestos
Address spaces: `10.44.0.0/16`

### Topología

```mermaid
---
title: b_router_dos_puestos · 10.44.x.x/16
---
flowchart LR
    classDef red fill:#3b82f6,fill-opacity:0.12,stroke:#3b82f6,stroke-width:1px,color:#0f172a
    classDef equipo fill:#ffffff,stroke:#3b82f6,stroke-width:1px,color:#0f172a
    classDef puerta fill:#ffffff,stroke:#3b82f6,stroke-width:2px,color:#0f172a
    classDef internet fill:#f8fafc,stroke:#64748b,stroke-width:1px,color:#0f172a
    internet(["Internet"])
    class internet internet
    n_rte1(("rte1<br/>10.44.1.1/24<br/>10.44.2.1/24"))
    class n_rte1 puerta
    subgraph red0["lan1 · 10.44.1.x/24"]
        direction TB
        n_wsp1["wsp1<br/>dhcp"]
        class n_wsp1 equipo
    end
    class red0 red
    subgraph red1["lan2 · 10.44.2.x/24"]
        direction TB
        n_wsp2["wsp2<br/>dhcp"]
        class n_wsp2 equipo
    end
    class red1 red
    internet --- n_rte1
    red0 --- n_rte1
    n_rte1 --- red1
```

*clase por forma — círculo: router; rectángulo: workstation. Las áreas son las redes y un equipo con pata en varias va en su frontera; aristas sin flecha: sólo la jerarquía declarada.*

### Cableado (L2)

```mermaid
flowchart TB
    classDef equipo fill:#ffffff,stroke:#1d4ed8,stroke-width:1px,color:#0f172a
    classDef puerta fill:#ffffff,stroke:#1d4ed8,stroke-width:2px,color:#0f172a
    n_rte1(("rte1<br/>p1, p2"))
    class n_rte1 puerta
    n_wsp1["wsp1<br/>p1"]
    class n_wsp1 equipo
    n_wsp2["wsp2<br/>p1"]
    class n_wsp2 equipo
    n_rte1 ---|rte1p1 ↔ wsp1p1| n_wsp1
    n_rte1 ---|rte1p2 ↔ wsp2p1| n_wsp2
```

*cada arista dice las dos puntas que une.*

### Networks

| network | address |
| --- | --- |
| `lan1` | `10.44.1.0/24` |
| `lan2` | `10.44.2.0/24` |

### Nodes

| role | type | stage | interfaces | address | resources |
| --- | --- | --- | --- | --- | --- |
| `rte1` | router | 1 | `lan1`, `lan2` | management (derived) | cores=2, disk=1, memory=512 |
| `wsp1` | workstation | 2 | `lan1` | from router (DHCP) | cores=1, disk=2, memory=256 |
| `wsp2` | workstation | 2 | `lan2` | from router (DHCP) | cores=1, disk=2, memory=256 |

### Cables

| bridge | a | z | network |
| --- | --- | --- | --- |
| `b_rte1p1_wsp1p1` | `rte1p1` | `wsp1p1` | `10.44.1.0/24` |
| `b_rte1p2_wsp2p1` | `rte1p2` | `wsp2p1` | `10.44.2.0/24` |

Configured areas: `addresses`, `dhcp_server`, `services`, `snmp`, `users`.

<!-- netlabs:end -->
