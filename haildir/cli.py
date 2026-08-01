import click
import mailbox
import json
import os
from pathlib import Path
import shutil
import logging
from . import hail
from . import search
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

# Maildir file -> email index, so a later run can skip a message without
# opening it. Optional: without it every message is read again, which is slow
# but correct, so an output directory built before this file existed still works.
SOURCES_FILE = "sources.json"

# The settings the search index was built with, so a later run can tell that it
# is being asked for something it cannot deliver incrementally. Optional: a
# build made before this file existed used the default.
BUILD_FILE = "build.json"

# Directories generated from the Maildir
GENERATED_DIRS = ("emails", "attachments")


class IncompleteBuild(click.ClickException):
    """Raised when the output directory holds a partial or unreadable build."""

    def __init__(self, reason: str):
        super().__init__(f"{reason}\nRe-run with --rebuild to clear the output directory and start over.")


def write_json(path: Path, data) -> None:
    """Write a JSON file by replacing it, so an interrupted run leaves the old one intact."""
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=None)
    os.replace(tmp, path)


def clear_output(output_path: Path) -> None:
    """Remove everything a previous run generated, leaving anything else alone."""
    removed = []

    for name in GENERATED_DIRS:
        target = output_path / name
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(f"{name}/")

    for name in STATE_FILES + (SOURCES_FILE, BUILD_FILE):
        target = output_path / name
        if target.is_file():
            target.unlink()
            removed.append(name)

    if removed:
        logger.info(f"Cleared previous build: {', '.join(removed)}")
    else:
        logger.info("Nothing to clear; output directory holds no previous build.")


def discard_temp_files(output_path: Path) -> None:
    """Drop the temporary files an interrupted run may have left behind."""
    for name in STATE_FILES + (SOURCES_FILE, BUILD_FILE):
        (output_path / f"{name}.tmp").unlink(missing_ok=True)


def find_closing_bracket(index_file: Path) -> tuple[int, bool]:
    """
    Locate the ']' that closes the array in index.json.

    Returns (offset, has_entries). Raises IncompleteBuild unless the file really
    does end with that bracket: a file left unclosed by an interrupted run must
    not be mistaken for a complete one, because every entry contains a ']' of
    its own and appending to the wrong one would destroy the file.
    """
    whitespace = b" \t\r\n"

    with index_file.open("rb") as f:
        size = f.seek(0, os.SEEK_END)

        # The last non-whitespace byte of the file has to be the closing bracket
        bracket = -1
        pos = size
        while pos > 0:
            start = max(0, pos - 4096)
            f.seek(start)
            chunk = f.read(pos - start).rstrip(whitespace)
            if chunk:
                if chunk.endswith(b"]"):
                    bracket = start + len(chunk) - 1
                break
            pos = start

        if bracket < 0:
            raise IncompleteBuild(
                f"{index_file} does not end in ']', so a previous run did not finish."
            )

        # The last non-whitespace byte before it tells us whether the array
        # holds any entries: '[' means it was empty.
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

    return bracket, has_entries


class IndexWriter:
    """
    Builds index.json off to the side and moves it into place at the end, so
    the existing file stays valid and servable for the whole run.
    """

    def __init__(self, index_file: Path, incremental: bool):
        self.index_file = index_file
        self.tmp_file = index_file.with_name(index_file.name + ".tmp")
        self.incremental = incremental
        self.f = None
        self.first_item = True

    def _start(self) -> None:
        if self.incremental:
            # Copy what previous runs recorded, minus the closing bracket
            bracket, has_entries = find_closing_bracket(self.index_file)
            with self.index_file.open("rb") as src, self.tmp_file.open("wb") as dst:
                remaining = bracket
                while remaining > 0:
                    chunk = src.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    dst.write(chunk)
                    remaining -= len(chunk)
            self.first_item = not has_entries
        else:
            with self.tmp_file.open("w", encoding="utf-8") as f:
                f.write("[\n")
            self.first_item = True

        self.f = self.tmp_file.open("a", encoding="utf-8")

    def add(self, entry) -> None:
        if self.f is None:
            self._start()
        if not self.first_item:
            self.f.write(",\n")
        json.dump(entry, self.f, ensure_ascii=False, indent=None)
        self.first_item = False

    def commit(self) -> None:
        """Close the array and put the finished file in place."""
        if self.f is None:
            self._start()
        self.f.write("\n]")
        self.f.close()
        self.f = None
        os.replace(self.tmp_file, self.index_file)

    def discard(self) -> None:
        """Throw the working copy away, leaving the existing index.json alone."""
        if self.f is not None:
            self.f.close()
            self.f = None
        self.tmp_file.unlink(missing_ok=True)


