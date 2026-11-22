# Laboratorio `c_enrutar_y_conmutar`

Lo que se aprendió ejecutándolo va debajo de la tabla. La tabla se genera con
`./netlabs docs` y no se edita a mano: sale de la declaración.

<!-- netlabs:begin -- generado por `./netlabs docs`; no se edita a mano -->

## c_enrutar_y_conmutar
Address spaces: `10.46.0.0/16`

### Topología

<svg xmlns="http://www.w3.org/2000/svg" width="381" height="628" viewBox="0 0 381 628" role="img" aria-label="Plano de c_enrutar_y_conmutar">
<rect width="381" height="628" fill="#ffffff"/>
<text x="190.7" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">c_enrutar_y_conmutar</text>
<text x="190.7" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.46.x.x/16</text>
<g transform="translate(170.0,206.0)">
<rect x="-146.0" y="6.0" width="292.0" height="338.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-130.0" y="27.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1d4ed8">lan</text><text x="-130.0" y="42.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.46.1.x/24</text><text x="-130.0" y="57.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1d4ed8">puerta 10.46.1.1/24</text>
<g transform="translate(0.0,118.0) scale(1.0)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g>
<g transform="translate(0.0,202.0) scale(1.0)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g>
<g transform="translate(-65.0,286.0) scale(1.0)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g>
<g transform="translate(65.0,286.0) scale(1.0)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="20" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2"/><line x1="-13" y1="-5" x2="11" y2="-7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="13,-5 8.8,-2.4 8.8,-7.6" fill="#1d4ed8"/><line x1="13" y1="5" x2="-15" y2="3" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-13,5 -8.8,2.4 -8.8,7.6" fill="#1d4ed8"/><line x1="-5" y1="13" x2="-7" y2="-15" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-5,-13 -2.4,-8.8 -7.6,-8.8" fill="#1d4ed8"/><line x1="5" y1="-13" x2="3" y2="11" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="5,13 2.4,8.8 7.6,8.8" fill="#1d4ed8"/></g>
<g transform="translate(0.0,-104.0) scale(1.0)"><path d="M-30 8c-6 0-11-5-11-11s5-11 11-11c2-8 9-13 17-13 9 0 16 6 18 14 7 0 12 5 12 11s-5 10-12 10z" fill="#f8fafc" stroke="#64748b" stroke-width="2" transform="translate(3,6)"/></g>
<line x1="0.0" y1="-79.0" x2="0.0" y2="-25.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round" stroke-dasharray="5 4"/>
<line x1="0.0" y1="25.0" x2="0.0" y2="102.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="0.0" y1="134.0" x2="0.0" y2="186.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="-12.4" y1="218.0" x2="-51.1" y2="268.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<line x1="12.4" y1="218.0" x2="51.1" y2="268.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/>
<text x="38.0" y="122.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swc1</text>
<text x="38.0" y="206.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swa1</text>
<text x="-65.0" y="314.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text><text x="-65.0" y="326.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="65.0" y="314.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text><text x="65.0" y="326.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" font-weight="400" fill="#475569" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">dhcp</text>
<text x="31.0" y="4.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text>
<text x="0.0" y="-136.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">Internet</text>
</g>
<rect x="24.0" y="580.0" width="333.4" height="38" rx="10" fill="#ffffff" stroke="#e2e8f0"/><rect x="36.0" y="592.0" width="18" height="14" rx="4" fill="#3b82f6" fill-opacity="0.08" stroke="#93b4f5"/><text x="59.0" y="603.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">red</text><g transform="translate(96.8,599.0) scale(0.72)"><circle r="20" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2"/><line x1="-13" y1="-5" x2="11" y2="-7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="13,-5 8.8,-2.4 8.8,-7.6" fill="#1d4ed8"/><line x1="13" y1="5" x2="-15" y2="3" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-13,5 -8.8,2.4 -8.8,7.6" fill="#1d4ed8"/><line x1="-5" y1="13" x2="-7" y2="-15" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-5,-13 -2.4,-8.8 -7.6,-8.8" fill="#1d4ed8"/><line x1="5" y1="-13" x2="3" y2="11" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="5,13 2.4,8.8 7.6,8.8" fill="#1d4ed8"/></g><text x="119.7" y="603.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">router</text><g transform="translate(202.0,599.0) scale(0.72)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g><text x="229.8" y="603.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">switch</text><g transform="translate(305.6,599.0) scale(0.72)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g><text x="327.0" y="603.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">puesto</text>
</svg>


*cada área es una red; su cabecera dice la subred y la dirección de su puerta. La forma del símbolo dice la clase de equipo y la línea dice que están conectados: sin flechas, que el plano no inventa un sentido de tráfico.*

### Cableado (L2)

