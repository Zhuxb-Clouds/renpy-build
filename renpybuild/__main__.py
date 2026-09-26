#!/usr/bin/env python3

import sys
import argparse
import shutil
import datetime
import zipfile
from pathlib import Path

import renpybuild.task
from renpybuild.context import Context

import tasks as _

known_platforms = [ ]

# Platform Registry ############################################################


class Platform:

    def __init__(self, platform, arch, python, experimental=False):
        self.platform = platform
        self.arch = arch
        self.python = python
        self.experimental = experimental

        known_platforms.append(self)


class PackageTarget:

    def __init__(self, platform, arch, python):
        self.platform = platform
        self.arch = arch
        self.python = python


# Python 3

Platform("linux", "x86_64", "3")
Platform("linux", "aarch64", "3")

Platform("windows", "x86_64", "3")

Platform("mac", "x86_64", "3")
Platform("mac", "arm64", "3")

Platform("android", "x86_64", "3")
Platform("android", "arm64_v8a", "3")
Platform("android", "armeabi_v7a", "3")

Platform("ios", "arm64", "3")
Platform("ios", "sim-x86_64", "3")
Platform("ios", "sim-arm64", "3")

Platform("web", "wasm", "3")


COMMON_RENPY_IGNORES = shutil.ignore_patterns(
    ".git",
    "__pycache__",
    "*.pyo",
    ".pytest_cache",
    ".mypy_cache",
    ".venv",
    ".vscode",
)


def iter_package_targets(args):

    platforms = set(i.strip() for i in args.platforms.split(",") if i)
    archs = set(i.strip() for i in args.archs.split(",") if i)
    pythons = set(i.strip() for i in args.pythons.split(",") if i)

    rv = [ ]

    for platform in known_platforms:
        if platforms and (platform.platform not in platforms):
            continue

        if archs and (platform.arch not in archs):
            continue

        if pythons and (platform.python not in pythons):
            continue

        rv.append(platform)

    return rv


def runtime_dir_name(platform: Platform):
    if platform.platform == "mac":
        return f"py{platform.python}-{platform.platform}-universal"

    return f"py{platform.python}-{platform.platform}-{platform.arch}"


def platform_lib_dir_name(platform: Platform):
    if platform.platform == "mac":
        return f"{platform.platform}-universal"

    return f"{platform.platform}-{platform.arch}"


def archive_name(target: Platform):
    if target.platform == "linux" and target.arch == "x86_64":
        return "renpy-linux"

    if target.platform == "windows" and target.arch == "x86_64":
        return "renpy-windows"

    return f"renpy-{target.platform}-{target.arch}"


STEAM_SDK_MEMBERS = {
    ("linux", "x86_64"): ("sdk/redistributable_bin/linux64/libsteam_api.so", "libsteam_api.so"),
    ("windows", "x86_64"): ("sdk/redistributable_bin/win64/steam_api64.dll", "steam_api64.dll"),
    ("mac", "x86_64"): ("sdk/redistributable_bin/osx/libsteam_api.dylib", "libsteam_api.dylib"),
    ("mac", "arm64"): ("sdk/redistributable_bin/osx/libsteam_api.dylib", "libsteam_api.dylib"),
    ("mac", "universal"): ("sdk/redistributable_bin/osx/libsteam_api.dylib", "libsteam_api.dylib"),
}


def latest_steam_sdk_archive():
    candidates = list(root.glob("tars/steamworks_sdk_*.zip"))

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


