# /// script
# requires-python = ">=3.13"
# dependencies = [
#     "requests",
# ]
# ///

import json
import pathlib
import platform
import shutil
import subprocess
import tarfile
# import zipfile

import requests

zig_version_json_url = "https://ziglang.org/download/index.json"
zig_platform_key = platform.machine().lower() + "-" + platform.system().lower()
target_dir = pathlib.Path("~/.local/share/mise/installs/zig/").expanduser()

zls_version_json_url = "https://releases.zigtools.org/v1/zls/select-version?zig_version={}&compatibility=only-runtime"


def extract_tar_strip_leading_dir(tar_file, extract_dir, mode, strip_components=1):
    """
    Extracts the contents of a .tar.xz file, stripping the specified number of
    leading directory components from the extracted file paths.

    Args:
      tar_xz_file: Path to the .tar.xz file.
      extract_dir: Path to the directory where the files should be extracted.
      strip_components: Number of leading directory components to strip.
                        Defaults to 1.

    Raises:
      FileNotFoundError: If the tar_xz_file is not found.
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

                tar.extract(member, path=extract_dir)
            print(f"Successfully extracted {tar_file} to {extract_dir}")

    except FileNotFoundError:
        print(f"Error: {tar_file} not found.")
    except Exception as e:
        print(f"An error occurred during extraction: {e}")


def main() -> None:
    zig_version_json = requests.get(zig_version_json_url).json()
    # print(json.dumps(zig_version_json['master'], indent=4))
    zig_version_master = zig_version_json["master"]["version"]

    zig_dev_latest_dir = target_dir / "dev-latest"
    zig_dev_latest = zig_dev_latest_dir / "bin/zig"
    old_zig_dir = None
    if zig_dev_latest.exists():
        zig_version_current = (
            subprocess.run([zig_dev_latest, "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
        )
    else:
        zig_version_current = subprocess.run(["zig", "version"], stdout=subprocess.PIPE).stdout.decode("UTF-8").strip()
    print(f"Master Version: {zig_version_master}")
    print(f"Current Version: {zig_version_current}")
    new_version_available = zig_version_current < zig_version_master
    if new_version_available:
        print(f"New Version Available?: {zig_version_current < zig_version_master}")
        zig_file_master = zig_version_json["master"][zig_platform_key]["tarball"]

        if zig_file_master.endswith(".tar.xz"):
            zig_file = pathlib.Path("zig.tar.xz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:xz"
        elif zig_file_master.endswith(".tar.gz"):
            zig_file = pathlib.Path("zig.tar.gz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:gz"
        # elif zig_file_master.endswith('.zip'):
        #     zig_file = pathlib.Path('zig.zip')
        #     # TODO: no clue if we need to strip leading dir here
        #     opener = zipfile.open
        #     open_mode = 'r'
        else:
            raise Exception(f"Unknown file type: {zig_file_master}")

        print(f"Downloading {zig_file_master}")
        # Download the file
        response = requests.get(zig_file_master, stream=True)
        with zig_file.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        print(f"Extracting {zig_file} to {target_dir}")
        # Extract the file to ~/.local/share/mise/zig/{zig_version_master}
        try:
            dest_dir = pathlib.Path(target_dir) / zig_version_master
            # dest_dir.mkdir(parents=True, exist_ok=True)
            extract(zig_file, dest_dir, open_mode)
            # symlink the new version to ~/.local/share/mise/zig/dev-latest
            print(f"Symlinking {dest_dir} to {zig_dev_latest_dir}")
            if zig_dev_latest_dir.exists():
                old_zig_dir = zig_dev_latest_dir.resolve()
                zig_dev_latest_dir.unlink()
            zig_dev_latest_dir.symlink_to(dest_dir, target_is_directory=True)
            zig_dev_latest_bin = zig_dev_latest_dir / "bin"
            if not zig_dev_latest_bin.exists():
                zig_dev_latest_bin.mkdir(parents=True)
                zig_dev_latest.symlink_to(dest_dir / "zig")
            zig_file.unlink()
        except FileExistsError:
            print("File already exists")
        except Exception as e:
            print(e)
    else:
        print("No New Zig Version Available")

    # ZLS

    print("Checking for ZLS")
    zls_dev_latest = zig_dev_latest_dir / "bin/zls"
    if not zls_dev_latest.exists():
        print("ZLS not found, retrieving correct version")
        zls_version_json = requests.get(zls_version_json_url.format(zig_version_master.replace("+", "%2B"))).json()
        # print(json.dumps(zls_version_json, indent=4))
        zls_tar = zls_version_json[zig_platform_key]["tarball"]
        if zls_tar.endswith(".tar.xz"):
            zls_file = pathlib.Path("zls.tar.xz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:xz"
        elif zls_tar.endswith(".tar.gz"):
            zls_file = pathlib.Path("zls.tar.gz")
            extract = extract_tar_strip_leading_dir
            open_mode = "r:gz"
        # elif zls_tar.endswith('.zip'):
        #     zls_file = pathlib.Path('zls.zip')
        else:
            raise Exception(f"Unknown file type: {zls_file}")

        print(f"Downloading {zls_tar}")
        # Download the file
        response = requests.get(zls_tar, stream=True)
        with zls_file.open("wb") as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        zls_dev_latest_dir = zig_dev_latest_dir / "zls"
        print(f"Extracting {zls_file} to {zls_dev_latest_dir}")
        # Extract the file to ~/.local/share/mise/zig/{zig_version_master}
        try:
            if not zls_dev_latest_dir.exists():
                zls_dev_latest_dir.mkdir(parents=True)
            extract(zls_file, zls_dev_latest_dir, open_mode, strip_components=0)
            zls_dev_latest.symlink_to(zls_dev_latest_dir / "zls")
            zls_file.unlink()
        except FileExistsError:
            print("File already exists")
        except Exception as e:
            print(e)

    if old_zig_dir:
        # remove the old zig version
        print(f"Removing old zig version: {old_zig_dir}")
        shutil.rmtree(old_zig_dir)


if __name__ == "__main__":
    main()
