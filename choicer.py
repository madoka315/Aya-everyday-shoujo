import random
import time
import re
import json

# 换日偏移：种子按「UTC 时间戳 + 8h」取天数，即北京时间零点换日（原为 UTC 早 8 点换日）
DAY_OFFSET = 8 * 3600

# config 未提供 rare_words 时的兜底检测词（对应既有概率分支：10% 与 1%×3）
DEFAULT_RARE_WORDS = ('异色瞳', '多重人格', '发梢', '一缕头发')


class Choicer:
    def _compile(self, d):
        t = type(d)
        if t is list:
            r = []
            for x in d:
                if type(x) is str and x.startswith('{') and x.endswith('}'):
                    for y in self.map[x[1:-1]]:
                        r.append(y[0])
                else:
                    r.append(x)
            p = 1.0 / len(r)
            return [(self._compile(x), p) for x in r]
        elif t is str:
            return d
        elif t is dict:
            if 'start' in d:
                return [(self._compile(d['d']), d['p'], d['start'])]
            elif 'p' in d:
                return [(self._compile(d['d']), d['p'])]
            else:
                return [(self._compile(x), d[x]) for x in d]
        else:
            return []
    reg = re.compile('{(.*?)}')

    def _runstr(self, s: str, vals: dict={}) -> str:
        for k in vals:
            s = s.replace(f'{{{k}}}', vals[k])
        for k in self.vals:
            s = s.replace(f'{{{k}}}', self.vals[k])

        def repl(match):
            key = match.group(1)
            k = key.split(':')[0]
            if key not in self.m:
                self.m[key] = set()

            while True:
                r = self._run(self.map[k])
                if r not in self.m[key]:
                    self.m[key].add(r)
                    return r

        return Choicer.reg.sub(repl, s)

    def _run(self, d) -> str:
        t = type(d)
        if t is str:
            return self._runstr(d)
        elif t is list:
            if len(d) == 1 and len(d[0]) == 3: # loop expr
                sb = []
                d = d[0]
                x = d[0]
                i = d[2]

                while True:
                    sb.append(self._runstr(x, {
                        "i": str(i)
                    }))
                    i += 1
                    if self.rand.random() >= d[1]:
                        break
                return ''.join(sb)
            else:
                r = self.rand.random()
                for d2, p in d:
                    if p > r:
                        return self._run(d2)
                    else:
                        r -= p
                return ''
        else:
            return ''

    def __init__(self, config):
        self.rand = random.Random()
        self.date = config['date']

        self._raw_common = dict(config['parts'])
        self._raw_rare = {k: list(v) for k, v in (config.get('rare_parts') or {}).items()}
        self._rare_prob = config.get('rare_prob') or {}
        self.festivals = config.get('festivals') or []
        self._cur_festival = None
        self.rare_words = config.get('rare_words') or DEFAULT_RARE_WORDS
        self._rebuild(self._raw_common, self._raw_rare)

        self.result = [self._compile(x) for x in config['result']]

    def _rebuild(self, common_raw, rare_raw):
        # 按 parts 的声明顺序重建（_compile 对 "{name}" 纯引用串做编译期展开，
        # 依赖声明顺序，如 haircolor 引用 color）
        self.map = {}
        for name, raw in common_raw.items():
            common_c = self._compile(raw)
            rare = rare_raw.get(name)
            if rare:
                p = self._rare_prob.get(name, 0.05)
                # 稀有池在前：r < p 落稀有，否则归入普通池（普通池补余 1-p 必命中）
                self.map[name] = [(self._compile(rare), p), (common_c, 1 - p)]
            else:
                self.map[name] = common_c

    def _apply_festival(self, fest):
        common = dict(self._raw_common)
        rare = {k: list(v) for k, v in self._raw_rare.items()}
        if fest:
            for name, adds in (fest.get('parts') or {}).items():
                common[name] = list(common.get(name, [])) + list(adds)
            for name, adds in (fest.get('rare_parts') or {}).items():
                rare[name] = list(rare.get(name, [])) + list(adds)
        self._rebuild(common, rare)

    def _active_festival(self):
        today = time.strftime('%m-%d', time.gmtime(time.time() + DAY_OFFSET))
        for f in self.festivals:
            start, end = f.get('start'), f.get('end')
            if not start or not end:
                continue
            if start <= end:
                if start <= today <= end:
                    return f
            elif today >= start or today <= end:  # 跨年区间
                return f
        return None

    def _setseed(self, qq):
        if self.date:
            day = int((time.time() + DAY_OFFSET) / 3600 / 24)
        else:
            day = 1
        self.rand.seed(qq * day)

    def format_msg(self, qq, name):
        fest = self._active_festival()
        if fest is not self._cur_festival:
            self._apply_festival(fest)
            self._cur_festival = fest
        self.vals = {
            "name": name
        }
        self._setseed(qq)
        self.m = {}
        msg = ''.join([self._run(x) for x in self.result])
        tags = [w for w in self.rare_words if w in msg]
        if tags:
            msg += ' ' + '✨' * len(tags)
        return msg
