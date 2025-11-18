import json
import os
from dataclasses import dataclass, asdict
from typing import Optional, Dict, List


DEFAULT_CONFIG_PATH = os.path.join(os.getcwd(), "config.json")
DOTENV_PATH = os.path.join(os.getcwd(), ".env")


@dataclass
class Config:
    music_root: str
    # Optional Chromium flags for Qt WebEngine, space-separated
    webengine_flags: Optional[str] = None


def _default_music_root() -> str:
    userprofile = os.environ.get("USERPROFILE") or os.path.expanduser("~")
    default = os.path.join(userprofile, "Music")
    return default


def load_config(path: str = DEFAULT_CONFIG_PATH) -> Config:
    if not os.path.exists(path):
        cfg = Config(music_root=_default_music_root(), webengine_flags=None)
        save_config(cfg, path)
        return cfg
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    # Back-compat: ignore any legacy secret keys in config.json
    return Config(
        music_root=data.get("music_root") or _default_music_root(),
        webengine_flags=data.get("webengine_flags"),
    )


def save_config(cfg: Config, path: str = DEFAULT_CONFIG_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(cfg), f, indent=2)


def get_youtube_api_key() -> Optional[str]:
    return os.environ.get("YOUTUBE_API_KEY")


def get_soundcloud_client_id() -> Optional[str]:
    return os.environ.get("SOUNDCLOUD_CLIENT_ID")


# --- .env helpers ---
def _read_env_lines(path: str = DOTENV_PATH) -> List[str]:
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as f:
        return f.read().splitlines()


def _write_env_lines(lines: List[str], path: str = DOTENV_PATH) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + ("\n" if lines and not lines[-1].endswith("\n") else ""))


def set_env_vars(updates: Dict[str, Optional[str]], path: str = DOTENV_PATH) -> None:
    # Load existing
    lines = _read_env_lines(path)
    mapping: Dict[str, str] = {}
    order: List[str] = []
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            order.append(line)
            continue
        key, val = line.split("=", 1)
        mapping[key] = val
        order.append(key)
    # Apply updates (None clears the key)
    for k, v in updates.items():
        if v is None or v == "":
            mapping.pop(k, None)
            if k not in order:
                order.append(k)  # to remove if present in rebuild
        else:
            mapping[k] = v
            if k not in order:
                order.append(k)
    # Rebuild lines, preserving unknown/comment lines
    new_lines: List[str] = []
    for token in order:
        if not token or token.lstrip().startswith("#") or "=" in token:
            # original non-kv line
            if token and token.lstrip().startswith("#"):
                new_lines.append(token)
            elif "=" in token:
                k = token.split("=", 1)[0]
                if k in mapping:
                    new_lines.append(f"{k}={mapping[k]}")
                    mapping.pop(k, None)
                # else drop removed key
            else:
                new_lines.append(token)
        else:
            # token is a key name from order
            k = token
            if k in mapping:
                new_lines.append(f"{k}={mapping[k]}")
                mapping.pop(k, None)
    for k, v in mapping.items():
        new_lines.append(f"{k}={v}")
    _write_env_lines(new_lines, path)


def set_youtube_api_key(value: Optional[str]) -> None:
    set_env_vars({"YOUTUBE_API_KEY": value})


def set_soundcloud_client_id(value: Optional[str]) -> None:
    set_env_vars({"SOUNDCLOUD_CLIENT_ID": value})
