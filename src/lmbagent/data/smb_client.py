import os
import re
import tempfile
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv


_DEFAULT_SERVER = "10.156.212.11"


def _load_env():
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        load_dotenv(env_path)
        global _DEFAULT_SERVER
        _DEFAULT_SERVER = os.getenv("SMB_SERVER", _DEFAULT_SERVER)


_load_env()


def parse_unc_path(path_str: str) -> Optional[tuple[str, str, str]]:
    """Parse a UNC or SMB path into (server, share, relative_path).

    Accepts:
      \\\\server\\share\\path\\to\\file.xlsx
      smb://server/share/path/to/file.xlsx
      //server/share/path/to/file.xlsx
    Returns None if not an SMB path.
    """
    path_str = path_str.strip().strip('"').strip("'")
    path_str_fwd = path_str.replace("\\", "/")

    if path_str_fwd.startswith("smb://"):
        path_str_fwd = path_str_fwd[len("smb://"):]
    elif path_str_fwd.startswith("//"):
        path_str_fwd = path_str_fwd[2:]
    else:
        return None

    parts = [p for p in path_str_fwd.split("/") if p]
    if len(parts) < 2:
        return None

    server = parts[0]
    share = parts[1]
    rel = "/".join(parts[2:])
    return server, share, rel


def _split_user(username: str) -> tuple[str, str]:
    """Split 'domain\\user' or 'user@domain' into (user, domain)."""
    if "\\" in username:
        domain, user = username.rsplit("\\", 1)
        return user, domain
    if "@" in username:
        user, domain = username.split("@", 1)
        return user, domain
    return username, ""


def _connect(
    server: str = "",
    username: str = "",
    password: str = "",
):
    from impacket.smbconnection import SMBConnection

    if not server:
        server = _DEFAULT_SERVER
    user, domain = _split_user(username)
    conn = SMBConnection(server, server, sess_port=445)
    conn.login(user, password, domain=domain)
    return conn


def smb_login(
    server: str,
    username: str,
    password: str,
) -> bool:
    try:
        conn = _connect(server, username, password)
        conn.close()
        return True
    except Exception:
        return False


def list_shares(
    server: str = "",
    username: str = "",
    password: str = "",
) -> list[dict]:
    conn = _connect(server, username, password)
    try:
        result = []
        for s in conn.listShares():
            name = str(s["shi1_netname"]).strip().rstrip("\x00")
            stype = int(s["shi1_type"])
            remark = str(s["shi1_remark"]).strip().rstrip("\x00")
            if not (stype & 0x80000000):
                result.append({"name": name, "type": stype, "remark": remark})
        return result
    finally:
        conn.close()


def list_dir(
    share: str,
    path: str = "",
    server: str = "",
    username: str = "",
    password: str = "",
) -> list[dict]:
    conn = _connect(server, username, password)
    try:
        pattern = (path.strip("/") + "/*").lstrip("/")
        if pattern == "*":
            pattern = "*"
        entries = conn.listPath(share, pattern.replace("/", "\\\\"))
        result = []
        for e in entries:
            name = e.get_longname()
            if name in (".", ".."):
                continue
            result.append({
                "name": name,
                "is_dir": bool(e.is_directory()),
                "size": e.get_filesize(),
            })
        return result
    finally:
        conn.close()


def download_file(
    share: str,
    remote_path: str,
    local_path: Optional[str] = None,
    server: str = "",
    username: str = "",
    password: str = "",
) -> str:
    conn = _connect(server, username, password)
    try:
        if local_path is None:
            local_path = os.path.join(
                tempfile.gettempdir(), "smb_downloads", Path(remote_path).name
            )
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            conn.getFile(share, remote_path.replace("/", "\\\\"), f.write)
        return local_path
    finally:
        conn.close()


def walk(
    share: str,
    path: str = "",
    max_depth: int = 2,
    server: str = "",
    username: str = "",
    password: str = "",
    _depth: int = 0,
) -> list[dict]:
    if _depth > max_depth:
        return []
    entries = list_dir(share, path, server, username, password)
    result = []
    for e in entries:
        full = f"{path}/{e['name']}" if path else e["name"]
        result.append({**e, "path": full})
        if e["is_dir"]:
            result.extend(
                walk(share, full, max_depth, server, username, password, _depth + 1)
            )
    return result
