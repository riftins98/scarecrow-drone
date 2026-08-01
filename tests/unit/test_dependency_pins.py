"""The four dependency declarations must not drift apart.

The same runtime dependency set is written out by hand in four places, because
each answers a different question and none can be derived from the others:

    requirements.txt          the pinned reference; the venv track installs it
    pixi.toml                 the macOS environment (conda toolchain + pypi)
    docker/Dockerfile         the Windows/Linux image
    pyproject.toml            the `scarecrow` package itself, for a Pi

Only ``requirements.txt`` carries versions for the flight stack, and the other
two environments say so in their own comments ("the pin matches
requirements.txt"). Nothing enforced it. The Dockerfile in particular does not
``pip install -r requirements.txt`` — it retypes the whole list inline, so the
lists agreed only for as long as someone remembered to edit both.

That is a slow failure. A dependency removed from one file and left in another
ships an image carrying a package nothing imports; a version bumped in one
place and not the other means macOS and Windows run different code and the
difference surfaces as a flight bug on one platform only.

``pyproject.toml`` deliberately does NOT pin. It describes the package, and a
package that pins its dependencies exactly cannot be co-installed with
anything. It is checked for *presence*, not versions.
"""
import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

# Installed for real hardware only, so the simulation image deliberately omits
# it. Asserted below rather than merely commented.
HARDWARE_ONLY = {"rplidar-roboticia"}

# Everything a simulated flight imports. Each must be reachable from a plain
# `pip install -e ".[sim]"`, which is how the package lands on a Raspberry Pi.
FLIGHT_STACK = {
    "mavsdk",
    "numpy",
    "opencv-python-headless",
    "pillow",
    "matplotlib",
    "aiohttp",
    "torch",
    "torchvision",
    "ultralytics",
}


def _normalise(name):
    return name.lower().replace("_", "-").strip("'\"")


def requirements_pins():
    """``name==version`` from requirements.txt, ignoring the `-r` include."""
    pins = {}
    for line in (ROOT / "requirements.txt").read_text().splitlines():
        line = line.split("#")[0].strip()
        if not line or line.startswith("-"):
            continue
        if "==" in line:
            name, version = line.split("==", 1)
            pins[_normalise(name)] = version.strip()
    return pins


def pixi_pins():
    """Pins from pixi.toml's conda [dependencies] and [pypi-dependencies].

    Both tables matter: numpy is declared on the conda side (gz-sim8-python
    pulls it in, and declaring it on both sides makes the solve unsatisfiable),
    everything else on the pypi side.
    """
    data = tomllib.loads((ROOT / "pixi.toml").read_text())
    pins = {}
    for table in ("dependencies", "pypi-dependencies"):
        for name, spec in data.get(table, {}).items():
            if isinstance(spec, str) and spec.startswith("=="):
                pins[_normalise(name)] = spec[2:]
    return pins


def dockerfile_pins():
    """Pins from the Dockerfile's runtime `pip install` layer.

    Scoped to the runtime install so the PX4 build-time lock file, which is
    installed separately and versioned independently, is not compared against
    the flight stack.
    """
    # Join line continuations first, so each RUN is one logical line. Matching
    # the continuations inside the RUN pattern does not work: the greedy
    # `[^\n]*` eats the trailing backslash the continuation needs to see.
    text = re.sub(r"\\\n\s*", " ", (ROOT / "docker" / "Dockerfile").read_text())
    runs = [
        line
        for line in text.splitlines()
        if line.startswith("RUN")
        and "pip install" in line
        and "requirements-px4" not in line
    ]
    pins = {}
    for block in runs:
        for name, version in re.findall(r"'?([A-Za-z0-9_.-]+)'?==([0-9][0-9A-Za-z.]*)", block):
            pins[_normalise(name)] = version
    return pins


def pyproject_declared():
    """Every distribution name pyproject declares, across all extras."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text())
    project = data["project"]
    names = set()
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    for spec in specs:
        names.add(_normalise(re.split(r"[<>=!\[ ]", spec, 1)[0]))
    return names


class TestPinsAgree:
    """Every package two files share must carry the same version."""

    @pytest.mark.parametrize("other_name", ["pixi.toml", "docker/Dockerfile"])
    def test_shared_pins_match_requirements(self, other_name):
        reference = requirements_pins()
        other = pixi_pins() if other_name == "pixi.toml" else dockerfile_pins()

        disagreements = {
            name: (reference[name], other[name])
            for name in reference.keys() & other.keys()
            if reference[name] != other[name]
        }

        assert not disagreements, (
            f"{other_name} disagrees with requirements.txt: "
            + ", ".join(
                f"{n} (requirements={r}, {other_name}={o})"
                for n, (r, o) in sorted(disagreements.items())
            )
        )

    def test_the_reference_is_not_empty(self):
        """A parser that silently matches nothing would pass every test above."""
        assert len(requirements_pins()) >= 10
        assert len(pixi_pins()) >= 10
        assert len(dockerfile_pins()) >= 10


class TestNothingUndeclared:
    def test_docker_installs_nothing_requirements_has_not_declared(self):
        """An undeclared pin in the image is a dependency no other track has."""
        webapp = {
            _normalise(line.split("==")[0].split(">=")[0])
            for line in (ROOT / "webapp" / "backend" / "requirements.txt")
            .read_text()
            .splitlines()
            if line.strip() and not line.startswith("#")
        }
        declared = requirements_pins().keys() | webapp

        undeclared = dockerfile_pins().keys() - declared

        assert not undeclared, (
            f"docker/Dockerfile installs {sorted(undeclared)}, which no "
            "requirements file declares"
        )

    def test_hardware_only_packages_stay_out_of_the_image(self):
        """The simulation image has no radio to talk to a real RPLidar."""
        assert not (HARDWARE_ONLY & dockerfile_pins().keys())


class TestPackageIsInstallable:
    """`pip install -e ".[sim]"` must produce a package that can actually fly."""

    @pytest.mark.parametrize("package", sorted(FLIGHT_STACK))
    def test_flight_stack_is_declared_in_pyproject(self, package):
        assert package in pyproject_declared(), (
            f"{package} is pinned in requirements.txt but missing from "
            "pyproject.toml, so installing the package alone yields one that "
            "fails at the moment it is first used"
        )

    def test_pyproject_does_not_pin_exact_versions(self):
        """A library that pins == cannot be co-installed with anything."""
        data = tomllib.loads((ROOT / "pyproject.toml").read_text())
        specs = list(data["project"].get("dependencies", []))
        for extra in data["project"].get("optional-dependencies", {}).values():
            specs.extend(extra)

        # Test tooling is allowed to pin — it is not part of the library's
        # install surface and reproducible test runs are worth more there.
        runtime = [s for s in specs if _normalise(re.split(r"[<>=!\[ ]", s, 1)[0]) not in {
            "pytest", "pytest-asyncio", "pytest-cov", "httpx",
            "fastapi", "uvicorn", "aiofiles",
        }]

        pinned = [s for s in runtime if "==" in s]
        assert not pinned, f"pyproject pins exact versions: {pinned}"
