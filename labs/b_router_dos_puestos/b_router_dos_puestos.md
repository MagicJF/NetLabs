# Laboratorio `b_router_dos_puestos`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## b_router_dos_puestos
Address spaces: `10.44.0.0/16`

### Topología

<svg xmlns="http://www.w3.org/2000/svg" width="384" height="369" viewBox="0 0 384 369" role="img" aria-label="Plano de b_router_dos_puestos">
<rect width="384" height="369" fill="#ffffff"/>
<text x="192.0" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">b_router_dos_puestos</text>
<text x="192.0" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.44.x.x/16</text>
<g transform="translate(192.0,206.0)">
<rect x="-168.0" y="-85.0" width="162.0" height="170.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-152.0" y="-64.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan1</text><text x="-152.0" y="-49.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.44.1.x/24</text><text x="-152.0" y="-34.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.44.1.100-199</text>
<rect x="6.0" y="-85.0" width="162.0" height="170.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="22.0" y="-64.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan2</text><text x="22.0" y="-49.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.44.2.x/24</text><text x="22.0" y="-34.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.44.2.100-199</text>
<g transform="translate(-87.0,0.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(87.0,0.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g>
<g transform="translate(0.0,-104.0) scale(1.0)"><path d="M-30 8c-6 0-11-5-11-11s5-11 11-11c2-8 9-13 17-13 9 0 16 6 18 14 7 0 12 5 12 11s-5 10-12 10z" fill="#f4f7fa" stroke="#5b7793" stroke-width="1.8" transform="translate(3,6)"/></g>
<line x1="0.0" y1="-80.0" x2="0.0" y2="-22.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="5 4"/>
<line x1="-22.0" y1="0.0" x2="-68.0" y2="0.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="22.0" y1="0.0" x2="68.0" y2="0.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<text x="-112.0" y="-2.0" text-anchor="end" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text><text x="-112.0" y="10.0" text-anchor="end" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="112.0" y="-2.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text><text x="112.0" y="10.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="0.0" y="32.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text><text x="0.0" y="44.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.44.1.1/24</text><text x="0.0" y="56.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.44.2.1/24</text>
<text x="0.0" y="-135.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">Internet</text>
</g>
<rect x="85.4" y="321.0" width="213.2" height="38" rx="10" fill="#ffffff" stroke="#e2e8f0"/><rect x="97.4" y="333.0" width="18" height="14" rx="4" fill="#3b82f6" fill-opacity="0.08" stroke="#93b4f5"/><text x="120.4" y="344.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">red</text><g transform="translate(156.1,340.0) scale(0.72)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g><text x="176.8" y="344.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">router</text><g transform="translate(249.7,340.0) scale(0.72)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g><text x="268.2" y="344.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">puesto</text>
</svg>


*cada área es una red; su cabecera dice la subred y la dirección de su puerta. La forma del símbolo dice la clase de equipo y la línea dice que están conectados: sin flechas, que el plano no inventa un sentido de tráfico.*

### Cableado (L2)

<svg xmlns="http://www.w3.org/2000/svg" width="384" height="343" viewBox="0 0 384 343" role="img" aria-label="Plano de b_router_dos_puestos">
<rect width="384" height="343" fill="#ffffff"/>
<text x="192.0" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">b_router_dos_puestos</text>
<text x="192.0" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.44.x.x/16</text>
<g transform="translate(192.0,180.0)">
<rect x="-168.0" y="-85.0" width="162.0" height="170.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-152.0" y="-64.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan1</text><text x="-152.0" y="-49.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.44.1.x/24</text><text x="-152.0" y="-34.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.44.1.100-199</text>
<rect x="6.0" y="-85.0" width="162.0" height="170.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="22.0" y="-64.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan2</text><text x="22.0" y="-49.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.44.2.x/24</text><text x="22.0" y="-34.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.44.2.100-199</text>
<g transform="translate(-87.0,0.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(87.0,0.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g>
<line x1="-22.0" y1="0.0" x2="-68.0" y2="0.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-50.0" y="-8.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="-40.0" y="3.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text><rect x="-60.0" y="-8.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="-50.0" y="3.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<line x1="22.0" y1="0.0" x2="68.0" y2="0.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="30.0" y="-8.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="40.0" y="3.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p2</text><rect x="40.0" y="-8.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="50.0" y="3.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<text x="-112.0" y="4.0" text-anchor="end" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text>
<text x="112.0" y="4.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text>
<text x="0.0" y="32.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text>
</g>
<rect x="85.4" y="295.0" width="213.2" height="38" rx="10" fill="#ffffff" stroke="#e2e8f0"/><rect x="97.4" y="307.0" width="18" height="14" rx="4" fill="#3b82f6" fill-opacity="0.08" stroke="#93b4f5"/><text x="120.4" y="318.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">red</text><g transform="translate(156.1,314.0) scale(0.72)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g><text x="176.8" y="318.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">router</text><g transform="translate(249.7,314.0) scale(0.72)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g><text x="268.2" y="318.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">puesto</text>
</svg>


*cada punta de cada cable dice el puerto que ocupa; la línea, el cable que los une tal y como se declara.*

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
