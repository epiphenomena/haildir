import json
import re
from pathlib import Path
from typing import Dict, List, Set

def tokenize(text: str) -> List[str]:
    """Tokenize text into words, converting to lowercase and removing punctuation."""
    # Convert to lowercase and split on whitespace and punctuation
    words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    return words

class InvertedIndex:
    """An inverted index that can be built incrementally."""

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.inverted_index: Dict[str, Set[int]] = {}
        self.id_to_email: Dict[int, str] = {}
        self.next_id = 0

    def add_email(self, email_data: Dict) -> None:
        """Add an email to the inverted index."""
        email_id = self.next_id
        email_filename = email_data["id"]

        # Store the mapping
        self.id_to_email[email_id] = email_filename

        # Combine all text fields for indexing
        content = f"{email_data.get('subject', '')} {email_data.get('from', '')} {email_data.get('to', '')} {email_data.get('cc', '')} {email_data.get('body_text', '')} {email_data.get('body_html', '')}"

        # Tokenize the content
        words = tokenize(content)

        # Add each word to the index
        for word in words:
            if word not in self.inverted_index:
                self.inverted_index[word] = set()
            self.inverted_index[word].add(email_id)

        self.next_id += 1

    def finalize(self) -> None:
        """Finalize the index files by writing them to disk."""
        # Convert sets to lists for JSON serialization
        serializable_index = {word: list(email_ids) for word, email_ids in self.inverted_index.items()}

        # Save the inverted index
        search_index_file = self.output_path / "search_index.json"
        with open(search_index_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_index, f, ensure_ascii=False, indent=None)

        # Save the ID to email mapping
        id_mapping_file = self.output_path / "id_mapping.json"
        with open(id_mapping_file, 'w', encoding='utf-8') as f:
            json.dump(self.id_to_email, f, ensure_ascii=False, indent=None)