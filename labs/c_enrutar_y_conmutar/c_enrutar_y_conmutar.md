# Laboratorio `c_enrutar_y_conmutar`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## c_enrutar_y_conmutar
Address spaces: `10.46.0.0/16`

### Topología

<svg xmlns="http://www.w3.org/2000/svg" width="340" height="574" viewBox="0 0 340 574" role="img" aria-label="Plano de c_enrutar_y_conmutar">
<rect width="340" height="574" fill="#ffffff"/>
<text x="170.0" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">c_enrutar_y_conmutar</text>
<text x="170.0" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.46.x.x/16</text>
<g transform="translate(170.0,206.0)">
<rect x="-146.0" y="6.0" width="292.0" height="338.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-130.0" y="27.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan</text><text x="-130.0" y="42.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.46.1.x/24</text><text x="-130.0" y="57.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.46.1.100-199</text>
<g transform="translate(0.0,118.0) scale(1.0)"><rect x="-24" y="-10" width="48" height="20" rx="3" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-14" y1="-3" x2="8.8" y2="-4.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,-3 6.8,-1.0 6.8,-5.0" fill="#7c4dff"/><line x1="14" y1="3" x2="-11.2" y2="1.8" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-10,3 -6.8,1.0 -6.8,5.0" fill="#7c4dff"/><path d="M-16 10v3M-8 10v3M0 10v3M8 10v3M16 10v3" stroke="#7c4dff" stroke-width="1.4"/></g>
<g transform="translate(0.0,202.0) scale(1.0)"><rect x="-24" y="-10" width="48" height="20" rx="3" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-14" y1="-3" x2="8.8" y2="-4.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,-3 6.8,-1.0 6.8,-5.0" fill="#7c4dff"/><line x1="14" y1="3" x2="-11.2" y2="1.8" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-10,3 -6.8,1.0 -6.8,5.0" fill="#7c4dff"/><path d="M-16 10v3M-8 10v3M0 10v3M8 10v3M16 10v3" stroke="#7c4dff" stroke-width="1.4"/></g>
<g transform="translate(-65.0,286.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(65.0,286.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g>
<g transform="translate(0.0,-104.0) scale(1.0)"><path d="M-30 8c-6 0-11-5-11-11s5-11 11-11c2-8 9-13 17-13 9 0 16 6 18 14 7 0 12 5 12 11s-5 10-12 10z" fill="#f4f7fa" stroke="#5b7793" stroke-width="1.8" transform="translate(3,6)"/></g>
<line x1="0.0" y1="-80.0" x2="0.0" y2="-22.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="5 4"/>
<line x1="0.0" y1="22.0" x2="0.0" y2="103.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="0.0" y1="133.0" x2="0.0" y2="187.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="-11.6" y1="217.0" x2="-51.8" y2="269.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="11.6" y1="217.0" x2="51.8" y2="269.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<text x="35.0" y="122.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swc1</text>
<text x="35.0" y="206.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swa1</text>
<text x="-65.0" y="313.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text><text x="-65.0" y="325.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="65.0" y="313.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text><text x="65.0" y="325.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="28.0" y="-2.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text><text x="28.0" y="10.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.46.1.1/24</text>
<text x="0.0" y="-135.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">Internet</text>
</g>
</svg>


*cada área es una red; su cabecera dice la subred y el rango que reparte. Cada equipo lleva escrito lo que no cambia —su dirección estática, o `dhcp`— y la forma de su símbolo dice su clase. La línea dice que están conectados y va sin flechas: el plano no inventa un sentido de tráfico.*

### Cableado (L2)

