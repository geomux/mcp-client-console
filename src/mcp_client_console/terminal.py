# terminal.py
# Terminal GUI and text handling kept neat and tidy here for import elsewhere


### ---------------
### --- CLI GUI ---
### ---------------

RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
BOLD_BLUE = "\033[1;34m"
BOLD_RED = "\033[1;31m"
BRIGHT_MAGENTA = "\033[95m"
DIM = "\033[2m"

PROMPT_KEY = f"{BOLD_GREEN}>: {RESET}" # colorful UI settings for console chat prompt key.


def clear_terminal():
    os.system("cls" if os.name == "nt" else "clear")

def header_text(text: str) -> str:
    """Styles passed string to fancy header formatting"""
    return f"{BOLD_BLUE}{text}{RESET}"

def model_text(text: str) -> str:
    """Styles passed string to fancy model text formatting"""
    return f"\n{BRIGHT_MAGENTA}MODEL: {text}{RESET}"

def subheader_text(text: str) -> str:
    return f"{BOLD_GREEN}{text}{RESET}"

def error_text(text: str) -> str:
    """Styles passed string to fancy error text formatting"""
    return f"\n{BOLD_RED}ERROR: {text}{RESET}"

def tool_text(text: str) -> str:
    """Styles text showing off a tool the model is running"""
    return f"{DIM} -> {text}{RESET}"


