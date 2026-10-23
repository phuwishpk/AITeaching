"""Fuzzy Logic เขียนเองตามขั้นตอนในใบงานที่ 5

1. Fuzzification: แปลงค่าตัวเลขเป็นระดับความเป็นสมาชิก (μ ตั้งแต่ 0.0 ถึง 1.0)
2. Rule Evaluation: เงื่อนไข AND ใช้ค่า min ของแต่ละเงื่อนไข แล้วรวมผลของทุกกฎด้วย max
3. Defuzzification: หาจุดศูนย์ถ่วง (Center of Gravity) ของพื้นที่ใต้กราฟผลลัพธ์

มี 3 ระบบ: ตัดสิน Impasse ตอนผิดครั้งที่ 3, เลือกความยากข้อถัดไป และคำนวณ Risk Score
"""

from dataclasses import dataclass, field


def trimf(x: float, a: float, b: float, c: float) -> float:
    """สามเหลี่ยม: เริ่มที่ a สูงสุดที่ b จบที่ c"""
    if x <= a or x >= c:
        return 1.0 if x == b else 0.0
    if x <= b:
        return (x - a) / (b - a) if b != a else 1.0
    return (c - x) / (c - b) if c != b else 1.0


def trapmf(x: float, a: float, b: float, c: float, d: float) -> float:
    """สี่เหลี่ยมคางหมู: ขึ้นจาก a ถึง b เต็มช่วง b ถึง c ลงจาก c ถึง d"""
    if x < a or x > d:
        return 0.0
    if b <= x <= c:
        return 1.0
    if x < b:
        return (x - a) / (b - a) if b != a else 1.0
    return (d - x) / (d - c) if d != c else 1.0


@dataclass
class FuzzySet:
    label: str
    shape: str  # "tri" หรือ "trap"
    points: tuple

    def mu(self, x: float) -> float:
        if self.shape == "tri":
            return trimf(x, *self.points)
        return trapmf(x, *self.points)


@dataclass
class FuzzyVar:
    name: str
    label: str
    low: float
    high: float
    sets: dict[str, FuzzySet]

    def fuzzify(self, x: float) -> dict[str, float]:
        x = max(self.low, min(self.high, x))
        return {key: round(s.mu(x), 4) for key, s in self.sets.items()}


@dataclass
class Rule:
    conditions: list[tuple[str, str]]  # [(ชื่อตัวแปร, ชื่อเซต)] เชื่อมด้วย AND
    result: str


@dataclass
class FuzzySystem:
    name: str
    inputs: list[FuzzyVar]
    output: FuzzyVar
    rules: list[Rule] = field(default_factory=list)

    def rule_text(self, rule: Rule) -> str:
        names = {v.name: v for v in self.inputs}
        parts = [f"{names[var].label} {names[var].sets[s].label}" for var, s in rule.conditions]
        return f"ถ้า {' และ '.join(parts)} แล้ว {self.output.label} {self.output.sets[rule.result].label}"

    def evaluate(self, values: dict[str, float]) -> dict:
        # 1) Fuzzification
        memberships = {v.name: v.fuzzify(values[v.name]) for v in self.inputs}
        # 2) Rule Evaluation (AND = min)
        fired = []
        for rule in self.rules:
            strength = min(memberships[var][s] for var, s in rule.conditions)
            fired.append({"text": self.rule_text(rule), "result": rule.result, "strength": round(strength, 4)})
        # รวมผลแต่ละเซตผลลัพธ์ด้วย max แล้วตัดยอด (clip) กราฟของเซตนั้น
        clip = {key: 0.0 for key in self.output.sets}
        for f in fired:
            clip[f["result"]] = max(clip[f["result"]], f["strength"])
        # 3) Defuzzification ด้วย Center of Gravity บนแกน 0–100
        curve, num, den = [], 0.0, 0.0
        steps = 100
        for i in range(steps + 1):
            y = self.output.low + (self.output.high - self.output.low) * i / steps
            mu = max((min(clip[key], s.mu(y)) for key, s in self.output.sets.items()), default=0.0)
            curve.append([round(y, 2), round(mu, 4)])
            num += y * mu
            den += mu
        crisp = num / den if den > 0 else (self.output.low + self.output.high) / 2
        return {
            "system": self.name,
            "inputs": {v.name: round(values[v.name], 4) for v in self.inputs},
            "memberships": memberships,
            "rules": fired,
            "clip": {k: round(v, 4) for k, v in clip.items()},
            "curve": curve,
            "output": round(crisp, 2),
        }

    def describe(self) -> dict:
        """นิยามของระบบ สำหรับวาดกราฟความเป็นสมาชิกในหน้า Admin"""
        def var_info(v: FuzzyVar) -> dict:
            return {
                "name": v.name, "label": v.label, "low": v.low, "high": v.high,
                "sets": {k: {"label": s.label, "shape": s.shape, "points": list(s.points)} for k, s in v.sets.items()},
            }
        return {
            "name": self.name,
            "inputs": [var_info(v) for v in self.inputs],
            "output": var_info(self.output),
            "rules": [self.rule_text(r) for r in self.rules],
        }


