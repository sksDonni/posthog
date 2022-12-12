from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional, Union

from django.utils.timezone import now
from statshog.defaults.django import statsd

from posthog.caching.calculate_results import calculate_cache_key, calculate_result_by_insight
from posthog.caching.insight_cache import update_cached_state
from posthog.models import DashboardTile, Insight
from posthog.models.dashboard import Dashboard
from posthog.utils import get_safe_cache


@dataclass(frozen=True)
class InsightResult:
    result: Optional[Any]
    last_refresh: Optional[datetime]
    cache_key: Optional[str]
    is_cached: bool
    timezone: Optional[str]


@dataclass(frozen=True)
class NothingInCacheResult(InsightResult):
    result: Optional[Any] = None
    last_refresh: Optional[datetime] = None
    cache_key: Optional[str] = None
    is_cached: bool = False
    timezone: Optional[str] = None


def fetch_cached_insight_result(target: Union[Insight, DashboardTile]) -> InsightResult:
    """
    Returns cached value for this insight.

    InsightResult.result will be None if value was not found in cache.
    """

    cache_key = calculate_cache_key(target)
    if cache_key is None:
        return NothingInCacheResult(cache_key=None)

    cached_result = get_safe_cache(cache_key)

    if cached_result is None:
        statsd.incr("posthog_cloud_insight_cache_miss")
        return NothingInCacheResult(cache_key=cache_key)
    else:
        statsd.incr("posthog_cloud_insight_cache_hit")
        return InsightResult(
            result=cached_result.get("result"),
            last_refresh=cached_result.get("last_refresh"),
            cache_key=cache_key,
            is_cached=True,
            # :TODO: This is only populated in some code paths writing to cache
            timezone=cached_result.get("timezone"),
        )


def synchronously_update_cache(insight: Insight, dashboard: Optional[Dashboard]) -> InsightResult:
    cache_key, cache_type, result = calculate_result_by_insight(team=insight.team, insight=insight, dashboard=dashboard)
    timestamp = now()
    update_cached_state(
        insight.team_id, cache_key, timestamp, {"result": result, "type": cache_type, "last_refresh": timestamp}
    )

    return InsightResult(
        result=result, last_refresh=timestamp, cache_key=cache_key, is_cached=False, timezone=insight.team.timezone
    )