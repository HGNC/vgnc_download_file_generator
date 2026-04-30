#!/usr/bin/env python3
"""Fix mysqlclient library path on macOS.

On macOS with MySQL 9.x, mysqlclient may be built looking for libmysqlclient.21.dylib
but MySQL 9.x provides libmysqlclient.24.dylib. This script uses install_name_tool
to fix the library path.

Run this after installing mysqlclient:
    uv pip install mysqlclient
    python scripts/fix_mysqlclient.py
"""

import subprocess
import sys
from pathlib import Path


def find_mysqlclient_so() -> Path | None:
    """Find the mysqlclient .so file in the current environment."""
    for site_packages in Path(sys.prefix).glob("lib/python*/site-packages"):
        for so_file in site_packages.glob("MySQLdb/_mysql*.so"):
            return so_file
    return None


def find_mysql_dylib() -> Path | None:
    """Find the MySQL client dylib on the system."""
    candidate_paths = [
        "/opt/homebrew/opt/mysql-client/lib/libmysqlclient.dylib",
        "/opt/homebrew/opt/mysql/lib/libmysqlclient.dylib",
        "/usr/local/mysql/lib/libmysqlclient.dylib",
    ]
    for path in candidate_paths:
        if Path(path).exists():
            return Path(path)

    # Try to find any version
    for pattern in ["/opt/homebrew/opt/mysql-client/lib/libmysqlclient.*.dylib"]:
        matches = list(Path("/").glob(pattern[1:]))
        if matches:
            return matches[0]

    return None


def get_linked_libraries(so_file: Path) -> list[str]:
    """Get the list of linked libraries using otool."""
    result = subprocess.run(
        ["otool", "-L", str(so_file)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []

    libraries = []
    for line in result.stdout.splitlines()[1:]:
        line = line.strip()
        if line.startswith("@rpath/libmysqlclient"):
            libraries.append(line.split()[0])
    return libraries


def fix_library_path(so_file: Path, old_path: str, new_path: Path) -> bool:
    """Fix the library path using install_name_tool."""
    result = subprocess.run(
        ["install_name_tool", "-change", old_path, str(new_path), str(so_file)],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def main() -> int:
    if sys.platform != "darwin":
        print("This script is only needed on macOS.")
        return 0

    so_file = find_mysqlclient_so()
    if not so_file:
        print("ERROR: Could not find mysqlclient .so file")
        print("Make sure mysqlclient is installed: uv pip install mysqlclient")
        return 1

    print(f"Found mysqlclient: {so_file}")

    linked = get_linked_libraries(so_file)
    if not linked:
        print("No @rpath/libmysqlclient references found - nothing to fix")
        return 0

    mysql_dylib = find_mysql_dylib()
    if not mysql_dylib:
        print("ERROR: Could not find MySQL client library")
        print("Install mysql-client: brew install mysql-client")
        return 1

    print(f"Found MySQL client: {mysql_dylib}")

    for old_path in linked:
        print(f"Fixing: {old_path} -> {mysql_dylib}")
        if not fix_library_path(so_file, old_path, mysql_dylib):
            print(f"ERROR: Failed to fix {old_path}")
            return 1

    print("Successfully fixed mysqlclient library paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
