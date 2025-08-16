import click
import mailbox
import json
from pathlib import Path
from email.utils import parseaddr
from datetime import datetime
import hashlib
import shutil
from .search import InvertedIndex

def parse_maildir(maildir_path: Path, output_path: Path) -> None:
    """Parse Maildir and extract email data, building indexes incrementally."""
    maildir = mailbox.Maildir(str(maildir_path))

    # Create directory for email data
    emails_dir = output_path / "emails"
    emails_dir.mkdir(exist_ok=True)

    # Create files for incremental index building
    index_file = output_path / "index.json"
    addresses_file = output_path / "addresses.json"

    # Track unique addresses for autocomplete
    addresses = set()

    metadata = []

    # Create incremental inverted index
    inverted_index = InvertedIndex(output_path)

    # Process each message
    for key, msg in maildir.iteritems():
        try:
            # Extract basic information
            message_id = msg.get('Message-ID', '')
            if not message_id:
                # Generate a unique ID if Message-ID is missing
                message_id = hashlib.md5(f"{msg.get('From', '')}{msg.get('Date', '')}".encode()).hexdigest()

            # Sanitize message_id for use as filename
            safe_message_id = "".join(c for c in message_id if c.isalnum() or c in ('-', '_')).rstrip()
            if not safe_message_id:
                safe_message_id = key  # Fallback to maildir key

            # Parse headers
            date_str = msg.get('Date', '')
            try:
                date_obj = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S %z') if date_str else None
                date_iso = date_obj.isoformat() if date_obj else ''
            except ValueError:
                # Handle common date format variations
                try:
                    date_obj = datetime.strptime(date_str, '%a, %d %b %Y %H:%M:%S') if date_str else None
                    date_iso = date_obj.isoformat() if date_obj else ''
                except ValueError:
                    date_iso = ''  # Unable to parse date

            subject = msg.get('Subject', '')
            from_addr = msg.get('From', '')
            to_addr = msg.get('To', '')
            cc_addr = msg.get('Cc', '')

            # Extract addresses for autocomplete
            for addr in [from_addr, to_addr, cc_addr]:
                if addr:
                    name, email = parseaddr(addr)
                    if email:
                        addresses.add(email.lower())

            # Extract body content
            body_text = ""
            body_html = ""

            if msg.is_multipart():
                for part in msg.walk():
                    if part.get_content_type() == "text/plain":
                        body_text += part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
                    elif part.get_content_type() == "text/html":
                        body_html += part.get_payload(decode=True).decode(part.get_content_charset() or 'utf-8', errors='replace')
            else:
                if msg.get_content_type() == "text/plain":
                    body_text = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')
                elif msg.get_content_type() == "text/html":
                    body_html = msg.get_payload(decode=True).decode(msg.get_content_charset() or 'utf-8', errors='replace')

            # Create preview text (first 100 characters of body)
            preview = (body_text or body_html)[:100].replace('\n', ' ').strip()

            # Save email data to JSON file
            email_data = {
                "id": safe_message_id,
                "date": date_iso,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "body_text": body_text,
                "body_html": body_html
            }

            email_file = emails_dir / f"{safe_message_id}.json"
            with open(email_file, 'w', encoding='utf-8') as f:
                json.dump(email_data, f, ensure_ascii=False, indent=2)

            # Add to main index
            meta = {
                "id": safe_message_id,
                "date": date_iso,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "preview": preview
            }

            metadata.append(meta)

            # Add to inverted search index (only metadata needed for indexing)
            inverted_index.add_email({
                "id": safe_message_id,
                "subject": subject,
                "from": from_addr,
                "to": to_addr,
                "cc": cc_addr,
                "body_text": body_text,
                "body_html": body_html
            })

        except Exception as e:
            print(f"Error processing message {key}: {e}")
            continue

    with open(index_file, 'wt', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2)

    # Save addresses for autocomplete
    with open(addresses_file, 'w', encoding='utf-8') as f:
        json.dump(list(addresses), f, ensure_ascii=False, indent=2)

    # Finalize the inverted index
    inverted_index.finalize()

def copy_assets(output_path: Path) -> None:
    """Copy static assets to output directory."""
    assets_src = Path(__file__).parent / "assets"
    if assets_src.exists():
        for item in assets_src.iterdir():
            if item.is_file():
                shutil.copy2(item, output_path / item.name)

@click.command()
@click.argument('maildir_path', type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True))
@click.argument('output_path', type=click.Path(file_okay=False, dir_okay=True, resolve_path=True))
def main(maildir_path: str, output_path: str) -> None:
    """Convert a Maildir archive to a static, searchable HTML site."""
    maildir_path = Path(maildir_path)
    output_path = Path(output_path)

    # Ensure output directory exists
    output_path.mkdir(parents=True, exist_ok=True)

    # Parse maildir
    parse_maildir(maildir_path, output_path)

    # Copy assets
    copy_assets(output_path)

    # Count processed emails by counting files in emails directory
    emails_dir = output_path / "emails"
    email_count = len([f for f in emails_dir.iterdir() if f.is_file()]) if emails_dir.exists() else 0

    click.echo(f"Processed Maildir: {maildir_path}")
    click.echo(f"Output directory: {output_path}")
    click.echo(f"Generated {email_count} email entries")

if __name__ == '__main__':
    main()