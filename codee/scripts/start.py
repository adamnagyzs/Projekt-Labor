"""Egyablakos indító: adatbázis, szerver, kliens — egyetlen lépésben.

A bemutatón nem akarunk két parancsablakot nyitogatni. Ez a szkript elindítja a
konténereket, felhúzza a szervert, megvárja, amíg az tényleg válaszol, és csak
utána nyitja meg a klienst. Amikor a kliensablakot bezárják, a szervert is leállítja.

Futtatható közvetlenül (`uv run python scripts/start.py`), vagy a belőle készült
`Leltariv.exe`-ként. Az utóbbi esetben a projekt mappáját az alábbi sorrendben keresi:

1. parancssori argumentum;
2. a `leltariv-utvonal.txt` fájl a futtatható mellett;
3. a saját helyéből felfelé haladva;
4. ha egyik sem, akkor megkérdezi, és a választ elmenti.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HEALTH_URL = "http://127.0.0.1:8000/health"
SERVER_START_TIMEOUT = 90
CONFIG_NAME = "leltariv-utvonal.txt"

#: Ahol a telepítők elhelyezik az eszközöket, ha nincsenek a rendszer PATH-ában.
#: Az asztalról indított program más környezetet örököl, mint egy megnyitott
#: parancsablak, ezért nem elég a PATH-ra hagyatkozni.
TOOL_LOCATIONS: dict[str, tuple[str, ...]] = {
    "docker": (
        r"C:\Program Files\Rancher Desktop\resources\resources\win32\bin",
        r"~\.rd\bin",
        r"C:\Program Files\Docker\Docker\resources\bin",
    ),
    "uv": (
        r"~\.local\bin",
        r"C:\Program Files\uv",
    ),
}


def find_tool(name: str) -> str:
    """Az eszköz teljes elérési útja, vagy érthető hiba, ha nincs meg."""
    found = shutil.which(name)
    if found:
        return found

    for location in TOOL_LOCATIONS.get(name, ()):
        candidate = Path(os.path.expanduser(location)) / f"{name}.exe"
        if candidate.is_file():
            return str(candidate)

    raise SystemExit(
        f"Nem találom a(z) {name} programot.\n"
        f"Telepítve van? Ha igen, tedd a mappáját a PATH-ba, vagy indítsd a programot "
        f"abból a parancsablakból, ahol a {name} működik."
    )


def here() -> Path:
    """A futtatható (vagy a szkript) mappája."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def looks_like_workspace(path: Path) -> bool:
    """Igaz, ha a mappa a `codee` workspace gyökere."""
    return (path / "pyproject.toml").is_file() and (path / "packages").is_dir()


def find_workspace_upwards(start: Path) -> Path | None:
    for candidate in [start, *start.parents]:
        if looks_like_workspace(candidate):
            return candidate
        if looks_like_workspace(candidate / "codee"):
            return candidate / "codee"
    return None


def read_saved_path() -> Path | None:
    config = here() / CONFIG_NAME
    if not config.is_file():
        return None

    saved = Path(config.read_text(encoding="utf-8").strip())
    if looks_like_workspace(saved):
        return saved
    if looks_like_workspace(saved / "codee"):
        return saved / "codee"
    return None


def ask_for_path() -> Path:
    print("Nem találom a projektet. Add meg a mappát, ahol a codee könyvtár van.")
    print("Példa: C:\\Users\\Sanyi\\Desktop\\projekt-labor\n")

    while True:
        answer = input("Mappa: ").strip().strip('"')
        if not answer:
            continue

        given = Path(answer)
        for candidate in (given, given / "codee"):
            if looks_like_workspace(candidate):
                (here() / CONFIG_NAME).write_text(str(candidate), encoding="utf-8")
                print(f"Megjegyeztem: {candidate}\n")
                return candidate

        print("Ebben a mappában nem találom a workspace-t. Próbáld újra.\n")


def resolve_workspace() -> Path:
    if len(sys.argv) > 1:
        given = Path(sys.argv[1])
        for candidate in (given, given / "codee"):
            if looks_like_workspace(candidate):
                return candidate

    saved = read_saved_path()
    if saved is not None:
        return saved

    found = find_workspace_upwards(here())
    if found is not None:
        return found

    return ask_for_path()


def run(command: list[str], cwd: Path) -> int:
    """Parancs futtatása a workspace-ben, a kimenet ide folyik."""
    return subprocess.call(command, cwd=cwd)


def start_database(workspace: Path) -> None:
    print("Adatbázis indítása...")
    docker = find_tool("docker")

    if run([docker, "compose", "up", "-d"], workspace) != 0:
        raise SystemExit(
            "\nA konténerek nem indultak el.\n"
            "Fut a Docker (Rancher Desktop)? Indítsd el, és próbáld újra."
        )


def server_is_up() -> bool:
    try:
        with urllib.request.urlopen(HEALTH_URL, timeout=2) as response:
            return response.status == 200
    except (urllib.error.URLError, OSError):
        return False


def wait_for_server(process: subprocess.Popen[bytes]) -> None:
    print("Várom a szervert...", end="", flush=True)
    deadline = time.monotonic() + SERVER_START_TIMEOUT

    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SystemExit(
                "\n\nA szerver elindulás közben leállt. A fenti üzenet mondja meg, miért."
            )
        if server_is_up():
            print(" kész.")
            return
        print(".", end="", flush=True)
        time.sleep(1)

    process.terminate()
    raise SystemExit("\n\nA szerver nem válaszolt időben. Fut az adatbázis? Jó a .env?")


def main() -> None:
    workspace = resolve_workspace()
    print(f"Projekt: {workspace}\n")

    uv = find_tool("uv")

    if not (workspace / ".env").is_file():
        example = workspace / ".env.example"
        if example.is_file():
            (workspace / ".env").write_text(example.read_text(encoding="utf-8"), encoding="utf-8")
            print("A .env nem létezett, létrehoztam a mintából. Nézd át, ha valami nem stimmel.\n")

    start_database(workspace)

    print("Szerver indítása...")
    server = subprocess.Popen(
        [uv, "run", "uvicorn", "leltariv_server.main:app", "--host", "127.0.0.1", "--port", "8000"],
        cwd=workspace,
    )

    try:
        wait_for_server(server)
        print("\nKliens indítása. Az ablak bezárásával minden leáll.\n")
        run([uv, "run", "python", "-m", "leltariv_client.app"], workspace)
    finally:
        print("\nSzerver leállítása...")
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
        print("Kész.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nMegszakítva.")
    except SystemExit as stop:
        if stop.code not in (0, None):
            print(f"\n{stop.code}")
        input("\nNyomj Entert a bezáráshoz.")
    except Exception as error:  # noqa: BLE001 — az ablak ne tűnjön el olvasatlan hibával
        print(f"\nVáratlan hiba: {error}")
        input("\nNyomj Entert a bezáráshoz.")
