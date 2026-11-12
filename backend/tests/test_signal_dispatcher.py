# backend/tests/test_signal_dispatcher.py
"""SignalDispatcher：展示/推送/开仓一条链的编排单测（项目约定：asyncio.run 驱动）。"""
import queue

from app.signals.dispatcher import SignalDispatcher


class _FakeStore:
    def __init__(self):
        self.items = []

    def add(self, record):
        self.items.append(dict(record))


class _FakeAutoTrader:
    def __init__(self, actions):
        self.actions = list(actions)  # 按调用顺序返回的 action
        self.seen = []

    async def on_signal(self, record):
        self.seen.append(record['symbol'])
        action = self.actions.pop(0) if self.actions else 'skip'
        return {'action': action, 'reason': 'test'}


class _FakeNotifier:
    def __init__(self):
        self.pushed = []

    async def push_signal_batch(self, batch, settings=None):
        self.pushed.append([r['symbol'] for r in batch])
        return True


def test_dispatch_batch_fans_out_to_store_push_and_trader(monkeypatch):
    store = _FakeStore()
    trader = _FakeAutoTrader(['skip', 'open', 'skip'])
    fake_notifier = _FakeNotifier()
    monkeypatch.setattr('app.signals.dispatcher.notifier', fake_notifier)

    dispatcher = SignalDispatcher(store=store, auto_trader=trader)

    async def run():
        return await dispatcher.dispatch_batch([{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}])

    stats = _run(run())

    assert stats == {'total': 3, 'open': 1, 'skip': 2, 'error': 0}
    assert [r['symbol'] for r in store.items] == ['A', 'B', 'C']      # 展示全量保留
    assert fake_notifier.pushed == [['A', 'B', 'C']]                  # 推送收到同一批
    assert trader.seen == ['A', 'B', 'C']                             # 开仓逐条处理


def test_dispatch_batch_survives_trader_error(monkeypatch):
    class _BoomTrader:
        async def on_signal(self, record):
            if record['symbol'] == 'B':
                raise RuntimeError('boom')
            return {'action': 'skip'}

    store = _FakeStore()
    fake_notifier = _FakeNotifier()
    monkeypatch.setattr('app.signals.dispatcher.notifier', fake_notifier)
    dispatcher = SignalDispatcher(store=store, auto_trader=_BoomTrader())

    async def run():
        return await dispatcher.dispatch_batch(
            [{'symbol': 'A'}, {'symbol': 'B'}, {'symbol': 'C'}])

    stats = _run(run())

    assert stats['error'] == 1
    assert stats['skip'] == 2
    assert len(store.items) == 3  # 单条异常不中断整批


def test_drain_batch_caps_at_max():
    q = queue.Queue()
    for i in range(50):
        q.put({'symbol': f'S{i}'})
    dispatcher = SignalDispatcher(store=_FakeStore(), auto_trader=_FakeAutoTrader([]), queue_obj=q)

    batch = dispatcher._drain_batch(q.get_nowait())

    assert len(batch) == 20  # notifier.MAX_BATCH
    assert q.qsize() == 30


def test_consume_loop_processes_queue(monkeypatch):
    """端到端：队列 -> 消费循环 -> 三路分发 -> stop 退出。"""
    store = _FakeStore()
    trader = _FakeAutoTrader(['open'])
    fake_notifier = _FakeNotifier()
    monkeypatch.setattr('app.signals.dispatcher.notifier', fake_notifier)

    q = queue.Queue()
    q.put({'symbol': 'BTC'})
    dispatcher = SignalDispatcher(store=store, auto_trader=trader, queue_obj=q)

    def run():
        async def _main():
            import asyncio
            task = dispatcher.start()  # start 内部 create_task，需要事件循环
            for _ in range(100):
                await asyncio.sleep(0.05)
                if len(store.items) >= 1 and trader.seen:
                    break
            await dispatcher.stop()
        _run(_main())

    run()
    assert [r['symbol'] for r in store.items] == ['BTC']
    assert trader.seen == ['BTC']


def _run(coro):
    import asyncio
    return asyncio.run(coro)
