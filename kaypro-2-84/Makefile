IMAGE = cpm

.PHONY: build run run-persist native start stop status clean

build:
	docker build -t $(IMAGE) .

run: build
	docker run -it $(IMAGE)

run-persist: build
	docker run -it -v $(PWD)/B/0:/cpm/B/0 $(IMAGE)

native: RunCPM

RunCPM:
	bash build_runcpm.sh

start: RunCPM
	python cpm.py start

stop:
	python cpm.py stop

status:
	python cpm.py status

clean:
	-python cpm.py stop 2>/dev/null
	rm -f RunCPM .cpm.sock .cpm.pid

.DEFAULT_GOAL := run
