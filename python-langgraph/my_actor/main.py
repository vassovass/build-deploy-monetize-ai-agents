"""Module defines the main entry point for the Apify Actor.

Feel free to modify this file to suit your specific needs.

To build Apify Actors, use the Apify SDK toolkit, read more at the official documentation:
https://docs.apify.com/sdk/python
"""

from __future__ import annotations

import asyncio
import logging

from apify import Actor
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

from .models import AgentStructuredOutput
from .tools import get_scraped_posts, tool_calculator_sum, tool_scrape_instagram_profile_posts
from .utils import log_state

SYSTEM_PROMPT = (
    'You analyze Instagram engagement. Use tool_scrape_instagram_profile_posts to fetch '
    'posts; scrape each handle at most once. The tool computes total_likes and '
    'total_comments for you - report those numbers, do not recalculate them. Always '
    'return most_popular_posts as an array, chosen only from the scraped posts: a '
    'single-element array when the query asks for the most popular post, an empty array '
    'when it does not.'
)


async def main() -> None:
    """Define a main entry point for the Apify Actor.

    This coroutine is executed using `asyncio.run()`, so it must remain an asynchronous function for proper execution.
    Asynchronous execution is required for communication with Apify platform, and it also enhances performance in
    the field of web scraping significantly.

    Raises:
        ValueError: If the input is missing required attributes.
    """
    async with Actor:
        # Stop quickly (and cheaply) if the user or platform aborts the run
        async def on_aborting() -> None:
            await asyncio.sleep(1)
            await Actor.exit()

        Actor.on('aborting', on_aborting)

        # Charge for Actor start
        await Actor.charge('actor-start')

        # Handle input
        actor_input = await Actor.get_input()

        query = actor_input.get('query')
        if not query:
            msg = 'Missing "query" attribute in input!'
            raise ValueError(msg)

        model_name = actor_input.get('modelName', 'gpt-4o-mini')
        debug = bool(actor_input.get('debug', False))
        if debug:
            Actor.log.setLevel(logging.DEBUG)

        llm = ChatOpenAI(model=model_name)

        # Create the agent graph
        # see https://docs.langchain.com/oss/python/langchain/agents
        tools = [tool_calculator_sum, tool_scrape_instagram_profile_posts]
        graph = create_agent(llm, tools, system_prompt=SYSTEM_PROMPT, response_format=AgentStructuredOutput)

        final_state = await graph.ainvoke({'messages': [('user', query)]})
        if debug:
            log_state(final_state)

        response: AgentStructuredOutput | None = final_state.get('structured_response')
        if not response:
            Actor.log.error('Failed to get a response from the agent!')
            await Actor.fail(status_message='Failed to get a response from the agent!')
            return

        # The validated posts scraped this run are the ground truth the agent's answer
        # is checked against - the LLM cannot invent a top post that was never scraped
        scraped = get_scraped_posts()
        if not scraped:
            Actor.log.error('No posts were scraped, so there is no evidence behind the totals.')
            await Actor.fail(status_message='The Instagram scrape produced no usable posts.')
            return

        claimed = [p for p in response.most_popular_posts if p.url in scraped]
        top = max(claimed, key=lambda p: scraped[p.url]['likes'] + scraped[p.url]['comments'], default=None)
        complete = not response.most_popular_posts or top is not None
        if not complete:
            Actor.log.warning(
                'The agent named a most-popular post that was never scraped, so the result '
                'is partial and the task-completed fee will not be charged.'
            )

        summary = (
            f'The latest posts have {response.total_likes:,} likes and '
            f'{response.total_comments:,} comments in total. '
        )
        if top:
            top_data = scraped[top.url]
            summary += (
                f'The most popular post is {top.url} with '
                f'{top_data["likes"]:,} likes and {top_data["comments"]:,} comments.'
            )
        else:
            summary += 'No most-popular post was identified.'

        # Push results to the key-value store and dataset. The task-completed fee is
        # charged atomically with the push, and only when the deliverable is complete
        await Actor.set_value('response.txt', summary)
        Actor.log.info('Saved the "response.txt" file into the key-value store!')

        await Actor.push_data(
            {
                'status': 'complete' if complete else 'partial',
                'response': summary,
                'structured_response': response.model_dump(),
            },
            charged_event_name='task-completed' if complete else None,
        )
        Actor.log.info('Pushed data into the dataset!')
