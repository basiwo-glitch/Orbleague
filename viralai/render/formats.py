"""Die Spielformate der ORB LEAGUE. Jedes Format ist eine deterministische Physik-Simulation.

Gleicher Seed -> gleiches Ergebnis. Der "Director" simuliert viele Seeds ohne Grafik
und wählt den spannendsten aus (knappe Entscheidungen, Führungswechsel, Comebacks) –
das Ergebnis selbst wird nie manipuliert, die Physik entscheidet.
"""
import math
import random

from PIL import ImageDraw

from .. import brand
from . import engine as E

FPS = E.FPS


def _wrap(a):
    return (a + math.pi) % (2 * math.pi) - math.pi


class Body:
    __slots__ = ("name", "x", "y", "vx", "vy", "r", "alive", "hp", "trail", "power", "flash", "out", "cooldown")

    def __init__(self, name, x, y, vx, vy, r):
        self.name, self.x, self.y, self.vx, self.vy, self.r = name, x, y, vx, vy, r
        self.alive, self.hp, self.trail, self.power, self.flash, self.out, self.cooldown = True, 100.0, [], None, 0.0, False, 0.0

    @property
    def color(self):
        return brand.orb_color(self.name)


def collide_pair(a, b):
    dx, dy = b.x - a.x, b.y - a.y
    d2 = dx * dx + dy * dy
    rr = a.r + b.r
    if d2 >= rr * rr or d2 == 0:
        return None
    d = math.sqrt(d2)
    nx, ny = dx / d, dy / d
    ov = (rr - d) / 2
    a.x -= nx * ov; a.y -= ny * ov
    b.x += nx * ov; b.y += ny * ov
    rel = (a.vx - b.vx) * nx + (a.vy - b.vy) * ny
    if rel <= 0:
        return None
    a_att = a.vx * nx + a.vy * ny
    b_att = -(b.vx * nx + b.vy * ny)
    a.vx -= rel * nx; a.vy -= rel * ny
    b.vx += rel * nx; b.vy += rel * ny
    return rel, a_att, b_att


class Match:
    key = "base"
    header = "WHO WINS?"
    max_t = 45.0

    def __init__(self, orbs, seed, mods=None):
        self.orbs_names = list(orbs)
        self.seed = seed
        self.rng = random.Random(seed)
        self.mods = mods or {}
        self.t = 0.0
        self.frame = 0
        self.done = False
        self.winner = None
        self.events = []
        self.particles = []
        self.shake = 0.0
        self.leader = None
        self.setup()

    # Unterklassen
    def setup(self): ...
    def physics(self, dt, ev): ...
    def standings(self): return []
    def draw_world(self, img, ox, oy): ...
    def draw_hud(self, img): ...

    def emit(self, ev, etype, **kw):
        e = {"t": round(self.t, 3), "type": etype}
        e.update(kw)
        ev.append(e)

    def step(self):
        ev = []
        if not self.done:
            sub = getattr(self, "substeps", 4)
            dt = 1 / FPS / sub
            for _ in range(sub):
                self.physics(dt, ev)
                self.t += dt
                if self.done:
                    break
            st = self.standings()
            if st and not self.done:
                lead = st[0][0]
                if self.leader and lead != self.leader and (len(st) < 2 or st[0][1] != st[1][1]):
                    self.emit(ev, "lead_change", orb=lead, prev=self.leader)
                self.leader = lead
            for b in self.bodies:
                if b.alive:
                    b.trail.append((b.x, b.y))
                    if len(b.trail) > 9:
                        b.trail.pop(0)
                b.flash = max(0.0, b.flash - 1 / FPS)
        else:
            self.t += 1 / FPS
            for b in self.bodies:
                if b.out:
                    b.vy += 900 / FPS
                    b.x += b.vx / FPS; b.y += b.vy / FPS
        for p in self.particles:
            p[0] += p[2] / FPS; p[1] += p[3] / FPS; p[3] += 600 / FPS; p[4] -= 1 / FPS
        self.particles = [p for p in self.particles if p[4] > 0]
        self.shake = max(0.0, self.shake - 1 / FPS * 2.5)
        self.frame += 1
        self.events.extend(ev)
        return ev

    def burst(self, x, y, color, n=26, speed=650):
        for _ in range(n):
            a = self.rng.uniform(0, 2 * math.pi)
            s = self.rng.uniform(0.3, 1) * speed
            self.particles.append([x, y, math.cos(a) * s, math.sin(a) * s - 200, self.rng.uniform(0.4, 0.9), color])

    # Zeichnen gemeinsamer Elemente
    def draw_body(self, img, b, ox, oy, mood="normal"):
        for i, (tx, ty) in enumerate(b.trail[:-1]):
            k = (i + 1) / len(b.trail)
            E.paste(img, E.dot_sprite(b.color, max(3, int(b.r * 0.75 * k)), int(90 * k)), tx + ox, ty + oy)
        E.paste(img, E.glow_sprite(b.color, b.r, 0.65 if b.flash > 0 else 0.45), b.x + ox, b.y + oy)
        spr = E.orb_sprite(b.name, b.r, E.look_index(b.vx, b.vy), mood)
        if b.flash > 0:
            spr = E.scaled(spr, 1 + 0.25 * b.flash)
        E.paste(img, spr, b.x + ox, b.y + oy)

    def draw_particles(self, img, ox, oy):
        d = ImageDraw.Draw(img)
        for x, y, _, _, life, col in self.particles:
            s = 3 + 7 * life
            d.ellipse([x + ox - s, y + oy - s, x + ox + s, y + oy + s], fill=tuple(col) + (255,))