def load_state(output_path: Path) -> tuple[bool, set, int, dict, int]:
    """
    Prepare the output directory for an incremental build.

    Returns (incremental, addresses, initial_count, sources, result_limit) where
    addresses holds the autocomplete entries recorded so far, initial_count is
    the number of indexes already handed out by previous runs, sources maps
    Maildir files to the email index built from them, and result_limit is the
    posting-list limit the existing search index was built with.
    """
    present = [name for name in STATE_FILES if (output_path / name).is_file()]

    if not present:
        return False, set(), 0, {}, search.RESULT_LIMIT

    if len(present) != len(STATE_FILES):
        missing = [name for name in STATE_FILES if name not in present]
        raise IncompleteBuild(
            f"{output_path} holds a partial build; missing {', '.join(missing)}."
        )

    try:
        # Checked up front so a half-written index.json stops the run before it
        # does any work, rather than being appended to
        find_closing_bracket(output_path / "index.json")

        initial_count = hail.Hail.load_id_idx(output_path)
        with open(output_path / "addresses.json", "r", encoding="utf-8") as f:
            addresses = set(json.load(f))

        sources = {}
        sources_file = output_path / SOURCES_FILE
        if sources_file.is_file():
            with open(sources_file, "r", encoding="utf-8") as f:
                sources = json.load(f)
            if not isinstance(sources, dict):
                raise ValueError(f"{sources_file} is not a JSON object")

        # A build made before this file existed used the default
        result_limit = search.RESULT_LIMIT
        build_file = output_path / BUILD_FILE
        if build_file.is_file():
            with open(build_file, "r", encoding="utf-8") as f:
                settings = json.load(f)
            if not isinstance(settings, dict):
                raise ValueError(f"{build_file} is not a JSON object")
            recorded = settings.get("max_postings", result_limit)
            if not isinstance(recorded, int) or recorded < 1:
                raise ValueError(f"{build_file} has a bad max_postings: {recorded!r}")
            result_limit = recorded
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        raise IncompleteBuild(f"Could not read the previous build in {output_path}: {e}")

    logger.info(
        f"Resuming build in {output_path}: {initial_count} emails and "
        f"{len(addresses)} addresses already indexed."
    )
    if not sources:
        logger.info(
            f"No {SOURCES_FILE} yet, so every message has to be read this run; "
            "later runs will skip the ones already built."
        )

    return True, addresses, initial_count, sources, result_limit


