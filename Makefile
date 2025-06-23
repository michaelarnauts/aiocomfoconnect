check: check-pylint check-black

check-pylint:
	@poetry run pylint --load-plugins=pylint_protobuf aiocomfoconnect/*.py

check-black:
	@poetry run black --check aiocomfoconnect/*.py

codefix:
	@poetry run isort aiocomfoconnect/*.py
	@poetry run black aiocomfoconnect/*.py

test:
	@poetry run pytest --cov=aiocomfoconnect --cov-report=term --cov-report=xml

build:
	docker build -t aiocomfoconnect .

.PHONY: check codefix test
