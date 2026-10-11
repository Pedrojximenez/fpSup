#!/usr/bin/env python3
"""Offline original-instruction integer binding probe; never a camera adapter."""
from pathlib import Path
import importlib.util

# Reuse the pinned, guarded canonical registration harness without modifying it.
SHARED = Path(__file__).resolve().parents[2] / "research/ui/tools/native_variable_probe/registry_probe.py"
spec = importlib.util.spec_from_file_location("shared_registry_probe", SHARED)
registry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(registry)
from unicorn import UC_HOOK_MEM_READ, UcError
from unicorn.arm_const import UC_ARM_REG_PC, UC_ARM_REG_LR, UC_ARM_REG_SP

SUBSCRIBE = 0xC05DCB18
UNSUBSCRIBE = 0xC05DCB30
NOTIFY = 0xC05D9F90
SET_NOTIFY = 0xC05DC7C8
SET_SILENT = 0xC05DC778  # Suppresses app-variable callback, NOT component updates.
SET_INDEX = 0xC05DC818
EXTRA_NATIVE = {
    "subscribe_wrapper": (SUBSCRIBE, 0xC05DCB2C),
    "unsubscribe_wrapper": (UNSUBSCRIBE, 0xC05DCB40),
    "subscription_mutation": (0xC05D9EB8, 0xC05D9F8A),
    "notify_private_then_global": (NOTIFY, 0xC05D9FC8),
    "set_named_notify_wrapper": (SET_NOTIFY, 0xC05DC818),
    "set_named_no_callback_wrapper": (SET_SILENT, 0xC05DC7C6),
    "set_index_or_name_wrapper": (SET_INDEX, 0xC05DC83C),
    "set_batch_core": (0xC05DC178, 0xC05DC468),
    "dispatch_bound_components": (0xC05DC0D0, 0xC05DC174),
    "temporary_vector_init": (0xC05D7430, 0xC05D745C),
    "temporary_vector_destroy": (0xC05D7470, 0xC05D7496),
    "vector_count": (0xC05D7530, 0xC05D7536),
}


