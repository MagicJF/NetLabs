# PROPÓSITO:   abrir el camino la primera vez: entrar por la consola de la API al
#              invitado de gestión y dejarlo con un túnel inverso hacia el nodo de
#              control, como servicio que se levanta solo. Después de esto, la consola
#              no se vuelve a usar.
# INVARIANTES: la clave privada del túnel va en el script y no se imprime nunca.
#              El script se ejecuta en UNA línea (base64) para que la consola no tenga
#              que interpretar heredocs línea a línea.
#              No se instala nada que necesite red para llegar hasta aquí: el túnel es
#              lo primero que se abre.
# VER:         docs/decisiones/0002-arranque-del-servicio-de-gestion.md

from __future__ import annotations

import base64
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import console  # noqa: E402

RAIZ = pathlib.Path(__file__).resolve().parent.parent.parent


def script(env: dict, secrets: dict, clave_privada: str) -> str:
    tunel = env["management"]["tunnel"]
    ssh_port = tunel["local_ssh_port"]
    web_port = tunel["local_web_port"]
    destino = f"{secrets['pve_tunnel_usuario']}@{secrets['pve_tunnel_salida_host']}"
    return f"""mkdir -p /root/.ssh /etc/netlabs
cat > /root/.ssh/netlabs_tunnel <<'NETLABSKEY'
{clave_privada.rstrip()}
NETLABSKEY
chmod 700 /root/.ssh
chmod 600 /root/.ssh/netlabs_tunnel
ssh-keygen -y -f /root/.ssh/netlabs_tunnel > /root/.ssh/netlabs_tunnel.pub
chmod 644 /root/.ssh/netlabs_tunnel.pub
if ! grep -q '^netlabs-tunnel' /root/.ssh/authorized_keys 2>/dev/null; then
  cat /root/.ssh/netlabs_tunnel.pub | sed 's/^/netlabs-tunnel /' >> /root/.ssh/authorized_keys || true
fi
cat > /etc/netlabs/tunnel.sh <<'NETLABSSH'
#!/bin/sh
exec ssh -N -T -i /root/.ssh/netlabs_tunnel \\
  -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o LogLevel=ERROR \\
  -o ExitOnForwardFailure=yes -o ServerAliveInterval=20 -o ServerAliveCountMax=3 \\
  -o TCPKeepAlive=yes \\
  -R {ssh_port}:localhost:22 -R {web_port}:localhost:443 \\
  -p {secrets['pve_tunnel_salida_puerto']} {destino}
NETLABSSH
chmod 755 /etc/netlabs/tunnel.sh
cat > /etc/systemd/system/netlabs-tunnel.service <<'NETLABSUNIT'
[Unit]
Description=netlabs: camino hacia el nodo de control
After=network-online.target
Wants=network-online.target
[Service]
ExecStart=/etc/netlabs/tunnel.sh
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
NETLABSUNIT
systemctl daemon-reload
systemctl enable netlabs-tunnel >/dev/null 2>&1
systemctl restart netlabs-tunnel
sleep 2
systemctl is-active netlabs-tunnel
echo NETLABS-TUNEL-LISTO
"""


def main(sitio_json: str) -> int:
    env = __import__("yaml").safe_load((RAIZ / "netlabs.yml").read_text())
    secrets = __import__("yaml").safe_load((RAIZ / "secrets.yml").read_text())
    sitio = json.loads(pathlib.Path(sitio_json).read_text())
    clave = pathlib.Path(env["management"]["tunnel"]["key"]).expanduser().read_text()
    apis = console.Apis(
        secrets["pve_nodo"], secrets["pve_puerto"], secrets["pve_nombre_nodo"],
        secrets["pve_token_id"], secrets["pve_token_secreto"],
    )
    orden = "echo " + base64.b64encode(script(env, secrets, clave).encode()).decode() + " | base64 -d | sh"
    salida = console.run(apis, int(sitio["vmid"]), [orden], timeout=180)
    print(salida[-1200:])
    return 0 if "NETLABS-TUNEL-LISTO" in salida else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
