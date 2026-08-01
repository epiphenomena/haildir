"""
Generate a Maildir that exercises the search index.

The checked-in test/maildir is four messages and 24 words, which cannot show
whether search works: it has no word common enough to be dropped from the
index, no pair of words that distinguishes AND from OR, and no address in a
body. This builds one that does. It is generated rather than committed because
tripping the posting-list limit takes hundreds of messages.
"""

import shutil
import sys
from pathlib import Path

# One word has to appear in more emails than the default --max-postings
COMMON = 600


def write(root: Path, n: int, frm: str, subject: str, body: str) -> None:
    (root / "cur" / f"m{n:05d}").write_text(
        f"From: {frm}\n"
        f"To: clint@example.com\n"
        f"Subject: {subject}\n"
        f"Date: 01 Jan 2024 10:00:00 +0000\n"
        f"Message-ID: <m{n}@example.com>\n"
        f"\n{body}\n",
        encoding="utf-8",
    )


def generate(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
    for name in ("cur", "new", "tmp"):
        (root / name).mkdir(parents=True)

    # Common enough that its posting list is dropped from the index
    for i in range(COMMON):
        write(root, i, "list@example.com", "Weekly newsletter",
              f"newsletter issue {i} filler text")

    # "alpha" in two, "bravo" in two, one holding both: pins AND against OR
    write(root, 1000, "a@example.com", "Alpha one", "alpha appears here")
    write(root, 1001, "a@example.com", "Alpha two", "alpha again")
    write(root, 1002, "b@example.com", "Bravo one", "bravo appears here")
    write(root, 1003, "b@example.com", "Bravo two", "bravo again")
    write(root, 1004, "c@example.com", "Both", "alpha and bravo together")

    # An address in a body: the indexer splits it on the punctuation, so the
    # search box has to split it the same way
    write(root, 1005, "Deep Thought <deep.thought@hitchhiker.example>", "Answer",
          "Contact deep.thought@hitchhiker.example about the answer, 42.")

    print(f"Wrote {COMMON + 6} messages to {root}")


if __name__ == "__main__":
    generate(Path(sys.argv[1] if len(sys.argv) > 1 else "test/search_maildir"))
