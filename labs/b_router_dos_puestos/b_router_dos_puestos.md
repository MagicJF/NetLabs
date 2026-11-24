# Laboratorio `b_router_dos_puestos`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## b_router_dos_puestos
Address spaces: `10.44.0.0/16`

### Topología

<svg xmlns="http://www.w3.org/2000/svg" width="536" height="350" viewBox="0 0 536 350" role="img" aria-label="Plano de b_router_dos_puestos">
<rect width="536" height="350" fill="#ffffff"/>
<text x="268.0" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">b_router_dos_puestos</text>
<text x="268.0" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.44.0.0 - 10.44.255.255 (/16)</text>
<g transform="translate(24.0,76.0)">
<rect x="0.0" y="0.0" width="488.0" height="250.0" rx="14" fill="#3b82f6" fill-opacity="0.03" stroke="#93b4f5" stroke-width="1.4" stroke-dasharray="7 5"/><g data-area="10.44.0.0 - 10.44.255.255 (/16)" data-x="0.0" data-y="0.0" data-ancho="488.0" data-alto="250.0" data-subred="10.44.0.0 - 10.44.255.255 (/16)" data-nube="0" data-hijas="2"/><text x="16.0" y="21.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8" paint-order="stroke" stroke="#ffffff" stroke-width="3.2">10.44.0.0 - 10.44.255.255 (/16)</text><text x="16.0" y="36.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569" paint-order="stroke" stroke="#ffffff" stroke-width="3">10.44.0.0 - 10.44.255.255 (/16)</text>
<rect x="20.0" y="53.0" width="170.0" height="177.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><g data-area="lan1" data-x="20.0" data-y="53.0" data-ancho="170.0" data-alto="177.0" data-subred="10.44.1.0 - 10.44.1.255 (/24)" data-nube="0" data-hijas="0"/><text x="36.0" y="74.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8" paint-order="stroke" stroke="#ffffff" stroke-width="3.2">lan1</text><text x="36.0" y="89.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569" paint-order="stroke" stroke="#ffffff" stroke-width="3">10.44.1.0 - 10.44.1.255 (/24)</text><text x="36.0" y="104.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8" paint-order="stroke" stroke="#ffffff" stroke-width="3">dhcp 10.44.1.100-199</text>
<rect x="298.0" y="53.0" width="170.0" height="177.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><g data-area="lan2" data-x="298.0" data-y="53.0" data-ancho="170.0" data-alto="177.0" data-subred="10.44.2.0 - 10.44.2.255 (/24)" data-nube="0" data-hijas="0"/><text x="314.0" y="74.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8" paint-order="stroke" stroke="#ffffff" stroke-width="3.2">lan2</text><text x="314.0" y="89.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569" paint-order="stroke" stroke="#ffffff" stroke-width="3">10.44.2.0 - 10.44.2.255 (/24)</text><text x="314.0" y="104.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8" paint-order="stroke" stroke="#ffffff" stroke-width="3">dhcp 10.44.2.100-199</text>
<line x1="222.0" y1="144.7" x2="124.0" y2="159.2" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><text x="196.3" y="140.5" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#475569">p1</text><text x="149.7" y="147.4" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#475569">p1</text>
<line x1="266.0" y1="144.7" x2="364.0" y2="159.2" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><text x="291.7" y="140.5" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#475569">p2</text><text x="338.3" y="147.4" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="9" fill="#475569">p1</text>
<g data-rol="rte1" data-x="244.0" data-y="141.5" transform="translate(244.0,141.5) scale(1.0)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g>
<g data-rol="wsp1" data-x="105.0" data-y="162.0" transform="translate(105.0,162.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g data-rol="wsp2" data-x="383.0" data-y="162.0" transform="translate(383.0,162.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<text x="244.0" y="82.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text><text x="244.0" y="94.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.44.1.1/24</text><text x="244.0" y="106.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.44.2.1/24</text>
<text x="80.0" y="160.0" text-anchor="end" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text><text x="80.0" y="172.0" text-anchor="end" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="408.0" y="160.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text><text x="408.0" y="172.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
</g>
</svg>


*cada área es una red; su cabecera dice la subred y el rango que reparte. Cada equipo lleva escrito lo que no cambia —su dirección estática, o `dhcp`— y la forma de su símbolo dice su clase. La línea dice que están conectados y va sin flechas: el plano no inventa un sentido de tráfico.*

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
