import click
import mailbox
import json
import os
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

# The files that carry state from one build to the next. An incremental build
# needs all of them: each one is rewritten wholesale at the end of a run, so a
# missing file would silently drop everything a previous run recorded.
STATE_FILES = ("index.json", "addresses.json", "search_index.json", "id_mapping.json")

# Directories generated from the Maildir
GENERATED_DIRS = ("emails", "attachments")


class IncompleteBuild(click.ClickException):
    """Raised when the output directory holds a partial or unreadable build."""

    def __init__(self, reason: str):
        super().__init__(f"{reason}\nRe-run with --rebuild to clear the output directory and start over.")


def clear_output(output_path: Path) -> None:
    """Remove everything a previous run generated, leaving anything else alone."""
    removed = []

    for name in GENERATED_DIRS:
        target = output_path / name
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(f"{name}/")

    for name in STATE_FILES:
        target = output_path / name
        if target.is_file():
            target.unlink()
            removed.append(name)

    if removed:
        logger.info(f"Cleared previous build: {', '.join(removed)}")
    else:
        logger.info("Nothing to clear; output directory holds no previous build.")


def reopen_index_for_append(index_file: Path) -> bool:
    """
    Strip the closing bracket off an existing index.json so more entries can be
    appended to the array. Returns True if the array already holds entries.
    """
    whitespace = b" \t\r\n"

    with index_file.open("r+b") as f:
        size = f.seek(0, os.SEEK_END)

        # Scan backwards for the closing bracket
        bracket = -1
        pos = size
        while pos > 0 and bracket < 0:
            start = max(0, pos - 4096)
            f.seek(start)
            chunk = f.read(pos - start)
            found = chunk.rfind(b"]")
            if found >= 0:
                bracket = start + found
            pos = start

        if bracket < 0:
            raise IncompleteBuild(f"{index_file} is not a complete JSON array.")

        # The last non-whitespace byte before the bracket tells us whether the
        # array had any entries: '[' means it was empty.
        has_entries = False
        pos = bracket
        while pos > 0:
            start = max(0, pos - 4096)
            f.seek(start)
            chunk = f.read(pos - start).rstrip(whitespace)
            if chunk:
                has_entries = not chunk.endswith(b"[")
                break
            pos = start

        f.truncate(bracket)

    return has_entries


def load_state(output_path: Path) -> tuple[bool, set, int]:
    """
    Prepare the output directory for an incremental build.

    Returns (incremental, addresses, initial_count) where addresses holds the
    autocomplete entries recorded so far and initial_count is the number of
    indexes already handed out by previous runs.
    """
    present = [name for name in STATE_FILES if (output_path / name).is_file()]

    if not present:
        return False, set(), 0

    if len(present) != len(STATE_FILES):
        missing = [name for name in STATE_FILES if name not in present]
        raise IncompleteBuild(
            f"{output_path} holds a partial build; missing {', '.join(missing)}."
        )

    try:
        initial_count = hail.Hail.load_id_idx(output_path)
        with open(output_path / "addresses.json", "r", encoding="utf-8") as f:
            addresses = set(json.load(f))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        raise IncompleteBuild(f"Could not read the previous build in {output_path}: {e}")

    logger.info(
        f"Resuming build in {output_path}: {initial_count} emails and "
        f"{len(addresses)} addresses already indexed."
    )
    return True, addresses, initial_count


