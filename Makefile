MACHINE ?= kaypro-2-84
MACHINE_DIR = machines/$(MACHINE)
IMAGE = cpm-$(MACHINE)

.PHONY: build run run-persist native start stop status machines test clean

# Docker: the machine directory is the build context, so the Dockerfile's
# COPY . picks up that machine's drives (and its .dockerignore trims the rest).
build:
	docker build -t $(IMAGE) -f harness/Dockerfile $(MACHINE_DIR)

run: build
	docker run -it $(IMAGE)

run-persist: build
	docker run -it -v $(PWD)/$(MACHINE_DIR)/B/0:/cpm/B/0 $(IMAGE)

native: RunCPM

RunCPM:
	bash harness/build_runcpm.sh

start: RunCPM
	python cpm.py --machine $(MACHINE) start

stop:
	python cpm.py --machine $(MACHINE) stop

status:
	python cpm.py --machine $(MACHINE) status

machines:
	python cpm.py machines

test: RunCPM
	python -m unittest discover -s tests -v

clean:
	-python cpm.py --machine $(MACHINE) stop 2>/dev/null
	rm -f RunCPM machines/*/.cpm.sock machines/*/.cpm.pid

.DEFAULT_GOAL := run
