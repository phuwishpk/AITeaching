"""K-Means เขียนเอง ต่อยอดโค้ดในบทที่ 6 สไลด์ 11

โค้ดในคาบคำนวณ Euclidean distance แล้วจัดนักเรียนเข้ากลุ่มที่ใกล้ที่สุดเพียงรอบเดียว
ที่นี่เพิ่มขั้นปรับ centroid แล้ววนซ้ำจนกลุ่มไม่เปลี่ยน
ใช้ 3 ฟีเจอร์: เวลาคิดเฉลี่ย, สัดส่วนที่ตอบถูก และความยาว Session เฉลี่ย
"""

import math
import random

FEATURES = [
    ("avg_rt", "เวลาคิดเฉลี่ย (วินาที)"),
    ("accuracy", "สัดส่วนที่ตอบถูก"),
    ("session_min", "ความยาว Session เฉลี่ย (นาที)"),
]

CLUSTER_NAMES = {
    "fast": ("Fast Learners", "เรียนเร็วและแม่นยำ"),
    "struggling": ("Struggling Learners", "ใช้เวลานานและยังพลาดบ่อย"),
    "guesser": ("Trial-and-Error Guessers", "ตอบเร็วแต่พลาดบ่อย"),
    "bite": ("Bite-sized Users", "เข้ามาเรียนทีละช่วงสั้น ๆ"),
}


