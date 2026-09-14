"""Cliente minimo del Docker Engine API sobre el socket Unix montado en
el propio contenedor (/var/run/docker.sock) -- sin el CLI de `docker`
(no esta instalado en la imagen, ver Dockerfile.geant4-worker) ni
dependencias nuevas (requests no soporta sockets Unix sin el paquete
aparte `requests-unixsocket`; esto usa solo http.client/socket/json de
la stdlib). Usado exclusivamente por auto_update() en worker.py para que
un worker Docker pueda leer su propia identidad y recrearse a si mismo
con una imagen nueva -- ver AGENTS.md, "Auto-actualizacion de workers
Docker".

Requiere que el contenedor monte el socket del host:
    -v /var/run/docker.sock:/var/run/docker.sock
No aplica a la via sin Docker (GUIA_WORKER_LOCAL.md) -- ahi no hay
contenedor que recrear, auto_update() se vuelve no-op (ver worker.py).
"""
import http.client
import json
import socket
from urllib.parse import quote


class DockerAPIError(Exception):
    pass


class UnixSocketHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float = 30.0):
        super().__init__("localhost", timeout=timeout)
        self.unix_socket = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect(self.unix_socket)


class DockerClient:
    def __init__(self, socket_path: str = "/var/run/docker.sock", timeout: float = 30.0):
        self.socket_path = socket_path
        self.timeout = timeout

    def _request(self, method: str, path: str, body: dict | None = None, timeout: float | None = None) -> tuple:
        conn = UnixSocketHTTPConnection(self.socket_path, timeout=timeout or self.timeout)
        headers = {}
        data = None
        if body is not None:
            data = json.dumps(body).encode("utf-8")
            headers["Content-Type"] = "application/json"
        try:
            conn.request(method, path, body=data, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
            return resp.status, raw
        except (OSError, http.client.HTTPException) as exc:
            raise DockerAPIError(f"Docker transport {method} {path}: {exc}") from exc
        finally:
            conn.close()

    def available(self) -> bool:
        try:
            status, _ = self._request("GET", "/_ping", timeout=5)
            return status == 200
        except DockerAPIError:
            return False

    def inspect_container(self, container_id: str) -> dict:
        status, raw = self._request("GET", f"/containers/{container_id}/json")
        if status != 200:
            raise DockerAPIError(f"inspect_container({container_id}) -> {status}: {raw[:500]!r}")
        return json.loads(raw)

    def inspect_image(self, reference: str) -> dict:
        status, raw = self._request("GET", f"/images/{quote(reference, safe='')}/json")
        if status != 200:
            raise DockerAPIError(f"inspect_image -> {status}: {raw[:500]!r}")
        return json.loads(raw)

    def rename_container(self, container_id: str, name: str) -> None:
        status, raw = self._request("POST", f"/containers/{container_id}/rename?name={quote(name, safe='')}")
        if status != 204:
            raise DockerAPIError(f"rename_container -> {status}: {raw[:500]!r}")

    def set_restart_policy(self, container_id: str, policy: dict) -> None:
        status, raw = self._request("POST", f"/containers/{container_id}/update", {"RestartPolicy": policy})
        if status != 200:
            raise DockerAPIError(f"set_restart_policy -> {status}: {raw[:500]!r}")

    def pull_image(self, repository: str, digest: str) -> None:
        """repository sin tag/digest (ej. 'ghcr.io/org/repo'), digest
        completo con prefijo 'sha256:...'. Bloquea hasta que el pull
        termine (Docker Engine API hace streaming NDJSON de progreso;
        se drena todo el cuerpo, no hace falta parsearlo linea por
        linea para saber si termino)."""
        from urllib.parse import quote
        path = f"/images/create?fromImage={quote(repository, safe='')}&tag={quote(digest, safe='')}"
        status, raw = self._request("POST", path, timeout=600)
        if status != 200:
            raise DockerAPIError(f"pull_image({repository}@{digest}) -> {status}: {raw[-1000:]!r}")
        try:
            for line in raw.splitlines():
                if line.strip():
                    event = json.loads(line)
                    if event.get("error") or event.get("errorDetail"):
                        raise DockerAPIError(f"pull_image failed: {event}")
        except (ValueError, AttributeError) as exc:
            raise DockerAPIError("Invalid Docker pull stream") from exc

    def create_container(self, name: str, image: str, env: list, host_config: dict, labels: dict | None = None) -> str:
        body = {"Image": image, "Env": env, "HostConfig": host_config, "Labels": labels or {}}
        status, raw = self._request("POST", f"/containers/create?name={name}", body=body)
        if status == 409:
            raise DockerAPIError(f"create_container({name}): ya existe un contenedor con ese nombre")
        if status != 201:
            raise DockerAPIError(f"create_container({name}) -> {status}: {raw[:500]!r}")
        return json.loads(raw)["Id"]

    def start_container(self, container_id: str) -> None:
        status, raw = self._request("POST", f"/containers/{container_id}/start")
        if status not in (204, 304):  # 304 = ya estaba corriendo
            raise DockerAPIError(f"start_container({container_id}) -> {status}: {raw[:500]!r}")

    def remove_container(self, container_id: str, force: bool = False) -> None:
        status, raw = self._request("DELETE", f"/containers/{container_id}?force={'true' if force else 'false'}")
        if status not in (204, 404):  # 404 = ya no existia, no es un error aqui
            raise DockerAPIError(f"remove_container({container_id}) -> {status}: {raw[:500]!r}")

    def is_running(self, container_id: str) -> bool:
        try:
            info = self.inspect_container(container_id)
            return bool(info.get("State", {}).get("Running"))
        except DockerAPIError:
            return False
