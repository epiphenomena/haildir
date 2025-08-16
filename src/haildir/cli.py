import click
import os
import sys
from pathlib import Path

@click.command()
@click.argument('maildir_path', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
@click.argument('output_path', type=click.Path(file_okay=False, dir_okay=True, resolve_path=True))
def main(maildir_path: str, output_path: str) -> None:
    """Convert a Maildir archive to a static, searchable HTML site."""
    maildir_path = Path(maildir_path)
    output_path = Path(output_path)
    
    # Ensure output directory exists
    output_path.mkdir(parents=True, exist_ok=True)
    
    # TODO: Implement maildir parsing, indexing, and site generation
    click.echo(f"Processing Maildir: {maildir_path}")
    click.echo(f"Output directory: {output_path}")
    click.echo("This is a placeholder. Implementation will be added in subsequent steps.")

if __name__ == '__main__':
    main()
