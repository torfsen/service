.PHONY: _confirm pypi sphinx test testpypi tox

# See https://stackoverflow.com/a/47839479/857390
_confirm:
	@(read -p "Are you sure? [y/N]: " sure && \
	  case "$$sure" in [yY]) true;; *) false;; esac )

pypi: sphinx tox _confirm
	rm -rf dist
	rm -rf *.egg-info
	./setup.py sdist
	twine upload dist/*

sphinx:
	rm -rf build/sphinx
	sphinx-build -W -b html docs/ build/sphinx/

test:
	./runtests.py

testpypi: sphinx tox _confirm
	rm -rf dist
	rm -rf *.egg-info
	./setup.py sdist
	twine upload --repository-url https://test.pypi.org/legacy/ dist/*

tox:
	rm -rf .tox
	tox

