"""Main entry point for the VGNC download file generator."""

from . import __version__


def main() -> None:
    """Main entry point for the CLI."""
    print(f"VGNC Download File Generator v{__version__}")


if __name__ == "__main__":
    main()
