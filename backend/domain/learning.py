from math import pi,cos,sin
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error

def design(hour, clear):
    angle=2*pi*hour/24
    return [sin(angle),cos(angle),sin(2*angle),cos(2*angle),int(clear)]

def calculate(data):
    if data.get('kind') == 'prepcard':
        return calculate_prepcard(data)
    rows=data['rows']
    train,held=rows[:-6],rows[-6:]
    model=LinearRegression()
    model.fit([design(x['hour'],x['clear']) for x in train],[x['load_wh'] for x in train])
    actual=[x['load_wh'] for x in held]
    predicted=model.predict([design(x['hour'],x['clear']) for x in held])
    target=float(model.predict([design(data['window']['hour'],data['clear'])])[0])
    mae=float(mean_absolute_error(actual,predicted))
    return {'mae':round(mae,3),'plan_wh':round(max(target,0)+mae,3),'held_out':len(held),
           'period':24,'training':len(train)}

def _tier(clear):
    return 'clear' if clear else 'cloudy'

def calculate_prepcard(data):
    """同一批复核读数一次拟合，分别预测晴/阴两档。

    余量取留出段（末 6 小时）内同天气样本里少算最多的电量，
    即 max(实际 - 预测, 0)；该天气在留出段没有样本时不给该档（null）。
    """
    rows=data['rows']
    train,held=rows[:-6],rows[-6:]
    model=LinearRegression()
    model.fit([design(x['hour'],x['clear']) for x in train],[x['load_wh'] for x in train])
    hour=data['window']['hour']
    tiers={}
    for clear in (True,False):
        same=[x for x in held if x['clear']==clear]
        if not same:
            tiers[_tier(clear)]=None
            continue
        predicted_held=model.predict([design(x['hour'],x['clear']) for x in same])
        margin=max(0.0, max(x['load_wh']-p for x,p in zip(same,predicted_held)))
        target=float(model.predict([design(hour,clear)])[0])
        tiers[_tier(clear)]=round(max(target,0.0)+margin,3)
    return {'kind':'prepcard','clear_wh':tiers['clear'],'cloudy_wh':tiers['cloudy'],
            'held_out':len(held),'period':24,'training':len(train)}
