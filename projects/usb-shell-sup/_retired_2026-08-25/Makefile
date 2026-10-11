CC ?= clang
CFLAGS ?= -O2 -Wall -Wextra
LIBUSB_DIR ?= /Users/dido/Documents/Codex/2026-08-16/4

all: fpshelld fpshd

autorun:
	./build_compact_autorun.py

test: fpshelld autorun
	python3 test_fpshell.py
	python3 test_autorun.py

fpshd: fpshd.c
	$(CC) $(CFLAGS) $< -I$(LIBUSB_DIR) -L$(LIBUSB_DIR) -lusb-1.0 \
		-Wl,-rpath,$(LIBUSB_DIR) -Wl,-rpath,@loader_path/../lib -o $@

vendor-autorun:
	./build_vendor_autorun.py

fpshelld: fpshelld.c
	$(CC) $(CFLAGS) $< -I$(LIBUSB_DIR) -L$(LIBUSB_DIR) -lusb-1.0 \
		-Wl,-rpath,$(LIBUSB_DIR) -Wl,-rpath,@loader_path/../lib -o $@

package: all autorun test
	./package_release.py

clean:
	rm -f fpshelld fpshd

.PHONY: all autorun vendor-autorun clean package test
