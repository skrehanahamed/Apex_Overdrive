PY := .venv/bin/python
STAMP := .venv/.installed

.PHONY: run setup assets bot clean help

run: $(STAMP)  ## install deps on first use, then launch the game
	$(PY) main.py

setup: $(STAMP)

$(STAMP): requirements.txt
	python3 -m venv .venv
	.venv/bin/pip install -q -r requirements.txt
	@touch $(STAMP)

assets: $(STAMP)  ## cut sheets/*.png into transparent sprites in assets/
	$(PY) tools/build_assets.py

bot: $(STAMP)  ## watch the autopilot drive
	$(PY) main.py --bot

clean:
	rm -rf .venv __pycache__ apex/__pycache__

help:
	@echo "make run     - play"
	@echo "make assets  - rebuild assets/ from the generated sheets in sheets/"
	@echo "make bot     - autopilot demo"
