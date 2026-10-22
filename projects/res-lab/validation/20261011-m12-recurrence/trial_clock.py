"""Host chronology for a bounded trial; never communicates with the camera.

Completed frames are observations of bytes delivered by ffmpeg. They are not
sensor exposure timestamps: camera, HDMI and host buffering remain unmeasured.
"""
import datetime
import json
import pathlib
import time


class TrialClock:
    def __init__(self, path, raw, frame_bytes):
        self.path = pathlib.Path(path)
        self.raw = pathlib.Path(raw)
        self.frame_bytes = frame_bytes
        self.origin_ns = time.monotonic_ns()
        # Refuse to overwrite an earlier trial, including an incomplete one.
        with self.path.open('x'):
            pass
        self.sequence = 0
        self.mark('clock_created', limitation='host delivery chronology, not exposure timing')

    def mark(self, event, **details):
        monotonic_ns = time.monotonic_ns()
        wall_ns = time.time_ns()
        try:
            size = self.raw.stat().st_size
        except FileNotFoundError:
            size = 0
        record = {
            'sequence': self.sequence,
            'event': event,
            'monotonic_ns': monotonic_ns,
            'elapsed_seconds': (monotonic_ns-self.origin_ns)/1e9,
            'wall_ns': wall_ns,
            'utc': datetime.datetime.fromtimestamp(
                wall_ns/1e9, datetime.timezone.utc).isoformat(),
            'completed_frames': size//self.frame_bytes,
            'pending_frame_bytes': size % self.frame_bytes,
            **details,
        }
        with self.path.open('a') as stream:
            stream.write(json.dumps(record, ensure_ascii=True)+'\n')
        self.sequence += 1
        return record

    def command(self, send, command, action):
        """Log before sending and after completion; never retry an exception."""
        begin = self.mark('command_begin', command=command, action=action)
        try:
            reply = send(command)
        except BaseException as exc:
            self.mark('command_error', command=command, action=action,
                      begin_sequence=begin['sequence'], error=type(exc).__name__)
            raise
        self.mark('command_end', command=command, action=action,
                  begin_sequence=begin['sequence'], reply=reply)
        return reply
