# haildir

Convert Maildir archives to a static, searchable HTML site.

## Overview

`haildir` is a tool that converts Maildir email archives into a static HTML website that can be easily browsed and searched. It's designed to handle large archives (10+ GB) by processing emails incrementally and generating efficient static indexes. Intitally created with Qwen code -- less than an hour of human input -- a passable output. It successfully loaded and indexed a 15GB+ maildir created by getmail downloaded from gmail. Since gone through some refinement.

Gmail's search has gotten less effective. And every other mail reading client I have tested has failed to provide effective search. All of them fail to find messages that I know exist and contain the search terms. While it would be convenient to have good search built  into whatever client I am using, that is apparently not an option, and I'm not prepared to support my own clients. So the next best thing is a searchable archive. I already have a backup script in place that saves my email into a maildir format. Haildir reads through that directory and outputs a "static" (as in requires only a server that can serve static files) web based frontend. Super simple. Only supports searching. But can search by words (using a static json based inverted index), to/from addresses (with autocomplete), and filter by date range. The search indexes are large, but even for my 15+GB archive the memory used by the browser tab is less than used by the slack tab.

As an excerise in using genAI for development, this has been interesting. This is exactly the kind of project that 1) I would put off forever if I were writing it myself because it would require learning several new python libs, and more code in javascript than I would enjoy; and 2) exactly the kind of code that should be ideal for LLMs -- the quality of the code doesn't matter because this is the end product, no one is building anything on top of this, the architecture is relatively simple with few moving parts, the security implications are low, and it's relatively easy to test for accuracy. I will note that despite repeated explicit instructions, the LLM completely failed to produce python code that processed each email individually and then freed that memory. All of the early iterations kept handles to the messages in a way that would either read through every message before starting to process them, or hold onto references to already processed messages -- in both cases consuming too much RAM. The LLM holds no computational model and so can not "understand" how code works -- it just emits tokens.

## TODO

- Sanitize the html format email bodies. Currently the email bodies are displaying inside iframes. This is probably acceptable from a security perspective if all you care about is avoiding XSS. But, for example, images are loaded automatically by the browser so tracking that relies on those images works. Also, the search indexes tokenize the html entities. I could use bleach to drop most of the html entities. Or convert to markdown (but lose links?). Need to think about how to make images optional on a per message basis.
- Add links to other messages in thread. A la the classic message boards.
- Come up with a way to minimize data loaded by client without requiring server side code.


## Features

- Converts Maildir format email archives to static HTML/CSS/JS
- Clean, modern, well-formatted interface
- Full-text search capabilities
- Filtering by sender, recipient, and date range
- Autocomplete for email addresses
- Supports email attachments

## Installation

1. Install `uv` package manager:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Clone the repository:
   ```bash
   git clone https://github.com/epiphenomena/haildir
   cd haildir
   ```

3. Install dependencies:
   ```bash
   uv sync
   ```

## Usage

```bash
uv run haildir /path/to/maildir /path/to/output
cd /path/to/output
uv run python -m http.server -p 8000
```

This will process the Maildir archive and generate a static website in the output directory.
Then start up a simple dev server in the output dir.

### Incremental builds

By default only the emails missing from the output directory are built, so the
command can be re-run as the Maildir grows and it will just pick up the new
messages. Messages are matched by `Message-ID`, and each one keeps the index it
was first assigned, so the search indexes stay valid across runs. If an email's
JSON file has gone missing from the output directory it is written again
without disturbing the indexes.

`sources.json` records which Maildir file produced which email, so a re-run
skips files it has already built without opening them — a run with nothing new
costs a directory listing rather than a full parse of the archive. Deleting it
only makes the next run slow, not wrong: it is rebuilt by reading every message
again.

Note that a Maildir downloaded from Gmail usually holds several copies of the
same message (one per label), so the number of emails in the output is expected
to be well below the number of files in the Maildir. Copies after the first are
counted as "skipped".

Each run leaves the previous output servable until it finishes: `index.json`,
`search_index.json`, `addresses.json`, `id_mapping.json` and `sources.json` are
written to a temporary file and moved into place at the end, so an interrupted
run costs that run's work and nothing else. If a run leaves `index.json`
unclosed (which the versions before this could do), the next build stops and
asks for `--rebuild` instead of appending to a broken file.

To throw away the previous build and start over:

```bash
uv run haildir --rebuild /path/to/maildir /path/to/output
```

(`--clear` does the same thing.) This removes the `emails/` and `attachments/`
directories and the generated `index.json`, `addresses.json`,
`search_index.json`, `id_mapping.json`, `sources.json` and `build.json`; anything else in the output
directory is left alone. If those generated files are only partly present the
build stops and asks for `--rebuild` rather than quietly dropping the emails a
previous run had recorded.

### Searching

A query is split into words the same way the indexer split the emails, so
punctuation does not have to be typed around: searching
`deep.thought@example.com` looks up `deep`, `thought`, `example` and `com`.

Several words match the emails holding **all** of them, not any of them.

Words appearing in more than `--max-postings` emails (500 by default) are left
out of the search index to keep it small. They are recorded so the page can say
a word was ignored rather than reporting no results for it, and a query made
only of such words returns everything instead of nothing. Raising the limit
makes more words searchable at the cost of a larger `search_index.json`:

```bash
uv run haildir --rebuild --max-postings 5000 /path/to/maildir /path/to/output
```

The limit is only accepted together with `--rebuild`, and the build records it
in `build.json`. An incremental run keeps ignoring the words a previous run
dropped — their posting lists were never written, so they cannot be recovered
from the existing index — and asking it for a different limit is refused rather
than applied to new words only.

### Serving from a subdirectory

Every path in the generated site is relative to the page holding it, so the
output directory can be served from anywhere — `https://example.com/` or
`https://example.com/mail/archive/` — without being rebuilt.

### Running tests

Create a test Maildir structure and run the tool on it:
```bash
rake test
```

Check the search itself against an index large enough to exercise it (needs
`node`). This generates a Maildir with a word common enough to be dropped from
the index and words that distinguish "all of these" from "any of these", builds
it, and runs the page's own search functions over the result:
```bash
rake search_test
```

### Running a development server

To run a simple HTTP server to view the generated site:
```bash
rake serve
```

To run tests and then start the server:
```bash
rake test_and_serve
```

### Code quality

Check code with ruff:
```bash
uv run ruff check src/haildir
```

## Architecture

For detailed information about the architecture and implementation plan, see [architecture.md](architecture.md).