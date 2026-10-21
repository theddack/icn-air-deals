"""행사 상태 판정. 화면(site/app.js)도 같은 규칙을 쓴다."""

from datetime import date, datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))

ENDED_KEEP_DAYS = 7      # 마감 후 목록에 남기는 기간
# 마감일을 모르는 행사(날짜 미상, 또는 시작일만 앎). 마지막 기사 후 STALE_AFTER_DAYS가 지나면 '진행 여부 미확인'으로
# 접어 두고, UNDATED_KEEP_DAYS까지 남긴다. 2026-10-21 전에는 14일에 지워서 가격이 있던 에어서울 '임박 특가'(10/4)가
# 10/18에 사라지고 정보 없는 기사만 남았다
STALE_AFTER_DAYS = 14
UNDATED_KEEP_DAYS = 30


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


def is_stale(deal, today):
    """마감일을 모르고 마지막 기사가 STALE_AFTER_DAYS보다 오래된 행사. 끝났는지 알 수 없다."""
    if deal.get("sale_end") or (deal.get("sale_start") and today < _d(deal["sale_start"])):
        return False
    return (today - _d(deal["last_published"])).days > STALE_AFTER_DAYS


def display_status(deal, today):
    """status()에 'stale'(진행 여부 미확인)을 더한 화면용 상태. site/app.js statusOf와 같다."""
    if is_stale(deal, today):
        return "stale"
    return status(_d(deal.get("sale_start")), _d(deal.get("sale_end")), today)


def has_facts(deal):
    """다시 볼 가치가 있는 정보(할인율·가격, 탑승 기간, 행사명, 도착지)가 하나라도 있는가."""
    return bool(deal.get("discount") or deal.get("travel_start") or deal.get("travel_end") or deal.get("event_name")
                or deal.get("destination") or deal.get("route_text"))


def should_keep(deal, today):
    start = _d(deal.get("sale_start"))
    end = _d(deal.get("sale_end"))
    st = status(start, end, today)
    if st == "ended":
        return (today - end).days <= ENDED_KEEP_DAYS
    if st == "undated" or (st == "live" and not end):
        last = _d(deal["last_published"])
        # 정보가 하나도 없는 행사는 진행 여부 미확인으로 남겨 봐야 쓸모가 없어 예전처럼 STALE_AFTER_DAYS에 뺀다
        return (today - last).days <= (UNDATED_KEEP_DAYS if has_facts(deal) else STALE_AFTER_DAYS)
    return True


def _d(s):
    return date.fromisoformat(s) if s else None
