# PROPÓSITO:   la consola de un invitado, hablada POR LA API. Es la puerta de
#              emergencia del diseño y la única forma de abrir el túnel del servicio
#              persistente la primera vez: un contenedor no tiene agente de invitado y
#              nadie ha entrado todavía.
# INVARIANTES: no abre sesión SSH al hipervisor ni usa `pct`: entra por termproxy +
#              vncwebsocket, que es la consola de la API.
#              El protocolo está MEDIDO: el primer mensaje es `<usuario>:<ticket>\n` y
#              la respuesta `OK`; después cada mensaje es binario con un byte de canal
#              (0 = terminal) delante.
#              El fin se marca con un `echo` cuyo resultado no aparece en el comando:
#              si el marcador no llega, es un fallo, no un verde.
# LÍMITES:     síncrona y de un solo uso; no es un terminal interactivo.
# VER:         docs/decisiones/0002-arranque-del-servicio-de-gestion.md

from __future__ import annotations

import base64
import json
import os
import socket
import ssl
import struct
import time
import urllib.parse
import urllib.request


class ConsoleError(Exception):
    pass


class _WebSocket:
    """El trozo de WebSocket que hace falta: saludo, frames binarios y lectura."""

    def __init__(self, host: str, port: int, path: str, timeout: float = 20.0,
                 headers: dict | None = None):
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock = ssl._create_unverified_context().wrap_socket(self.sock, server_hostname=host)
        clave = base64.b64encode(os.urandom(16)).decode()
        self.sock.sendall((
            f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\nUpgrade: websocket\r\n"
            f"Connection: Upgrade\r\nSec-WebSocket-Key: {clave}\r\n"
            "Sec-WebSocket-Version: 13\r\nSec-WebSocket-Protocol: binary\r\n"
            + "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items())
            + "\r\n"
        ).encode())
        respuesta = b""
        while b"\r\n\r\n" not in respuesta:
            trozo = self.sock.recv(4096)
            if not trozo:
                raise ConsoleError("la consola cerró durante el saludo")
            respuesta += trozo
        if b"101" not in respuesta.split(b"\r\n")[0]:
            raise ConsoleError(f"la consola rechazó el saludo: {respuesta[:120]!r}")

    def _frame(self, datos: bytes) -> None:
        mascara = os.urandom(4)
        cabecera = bytearray([0x82])
        largo = len(datos)
        if largo < 126:
            cabecera.append(0x80 | largo)
        elif largo < 65536:
            cabecera.append(0x80 | 126)
            cabecera += struct.pack(">H", largo)
        else:
            cabecera.append(0x80 | 127)
            cabecera += struct.pack(">Q", largo)
        cabecera += mascara
        self.sock.sendall(bytes(cabecera) + bytes(b ^ mascara[i % 4] for i, b in enumerate(datos)))

    def send_text(self, texto: str) -> None:
        self._frame(texto.encode())

    def send_terminal(self, texto: str) -> None:
        # El formato lo dicta el cliente de xterm.js de Proxmox: "0:<bytes>:<datos>".
        datos = texto.encode()
        self._frame(b"0:" + str(len(datos)).encode() + b":" + datos)

    def recv(self, segundos: float = 5.0) -> str:
        self.sock.settimeout(segundos)
        try:
            cabecera = self.sock.recv(2)
        except socket.timeout:
            return ""
        if len(cabecera) < 2:
            return ""
        opcode = cabecera[0] & 0x0F
        largo = cabecera[1] & 0x7F
        if largo == 126:
            largo = struct.unpack(">H", self.sock.recv(2))[0]
        elif largo == 127:
            largo = struct.unpack(">Q", self.sock.recv(8))[0]
        datos = b""
        while len(datos) < largo:
            datos += self.sock.recv(largo - len(datos))
        if opcode == 0x8:
            raise ConsoleError("la consola se cerró")
        if opcode == 0x9:
            return ""
        return datos[1:].decode(errors="replace") if datos[:1] == b"\x00" else datos.decode(errors="replace")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def _drenar(ws: _WebSocket, salida: str, espera: float = 2.0, hasta: str | None = None,
            limite: float = 120.0) -> str:
    """Lee de la consola hasta que deje de hablar o hasta ver `hasta`."""
    final = time.time() + limite
    mudo = 0
    while time.time() < final:
        trozo = ws.recv(espera)
        if not trozo:
            mudo += 1
            if mudo >= 2:
                break
            continue
        mudo = 0
        salida += trozo
        if hasta and hasta in salida:
            break
    return salida


def run(apis: "Apis", vmid: int, lineas: list[str], espera: float = 2.0,
        timeout: float = 180.0) -> str:
    """Escribe líneas en la consola de un invitado y devuelve lo que respondió."""
    datos = apis.post(f"/nodes/{apis.node}/lxc/{vmid}/termproxy")
    ticket, puerto, usuario = datos["ticket"], datos["port"], datos.get("user")
    ruta = (
        f"/api2/json/nodes/{apis.node}/lxc/{vmid}/vncwebsocket"
        f"?port={puerto}&vncticket={urllib.parse.quote(ticket, safe='')}"
    )
    ws = _WebSocket(apis.host, apis.port, ruta, headers={"Authorization": apis._auth})
    try:
        ws.send_text(f"{usuario}:{ticket}\n")
        if "OK" not in ws.recv(6):
            raise ConsoleError("la consola no contestó OK al saludo: el ticket no vale para esta sesión")
        time.sleep(0.6)
        ws.send_terminal("\r")
        salida = _drenar(ws, "", espera, limite=10)
        for linea in lineas:
            ws.send_terminal(linea + "\r")
            # Las líneas largas tardan: se drena hasta que la consola calla.
            salida = _drenar(ws, salida, espera, limite=min(timeout, 60))
        # El marcador se calcula dentro del invitado: así no puede aparecer en el eco
        # del comando y el final se reconoce de verdad.
        semilla = int(time.time()) % 1000
        ws.send_terminal(f"echo NETLABS-CONSOLA-{semilla}-$((6*7))\r")
        buscado = f"NETLABS-CONSOLA-{semilla}-42"
        salida = _drenar(ws, salida, espera, hasta=buscado, limite=timeout)
        if buscado not in salida:
            raise ConsoleError(f"la consola no llegó al marcador en {timeout:.0f}s; lo último: {salida[-400:]!r}")
        return salida
    finally:
        ws.close()


class Apis:
    """Las llamadas de API que la consola necesita, y nada más."""

    def __init__(self, host: str, port: int, node: str, token_id: str, token: str):
        self.host, self.port, self.node = host, int(port), node
        self._auth = f"PVEAPIToken={token_id}={token}"

    def _call(self, metodo: str, ruta: str, cuerpo: dict | None = None):
        datos = urllib.parse.urlencode(cuerpo, doseq=True).encode() if cuerpo else None
        peticion = urllib.request.Request(
            f"https://{self.host}:{self.port}/api2/json{ruta}",
            data=datos, method=metodo, headers={"Authorization": self._auth},
        )
        with urllib.request.urlopen(
            peticion, context=ssl._create_unverified_context(), timeout=30
        ) as respuesta:
            texto = respuesta.read().decode()
            return json.loads(texto)["data"] if texto.strip() else None

    def get(self, ruta: str):
        return self._call("GET", ruta)

    def post(self, ruta: str, cuerpo: dict | None = None):
        return self._call("POST", ruta, cuerpo)
