#!/usr/bin/env python3

import sys
import argparse
import shutil
import datetime
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


PACKAGE_PLATFORMS = {"linux", "windows"}
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
        if platform.platform not in PACKAGE_PLATFORMS:
            continue

        if platforms and (platform.platform not in platforms):
            continue

        if archs and (platform.arch not in archs):
            continue

        if pythons and (platform.python not in pythons):
            continue

        rv.append(platform)

    return rv


def runtime_dir_name(platform: Platform):
    return f"py{platform.python}-{platform.platform}-{platform.arch}"


def platform_lib_dir_name(platform: Platform):
    return f"{platform.platform}-{platform.arch}"


def archive_name(target: Platform):
    if target.platform == "linux" and target.arch == "x86_64":
        return "renpy-linux"

    if target.platform == "windows" and target.arch == "x86_64":
        return "renpy-windows"

    return f"renpy-{target.platform}-{target.arch}"


def make_renpy_copy_ignore(renpy_src: Path, target: Platform):

    runtime_dirs = { runtime_dir_name(i) for i in known_platforms if i.platform in PACKAGE_PLATFORMS }
    platform_dirs = { platform_lib_dir_name(i) for i in known_platforms if i.platform in PACKAGE_PLATFORMS }

    keep_runtime_dir = runtime_dir_name(target)
    keep_platform_dir = platform_lib_dir_name(target)

    if target.platform == "windows":
        blocked_top_level = {
            "renpy.sh",
            "renpy3.sh",
            "run.sh",
        }
    else:
        blocked_top_level = {
            "7z.sfx",
            "renpy.exe",
            "renpy3.exe",
        }

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
                if (name in runtime_dirs) and (name != keep_runtime_dir):
                    ignored.add(name)

                if (name in platform_dirs) and (name != keep_platform_dir):
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

        print(f"[package {target_index}/{total_targets}] Creating compressed archive", flush=True)
        archive_base = str(package_root / archive_name(target))
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
