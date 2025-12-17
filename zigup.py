#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.6"
# dependencies = [
#     "requests",
# ]
# ///
import argparse
import json
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile

import requests

__version__ = "0.2.0"

zig_version_json_url = "https://ziglang.org/download/index.json"
zig_platform_key = platform.machine().lower() + "-" + platform.system().lower()
target_dir = pathlib.Path("~/.local/share/mise/installs/zig/").expanduser()

zls_version_json_url = "https://releases.zigtools.org/v1/zls/select-version?zig_version={}&compatibility=only-runtime"


def parse_zig_version(version_str):
    """
    Parse a Zig version string like '0.15.0-dev.1145+3ae0ba096' into comparable components.
    Returns a tuple: (major, minor, patch, is_dev, dev_build_num, commit_hash)
    """
    # Pattern for Zig version: major.minor.patch[-dev.build_num][+commit_hash]
    pattern = r'^(\d+)\.(\d+)\.(\d+)(?:-dev\.(\d+))?(?:\+([a-f0-9]+))?$'
    match = re.match(pattern, version_str)

    if not match:
        # Fallback to string comparison for unexpected formats
        return (0, 0, 0, False, 0, version_str)

    major, minor, patch, dev_build, commit = match.groups()

    return (
        int(major),
        int(minor),
        int(patch),
        dev_build is not None,  # is_dev
        int(dev_build) if dev_build else 0,
        commit or ""
    )


def is_newer_version(current_version, latest_version):
    """
    Compare two Zig version strings to determine if latest is newer than current.
    Handles the Zig versioning scheme properly including dev builds.
    """
    current = parse_zig_version(current_version)
    latest = parse_zig_version(latest_version)

    # Compare major.minor.patch first
    if current[:3] != latest[:3]:
        return current[:3] < latest[:3]

    # Same base version, check dev status
    current_is_dev, latest_is_dev = current[3], latest[3]

    # Release > dev build (e.g., 0.15.0 > 0.15.0-dev.1145)
    if not current_is_dev and latest_is_dev:
        return False
    if current_is_dev and not latest_is_dev:
        return True

    # Both are dev builds, compare build numbers
    if current_is_dev and latest_is_dev:
        return current[4] < latest[4]

    # Both are releases with same version - no update needed
    return False


def extract_tar_strip_leading_dir(tar_file, extract_dir, mode, strip_components=1):
    """
    Extracts the contents of a .tar{.xz,.gz} file, stripping the specified number of
    leading directory components from the extracted file paths.

    Args:
      tar_file: Path to the tar file.
      extract_dir: Path to the directory where the files should be extracted.
      strip_components: Number of leading directory components to strip.
                        Defaults to 1.

    Raises:
      FileNotFoundError: If the tar_file is not found.
      Exception: If any other error occurs during extraction.
    """
    try:
        with tarfile.open(tar_file, mode) as tar:
            for member in tar.getmembers():
                # Get the path components as a list
                path_components = pathlib.Path(member.name).parts

                # Strip the specified number of leading components
                stripped_path_components = path_components[strip_components:]

                # Reconstruct the path with the stripped components
                member.name = str(pathlib.Path(*stripped_path_components))

                tar.extract(member, path=extract_dir, filter='data')
            print(f"Successfully extracted {tar_file} to {extract_dir}")

    except FileNotFoundError:
        print(f"Error: {tar_file} not found.")
    except Exception as e:
        print(f"An error occurred during extraction: {e}")


