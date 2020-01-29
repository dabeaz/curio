# Shortcuts for various tasks (UNIX only).

PYTHON = python

all: test

# ===================================================================
# Install
# ===================================================================

# Remove all build files.
clean:
	rm -rf `find . -type d -name __pycache__ \
		-o -type f -name \*.bak \
		-o -type f -name \*.orig \
		-o -type f -name \*.pyc \
		-o -type f -name \*.pyd \
		-o -type f -name \*.pyo \
		-o -type f -name \*.rej \
		-o -type f -name \*.so \
		-o -type f -name \*.~ `
	rm -rf \
		*.core \
		*.egg-info \
		.coverage \
		.tox \
		build/ \
		dist/ \
		docs/_build/ \
		htmlcov/ \
		tmp/

_:

# ===================================================================
# Tests
# ===================================================================

# Run all tests.
test: 
	$(PYTHON) -m pytest

# ===================================================================
# Linters
# ===================================================================

pep8:
	@git ls-files | grep \\.py$ | xargs $(PYTHON) -m pep8

pyflakes:
	@export PYFLAKES_NODOCTEST=1 && \
		git ls-files | grep \\.py$ | xargs $(PYTHON) -m pyflakes

flake8:
	@git ls-files | grep \\.py$ | xargs $(PYTHON) -m flake8 --max-line-length=100

autopep8:
	@git ls-files | grep \\.py$ | xargs $(PYTHON) -m autopep8 --in-place --aggressive --max-line-length=100
