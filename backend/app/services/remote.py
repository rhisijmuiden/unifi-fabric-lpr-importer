"""Remote backup locations: FTP, FTPS (explicit or implicit TLS) and SCP over SSH.

Every location offers the same small set of file operations inside one remote
directory. SCP targets use the SFTP subsystem of the SSH server when it has one
and fall back to the classic scp protocol plus shell commands when it does not.
"""

import base64
import ftplib
import hashlib
import io
import posixpath
import shlex
import socket
import ssl
import stat
from dataclasses import dataclass
from typing import Protocol

import paramiko

TIMEOUT = 30
PROTOCOLS = ("ftp", "ftps", "scp")
DEFAULT_PORTS = {"ftp": 21, "ftps": 21, "scp": 22}


class RemoteError(Exception):
    """A remote operation failed. `code` is translated in the UI."""

    def __init__(self, code: str, message: str = ""):
        super().__init__(message or code)
        self.code = code


@dataclass
class TargetConfig:
    protocol: str
    host: str
    port: int
    username: str = ""
    password: str = ""
    auth_method: str = "password"  # scp: password | key
    private_key: str = ""  # scp with auth_method "key"
    host_key: str = ""  # scp: pinned fingerprint, empty = accept and report
    remote_path: str = "lpr-importer"
    ftps_implicit: bool = False
    verify_tls: bool = True
    passive: bool = True
    # Create the remote directory when it is missing (backups); off for reading imports.
    create_dir: bool = True


@dataclass
class RemoteFile:
    name: str
    size: int | None = None


class Remote(Protocol):
    host_key: str

    def list(self) -> list[RemoteFile]: ...
    def upload(self, name: str, data: bytes) -> None: ...
    def download(self, name: str) -> bytes: ...
    def delete(self, name: str) -> None: ...
    def close(self) -> None: ...


def _safe_name(name: str) -> str:
    if not name or "/" in name or name in (".", ".."):
        raise RemoteError("invalid_name", f"Invalid file name: {name}")
    return name


# ---------------------------------------------------------------- FTP / FTPS


class _FTP_TLS(ftplib.FTP_TLS):
    """FTPS that reuses the TLS session on data connections, which servers such as
    vsftpd (require_ssl_reuse) and FileZilla Server demand."""

    def ntransfercmd(self, cmd, rest=None):
        conn, size = ftplib.FTP.ntransfercmd(self, cmd, rest)
        if self._prot_p:
            conn = self.context.wrap_socket(conn, server_hostname=self.host, session=self.sock.session)
        return conn, size