def add_steam_support(target: Platform, renpy_dest: Path):
    sdk_member = STEAM_SDK_MEMBERS.get((target.platform, target.arch))

    if sdk_member is None:
        return

    sdk_archive = latest_steam_sdk_archive()

    if sdk_archive is None:
        print(f"No Steam SDK archive found for {target.platform}-{target.arch}; skipping Steam support.", flush=True)
        return

    runtime_dest = renpy_dest / "lib" / runtime_dir_name(target)

    if not runtime_dest.exists():
        print(f"Missing runtime directory {runtime_dir_name(target)}; skipping Steam support.", flush=True)
        return

    sdk_path, output_name = sdk_member

    with zipfile.ZipFile(sdk_archive) as zf:
        try:
            with zf.open(sdk_path) as src, open(runtime_dest / output_name, "wb") as dst:
                shutil.copyfileobj(src, dst)
        except KeyError:
            print(f"Steam SDK archive {sdk_archive.name} is missing {sdk_path}; skipping Steam support.", flush=True)
            return

    steamapi_src = root / "steamapi" / "steamapi.py"
    steamapi_dest = renpy_dest / "steamapi.py"

    if steamapi_src.exists() and not steamapi_dest.exists():
        shutil.copy2(steamapi_src, steamapi_dest)

    print(f"Included Steam support from {sdk_archive.name}", flush=True)


def make_renpy_copy_ignore(renpy_src: Path, target: Platform):
    runtime_dirs = { runtime_dir_name(i) for i in known_platforms }
    platform_dirs = { platform_lib_dir_name(i) for i in known_platforms }

    keep_runtime_dirs = { runtime_dir_name(target) }
    keep_platform_dirs = { platform_lib_dir_name(target) }

    blocked_top_level = set()

    if target.platform == "windows":
        blocked_top_level.update({
            "renpy.sh",
            "renpy3.sh",
            "run.sh",
        })
    else:
        blocked_top_level.update({
            "7z.sfx",
            "renpy.exe",
            "renpy3.exe",
        })

    return make_renpy_copy_ignore_for_dirs(
        renpy_src,
        runtime_dirs,
        platform_dirs,
        keep_runtime_dirs,
        keep_platform_dirs,
        blocked_top_level,
    )


def make_renpy_copy_ignore_for_dirs(
    renpy_src: Path,
    runtime_dirs,
    platform_dirs,
    keep_runtime_dirs,
    keep_platform_dirs,
    blocked_top_level,
):

    def ignore(path, names):
        ignored = set(COMMON_RENPY_IGNORES(path, names))

        current = Path(path)

        try:
            relative = current.relative_to(renpy_src)
        except ValueError:
            return ignored

        if relative == Path("."):
            ignored.update(name for name in names if name in blocked_top_level)

        if relative == Path("lib"):
            for name in names:
                if (name in runtime_dirs) and (name not in keep_runtime_dirs):
                    ignored.add(name)

                if (name in platform_dirs) and (name not in keep_platform_dirs):
                    ignored.add(name)

        return ignored

    return ignore


def package_outputs(args):

    if not args.package:
        return

    if args.no_package:
        return

    package_root = Path(args.package_dir).resolve() if args.package_dir else (root / "tmp" / "packages")
    package_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    renpy_src = root / "renpy"

    if args.package_mode == "desktop":
        package_desktop_outputs(args, package_root, timestamp, renpy_src)
        return

    targets = iter_package_targets(args)

    if not targets:
        print("No package targets selected.")
        return

    total_targets = len(targets)

    for target_index, target in enumerate(targets, start=1):

        runtime_dir = renpy_src / "lib" / runtime_dir_name(target)

        if not runtime_dir.exists():
            print(
                f"[package {target_index}/{total_targets}] Skipping {target.platform}-{target.arch}: "
                f"missing runtime {runtime_dir.relative_to(root)}",
                flush=True,
            )
            continue

        bundle_name = f"renpy-{target.platform}-{target.arch}-{timestamp}"
        bundle_dir = package_root / bundle_name

        if bundle_dir.exists():
            shutil.rmtree(bundle_dir)

        print(f"[package {target_index}/{total_targets}] Packaging {target.platform}-{target.arch}", flush=True)

        renpy_dest = bundle_dir / "renpy"

        print(f"[package {target_index}/{total_targets}] Copying Ren'Py tree", flush=True)
        shutil.copytree(
            renpy_src,
            renpy_dest,
            ignore=make_renpy_copy_ignore(renpy_src, target),
        )

        add_steam_support(target, renpy_dest)

        print(f"[package {target_index}/{total_targets}] Creating compressed archive", flush=True)
        archive_base = str(package_root / archive_name(target))
        archive_path = shutil.make_archive(archive_base, "gztar", root_dir=bundle_dir, base_dir="renpy")

        print(f"Packaged build outputs to: {bundle_dir}")
        print(f"Archive created at: {archive_path}")