def parse_maildir(maildir_path: Path, output_path: Path) -> None:
    """Parse Maildir and extract email data, building indexes incrementally."""
    incremental, addresses, initial_count = load_state(output_path)

    maildir = mailbox.Maildir(str(maildir_path))
    total_messages = len(maildir)
    logger.info(f"Found {total_messages} messages in Maildir: {maildir_path}")

    # Create directories for email data and attachments
    emails_dir = output_path / "emails"
    attachments_dir = output_path / "attachments"
    emails_dir.mkdir(exist_ok=True)
    attachments_dir.mkdir(exist_ok=True)

    # Emails written out by a previous run; anything missing from here gets
    # rebuilt. Only consulted for indexes a previous run handed out: a file left
    # over from anything else is meaningless and gets overwritten.
    existing_files = {f.name for f in emails_dir.iterdir() if f.is_file()}

    # Indexes handed out during this run, to skip duplicate Message-IDs
    built_this_run = set()

    # Create files for incremental index building
    index_file = output_path / "index.json"

    if incremental:
        # Reopen the existing array instead of starting a new one
        first_index_item = not reopen_index_for_append(index_file)
    else:
        # Initialize index file with an opening bracket
        with open(index_file, "w", encoding="utf-8") as f:
            f.write("[\n")
        first_index_item = True

    # Create incremental inverted index
    inverted_index = InvertedIndex(output_path, load_existing=incremental)

    added = 0
    rebuilt = 0
    skipped = 0

    # Process each message with progress bar
    with click.progressbar(
        maildir.iteritems(),
        length=total_messages,
        label='Processing emails',
        item_show_func=lambda x: f"Email {x[0] if x else ''}" if x else ""
    ) as bar:
        for key, msg in bar:
            h = None
            try:
                # Create Hail instance for the message; a message seen by an
                # earlier run keeps the index it was given then.
                h = hail.Hail(msg)

                if h.idx < initial_count:
                    # Already in the indexes from an earlier run
                    if h.filename in existing_files:
                        skipped += 1
                        continue
                    # Its file is gone: put the file back, leaving the indexes
                    # (which already describe it) alone.
                    h.save_attachments(attachments_dir)
                    h.save(emails_dir)
                    existing_files.add(h.filename)
                    rebuilt += 1
                    continue

                if h.idx in built_this_run:
                    # Duplicate Message-ID within this run
                    skipped += 1
                    continue

                # Update the global addresses set with extracted addresses
                addresses.update(h.addresses)

                # Save attachments if any
                h.save_attachments(attachments_dir)

                h.save(emails_dir)

                # Add to inverted search index
                inverted_index.add_email(h)

                # Add to main index
                with open(index_file, "a", encoding="utf-8") as f:
                    if not first_index_item:
                        f.write(",\n")
                    json.dump(h.index_data, f, ensure_ascii=False, indent=None)
                    first_index_item = False

                built_this_run.add(h.idx)
                added += 1

            except Exception as e:
                logger.error(f"Error processing message {key}: {e}", exc_info=True)
                if h is not None and h.idx >= initial_count and h.idx not in built_this_run:
                    # It never made it into the indexes, so drop the id and any
                    # half-written file and let the next run try again instead
                    # of assuming it was done.
                    hail.Hail.forget(h.original_id)
                    (emails_dir / h.filename).unlink(missing_ok=True)
                continue

    # Close index files with closing brackets
    with open(index_file, "a", encoding="utf-8") as f:
        f.write("\n]")

    # Save addresses for autocomplete
    with open(output_path / "addresses.json", "w", encoding="utf-8") as f:
        json.dump(sorted(addresses), f, ensure_ascii=False, indent=None)

    # Finalize the inverted index
    inverted_index.save()
    hail.Hail.save_id_idx(output_path)

    # Log completion statistics
    email_count = len(hail.Hail.d)
    address_count = len(addresses)
    logger.info(
        f"Added {added} new emails, rebuilt {rebuilt} missing files, "
        f"skipped {skipped} already built."
    )
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
@click.option(
    "--rebuild",
    "--clear",
    "rebuild",
    is_flag=True,
    help="Clear the previously generated files from the output directory and build everything again.",
)
def main(maildir_path: str, output_path: str, rebuild: bool) -> None:
    """
    Convert a Maildir archive to a static, searchable HTML site.

    Only emails missing from the output directory are built, so the command can
    be re-run as the Maildir grows. Use --rebuild to start from scratch.
    """
    logger.info("Starting Maildir conversion process")
    logger.info(f"Input Maildir path: {maildir_path}")
    logger.info(f"Output directory: {output_path}")

    maildir_path_obj = Path(maildir_path)
    output_path_obj = Path(output_path)

    # Ensure output directory exists
    output_path_obj.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Created output directory: {output_path}")

    if rebuild:
        logger.info("Rebuilding from scratch...")
        clear_output(output_path_obj)

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