class _ImplicitFTP_TLS(_FTP_TLS):
    """FTPS with implicit TLS: the control connection is encrypted from the start."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sock = None

    @property
    def sock(self):
        return self._sock

    @sock.setter
    def sock(self, value):
        if value is not None and not isinstance(value, ssl.SSLSocket):
            value = self.context.wrap_socket(value, server_hostname=self.host)
        self._sock = value


class FtpRemote:
    host_key = ""

    def __init__(self, cfg: TargetConfig):
        self.cfg = cfg
        tls = cfg.protocol == "ftps"
        try:
            if tls:
                context = ssl.create_default_context()
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                if not cfg.verify_tls:
                    context.check_hostname = False
                    context.verify_mode = ssl.CERT_NONE
                cls = _ImplicitFTP_TLS if cfg.ftps_implicit else _FTP_TLS
                self.ftp: ftplib.FTP = cls(context=context, timeout=TIMEOUT)
            else:
                self.ftp = ftplib.FTP(timeout=TIMEOUT)
            self.ftp.connect(cfg.host, cfg.port)
            if tls and not cfg.ftps_implicit:
                self.ftp.auth()
            self.ftp.login(cfg.username or "anonymous", cfg.password or "")
            if tls:
                self.ftp.prot_p()
            self.ftp.set_pasv(cfg.passive)
            self._enter(cfg.remote_path)
        except RemoteError:
            self._close_quietly()
            raise
        except ftplib.error_perm as exc:
            self._close_quietly()
            code = "login_failed" if str(exc).startswith("530") else "remote_error"
            raise RemoteError(code, str(exc)) from exc
        except ssl.SSLCertVerificationError as exc:
            self._close_quietly()
            raise RemoteError("tls_verify_failed", str(exc)) from exc
        except (OSError, EOFError, ftplib.Error) as exc:
            self._close_quietly()
            raise RemoteError("connect_failed", str(exc) or exc.__class__.__name__) from exc

    def _enter(self, path: str) -> None:
        path = (path or "").strip()
        if not path:
            return
        if path.startswith("/"):
            self.ftp.cwd("/")
        for part in [p for p in path.split("/") if p]:
            try:
                self.ftp.cwd(part)
            except ftplib.error_perm:
                if not self.cfg.create_dir:
                    raise RemoteError("not_found", f"Folder {path} not found")
                self.ftp.mkd(part)
                self.ftp.cwd(part)

    def _wrap(self, fn, *args):
        try:
            return fn(*args)
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):
                raise RemoteError("not_found", str(exc)) from exc
            raise RemoteError("remote_error", str(exc)) from exc
        except (OSError, EOFError, ftplib.Error) as exc:
            raise RemoteError("transfer_failed", str(exc) or exc.__class__.__name__) from exc

    def list(self) -> list[RemoteFile]:
        try:
            entries = list(self.ftp.mlsd(facts=["type", "size"]))
            return [
                RemoteFile(name, int(facts["size"]) if facts.get("size", "").isdigit() else None)
                for name, facts in entries
                if facts.get("type", "file") == "file"
            ]
        except ftplib.error_perm:
            pass  # server without MLSD
        try:
            names = self.ftp.nlst()
        except ftplib.error_perm as exc:
            if str(exc).startswith("550"):  # empty directory on some servers
                return []
            raise RemoteError("remote_error", str(exc)) from exc
        except (OSError, EOFError, ftplib.Error) as exc:
            raise RemoteError("transfer_failed", str(exc)) from exc
        return [RemoteFile(posixpath.basename(n)) for n in names]

    def upload(self, name: str, data: bytes) -> None:
        name = _safe_name(name)
        partial = name + ".part"
        self._wrap(self.ftp.storbinary, f"STOR {partial}", io.BytesIO(data))
        try:
            self.ftp.delete(name)
        except ftplib.Error:
            pass
        self._wrap(self.ftp.rename, partial, name)

    def download(self, name: str) -> bytes:
        buf = io.BytesIO()
        self._wrap(self.ftp.retrbinary, f"RETR {_safe_name(name)}", buf.write)
        return buf.getvalue()

    def delete(self, name: str) -> None:
        self._wrap(self.ftp.delete, _safe_name(name))

    def _close_quietly(self) -> None:
        ftp = getattr(self, "ftp", None)
        if ftp is not None:
            try:
                ftp.close()
            except Exception:
                pass

    def close(self) -> None:
        try:
            self.ftp.quit()
        except Exception:
            self._close_quietly()


# ---------------------------------------------------------------- SCP / SSH


def fingerprint(key: paramiko.PKey) -> str:
    digest = hashlib.sha256(key.asbytes()).digest()
    return "SHA256:" + base64.b64encode(digest).decode().rstrip("=")


def load_private_key(text: str) -> paramiko.PKey:
    for cls in (paramiko.Ed25519Key, paramiko.ECDSAKey, paramiko.RSAKey):
        try:
            return cls.from_private_key(io.StringIO(text))
        except (paramiko.SSHException, ValueError):
            continue
    raise RemoteError("invalid_key", "The SSH private key could not be read")


class ScpRemote:
    def __init__(self, cfg: TargetConfig):
        self.cfg = cfg
        self.sftp: paramiko.SFTPClient | None = None
        try:
            sock = socket.create_connection((cfg.host, cfg.port), timeout=TIMEOUT)
            self.transport = paramiko.Transport(sock)
            self.transport.start_client(timeout=TIMEOUT)
        except (OSError, paramiko.SSHException) as exc:
            raise RemoteError("connect_failed", str(exc) or exc.__class__.__name__) from exc
        try:
            self.host_key = fingerprint(self.transport.get_remote_server_key())
            if cfg.host_key and cfg.host_key != self.host_key:
                raise RemoteError(
                    "host_key_mismatch",
                    f"The server's host key changed (expected {cfg.host_key}, got {self.host_key})",
                )
            try:
                if cfg.auth_method == "key":
                    self.transport.auth_publickey(cfg.username, load_private_key(cfg.private_key))
                else:
                    self.transport.auth_password(cfg.username, cfg.password)
            except paramiko.AuthenticationException as exc:
                raise RemoteError("login_failed", str(exc) or "Authentication failed") from exc
            try:
                self.sftp = paramiko.SFTPClient.from_transport(self.transport)
            except paramiko.SSHException:
                self.sftp = None  # no SFTP subsystem: classic scp
            self.dir = self._prepare_dir(cfg.remote_path)
        except RemoteError:
            self.transport.close()
            raise
        except (OSError, paramiko.SSHException) as exc:
            self.transport.close()
            raise RemoteError("remote_error", str(exc)) from exc

    # -- helpers

    def _prepare_dir(self, path: str) -> str:
        path = (path or ".").strip() or "."
        if not self.cfg.create_dir:
            return path
        if self.sftp is not None:
            current = "/" if path.startswith("/") else ""
            for part in [p for p in path.split("/") if p and p != "."]:
                current = posixpath.join(current, part) if current else part
                try:
                    self.sftp.stat(current)
                except FileNotFoundError:
                    self.sftp.mkdir(current)
            return path
        self._exec(f"mkdir -p -- {shlex.quote(path)}")
        return path

    def _path(self, name: str) -> str:
        return posixpath.join(self.dir, _safe_name(name))

    def _exec(self, command: str, stdin: bytes = b"") -> bytes:
        chan = self.transport.open_session(timeout=TIMEOUT)
        try:
            chan.settimeout(TIMEOUT)
            chan.exec_command(command)
            if stdin:
                chan.sendall(stdin)
            chan.shutdown_write()
            out = bytearray()
            err = bytearray()
            while True:
                data = chan.recv(65536)
                if not data:
                    break
                out += data
            while chan.recv_stderr_ready():
                err += chan.recv_stderr(65536)
            status = chan.recv_exit_status()
        finally:
            chan.close()
        if status != 0:
            raise RemoteError("remote_error", err.decode(errors="replace").strip() or f"exit status {status}")
        return bytes(out)

    @staticmethod
    def _ack(chan: paramiko.Channel) -> None:
        reply = chan.recv(1)
        if reply != b"\x00":
            message = reply[1:] if reply else b""
            while not message.endswith(b"\n"):
                chunk = chan.recv(1)
                if not chunk:
                    break
                message += chunk
            raise RemoteError("transfer_failed", message.decode(errors="replace").strip() or "scp failed")

    def _wrap(self, fn, *args):
        try:
            return fn(*args)
        except FileNotFoundError as exc:
            raise RemoteError("not_found", str(exc)) from exc
        except RemoteError:
            raise
        except (OSError, paramiko.SSHException) as exc:
            raise RemoteError("transfer_failed", str(exc) or exc.__class__.__name__) from exc

    # -- operations

    def list(self) -> list[RemoteFile]:
        if self.sftp is not None:
            entries = self._wrap(self.sftp.listdir_attr, self.dir)
            return [RemoteFile(e.filename, e.st_size) for e in entries if not stat.S_ISDIR(e.st_mode or 0)]
        out = self._wrap(self._exec, f"ls -1 -- {shlex.quote(self.dir)}")
        return [RemoteFile(n) for n in out.decode(errors="replace").splitlines() if n]

    def upload(self, name: str, data: bytes) -> None:
        path = self._path(name)
        if self.sftp is not None:
            partial = path + ".part"
            self._wrap(self.sftp.putfo, io.BytesIO(data), partial)
            self._wrap(self.sftp.posix_rename, partial, path)
            return
        self._wrap(self._scp_put, path, data)

    def _scp_put(self, path: str, data: bytes) -> None:
        chan = self.transport.open_session(timeout=TIMEOUT)
        try:
            chan.settimeout(TIMEOUT)
            chan.exec_command(f"scp -t -- {shlex.quote(path)}")
            self._ack(chan)
            chan.sendall(f"C0600 {len(data)} {posixpath.basename(path)}\n".encode())
            self._ack(chan)
            chan.sendall(data)
            chan.sendall(b"\x00")
            self._ack(chan)
        finally:
            chan.close()

    def download(self, name: str) -> bytes:
        path = self._path(name)
        if self.sftp is not None:
            buf = io.BytesIO()
            self._wrap(self.sftp.getfo, path, buf)
            return buf.getvalue()
        return self._wrap(self._scp_get, path)

    def _scp_get(self, path: str) -> bytes:
        chan = self.transport.open_session(timeout=TIMEOUT)
        try:
            chan.settimeout(TIMEOUT)
            chan.exec_command(f"scp -f -- {shlex.quote(path)}")
            chan.sendall(b"\x00")
            header = b""
            while not header.endswith(b"\n"):
                chunk = chan.recv(1)
                if not chunk:
                    raise RemoteError("not_found", f"{path} not found")
                header += chunk
            if header[:1] in (b"\x01", b"\x02"):
                raise RemoteError("not_found", header[1:].decode(errors="replace").strip())
            size = int(header.split(b" ")[1])
            chan.sendall(b"\x00")
            data = bytearray()
            while len(data) < size:
                chunk = chan.recv(min(65536, size - len(data)))
                if not chunk:
                    raise RemoteError("transfer_failed", "Connection closed during download")
                data += chunk
            self._ack(chan)
            chan.sendall(b"\x00")
            return bytes(data)
        finally:
            chan.close()

    def delete(self, name: str) -> None:
        path = self._path(name)
        if self.sftp is not None:
            self._wrap(self.sftp.remove, path)
        else:
            self._wrap(self._exec, f"rm -f -- {shlex.quote(path)}")

    def close(self) -> None:
        try:
            if self.sftp is not None:
                self.sftp.close()
        finally:
            self.transport.close()


def connect(cfg: TargetConfig) -> Remote:
    if cfg.protocol not in PROTOCOLS:
        raise RemoteError("invalid_protocol", f"Unknown protocol {cfg.protocol}")
    if not cfg.host:
        raise RemoteError("connect_failed", "No host configured")
    return ScpRemote(cfg) if cfg.protocol == "scp" else FtpRemote(cfg)
