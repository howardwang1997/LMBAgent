import os
import tempfile
from pathlib import Path
from functools import lru_cache
from typing import Optional

from dotenv import load_dotenv


def _load_env():
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        load_dotenv(env_path)


def _get_creds():
    _load_env()
    server = os.getenv("SMB_SERVER", "")
    user = os.getenv("SMB_USERNAME", "")
    pwd = os.getenv("SMB_PASSWORD", "")
    if "@" in user:
        user = user.split("@", 1)[0]
    return server, user, pwd


def _connect():
    from impacket.smbconnection import SMBConnection

    server, user, pwd = _get_creds()
    if not server:
        raise RuntimeError("SMB_SERVER not set in .env")
    conn = SMBConnection(server, server, sess_port=445)
    conn.login(user, pwd, domain="")
    return conn


def list_shares() -> list[dict]:
    conn = _connect()
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


def list_dir(share: str, path: str = "") -> list[dict]:
    conn = _connect()
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


def download_file(share: str, remote_path: str, local_path: Optional[str] = None) -> str:
    conn = _connect()
    try:
        if local_path is None:
            local_path = os.path.join(tempfile.gettempdir(), "smb_downloads", Path(remote_path).name)
        os.makedirs(os.path.dirname(local_path), exist_ok=True)
        with open(local_path, "wb") as f:
            conn.getFile(share, remote_path.replace("/", "\\\\"), f.write)
        return local_path
    finally:
        conn.close()


def walk(share: str, path: str = "", max_depth: int = 2, _depth: int = 0) -> list[dict]:
    if _depth > max_depth:
        return []
    entries = list_dir(share, path)
    result = []
    for e in entries:
        full = f"{path}/{e['name']}" if path else e["name"]
        result.append({**e, "path": full})
        if e["is_dir"]:
            result.extend(walk(share, full, max_depth, _depth + 1))
    return result
