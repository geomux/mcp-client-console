# config_loader.py
# Finds, creates, and loads the user config.toml file

import sys
import tomllib
from pathlib import Path
from importlib.resources import files
from platformdirs import user_config_dir

APP_NAME = "mcp-client-console"

def config_path() -> Path:
    folder = Path(user_config_dir(APP_NAME, appauthor=False)) # appauthor=False stops Windows from adding an extra folder.
    file = folder / "config.toml"
    return file

def config_create() -> Path:
    config_file = config_path()
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        template = files("mcp_client_console").joinpath("default_config.toml")
        text = template.read_text()
        config_file.write_text(text)
        config_file.chmod(0o600) # owner access only, security concerns as token lives in this file
        print(f"Created config: {config_file}")
        print(f"Edit the values, save, and run the package again to begin.")
        sys.exit(1)
    return config_file

def config_load() -> dict: # returns dictionary because tomllib.load() converts config.toml into Python dictionary
    config_file = config_create()
    with open(config_file, "rb") as f: # note that tomllib needs to read in binary, hence "rb"
        config = tomllib.load(f)
    return config

def get_active_server(config: dict) -> dict:
    servers = config["server"]
    if len(servers) == 1:
        active_server = servers[0]
        return active_server
    print(f"Servers in config: ")
    for i, server in enumerate(servers, start=1):
        print(f"{i}. {server['name']} @ {server['url']}")
    active_server = input(f"Connect to a server. Enter number now: ")
    active_server = active_server.strip()
    server_number = int(active_server) - 1 # because Python indexes start at 0
    if server_number < 0 or server_number >= len(servers):
        print("Enter a listed server number.")
        sys.exit(1)
    return servers[server_number]

if __name__ == "__main__":
    config = config_load()
    server = get_active_server(config)
    print(f"Server Config Loaded.")
    print(f"Active Server: {server['name']}, " @ ", {server['url']}")