def _level_out(label: str) -> FuzzyVar:
    return FuzzyVar("out", label, 0, 100, {
        "low": FuzzySet("ต่ำ", "trap", (0, 0, 25, 45)),
        "mid": FuzzySet("กลาง", "tri", (30, 50, 70)),
        "high": FuzzySet("สูง", "trap", (55, 75, 100, 100)),
    })


SLOWNESS = FuzzyVar("slowness", "เวลาคิดเทียบเวลาที่คาด", 0, 3, {
    "fast": FuzzySet("เร็ว", "trap", (0, 0, 0.3, 0.6)),
    "normal": FuzzySet("ปกติ", "tri", (0.4, 0.9, 1.4)),
    "slow": FuzzySet("ช้า", "trap", (1.1, 1.6, 3, 3)),
})

# ---------- ระบบที่ 1: เวลาคิดยาวขึ้นต่อเนื่องจนเป็น Impasse หรือไม่ ----------
IMPASSE_SYSTEM = FuzzySystem(
    "impasse",
    inputs=[
        FuzzyVar("trend", "แนวโน้มเวลาคิด", -1, 2, {
            "down": FuzzySet("ลดลง", "trap", (-1, -1, -0.3, 0)),
            "flat": FuzzySet("คงที่", "tri", (-0.3, 0, 0.3)),
            "up": FuzzySet("เพิ่มขึ้น", "trap", (0.1, 0.5, 2, 2)),
        }),
        SLOWNESS,
    ],
    output=_level_out("ระดับ Impasse"),
    rules=[
        Rule([("trend", "up"), ("slowness", "slow")], "high"),
        Rule([("trend", "up"), ("slowness", "normal")], "high"),
        Rule([("trend", "up"), ("slowness", "fast")], "mid"),
        Rule([("trend", "flat"), ("slowness", "slow")], "mid"),
        Rule([("trend", "flat"), ("slowness", "normal")], "low"),
        Rule([("trend", "down")], "low"),
        Rule([("slowness", "fast")], "low"),
    ],
)

