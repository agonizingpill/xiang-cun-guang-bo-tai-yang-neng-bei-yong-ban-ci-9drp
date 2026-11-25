import json
import os
import sys
import tempfile

_TMP_DB = os.path.join(tempfile.mkdtemp(prefix='prepcard-test-'), 'test.db')
os.environ['DATABASE_URL'] = 'sqlite:///' + _TMP_DB
os.environ['REDIS_URL'] = 'redis://localhost:6379/0'
os.environ['JWT_SECRET'] = 'test-secret'
os.environ['SEED_DEMO'] = 'false'

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select  # noqa: E402
import pytest  # noqa: E402

from core import queueing  # noqa: E402
from core import audit as _audit  # noqa: E402,F402  注册 audit_trail 表
from core.db import engine, metadata, transaction  # noqa: E402
from domain import learning, prepcards_service as svc  # noqa: E402
from domain.airslots_model import airslots  # noqa: E402
from domain.battery_logs_model import battery_logs  # noqa: E402
from domain.prepcards_model import prepcards  # noqa: E402


class FakeBroker:
    """内存版 Redis：只覆盖队列与计算任务用到的接口。"""

    def __init__(self):
        self.kv = {}

    def pipeline(self):
        outer = self

        class Pipe:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                outer.multi = None

            def set(self, key, value, ex=None):
                outer.kv[key] = value

            def rpush(self, key, value):
                outer.kv.setdefault(key, []).append(value)

            def execute(self):
                outer.multi = None

        outer.multi = Pipe()
        return outer.multi

    def set(self, key, value, ex=None):
        self.kv[key] = value

    def get(self, key):
        return self.kv.get(key)

    def lrange(self, key, start, end):
        return list(self.kv.get(key, []))

    def lpush(self, key, value):
        self.kv.setdefault(key, []).insert(0, value)

    def lrem(self, key, count, value):
        if key in self.kv and value in self.kv[key]:
            self.kv[key].remove(value)

    def blmove(self, src, dst, timeout, src2=None, dest=None):
        items = self.kv.get(src, [])
        if not items:
            return None
        item = items.pop(0)
        self.kv.setdefault(dst, []).append(item)
        return item

    def ping(self):
        return True


def run_job(token):
    item = queueing.broker.lrange(queueing.QUEUE, 0, -1)[0]
    job = json.loads(item)
    assert job['token'] == token
    result = learning.calculate(job['input'])
    queueing.broker.set(f'compute:{token}',
                        json.dumps({'owner': job['owner'], 'input': job['input'],
                                    'status': 'ready', 'result': result}, allow_nan=False))


USER = {'sub': 'operator@demo.test', 'role': 'operator'}
REVIEWER = {'sub': 'reviewer@demo.test', 'role': 'reviewer'}


def setup_db():
    metadata.drop_all(engine)
    metadata.create_all(engine)
    with transaction() as conn:
        conn.execute(airslots.insert().values(code='AIR-17', title='晚间村讯', hour=18,
                                              license='本地插播', offline=True))
        conn.execute(airslots.insert().values(code='AIR-08', title='田间校时', hour=8,
                                              license='台外联播', offline=False))


def make_rows(clear_seq, held_overspend=0.0, seed=0):
    """造连续审签读数，默认 36 条（末 6 条为留出段）。"""
    n = len(clear_seq) if isinstance(clear_seq, (list, tuple)) else 36
    rows = []
    for i in range(n):
        clear = clear_seq[i] if isinstance(clear_seq, (list, tuple)) else clear_seq
        held = i >= n - 6
        load = 90 + (18 if i % 24 in (16, 17, 18, 19, 20, 21, 22, 23) else 0)
        if held:
            load += held_overspend
        rows.append({'code': f'WH-{seed}-{i:02d}', 'meter': 'BAT-T1', 'hour': i,
                     'load_wh': float(load), 'clear': bool(clear), 'verified': True})
    return rows


def insert_rows(rows):
    with transaction() as conn:
        for row in rows:
            conn.execute(battery_logs.insert().values(**row))


def prepare_input(rows, airslot='AIR-17'):
    return {'kind': 'prepcard',
            'window': {'code': airslot, 'hour': 18 if airslot == 'AIR-17' else 8},
            'rows': rows}


