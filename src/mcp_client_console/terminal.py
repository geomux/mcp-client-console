# terminal.py
# Terminal GUI and text handling kept neat and tidy here for import elsewhere

import os

### ---------------
### --- CLI GUI ---
### ---------------

ITALIC = "\033[3m"
RESET = "\033[0m"
BOLD_GREEN = "\033[1;32m"
BOLD_BLUE = "\033[1;34m"
BOLD_RED = "\033[1;31m"
BRIGHT_MAGENTA = "\033[95m"
DIM = "\033[2m"

WIDTH = 50 # constant for max width of things in terminal

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

def italic_text(text: str) -> str:
    """Styles passed string to a fancy italic formatting"""
    return f"\n{ITALIC}{text}{RESET}"



### ----------------------
### --- WELCOME BANNER ---
### ----------------------


def _row(plain_text: str, color: str = "") -> str:
    """Centers plain_text within WIDTH, colors it, then wraps in box borders.

    Padding math runs on the uncolored string so ANSI escape codes
    never get counted as visible characters.
    """
    centered = plain_text.center(WIDTH)
    styled = f"{color}{centered}{RESET}" if color else centered
    return f"{BOLD_BLUE}║{RESET}{styled}{BOLD_BLUE}║{RESET}"


def _row_left(plain_text: str, color: str = "") -> str:
    """Left-aligns plain_text within WIDTH (1-space indent), colors it, wraps in borders."""
    padded = f" {plain_text}".ljust(WIDTH)
    styled = f"{color}{padded}{RESET}" if color else padded
    return f"{BOLD_BLUE}║{RESET}{styled}{BOLD_BLUE}║{RESET}"


def welcome_banner() -> str:
    """Returns a styled ASCII welcome banner for MCP-CLIENT-CONSOLE startup."""
    top = f"{BOLD_BLUE}╔{'═' * WIDTH}╗{RESET}"
    bottom = f"{BOLD_BLUE}╚{'═' * WIDTH}╝{RESET}"

    lines = [
        top,
        _row(""),
        _row("MCP-CLIENT-CONSOLE", color=BOLD_GREEN),
        _row(""),
        bottom,
    ]
    lines.append(f"{DIM}type 'quit' to disconnect{RESET}\n")
    return "\n".join(lines)


