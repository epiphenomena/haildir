import click
import mailbox
import json
from pathlib import Path
import shutil
import logging
from . import hail
from .search import InvertedIndex

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

def parse_maildir(maildir_path: Path, output_path: Path) -> None:
    """Parse Maildir and extract email data, building indexes incrementally."""
    maildir = mailbox.Maildir(str(maildir_path))
    total_messages = len(maildir)
    logger.info(f"Found {total_messages} messages in Maildir: {maildir_path}")

    # Create directories for email data and attachments
    emails_dir = output_path / "emails"
    attachments_dir = output_path / "attachments"
    emails_dir.mkdir(exist_ok=True)
    attachments_dir.mkdir(exist_ok=True)

    # Create files for incremental index building
    index_file = output_path / "index.json"
    addresses_file = output_path / "addresses.json"

    # Initialize index files with opening brackets
    with open(index_file, "w", encoding="utf-8") as f:
        f.write("[\n")

    # Track unique addresses for autocomplete
    addresses = set()

    # Track if we've written the first item to each index file
    first_index_item = True

    # Create incremental inverted index
    inverted_index = InvertedIndex(output_path)

    # Process each message with progress bar
    with click.progressbar(
        maildir.iteritems(),
        length=total_messages,
        label='Processing emails',
        item_show_func=lambda x: f"Email {x[0] if x else ''}" if x else ""
    ) as bar:
        for key, msg in bar:
            try:
                # Create Hail instance for the message
                try:
                    h = hail.Hail.from_maildir(msg)
                except hail.EmailAlreadyProcessed:
                    continue

                # Update the global addresses set with extracted addresses
                addresses.update(h.addresses)

                # Save attachments if any
                h.save_attachments(attachments_dir)

                h.save(emails_dir)

                # Add to main index
                with open(index_file, "a", encoding="utf-8") as f:
                    if not first_index_item:
                        f.write(",\n")
                    json.dump(h.index_data, f, ensure_ascii=False, indent=None)
                    first_index_item = False

                    # Add to inverted search index
                    inverted_index.add_email(h)

            except Exception as e:
                logger.error(f"Error processing message {key}: {e}", exc_info=True)
                continue

    # Close index files with closing brackets
    with open(index_file, "a", encoding="utf-8") as f:
        f.write("\n]")

    # Save addresses for autocomplete
    with open(addresses_file, "w", encoding="utf-8") as f:
        json.dump(list(addresses), f, ensure_ascii=False, indent=None)

    # Finalize the inverted index
    inverted_index.save()
    hail.Hail.save_id_idx(output_path)

    # Log completion statistics
    email_count = len(hail.Hail.ls)
    address_count = len(addresses)
    logger.info(
        f"Completed processing. Generated {email_count} email entries and {address_count} unique addresses."
    )


def copy_assets(output_path: Path) -> None:
    """Copy static assets to output directory."""
    assets_src = Path(__file__).parent / "assets"
    if assets_src.exists():
        for item in assets_src.iterdir():
            if item.is_file():
                shutil.copy2(item, output_path / item.name)


@click.command()
@click.argument(
    "maildir_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
)
@click.argument(
    "output_path", type=click.Path(file_okay=False, dir_okay=True, resolve_path=True)
)
def main(maildir_path: str, output_path: str) -> None:
    """Convert a Maildir archive to a static, searchable HTML site."""
    logger.info("Starting Maildir conversion process")
    logger.info(f"Input Maildir path: {maildir_path}")
    logger.info(f"Output directory: {output_path}")

    maildir_path_obj = Path(maildir_path)
    output_path_obj = Path(output_path)

    # Ensure output directory exists
    output_path_obj.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Created output directory: {output_path}")

    # Parse maildir
    logger.info("Starting email parsing...")
    parse_maildir(maildir_path_obj, output_path_obj)
    logger.info("Email parsing completed.")

    # Copy assets
    logger.info("Copying static assets...")
    copy_assets(output_path_obj)
    logger.info("Assets copied successfully.")

    # Count processed emails by counting files in emails directory
    emails_dir = output_path_obj / "emails"
    email_count = (
        len([f for f in emails_dir.iterdir() if f.is_file()])
        if emails_dir.exists()
        else 0
    )

    logger.info("Conversion completed successfully!")
    logger.info(f"Total emails processed: {email_count}")
    logger.info(f"Output saved to: {output_path}")


if __name__ == "__main__":
    main()