class BindingProbe(registry.RegistryProbe):
    PAIR = registry.RegistryProbe.RAM + 0x3700
    CONTEXT = registry.RegistryProbe.RAM + 0x3800
    ASSIGNMENT = registry.RegistryProbe.RAM + 0x3900
    PRIVATE_CALLBACK = registry.RegistryProbe.SERVICES + 0x100
    GLOBAL_CALLBACK = registry.RegistryProbe.SERVICES + 0x110
    LOCK = registry.RegistryProbe.SERVICES + 0x120
    UNLOCK = registry.RegistryProbe.SERVICES + 0x130

    def __init__(self, image, lock_enabled=True):
        self.events = []
        self.callback_results = {}
        self.private_callback_action = None
        self.freed = {}
        self.pause_at = None
        self.paused = False
        self.pause_context = None
        self.lock_depth = 0
        super().__init__(image)
        self.write_words(self.APP + 8, self.ALLOCATOR)
        self.write_words(self.ROOT + 0x130, self.ALLOCATOR, self.RAM + 0x2100 if lock_enabled else 0)
        self.write_words(self.ALLOCATOR + 0x2C, self.LOCK | 1, self.UNLOCK | 1)
        self.uc.hook_add(UC_HOOK_MEM_READ, self._read_guard)

    def _read_guard(self, uc, access, address, size, value, _):
        for start, length in self.freed.items():
            if address < start + length and start < address + size:
                raise registry.ProbeError("native read of freed synthetic allocation: 0x%08X" % address)

    def _instruction(self, uc, address, size, data):
        if address == self.pause_at:
            self.pause_at = None
            self.paused = True
            self.pause_context = uc.context_save()
            uc.emu_stop()
            return
        if address in (self.PRIVATE_CALLBACK, self.GLOBAL_CALLBACK, self.LOCK, self.UNLOCK):
            self.instructions += 1
            args = [uc.reg_read(reg) for reg in registry.REGS]
            self.calls.append({"address": "0x%08X" % address, "args": args,
                               "lr": "0x%08X" % uc.reg_read(UC_ARM_REG_LR)})
            if address in (self.PRIVATE_CALLBACK, self.GLOBAL_CALLBACK):
                self.events.append({"kind": "private" if address == self.PRIVATE_CALLBACK else "global",
                                    "descriptor": args[0], "context": args[1],
                                    "value": self.words(args[0] + 8)[0], "lock_depth": self.lock_depth})
                if address == self.PRIVATE_CALLBACK and self.private_callback_action:
                    # Explicit callback-service stub: tail-delegate once to an ORIGINAL
                    # API. The original notify return LR is preserved; no native API is
                    # stubbed or re-entered through an independent emulator invocation.
                    action = self.private_callback_action
                    self.private_callback_action = None
                    if action == "unsubscribe_self":
                        values = (self.APP, self.NAME)
                        target = UNSUBSCRIBE
                    elif action == "revert_without_app_callback":
                        scratch = self.ASSIGNMENT + 0x40
                        self.write_words(scratch, 0, self.NAME, 0)
                        values = (self.APP, 0, 1, scratch)
                        target = SET_SILENT
                    else:
                        raise registry.ProbeError("unknown callback stub action")
                    for reg, value in zip(registry.REGS, values):
                        uc.reg_write(reg, value)
                    uc.reg_write(UC_ARM_REG_PC, target | 1)
                    return
            else:
                self.lock_depth += 1 if address == self.LOCK else -1
                if self.lock_depth not in (0, 1):
                    raise registry.ProbeError("unexpected synthetic lock depth")
                self.events.append({"kind": "lock" if address == self.LOCK else "unlock", "args": args[:2]})
            self._return(self.callback_results.get(address, 0))
            return
        if address == self.FREE:
            pointer = uc.reg_read(registry.REGS[0])
            if pointer in self.blocks:
                self.freed[pointer] = self.blocks[pointer]
        for name, (start, end) in EXTRA_NATIVE.items():
            if start <= address and address + size <= end:
                self.instructions += 1
                self.visited.add(name)
                return
        super()._instruction(uc, address, size, data)

    def register_private(self, value=0):
        result = self.register(value=value)
        if result:
            raise registry.ProbeError("fixture registration failed: %s" % result)
        result, descriptor = self.lookup()
        if result or not descriptor:
            raise registry.ProbeError("fixture lookup failed")
        return descriptor

    def subscribe(self, global_slot=False):
        callback = self.GLOBAL_CALLBACK if global_slot else self.PRIVATE_CALLBACK
        context = self.CONTEXT + (16 if global_slot else 0)
        self.write_words(self.PAIR, callback | 1, context)
        return self.run(SUBSCRIBE, self.APP, 0 if global_slot else self.NAME, self.PAIR)

    def unsubscribe(self, global_slot=False):
        return self.run(UNSUBSCRIBE, self.APP, 0 if global_slot else self.NAME)

    def set_integer(self, value, notify=True, name=None, index=None):
        name_ptr = self.NAME
        if name is not None:
            name_ptr = self.RAM + 0x3A00
            self.write(name_ptr, name.encode("ascii") + b"\0")
        if index is not None:
            self.write_words(self.ASSIGNMENT, 0, name_ptr, value & 0xFFFFFFFF, index & 0xFFFFFFFF)
            return self.run(SET_INDEX, self.APP, 1, self.ASSIGNMENT)
        self.write_words(self.ASSIGNMENT, 0, name_ptr, value & 0xFFFFFFFF)
        return self.run(SET_NOTIFY if notify else SET_SILENT, self.APP, 0, 1, self.ASSIGNMENT)

    def callback_events(self):
        return [event for event in self.events if event["kind"] in ("private", "global")]

    def begin_paused_notify(self, descriptor, pause_at):
        """Stop before an exact original instruction; no fictitious OS scheduling."""
        self.pause_at = pause_at
        self.paused = False
        try:
            self.run(NOTIFY, self.APP, descriptor)
        except registry.ProbeError as exc:
            if not self.paused or "bound exhausted" not in str(exc):
                raise
        if not self.paused:
            raise registry.ProbeError("requested native pause point was not reached")
        return self.pause_context

    def unsubscribe_while_paused(self):
        """Use a distinct synthetic stack, preserving the suspended native frame."""
        if not self.paused:
            raise registry.ProbeError("no native notification is paused")
        suspended_stack = self.STACK
        self.STACK = suspended_stack - 0x1000
        try:
            return self.unsubscribe()
        finally:
            self.STACK = suspended_stack

    def resume_saved(self, context):
        self.uc.context_restore(context)
        self.instructions = 0
        self.stopped = False
        try:
            self.uc.emu_start(self.uc.reg_read(UC_ARM_REG_PC) | 1, self.STOP + 2,
                              timeout=self.TIMEOUT_US, count=self.MAX_INSTRUCTIONS)
        except UcError as exc:
            raise registry.ProbeError("Unicorn rejected resumed execution: %s" % exc) from exc
        if not self.stopped or self.uc.reg_read(UC_ARM_REG_SP) != self.STACK:
            raise registry.ProbeError("resumed execution did not finish within bounds / restore SP")
        return self.uc.reg_read(registry.REGS[0])
