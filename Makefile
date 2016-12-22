# Shortcuts for various tasks (UNIX only).

PYTHON = python3.5

# In not in a virtualenv, add --user options for install commands.
INSTALL_OPTS = `$(PYTHON) -c "import sys; print('' if hasattr(sys, 'real_prefix') else '--user')"`

DEPS = pytest \
	sphinx \
	flake8 \
	pep8

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

# Install this package:
# - as the current user, in order to avoid permission issues
# - in development / edit mode, so that source can be modified on the fly
install:
	# make sure setuptools is installed (needed for 'develop' / edit mode)
	$(PYTHON) -c "import setuptools"
	$(PYTHON) setup.py develop $(INSTALL_OPTS)
	rm -rf tmp

# Uninstall this package via pip.
uninstall:
	cd ..; $(PYTHON) -m pip uninstall -y -v curio

# Install useful deps which are nice to have while developing / testing;
# deps these are also upgraded.
setup-dev-env:
	$(PYTHON) -m pip install $(INSTALL_OPTS) --upgrade pip
	$(PYTHON) -m pip install $(INSTALL_OPTS) --upgrade $(DEPS)

# ===================================================================
# Tests
# ===================================================================

# Run all tests.
test: install
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
