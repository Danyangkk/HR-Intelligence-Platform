FEISHU_L3_IDS = frozenset(
    {
        "l3-2-1-1",
        "l3-2-1-2",
        "l3-2-1-4",
        "l3-2-2-1",
        "l3-2-2-2",
        "l3-2-2-3",
        "l3-2-2-4",
        "l3-2-2-5",
        "l3-2-2-6",
        "l3-2-2-7",
        "l3-2-3-1",
    }
)

DOC_REPORT_L3_IDS = frozenset(
    {
        "l3-2-3-3",
        "l3-5-3-1",
        "l3-5-5-1",
        "l3-5-5-3",
        "l3-5-5-4",
        "l3-5-5-5",
        "l3-6-4-2",
        "l3-6-4-4",
        "l3-6-5-1",
        "l3-6-5-2",
        "l3-7-2-1",
        "l3-7-2-2",
    }
)


def source_of(l3_id: str) -> str:
    if l3_id.startswith("l3-1-"):
        return "rule"
    if l3_id in FEISHU_L3_IDS:
        return "feishu"
    if l3_id in DOC_REPORT_L3_IDS:
        return "report"
    return "import"
