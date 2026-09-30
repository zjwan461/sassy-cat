#!/usr/bin/env python3
"""Validate the leg/crank/wheel kinematics of a 2D rider rig.

为什么需要它：
    "生物骑在车上"最容易崩的三处：
      1) 曲柄转到某个角度时，脚到髋的距离超过了腿的总长 —— 腿会被拉成
         一根笔直的棍子（视觉上明显穿帮，或渲染成一个尖刺）。
      2) 反过来的极端：距离小于 |大腿-小腿|，膝盖无法折叠，两根骨头会打结。
      3) 踏板轨迹插进了车轮圆里 —— 脚穿模进轮胎。
    这个脚本按 0..360° 均匀采样曲柄角，把上面三条全部量化。

用法：
    python check_rig_geometry.py --bb 470 381 --hip 400 286 --crank 30 \
        --thigh 78 --shin 74 --rear-hub 382 368 --front-hub 592 368 --wheel-r 62 --ground 430

省略参数时使用上面这套默认值（即 pelican-rider-2d.html 的实测几何）。
退出码 0 = 通过；1 = 有硬性违规。
"""

import argparse
import math
import sys


def parse_args():
    p = argparse.ArgumentParser(description="2D rider rig kinematics validator")
    p.add_argument("--bb", nargs=2, type=float, default=[470.0, 381.0], metavar=("X", "Y"),
                   help="五通/中轴位置")
    p.add_argument("--hip", nargs=2, type=float, default=[400.0, 286.0], metavar=("X", "Y"),
                   help="髋关节（大腿根）位置")
    p.add_argument("--crank", type=float, default=30.0, help="曲柄长度（踏板圆半径）")
    p.add_argument("--thigh", type=float, default=78.0, help="大腿骨长")
    p.add_argument("--shin", type=float, default=74.0, help="小腿骨长")
    p.add_argument("--wheel-r", type=float, default=62.0, help="车轮半径")
    p.add_argument("--rear-hub", nargs=2, type=float, default=[382.0, 368.0], metavar=("X", "Y"))
    p.add_argument("--front-hub", nargs=2, type=float, default=[592.0, 368.0], metavar=("X", "Y"))
    p.add_argument("--ground", type=float, default=430.0, help="轮胎触地线 y")
    p.add_argument("--pedal-half", type=float, default=6.0, help="踏板半高（用于触地判定）")
    p.add_argument("--samples", type=int, default=3600, help="曲柄角采样数（默认 3600 = 0.1° 一步）")
    p.add_argument("--reach-margin", type=float, default=2.0,
                   help="允许腿伸直到总长的比例余量（px）")
    p.add_argument("--knee-limit", type=float, default=172.0,
                   help="膝角超过该度数视为'腿绷直僵硬'，仅警告")
    return p.parse_args()


