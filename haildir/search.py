import json
import re
import collections
from pathlib import Path
from typing import Dict, List, Set
from . import hail

RESULT_LIMIT = 500

def tokenize(text: str) -> List[str]:
    """Tokenize text into words, converting to lowercase and removing punctuation."""
    # Convert to lowercase and split on whitespace and punctuation
    words = re.findall(r'\b[a-zA-Z0-9]+\b', text.lower())
    return words

class InvertedIndex:
    """An inverted index that can be built incrementally."""

    def __init__(self, output_path: Path):
        self.output_path = output_path
        self.inverted_index: Dict[str, Set[int]] = collections.defaultdict(set)

    def add_email(self, msg: hail.Hail) -> None:
        """Add an email to the inverted index."""


        # Tokenize the content
        words = tokenize(msg.search_content())

        # Add each word to the index
        for word in words:
            self.inverted_index[word].add(msg.idx)

    def save(self) -> None:
        """Finalize the index files by writing them to disk."""
        # Convert sets to lists for JSON serialization
        serializable_index = {word: list(email_ids) for word, email_ids in self.inverted_index.items() if len(email_ids) < RESULT_LIMIT}

        # Save the inverted index
        search_index_file = self.output_path / "search_index.json"
        with open(search_index_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_index, f, ensure_ascii=False, indent=None)