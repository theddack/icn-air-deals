"""행사 상태 판정. 화면(site/app.js)도 같은 규칙을 쓴다."""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

ENDED_KEEP_DAYS = 7      # 마감 후 목록에 남기는 기간
UNDATED_KEEP_DAYS = 14   # 날짜 미상 행사를 마지막 기사 이후 남기는 기간


def today_kst():
    return datetime.now(KST).date()


def status(sale_start, sale_end, today):
    """'upcoming' | 'live' | 'ended' | 'undated'"""
    if sale_start and today < sale_start:
        return "upcoming"
    if sale_end and today > sale_end:
        return "ended"
    if sale_start or sale_end:
        return "live"
    return "undated"


def should_keep(deal, today):
    start = _d(deal.get("sale_start"))
    end = _d(deal.get("sale_end"))
    st = status(start, end, today)
    if st == "ended":
        return (today - end).days <= ENDED_KEEP_DAYS
    if st == "undated" or (st == "live" and not end):
        last = _d(deal["last_published"])
        return (today - last).days <= UNDATED_KEEP_DAYS
    return True


def _d(s):
    return date.fromisoformat(s) if s else None
