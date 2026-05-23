"""Introspect flight script CLI arguments by running ``<script> --help``.

We deliberately do NOT import the script — flight scripts have heavy side
effects (loading torch, killing mavsdk_server, etc.). Running ``--help`` as a
subprocess and parsing the output is safe and gives us a complete picture.

Public entrypoints:
    list_flight_scripts(scripts_dir) -> list[ScriptInfo]
    list_worlds(worlds_dir)          -> list[WorldInfo]
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from typing import Optional

# Default to whatever Python is running the backend. On Mac/Linux this is
# usually python3; on Windows native it's python.exe. Avoids "python3 not
# found" when the same interpreter is right there.
DEFAULT_PYTHON_BIN = sys.executable or "python3"


@dataclass
class ScriptArg:
    """One CLI argument the script accepts."""
    name: str             # e.g. "side" (no leading dashes; "_" preserved)
    flag: str             # e.g. "--side"
    type: str             # "str" | "int" | "float" | "bool" | "choice"
    default: Optional[object] = None
    help: str = ""
    choices: Optional[list[str]] = None
    required: bool = False


@dataclass
class ScriptInfo:
    name: str             # filename, e.g. "demo_flight_v2.py"
    path: str             # absolute path
    description: str = ""    # first sentence of help / module docstring
    args: list[ScriptArg] = field(default_factory=list)
    parse_error: Optional[str] = None  # populated if --help failed


@dataclass
class CameraInfo:
    """A streamable camera discovered in a world SDF.

    `name` is the bare token the headless launcher accepts as a flag
    (e.g. ``fixed`` -> ``--fixed``). The full model name in the SDF is
    ``<name>_cam`` (e.g. ``fixed_cam``); we strip the suffix so the API
    surface mirrors the launcher flags users would type.
    """
    name: str             # launcher flag stem, e.g. "fixed", "center"
    label: str            # human-readable, e.g. "Fixed", "Center"
    model: str            # underlying model used, e.g. "mono_cam_hd"


@dataclass
class WorldInfo:
    name: str             # without extension, e.g. "drone_garage_pigeon_3d"
    path: str             # absolute path to .sdf
    cameras: list[CameraInfo] = field(default_factory=list)


# ---- world enumeration ----------------------------------------------------

# Model URIs whose included instances are streamable cameras. The headless
# launcher (scripts/shell/launch_with_stream.sh) only knows how to point a
# WebRTC worker at these — drone-onboard cameras are not streamable from the
# webapp side and don't belong in the dropdown.
_STREAMABLE_CAMERA_MODELS = {"mono_cam_hd", "mono_cam"}

# Launcher flag stems we know about, in display order.
_KNOWN_CAMERA_FLAGS = ("fixed", "center")


def _parse_world_cameras(sdf_path: str) -> list[CameraInfo]:
    """Return streamable cameras included in a world SDF.

    Looks for ``<include>`` elements that pull in a camera model and whose
    ``<name>`` ends in ``_cam`` (the convention used in our worlds). The
    bare stem (everything before ``_cam``) becomes the launcher flag — e.g.
    ``fixed_cam`` -> launcher accepts ``--fixed``.

    Parser is lenient on purpose: an SDF that can't be parsed just returns
    an empty list rather than failing the whole /api/sim/options route.
    """
    try:
        tree = ET.parse(sdf_path)
    except (ET.ParseError, FileNotFoundError, OSError):
        return []

    root = tree.getroot()
    seen: dict[str, CameraInfo] = {}
    for include in root.iter("include"):
        uri_el = include.find("uri")
        name_el = include.find("name")
        if uri_el is None or name_el is None:
            continue
        uri = (uri_el.text or "").strip()
        name = (name_el.text or "").strip()
        if not uri or not name or not name.endswith("_cam"):
            continue
        # uri looks like "model://mono_cam_hd"
        model = uri.rsplit("/", 1)[-1]
        if model not in _STREAMABLE_CAMERA_MODELS:
            continue
        stem = name[: -len("_cam")]
        if not stem or stem in seen:
            continue
        seen[stem] = CameraInfo(
            name=stem,
            label=stem.replace("_", " ").title(),
            model=model,
        )

    # Sort by the known launcher-flag display order; unknowns trail alphabetically.
    known = [seen[k] for k in _KNOWN_CAMERA_FLAGS if k in seen]
    extras = sorted(
        (cam for k, cam in seen.items() if k not in _KNOWN_CAMERA_FLAGS),
        key=lambda c: c.name,
    )
    return known + extras


def list_worlds(worlds_dir: str) -> list[WorldInfo]:
    """Return every ``*.sdf`` in ``worlds_dir``, sorted by name, with
    streamable cameras parsed out of each SDF."""
    if not os.path.isdir(worlds_dir):
        return []
    out: list[WorldInfo] = []
    for fname in sorted(os.listdir(worlds_dir)):
        if fname.endswith(".sdf"):
            path = os.path.join(worlds_dir, fname)
            out.append(WorldInfo(
                name=fname[:-4],
                path=path,
                cameras=_parse_world_cameras(path),
            ))
    return out


# ---- script enumeration ---------------------------------------------------

# Lines we ignore when extracting the per-script description from --help.
_HELP_BOILERPLATE = re.compile(
    r"^(usage:|options:|positional arguments:|optional arguments:|"
    r"-h, --help|show this help message and exit|examples:)",
    re.IGNORECASE,
)


def list_flight_scripts(scripts_dir: str,
                        python_bin: str = DEFAULT_PYTHON_BIN,
                        timeout_s: float = 8.0,
                        fast: bool = False) -> list[ScriptInfo]:
    """Return every ``*.py`` in ``scripts_dir``, with parsed argparse metadata.

    For each script we run ``python3 <script> --help`` (in a subprocess) and
    parse its output. Scripts without argparse simply return no args (or fail
    quickly, which we also report).
    """
    if not os.path.isdir(scripts_dir):
        return []

    out: list[ScriptInfo] = []
    for fname in sorted(os.listdir(scripts_dir)):
        if not fname.endswith(".py") or fname.startswith("_"):
            continue
        full = os.path.join(scripts_dir, fname)
        if fast:
            info = ScriptInfo(
                name=fname,
                path=full,
                description=_extract_module_docstring(full),
            )
            out.append(info)
            continue
        info = _introspect_script(full, python_bin=python_bin, timeout_s=timeout_s)
        info.name = fname
        out.append(info)
    return out


def _introspect_script(path: str, python_bin: str, timeout_s: float) -> ScriptInfo:
    info = ScriptInfo(name=os.path.basename(path), path=path)

    # Fast path: skip --help entirely for scripts that don't use argparse.
    # Running --help on such a script doesn't fail -- Python ignores the flag
    # and the script's __main__ block starts running (often connecting to
    # MAVSDK), which then blocks for the full timeout. A simple text scan
    # avoids that wasted wait.
    if not _script_uses_argparse(path):
        info.description = _extract_module_docstring(path)
        return info

    try:
        proc = subprocess.run(
            [python_bin, path, "--help"],
            capture_output=True, text=True, timeout=timeout_s,
        )
    except subprocess.TimeoutExpired:
        info.parse_error = f"--help timed out after {timeout_s}s"
        return info
    except FileNotFoundError as e:
        info.parse_error = f"interpreter not found ({python_bin}): {e}"
        return info
    except Exception as e:
        info.parse_error = f"failed to run --help: {e}"
        return info

    # argparse writes help to stdout on success and to stderr on parse error.
    text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
    if not text.strip():
        info.parse_error = "no output from --help (script may not use argparse)"
        return info

    # If the script raised before parse_args could run, --help output is a
    # traceback. Don't pretend that's an argparse description.
    if "Traceback (most recent call last)" in text or proc.returncode != 0:
        first_line = next((l for l in text.strip().splitlines() if l.strip()), "")
        info.parse_error = f"script error during --help: {first_line[:120]}"
        info.description = _extract_module_docstring(path)
        return info

    info.description = _extract_description(text)
    info.args = _parse_argparse_options(text)
    return info


def _extract_description(help_text: str) -> str:
    """Pull the first descriptive non-boilerplate line out of the help block."""
    lines = [l.rstrip() for l in help_text.splitlines()]
    # argparse format: usage line, blank, description (possibly multi-line),
    # blank, "options:" / "positional arguments:" / etc.
    in_usage = False
    desc: list[str] = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            if desc:
                break
            continue
        if stripped.lower().startswith("usage:"):
            in_usage = True
            continue
        if in_usage and line.startswith(" "):
            # continuation of usage
            continue
        in_usage = False
        if _HELP_BOILERPLATE.match(stripped):
            break
        desc.append(stripped)
    return " ".join(desc).strip()


# Matches argparse option entries. Two-line form:
#   --side {left,right}, -s {left,right}
#                         help text continues here
# Or single-line form:
#   --target-alt TARGET_ALT  help text
# We greedily capture the option signature, then everything after.
_OPT_LINE = re.compile(
    r"^\s{2}(-{1,2}[A-Za-z][^\s,]*(?:[ \t,]+-{1,2}[A-Za-z][^\s,]*)*)"
    r"(?:[ \t]+(?:\{[^}]*\}|[A-Z_][A-Z0-9_]*))?"
    r"(?:[ \t]+(.*))?$"
)
_CHOICES_RE = re.compile(r"\{([^}]+)\}")
_DEFAULT_RE = re.compile(r"\(default[:\s]+(.+?)\)", re.IGNORECASE)
_TYPE_HINTS = (
    ("(int)", "int"),
    ("(float)", "float"),
    ("(bool)", "bool"),
)


def _parse_argparse_options(help_text: str) -> list[ScriptArg]:
    """Pull each --option / -o entry out of argparse --help output.

    Tolerant of multi-line help and the various forms argparse emits. Skips
    -h/--help. Recognizes choices, defaults, and infers type from the metavar
    (UPPERCASE), explicit "(int)"/"(float)" markers, or store_true flags.
    """
    options_section_started = False
    args: list[ScriptArg] = []
    current_help_lines: list[str] = []
    current_arg: Optional[ScriptArg] = None
    current_metavar: Optional[str] = None

    def finalize() -> None:
        if current_arg is None:
            return
        joined = " ".join(s.strip() for s in current_help_lines).strip()
        current_arg.help = joined
        # default from "(default: X)" in help text
        m = _DEFAULT_RE.search(joined)
        default_raw: Optional[str] = None
        if m:
            default_raw = m.group(1).strip().rstrip(".)")
        # type inference: explicit "(int)" / "(float)" hints, then sniff
        # numeric form of the default value
        if current_arg.type == "str":
            for needle, t in _TYPE_HINTS:
                if needle in joined.lower():
                    current_arg.type = t
                    break
        if current_arg.type == "str" and default_raw is not None:
            cleaned = default_raw.strip("'\"")
            try:
                int(cleaned)
                current_arg.type = "int"
            except ValueError:
                try:
                    float(cleaned)
                    current_arg.type = "float"
                except ValueError:
                    pass
        # apply default with the (possibly-refined) type
        if default_raw is not None and current_arg.type != "bool":
            current_arg.default = _coerce_value(default_raw, current_arg.type)
        args.append(current_arg)

    for raw_line in help_text.splitlines():
        line = raw_line.rstrip()
        stripped = line.strip()

        # Locate the "options:" section.
        if not options_section_started:
            if stripped.lower() in ("options:", "optional arguments:"):
                options_section_started = True
            continue

        # Empty line: keep collecting help text on continuation, but if we're
        # already past the args block, stop.
        if not stripped:
            continue

        # New section header? (positional arguments come after options
        # sometimes; we want to stop there.)
        if stripped.endswith(":") and not stripped.startswith("-"):
            finalize()
            current_arg = None
            current_help_lines = []
            break

        # An option line in argparse output starts at column 2 with a dash.
        # We need to distinguish the option-signature line from continuation
        # lines (which are indented further, ~24 cols).
        if line.startswith("  -") and not line.startswith("    "):
            finalize()
            current_help_lines = []
            current_arg = None
            current_metavar = None

            # Split signature from help. argparse pads to ~col 24 then the help
            # text; if the signature is long it wraps to the next line. The
            # signature is everything before the first run of 2+ spaces.
            content = line[2:]
            parts = re.split(r"\s{2,}", content, maxsplit=1)
            signature = parts[0].strip()
            inline_help = parts[1].strip() if len(parts) > 1 else ""
            if inline_help:
                current_help_lines.append(inline_help)

            # signature may be: "--side {left,right}, -s {left,right}"
            # or "--target-alt TARGET_ALT" or just "--show"
            # First, detect choices block.
            choices: Optional[list[str]] = None
            cm = _CHOICES_RE.search(signature)
            if cm:
                choices = [c.strip() for c in cm.group(1).split(",")]

            # Strip choice braces and metavars from the signature when
            # extracting flags. Split on commas/whitespace, keep tokens
            # starting with '-'.
            flag_tokens = []
            for tok in re.split(r"[,\s]+", _CHOICES_RE.sub("", signature)):
                tok = tok.strip()
                if not tok:
                    continue
                if tok.startswith("-"):
                    flag_tokens.append(tok)
                else:
                    # First non-flag token is the metavar (e.g. MODEL)
                    if current_metavar is None:
                        current_metavar = tok

            if not flag_tokens:
                current_arg = None
                continue
            # Prefer the long form (--xxx) if present.
            flag = next((f for f in flag_tokens if f.startswith("--")), flag_tokens[0])
            if flag in ("-h", "--help"):
                current_arg = None
                continue
            name = flag.lstrip("-").replace("-", "_")

            # Type inference:
            # - choices present -> "choice"
            # - metavar present -> "str" (refined later from help text hints)
            # - neither -> "bool" (store_true)
            if choices:
                arg_type = "choice"
            elif current_metavar is None:
                arg_type = "bool"
            else:
                arg_type = "str"

            current_arg = ScriptArg(
                name=name, flag=flag, type=arg_type,
                choices=choices,
                default=False if arg_type == "bool" else None,
            )
            continue

        # Continuation of help text for the last option.
        if current_arg is not None and line.startswith("  "):
            current_help_lines.append(stripped)
            continue

    finalize()
    return args


def _script_uses_argparse(path: str) -> bool:
    """Cheap text scan: True if the file imports argparse or builds a parser.

    Doesn't import or execute the script. False just means "we can't tell from
    text" -- in practice that overlaps with "no CLI args."
    """
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(8192)
    except OSError:
        return False
    return ("import argparse" in head
            or "from argparse" in head
            or "ArgumentParser(" in head)


def _extract_module_docstring(path: str) -> str:
    """Pull the first line of the module docstring, if any.

    Used as a fallback description when we don't run --help.
    """
    try:
        import ast
        with open(path, encoding="utf-8") as f:
            tree = ast.parse(f.read(), filename=path)
    except (OSError, SyntaxError):
        return ""
    doc = ast.get_docstring(tree) or ""
    first_line = doc.strip().split("\n", 1)[0].strip()
    return first_line


def _coerce_value(raw: str, declared_type: str):
    """Best-effort coerce a default value string to the declared type."""
    raw = raw.strip().strip("'\"")
    if raw.lower() in ("none", "null"):
        return None
    if declared_type == "int":
        try:
            return int(raw)
        except ValueError:
            return raw
    if declared_type == "float":
        try:
            return float(raw)
        except ValueError:
            return raw
    if declared_type == "bool":
        if raw.lower() in ("true", "1"):
            return True
        if raw.lower() in ("false", "0"):
            return False
    return raw


# ---- JSON helpers for FastAPI ---------------------------------------------

def script_info_to_dict(info: ScriptInfo) -> dict:
    """Convert dataclass -> dict, with nested args also serialized."""
    d = asdict(info)
    return d


def world_info_to_dict(info: WorldInfo) -> dict:
    return asdict(info)
