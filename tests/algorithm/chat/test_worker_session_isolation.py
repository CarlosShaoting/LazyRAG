"""Regression: an interrupted agent must not leak history through a reused worker."""
import threading
import unittest

import lazyllm


class WorkerIsolationTest(unittest.TestCase):
    def test_reused_worker_discards_interrupted_workspace(self):
        def interrupted():
            lazyllm.locals['_lazyllm_agent']['workspace'] = {'history': ['old retry request']}
            return threading.get_ident()

        def inspect():
            return (threading.get_ident(), lazyllm.globals._sid,
                    dict(lazyllm.locals['_lazyllm_agent']))

        with lazyllm.ThreadPoolExecutor(max_workers=1) as pool:
            lazyllm.globals._init_sid('isolation-old')
            worker = pool.submit(interrupted).result()
            lazyllm.globals._init_sid('isolation-new')
            next_worker, sid, state = pool.submit(inspect).result()
        self.assertEqual(worker, next_worker)
        self.assertEqual(sid, 'isolation-new')
        self.assertEqual(state, {})

    def test_concurrent_sessions_keep_separate_state(self):
        barrier = threading.Barrier(2)

        def run(label):
            lazyllm.locals['_lazyllm_agent']['workspace'] = {'history': [label]}
            barrier.wait(timeout=5)
            return lazyllm.globals._sid, lazyllm.locals['_lazyllm_agent']['workspace']['history']

        with lazyllm.ThreadPoolExecutor(max_workers=2) as pool:
            lazyllm.globals._init_sid('isolation-a')
            first = pool.submit(run, 'a')
            lazyllm.globals._init_sid('isolation-b')
            second = pool.submit(run, 'b')
            self.assertEqual(first.result(), ('isolation-a', ['a']))
            self.assertEqual(second.result(), ('isolation-b', ['b']))


if __name__ == '__main__':
    unittest.main()