def test_prepcard_margin_is_max_underestimate_by_weather():
    # 训练段晴阴都有；留出段 6 条全晴，阴天无留出样本
    seq = [i % 3 != 0 for i in range(30)] + [True] * 6
    rows = make_rows(seq, held_overspend=12.0)
    out = learning.calculate_prepcard(prepare_input(rows))
    assert out['kind'] == 'prepcard'
    assert out['cloudy_wh'] is None          # 留出段无阴天样本 -> 不给档
    assert out['clear_wh'] is not None
    # 留出段每个晴样本都被少算 12 Wh，最大欠发即余量，应被计入
    held = rows[-6:]
    design = [learning.design(x['hour'], x['clear']) for x in held]
    from sklearn.linear_model import LinearRegression
    model = LinearRegression().fit([learning.design(x['hour'], x['clear']) for x in rows[:-6]],
                                   [x['load_wh'] for x in rows[:-6]])
    margin = max(0.0, max(x['load_wh'] - p for x, p in zip(held, model.predict(design))))
    # OLS 只在训练段拟合，留出段注入的抬高无法被完全吸收，余量为同天气最大欠发（量级在注入值附近）
    assert 0 < margin < 12.0 * 1.5
    target = float(model.predict([learning.design(prepare_input(rows)['window']['hour'], True)])[0])
    assert out['clear_wh'] == pytest.approx(max(target, 0.0) + margin, abs=1e-3)


def test_prepcard_both_tiers_when_both_held_out():
    clear_seq = [True] * 33 + [False, False, False]  # 留出段含 3 晴 3 阴
    rows = make_rows(clear_seq)
    out = learning.calculate_prepcard(prepare_input(rows))
    assert out['clear_wh'] is not None and out['cloudy_wh'] is not None
    assert out['held_out'] == 6


def test_legacy_reserve_calculation_unchanged():
    rows = make_rows([True] * 36)
    out = learning.calculate({'rows': rows, 'window': {'hour': 18}, 'clear': True})
    assert set(out) == {'mae', 'plan_wh', 'held_out', 'period', 'training'}


def test_prepare_rejects_short_readings(monkeypatch):
    monkeypatch.setattr(queueing, 'broker', FakeBroker())
    setup_db()
    insert_rows(make_rows([True] * 30))
    from domain.prepcards_schemas import PrepareCard
    with pytest.raises(Exception) as exc:
        with transaction() as conn:
            svc.prepare_card(conn, USER, PrepareCard(airslot='AIR-17', meter='BAT-T1'))
    assert '三十六小时' in str(exc.value.detail)


def test_full_issue_and_claim_flow(monkeypatch):
    broker = FakeBroker()
    monkeypatch.setattr(queueing, 'broker', broker)
    setup_db()
    insert_rows(make_rows([i % 3 != 0 for i in range(30)] + [True] * 6, held_overspend=10.0))

    from domain.prepcards_schemas import ClaimCard, IssueCard, PrepareCard
    with transaction() as conn:
        queued = svc.prepare_card(conn, USER, PrepareCard(airslot='AIR-17', meter='BAT-T1'))
    run_job(queued['token'])

    with transaction() as conn:
        card = svc.issue_card(conn, REVIEWER, IssueCard(code='PC-1', token=queued['token']))
    assert card['state'] == '待领用'
    assert card['clear_wh'] is not None
    assert card['cloudy_wh'] is None

    # 阴天档无留出样本，拒绝领卡
    with pytest.raises(Exception) as exc:
        with transaction() as conn:
            svc.claim_card(conn, USER, ClaimCard(card='PC-1', receipt='RC-1', clear=False))
    assert '不发这一档' in exc.value.detail

    # 晴档可领
    with transaction() as conn:
        claimed = svc.claim_card(conn, USER, ClaimCard(card='PC-1', receipt='RC-1', clear=True))
    assert claimed['state'] == '已领用'
    assert claimed['claimed_weather'] == '晴天'
    assert claimed['receipt'] == 'RC-1'

    # 断线后同一凭据重试 -> 拿回原卡，不重复领
    with transaction() as conn:
        retry = svc.claim_card(conn, USER, ClaimCard(card='PC-1', receipt='RC-1', clear=True))
    assert retry['receipt'] == 'RC-1' and retry['claimed_wh'] == claimed['claimed_wh']

    # 另一人不同凭据 -> 认先领成的那份
    other = {'sub': 'operator2@demo.test', 'role': 'operator'}
    with pytest.raises(Exception) as exc:
        with transaction() as conn:
            svc.claim_card(conn, other, ClaimCard(card='PC-1', receipt='RC-2', clear=True))
    assert '已被其他凭据领走' in exc.value.detail

    with transaction() as conn:
        row = dict(conn.execute(select(prepcards).where(prepcards.c.code == 'PC-1')).mappings().one())
    assert row['receipt'] == 'RC-1'


