CC        ?= clang
CFLAGS    ?= -O2 -Wall -Wextra
LIBUSB    ?= /Users/dido/Documents/Codex/2026-08-16/4

all: fpshd autorun

fpshd: fpshd.c
	$(CC) $(CFLAGS) $< -I$(LIBUSB) -L$(LIBUSB) -lusb-1.0 \
		-Wl,-rpath,$(LIBUSB) -o $@

autorun:
	./build_autorun.py
	./build_autorun.py --diag

card: autorun
	@test -d "$(CARD)" || { echo "usage: make card CARD=/Volumes/<name> [DIAG=1]"; exit 2; }
	cp dist/$(if $(DIAG),AutoRun.diag.txt,AutoRun.txt) "$(CARD)/AutoRun.txt"
	@sync; dot_clean -m "$(CARD)" 2>/dev/null; sync
	@cmp -s dist/$(if $(DIAG),AutoRun.diag.txt,AutoRun.txt) "$(CARD)/AutoRun.txt" \
		&& echo "card written and verified: $(CARD)/AutoRun.txt" \
		|| { echo "VERIFY FAILED"; exit 1; }

clean:
	rm -f fpshd
	rm -rf dist

.PHONY: all autorun card clean