def main() -> int:
    a = parse_args()

    bb = a.bb
    hip = a.hip
    reach = a.thigh + a.shin
    min_reach = abs(a.thigh - a.shin) + 2.0

    print("─" * 62)
    print("  腿部运动学校验")
    print("─" * 62)
    print(f"  髋           : ({hip[0]:.0f}, {hip[1]:.0f})")
    print(f"  五通         : ({bb[0]:.0f}, {bb[1]:.0f})")
    print(f"  曲柄半径     : {a.crank:.0f}px")
    print(f"  腿总长       : {a.thigh:.0f} + {a.shin:.0f} = {reach:.0f}px")
    print(f"  采样点数     : {a.samples}")
    print("─" * 62)

    over_reach = []      # 腿被拉直 / 够不到
    under_reach = []     # 膝盖折不动
    wheel_hits = []      # 踏板插进车轮
    ground_hits = []     # 脚穿到地面以下
    dmin, dmax, dsum = float("inf"), float("-inf"), 0.0
    knee_max, knee_min = 0.0, 180.0
    wheel_list = [("后轮", a.rear_hub), ("前轮", a.front_hub)]

    for i in range(a.samples):
        ang = 2.0 * math.pi * i / a.samples
        px = bb[0] + a.crank * math.cos(ang)
        py = bb[1] + a.crank * math.sin(ang)

        d = math.hypot(px - hip[0], py - hip[1])
        dmin, dmax, dsum = min(dmin, d), max(dmax, d), dsum + d

        # 余弦定理求膝内角（髋-膝-踏板）
        cos_k = (a.thigh ** 2 + a.shin ** 2 - d ** 2) / (2.0 * a.thigh * a.shin)
        cos_k = max(-1.0, min(1.0, cos_k))
        knee = math.degrees(math.acos(cos_k))
        knee_max, knee_min = max(knee_max, knee), min(knee_min, knee)

        if d > reach - a.reach_margin:
            over_reach.append((math.degrees(ang), d))
        if d < min_reach:
            under_reach.append((math.degrees(ang), d))

        for name, hub in wheel_list:
            if math.hypot(px - hub[0], py - hub[1]) < a.wheel_r - 4.0:
                wheel_hits.append((math.degrees(ang), name))

        if py + a.pedal_half > a.ground + 1.0:
            ground_hits.append((math.degrees(ang), py))

    avg = dsum / a.samples
    print("  踏板→髋 距离 : "
          f"min {dmin:.1f}   avg {avg:.1f}   max {dmax:.1f}   (腿总长 {reach:.0f})")
    print(f"  膝内角范围   : {knee_min:.1f}° ~ {knee_max:.1f}°")
    print("─" * 62)

    hard_fail = 0

    def report(label, items, unit="°"):
        """items 里的元素是 (曲柄角, 数值或标签)。第二项可能是字符串（如车轮名）。"""
        nonlocal hard_fail
        if not items:
            print(f"  ✅ {label}: 0 次")
            return
        # 只挑第二项是数字的来做"最严重"排序，字符串元组兜底放在后面
        numeric = [it for it in items if len(it) > 1 and isinstance(it[1], (int, float))]
        worst = max(numeric, key=lambda t: t[1]) if numeric else items[0]
        detail = f"{worst[1]:.1f}" if isinstance(worst[1], (int, float)) else str(worst[1])
        print(f"  ❌ {label}: {len(items)}/{a.samples} 次  最严重 {worst[0]:.1f}{unit} (值={detail})")
        hard_fail += 1

    # 距离范围检查（比逐点更直白）
    if dmax > reach - a.reach_margin:
        print(f"  ❌ 踏板最远处 {dmax:.1f}px 超过腿长 {reach:.0f}px 的可达范围 "
              f"→ 腿会被拉直/脱臼。请把髋靠近五通、加大腿长，或缩短曲柄。")
        hard_fail += 1
    else:
        print(f"  ✅ 最远处 {dmax:.1f}px ≤ 腿长可达上限 {reach - a.reach_margin:.1f}px")
    if dmin < min_reach:
        print(f"  ❌ 最近处 {dmin:.1f}px 小于 |大腿-小腿| {abs(a.thigh - a.shin):.1f}px "
              f"→ 膝盖无法折叠，骨头会打结。")
        hard_fail += 1
    else:
        print(f"  ✅ 最近处 {dmin:.1f}px ≥ 折叠下限 {abs(a.thigh - a.shin):.1f}px")

    report("踏板越出可达范围", over_reach)
    report("膝盖折叠空间不足", under_reach)
    report("踏板插进车轮圆", wheel_hits)
    report("脚穿到地面以下", ground_hits)

    if knee_max > a.knee_limit:
        print(f"  ⚠️  最大膝角 {knee_max:.1f}° > {a.knee_limit:.0f}° —— 腿在某一段几乎绷直，"
              f"视觉上会显得僵硬。建议把髋抬高或前移一点。")
    else:
        print(f"  ✅ 最大膝角 {knee_max:.1f}° ≤ {a.knee_limit:.0f}°，全程保持自然弯曲")

    print("─" * 62)
    if hard_fail:
        print(f"❌ 校验失败：{hard_fail} 项硬性违规，先改几何再出片。")
        return 1
    print("🎉 几何自洽：腿全程可及、膝盖有弯曲余量、踏板不穿轮不穿地。")
    print("   提示：这只是静态可达性检查。落地前仍要跑 smoke_test.py 看有没有运行时 NaN。")
    return 0


if __name__ == "__main__":
    sys.exit(main())