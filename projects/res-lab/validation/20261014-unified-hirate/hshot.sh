#!/bin/sh
ffmpeg -hide_banner -loglevel error -f avfoundation -pixel_format uyvy422 -framerate 60 -video_size 1920x1080 -i "AVerMedia ExtremeCap UVC:none" -frames:v 1 -update 1 -vf scale=960:-1 -y "$1"
