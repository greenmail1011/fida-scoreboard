"""End-to-end test of Google admin login with a mock Firebase.
usage: python3 auth_test.py <repo dir> <out dir>"""
import sys, threading, http.server, functools, json, os
from playwright.sync_api import sync_playwright

REPO, OUT = sys.argv[1], sys.argv[2]
HERE = os.path.dirname(os.path.abspath(__file__))
MOCK = open(os.path.join(HERE, 'mockfb.js'), encoding='utf-8').read()
os.makedirs(OUT, exist_ok=True)
class Q(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a): pass
H = functools.partial(Q, directory=REPO)
srv = http.server.ThreadingHTTPServer(('127.0.0.1', 8765), H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
BASE = 'http://127.0.0.1:8765/index.html'
X = 'judge.x@gmail.com'
SUPER = 'dronex666666@gmail.com'
fails = []

def check(name, cond, info=''):
    print(('PASS ' if cond else 'FAIL ') + name + (f'  [{info}]' if info and not cond else ''))
    if not cond: fails.append(name)

with sync_playwright() as p:
    b = p.chromium.launch()
    ctx = b.new_context(viewport={'width': 1280, 'height': 900})
    state = {'cdn': 'mock'}  # 'mock' or 'down'
    def cdn(route):
        if state['cdn'] == 'down':
            return route.abort()
        body = MOCK if 'firebase-app-compat' in route.request.url else ''
        route.fulfill(status=200, content_type='application/javascript', body=body)
    ctx.route('**/cdn.jsdelivr.net/**', cdn)
    pg = ctx.new_page()
    errs = []
    pg.on('pageerror', lambda e: errs.append(str(e)))
    T = lambda: pg.locator('#toast').inner_text()
    phase = lambda: pg.evaluate("(JSON.parse(localStorage.getItem('fida-ds-score-v3'))||{match:{phase:'setup'}}).match.phase")
    score = lambda: pg.evaluate("JSON.parse(localStorage.getItem('fida-ds-score-v3')).match.score")
    auth_txt = lambda: pg.locator('#v-control .js-auth').inner_text()
    def key(k):
        pg.locator('body').click(position={'x': 5, 'y': 5}); pg.keyboard.press(k); pg.wait_for_timeout(250)

    # 1. not signed in
    pg.goto(BASE + '#control'); pg.wait_for_timeout(600)
    check('1 login button shown', '用 Google 登入' in auth_txt(), auth_txt())
    check('1 no PIN field', pg.locator('[data-cp-pin]').count() == 0)
    check('1 room defaults to MAIN', pg.locator('#v-control [data-cr]').input_value() == 'MAIN')
    key('g')
    check('1 start blocked', '請先' in T(), T())
    check('1 phase still setup', phase() == 'setup', phase())
    check('1 name inputs disabled', pg.locator('#name-red').is_disabled())
    check('1 body locked', pg.evaluate("document.body.classList.contains('locked')"))
    pg.screenshot(path=f'{OUT}/1_signed_out.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 260})

    # 2. signed in, not an admin
    pg.evaluate(f"localStorage.setItem('mock-login-as','{X}')")
    pg.locator('#v-control [data-auth="in"]').click(); pg.wait_for_timeout(500)
    check('2 email shown', X in auth_txt(), auth_txt())
    check('2 marked not admin', '不是管理員' in auth_txt(), auth_txt())
    key('g')
    check('2 start blocked for non-admin', '不是管理員' in T(), T())
    pg.screenshot(path=f'{OUT}/2_not_admin.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 260})
    check('2 forged write denied by rules', pg.evaluate("firebase.database().ref('rooms/MAIN/state').set({x:1}).then(()=>'ok',e=>e.code)") == 'PERMISSION_DENIED')
    check('2 non-admin cannot read admin list', pg.evaluate("firebase.database().ref('admins').once('value').then(()=>'ok',e=>e.code)") == 'PERMISSION_DENIED')
    check('2 non-admin cannot add self', pg.evaluate(f"firebase.database().ref('admins/{X.replace('.', ',')}').set(true).then(()=>'ok',e=>e.code)") == 'PERMISSION_DENIED')

    # 3. super admin adds X
    pg.locator('#v-control [data-auth="out"]').click(); pg.wait_for_timeout(300)
    check('3 signed out', '用 Google 登入' in auth_txt(), auth_txt())
    pg.evaluate(f"localStorage.setItem('mock-login-as','{SUPER}')")
    pg.locator('#v-control [data-auth="in"]').click(); pg.wait_for_timeout(500)
    check('3 super chip', '超級管理員' in auth_txt(), auth_txt())
    check('3 admin list visible', pg.locator('#v-control .admins').count() == 1)
    pg.locator('#v-control [data-admin-new]').fill(X.upper())
    pg.locator('#v-control [data-admin-add]').click(); pg.wait_for_timeout(400)
    db = pg.evaluate("JSON.parse(localStorage.getItem('mock-db'))")
    check('3 X stored lowercase, dots as commas', db.get('admins', {}).get('judge,x@gmail,com') is True, json.dumps(db))
    check('3 X listed', X in auth_txt(), auth_txt())
    pg.screenshot(path=f'{OUT}/3_super.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 340})
    pg.locator('#v-control [data-auth="out"]').click(); pg.wait_for_timeout(300)

    # 4. X is now admin: scores locally, then joins room MAIN
    pg.evaluate(f"localStorage.setItem('mock-login-as','{X}')")
    pg.locator('#v-control [data-auth="in"]').click(); pg.wait_for_timeout(500)
    check('4 X is admin', '管理員' in auth_txt() and '不是' not in auth_txt(), auth_txt())
    check('4 inputs enabled', not pg.locator('#name-red').is_disabled())
    key('g'); key('q'); key('q'); key('j')
    check('4 local scoring works', phase() == 'running' and score() == {'red': 2, 'blue': 0}, f'{phase()} {score()}')
    check('4 cloud box hidden by default', not pg.locator('#v-control .js-cloud').is_visible())
    check('4 toggle button shown', pg.locator('#v-control [data-cloud-tg]').is_visible())
    pg.locator('#v-control [data-cloud-tg]').click(); pg.wait_for_timeout(200)
    check('4 toggle opens cloud box', pg.locator('#v-control .js-cloud').is_visible())
    pg.locator('#v-control [data-cloud="on"]').click(); pg.wait_for_timeout(700)
    key('u')
    pg.wait_for_timeout(400)
    db = pg.evaluate("JSON.parse(localStorage.getItem('mock-db'))")
    st = db.get('rooms', {}).get('MAIN', {}).get('state', {})
    check('4 room MAIN created and updated', st.get('match', {}).get('score') == {'red': 2, 'blue': 1}, json.dumps(st.get('match', {}).get('score')))
    tg = pg.locator('#v-control [data-cloud-tg]').inner_text()
    check('4 toggle shows room name', 'MAIN' in tg, tg)
    pg.locator('#v-control [data-cloud-tg]').click(); pg.wait_for_timeout(200)
    check('4 toggle closes cloud box', not pg.locator('#v-control .js-cloud').is_visible())
    pg.screenshot(path=f'{OUT}/4b_collapsed.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 260})
    pg.reload(); pg.wait_for_timeout(700)
    check('4 closed state remembered after reload', not pg.locator('#v-control .js-cloud').is_visible())
    pg.locator('#v-control [data-cloud-tg]').click(); pg.wait_for_timeout(200)
    check('4 cloud chip says can operate', '可操作' in pg.locator('#v-control .js-cloud').inner_text())
    check('4 anonymous sign-in never used', 'ANON' not in pg.evaluate('__mockLog'))
    pg.screenshot(path=f'{OUT}/4_admin_room.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 300})

    # 5. score screen in another tab, no login needed
    sc = ctx.new_page(); sc.goto(BASE + '?room=MAIN#score-screen'); sc.wait_for_timeout(700)
    check('5 score screen has no login bar visible', not sc.locator('#v-control').is_visible() and not sc.locator('#v-overview').is_visible())
    sc_score = sc.evaluate("JSON.parse(localStorage.getItem('fida-ds-score-v3')).match.score")
    check('5 score screen shows room score', sc_score == {'red': 2, 'blue': 1}, str(sc_score))
    sc.close()

    # 6. super removes X on another device -> X loses rights live
    pg.evaluate("(()=>{const d=JSON.parse(localStorage.getItem('mock-db'));delete d.admins['judge,x@gmail,com'];localStorage.setItem('mock-db',JSON.stringify(d));__mockNotify();})()")
    pg.wait_for_timeout(300)
    check('6 X shown not admin after removal', '不是管理員' in auth_txt(), auth_txt())
    key('q')
    check('6 X blocked after removal', '不是管理員' in T(), T())
    # restore for offline test
    pg.evaluate("(()=>{const d=JSON.parse(localStorage.getItem('mock-db'));d.admins['judge,x@gmail,com']=true;localStorage.setItem('mock-db',JSON.stringify(d));__mockNotify();})()")
    pg.wait_for_timeout(300)
    check('6 X admin again', '不是' not in auth_txt(), auth_txt())

    # 7. reload with no network (Firebase library cannot load): cached admin keeps working
    state['cdn'] = 'down'
    pg.reload(); pg.wait_for_timeout(800)
    check('7 offline: cached admin shown', '離線沿用' in auth_txt(), auth_txt())
    key('q')
    m = pg.evaluate("JSON.parse(localStorage.getItem('fida-ds-score-v3')).match.score")
    pend = pg.evaluate("JSON.parse(localStorage.getItem('fida-pending-v1')||'null')")
    check('7 offline scoring works and is queued', m['red'] == 3 and pend and len(pend['actions']) == 1, f'{m} {pend}')
    pg.screenshot(path=f'{OUT}/7_offline.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 300})
    # network back: queue uploads
    state['cdn'] = 'mock'
    pg.evaluate("window.dispatchEvent(new Event('online'))"); pg.wait_for_timeout(2500)
    db = pg.evaluate("JSON.parse(localStorage.getItem('mock-db'))")
    check('7 queued action uploaded after reconnect', db['rooms']['MAIN']['state']['match']['score']['red'] == 3, json.dumps(db['rooms']['MAIN']['state']['match']['score']))

    # 8. after sign-out the cache is cleared
    pg.locator('#v-control [data-auth="out"]').click(); pg.wait_for_timeout(400)
    check('8 cache cleared on sign-out', pg.evaluate("localStorage.getItem('fida-admin-v1')") is None)
    key('q')
    check('8 blocked after sign-out', '請先' in T(), T())

    # 9. overview page also shows the bar and blocks remote buttons
    pg.goto(BASE + '#overview'); pg.wait_for_timeout(500)
    check('9 overview login bar', '用 Google 登入' in pg.locator('#v-overview .js-auth').inner_text())
    pg.locator('#v-overview [data-hw="end"]').click(); pg.wait_for_timeout(200)
    check('9 overview remote blocked', '請先' in T(), T())
    pg.set_viewport_size({'width': 390, 'height': 800}); pg.wait_for_timeout(200)
    pg.screenshot(path=f'{OUT}/9_mobile.png', clip={'x': 0, 'y': 0, 'width': 390, 'height': 420})
    check('9 no horizontal scroll on phone', pg.evaluate('document.documentElement.scrollWidth<=innerWidth+1'))

    # 10. built-in admins work right after login, without being added to the list
    pg.goto(BASE + '#control'); pg.wait_for_timeout(500)
    for em in ['Tomy@fzt.cc', 'greenmail1011@gmail.com']:
        pg.evaluate(f"localStorage.setItem('mock-login-as','{em}')")
        pg.locator('#v-control [data-auth="in"]').click(); pg.wait_for_timeout(500)
        check(f'10 {em} is admin', '管理員' in auth_txt() and '不是' not in auth_txt(), auth_txt())
        check(f'10 {em} rules allow writing', pg.evaluate("firebase.database().ref('rooms/MAIN/state/cfg/duration').set(180).then(()=>'ok',e=>e.code)") == 'ok')
        pg.locator('#v-control [data-auth="out"]').click(); pg.wait_for_timeout(300)
    pg.evaluate(f"localStorage.setItem('mock-login-as','{SUPER}')")
    pg.locator('#v-control [data-auth="in"]').click(); pg.wait_for_timeout(500)
    check('10 super sees built-in admins', all(e in auth_txt() for e in ['tomycbf@gmail.com', 'tomy@fzt.cc', 'zikai2000@gmail.com', 'greenmail1011@gmail.com']) and '內建管理員' in auth_txt(), auth_txt())
    pg.set_viewport_size({'width': 1280, 'height': 900}); pg.wait_for_timeout(200)
    pg.screenshot(path=f'{OUT}/10_list.png', clip={'x': 0, 'y': 0, 'width': 1280, 'height': 420})

    check('no page errors', not errs, '; '.join(errs))
    b.close()
srv.shutdown()
print('\nALL PASS' if not fails else f'\n{len(fails)} FAILED: {fails}')
sys.exit(1 if fails else 0)