def test_second_receipt_loses_race_then_its_retry_is_still_rejected(monkeypatch):
    """模拟两人同时提交：RC-A 先领成，RC-B 冲突；RC-B 再重试仍冲突。"""
    broker = FakeBroker()
    monkeypatch.setattr(queueing, 'broker', broker)
    setup_db()
    insert_rows(make_rows([True] * 33 + [False, False, False]))
    from domain.prepcards_schemas import ClaimCard, IssueCard, PrepareCard

    with transaction() as conn:
        queued = svc.prepare_card(conn, USER, PrepareCard(airslot='AIR-08', meter='BAT-T1'))
    run_job(queued['token'])
    with transaction() as conn:
        svc.issue_card(conn, REVIEWER, IssueCard(code='PC-2', token=queued['token']))

    with transaction() as conn:
        first = svc.claim_card(conn, USER, ClaimCard(card='PC-2', receipt='RC-A', clear=False))
    assert first['receipt'] == 'RC-A'
    for _ in range(2):
        with pytest.raises(Exception) as exc:
            with transaction() as conn:
                svc.claim_card(conn, USER, ClaimCard(card='PC-2', receipt='RC-B', clear=False))
        assert '已被其他凭据领走' in exc.value.detail


def test_http_layer_and_idempotency(monkeypatch):
    from fastapi.testclient import TestClient
    broker = FakeBroker()
    monkeypatch.setattr(queueing, 'broker', broker)
    setup_db()
    insert_rows(make_rows([i % 2 == 0 for i in range(36)]))

    from core.app import app
    with TestClient(app) as client:
        login = client.post('/auth/login', json={'email': 'reviewer@demo.test',
                                                 'password': 'DemoC0de!2026'}).json()
        headers = {'Authorization': 'Bearer ' + login['token']}

        queued = client.post('/prepcards/prepare', json={'airslot': 'AIR-17', 'meter': 'BAT-T1'},
                             headers=headers).json()
        run_job(queued['token'])
        issued = client.post('/prepcards/issue', json={'code': 'PC-WEB', 'token': queued['token']},
                             headers=headers)
        assert issued.status_code == 200

        op_login = client.post('/auth/login', json={'email': 'operator@demo.test',
                                                    'password': 'DemoC0de!2026'}).json()
        op_headers = {'Authorization': 'Bearer ' + op_login['token']}
        first = client.post('/prepcards/claim',
                            json={'card': 'PC-WEB', 'receipt': 'RC-WEB', 'clear': True},
                            headers=op_headers)
        assert first.status_code == 200 and first.json()['receipt'] == 'RC-WEB'
        retry = client.post('/prepcards/claim',
                            json={'card': 'PC-WEB', 'receipt': 'RC-WEB', 'clear': True},
                            headers=op_headers)
        assert retry.status_code == 200 and retry.json() == first.json()
        rows = client.get('/prepcards', headers=op_headers).json()
        assert rows[0]['state'] == '已领用'

        # viewer 不能提交
        v = client.post('/auth/login', json={'email': 'viewer@demo.test',
                                             'password': 'DemoC0de!2026'}).json()
        denied = client.post('/prepcards/prepare', json={'airslot': 'AIR-17', 'meter': 'BAT-T1'},
                             headers={'Authorization': 'Bearer ' + v['token']})
        assert denied.status_code == 403
        # 未登录 401
        assert client.get('/prepcards').status_code == 401
