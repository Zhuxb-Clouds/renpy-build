from renpybuild.context import Context
from renpybuild.task import task
from pathlib import Path
import zipfile


def latest_steam_sdk_archive(c: Context):

    candidates = list(Path(str(c.path("{{ tars }}"))).glob("steamworks_sdk_*.zip"))

    if not candidates:
        return None

    def version_key(path: Path):
        stem = path.stem
        version = stem.rsplit("_", 1)[-1]

        try:
            return int(version)
        except ValueError:
            return -1

    return max(candidates, key=version_key)


@task(kind="host", platforms="all")
def unpack_sdk(c: Context):

    c.clean("{{ install }}/steam")

    sdk_archive = latest_steam_sdk_archive(c)

    if sdk_archive is None:
        return

    zf = zipfile.ZipFile(sdk_archive)
    zf.extractall(c.path("{{ install }}/steam"))
    zf.close()


@task(kind="host", platforms="all")
def patch_sdk(c: Context):

    if not c.path("{{host}}/steam/sdk").exists():
        return

    c.chdir("{{ install }}/steam/sdk")
    # c.patch("steam-cdecl.diff")


@task(kind="python", platforms="linux,windows,mac", always=True)
def build(c: Context):

    if not c.path("{{host}}/steam/sdk").exists():
        return

    if c.platform == "linux" and c.arch == "x86_64":
        c.var("steamdll", "{{ host }}/steam/sdk/redistributable_bin/linux64/libsteam_api.so")
    elif c.platform == "windows" and c.arch == "x86_64":
        c.var("steamdll", "{{ host }}/steam/sdk/redistributable_bin/win64/steam_api64.dll")
    elif c.platform == "mac":
        c.var("steamdll", "{{ host }}/steam/sdk/redistributable_bin/osx/libsteam_api.dylib")
    else:
        return

    c.run("cp {{steamdll}} {{dlpa}}")

    c.run("install -d {{pytmp}}/steam")
    c.run("{{ root }}/steamapi/generate.py {{ host }}/steam/sdk/public/steam/steam_api.json {{ pytmp }}/steam/steamapi.py")

    c.run("cp {{ pytmp }}/steam/steamapi.py {{renpy}}/steamapi.py")
