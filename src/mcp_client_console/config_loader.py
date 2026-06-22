# config_loader.py
# Finds, creates, and loads the user config.toml file for remote server access

import sys
import tomllib
from pathlib import Path
from importlib.resources import files
from platformdirs import user_config_dir

APP_NAME = "mcp-client-console"

def config_path() -> Path:
    """Defines destination filepath for Config File"""
    folder = Path(user_config_dir(APP_NAME, appauthor=False)) # appauthor=False stops Windows from adding an extra folder.
    file = folder / "config.toml"
    return file

def config_create() -> Path:
    """Creates Config File (from template) if does not exist"""
    config_file = config_path()
    if not config_file.exists():
        config_file.parent.mkdir(parents=True, exist_ok=True)
        template = files("mcp_client_console").joinpath("config_default.toml")
        text = template.read_text(encoding="utf-8-sig")
        config_file.write_text(text, encoding="utf-8-sig")
            # this (encoding="utf-8-sig") argument to strip BOM (byte order mark) from config file if present.
            # some programs save a BOM on the top of the file. BOM can be unexpected and cause crashes.
        config_file.chmod(0o600) # owner access only, security concerns as token lives in this file
        print("_"*50)
        print("\n[ CONFIG CREATED ]")
        print"\nfilepath:"
        print(f"\n{config_file}")
        print(f"\nOpen config file, review and edit accordingly, save, and run the package again to begin.")
        print("_"*50)
        sys.exit(1)
    return config_file

def config_load() -> dict:
    """Load settings from Config File into Python dictionary"""
    config_file = config_create()
    config_text = config_file.read_text(encoding="utf-8-sig")
    config_dictionary = tomllib.loads(config_text)
    return config_dictionary


def get_active_server(config_dictionary: dict) -> dict:
    """User chooses an active server from Config File"""
    available_servers = config_dictionary["server"]
    if len(available_servers) == 1:
        server_choice = available_servers[0]
        return server_choice

    still_choosing = True
    while still_choosing == True:
        print("_" * 50)
        print(f"\n[ AVAILABLE SERVERS ]\n")
        for i, server in enumerate(available_servers, start=1):
            print(f"[ {i} ] {server['name']} @ {server['url']}")
        print("_" * 50)
        print(f"\nTo connect to a server, enter number below... ")
        server_choice = input(f">: ").strip()
        print("_" * 50)
        if server_choice.isdigit() == False:
            print(f"\nEnter a server number listed above.")
            continue

        server_number = int(server_choice) - 1 # because Python indexes start at 0
        if server_number < 0 or server_number >= len(available_servers):
            print(f"\nEnter a server number listed above.")
            continue
        return available_servers[server_number]

if __name__ == "__main__":
    config = config_load()
    server = get_active_server(config)
    print("_" * 50)
    print(f"Server Config Loaded.")
    print(f"Active Server: {server['name']} @ {server['url']}")



