# config_loader.py
# Finds, creates, and loads the user config.toml file for remote server access

import sys
import tomllib
from importlib.resources import files
from mcp_client_console.terminal import clear_terminal, welcome_banner, italic_text, header_text
from pathlib import Path
from platformdirs import user_config_dir
from urllib.parse import urlparse

APP_NAME = "mcp-client-console"


### -------
### CLI GUI
### -------
RESET = "\033[0m"
BOLD_RED = "\033[1;31m"

def error_text(text: str) -> str:
    """Styles passed string to fancy error text formatting"""
    return f"\n{BOLD_RED}ERROR: {text}{RESET}"


### ----------
### MAIN LOGIC
### ----------
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
        clear_terminal()
        print(welcome_banner())
        print("_"*50)
        print(header_text("\n[ CONFIG CREATED ]"))
        print("\nfilepath:")
        print(italic_text(f"{config_file}"))
        print(f"\n{header_text("Open config file,")} review and edit accordingly, save, and run the package again to begin...")
        print("_"*50)
        print("\n")
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
        problem = _url_problem(server_choice) # no menu to return to on this path, so a bad URL must stop here
        if problem:
            clear_terminal()
            print(welcome_banner())
            print("_" * 50)
            print(error_text(problem))
            print(italic_text(f"\nConfig file: {config_path()}\n"))
            print("Fix the URL, save, and run the package again...")
            print("_" * 50)
            print("\n")
            sys.exit(1)
        return server_choice

    error_message = ""
    notice_message = "" # like error_message, held (not printed) so it survives the next clear_terminal()
    still_choosing = True
    while still_choosing == True:
        clear_terminal()
        print(welcome_banner())
        print(italic_text("edit available servers anytime in user .config directory"))
        print("_" * 50)
        print(f"\n[ AVAILABLE SERVERS ]\n")
        for i, server in enumerate(available_servers, start=1):
            print(f"[ {i} ] {server['name']} @ {server['url']}")
        print("_" * 50)

        if notice_message:
            print(notice_message)

        if error_message:
            print(error_text(error_message))

        print("\nTo connect to a server, enter number below... ")
        try:
            server_choice = input(f">: ").strip()
        except (KeyboardInterrupt, EOFError): # Ctrl+C / Ctrl+D at the menu leaves the app
            server_choice = "quit"
        print("_" * 50)

        ### the banner offers these commands, so they must answer here too - before any server is connected
        if server_choice.lower() in ("quit", "exit"):
            clear_terminal()
            print(welcome_banner())
            print(italic_text("\nGoodbye...\n"))
            sys.exit(0)

        if server_choice.lower() in ("config", "configuration"):
            error_message = ""
            notice_message = (
                f"{header_text('[ CONFIG FILE ]')}\n\n"
                f"{italic_text(str(config_path()))}\n\n"
                "Add, remove, or re-address servers there, then run the package again..."
            )
            continue

        if server_choice.lower() == "tools":
            error_message = ""
            notice_message = italic_text("\nTools belong to a server - connect to one first, then type 'tools'.")
            continue

        if not server_choice: # bare Enter is a no-op, leaves any notice on screen
            continue

        notice_message = "" # any real selection attempt clears an old notice

        if not server_choice.isdigit():
            error_message = ("\nEnter a server number listed above, or type 'config' or 'quit'.")
            continue

        server_number = int(server_choice) - 1 # because Python indexes start at 0
        if server_number < 0 or server_number >= len(available_servers):
            error_message = ("\nEnter a server number listed above.") # assigned (not printed) so it survives clear_terminal() on the next redraw
            continue

        server_choice = available_servers[server_number]
        problem = _url_problem(server_choice)
        if problem:
            error_message = problem
            continue
        return server_choice

def _url_problem(server: dict) -> str | None:
    """
        Automated catch if Config file's URL does not contain /mcp or https://
    """
    url = server["url"]
    parts = urlparse(url)
    if not parts.scheme or not parts.netloc:
        return f"\n{url}\nis not a valid URL. Include http:// or https://"
    if not parts.path.rstrip("/"):
        return f"\n{url}\nis missing the server's mount path (e.g. /mcp)."
    if parts.scheme != "https":
        on_this_machine = parts.hostname in ("127.0.0.1", "localhost", "::1")
        if not (on_this_machine or server.get("allow_insecure", False)):
            return (
                f"\n{url}\nwould send the bearer token unencrypted. Please use https:// or OVERRIDE by setting allow_insecure on this [[server]] settings in Config."
            )


if __name__ == "__main__":
    config = config_load()
    server = get_active_server(config)
    print("_" * 50)
    print(f"Server Config Loaded.")
    print(f"Active Server: {server['name']} @ {server['url']}")



