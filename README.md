# TicketsAPI
The tickets function that xelA uses to easily show on web.

## Requirements
- Python >=3.13
- [uv](https://docs.astral.sh/uv/)

## Setup
1. `make install` (or `uv sync --extra dev`), this also installs Dart Sass for compiling the styles
2. Copy `.env.example` to `.env` and fill it in
3. `make sass` to compile the styles, or `make sass_watch` while working on them
4. `uv run index.py`

The database tables are created from `schema.sql` on startup.

## Note
This source was only made open-source for transparency reasons, please don't steal the code and claim it as your own.