# ---------- ระบบที่ 2: ความยากของข้อถัดไป ----------
DIFFICULTY_SYSTEM = FuzzySystem(
    "difficulty",
    inputs=[
        FuzzyVar("mastery", "Mastery", 0, 1, {
            "low": FuzzySet("ต่ำ", "trap", (0, 0, 0.3, 0.5)),
            "mid": FuzzySet("กลาง", "tri", (0.35, 0.6, 0.85)),
            "high": FuzzySet("สูง", "trap", (0.7, 0.85, 1, 1)),
        }),
        SLOWNESS,
    ],
    output=FuzzyVar("out", "ความยากข้อถัดไป", 0, 100, {
        "easy": FuzzySet("ง่าย", "trap", (0, 0, 20, 40)),
        "mid": FuzzySet("กลาง", "tri", (30, 50, 70)),
        "hard": FuzzySet("ยาก", "trap", (60, 80, 100, 100)),
    }),
    rules=[
        Rule([("mastery", "high"), ("slowness", "fast")], "hard"),
        Rule([("mastery", "high"), ("slowness", "normal")], "hard"),
        Rule([("mastery", "high"), ("slowness", "slow")], "mid"),
        Rule([("mastery", "mid"), ("slowness", "fast")], "mid"),
        Rule([("mastery", "mid"), ("slowness", "normal")], "mid"),
        Rule([("mastery", "mid"), ("slowness", "slow")], "easy"),
        Rule([("mastery", "low")], "easy"),
    ],
)

# ---------- ระบบที่ 3: Risk Score (โอกาส Drop-out) แสดงเฉพาะครูและ Admin ----------
RISK_SYSTEM = FuzzySystem(
    "risk",
    inputs=[
        FuzzyVar("error_rate", "อัตราตอบผิด", 0, 1, {
            "low": FuzzySet("ต่ำ", "trap", (0, 0, 0.2, 0.4)),
            "mid": FuzzySet("กลาง", "tri", (0.25, 0.5, 0.75)),
            "high": FuzzySet("สูง", "trap", (0.6, 0.8, 1, 1)),
        }),
        FuzzyVar("disengagement", "สัญญาณถอดใจ", 0, 1, {
            "low": FuzzySet("ต่ำ", "trap", (0, 0, 0.15, 0.35)),
            "mid": FuzzySet("กลาง", "tri", (0.2, 0.45, 0.7)),
            "high": FuzzySet("สูง", "trap", (0.55, 0.75, 1, 1)),
        }),
        SLOWNESS,
    ],
    output=_level_out("Risk Score"),
    rules=[
        Rule([("error_rate", "high"), ("disengagement", "high")], "high"),
        Rule([("error_rate", "high"), ("slowness", "slow")], "high"),
        Rule([("error_rate", "mid"), ("disengagement", "high")], "high"),
        Rule([("error_rate", "high"), ("disengagement", "low")], "mid"),
        Rule([("error_rate", "mid"), ("disengagement", "mid")], "mid"),
        Rule([("error_rate", "low"), ("disengagement", "high")], "mid"),
        Rule([("error_rate", "mid"), ("disengagement", "low")], "low"),
        Rule([("error_rate", "low"), ("disengagement", "low")], "low"),
    ],
)

SYSTEMS = {s.name: s for s in (IMPASSE_SYSTEM, DIFFICULTY_SYSTEM, RISK_SYSTEM)}


def rt_trend(rts: list[float]) -> float:
    """แนวโน้มเวลาคิด: ใช้ค่าที่น้อยที่สุดของการเพิ่มขึ้นแต่ละครั้ง
    ถ้าเวลายาวขึ้นทุกครั้ง ค่าจะเป็นบวก ถ้ามีครั้งไหนเร็วลง ค่าจะเป็นศูนย์หรือติดลบ"""
    if len(rts) < 2:
        return 0.0
    steps = [(b - a) / max(a, 1.0) for a, b in zip(rts, rts[1:])]
    return max(-1.0, min(2.0, min(steps)))


def impasse(rts: list[float], expected_time: float) -> dict:
    slowness = rts[-1] / max(expected_time, 1.0) if rts else 1.0
    return IMPASSE_SYSTEM.evaluate({"trend": rt_trend(rts), "slowness": slowness})


def difficulty(mastery: float | None, slowness: float) -> dict:
    return DIFFICULTY_SYSTEM.evaluate({"mastery": 0.5 if mastery is None else mastery, "slowness": slowness})


def risk(error_rate: float, disengagement: float, slowness: float) -> dict:
    return RISK_SYSTEM.evaluate({"error_rate": error_rate, "disengagement": disengagement, "slowness": slowness})
