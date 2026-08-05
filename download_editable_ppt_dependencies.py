#!/usr/bin/env python3
"""Download and package LazyMind Desktop editable-PPT dependencies.

The generated ZIP files are ready to upload to the configured dependency host.
They contain the exporter source, production node_modules, and the target
platform's Playwright Chromium installation at the archive root.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import zipfile
from pathlib import Path
from urllib.parse import urljoin


REPO_ROOT = Path(__file__).resolve().parent
EXPORTER_ROOT = REPO_ROOT / "plugins" / "ppt-plugin" / "runtime" / "scripts" / "export_pptx"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "dist" / "editable-ppt-dependencies"
DEFAULT_BASE_URL = "https://modelscope.cn/datasets/CarlosShaoting/lazymind-cst/resolve/master/"

TARGETS = {
    "windows-x64": {
        "manifest_platform": "windows",
        "manifest_arch": "x64",
        "playwright_platform": "win64",
        "config_key": "windowsX64",
    },
    "darwin-arm64": {
        "manifest_platform": "darwin",
        "manifest_arch": "arm64",
        # Chromium's mac-arm64 artifact is shared across supported macOS releases.
        "playwright_platform": "mac15-arm64",
        "config_key": "darwinArm64",
    },
    "linux-x64": {
        "manifest_platform": "linux",
        "manifest_arch": "x64",
        # LazyMind's Linux local runtime and release build use Ubuntu 24.04 x64.
        "playwright_platform": "ubuntu24.04-x64",
        "config_key": "linuxX64",
    },
}

ENV_PREFIXES = {
    "windows-x64": "LAZYMIND_EDITABLE_PPT_WINDOWS_X64",
    "darwin-arm64": "LAZYMIND_EDITABLE_PPT_DARWIN_ARM64",
    "linux-x64": "LAZYMIND_EDITABLE_PPT_LINUX_X64",
}

LINUX_RUNTIME_PACKAGES = ("libnspr4", "libnss3", "libasound2t64")


def run(command: list[str], *, cwd: Path, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def read_exporter_version() -> str:
    package = json.loads((EXPORTER_ROOT / "package.json").read_text(encoding="utf-8"))
    version = str(package.get("version") or "").strip()
    if not version or any(char not in "0123456789.-_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ" for char in version):
        raise RuntimeError(f"invalid exporter version: {version!r}")
    return version


def copy_exporter_source(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for filename in ("html_to_pptx.mjs", "package.json", "package-lock.json"):
        source = EXPORTER_ROOT / filename
        if not source.is_file():
            raise FileNotFoundError(source)
        shutil.copy2(source, destination / filename)
    shutil.copytree(EXPORTER_ROOT / "lib", destination / "lib", symlinks=True)


def install_node_dependencies(payload: Path) -> None:
    env = os.environ.copy()
    env["PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD"] = "1"
    run(
        [
            "npm",
            "install",
            "--omit=dev",
            "--omit=optional",
            "--no-audit",
            "--no-fund",
        ],
        cwd=payload,
        env=env,
    )
    for marker in ("pptxgenjs", "playwright", "echarts"):
        if not (payload / "node_modules" / marker).exists():
            raise RuntimeError(f"npm dependency missing after install: {marker}")
    # Runtime code imports modules directly and never needs npm's platform-
    # specific .bin shims. Removing them also avoids Windows symlink privileges.
    bin_dir = payload / "node_modules" / ".bin"
    if bin_dir.exists():
        shutil.rmtree(bin_dir)


def install_target_browser(payload: Path, playwright_platform: str) -> None:
    browsers = payload / "browsers"
    browsers.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PLAYWRIGHT_BROWSERS_PATH"] = str(browsers)
    env["PLAYWRIGHT_HOST_PLATFORM_OVERRIDE"] = playwright_platform
    run(
        [
            "node",
            str(payload / "node_modules" / "playwright" / "cli.js"),
            "install",
            "chromium",
        ],
        cwd=payload,
        env=env,
    )
    if not any(browsers.glob("chromium-*")):
        raise RuntimeError(f"Chromium was not downloaded for {playwright_platform}")


def install_linux_runtime_libraries(payload: Path) -> None:
    """Bundle the shared libraries absent from a minimal Ubuntu 24.04/WSL install."""
    if shutil.which("apt-get") is None or shutil.which("dpkg-deb") is None:
        raise RuntimeError("Linux dependency packaging requires apt-get and dpkg-deb")
    download_dir = payload.parent / "linux-debs"
    download_dir.mkdir(parents=True, exist_ok=True)
    run(["apt-get", "download", *LINUX_RUNTIME_PACKAGES], cwd=download_dir)
    debs = sorted(download_dir.glob("*.deb"))
    if len(debs) != len(LINUX_RUNTIME_PACKAGES):
        raise RuntimeError("not all Linux Chromium runtime packages were downloaded")
    sysroot = payload / "linux-sysroot"
    for archive in debs:
        run(["dpkg-deb", "--extract", str(archive), str(sysroot)], cwd=download_dir)
    required = (
        sysroot / "usr/lib/x86_64-linux-gnu/libnspr4.so",
        sysroot / "usr/lib/x86_64-linux-gnu/libnss3.so",
        sysroot / "usr/lib/x86_64-linux-gnu/libasound.so.2",
    )
    missing = [str(path) for path in required if not path.exists()]
    if missing:
        raise RuntimeError(f"Linux Chromium runtime library missing: {', '.join(missing)}")


def write_bundle_manifest(payload: Path, target: str, version: str) -> None:
    target_config = TARGETS[target]
    playwright_package = json.loads(
        (payload / "node_modules" / "playwright" / "package.json").read_text(encoding="utf-8")
    )
    manifest = {
        "schemaVersion": 1,
        "platform": target_config["manifest_platform"],
        "arch": target_config["manifest_arch"],
        "version": version,
        "playwrightVersion": playwright_package.get("version", ""),
    }
    (payload / "bundle-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def zip_payload(payload: Path, destination: Path, *, preserve_symlinks: bool) -> None:
    """Create a root-layout ZIP while preserving Unix symlinks and modes."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        destination.unlink()
    with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for current_root, dirnames, filenames in os.walk(payload, followlinks=False):
            dirnames.sort()
            filenames.sort()
            root = Path(current_root)
            entries = [root / name for name in dirnames + filenames]
            for entry in entries:
                relative = entry.relative_to(payload).as_posix()
                file_stat = entry.lstat()
                if stat.S_ISLNK(file_stat.st_mode):
                    if preserve_symlinks:
                        info = zipfile.ZipInfo(relative)
                        info.create_system = 3
                        info.external_attr = (stat.S_IFLNK | 0o777) << 16
                        archive.writestr(info, os.readlink(entry))
                    else:
                        resolved = entry.resolve(strict=True)
                        if not resolved.is_file():
                            raise RuntimeError(f"cannot dereference non-file Windows symlink: {entry}")
                        archive.write(resolved, relative)
                elif entry.is_file():
                    archive.write(entry, relative)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_archive(path: Path, target: str) -> None:
    executable_suffix = (
        "/chrome-headless-shell.exe"
        if target == "windows-x64"
        else "/chrome-headless-shell"
    )
    with zipfile.ZipFile(path) as archive:
        bad_member = archive.testzip()
        if bad_member:
            raise RuntimeError(f"corrupt ZIP member: {bad_member}")
        names = archive.namelist()
        required = {
            "bundle-manifest.json",
            "html_to_pptx.mjs",
            "package.json",
        }
        missing = sorted(required.difference(names))
        if missing:
            raise RuntimeError(f"bundle is missing root files: {', '.join(missing)}")
        if not any(name.startswith("node_modules/playwright/") for name in names):
            raise RuntimeError("bundle is missing node_modules/playwright")
        if not any(name.startswith("node_modules/pptxgenjs/") for name in names):
            raise RuntimeError("bundle is missing node_modules/pptxgenjs")
        if not any(name.endswith(executable_suffix) for name in names):
            raise RuntimeError(f"bundle is missing target Chromium executable: {executable_suffix}")
        manifest = json.loads(archive.read("bundle-manifest.json"))
        expected = TARGETS[target]
        if manifest.get("platform") != expected["manifest_platform"] or manifest.get("arch") != expected["manifest_arch"]:
            raise RuntimeError(f"bundle manifest does not match target {target}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Download Chromium and build uploadable editable-PPT dependency ZIP files."
    )
    parser.add_argument(
        "--target",
        action="append",
        choices=[*TARGETS, "all"],
        help="Target to build; repeat for multiple targets (default: all).",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--version", default="")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the resolved output plan without downloading anything.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    requested = args.target or ["all"]
    targets = list(TARGETS) if "all" in requested else list(dict.fromkeys(requested))
    version = args.version.strip() or read_exporter_version()
    output_dir = args.output_dir.expanduser().resolve()
    base_url = args.base_url.rstrip("/") + "/"

    print(f"Exporter source: {EXPORTER_ROOT}")
    print(f"Output directory: {output_dir}")
    print(f"Version: {version}")
    print(f"Targets: {', '.join(targets)}")
    for target in targets:
        print(f"  - lazymind-editable-ppt-{target}-{version}.zip")
    if args.dry_run:
        return 0

    if not EXPORTER_ROOT.is_dir():
        raise FileNotFoundError(EXPORTER_ROOT)
    if shutil.which("node") is None or shutil.which("npm") is None:
        raise RuntimeError("node and npm must be available on PATH")

    work_dir = output_dir / ".work"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    common_payload = work_dir / "common"
    copy_exporter_source(common_payload)
    install_node_dependencies(common_payload)

    checksums: dict[str, str] = {}
    config_path = output_dir / "editable-ppt-dependencies.json"
    config: dict[str, object] = {"schemaVersion": 1}
    if config_path.is_file():
        try:
            previous = json.loads(config_path.read_text(encoding="utf-8"))
            for target_config in TARGETS.values():
                key = target_config["config_key"]
                if isinstance(previous.get(key), dict):
                    config[key] = previous[key]
        except (OSError, json.JSONDecodeError):
            pass
    for target in targets:
        print(f"\n==> Building {target}", flush=True)
        payload = work_dir / target / "payload"
        shutil.copytree(common_payload, payload, symlinks=True)
        install_target_browser(payload, TARGETS[target]["playwright_platform"])
        if target == "linux-x64":
            install_linux_runtime_libraries(payload)
        write_bundle_manifest(payload, target, version)

        filename = f"lazymind-editable-ppt-{target}-{version}.zip"
        archive_path = output_dir / filename
        zip_payload(
            payload,
            archive_path,
            preserve_symlinks=TARGETS[target]["manifest_platform"] != "windows",
        )
        validate_archive(archive_path, target)
        checksum = sha256_file(archive_path)
        checksums[filename] = checksum
        config[TARGETS[target]["config_key"]] = {
            "url": urljoin(base_url, filename),
            "sha256": checksum,
        }
        print(f"Created: {archive_path}")
        print(f"SHA256:  {checksum}")

    for target, target_config in TARGETS.items():
        config.setdefault(target_config["config_key"], {"url": "", "sha256": ""})

    # Include all retained archives in the checksum inventory, including a
    # second platform built by an earlier single-target invocation.
    for archive_path in sorted(output_dir.glob("lazymind-editable-ppt-*.zip")):
        checksums.setdefault(archive_path.name, sha256_file(archive_path))

    release_env: dict[str, str] = {}
    for target, target_config in TARGETS.items():
        entry = config.get(target_config["config_key"])
        if not isinstance(entry, dict) or not entry.get("url") or not entry.get("sha256"):
            continue
        env_prefix = ENV_PREFIXES[target]
        release_env[f"{env_prefix}_URL"] = str(entry["url"])
        release_env[f"{env_prefix}_SHA256"] = str(entry["sha256"])

    (output_dir / "SHA256SUMS.txt").write_text(
        "".join(f"{checksum}  {filename}\n" for filename, checksum in sorted(checksums.items())),
        encoding="utf-8",
    )
    (output_dir / "editable-ppt-dependencies.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (output_dir / "editable-ppt-dependencies.env").write_text(
        "".join(f"{key}={value}\n" for key, value in sorted(release_env.items())),
        encoding="utf-8",
    )
    (output_dir / "editable-ppt-dependencies.ps1").write_text(
        "".join(f'$env:{key} = "{value}"\n' for key, value in sorted(release_env.items())),
        encoding="utf-8",
    )
    shutil.rmtree(work_dir)

    print("\nUpload the ZIP files, then load the generated .env/.ps1 file before the Desktop release build.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