# ======================================================================= ESCAPE
class Escape(Match):
    key = "escape"
    header = "WHO ESCAPES FIRST?"
    max_t = 48.0
    substeps = 4

    def setup(self):
        self.cx, self.cy, self.R = 540, 1010, 400
        self.ring_a = self.rng.uniform(-math.pi, math.pi)
        self.omega = self.mods.get("spin", 1.0) * self.rng.choice([-1, 1]) * 1.05
        self.g = self.mods.get("gravity", 1.0) * 1150
        self.gap0 = 0.16 * self.mods.get("gap", 1.0)
        self.open_at = 3.0
        self.opened = False
        r = 34 if len(self.orbs_names) <= 6 else 26
        self.bodies = []
        for i, n in enumerate(self.orbs_names):
            a = 2 * math.pi * i / len(self.orbs_names) + self.rng.uniform(-0.3, 0.3)
            d = self.rng.uniform(60, 190)
            sp = self.rng.uniform(250, 520)
            va = self.rng.uniform(0, 2 * math.pi)
            self.bodies.append(Body(n, self.cx + d * math.cos(a), self.cy + d * math.sin(a), sp * math.cos(va), sp * math.sin(va), r))
        self.bounces = {n: 0 for n in self.orbs_names}

    def gap(self):
        if self.t < self.open_at:
            return 0.0
        return min(self.gap0 + 0.010 * (self.t - self.open_at), self.gap0 * (self.t - self.open_at) / 0.4)

    def physics(self, dt, ev):
        self.ring_a = _wrap(self.ring_a + self.omega * dt)
        gap = self.gap()
        if gap > 0 and not self.opened:
            self.opened = True
            self.emit(ev, "gate_open")
        live = [b for b in self.bodies if b.alive]
        for b in live:
            b.vy += self.g * dt
            b.x += b.vx * dt; b.y += b.vy * dt
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                if collide_pair(live[i], live[j]):
                    self.emit(ev, "clash", a=live[i].name, b=live[j].name)
        for b in live:
            dx, dy = b.x - self.cx, b.y - self.cy
            dist = math.hypot(dx, dy)
            if dist > self.R + b.r + 6:
                b.alive, b.out = False, True
                if not self.winner:
                    self.winner = b.name
                    self.done = True
                    self.emit(ev, "escape", orb=b.name)
                    self.burst(b.x, b.y, b.color, 40, 800)
                    self.shake = 1.0
                continue
            if dist > self.R - b.r:
                ang = math.atan2(dy, dx)
                rel = _wrap(ang - self.ring_a)
                margin = gap / 2 - (b.r / self.R) * 0.85
                if gap > 0 and abs(rel) < margin:
                    continue  # rollt durch die Lücke
                nx, ny = dx / dist, dy / dist
                vn = b.vx * nx + b.vy * ny
                if vn > 0:
                    b.vx -= 2 * vn * nx; b.vy -= 2 * vn * ny
                    sp = math.hypot(b.vx, b.vy)
                    boost = min(1.025, 1500 / max(sp, 1))
                    b.vx *= boost; b.vy *= boost
                    if sp < 520:
                        k = 520 / max(sp, 1)
                        b.vx *= k; b.vy *= k
                    self.bounces[b.name] += 1
                    b.flash = 0.25
                    near = gap > 0 and abs(rel) < gap / 2 + 0.10
                    self.emit(ev, "bounce", orb=b.name, n=self.bounces[b.name], near_miss=near)
                if dist > self.R - b.r:
                    b.x, b.y = self.cx + nx * (self.R - b.r), self.cy + ny * (self.R - b.r)
        if self.t > self.max_t and not self.done:
            self.done = True
            self.winner = max(self.bounces, key=self.bounces.get)
            self.emit(ev, "timeout", orb=self.winner)

    def standings(self):
        return []  # bei Escape gibt es keine "Führung" – nur den ersten Ausbruch

    def draw_world(self, img, ox, oy):
        ring = E.ring_sprite(self.R + 9, 16, round(self.gap(), 2) if self.gap() > 0 else 0.0)
        rot = ring.rotate(-math.degrees(self.ring_a), resample=3)
        E.paste(img, rot, self.cx + ox, self.cy + oy)
        for b in self.bodies:
            if b.alive or b.out:
                self.draw_body(img, b, ox, oy, "win" if b.name == self.winner else "normal")
        self.draw_particles(img, ox, oy)

    def draw_hud(self, img):
        # Bounce-Zähler pro Orb (unten)
        n = len(self.bodies)
        w = 900 / n
        for i, b in enumerate(self.bodies):
            x = 90 + w * i + w / 2
            E.paste(img, E.orb_sprite(b.name, 26, -1, "win" if b.name == self.winner else "normal"), x, 1520)
            E.paste(img, E.text_sprite(str(self.bounces[b.name]), 40, brand.WHITE, brand.FONT_BOLD), x, 1585)


