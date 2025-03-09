#!/bin/bash
set -e  # Exit on error

# Install Python dependencies
pip install -r requirements.txt

# Install Playwright Browsers
playwright install --with-deps