def euclidean(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def standardize(rows: list[list[float]]) -> tuple[list[list[float]], list[float], list[float]]:
    """ปรับสเกลเป็น z-score ไม่ให้ฟีเจอร์ที่ตัวเลขใหญ่ (เวลา) กลบฟีเจอร์ที่ตัวเลขเล็ก (สัดส่วนถูก)"""
    columns = list(zip(*rows))
    means = [sum(c) / len(c) for c in columns]
    stds = [math.sqrt(sum((x - m) ** 2 for x in c) / len(c)) or 1.0 for c, m in zip(columns, means)]
    scaled = [[(x - m) / s for x, m, s in zip(row, means, stds)] for row in rows]
    return scaled, means, stds


def _init_centroids(points: list[list[float]], k: int, rng: random.Random) -> list[list[float]]:
    """k-means++: เลือก centroid แรกแบบสุ่ม ตัวถัดไปเลือกจุดที่อยู่ไกลจาก centroid เดิมมากกว่า"""
    centroids = [list(rng.choice(points))]
    while len(centroids) < k:
        dists = [min(euclidean(p, c) ** 2 for c in centroids) for p in points]
        total = sum(dists)
        if total == 0:
            centroids.append(list(rng.choice(points)))
            continue
        pick, acc = rng.random() * total, 0.0
        for p, d in zip(points, dists):
            acc += d
            if acc >= pick:
                centroids.append(list(p))
                break
    return centroids


def kmeans(points: list[list[float]], k: int, seed: int = 7, max_iter: int = 100) -> dict:
    if not points:
        return {"centroids": [], "labels": [], "iterations": 0, "inertia": 0.0}
    k = min(k, len(points))
    rng = random.Random(seed)
    centroids = _init_centroids(points, k, rng)
    labels: list[int] = [-1] * len(points)
    iterations = 0
    for iterations in range(1, max_iter + 1):
        # ขั้นที่ 1 (เหมือนโค้ดในคาบ): จัดแต่ละจุดเข้ากลุ่มที่ centroid ใกล้ที่สุด
        new_labels = [min(range(k), key=lambda j: euclidean(p, centroids[j])) for p in points]
        if new_labels == labels:
            break
        labels = new_labels
        # ขั้นที่ 2 (เพิ่มจากในคาบ): ย้าย centroid ไปที่ค่าเฉลี่ยของสมาชิกในกลุ่ม
        for j in range(k):
            members = [p for p, label in zip(points, labels) if label == j]
            if members:
                centroids[j] = [sum(col) / len(members) for col in zip(*members)]
    inertia = sum(euclidean(p, centroids[label]) ** 2 for p, label in zip(points, labels))
    return {"centroids": centroids, "labels": labels, "iterations": iterations, "inertia": round(inertia, 4)}


def elbow(points: list[list[float]], max_k: int = 6) -> list[dict]:
    """ค่า inertia ของ k ต่าง ๆ ใช้วิธี Elbow ประกอบการเลือก k = 4"""
    return [{"k": k, "inertia": kmeans(points, k)["inertia"]} for k in range(1, min(max_k, len(points)) + 1)]


def name_clusters(raw_centroids: list[list[float]]) -> tuple[dict[int, str], list[str]]:
    """ตั้งชื่อกลุ่มจากตำแหน่ง centroid ด้วยกฎที่เขียนไว้ชัด (K-Means เองไม่รู้ชื่อกลุ่ม)"""
    remaining = list(range(len(raw_centroids)))
    names: dict[int, str] = {}
    reasons: list[str] = []
    if not remaining:
        return names, reasons
    # กฎ 1: Session สั้นที่สุด → Bite-sized Users
    bite = min(remaining, key=lambda j: raw_centroids[j][2])
    names[bite] = "bite"
    remaining.remove(bite)
    reasons.append("กลุ่มที่ Session เฉลี่ยสั้นที่สุด = Bite-sized Users")
    if remaining:
        # กฎ 2: ตอบถูกมากที่สุด → Fast Learners
        fast = max(remaining, key=lambda j: raw_centroids[j][1])
        names[fast] = "fast"
        remaining.remove(fast)
        reasons.append("กลุ่มที่สัดส่วนตอบถูกสูงที่สุดในที่เหลือ = Fast Learners")
    if remaining:
        # กฎ 3: ในสองกลุ่มที่เหลือ กลุ่มที่ตอบเร็วกว่า → Guessers อีกกลุ่ม → Struggling
        guesser = min(remaining, key=lambda j: raw_centroids[j][0])
        names[guesser] = "guesser"
        remaining.remove(guesser)
        reasons.append("ในกลุ่มที่เหลือ กลุ่มที่เวลาคิดสั้นกว่า = Trial-and-Error Guessers")
    for j in remaining:
        names[j] = "struggling"
    if remaining:
        reasons.append("กลุ่มสุดท้าย = Struggling Learners")
    return names, reasons


def cluster_students(rows: list[dict], k: int = 4) -> dict:
    """rows: [{"code", "avg_rt", "accuracy", "session_min", "simulated"}]"""
    if len(rows) < k:
        return {"points": [], "centroids": [], "elbow": [], "rules": [], "k": k, "iterations": 0}
    raw = [[r[f] for f, _ in FEATURES] for r in rows]
    scaled, means, stds = standardize(raw)
    result = kmeans(scaled, k)
    raw_centroids = [[c * s + m for c, s, m in zip(cent, stds, means)] for cent in result["centroids"]]
    names, reasons = name_clusters(raw_centroids)
    points = []
    for row, label, z in zip(rows, result["labels"], scaled):
        key = names.get(label, "struggling")
        points.append({
            "code": row["code"],
            "simulated": row.get("simulated", False),
            "cluster": key,
            "cluster_name": CLUSTER_NAMES[key][0],
            "avg_rt": round(row["avg_rt"], 2),
            "accuracy": round(row["accuracy"], 3),
            "session_min": round(row["session_min"], 2),
            "distance": round(euclidean(z, result["centroids"][label]), 3),
        })
    centroids = []
    for j, cent in enumerate(raw_centroids):
        key = names.get(j, "struggling")
        centroids.append({
            "cluster": key,
            "cluster_name": CLUSTER_NAMES[key][0],
            "description": CLUSTER_NAMES[key][1],
            "avg_rt": round(cent[0], 2),
            "accuracy": round(cent[1], 3),
            "session_min": round(cent[2], 2),
            "size": sum(1 for p in points if p["cluster"] == key),
        })
    return {
        "k": k,
        "features": [{"key": f, "label": label} for f, label in FEATURES],
        "points": points,
        "centroids": centroids,
        "iterations": result["iterations"],
        "inertia": result["inertia"],
        "elbow": elbow(scaled),
        "rules": reasons,
    }


def nearest_cluster(model: dict, row: dict) -> str | None:
    """จัดนักเรียนคนใหม่เข้ากลุ่มที่ centroid ใกล้ที่สุด (ใช้ค่าเฉลี่ยและส่วนเบี่ยงเบนชุดเดิม)"""
    point = next((p for p in model.get("points", []) if p["code"] == row["code"]), None)
    return point["cluster"] if point else None
