#!/usr/bin/env python3
"""Offline fault-injection tests for og3k_load's first-install transaction."""

from __future__ import annotations

import contextlib
import io as textio
import unittest

import og3k_load as loader
from og3k_plan import EMIT_FN, HOOKS, OWNED, Plan


class CheckedPlan:
    """Reuse one assembled plan while keeping apply()'s public Plan surface."""

    def __init__(self, plan):
        self._plan = plan

    def __getattr__(self, name):
        return getattr(self._plan, name)

    def check(self):
        return []


class FakeIO:
    def __init__(self, plan, overrides=None, fail_write=None, fail_sync=None):
        self.plan = plan
        self.memory = dict(overrides or {})
        self.events = []
        self.fail_write = fail_write
        self.fail_sync = fail_sync
        self.write_count = 0
        self.sync_count = 0
        self.failed_write = False

    def read(self, address):
        self.events.append(("read", address))
        return self.memory.get(address, self.plan.word(address))

    def write(self, address, value):
        self.write_count += 1
        self.events.append(("write", address, value))
        if (not self.failed_write and self.fail_write is not None and
                self.fail_write(address, value, self.write_count)):
            self.failed_write = True
            raise loader.WriteFailed(f"injected write failure 0x{address:08X}")
        changed = self.memory.get(address, self.plan.word(address)) != value
        self.memory[address] = value
        return changed

    def sync(self):
        self.sync_count += 1
        self.events.append(("sync", self.sync_count))
        if self.fail_sync is not None and self.fail_sync(self.sync_count):
            raise loader.CacheFailed("injected cache failure")


class LoaderTransactionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.real_plan = Plan()
        cls.plan = CheckedPlan(cls.real_plan)
        cls.items = list(cls.real_plan.all())
        cls.desired = {address: value for address, value, _ in cls.items}
        cls.hooks = {site: cls.desired[site] for site, *_ in HOOKS}
        cls.exec_sites = set(OWNED) | set(cls.hooks) | {EMIT_FN}

    def plan_hook_writes(self, io):
        return [(event[1], event[2]) for event in io.events
                if len(event) == 3 and event[0] == "write" and
                event[1] in self.hooks and event[2] == self.hooks[event[1]]]

    def run_apply(self, io, check=False):
        with contextlib.redirect_stdout(textio.StringIO()):
            return loader.apply(self.plan, io, check=check)

    def test_check_is_read_only(self):
        io = FakeIO(self.real_plan)
        self.assertEqual(self.run_apply(io, check=True), 0)
        self.assertFalse(any(event[0] in ("write", "sync") for event in io.events))

    def test_success_publishes_body_before_hooks_and_picker_last(self):
        io = FakeIO(self.real_plan)
        self.assertEqual(self.run_apply(io), 0)
        first_sync = next(i for i, event in enumerate(io.events) if event[0] == "sync")
        hook_events = [(i, e[1]) for i, e in enumerate(io.events)
                       if e[0] == "write" and e[1] in self.hooks and
                       e[2] == self.hooks[e[1]]]
        self.assertTrue(hook_events)
        self.assertTrue(all(index > first_sync for index, _ in hook_events))
        self.assertEqual([address for _, address in hook_events],
                         [site for site, *_ in HOOKS])
        self.assertEqual(hook_events[-1][1], HOOKS[-1][0])
        self.assertGreaterEqual(io.sync_count, 2)

    def test_foreign_active_inactive_and_legacy_sites_make_zero_writes(self):
        cases = [HOOKS[0][0], next(iter(set(OWNED) - set(self.hooks))), EMIT_FN]
        for site in cases:
            with self.subTest(site=f"0x{site:08X}"):
                io = FakeIO(self.real_plan, {site: 0xE7F001F0})
                self.assertEqual(self.run_apply(io), 1)
                self.assertFalse(any(e[0] in ("write", "sync") for e in io.events))

    def test_stale_private_word_requires_cold_boot_with_zero_writes(self):
        private = next(address for address, value, _ in self.items
                       if loader.PRIVATE_LO <= address < loader.PRIVATE_HI and
                       value != self.real_plan.word(address))
        io = FakeIO(self.real_plan, {private: 0x12345678})
        self.assertEqual(self.run_apply(io), 1)
        self.assertFalse(any(e[0] in ("write", "sync") for e in io.events))

    def test_body_failure_never_arms_a_hook(self):
        body = [(a, v) for a, v, _ in self.items if a not in self.exec_sites]
        samples = [body[0], body[len(body) // 2], body[-1]]
        for address, wanted in samples:
            with self.subTest(address=f"0x{address:08X}"):
                io = FakeIO(self.real_plan,
                            fail_write=lambda a, v, n, target=address:
                            a == target and v == wanted)
                self.assertEqual(self.run_apply(io), 1)
                self.assertEqual(self.plan_hook_writes(io), [])
                for site in self.exec_sites:
                    self.assertEqual(io.memory.get(site, self.real_plan.word(site)),
                                     self.real_plan.word(site))

    def test_first_cache_failure_never_arms_a_hook(self):
        io = FakeIO(self.real_plan, fail_sync=lambda count: count == 1)
        self.assertEqual(self.run_apply(io), 1)
        self.assertEqual(self.plan_hook_writes(io), [])
        for site in self.exec_sites:
                self.assertEqual(io.memory.get(site, self.real_plan.word(site)),
                                 self.real_plan.word(site))

    def test_final_cache_failure_rolls_all_hooks_back(self):
        io = FakeIO(self.real_plan, fail_sync=lambda count: count == 2)
        self.assertEqual(self.run_apply(io), 1)
        self.assertTrue(self.plan_hook_writes(io))
        for site in self.exec_sites:
            self.assertEqual(io.memory.get(site, self.real_plan.word(site)),
                             self.real_plan.word(site))
        self.assertGreaterEqual(io.sync_count, 3)

    def test_each_hook_failure_rolls_all_hooks_back(self):
        for failed_site, failed_value in list(self.hooks.items()):
            with self.subTest(site=f"0x{failed_site:08X}"):
                io = FakeIO(self.real_plan,
                            fail_write=lambda a, v, n, site=failed_site,
                            value=failed_value: a == site and v == value)
                self.assertEqual(self.run_apply(io), 1)
                for site in self.exec_sites:
                    self.assertEqual(io.memory.get(site, self.real_plan.word(site)),
                                     self.real_plan.word(site))
                self.assertGreaterEqual(io.sync_count, 2)

    def test_partial_or_different_install_is_read_only(self):
        first = HOOKS[0][0]
        io = FakeIO(self.real_plan, {first: self.hooks[first]})
        self.assertEqual(self.run_apply(io), 1)
        self.assertFalse(any(e[0] in ("write", "sync") for e in io.events))

    def test_exact_install_is_idempotent(self):
        installed = dict(self.desired)
        io = FakeIO(self.real_plan, installed)
        self.assertEqual(self.run_apply(io), 0)
        self.assertFalse(any(e[0] in ("write", "sync") for e in io.events))


if __name__ == "__main__":
    unittest.main()