<svg xmlns="http://www.w3.org/2000/svg" width="340" height="548" viewBox="0 0 340 548" role="img" aria-label="Plano de c_enrutar_y_conmutar">
<rect width="340" height="548" fill="#ffffff"/>
<text x="170.0" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">c_enrutar_y_conmutar</text>
<text x="170.0" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.46.x.x/16</text>
<g transform="translate(170.0,180.0)">
<rect x="-146.0" y="6.0" width="292.0" height="338.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-130.0" y="27.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1b5fa8">lan</text><text x="-130.0" y="42.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.46.1.x/24</text><text x="-130.0" y="57.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1b5fa8">dhcp 10.46.1.100-199</text>
<g transform="translate(0.0,118.0) scale(1.0)"><rect x="-24" y="-10" width="48" height="20" rx="3" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-14" y1="-3" x2="8.8" y2="-4.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,-3 6.8,-1.0 6.8,-5.0" fill="#7c4dff"/><line x1="14" y1="3" x2="-11.2" y2="1.8" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-10,3 -6.8,1.0 -6.8,5.0" fill="#7c4dff"/><path d="M-16 10v3M-8 10v3M0 10v3M8 10v3M16 10v3" stroke="#7c4dff" stroke-width="1.4"/></g>
<g transform="translate(0.0,202.0) scale(1.0)"><rect x="-24" y="-10" width="48" height="20" rx="3" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-14" y1="-3" x2="8.8" y2="-4.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="10,-3 6.8,-1.0 6.8,-5.0" fill="#7c4dff"/><line x1="14" y1="3" x2="-11.2" y2="1.8" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-10,3 -6.8,1.0 -6.8,5.0" fill="#7c4dff"/><path d="M-16 10v3M-8 10v3M0 10v3M8 10v3M16 10v3" stroke="#7c4dff" stroke-width="1.4"/></g>
<g transform="translate(-65.0,286.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(65.0,286.0) scale(1.0)"><rect x="-15" y="-13" width="30" height="21" rx="2" fill="#ffffff" stroke="#5b7793" stroke-width="1.8"/><rect x="-11.5" y="-9.5" width="23" height="14" rx="1" fill="#eef5fb"/><path d="M-4 8v5h8V8" fill="none" stroke="#5b7793" stroke-width="1.6"/><rect x="-9" y="13" width="18" height="2.4" rx="1.2" fill="#5b7793"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="15.5" fill="#ffffff" stroke="#7c4dff" stroke-width="2"/><line x1="-3" y1="0" x2="-12.7" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="-11.5,0 -8.1,-2.2 -8.1,2.2" fill="#7c4dff"/><line x1="3" y1="0" x2="10.3" y2="-1.2" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="11.5,0 8.1,2.2 8.1,-2.2" fill="#7c4dff"/><line x1="0" y1="-3" x2="-1.2" y2="-12.7" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,-11.5 2.2,-8.1 -2.2,-8.1" fill="#7c4dff"/><line x1="0" y1="3" x2="-1.2" y2="10.3" stroke="#7c4dff" stroke-width="1.5" stroke-linecap="round"/><polygon points="0,11.5 -2.2,8.1 2.2,8.1" fill="#7c4dff"/></g>
<line x1="0.0" y1="22.0" x2="0.0" y2="103.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-10.0" y="32.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="0.0" y="43.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text><rect x="-10.0" y="77.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="0.0" y="88.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<line x1="0.0" y1="133.0" x2="0.0" y2="187.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-10.0" y="143.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="0.0" y="154.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p2</text><rect x="-10.0" y="161.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="0.0" y="172.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<line x1="-11.6" y1="217.0" x2="-51.8" y2="269.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-32.6" y="223.2" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="-22.6" y="234.7" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p2</text><rect x="-50.8" y="246.8" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="-40.8" y="258.3" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<line x1="11.6" y1="217.0" x2="51.8" y2="269.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="12.6" y="223.2" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="22.6" y="234.7" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p3</text><rect x="30.8" y="246.8" width="20" height="16" rx="5" fill="#ffffff" stroke="#1b5fa8" stroke-width="1.1"/><text x="40.8" y="258.3" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1b5fa8">p1</text>
<text x="35.0" y="122.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swc1</text>
<text x="35.0" y="206.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swa1</text>
<text x="-65.0" y="313.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text><text x="-65.0" y="325.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="65.0" y="313.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text><text x="65.0" y="325.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="0.0" y="-41.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text><text x="0.0" y="-29.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">10.46.1.1/24</text>
</g>
</svg>


*cada punta de cada cable dice el puerto que ocupa; la línea, el cable que los une tal y como se declara.*

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