def parse_maildir(
    maildir_path: Path, output_path: Path, result_limit: int, limit_given: bool
) -> None:
    """Parse Maildir and extract email data, building indexes incrementally."""
    discard_temp_files(output_path)
    incremental, addresses, initial_count, sources, built_limit = load_state(output_path)

    if incremental:
        # The words a previous run dropped were stored as empty lists and their
        # real posting lists were never written, so a different limit cannot be
        # applied to them without reading every message again. Accepting one
        # here would cap new words differently from old ones, which is worse
        # than refusing.
        if limit_given and result_limit != built_limit:
            raise click.ClickException(
                f"This build's search index was made with --max-postings {built_limit}. "
                f"Changing it to {result_limit} needs --rebuild, because the words the "
                "previous runs dropped cannot be recovered from the existing index."
            )
        result_limit = built_limit

    maildir = mailbox.Maildir(str(maildir_path))
    keys = maildir.keys()
    logger.info(f"Found {len(keys)} messages in Maildir: {maildir_path}")

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

    # Maildir files accounted for by the end of this run. Built up from scratch
    # rather than edited, so files that have left the Maildir drop out.
    new_sources = {}

    index_writer = IndexWriter(output_path / "index.json", incremental)
    inverted_index = InvertedIndex(
        output_path, load_existing=incremental, result_limit=result_limit
    )

    added = 0
    rebuilt = 0
    skipped = 0

    # Process each message with progress bar
    with click.progressbar(
        keys,
        length=len(keys),
        label='Processing emails',
        item_show_func=lambda x: f"Email {x}" if x else ""
    ) as bar:
        for key in bar:
            h = None
            try:
                # A file a previous run already built is skipped without being
                # opened, which is what makes a re-run cheap.
                known_idx = sources.get(key)
                if known_idx is not None and f"{known_idx}.json" in existing_files:
                    new_sources[key] = known_idx
                    skipped += 1
                    continue

                # Create Hail instance for the message; a message seen by an
                # earlier run keeps the index it was given then.
                h = hail.Hail(maildir[key])

                if h.idx < initial_count:
                    # Already in the indexes from an earlier run
                    if h.filename in existing_files:
                        new_sources[key] = h.idx
                        skipped += 1
                        continue
                    # Its file is gone: put the file back, leaving the indexes
                    # (which already describe it) alone.
                    h.save_attachments(attachments_dir)
                    h.save(emails_dir)
                    existing_files.add(h.filename)
                    new_sources[key] = h.idx
                    rebuilt += 1
                    continue

                if h.idx in built_this_run:
                    # Another copy of a message already built this run
                    new_sources[key] = h.idx
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
                index_writer.add(h.index_data)

                built_this_run.add(h.idx)
                new_sources[key] = h.idx
                added += 1

            except Exception as e:
                logger.error(f"Error processing message {key}: {e}", exc_info=True)
                if h is not None and h.idx >= initial_count and h.idx not in built_this_run:
                    # It never made it into the indexes, so drop the id and any
                    # half-written file and let the next run try again instead
                    # of assuming it was done. Its Maildir file is deliberately
                    # left out of new_sources so it is read again.
                    hail.Hail.forget(h.original_id)
                    (emails_dir / h.filename).unlink(missing_ok=True)
                continue

    logger.info(
        f"Added {added} new emails, rebuilt {rebuilt} missing files, "
        f"skipped {skipped} already built."
    )

    if added or not incremental:
        index_writer.commit()
        write_json(output_path / "addresses.json", sorted(addresses))
        inverted_index.save()
        hail.Hail.save_id_idx(output_path)
        logger.info(
            f"Completed processing. Generated {len(hail.Hail.d)} email entries "
            f"and {len(addresses)} unique addresses."
        )
    else:
        # Nothing reached the indexes, so leave them exactly as they were
        index_writer.discard()
        logger.info("Indexes unchanged.")

    if new_sources != sources:
        write_json(output_path / SOURCES_FILE, new_sources)

    # Recorded so a later run can tell what the existing index was built with
    build_file = output_path / BUILD_FILE
    if not build_file.is_file() or built_limit != result_limit:
        write_json(build_file, {"max_postings": result_limit})


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
@click.option(
    "--max-postings",
    "result_limit",
    type=click.IntRange(min=1),
    default=search.RESULT_LIMIT,
    show_default=True,
    help=(
        "Drop a word from the search index once it appears in this many emails. "
        "Raising it makes common words searchable at the cost of a larger "
        "search_index.json. Only accepted with --rebuild: the words a previous "
        "run dropped cannot be recovered from the existing index."
    ),
)
@click.pass_context
def main(
    ctx: click.Context, maildir_path: str, output_path: str, rebuild: bool, result_limit: int
) -> None:
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
    limit_given = (
        ctx.get_parameter_source("result_limit") != click.core.ParameterSource.DEFAULT
    )
    parse_maildir(maildir_path_obj, output_path_obj, result_limit, limit_given)
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
