import click
import mailbox
import json
from pathlib import Path
from email.utils import parseaddr
from datetime import datetime
import hashlib
import shutil
import logging
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

    # Process each message
    processed_count = 0
    for key, msg in maildir.items():
        processed_count += 1
        if processed_count % 100 == 0:  # Log progress every 100 emails
            logger.info(f"Processing email {processed_count}/{total_messages}")

        try:
            # Extract basic information
            message_id = msg.get("Message-ID", "")
            if not message_id:
                # Generate a unique ID if Message-ID is missing
                message_id = hashlib.md5(
                    f"{msg.get('From', '')}{msg.get('Date', '')}".encode()
                ).hexdigest()

            # Sanitize message_id for use as filename
            safe_message_id = "".join(
                c for c in message_id if c.isalnum() or c in ("-", "_")
            ).rstrip()
            if not safe_message_id:
                safe_message_id = key  # Fallback to maildir key

            # Parse headers
            date_str = msg.get("Date", "")
            try:
                date_obj = (
                    datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S %z")
                    if date_str
                    else None
                )
                date_iso = date_obj.isoformat() if date_obj else ""
            except ValueError:
                # Handle common date format variations
                try:
                    date_obj = (
                        datetime.strptime(date_str, "%a, %d %b %Y %H:%M:%S")
                        if date_str
                        else None
                    )
                    date_iso = date_obj.isoformat() if date_obj else ""
                except ValueError:
                    date_iso = ""  # Unable to parse date

            subject = msg.get("Subject", "")
            from_addr = msg.get("From", "")
            to_addr = msg.get("To", "")
            cc_addr = msg.get("Cc", "")

            # Extract addresses for autocomplete
            for addr in [from_addr, to_addr, cc_addr]:
                if addr:
                    name, email = parseaddr(addr)
                    if email:
                        addresses.add(email.lower())

            # Extract body content and attachments
            body_text = ""
            body_html = ""
            attachments = []

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        try:
                            payload = part.get_payload(decode=True)
                            if isinstance(payload, bytes):
                                body_text += payload.decode(
                                    part.get_content_charset() or "utf-8",
                                    errors="replace",
                                )
                            else:
                                body_text += str(payload)
                        except Exception as e:
                            logger.warning(f"Error decoding text/plain payload: {e}")
                    elif part.get_content_type() == "text/html":
                        try:
                            payload = part.get_payload(decode=True)
                            if isinstance(payload, bytes):
                                body_html += payload.decode(
                                    part.get_content_charset() or "utf-8",
                                    errors="replace",
                                )
                            else:
                                body_html += str(payload)
                        except Exception as e:
                            logger.warning(f"Error decoding text/html payload: {e}")
                    elif part.get_content_disposition() == "attachment":
                        # Handle attachments
                        filename = part.get_filename()
                        if filename:
                            # Generate a unique filename for the attachment
                            attachment_id = hashlib.md5(
                                f"{safe_message_id}{filename}".encode()
                            ).hexdigest()
                            attachment_filename = f"{attachment_id}_{filename}"

                            logger.debug(f"Processing attachment: {filename} for email {safe_message_id}")

                            # Save attachment to disk
                            attachment_path = attachments_dir / attachment_filename
                            with open(attachment_path, "wb") as f:
                                f.write(part.get_payload(decode=True))

                            # Store attachment metadata
                            attachments.append(
                                {
                                    "filename": filename,
                                    "saved_filename": attachment_filename,
                                    "content_type": part.get_content_type(),
                                }
                            )
                            logger.debug(f"Saved attachment: {attachment_filename}")
            else:
                if msg.get_content_type() == "text/plain":
                    body_text = msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", errors="replace"
                    )
                elif msg.get_content_type() == "text/html":
                    body_html = msg.get_payload(decode=True).decode(
                        msg.get_content_charset() or "utf-8", errors="replace"
                    )

            # Create preview text (first 100 characters of body)
            preview = (body_text or body_html)[:100].replace("\n", " ").strip()

            # Save email data to JSON file
            email_data = {
                "id": safe_message_id,
                "date": date_iso,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "body_text": body_text,
                "body_html": body_html,
                "attachments": attachments,
            }

            email_file = emails_dir / f"{safe_message_id}.json"
            with open(email_file, "w", encoding="utf-8") as f:
                json.dump(email_data, f, ensure_ascii=False, indent=2)

            # Add to main index
            index_entry = {
                "id": safe_message_id,
                "date": date_iso,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "preview": preview,
            }

            with open(index_file, "a", encoding="utf-8") as f:
                if not first_index_item:
                    f.write(",\n")
                json.dump(index_entry, f, ensure_ascii=False, indent=2)
                first_index_item = False

            # Add to inverted search index (only metadata needed for indexing, excluding attachments)
            inverted_index.add_email(
                {
                    "id": safe_message_id,
                    "subject": subject,
                    "from": from_addr,
                    "to": to_addr,
                    "cc": cc_addr,
                    "body_text": body_text,
                    "body_html": body_html,
                }
            )
            logger.debug(f"Added email {safe_message_id} to inverted index")

        except Exception as e:
            logger.error(f"Error processing message {key}: {e}", exc_info=True)
            continue

    # Close index files with closing brackets
    with open(index_file, "a", encoding="utf-8") as f:
        f.write("\n]")

    # Save addresses for autocomplete
    with open(addresses_file, "w", encoding="utf-8") as f:
        json.dump(list(addresses), f, ensure_ascii=False, indent=2)

    # Finalize the inverted index
    inverted_index.finalize()

    # Log completion statistics
    email_count = len([f for f in emails_dir.iterdir() if f.is_file()])
    address_count = len(addresses)
    logger.info(f"Completed processing. Generated {email_count} email entries and {address_count} unique addresses.")


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
