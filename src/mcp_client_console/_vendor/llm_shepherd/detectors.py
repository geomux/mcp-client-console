# detectors.py
# Pure analysis helpers that spot doomed or repeated tool calls BEFORE they waste a round.
# No state, no imports - every function takes strings in and returns findings out.


### ------------------------------
### --- SHELL OPERATOR SCANNER ---
### ------------------------------

# Operators that require a shell to mean anything. The remote server runs commands
# with subprocess and NO shell, so these arrive as literal text and always fail.
_HARD_OPERATORS = {"|", ">", "<", ";", "&", "`"}

def shell_operators(command: str) -> list[str]:
    """Return shell operators found OUTSIDE quotes in a command string.
    command: the raw command line the model wants run_command to execute.
    Quoted operators (grep "a|b") are legitimate literal arguments and are NOT flagged.
    Soft glob characters (* ? ~ $VAR) are NOT flagged here - see glob_characters().
    """
    found = []
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        char = command[i]
        if in_single:
            if char == "'":
                in_single = False
        elif in_double:
            if char == '"':
                in_double = False
        elif char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char == "$" and i + 1 < len(command) and command[i + 1] == "(":
            found.append("$(")
        elif char in _HARD_OPERATORS:
            found.append(char)
        i += 1
    ordered = []  # dedupe while preserving first-seen order
    for operator in found:
        if operator not in ordered:
            ordered.append(operator)
    return ordered


def glob_characters(command: str) -> list[str]:
    """Return soft glob/expansion characters found OUTSIDE quotes (* ? ~ $).
    command: the raw command line.
    These are only WARNED about, never blocked: find -name *.py is valid usage
    because find does its own pattern matching without a shell.
    """
    found = []
    in_single = False
    in_double = False
    i = 0
    while i < len(command):
        char = command[i]
        if in_single:
            if char == "'":
                in_single = False
        elif in_double:
            if char == '"':
                in_double = False
        elif char == "'":
            in_single = True
        elif char == '"':
            in_double = True
        elif char in "*?~$":
            if not (char == "$" and i + 1 < len(command) and command[i + 1] == "("):
                found.append(char)
        i += 1
    ordered = []
    for char in found:
        if char not in ordered:
            ordered.append(char)
    return ordered


### --------------------------
### --- CONFUSION DETECTOR ---
### --------------------------

def glob_confusion(raw_result: str) -> bool:
    """Detect a result that smells like the no-shell trap AFTER execution.
    raw_result: raw tool output text.
    Example: ls -d /home/* ran without a shell, so ls was handed the literal
    argument '/home/*' and printed "cannot access '/home/*': No such file...".
    """
    if not raw_result:
        return False
    lowered = raw_result.lower()
    complained = ("cannot access" in lowered) or ("no such file or directory" in lowered)
    if not complained:
        return False
    return any(char in raw_result for char in ("*", "~", "$", "|"))


### ----------------------
### --- REPEAT SCORING ---
### ----------------------

def near_repeat(text_a: str, text_b: str) -> float:
    """Jaccard similarity of two strings' token sets (0.0 - 1.0).
    text_a: first normalized call string.
    text_b: second normalized call string.
    Used to warn about nearly-identical calls that dodge the exact-repeat check.
    """
    tokens_a = set(text_a.split())
    tokens_b = set(text_b.split())
    if not tokens_a or not tokens_b:
        return 0.0
    return len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
