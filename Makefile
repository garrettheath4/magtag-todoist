.PHONY: all prod dev clean FORCE

TARGET = /Volumes/CIRCUITPY
PROD_LIB = lib/adafruit-circuitpython-bundle-10.x-mpy-20260321/lib
DEV_LIB = lib/adafruit-circuitpython-bundle-py-20260321/lib

MODULE_DIRS = adafruit_bitmap_font adafruit_display_shapes adafruit_display_text adafruit_imageload adafruit_io adafruit_magtag adafruit_minimqtt adafruit_portalbase
MODULE_FILES = adafruit_connection_manager adafruit_datetime adafruit_fakerequests adafruit_logging adafruit_requests adafruit_ticks neopixel simpleio

code.py: FORCE
	cp code.py "$(TARGET)/code.py"

my_secrets.py: FORCE
	cp my_secrets.py "$(TARGET)/my_secrets.py"

prod: code.py my_secrets.py
	for dir in $(MODULE_DIRS); do \
		cp -rfv "$(PROD_LIB)/$$dir" "$(TARGET)/lib/" ; \
	done
	for file in $(MODULE_FILES); do \
		cp -fv "$(PROD_LIB)/$$file.mpy" "$(TARGET)/lib/" ; \
	done

dev: code.py my_secrets.py
	for dir in $(MODULE_DIRS); do \
		cp -rfv "$(DEV_LIB)/$$dir" "$(TARGET)/lib/" ; \
	done
	for file in $(MODULE_FILES); do \
		cp -fv "$(DEV_LIB)/$$file.py" "$(TARGET)/lib/" ; \
	done

all: prod

clean:
	rm -rf "$(TARGET)"/lib/*
