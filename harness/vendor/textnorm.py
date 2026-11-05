"""日本語の数字の表記の正規化（機械の検査が使う部分だけ）。

- kanji_numbers_to_arabic: 漢数字 → 算用数字。「数＋単位」だけを変換し、熟語は除外の一覧で守る。
  「十分」は直後が 以内/後/前/間/おき のときだけ 10分。万・億は区切りとして残す（四百八十万円 → 480万円、
  五万五千円 → 5万5000円）。パーセント・パー（口語）は % にする。単位の無い数（「十二から十八」など）は変換しない
- _RESTART_RE・_DASH_RE: 言い直しの印（内容語の欠落の検査で、言い直す前の語を見分けるのに使う）

外の部品は Python の標準ライブラリだけ。
"""

import re

# 「数＋単位」の単位（長いものを先に照合する）
UNITS = sorted(["円", "%", "パーセント", "パー", "件", "名", "人", "時", "分", "秒", "日", "月", "年", "億", "万", "千",
                "個", "本", "台", "回", "倍", "ポイント", "類", "条", "か月", "ヶ月", "週", "割", "社", "店", "部", "点"],
               key=len, reverse=True)

# 変換しない熟語（数字の部分がこの語の一部なら変換しない）
EXCLUDE = [
    "一時", "一次", "一緒", "一般", "一部", "一度", "一番", "一律", "一括", "一斉",
    "一人", "一本化", "一回り", "一点張り", "一点一点", "一点集中", "一日中", "一時的", "一時期", "一人ひとり", "一人前",
    "同一", "統一", "唯一", "単一", "均一", "画一", "随一", "逐一", "万一", "第一人者",
    "一石二鳥", "二人三脚", "三日坊主", "四六時中", "八百屋", "十人十色", "百人一首", "千差万別",
]