def package_desktop_outputs(args, package_root: Path, timestamp: str, renpy_src: Path):

    platforms = set(i.strip() for i in args.platforms.split(",") if i)
    selected_platforms = [
        i for i in ("linux", "windows", "mac")
        if (not platforms) or (i in platforms)
    ]

    if not selected_platforms:
        print("No desktop package targets selected.")
        return

    package_targets = {
        "linux": PackageTarget("linux", "x86_64", "3"),
        "windows": PackageTarget("windows", "x86_64", "3"),
        "mac": PackageTarget("mac", "universal", "3"),
    }

    runtime_dirs = { runtime_dir_name(package_targets[i]) for i in selected_platforms }
    platform_dirs = { platform_lib_dir_name(package_targets[i]) for i in selected_platforms }
    missing_runtime_dirs = [ ]

    for runtime_dir in runtime_dirs:
        if not (renpy_src / "lib" / runtime_dir).exists():
            missing_runtime_dirs.append(runtime_dir)

    if missing_runtime_dirs:
        print(
            "Skipping desktop package: missing runtimes " + ", ".join(sorted(missing_runtime_dirs)),
            flush=True,
        )
        return

    package_name = args.package_name or f"renpy-{datetime.datetime.now().strftime('%Y%m%d')}"
    bundle_name = f"{package_name}-{timestamp}"
    bundle_dir = package_root / bundle_name

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    print(
        f"[package desktop] Packaging desktop runtimes for {', '.join(selected_platforms)}",
        flush=True,
    )

    renpy_dest = bundle_dir / "renpy"

    print("[package desktop] Copying Ren'Py tree", flush=True)
    shutil.copytree(
        renpy_src,
        renpy_dest,
        ignore=make_renpy_copy_ignore_for_dirs(
            renpy_src,
            { runtime_dir_name(i) for i in package_targets.values() },
            { platform_lib_dir_name(i) for i in package_targets.values() },
            runtime_dirs,
            platform_dirs,
            set(),
        ),
    )

    for platform in selected_platforms:
        add_steam_support(package_targets[platform], renpy_dest)

    print("[package desktop] Creating compressed archive", flush=True)
    archive_base = str(package_root / package_name)
    archive_path = shutil.make_archive(archive_base, "gztar", root_dir=bundle_dir, base_dir="renpy")

    print(f"Packaged build outputs to: {bundle_dir}")
    print(f"Archive created at: {archive_path}")

def build(args):

    platforms = set(i.strip() for i in args.platforms.split(",") if i)
    archs = set(i.strip() for i in args.archs.split(",") if i)
    pythons = set(i.strip() for i in args.pythons.split(",") if i)

    # Check that the platforms, archs, and pythons are known.

    for i in platforms:
        if i not in { j.platform for j in known_platforms }:
            print("Platform", i, "is not known.", file=sys.stderr)
            sys.exit(1)

    for i in archs:
        if i not in { j.arch for j in known_platforms }:
            print("Architecture", i, "is not known.", file=sys.stderr)
            sys.exit(1)

    for i in pythons:
        if i not in { j.python for j in known_platforms }:
            print("Python", i, "is not known.", file=sys.stderr)
            sys.exit(1)

    # Actually build everything.

    last_task = None

    if args.stop:
        for task in renpybuild.task.tasks:
            if task.name == args.stop:
                last_task = task

    for task in renpybuild.task.tasks:
        for p in known_platforms:

            if platforms and (p.platform not in platforms):
                continue

            if archs and (p.arch not in archs):
                continue

            if pythons and (p.python not in pythons):
                continue

            platform = p.platform
            arch = p.arch
            python = p.python

            context = Context(
                p.platform,
                p.arch,
                p.python,
                root,
                args)

            task.run(context)

        if task is last_task:
            break

    print("")
    print("Build finished successfully.")

    package_outputs(args)


