"""Prozeduraler Sound: Beat, Kollisions-Melodie, SFX. Alles synthetisch -> rechtefrei."""
import math
import wave

import numpy as np

SR = 44100
PENTA = [0, 2, 4, 7, 9]  # Dur-Pentatonik -> jede Notenfolge klingt "richtig"


def midi_hz(m):
    return 440.0 * 2 ** ((m - 69) / 12)


def penta_note(i, base=60):
    octave, step = divmod(i, len(PENTA))
    return midi_hz(base + 12 * octave + PENTA[step])


class Track:
    def __init__(self, duration, seed=0):
        self.n = int(duration * SR) + SR
        self.buf = np.zeros(self.n, np.float32)
        self.rng = np.random.default_rng(seed)

    def _add(self, t, sig):
        i = int(t * SR)
        if i >= self.n or i < 0:
            return
        j = min(self.n, i + len(sig))
        self.buf[i:j] += sig[: j - i]

    @staticmethod
    def _env(n, a=0.004, d=0.25):
        t = np.arange(n) / SR
        env = np.minimum(1, t / a) * np.exp(-t / d)
        return env

    def pluck(self, t, hz, vol=0.25, dur=0.6):
        n = int(dur * SR)
        tt = np.arange(n) / SR
        sig = (np.sin(2 * np.pi * hz * tt) + 0.35 * np.sin(4 * np.pi * hz * tt) + 0.12 * np.sin(6 * np.pi * hz * tt))
        self._add(t, (sig * self._env(n, 0.002, dur / 4) * vol).astype(np.float32))

    def bell(self, t, hz, vol=0.2, dur=1.2):
        n = int(dur * SR)
        tt = np.arange(n) / SR
        sig = np.sin(2 * np.pi * hz * tt + 1.8 * np.sin(2 * np.pi * hz * 3.5 * tt) * np.exp(-tt * 3))
        self._add(t, (sig * self._env(n, 0.002, dur / 3) * vol).astype(np.float32))

    def hit(self, t, vol=0.5, pitch=1.0):
        n = int(0.28 * SR)
        tt = np.arange(n) / SR
        f = 160 * pitch * np.exp(-tt * 18) + 45
        body = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 14)
        noise = self.rng.normal(0, 1, n) * np.exp(-tt * 40) * 0.6
        self._add(t, ((body + noise) * vol).astype(np.float32))

    def tick(self, t, hz=1800, vol=0.12):
        n = int(0.05 * SR)
        tt = np.arange(n) / SR
        self._add(t, (np.sin(2 * np.pi * hz * tt) * np.exp(-tt * 90) * vol).astype(np.float32))

    def whoosh(self, t, vol=0.35, dur=0.7):
        n = int(dur * SR)
        noise = self.rng.normal(0, 1, n)
        # einfacher Tiefpass mit wandernder Grenzfrequenz
        out = np.zeros(n, np.float32)
        y = 0.0
        for k in range(0, n, 64):
            a = 0.02 + 0.25 * math.sin(math.pi * k / n)
            seg = noise[k:k + 64]
            for m, x in enumerate(seg):
                y += a * (x - y)
                out[k + m] = y
        env = np.sin(np.linspace(0, np.pi, n)) ** 2
        self._add(t, (out * env * vol * 2.2).astype(np.float32))

    def boom(self, t, vol=0.7):
        n = int(0.9 * SR)
        tt = np.arange(n) / SR
        f = 90 * np.exp(-tt * 6) + 30
        sig = np.sin(2 * np.pi * np.cumsum(f) / SR) * np.exp(-tt * 4)
        sig += self.rng.normal(0, 1, n) * np.exp(-tt * 10) * 0.5
        self._add(t, (sig * vol).astype(np.float32))

    def fanfare(self, t, base=72, vol=0.22):
        for k, (st, dt) in enumerate([(0, 0.0), (4, 0.12), (7, 0.24), (12, 0.36)]):
            self.bell(t + dt, midi_hz(base + st), vol, 1.6)
        self.bell(t + 0.5, midi_hz(base + 16), vol * 0.9, 2.0)

    def beat(self, start, end, bpm=124, intensity=lambda t: 1.0, root=48):
        """Minimaler Hintergrund-Groove (Kick, HiHat, Bass). Intensität darf steigen."""
        spb = 60 / bpm
        t, k = start, 0
        bass = [0, 0, 7, 5]
        while t < end:
            it = intensity(t)
            self.hit(t, 0.22 * it, 0.7)
            self.tick(t + spb / 2, 7000, 0.035 * it)
            if k % 2 == 0:
                hz = midi_hz(root + bass[(k // 2) % 4])
                n = int(spb * 2 * SR)
                tt = np.arange(n) / SR
                sig = np.tanh(2 * np.sin(2 * np.pi * hz * tt)) * np.exp(-tt * 1.6) * 0.09 * it
                self._add(t, sig.astype(np.float32))
            t += spb
            k += 1

    def write(self, path, length):
        n = int(length * SR)
        b = self.buf[:n]
        b = np.tanh(b * 1.1)  # sanfter Limiter
        peak = float(np.max(np.abs(b))) or 1.0
        b = b / peak * 0.89
        pcm = (b * 32767).astype(np.int16)
        stereo = np.repeat(pcm[:, None], 2, axis=1)
        with wave.open(path, "wb") as w:
            w.setnchannels(2)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(stereo.tobytes())