_DIG = {"〇": 0, "零": 0, "一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_SMALL = {"十": 10, "百": 100, "千": 1000}
_KNUM = "〇零一二三四五六七八九十百千万億"
_UNIT_RE = "|".join(re.escape(u) for u in UNITS)
# 数（漢数字。小数点「点」を含みうる）＋単位
# 「パー」は口語の％。「三パーティー」などのカタカナ語の一部では単位とみなさない（直後にカタカナが続く場合は除外）
# 直前が算用数字のときは変換しない（「480万円」の「万」を一万と読まない）
_PAT = re.compile(rf"(?<![0-9０-９.,，])([{_KNUM}]+)(?:点([〇零一二三四五六七八九]+))?({_UNIT_RE})(?![ァ-ヴー])")
_JUPPUN = re.compile(r"(?<![〇零一二三四五六七八九十百千万億])十分(?=以内|後|前|間|おき)")


def _below_10000(s: str) -> int | None:
    total, cur = 0, None
    for ch in s:
        if ch in _DIG:
            if cur is not None:  # 「二三」のような並びは数として扱わない
                return None
            cur = _DIG[ch]
        elif ch in _SMALL:
            total += (cur if cur is not None else 1) * _SMALL[ch]
            cur = None
        else:
            return None
    return total + (cur or 0)


def _kanji_to_arabic(s: str) -> str | None:
    """万・億を区切りとして残す形で変換する。変換できなければ None。"""
    out, rest = "", s
    for big in ("億", "万"):
        if big in rest:
            head, rest = rest.split(big, 1)
            v = _below_10000(head) if head else 1
            if v is None:
                return None
            out += f"{v}{big}"
    if rest:
        v = _below_10000(rest)
        if v is None:
            return None
        out += str(v)
    return out


# 除外語のうち、直後が特定の文字なら除外しない（「一時間」「一時間半」は時間の長さなので変換する）
EXCLUDE_UNLESS_FOLLOWED = {"一時": "間"}


def _excluded(text: str, start: int, end: int) -> bool:
    """除外語が数の先頭以前から始まって数と重なる場合だけ除外する
    （「十一時」の中の「一時」のように、数の途中から始まる一致では除外しない）。"""
    for w in EXCLUDE:
        for m in re.finditer(re.escape(w), text):
            nxt = EXCLUDE_UNLESS_FOLLOWED.get(w)
            if nxt and text[m.end():m.end() + len(nxt)] == nxt:
                continue
            if m.start() <= start < m.end() or (m.start() < start and m.end() > start):
                return True
    return False


# 範囲表現: 「三から五営業日」「十から二十件」「二十から三十代」「三ないし五日」「十〜二十件」は、
# 右側に単位が無くても両側の数を変換する（片側だけ変換されて「十から20件」のように混ざるのを防ぐ）。
# 「一から十まで」（慣用句）は変換しない。「一からやり直す」のように右側が数でないものは範囲ではない
_RANGE_NUM = "[〇零一二三四五六七八九十百千]+"
_RANGE_RE = re.compile(rf"(?<![0-9０-９.,，{_KNUM}])({_RANGE_NUM})(から|〜|～|ないし)({_RANGE_NUM})(?![万億])")
_RANGE_EXCLUDE = ("一から十",)


def _convert_ranges(text: str) -> str:
    def sub(m):
        if m.group(0) in _RANGE_EXCLUDE or _excluded(text, m.start(), m.end()):
            return m.group(0)
        a, b = _kanji_to_arabic(m.group(1)), _kanji_to_arabic(m.group(3))
        if a is None or b is None:
            return m.group(0)
        return f"{a}{m.group(2)}{b}"
    return _RANGE_RE.sub(sub, text)


# 版の番号: 「一点零点六」→1.0.6。点が2つ以上の並び、または V の直後なら点が1つでも版の番号とみなす
# （「一点一点」「一点集中」は EXCLUDE と、点の後ろに数字が続く形に限ることで変換しない）
_VD = "〇零一二三四五六七八九"
_VERSION_RE = re.compile(rf"(?<![{_KNUM}点])([{_VD}]{{1,3}})((?:点[{_VD}]{{1,3}}){{2,3}})(?![{_KNUM}点])")
_VERSION_V_RE = re.compile(rf"(?<=[VvＶｖ])([{_VD}]{{1,3}})((?:点[{_VD}]{{1,3}}){{1,3}})(?![{_KNUM}点])")


def _convert_versions(text: str) -> str:
    def sub(m: re.Match) -> str:
        parts = [m.group(1)] + m.group(2).split("点")[1:]
        return ".".join("".join(str(_DIG[c]) for c in p) for p in parts)
    return _VERSION_RE.sub(sub, _VERSION_V_RE.sub(sub, text))


def kanji_numbers_to_arabic(text: str) -> str:
    text = _convert_versions(text)
    text = _convert_ranges(_JUPPUN.sub("10分", text))
    out, last = [], 0
    for m in _PAT.finditer(text):
        num, frac, unit = m.group(1), m.group(2), m.group(3)
        if _excluded(text, m.start(), m.end()):
            continue
        if unit == "点" and text[m.end():m.end() + 1] in "〇零一二三四五六七八九":
            continue  # 「二点五パー」のように単位が不明な小数は変換しない（半端な「2点五」を作らない）
        if num in ("万", "億", "万億"):  # 数字を伴わない「万」「億」だけの一致（「万円」など）は変換しない
            continue
        if m.group(0) == "十分":  # 「十分（じゅうぶん）」。10分の意味の場合は _JUPPUN で変換済み
            continue
        conv = _kanji_to_arabic(num + (unit if unit in ("万", "億") else ""))
        if conv is None:
            continue
        if unit in ("万", "億"):
            body, unit_out = conv, ""
        else:
            body, unit_out = conv, ("%" if unit in ("パーセント", "パー") else unit)
            if unit == "千":  # 「三千」→3000
                v = _below_10000(num + "千")
                if v is None:
                    continue
                body, unit_out = str(v), ""
        if frac:
            body += "." + "".join(str(_DIG[c]) for c in frac)
        out.append(text[last:m.start()] + body + unit_out)
        last = m.end()
    out.append(text[last:])
    # 算用数字＋「千」（「2万8千円」）を千の位まで算用数字にする: 8千→8000、1千万→1000万
    return re.sub(r"(?<![0-9])([1-9])千", lambda m: m.group(1) + "000", "".join(out))


# ---- 言い直しの印 ----
_RESTART_RE = re.compile(r"いや[、，]|[、，]\s*いや|じゃなくて|ではなくて|違う|ちがう|訂正|間違えた|言い直|っていうか|ていうか|(?:^|[、。])あ[、，]|…|‥")
# 音声認識は言いかけ・言い直しを「-」「--」でつなぐことがある（「ニュースリ-ニュースリリース」「当該-- 今持っている」）。
# 日本語の直後のハイフン・ダッシュを印とみなす。「Wi-Fi」のような英字の間のハイフンは対象外
_DASH_RE = re.compile(r"(?<=[぀-ヿ㐀-鿿])[-‐–—]{1,2}")