<svg xmlns="http://www.w3.org/2000/svg" width="381" height="602" viewBox="0 0 381 602" role="img" aria-label="Plano de c_enrutar_y_conmutar">
<rect width="381" height="602" fill="#ffffff"/>
<text x="190.7" y="28" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="15" font-weight="650" fill="#0f172a">c_enrutar_y_conmutar</text>
<text x="190.7" y="45" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11.5" fill="#475569">10.46.x.x/16</text>
<g transform="translate(170.0,180.0)">
<rect x="-146.0" y="6.0" width="292.0" height="338.0" rx="14" fill="#3b82f6" fill-opacity="0.06" stroke="#93b4f5" stroke-width="1.4"/><text x="-130.0" y="27.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="650" fill="#1d4ed8">lan</text><text x="-130.0" y="42.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#475569">10.46.1.x/24</text><text x="-130.0" y="57.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10.5" fill="#1d4ed8">puerta 10.46.1.1/24</text>
<g transform="translate(0.0,118.0) scale(1.0)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g>
<g transform="translate(0.0,202.0) scale(1.0)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g>
<g transform="translate(-65.0,286.0) scale(1.0)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g>
<g transform="translate(65.0,286.0) scale(1.0)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g>
<g transform="translate(0.0,0.0) scale(1.0)"><circle r="20" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2"/><line x1="-13" y1="-5" x2="11" y2="-7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="13,-5 8.8,-2.4 8.8,-7.6" fill="#1d4ed8"/><line x1="13" y1="5" x2="-15" y2="3" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-13,5 -8.8,2.4 -8.8,7.6" fill="#1d4ed8"/><line x1="-5" y1="13" x2="-7" y2="-15" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-5,-13 -2.4,-8.8 -7.6,-8.8" fill="#1d4ed8"/><line x1="5" y1="-13" x2="3" y2="11" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="5,13 2.4,8.8 7.6,8.8" fill="#1d4ed8"/></g>
<line x1="0.0" y1="25.0" x2="0.0" y2="102.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-10.0" y="35.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="0.0" y="46.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p1</text><rect x="-10.0" y="76.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="0.0" y="87.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p1</text>
<line x1="0.0" y1="134.0" x2="0.0" y2="186.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-10.0" y="144.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="0.0" y="155.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p2</text><rect x="-10.0" y="160.0" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="0.0" y="171.5" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p1</text>
<line x1="-12.4" y1="218.0" x2="-51.1" y2="268.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="-33.4" y="224.2" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="-23.4" y="235.7" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p2</text><rect x="-50.1" y="245.8" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="-40.1" y="257.3" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p1</text>
<line x1="12.4" y1="218.0" x2="51.1" y2="268.0" stroke="#94a3b8" stroke-width="1.6" stroke-linecap="round"/><rect x="13.4" y="224.2" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="23.4" y="235.7" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p3</text><rect x="30.1" y="245.8" width="20" height="16" rx="5" fill="#ffffff" stroke="#1d4ed8" stroke-width="1.1"/><text x="40.1" y="257.3" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="10" font-weight="600" fill="#1d4ed8">p1</text>
<text x="38.0" y="122.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swc1</text>
<text x="38.0" y="206.0" text-anchor="start" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">swa1</text>
<text x="-65.0" y="314.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp1</text>
<text x="65.0" y="314.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">wsp2</text>
<text x="0.0" y="-32.0" text-anchor="middle" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="12.5" font-weight="600" fill="#0f172a" stroke="#ffffff" stroke-width="3.5" paint-order="stroke">rte1</text>
</g>
<rect x="24.0" y="554.0" width="333.4" height="38" rx="10" fill="#ffffff" stroke="#e2e8f0"/><rect x="36.0" y="566.0" width="18" height="14" rx="4" fill="#3b82f6" fill-opacity="0.08" stroke="#93b4f5"/><text x="59.0" y="577.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">red</text><g transform="translate(96.8,573.0) scale(0.72)"><circle r="20" fill="#dbeafe" stroke="#1d4ed8" stroke-width="2"/><line x1="-13" y1="-5" x2="11" y2="-7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="13,-5 8.8,-2.4 8.8,-7.6" fill="#1d4ed8"/><line x1="13" y1="5" x2="-15" y2="3" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-13,5 -8.8,2.4 -8.8,7.6" fill="#1d4ed8"/><line x1="-5" y1="13" x2="-7" y2="-15" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-5,-13 -2.4,-8.8 -7.6,-8.8" fill="#1d4ed8"/><line x1="5" y1="-13" x2="3" y2="11" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="5,13 2.4,8.8 7.6,8.8" fill="#1d4ed8"/></g><text x="119.7" y="577.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">router</text><g transform="translate(202.0,573.0) scale(0.72)"><rect x="-28" y="-12" width="56" height="24" rx="4" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><line x1="-16" y1="-4" x2="14" y2="-6" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="16,-4 11.8,-1.4 11.8,-6.6" fill="#1d4ed8"/><line x1="16" y1="4" x2="-18" y2="2" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/><polygon points="-16,4 -11.8,1.4 -11.8,6.6" fill="#1d4ed8"/><polygon points="-20,-9 -20,-1 -16,-1 -16,-9" fill="#bfdbfe"/></g><text x="229.8" y="577.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">switch</text><g transform="translate(305.6,573.0) scale(0.72)"><rect x="-19" y="-15" width="38" height="24" rx="2.5" fill="#ffffff" stroke="#1d4ed8" stroke-width="2"/><path d="M-19 -7H19" stroke="#1d4ed8" stroke-width="1.3"/><path d="M0 9V14M-7 14H7" stroke="#1d4ed8" stroke-width="1.6" stroke-linecap="round"/></g><text x="327.0" y="577.0" font-family="'Inter','Segoe UI',Helvetica,Arial,sans-serif" font-size="11" fill="#475569">puesto</text>
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
