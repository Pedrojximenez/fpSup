"""Single-ROI fp 5.02 experimental contrast backend; no implicit connection."""
import focus_bridge as b
from settled_sampler import SettledSampler


class CameraBackend:
    def __init__(self, bridge, cancel=lambda: False, event=lambda item: None):
        self.bridge = bridge
        self.cancel = cancel
        self.event = event
        self.sampler = SettledSampler(bridge.io, bridge, cancel=cancel, event=event)

    def observe(self):
        if self.cancel():
            raise b.BridgeError('cancelled before observation')
        return self.sampler.observe()

    def move_to(self, target):
        if self.cancel():
            raise b.BridgeError('cancelled before motion')
        self.bridge.submit_validation_move(target)
        completion = self.bridge.confirm_done(expected=target, cancel=self.cancel)
        self.event({'event': 'move_completed', 'completion': completion})
        if self.cancel():
            raise b.BridgeError('cancelled after native stop/completion')
        return self.observe()

    def stop(self):
        if self.bridge.quarantined:
            return {'verified': False, 'reason': 'transport/ownership quarantined; no repeated abort'}
        if self.bridge.movement_owned:
            requested = ({'requested': False, 'reason': 'abort already attempted; no repeat'}
                         if self.bridge.abort_attempted else self.bridge.request_validation_stop())
            completion = self.bridge.confirm_done()
        else:
            requested = {'requested': False, 'reason': 'no owned pending movement'}
            completion = {'native_done': self.bridge.flags(5) == 3,
                          'position': b.signed(self.bridge.call(0)[0])}
        return {'verified': completion['native_done'], 'request': requested,
                'completion': completion, 'optical_stop_verified': False}
