"""Main entry point for the VGNC download file generator."""

import sys

import click
from rich.console import Console
from rich.progress import BarColumn, Progress, TaskID, TextColumn, TimeRemainingColumn

from vgnc_download_file_generator import __version__
from vgnc_download_file_generator.config import AppConfig, get_settings
from vgnc_download_file_generator.database.connection import DatabaseConnection
from vgnc_download_file_generator.generator import BaseFileGenerator
from vgnc_download_file_generator.generators import (
    VgncEnsembl,
    VgncPublic,
    VgncWithdrawn,
)
from vgnc_download_file_generator.models.species import SpeciesInfo
from vgnc_download_file_generator.writers.gcs_writer import GCSStreamWriter

console = Console()


@click.command()
@click.version_option(version=__version__)
@click.option(
    "--species",
    required=True,
    help="Species taxon ID (e.g., 9913 for cow) or 'All' for all species",
)
@click.option(
    "--chromosome",
    help="Chromosome identifier (e.g., 'X', '1', 'Un'). Required for chromosome-specific files.",
)
@click.option(
    "--locus-type",
    help="Locus type filter (e.g., 'gene with protein product')",
)
@click.option(
    "--locus-group",
    help="Locus group filter (e.g., 'protein-coding gene')",
)
@click.option(
    "--file-type",
    type=click.Choice(["vgnc_public", "vgnc_ensembl", "vgnc_withdrawn"], case_sensitive=False),
    default="vgnc_public",
    help="Type of file to generate (default: vgnc_public)",
)
@click.option(
    "--formats",
    default="tsv",
    help="Output formats: comma-separated list of 'tsv' and/or 'json' (default: tsv)",
)
@click.option(
    "--compress",
    is_flag=True,
    help="Enable gzip compression for output files",
)
@click.option(
    "--dry-run",
    is_flag=True,
    help="Show what would be generated without actually connecting to database or GCS",
)
@click.option(
    "--project-id",
    envvar="GCS_PROJECT_ID",
    help="Google Cloud project ID (or set GCS_PROJECT_ID env var)",
)
@click.option(
    "--bucket-name",
    envvar="GCS_BUCKET",
    help="GCS bucket name (or set GCS_BUCKET env var)",
)
@click.option(
    "--dbhost",
    envvar="DB_HOST",
    help="Database host (or set DB_HOST env var)",
)
@click.option(
    "--dbuser",
    envvar="DB_USER",
    help="Database user (or set DB_USER env var)",
)
@click.option(
    "--dbpass",
    envvar="DB_PASSWORD",
    help="Database password (or set DB_PASSWORD env var)",
)
@click.option(
    "--dbport",
    envvar="DB_PORT",
    type=int,
    help="Database port (or set DB_PORT env var)",
)
@click.option(
    "--dbname",
    envvar="DB_NAME",
    help="Database name (or set DB_NAME env var)",
)
def main(
    species: str,
    chromosome: str | None,
    locus_type: str | None,
    locus_group: str | None,
    file_type: str,
    formats: str,
    compress: bool,
    dry_run: bool,
    project_id: str,
    bucket_name: str,
    dbhost: str,
    dbuser: str,
    dbpass: str,
    dbport: int,
    dbname: str,
) -> None:
    """Generate VGNC download files and upload to GCS.

    Examples:

        # Generate TSV and JSON for cow chromosome X
        vgnc-download-file-generator --species 9913 --chromosome X --formats tsv,json

        # Generate all species files
        vgnc-download-file-generator --species All --formats tsv,json

        # Generate Ensembl mapping
        vgnc-download-file-generator --species All --file-type vgnc_ensembl
    """
    console.print(f"[bold blue]VGNC Download File Generator v{__version__}[/bold blue]")
    console.print()

    try:
        # Parse formats
        format_list = [f.strip().lower() for f in formats.split(",")]
        format_list = [f for f in format_list if f in ("tsv", "json")]
        if not format_list:
            console.print("[red]Error: At least one valid format (tsv or json) must be specified[/red]")
            sys.exit(1)

        # Handle dry-run mode early (skip config validation and database/GCS connection)
        if dry_run:
            console.print("[yellow]DRY RUN MODE - No files will be generated[/yellow]")
            console.print()

            # Parse species for dry-run display
            if species.lower() == "all":
                species_id: int | str = "All"
                display_name = "All"
            else:
                try:
                    species_id = int(species)
                    display_name = f"taxon_id {species_id}"
                except ValueError:
                    console.print(f"[red]Error: Invalid species ID '{species}'. Must be a number or 'All'[/red]")
                    sys.exit(1)

            # Show what would be generated
            console.print("[bold]Files that would be generated:[/bold]")
            console.print(f"  File Type: {file_type}")
            console.print(f"  Species: {display_name}")
            if chromosome:
                console.print(f"  Chromosome: {chromosome}")
            if locus_type:
                console.print(f"  Locus Type: {locus_type}")
            if locus_group:
                console.print(f"  Locus Group: {locus_group}")
            console.print(f"  Formats: {', '.join(format_list).upper()}")
            console.print(f"  Compression: {'Yes' if compress else 'No'}")
            console.print()
            console.print("[dim]Note: Run without --dry-run to actually generate files[/dim]")
            console.print("[dim]      (requires database and GCS configuration)[/dim]")
            sys.exit(0)

        # Load configuration from environment variables
        config = get_settings()

        # Override with CLI arguments if provided
        if project_id:
            config.gcs.project_id = project_id
        if bucket_name:
            config.gcs.bucket_name = bucket_name
        if dbhost:
            config.database.dbhost = dbhost
        if dbuser:
            config.database.dbuser = dbuser
        if dbpass:
            config.database.dbpasswd = dbpass
        if dbport:
            config.database.dbport = dbport
        if dbname:
            config.database.dbname = dbname

        # Validate configuration
        if not config.gcs.project_id or not config.gcs.bucket_name:
            console.print("[red]Error: GCS configuration missing. Set --project-id and --bucket-name or use env vars[/red]")
            sys.exit(1)

        if not config.database.dbhost or not config.database.dbuser:
            console.print("[red]Error: Database configuration missing. Set database credentials or use env vars[/red]")
            sys.exit(1)

        # Display configuration
        console.print("[bold]Configuration:[/bold]")
        console.print(f"  GCS Bucket: {config.gcs.bucket_name}")
        console.print(f"  Project ID: {config.gcs.project_id}")
        console.print(f"  Database: {config.database.dbhost}:{config.database.dbport}/{config.database.dbname}")
        console.print()

        # Initialize database connection
        console.print("[dim]Connecting to database...[/dim]")
        db = DatabaseConnection(config.database)

        # Initialize GCS writer
        console.print("[dim]Initializing GCS writer...[/dim]")
        if config.gcs.path_prefix:
            console.print(f"[dim]Using GCS path prefix: {config.gcs.path_prefix}[/dim]")
        gcs_writer = GCSStreamWriter(
            bucket_name=config.gcs.bucket_name,
            project_id=config.gcs.project_id,
            path_prefix=config.gcs.path_prefix,
        )

        # Parse species and get display name from database
        if species.lower() == "all":
            species_id: int | str = "All"
            display_name = "All"
        else:
            try:
                species_id = int(species)
                # Query database for actual species display name
                from vgnc_download_file_generator.database.queries import build_species_display_name_query, compile_query_for_mysql

                query = build_species_display_name_query(species_id)
                cursor = db.get_streaming_cursor()
                sql, params = compile_query_for_mysql(query)
                cursor.execute(sql, params)
                result = cursor.fetchone()
                cursor.close()

                if result and result[0]:
                    display_name = result[0]
                else:
                    console.print(f"[yellow]Warning: Species ID {species_id} not found in database. Using taxon_id as display name.[/yellow]")
                    display_name = f"taxon_id_{species_id}"
            except ValueError:
                console.print(f"[red]Error: Invalid species ID '{species}'. Must be a number or 'All'[/red]")
                sys.exit(1)

        # Create species info with actual display name from database
        species_info = SpeciesInfo(taxon_id=species_id, display_name=display_name, is_live="Y")

        # Create the appropriate generator
        generator_class: type[BaseFileGenerator]
        if file_type == "vgnc_ensembl":
            generator_class = VgncEnsembl
        elif file_type == "vgnc_withdrawn":
            generator_class = VgncWithdrawn
        else:  # vgnc_public
            generator_class = VgncPublic

        # Create generator instance
        generator = generator_class(
            db=db,
            species=species_info,
            chromosome=chromosome,
            locus_group=locus_group,
            locus_type=locus_type,
        )

        # Show what will be generated
        console.print("[bold]Generation Plan:[/bold]")
        console.print(f"  File Type: {file_type}")
        console.print(f"  Species: {display_name}")
        if chromosome:
            console.print(f"  Chromosome: {chromosome}")
        if locus_type:
            console.print(f"  Locus Type: {locus_type}")
        if locus_group:
            console.print(f"  Locus Group: {locus_group}")
        console.print(f"  Formats: {', '.join(format_list).upper()}")
        console.print(f"  Compression: {'Yes' if compress else 'No'}")
        console.print()

        # Generate files for each format
        for fmt in format_list:
            filename = generator.generate_filename(fmt)
            console.print(f"[bold]Generating {fmt.upper()} file:[/bold] {filename}")

            # Determine content type
            content_type = "text/tab-separated-values" if fmt == "tsv" else "application/json"

            # Compression is only applied when explicitly requested via --compress flag
            should_compress = compress

            # Show compression status
            if should_compress:
                console.print("[dim]  (compressed)[/dim]")

            if fmt == "tsv":
                # Check if TSV generator has data before opening GCS stream
                row_iterator = iter(generator.generate_tsv_rows())
                header_row = next(row_iterator, None)

                if header_row is None:
                    console.print(f"[dim]ℹ[/dim] No data found for {filename} - skipping GCS upload")
                    continue

                first_data_row = next(row_iterator, None)

                if first_data_row is None:
                    console.print(f"[dim]ℹ[/dim] No data found for {filename} - skipping GCS upload")
                    continue

                # Stream TSV directly to GCS
                with gcs_writer.open_write_stream(filename, content_type, compress=should_compress) as f:
                    lines_written = 0
                    with Progress(
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        TimeRemainingColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Writing rows...", total=None)

                        # Write header and first data row
                        f.write(header_row)
                        lines_written += 1
                        f.write(first_data_row)
                        lines_written += 1

                        for line in row_iterator:
                            f.write(line)
                            lines_written += 1
                            if lines_written % 1000 == 0:
                                progress.update(task, description=f"Writing rows... ({lines_written:,})")

                    console.print(f"[green]✓[/green] Wrote {lines_written:,} lines to {filename}")

                    # Create backward compatibility copy for "cow" -> "cattle"
                    if display_name.lower() == "cow":
                        try:
                            gcs_writer.create_backward_compatibility_copy(filename, legacy_species="cow")
                            console.print("[dim]  Created backward compatibility copy (cow -> cattle)[/dim]")
                        except Exception as e:
                            console.print(f"[yellow]  Warning: Failed to create backward compatibility copy: {e}[/yellow]")

            else:  # json
                # Check if JSON generator has data before opening GCS stream
                row_iterator = iter(generator.generate_json_rows())
                first_row = next(row_iterator, None)

                if first_row is None:
                    console.print(f"[dim]ℹ[/dim] No data found for {filename} - skipping GCS upload")
                    continue

                # Stream JSON directly to GCS
                with gcs_writer.open_write_stream(filename, content_type, compress=should_compress) as f:
                    rows_written = 0
                    with Progress(
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                        TimeRemainingColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("Writing rows...", total=None)

                        # Write opening bracket
                        f.write("[\n")
                        f.write(first_row)
                        rows_written = 1

                        for row_json in row_iterator:
                            f.write(",\n")
                            f.write(row_json)
                            rows_written += 1
                            if rows_written % 1000 == 0:
                                progress.update(task, description=f"Writing rows... ({rows_written:,})")

                        # Write closing bracket
                        f.write("\n]")

                    console.print(f"[green]✓[/green] Wrote {rows_written:,} rows to {filename}")

                    # Create backward compatibility copy for "cow" -> "cattle"
                    if display_name.lower() == "cow":
                        try:
                            gcs_writer.create_backward_compatibility_copy(filename, legacy_species="cow")
                            console.print("[dim]  Created backward compatibility copy (cow -> cattle)[/dim]")
                        except Exception as e:
                            console.print(f"[yellow]  Warning: Failed to create backward compatibility copy: {e}[/yellow]")

        console.print()
        console.print("[bold green]All files generated successfully![/bold green]")

    except KeyboardInterrupt:
        console.print("\n[yellow]Operation cancelled by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