def remove_complete(args):

    tmp = root / "tmp"
    complete = tmp / "complete"

    if not complete.is_dir():
        return

    for fn in complete.iterdir():
        name = fn.name.split(".")[0]
        taskname = name.rpartition("-")[2]

        if (name in args.tasks) or (taskname in args.tasks):
            fn.unlink()


def rebuild(args):

    remove_complete(args)
    build(args)


def clean(args):

    def rmtree(p : Path):
        if p.exists():
            shutil.rmtree(p)

    def unlink(p : Path):
        if p.exists():
            p.unlink()

    tmp = root / "tmp"

    rmtree(tmp / "build")
    rmtree(tmp / "complete")
    rmtree(tmp / "host")
    rmtree(tmp / "source")

    for i in tmp.glob("install.*"):
        rmtree(i)

    def rmgen(d):
        rmtree(d / "gen3")
        rmtree(d / "gen3-static")

    rmgen(root / "tmp")
    rmgen(root / "pygame_sdl2")

    def rmtrio(name : str):
        """
        Deletes groups of directories and symlinks, like web, renios, and rapt.
        """

        unlink(root / "renpy" / name)
        rmtree(root / "renpy" / (name + "2"))
        rmtree(root / "renpy" / (name + "3"))

    rmtrio("web")
    rmtrio("renios")
    rmtrio("rapt")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--platforms", "--platform", default="")
    ap.add_argument("--archs", "--arch", default="")
    ap.add_argument("--pythons", "--python", default="3")

    ap.add_argument("--nostrip", action="store_true", default=False)
    ap.add_argument("--sdl", action="store_true", default=False, help="Do not clean SDL on rebuild.")

    ap.add_argument("--experimental", action="store_true", default=False)
    ap.add_argument("--package", action="store_true", default=False, help="Create a post-build package bundle.")
    ap.add_argument("--package-mode", choices=["split", "desktop"], default="split", help="Choose whether packaging emits per-platform archives or a single unified desktop archive.")
    ap.add_argument("--package-name", default="", help="Archive basename without extension. Used by desktop package mode and as an override when applicable.")
    ap.add_argument("--package-dir", default="", help="Directory used to store post-build bundles. Defaults to tmp/packages.")
    ap.add_argument("--no-package", action="store_true", default=False, help="Disable automatic packaging after build.")

    ap.add_argument("--stop", default=None, help="Stop after this task.")

    ap.set_defaults(function=build)

    subparsers = ap.add_subparsers()

    sp = subparsers.add_parser("build")
    sp.set_defaults(function=build)

    sp = subparsers.add_parser("rebuild")
    sp.add_argument("tasks", nargs='+')
    sp.set_defaults(function=rebuild)

    sp = subparsers.add_parser("clean")
    sp.set_defaults(function=clean)

    global root

    args = ap.parse_args()

    if not args.experimental:
        known_platforms[:] = [ i for i in known_platforms if not i.experimental ]

    root = Path(__file__).parent.parent.resolve()

    args.function(args)


if __name__ == "__main__":
    import os

    if os.environ.get('PYTHONHASHSEED') is None:
        os.environ['PYTHONHASHSEED'] = "0"
        os.execv(sys.executable, sys.orig_argv)
        # script will now re-execute with new hash seed

    main()
