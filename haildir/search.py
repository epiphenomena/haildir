import json
import os
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

    def __init__(self, output_path: Path, load_existing: bool = False):
        self.output_path = output_path
        self.index_file = output_path / "search_index.json"
        self.inverted_index: Dict[str, Set[int]] = collections.defaultdict(set)
        # Words that matched too many emails to be worth indexing. They are
        # stored in the index file as empty posting lists, which the client
        # treats exactly like a word that is not in the index at all.
        self.dropped: Set[str] = set()
        # Loaded on demand: a run that adds nothing never has to read it
        self.pending_load = load_existing

    def load(self) -> None:
        """Load an index written by a previous run so it can be extended."""
        self.pending_load = False
        with open(self.index_file, 'r', encoding='utf-8') as f:
            existing = json.load(f)

        if not isinstance(existing, dict):
            raise ValueError(f"{self.index_file} is not a JSON object")

        for word, email_ids in existing.items():
            if email_ids:
                self.inverted_index[word] = set(email_ids)
            else:
                self.dropped.add(word)

    def add_email(self, msg: hail.Hail) -> None:
        """Add an email to the inverted index."""

        if self.pending_load:
            self.load()

        # Tokenize the content
        words = tokenize(msg.search_content())

        # Add each word to the index
        for word in words:
            # Never revive a dropped word: its posting list is incomplete, so a
            # partial list of hits would be worse than no hits at all.
            if word not in self.dropped:
                self.inverted_index[word].add(msg.idx)

    def save(self) -> None:
        """Finalize the index files by writing them to disk."""
        if self.pending_load:
            # Nothing was added, but saving must not drop what is already there
            self.load()

        # Convert sets to lists for JSON serialization
        serializable_index = {}
        for word, email_ids in self.inverted_index.items():
            if len(email_ids) < RESULT_LIMIT:
                serializable_index[word] = sorted(email_ids)
            else:
                self.dropped.add(word)

        # Record the dropped words so a later incremental build keeps ignoring them
        for word in self.dropped:
            serializable_index[word] = []

        # Save the inverted index by replacing it, so an interrupted write
        # leaves the previous index intact
        tmp_file = self.index_file.with_name(self.index_file.name + ".tmp")
        with open(tmp_file, 'w', encoding='utf-8') as f:
            json.dump(serializable_index, f, ensure_ascii=False, indent=None)
        os.replace(tmp_file, self.index_file)