# Laboratorio `c_enrutar_y_conmutar`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## c_enrutar_y_conmutar
Address spaces: `10.46.0.0/16`

### Topología

```mermaid
architecture-beta
    service red_lan(cloud)[lan 10.46.1.0/24]
    service n_rte1(server)[rte1 router 10.46.1.1/24]
    service n_swc1(server)[swc1 switch]
    service n_swa1(server)[swa1 switch]
    service n_wsp1(server)[wsp1 workstation dhcp]
    service n_wsp2(server)[wsp2 workstation dhcp]
    n_rte1:R -- L:red_lan
    n_swc1:R -- L:red_lan
    n_swa1:R -- L:red_lan
    n_wsp1:R -- L:red_lan
    n_wsp2:R -- L:red_lan
```

### Cableado (L2)

```mermaid
architecture-beta
    service n_rte1(server)[rte1 (p1)]
    service n_swc1(server)[swc1 (p1, p2)]
    service n_swa1(server)[swa1 (p1, p2, p3)]
    service n_wsp1(server)[wsp1 (p1)]
    service n_wsp2(server)[wsp2 (p1)]
    n_rte1:R -- L:n_swc1
    n_swc1:R -- L:n_swa1
    n_swa1:R -- L:n_wsp1
    n_swa1:R -- L:n_wsp2
```

### Networks

| network | address |
| --- | --- |
| `lan` | `10.46.1.0/24` |

### Nodes

| role | type | stage | interfaces | address | resources |
| --- | --- | --- | --- | --- | --- |
| `rte1` | router | 1 | `lan` | management (derived) | cores=1, disk=1, memory=256 |
| `swa1` | switch | 2 | `lan`, `lan`, `lan` | management (derived) | cores=1, disk=1, memory=256 |
| `swc1` | switch | 2 | `lan`, `lan` | management (derived) | cores=1, disk=1, memory=256 |
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
