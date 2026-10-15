# make run    install if needed, then start the app at http://127.0.0.1:8000/
# make test   install if needed, then run all tests
# make clean  remove the virtualenv and caches

VENV := .venv
PORT ?= 8000

.PHONY: run test install clean

run: install
	$(VENV)/bin/uvicorn app.main:app --reload --port $(PORT)

test: install
	$(VENV)/bin/pytest

install: $(VENV)/.installed

# Reinstalls only when requirements.txt changes.
$(VENV)/.installed: requirements.txt
	python3 -m venv $(VENV)
	$(VENV)/bin/pip install -q -r requirements.txt
	touch $@

clean:
	rm -rf $(VENV) .pytest_cache