def main() -> int:
    # process command line arguments
    parser = argparse.ArgumentParser(
        description="Install or update Zig and ZLS dev-latest into mise/installs/zig",
        epilog="It's not super smart and has only been tested on Linux so far.",
    )
    parser.add_argument("--version", "-V", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--verbose", "-v", action="count", default=0, help="Increase verbosity")
    args = parser.parse_args()

    # Check to make sure mise is installed
    try:
        installed = subprocess.run(["mise", "version"], check=True, stdout=subprocess.PIPE).returncode == 0
    except FileNotFoundError:
        installed = False
    if not installed:
        print("mise is not installed, please install it first.")
        return 1

    # Verfiy target directory exists
    target_dir.mkdir(parents=True, exist_ok=True)

    zig_version_json = requests.get(zig_version_json_url).json()
    if args.verbose > 1:
        print(json.dumps(zig_version_json, indent=4))
    zig_version_master = zig_version_json["master"]["version"]

    zig_dev_latest_dir = target_dir / "dev-latest"
    zig_dev_latest = zig_dev_latest_dir / "bin/zig"
    old_zig_dir = None

    # Check if dev-latest symlink exists (even if broken) and is valid
    if zig_dev_latest_dir.is_symlink():
        # Try to use the symlinked version if the target still exists
        if zig_dev_latest.exists():
            zig_version_current = (
                subprocess.run([zig_dev_latest, "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
            )
        else:
            # Symlink is broken, get version from system zig as fallback
            zig_version_current = subprocess.run(["zig", "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
    elif zig_dev_latest.exists():
        # dev-latest exists as a regular directory (not a symlink)
        zig_version_current = (
            subprocess.run([zig_dev_latest, "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
        )
    else:
        # No dev-latest at all, use system zig
        zig_version_current = subprocess.run(["zig", "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
    print(f"Installed Version: {zig_version_current}")
    print(f"   Latest Version: {zig_version_master}")
    new_version_available = is_newer_version(zig_version_current, zig_version_master)
    if new_version_available:
        if args.verbose > 0:
            print(f"New Version Available: {new_version_available}")
        zig_file_master = zig_version_json["master"][zig_platform_key]["tarball"]

        if zig_file_master.endswith(".tar.xz"):
            zig_file = pathlib.Path("zig.tar.xz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:xz"
        elif zig_file_master.endswith(".tar.gz"):
            zig_file = pathlib.Path("zig.tar.gz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:gz"
        else:
            raise Exception(f"Unknown file type: {zig_file_master}")

        if args.verbose > 0:
            print(f"Downloading {zig_file_master}")
        # Download the file
        response = requests.get(zig_file_master, stream=True)
        with zig_file.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Extracting {zig_file} to {target_dir}")
        # Extract the file to ~/.local/share/mise/zig/{zig_version_master}
        dest_dir = pathlib.Path(target_dir) / zig_version_master
        try:
            # dest_dir.mkdir(parents=True, exist_ok=True)
            extract(zig_file, dest_dir, open_mode)

            # Ensure bin/ directory exists and zig binary is accessible at bin/zig
            # Some Zig distributions have bin/zig, others have zig at root
            zig_bin_dir = dest_dir / "bin"
            zig_binary = dest_dir / "zig"
            zig_in_bin = zig_bin_dir / "zig"

            if not zig_bin_dir.exists():
                zig_bin_dir.mkdir(parents=True)

            if zig_binary.exists() and not zig_in_bin.exists():
                # Move zig binary to bin/ directory for consistency
                shutil.move(str(zig_binary), str(zig_in_bin))

            # symlink the new version to ~/.local/share/mise/zig/dev-latest
            if args.verbose > 0:
                print(f"Symlinking {dest_dir} to {zig_dev_latest_dir}")
            # Remove old symlink/directory, handling both valid and broken symlinks
            if zig_dev_latest_dir.is_symlink():
                # Save the old directory path before unlinking (only if target exists)
                try:
                    old_zig_dir = zig_dev_latest_dir.resolve(strict=True)
                except (OSError, RuntimeError):
                    # Broken symlink or resolution error
                    pass
                zig_dev_latest_dir.unlink()
            elif zig_dev_latest_dir.exists():
                # It's a regular directory, save and remove it
                old_zig_dir = zig_dev_latest_dir
            # Create new symlink
            zig_dev_latest_dir.symlink_to(dest_dir, target_is_directory=True)
            zig_file.unlink()
        except FileExistsError:
            print("File already exists")
        except Exception as e:
            print(e)
    else:
        print("Latest version already installed.")
        return 0

    # ZLS - Always reinstall when updating Zig to ensure compatibility

    if args.verbose > 0:
        print("Installing ZLS for Zig {}".format(zig_version_master))
    zls_dev_latest = zig_dev_latest_dir / "bin/zls"
    # Remove old ZLS if it exists
    if zls_dev_latest.is_symlink():
        zls_dev_latest.unlink()
    elif zls_dev_latest.exists():
        zls_dev_latest.unlink()

    zls_dev_latest_dir = zig_dev_latest_dir / "zls"
    if zls_dev_latest_dir.exists():
        shutil.rmtree(zls_dev_latest_dir)

    if args.verbose > 0:
        print("Retrieving compatible ZLS version")
    zls_version_json = requests.get(zls_version_json_url.format(zig_version_master.replace("+", "%2B"))).json()
    if args.verbose > 1:
        print(json.dumps(zls_version_json, indent=4))
    zls_tar = zls_version_json[zig_platform_key]["tarball"]
    if zls_tar.endswith(".tar.xz"):
        zls_file = pathlib.Path("zls.tar.xz")
        extract = extract_tar_strip_leading_dir
        open_mode = "r:xz"
    elif zls_tar.endswith(".tar.gz"):
        zls_file = pathlib.Path("zls.tar.gz")
        extract = extract_tar_strip_leading_dir
        open_mode = "r:gz"
    else:
        raise Exception(f"Unknown file type: {zls_file}")

    if args.verbose > 0:
        print(f"Downloading {zls_tar}")
    # Download the file
    response = requests.get(zls_tar, stream=True)
    with zls_file.open("wb") as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)

    if args.verbose > 0:
        print(f"Extracting {zls_file} to {zls_dev_latest_dir}")
    # Extract the file to the ZLS subdirectory
    try:
        zls_dev_latest_dir.mkdir(parents=True, exist_ok=True)
        extract(zls_file, zls_dev_latest_dir, open_mode, strip_components=0)

        # Find the ZLS binary and move it to bin/zls
        zls_binary_in_extract = zls_dev_latest_dir / "zls"
        if zls_binary_in_extract.exists():
            # Ensure bin directory exists in the actual installation (not through symlink)
            actual_bin_dir = dest_dir / "bin"
            actual_bin_dir.mkdir(parents=True, exist_ok=True)

            # Move ZLS binary to bin directory
            zls_target = actual_bin_dir / "zls"
            if zls_target.exists() or zls_target.is_symlink():
                zls_target.unlink()
            shutil.move(str(zls_binary_in_extract), str(zls_target))
            if args.verbose > 0:
                print(f"Installed ZLS to {zls_target}")
        else:
            print(f"Warning: ZLS binary not found in {zls_dev_latest_dir}")

        zls_file.unlink()
    except FileExistsError:
        print("ZLS file already exists")
    except Exception as e:
        print(f"Error installing ZLS: {e}")

    if old_zig_dir:
        # remove the old zig version
        if args.verbose > 0:
            print(f"Removing old zig version: {old_zig_dir}")
        shutil.rmtree(old_zig_dir)

    return 0


if __name__ == "__main__":
    sys.exit(main())
