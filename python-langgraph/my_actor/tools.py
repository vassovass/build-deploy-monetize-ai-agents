"""Module defines the tools used by the agent.

Feel free to modify or add new tools to suit your specific needs.

To learn how to create a new tool, see:
- https://python.langchain.com/docs/concepts/tools/
- https://python.langchain.com/docs/how_to/#tools
"""

from __future__ import annotations

import re
from typing import Annotated

from apify import Actor
from apify_shared.consts import ActorJobStatus
from langchain_core.tools import tool
from pydantic import Field, ValidationError

from .models import ScrapedPost

# Bounds on the child apify/instagram-scraper runs. The Actor charges two flat
# pay-per-event fees, so scrape volume is the cost dimension that needs a budget:
# MAX_POSTS_LIMIT bounds one tool call (and is advertised in the tool schema the
# LLM sees), MAX_POSTS_PER_RUN bounds the whole run across repeated calls.
MAX_POSTS_LIMIT = 100
MAX_POSTS_PER_RUN = 200

_scrape_budget = MAX_POSTS_PER_RUN
_memo: dict[tuple[str, int], dict] = {}
_posts_cache: dict[str, dict] = {}


def get_scraped_posts() -> dict[str, dict]:
    """Return every validated post scraped in this run, keyed by post URL.

    main.py uses this as the deterministic ground truth when verifying the agent's
    answer and deciding whether the run is complete.
    """
    return _posts_cache


def _parse_handle(handle: str) -> str:
    """Accept a bare handle, an @handle, or a full profile URL; raise on anything else."""
    h = handle.strip()
    url_match = re.match(r'(?:https?://)?(?:www\.)?instagram\.com/([A-Za-z0-9._]+)', h)
    if url_match:
        h = url_match.group(1)
    h = h.lstrip('@').split('/')[0].split('?')[0]
    if not re.fullmatch(r'[A-Za-z0-9._]{1,30}', h):
        msg = f'Not a valid Instagram handle or profile URL: {handle!r}'
        raise ValueError(msg)
    return h


@tool
def tool_calculator_sum(numbers: list[int]) -> int:
    """Tool to calculate the sum of a list of numbers.

    Args:
        numbers (list[int]): List of numbers to sum.

    Returns:
        int: Sum of the numbers.
    """
    return sum(numbers)


@tool
async def tool_scrape_instagram_profile_posts(
    handle: str,
    max_posts: Annotated[int, Field(ge=1, le=MAX_POSTS_LIMIT)] = 10,
) -> dict:
    """Tool to scrape Instagram profile posts and compute their engagement totals.

    Args:
        handle (str): Instagram handle or profile URL (a leading '@' is fine).
        max_posts (int, optional): Number of most recent posts to scrape. Defaults to 10.

    Returns:
        dict: {'handle', 'post_count', 'total_likes', 'total_comments', 'posts'} where
            totals are computed deterministically from the validated posts and 'posts'
            holds one trimmed, JSON-serializable dict per post.

    Raises:
        ValueError: If the handle is not a valid Instagram handle or profile URL.
        RuntimeError: If the scraper run does not succeed or the run's scrape budget is spent.
    """
    global _scrape_budget

    handle = _parse_handle(handle)
    max_posts = max(1, min(max_posts, MAX_POSTS_LIMIT))

    memo_key = (handle, max_posts)
    if memo_key in _memo:
        return _memo[memo_key]

    if _scrape_budget <= 0:
        msg = 'The scrape budget for this run is spent. Answer from the posts already scraped.'
        raise RuntimeError(msg)
    max_posts = min(max_posts, _scrape_budget)

    run = await Actor.call(
        'apify/instagram-scraper',
        run_input={
            'directUrls': [f'https://www.instagram.com/{handle}/'],
            'resultsLimit': max_posts,
            'resultsType': 'posts',
            'searchLimit': 1,
        },
        max_total_charge_usd=1.0,
    )
    if run is None or run.status not in (ActorJobStatus.SUCCEEDED, ActorJobStatus.TIMED_OUT):
        status = run.status if run else 'no run object'
        msg = f'The apify/instagram-scraper run did not succeed (status: {status})'
        raise RuntimeError(msg)
    if run.status == ActorJobStatus.TIMED_OUT:
        Actor.log.warning('The scraper run timed out; using the posts it managed to scrape.')
    _scrape_budget -= max_posts

    dataset_items: list[dict] = (
        await Actor.apify_client.dataset(run.default_dataset_id).list_items(
            clean=True,
            limit=max_posts,
            fields=['url', 'likesCount', 'commentsCount', 'timestamp', 'caption', 'alt'],
        )
    ).items

    posts: list[dict] = []
    for item in dataset_items:
        # ScrapedPost's field constraints decide which posts count - see models.py.
        try:
            post = ScrapedPost.model_validate(item).model_dump(mode='json')
        except ValidationError as exc:
            first_error = exc.errors()[0]
            Actor.log.warning(
                'Skipping post %s: %s (%s)',
                item.get('url', '<no url>'),
                first_error.get('msg', 'invalid'),
                '.'.join(str(part) for part in first_error.get('loc', ())),
            )
            continue
        _posts_cache[post['url']] = post
        posts.append(
            {
                'url': post['url'],
                'likes': post['likes'],
                'comments': post['comments'],
                'timestamp': post['timestamp'],
                'caption': (post.get('caption') or '')[:120] or None,
            }
        )

    result = {
        'handle': handle,
        'post_count': len(posts),
        'total_likes': sum(p['likes'] for p in posts),
        'total_comments': sum(p['comments'] for p in posts),
        'posts': posts,
    }
    _memo[memo_key] = result
    return result
