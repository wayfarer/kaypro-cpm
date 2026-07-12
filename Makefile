MACHINE ?= kaypro-2-84

.PHONY: build run run-persist native start stop status clean

build run run-persist native start stop status clean:
	$(MAKE) -C $(MACHINE) $@

.DEFAULT_GOAL := run
