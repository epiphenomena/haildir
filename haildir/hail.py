import json
from pathlib import Path
import re
import email as std_email
from email.utils import parseaddr
import hashlib
import logging
from dateutil import parser as dateutil_parser

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


def clean_datetime_string(date_str):
    """Clean datetime string by removing unwanted suffixes before parsing."""
    # Pattern to capture content in parentheses at the end (like "(GMT+00:00)")
    parentheses_pattern = r"\([^)]*\)$"
    # Pattern to capture alphabetic text at the end (like "Pacific Standard Time")
    text_end_pattern = r"[a-zA-Z][a-zA-Z\s]+$"

    # Remove parentheses content at the end
    cleaned = re.sub(parentheses_pattern, "", date_str)
    # Remove trailing alphabetic text
    cleaned = re.sub(text_end_pattern, "", cleaned)
    return cleaned.strip()


class Hail:
    """
    A class to represent an email message from a Maildir.
    """
    # Class-level properties to track message IDs
    ls = []  # List of id strings
    d = {}  # Dict mapping id strings to their index in the list

    def __init__(self, msg):
        """
        Initialize the Hail instance with a message object from Maildir.

        Args:
            msg: The message object from iterating through the maildir
            key: The key from the maildir iteration
        """
        self.msg = msg

        # Extract and set the original Message-ID
        original_message_id = msg.get("Message-ID", "")
        if not original_message_id:
            logger.warning(f"Failed to get Message-ID: {msg}")
            # Generate a unique ID if Message-ID is missing
            original_message_id = hashlib.md5(
                f"{msg.get('From', '')}{msg.get('Date', '')}".encode()
            ).hexdigest()

        self.original_id = original_message_id

        # Sanitize message_id for use as filename
        self._id = "".join(
            c for c in original_message_id if c.isalnum() or c in ("-", "_")
        ).rstrip()
        if not self._id:
            # Fallback to a hash of the original message if no usable id can be created
            self._id = hashlib.md5(original_message_id.encode()).hexdigest()

        # Add the ID to class-level tracking
        self_cls = type(self)
        if self.id not in self_cls.d:
            idx = len(type(self).ls)
            self_cls.ls.append(self.id)
            self_cls.d[self.id] = idx
            self.idx = idx
        else:
            # If already exists, use existing index
            self.idx = self_cls.d[self.id]

    @property
    def id(self):
        """Return the sanitized message ID."""
        return self._id

    @classmethod
    def from_maildir(cls, msg):
        if msg.get("Message-ID", "") in cls.d:
            # Return existing instance if already processed
            existing_id = msg.get("Message-ID", "")
            return cls.d[existing_id]
        else:
            return cls(msg)

    @property
    def from_addr(self):
        """Return the from address."""
        return self.msg.get("From", "")

    @property
    def to_addr(self):
        """Return the to address."""
        return self.msg.get("To", "")

    @property
    def cc_addr(self):
        """Return the cc address."""
        return self.msg.get("Cc", "")

    @property
    def subject(self):
        """Return the subject of the email."""
        subject = self.msg.get("Subject", "")
        if isinstance(subject, std_email.header.Header):
            subject = str(subject)
        return subject

    @property
    def date(self):
        """Return the parsed date in ISO format."""
        date_str = self.msg.get("Date", "")
        date_obj = None

        if date_str:
            try:
                # Clean the datetime string by removing unwanted suffixes before parsing
                cleaned_date_str = clean_datetime_string(date_str)
                # Use dateutil to parse the date string, which handles many formats automatically
                date_obj = dateutil_parser.parse(cleaned_date_str)
            except (ValueError, TypeError) as e:
                logger.warning(f"Unable to parse date: {date_str}. Error: {e}")

        return date_obj.isoformat() if date_obj else ""

    @property
    def addresses(self):
        """Return the set of addresses for autocomplete."""
        addresses = set()
        for addr in [self.from_addr, self.to_addr, self.cc_addr]:
            if addr:
                name, email = parseaddr(addr)
                if email:
                    addresses.add(email.lower())
        return addresses

    @property
    def body_text(self):
        """Return the plain text body of the email."""
        body_text = ""
        if self.msg.is_multipart():
            for part in self.msg.walk():
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
        else:
            if self.msg.get_content_type() == "text/plain":
                payload = self.msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body_text = payload.decode(
                        self.msg.get_content_charset() or "utf-8",
                        errors="replace"
                    )
                else:
                    body_text = str(payload)
        return body_text

    @property
    def body_html(self):
        """Return the HTML body of the email."""
        body_html = ""
        if self.msg.is_multipart():
            for part in self.msg.walk():
                if part.get_content_type() == "text/html":
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
        else:
            if self.msg.get_content_type() == "text/html":
                payload = self.msg.get_payload(decode=True)
                if isinstance(payload, bytes):
                    body_html = payload.decode(
                        self.msg.get_content_charset() or "utf-8",
                        errors="replace"
                    )
                else:
                    body_html = str(payload)
        return body_html

    @property
    def attachments(self):
        """Return the list of attachments."""
        attachments = []
        if self.msg.is_multipart():
            for part in self.msg.walk():
                if part.get_content_disposition() == "attachment":
                    # Handle attachments
                    filename = part.get_filename()
                    if filename:
                        # Generate a unique filename for the attachment
                        attachment_filename = hashlib.md5(
                            f"{self.id}{filename}".encode()
                        ).hexdigest() + filename[-4:]

                        logger.debug(f"Processing attachment: {filename} for email {self.id}")

                        # Store attachment metadata
                        attachments.append(
                            {
                                "filename": filename,
                                "saved_filename": attachment_filename,
                                "content_type": part.get_content_type(),
                            }
                        )
        return attachments

    @property
    def preview(self):
        """Return preview text (first 100 characters of body)."""
        body_content = self.body_text or self.body_html
        return body_content[:100].replace("\n", " ").strip()



    @property
    def email_data(self):
        """Return the email data as a dictionary."""
        return {
            "id": self.id,
            "date": self.date,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "body_text": self.body_text,
            "body_html": self.body_html,
            "attachments": self.attachments,
        }

    @property
    def index_data(self):
        """Return the index data as a dictionary."""
        return {
            "id": self.id,
            "date": self.date,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "preview": self.preview,
            "has_attachments": len(self.attachments) > 0,
            "attachment_count": len(self.attachments),
            "attachments": [a["filename"] for a in self.attachments]  # Just the filenames for the index
        }

    @classmethod
    def getls(cls):
        """Return the list of all processed email IDs."""
        return cls.ls

    @classmethod
    def getd(cls):
        """Return the mapping from email IDs to their indices."""
        return cls.d

    def save_attachments(self, output_dir: Path):
        """
        Save any attachments in the given output directory.

        Args:
            output_dir: The directory where attachments should be saved
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

        if not self.msg.is_multipart():
            return

        for part in self.msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if filename:
                    # Generate a unique filename for the attachment
                    attachment_filename = hashlib.md5(
                        f"{self.id}{filename}".encode()
                    ).hexdigest() + filename[-4:]

                    logger.debug(f"Processing attachment: {filename} for email {self.id}")

                    # Save attachment to disk
                    attachment_path = output_dir / attachment_filename
                    with open(attachment_path, "wb") as f:
                        decoded_attachment = part.get_payload(decode=True)
                        if decoded_attachment:
                            f.write(decoded_attachment)
                        else:
                            logger.debug(f"Attachment Missing: {filename}")

                    logger.debug(f"Saved attachment: {attachment_filename}")

    def to_json(self):
        """Return the JSON representation of the email."""
        return json.dumps(self.email_data, ensure_ascii=False, indent=None)

    def save(self, output_dir: Path):
        """
        Save the email to a file named self.idx.json in the given directory.

        Args:
            output_dir: The directory where the email should be saved
        """
        output_dir = Path(output_dir)
        output_dir.mkdir(exist_ok=True)

        email_file = output_dir / f"{self.idx}.json"
        with open(email_file, "w", encoding="utf-8") as f:
            json.dump(self.email_data, f, ensure_ascii=False, indent=None)

    def search_entry(self):
        """Return the data needed for adding to the search indexes."""
        return {
            "id": self.id,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "body_text": self.body_text,
            "body_html": self.body_html,
        }