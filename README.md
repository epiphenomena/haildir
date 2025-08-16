# haildir

Convert Maildir archives to a static, searchable HTML site.

## Overview

`haildir` is a tool that converts Maildir email archives into a static HTML website that can be easily browsed and searched. It's designed to handle large archives (10+ GB) by processing emails incrementally and generating efficient static indexes.

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
   git clone https://github.com/yourusername/haildir.git
   cd haildir
   ```

3. Install dependencies:
   ```bash
   uv sync
   ```

## Usage

```bash
uv run haildir /path/to/maildir /path/to/output
```

This will process the Maildir archive and generate a static website in the output directory.

## Development

### Setting up the environment

1. Create a virtual environment:
   ```bash
   uv venv
   ```

2. Activate the virtual environment:
   ```bash
   source .venv/bin/activate
   ```

3. Install dependencies:
   ```bash
   uv sync
   ```

### Running tests

Create a test Maildir structure and run the tool on it:
```bash
rake test
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