# ======================================================================== CLASH
class Clash(Match):
    key = "clash"
    header = "LAST ORB STANDING"
    max_t = 55.0
    substeps = 4

    def setup(self):
        self.cx, self.cy, self.R = 540, 960, 430
        r = 54 if len(self.orbs_names) <= 4 else 44
        self.bodies = []
        for i, n in enumerate(self.orbs_names):
            a = 2 * math.pi * i / len(self.orbs_names) + self.rng.uniform(-0.2, 0.2)
            va = self.rng.uniform(0, 2 * math.pi)
            b = Body(n, self.cx + 230 * math.cos(a), self.cy + 230 * math.sin(a), 520 * math.cos(va), 520 * math.sin(va), r)
            self.bodies.append(b)
        self.items = []
        self.next_item = 5.0
        self.sudden = self.mods.get("sudden_death_at", 30.0)
        self.dmg_mult = self.mods.get("damage", 1.0)

    def target_speed(self):
        return 520 + 9 * self.t

    def physics(self, dt, ev):
        live = [b for b in self.bodies if b.alive]
        if self.t > self.sudden:
            if not getattr(self, "_sd", False):
                self._sd = True
                self.emit(ev, "sudden_death")
            self.R = max(250, self.R - 9 * dt)
        for b in live:
            b.x += b.vx * dt; b.y += b.vy * dt
            b.cooldown = max(0, b.cooldown - dt)
        for i in range(len(live)):
            for j in range(i + 1, len(live)):
                a, b = live[i], live[j]
                res = collide_pair(a, b)
                if not res:
                    continue
                rel, a_att, b_att = res
                att, dfn = (a, b) if a_att >= b_att else (b, a)
                q = min(1.0, abs(a_att - b_att) / 700)
                dmg = (8 + 13 * q) * self.dmg_mult * (2 if self.t > self.sudden else 1)
                crit = self.rng.random() < 0.10
                if att.power == "spike":
                    dmg *= 2.2
                    att.power = None
                    crit = True
                elif crit:
                    dmg *= 1.8
                dfn.hp -= dmg
                dfn.flash = 0.35
                self.shake = max(self.shake, 0.35 + 0.4 * crit)
                self.burst((a.x + b.x) / 2, (a.y + b.y) / 2, att.color, 10 + 10 * crit, 420)
                self.emit(ev, "hit", att=att.name, dfn=dfn.name, dmg=round(dmg, 1), crit=crit)
                if dfn.hp <= 0 and dfn.alive:
                    dfn.alive = False
                    dfn.hp = 0
                    self.burst(dfn.x, dfn.y, dfn.color, 46, 900)
                    self.shake = 1.0
                    self.emit(ev, "ko", orb=dfn.name, by=att.name, left=sum(1 for x in self.bodies if x.alive))
        ts = self.target_speed()
        for b in live:
            if not b.alive:
                continue
            dx, dy = b.x - self.cx, b.y - self.cy
            dist = math.hypot(dx, dy)
            if dist > self.R - b.r:
                nx, ny = dx / dist, dy / dist
                vn = b.vx * nx + b.vy * ny
                if vn > 0:
                    b.vx -= 2 * vn * nx; b.vy -= 2 * vn * ny
                    ang = self.rng.uniform(-0.12, 0.12)
                    c, s = math.cos(ang), math.sin(ang)
                    b.vx, b.vy = b.vx * c - b.vy * s, b.vx * s + b.vy * c
                    self.emit(ev, "wall", orb=b.name)
                b.x, b.y = self.cx + nx * (self.R - b.r), self.cy + ny * (self.R - b.r)
            sp = math.hypot(b.vx, b.vy) or 1
            k = 1 + (ts / sp - 1) * min(1, dt * 3)
            b.vx *= k; b.vy *= k
        # Power-Ups
        if self.t >= self.next_item and len(self.items) < 2:
            a, d = self.rng.uniform(0, 2 * math.pi), self.rng.uniform(0, self.R * 0.55)
            kind = self.rng.choice(["spike", "spike", "heal"])
            self.items.append([self.cx + d * math.cos(a), self.cy + d * math.sin(a), kind])
            self.next_item = self.t + self.rng.uniform(5.5, 8.0)
            self.emit(ev, "item_spawn", kind=kind)
        for it in list(self.items):
            for b in live:
                if b.alive and math.hypot(b.x - it[0], b.y - it[1]) < b.r + 26:
                    if it[2] == "heal":
                        b.hp = min(100, b.hp + 30)
                    else:
                        b.power = "spike"
                    self.items.remove(it)
                    b.flash = 0.4
                    self.emit(ev, "pickup", orb=b.name, kind=it[2])
                    break
        alive = [b for b in self.bodies if b.alive]
        if len(alive) <= 1:
            self.done = True
            self.winner = alive[0].name if alive else self.bodies[0].name
            self.emit(ev, "win", orb=self.winner)
        elif self.t > self.max_t:
            self.done = True
            self.winner = max(alive, key=lambda b: b.hp).name
            self.emit(ev, "timeout", orb=self.winner)

    def standings(self):
        return sorted(((b.name, round(b.hp, 1)) for b in self.bodies if b.alive), key=lambda kv: -kv[1])

    def draw_world(self, img, ox, oy):
        d = ImageDraw.Draw(img)
        R = self.R
        col = (255, 80, 80, 255) if self.t > self.sudden else (235, 238, 255, 255)
        for k, a in ((14, 40), (8, 90), (4, 255)):
            d.ellipse([self.cx - R - k + ox, self.cy - R - k + oy, self.cx + R + k + ox, self.cy + R + k + oy], outline=col[:3] + (a,), width=k)
        for x, y, kind in self.items:
            colr = (255, 70, 70) if kind == "spike" else (90, 255, 140)
            pulse = 1 + 0.15 * math.sin(self.t * 8)
            E.paste(img, E.glow_sprite(colr, 26, 0.8), x + ox, y + oy)
            E.paste(img, E.text_sprite("+" if kind == "heal" else "!", int(52 * pulse), colr, brand.FONT_BLACK, 4), x + ox, y + oy)
        for b in self.bodies:
            if b.alive:
                self.draw_body(img, b, ox, oy, "win" if b.name == self.winner else "normal")
                if b.power == "spike":
                    for k in range(8):
                        a = k * math.pi / 4 + self.t * 3
                        x0, y0 = b.x + ox + math.cos(a) * b.r, b.y + oy + math.sin(a) * b.r
                        x1, y1 = b.x + ox + math.cos(a) * (b.r + 18), b.y + oy + math.sin(a) * (b.r + 18)
                        d.line([(x0, y0), (x1, y1)], fill=(255, 80, 80, 255), width=6)
        self.draw_particles(img, ox, oy)

    def draw_hud(self, img):
        d = ImageDraw.Draw(img)
        n = len(self.bodies)
        top = 1450
        rowh = min(52, 200 // max(1, n))
        for i, b in enumerate(self.bodies):
            y = top + i * rowh
            E.paste(img, E.orb_sprite(b.name, 18, -1, "ko" if not b.alive else "normal"), 120, y + 16)
            d.rounded_rectangle([160, y + 4, 900, y + 30], 12, fill=(38, 42, 68, 255))
            w = 740 * max(0, b.hp) / 100
            if w > 4:
                d.rounded_rectangle([160, y + 4, 160 + w, y + 30], 12, fill=b.color + (255,))
            E.paste(img, E.text_sprite(str(int(math.ceil(b.hp))), 28, brand.WHITE, brand.FONT_BOLD, 3), 945, y + 16)


# ===================================================================== TERRITORY
class Territory(Match):
    key = "territory"
    header = "BIGGEST TERRITORY WINS"
    substeps = 6

    def setup(self):
        self.max_t = self.mods.get("duration", 36.0)
        self.x0, self.y0, self.cell = 60, 430, 48
        self.cols, self.rows = 20, 22
        n = len(self.orbs_names)
        self.grid = [[0] * self.cols for _ in range(self.rows)]
        for r in range(self.rows):
            for c in range(self.cols):
                if n == 2:
                    self.grid[r][c] = 0 if c < self.cols // 2 else 1
                else:
                    self.grid[r][c] = (0 if c < self.cols // 2 else 1) + (0 if r < self.rows // 2 else 2)
                    self.grid[r][c] %= n
        self.bodies = []
        spd = 760 * self.mods.get("speed", 1.0)
        for i, nm in enumerate(self.orbs_names):
            if n == 2:
                cx = self.x0 + (0.25 + 0.5 * i) * self.cols * self.cell
                cy = self.y0 + 0.5 * self.rows * self.cell
            else:
                cx = self.x0 + (0.25 + 0.5 * (i % 2)) * self.cols * self.cell
                cy = self.y0 + (0.25 + 0.5 * (i // 2)) * self.rows * self.cell
            a = self.rng.uniform(0.3, 1.25) + self.rng.choice([0, math.pi / 2, math.pi, 3 * math.pi / 2])
            self.bodies.append(Body(nm, cx, cy, spd * math.cos(a), spd * math.sin(a), 22))
        self.counts = [0] * n
        self._recount()
        self.last_tick = [0.0] * n
        self.countdown_emitted = set()

    def _recount(self):
        self.counts = [0] * len(self.bodies)
        for row in self.grid:
            for v in row:
                self.counts[v] += 1

    def physics(self, dt, ev):
        W_, H_ = self.cols * self.cell, self.rows * self.cell
        for idx, b in enumerate(self.bodies):
            b.x += b.vx * dt; b.y += b.vy * dt
            for px, py, axis in ((b.x + b.r, b.y, 0), (b.x - b.r, b.y, 0), (b.x, b.y + b.r, 1), (b.x, b.y - b.r, 1)):
                c = int((px - self.x0) // self.cell)
                r = int((py - self.y0) // self.cell)
                if 0 <= c < self.cols and 0 <= r < self.rows and self.grid[r][c] != idx:
                    old = self.grid[r][c]
                    self.grid[r][c] = idx
                    self.counts[idx] += 1
                    self.counts[old] -= 1
                    if axis == 0:
                        b.vx = -b.vx
                    else:
                        b.vy = -b.vy
                    if self.t - self.last_tick[idx] > 0.07:
                        self.last_tick[idx] = self.t
                        self.emit(ev, "paint", orb=b.name, idx=idx)
            if b.x - b.r < self.x0:
                b.x, b.vx = self.x0 + b.r, abs(b.vx)
            if b.x + b.r > self.x0 + W_:
                b.x, b.vx = self.x0 + W_ - b.r, -abs(b.vx)
            if b.y - b.r < self.y0:
                b.y, b.vy = self.y0 + b.r, abs(b.vy)
            if b.y + b.r > self.y0 + H_:
                b.y, b.vy = self.y0 + H_ - b.r, -abs(b.vy)
            # leichte Zufallsdrehung gegen Endlosschleifen
            if self.rng.random() < 0.002:
                a = self.rng.uniform(-0.25, 0.25)
                c_, s_ = math.cos(a), math.sin(a)
                b.vx, b.vy = b.vx * c_ - b.vy * s_, b.vx * s_ + b.vy * c_
        remaining = self.max_t - self.t
        sec = math.ceil(remaining)
        if 0 < sec <= 5 and sec not in self.countdown_emitted:
            self.countdown_emitted.add(sec)
            self.emit(ev, "countdown", n=sec)
        if self.t >= self.max_t:
            self.done = True
            i = max(range(len(self.counts)), key=lambda k: self.counts[k])
            self.winner = self.bodies[i].name
            self.emit(ev, "win", orb=self.winner, share=round(self.counts[i] / (self.cols * self.rows), 3))

    def standings(self):
        return sorted(((b.name, self.counts[i]) for i, b in enumerate(self.bodies)), key=lambda kv: -kv[1])

    def draw_world(self, img, ox, oy):
        d = ImageDraw.Draw(img)
        dark = [tuple(int(v * 0.5) for v in b.color) for b in self.bodies]
        edge = [tuple(int(v * 0.62) for v in b.color) for b in self.bodies]
        cs = self.cell
        for r in range(self.rows):
            for c in range(self.cols):
                v = self.grid[r][c]
                x, y = self.x0 + c * cs + ox, self.y0 + r * cs + oy
                d.rectangle([x, y, x + cs - 1, y + cs - 1], fill=dark[v] + (255,), outline=edge[v] + (255,))
        d.rectangle([self.x0 - 4 + ox, self.y0 - 4 + oy, self.x0 + self.cols * cs + 3 + ox, self.y0 + self.rows * cs + 3 + oy], outline=(240, 240, 255, 255), width=4)
        for b in self.bodies:
            self.draw_body(img, b, ox, oy, "win" if b.name == self.winner else "normal")
        self.draw_particles(img, ox, oy)

    def draw_hud(self, img):
        d = ImageDraw.Draw(img)
        total = self.cols * self.rows
        x = 60
        y = 1525
        for i, b in enumerate(self.bodies):
            w = 960 * self.counts[i] / total
            d.rectangle([x, y, x + w, y + 46], fill=b.color + (255,))
            if w > 90:
                E.paste(img, E.text_sprite(f"{round(100 * self.counts[i] / total)}%", 32, (15, 15, 25), brand.FONT_BLACK, 0), x + w / 2, y + 23)
            x += w
        rem = max(0, self.max_t - self.t)
        if 0 < rem <= 5.0 and not self.done:
            frac = rem - math.floor(rem)
            E.paste(img, E.scaled(E.with_alpha(E.text_sprite(str(math.ceil(rem)), 260, brand.ACCENT), 0.85), 0.8 + 0.4 * frac), 540, 960)
        else:
            E.paste(img, E.text_sprite(f"{rem:4.1f}s", 40, brand.MUTED, brand.FONT_BOLD), 540, 1610)


FORMATS = {c.key: c for c in (Escape, Clash, Territory)}


# ======================================================================= DIRECTOR
def simulate(fmt, orbs, seed, mods=None):
    m = FORMATS[fmt](orbs, seed, mods)
    while not m.done:
        m.step()
    return m


def drama_score(m):
    """Bewertet einen Simulationslauf nach Spannung. Höher = besser."""
    ev = m.events
    dur = m.t
    score = 0.0
    lc = [e for e in ev if e["type"] == "lead_change"]
    score += min(len(lc), 8) * 1.2
    late_lc = [e for e in lc if e["t"] > dur * 0.6]
    score += min(len(late_lc), 3) * 2.0
    if m.key == "escape":
        near = sum(1 for e in ev if e["type"] == "bounce" and e.get("near_miss"))
        score += min(near, 8) * 1.0
        score += 6 if 17 <= dur <= 34 else (-6 if dur < 10 else 0)
        nms = [e for e in ev if e["type"] == "bounce" and e.get("near_miss")]
        score += 0.5 * len({e["orb"] for e in nms})  # mehrere Kandidaten = offener Ausgang
        score += min(4, sum(1 for e in nms if e["t"] > dur - 6))  # Spannung kurz vor dem Ausbruch
        if any(e["type"] == "timeout" for e in ev):
            score -= 8
    elif m.key == "clash":
        kos = [e for e in ev if e["type"] == "ko"]
        crits = sum(1 for e in ev if e["type"] == "hit" and e.get("crit"))
        score += min(crits, 6) * 0.5
        score += 6 if 22 <= dur <= 42 else -4
        final = m.bodies[[b.name for b in m.bodies].index(m.winner)]
        score += 5 if 0 < final.hp < 30 else 0  # knapper Sieg
        if any(e["type"] == "timeout" for e in ev):
            score -= 6
        if kos and kos[0]["t"] < 6:
            score -= 3
        hits = [e for e in ev if e["type"] == "hit"]
        if not hits or hits[0]["t"] > 2.5:  # Action muss sofort beginnen (Retention!)
            score -= 10
    elif m.key == "territory":
        st = m.standings()
        margin = (st[0][1] - st[1][1]) / (m.cols * m.rows)
        if margin == 0:
            return -50.0  # Gleichstand -> Sieger wäre willkürlich, nie verwenden
        score += 8 * max(0, 0.06 - margin) / 0.06
        # Comeback: Führender bei 70 % ist nicht Sieger
        leader70 = None
        for e in lc:
            if e["t"] < dur * 0.7:
                leader70 = e["orb"]
        if leader70 and leader70 != m.winner:
            score += 5
    return round(score, 2)


def direct(fmt, orbs, mods=None, tries=24, base_seed=None):
    """Simuliert viele Seeds und gibt (seed, match, score) des spannendsten Laufs zurück."""
    rng = random.Random(base_seed)
    best = None
    for _ in range(tries):
        s = rng.randrange(1, 10**9)
        m = simulate(fmt, orbs, s, mods)
        sc = drama_score(m)
        if not best or sc > best[2]:
            best = (s, m, sc)
    return best
