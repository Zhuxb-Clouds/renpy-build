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


def package_outputs(args):

    if not args.package:
        return

    if args.no_package:
        return

    def progress(step: int, total: int, message: str):
        print(f"[package {step}/{total}] {message}", flush=True)

    tmp = root / "tmp"
    install_dirs = [p for p in sorted(tmp.glob("install.*")) if p.is_dir()]
    total_steps = 4 + len(install_dirs)
    step = 1
    renpy_copy_ignore = shutil.ignore_patterns(
        ".git",
        "__pycache__",
        "*.pyc",
        "*.pyo",
        ".pytest_cache",
        ".mypy_cache",
    )

    progress(step, total_steps, "Preparing package directories")
    package_root = Path(args.package_dir).resolve() if args.package_dir else (root / "tmp" / "packages")
    package_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    bundle_name = f"build-{timestamp}"
    bundle_dir = package_root / bundle_name

    if bundle_dir.exists():
        shutil.rmtree(bundle_dir)

    bundle_dir.mkdir(parents=True, exist_ok=True)

    step += 1
    progress(step, total_steps, "Copying Ren'Py source tree")
    renpy_src = root / "renpy"
    renpy_dest = bundle_dir / "renpy"
    if renpy_src.exists():
        shutil.copytree(renpy_src, renpy_dest, dirs_exist_ok=True, ignore=renpy_copy_ignore)

    step += 1
    progress(step, total_steps, "Preparing artifacts directory")
    artifacts_dir = bundle_dir / "artifacts"
    artifacts_dir.mkdir(parents=True, exist_ok=True)

    for p in install_dirs:
        step += 1
        progress(step, total_steps, f"Copying artifact: {p.name}")
        shutil.copytree(p, artifacts_dir / p.name, dirs_exist_ok=True)

    step += 1
    progress(step, total_steps, "Creating compressed archive")
    archive_base = str(package_root / bundle_name)
    archive_path = shutil.make_archive(archive_base, "gztar", root_dir=package_root, base_dir=bundle_name)

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
