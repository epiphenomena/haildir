Written in modern python 3.12+. Uses the standard library mailbox class to read the email.

Uses uv to manage python versions, venv and dependencies.

CLI tool called like: `uv run haildir /path/to/maildir /path/to/output`

Reads mail from maildir archive and produces a static html/css/js dir in output directory.
The site is clean, modern, well-formatted. The goal is for the user to be able to backup
their email from their email hosting service, and then turn that archive into a
browsable, searchable format. It is assumed that the user will set the backup
and generation of the haildir dir to run on a schedule. So the search index can be
static, and the site does not need to support live changes or incremental updates.

Supports full text search.

The maildir directory may contain 10+ GB of email. So parsing the files must
proceed file by file, rather than loading all into memory. Likewise for
displaying the mail in the browser -- we can't load all of the email in at once.
Need to create an index with dates, subjects, addresses, and whatever is needed to
support fulltext search over the contents of the email. Don't support searching the
attachments yet. But support opening the attachments from the browser.

The main page of the site should support browsing all email as though it were a
normal inbox. It should support easily filtering by from or to email addresses
(with autocomplete of address), and restricting to selected date ranges. The filtering
should work before or after searching (where the fulltext search includes subject,
addresses and content).

Builds a static search index in json that is loaded with the site.
Inspired by https://github.com/bartdegoede/python-searchengine

The CLI uses the click python library.

The haildir generated site has a root / page that supports clientside browsing,
searching and filtering. Clicking on an email navigates to a new page that displays
only that email with all details and downloadable attachments.

## Implementation Plan

1.  **Project Setup & CLI (Python)**
    *   **Environment:** Use `uv` for Python 3.12+, virtual environment, and dependencies.
    *   **Structure:** Create a basic Python package structure (e.g., `src/haildir/`, `pyproject.toml`).
    *   **CLI:** Use the `click` library to create the command-line interface: `uv run haildir /path/to/maildir /path/to/output`. This command will orchestrate the entire process.
    *   **Dependencies:** Add `click` and potentially `mailbox` (if it's not purely standard library) to `pyproject.toml`.

2.  **Maildir Parsing & Data Extraction (Python)**
    *   **Library:** Utilize Python's standard `mailbox` library to read the Maildir format.
    *   **Processing Loop:** Implement a robust loop that iterates through the maildir file-by-file to handle the 10+ GB size constraint, ensuring memory usage stays low.
    *   **Email Data Extraction:** For each email, parse and extract the following key information:
        *   Unique identifier (e.g., Message-ID, or generate one if missing).
        *   Header fields: `Date`, `Subject`, `From`, `To`, `Cc`.
        *   Body content (plaintext and/or HTML).
        *   Attachment metadata (names, sizes, paths within the maildir structure). Save attachments to the output directory.
    *   **Email Storage:** Save the processed email content (headers, body) into individual structured files (e.g., JSON) within the output directory, organized perhaps by a hash or ID for efficient retrieval. This avoids loading everything into memory later.

3.  **Static Index Generation (Python)**
    *   **Index Structure:** Create a comprehensive index data structure (likely a dictionary that will be serialized to JSON) containing:
        *   Metadata for quick browsing/filtering: Dates, Subjects, From/To/Cc addresses.
        *   Full-text content (subject, addresses, body) for search.
        *   Unique identifier linking back to the individual email file.
        *   Possibly pre-processed data for autocomplete (unique sender/recipient addresses).
    *   **Inspiration:** Implement a simplified version of the indexing approach described in `https://github.com/bartdegoede/python-searchengine`. This likely involves creating an inverted index mapping terms to the documents (emails) containing them, optimized for search speed.
    *   **Static Output:** Serialize this main index into one or more JSON files (e.g., `index.json`, `search_index.json`) and place them in the output directory. The architecture specifies a "static search index in json that is loaded with the site".

4.  **Static Site Generation (Python)**
    *   **Template Engine:** Use a simple Python templating engine (e.g., Jinja2) to generate HTML.
    *   **Main Page (`index.html`):** Generate the main inbox-like browsing page. This page will be the primary interface for searching, filtering, and browsing.
    *   **Email Detail Pages:** For each email, generate a dedicated HTML page displaying all details (headers, body) and providing links to downloadable attachments.
    *   **Assets:** Include/Copy static assets (CSS for modern styling, JavaScript libraries like the chosen search engine, and client-side JS logic) into the output directory.

5.  **Client-Side Functionality (JavaScript)**
    *   **Loading Index:** Implement JavaScript that loads the static JSON index file(s) generated in step 3 when the main page (`index.html`) loads.
    *   **Search Engine:** Integrate a client-side JavaScript search library (like FlexSearch.js) that can utilize the loaded static JSON search index.
    *   **Browsing & Filtering:**
        *   Implement UI elements for filtering by date range and email addresses (From/To).
        *   Add autocomplete functionality for email address fields using the pre-processed address data from the index.
        *   Implement logic to filter the displayed list of emails based on these criteria.
    *   **Interaction Logic:** Write JavaScript to handle the interaction between search, filtering, and displaying the list of emails on the main page. Ensure filtering works before or after searching.
    *   **Email Display:** Ensure navigation from the main list to individual email detail pages works correctly, and that attachment links on those pages point to the correct saved files.