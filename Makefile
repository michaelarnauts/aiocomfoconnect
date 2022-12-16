check: check-pylint check-black

check-pylint:
	@poetry run pylint aiocomfoconnect/*.py

check-black:
	@poetry run black --check aiocomfoconnect/*.py

codefix:
	@poetry run isort aiocomfoconnect/*.py
	@poetry run black aiocomfoconnect/*.py

test:
	@poetry run pytest

.PHONY: check codefix test
