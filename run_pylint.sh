#!/bin/zsh

# Find all Python files and pass them to pylint using xargs
find . -maxdepth 1 -name "*.py" | xargs pylint -d C
