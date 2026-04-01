import argparse
import json
from pathlib import Path


HIGH_WEIGHT_KEYWORDS = {
    "大学": 6,
    "高校": 6,
    "学生": 6,
    "学校": 5,
    "宿舍": 5,
    "校园": 6,
    "实习": 6,
    "兼职": 7,
    "就业": 5,
    "劳动合同": 5,
    "拖欠工资": 7,
    "培训贷": 8,
    "校园贷": 10,
    "网贷": 6,
    "消费贷": 5,
    "租房": 8,
    "押金": 8,
    "合租": 7,
    "中介": 6,
    "网购": 7,
    "退款": 6,
    "退货": 6,
    "假货": 7,
    "诈骗": 6,
    "电信诈骗": 8,
    "刷单": 8,
    "裸聊": 8,
    "敲诈": 6,
    "盗窃": 4,
    "网络": 4,
    "微信": 4,
    "QQ": 3,
    "著作权": 5,
    "人格权": 5,
    "隐私": 5,
    "名誉": 5,
    "交通事故": 4,
    "打架": 4,
    "故意伤害": 4,
}

NEGATIVE_KEYWORDS = {
    "公司": 2,
    "股东": 3,
    "招投标": 3,
    "税务": 3,
    "金融机构": 3,
    "上市": 3,
    "专利": 2,
    "海关": 2,
}


def to_text(data: dict) -> str:
    charge = data.get("charge")
    article = data.get("article")
    charge_text = " ".join(str(x) for x in charge) if isinstance(charge, list) else ""
    article_text = " ".join(str(x) for x in article) if isinstance(article, list) else ""
    core = [
        str(data.get("qw") or "")[:2000],
        str(data.get("fact") or "")[:1200],
        str(data.get("reason") or "")[:1200],
        str(data.get("result") or "")[:1200],
        charge_text,
        article_text,
    ]
    return "\n".join(core)


def score_text(text: str) -> int:
    s = 0
    for k, w in HIGH_WEIGHT_KEYWORDS.items():
        if k in text:
            s += w
    for k, w in NEGATIVE_KEYWORDS.items():
        if k in text:
            s -= w
    return s


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="candidate json folder path")
    parser.add_argument("--out-selected", required=True, help="output selected file list")
    parser.add_argument("--out-rest", required=True, help="output remaining file list")
    parser.add_argument("--ratio", type=float, default=0.5, help="selected ratio, default 0.5")
    args = parser.parse_args()

    source_root = Path(args.source)
    if not source_root.exists():
        raise SystemExit(f"Source not found: {source_root}")

    files = sorted(source_root.glob("*.json"))
    total = len(files)
    if total == 0:
        raise SystemExit(f"No json files in {source_root}")

    scored: list[tuple[int, Path]] = []
    for idx, p in enumerate(files, start=1):
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        text = to_text(data)
        scored.append((score_text(text), p))
        if idx % 5000 == 0:
            print(f"Scored {idx}/{total}")

    scored.sort(key=lambda x: x[0], reverse=True)
    selected_n = max(1, int(len(scored) * args.ratio))
    selected = [str(x[1].resolve()) for x in scored[:selected_n]]
    rest = [str(x[1].resolve()) for x in scored[selected_n:]]

    out_selected = Path(args.out_selected)
    out_rest = Path(args.out_rest)
    out_selected.parent.mkdir(parents=True, exist_ok=True)
    out_rest.parent.mkdir(parents=True, exist_ok=True)
    out_selected.write_text("\n".join(selected) + "\n", encoding="utf-8")
    out_rest.write_text("\n".join(rest) + "\n", encoding="utf-8")

    threshold_score = scored[selected_n - 1][0] if selected_n <= len(scored) else scored[-1][0]
    print(f"Total files: {len(scored)}")
    print(f"Selected files: {len(selected)}")
    print(f"Remaining files: {len(rest)}")
    print(f"Selection threshold score: {threshold_score}")


if __name__ == "__main__":
    main()
