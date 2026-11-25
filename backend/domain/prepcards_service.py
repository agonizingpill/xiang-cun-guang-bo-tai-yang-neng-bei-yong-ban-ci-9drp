from core.queueing import result, submit
from core.records import get, insert, need, scan, update
from domain.airslots_model import airslots
from domain.battery_logs_model import battery_logs
from domain.prepcards_model import prepcards

WEATHER = {True: '晴天', False: '阴天'}


def prepare_card(conn, user, data):
    slot = get(conn, airslots, data.airslot)
    rows = sorted([x for x in scan(conn, battery_logs) if x['meter'] == data.meter and x['verified']],
                  key=lambda x: x['hour'])
    need(len(rows) >= 36 and all(y['hour'] - x['hour'] == 1 for x, y in zip(rows, rows[1:])),
         '要有连续三十六小时审签读数')
    return submit(user, {'kind': 'prepcard', 'window': slot, 'rows': rows})


def issue_card(conn, user, data):
    run = result(user, data.token)
    need(run.get('result', {}).get('kind') == 'prepcard', '计算号不是晴阴备播卡任务')
    window = run['input']['window']
    stats = run['result']
    need(get(conn, airslots, window['code'])['hour'] == window['hour'], '节目时间已变')
    return insert(conn, prepcards, code=data.code, airslot=window['code'],
                  meter=run['input']['rows'][0]['meter'], token=data.token,
                  clear_wh=stats['clear_wh'], cloudy_wh=stats['cloudy_wh'], state='待领用',
                  receipt=None, claimed_weather=None, claimed_wh=None)


def claim_card(conn, user, data):
    card = get(conn, prepcards, data.card, lock=True)
    # 同一笔领用断线重试：凭据不变，直接拿回原卡，不重复领卡
    if card['receipt'] == data.receipt:
        return card
    need(card['state'] == '待领用', '此备播卡已被其他凭据领走')
    required = card['clear_wh'] if data.clear else card['cloudy_wh']
    need(required is not None, '留出段没有该天气样本，不发这一档')
    return update(conn, prepcards, data.card, state='已领用', receipt=data.receipt,
                  claimed_weather=WEATHER[data.clear], claimed_wh=required)
