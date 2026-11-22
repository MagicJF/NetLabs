# Laboratorio `c_enrutar_y_conmutar`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## c_enrutar_y_conmutar
Address spaces: `10.46.0.0/16`

### Topología

```mermaid
flowchart TB
    classDef red0 fill:#3b82f6,fill-opacity:0.15,stroke:#3b82f6,stroke-width:2px,color:#0f172a
    subgraph red0["lan · 10.46.1.x/24"]
        direction TB
        n_rte1(("📡 rte1<br/>10.46.1.1/24"))
        n_swc1["🔀 swc1"]
        n_swa1["🔀 swa1"]
        n_wsp1["🖥️ wsp1<br/>dhcp"]
        n_wsp2["🖥️ wsp2<br/>dhcp"]
    end
    class red0 red0
    n_rte1 --> n_swc1
    n_swc1 --> n_swa1
    n_swa1 --> n_wsp1
    n_swa1 --> n_wsp2
```

### Cableado (L2)

```mermaid
flowchart TB
    n_rte1["📡 rte1<br/>p1"]
    n_swc1["🔀 swc1<br/>p1, p2"]
    n_swa1["🔀 swa1<br/>p1, p2, p3"]
    n_wsp1["🖥️ wsp1<br/>p1"]
    n_wsp2["🖥️ wsp2<br/>p1"]
    n_rte1 -->|rte1p1 ↔ swc1p1| n_swc1
    n_swc1 -->|swc1p2 ↔ swa1p1| n_swa1
    n_swa1 -->|swa1p2 ↔ wsp1p1| n_wsp1
    n_swa1 -->|swa1p3 ↔ wsp2p1| n_wsp2
```

### Networks

| network | address |
| --- | --- |
| `lan` | `10.46.1.0/24` |

### Nodes

| role | type | stage | interfaces | address | resources |
| --- | --- | --- | --- | --- | --- |
| `rte1` | router | 1 | `lan` | management (derived) | cores=2, disk=1, memory=512 |
| `swa1` | switch | 2 | `lan`, `lan`, `lan` | management (derived) | cores=2, disk=1, memory=512 |
| `swc1` | switch | 2 | `lan`, `lan` | management (derived) | cores=2, disk=1, memory=512 |
| `wsp1` | workstation | 3 | `lan` | from router (DHCP) | cores=1, disk=2, memory=256 |
| `wsp2` | workstation | 3 | `lan` | from router (DHCP) | cores=1, disk=2, memory=256 |

### Cables

| bridge | a | z | network |
| --- | --- | --- | --- |
| `c_rte1p1_swc1p1` | `rte1p1` | `swc1p1` | `10.46.1.0/24` |
| `c_swc1p2_swa1p1` | `swc1p2` | `swa1p1` | `10.46.1.0/24` |
| `c_swa1p2_wsp1p1` | `swa1p2` | `wsp1p1` | `10.46.1.0/24` |
| `c_swa1p3_wsp2p1` | `swa1p3` | `wsp2p1` | `10.46.1.0/24` |

Configured areas: `addresses`, `dhcp_server`, `services`, `snmp`, `users`.

<!-- netlabs:end -->
