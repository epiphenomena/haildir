import json
from pathlib import Path
import re
import email as std_email
from email.utils import parseaddr
import hashlib
import logging
from dateutil import parser as dateutil_parser

# Read user email addresses from config.json if it exists
def get_user_emails():
    """Read user email addresses from config.json in the root directory."""
    config_path = Path(__file__).parent.parent / "config.json"
    if config_path.exists():
        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)
                return set(config.get("user_emails", []))  # Return a set of user emails
        except (json.JSONDecodeError, FileNotFoundError):
            logging.warning(f"Could not read config.json: {config_path}")
            return set()
    return set()

# Read user emails once at module load time
USER_EMAILS = get_user_emails()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

class EmailAlreadyProcessed(Exception):
    pass

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
        self.original_id = msg.get("Message-ID", "")
        if not self.original_id:
            logger.warning(f"Failed to get Message-ID: {msg}")
            # Generate a unique ID if Message-ID is missing
            self.original_id = hashlib.md5(
                f"{msg.get('From', '')}{msg.get('Date', '')}".encode()
            ).hexdigest()

        # Add the ID to class-level tracking
        self_cls = type(self)
        if self.original_id not in self_cls.d:
            idx = len(type(self).ls)
            self_cls.ls.append(self.original_id)
            self_cls.d[self.original_id] = idx
            self.idx = idx
        else:
            # If already exists, use existing index
            self.idx = self_cls.d[self.original_id]

    @classmethod
    def from_maildir(cls, msg):
        if id := msg.get("Message-ID", "") in cls.d:
            raise EmailAlreadyProcessed(id)
        else:
            return cls(msg)

    @property
    def from_addr(self):
        """Return the from address."""
        return parseaddr(self.msg.get("From", ""))[1].lower()

    @property
    def to_addr(self):
        """Return the to address."""
        to_header = self.msg.get("To", "")
        if to_header:
            # Split multiple addresses by comma and parse each one
            addresses = [addr.strip() for addr in to_header.split(',')]
            return [parseaddr(addr)[1].lower() for addr in addresses if parseaddr(addr)[1]]
        return []

    @property
    def cc_addr(self):
        """Return the cc address."""
        cc_header = self.msg.get("Cc", "")
        if cc_header:
            # Split multiple addresses by comma and parse each one
            addresses = [addr.strip() for addr in cc_header.split(',')]
            return [parseaddr(addr)[1].lower() for addr in addresses if parseaddr(addr)[1]]
        return []

    @property
    def subject(self):
        """Return the subject of the email."""
        subject = self.msg.get("Subject", "")
        if isinstance(subject, std_email.header.Header):
            subject = str(subject)
        return subject

    @property
    def date(self):
        """Return the parsed date in YYYY-MM-DD HH:mm format."""
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

        return date_obj.strftime("%Y-%m-%d %H:%M") if date_obj else ""

    @property
    def addresses(self):
        """Return the set of addresses for autocomplete."""
        addresses = set()
        addresses.add(self.from_addr)
        for addrs in [self.to_addr, self.cc_addr]:
            for addr in addrs:
                addresses.add(addr)
        return addresses

    @property
    def from_me(self):
        """Return whether the email is from one of the user's addresses."""
        return self.from_addr in USER_EMAILS

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
    def preview(self):
        """Return preview text (first 100 characters of body)."""
        body_content = self.body_text or self.body_html
        return body_content[:100].replace("\n", " ").strip()

    @property
    def to_dict(self):
        """Return the email data as a dictionary."""
        return {
            "id": self.original_id,
            "date": self.date,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "from_me": self.from_me,
            "body_text": self.body_text,
            "body_html": self.body_html,
            "attachments": self._attachments,
        }

    @property
    def index_data(self):
        """Return the index data as a dictionary."""
        return {
            "id": self.original_id,
            "date": self.date,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "from_me": self.from_me,
            "preview": self.preview,
            "has_attachments": len(self._attachments) > 0,
            "attachment_count": len(self._attachments),
            "attachments": [a["filename"] for a in self._attachments]  # Just the filenames for the index
        }

    def save_attachments(self, output_dir: Path):
        """
        Save any attachments in the given output directory.

        Args:
            output_dir: The directory where attachments should be saved
        """

        attachments = []

        for part in self.msg.walk():
            if part.get_content_disposition() == "attachment":
                filename = part.get_filename()
                if filename:
                    # Generate a unique filename for the attachment
                    if '.' in filename:
                        ext = filename.split('.')[-1]
                    else:
                        ext = ''
                    attachment_filename = hashlib.md5(
                        f"{self.original_id}{filename}".encode()
                    ).hexdigest() + ext

                    logger.debug(f"Processing attachment: {filename} for email {self.original_id}")

                    # Save attachment to disk
                    attachment_path = output_dir / attachment_filename
                    with open(attachment_path, "wb") as f:
                        decoded_attachment = part.get_payload(decode=True)
                        if decoded_attachment:
                            f.write(decoded_attachment)
                        else:
                            logger.debug(f"Attachment Missing: {filename}")

                    logger.debug(f"Saved attachment: {attachment_filename}")

                    attachments.append(
                        {
                            "filename": filename,
                            "saved_filename": attachment_filename,
                            "content_type": part.get_content_type(),
                        }
                    )
        self._attachments = attachments
        return attachments

    @property
    def filename(self):
        return f"{self.idx}.json"

    def to_json(self):
        """Return the JSON representation of the email."""
        return json.dumps(self.to_dict, ensure_ascii=False, indent=None)

    def save(self, output_dir: Path):
        """
        Save the email to a file named self.idx.json in the given directory.

        Args:
            output_dir: The directory where the email should be saved
        """
        with (output_dir / self.filename).open(mode="w", encoding="utf-8") as f:
            f.write(self.to_json())

    def search_content(self):
        return f"{self.subject} {' '.join(self.addresses)} {self.body_text} {self.body_html}"

    def search_entry(self):
        """Return the data needed for adding to the search indexes."""
        return {
            "id": self.original_id,
            "subject": self.subject,
            "from": self.from_addr,
            "to": self.to_addr,
            "cc": self.cc_addr,
            "body_text": self.body_text,
            "body_html": self.body_html,
        }

    @classmethod
    def save_id_idx(cls, dir):
        # Save the ID to email mapping
        id_mapping_file = dir / "id_mapping.json"
        with open(id_mapping_file, 'w', encoding='utf-8') as f:
            json.dump(cls.d, f, ensure_ascii=False, indent=None)