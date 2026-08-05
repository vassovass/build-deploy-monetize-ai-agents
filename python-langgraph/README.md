## What does Instagram Engagement Analyzer do?

**Instagram Engagement Analyzer** is an AI agent that reads a public
[Instagram](https://www.instagram.com/) profile's most recent posts and tells you, in one run,
**how much engagement the account is getting and which post is winning**. It totals the likes and
comments across the latest posts and surfaces the single most popular one, with its caption and a
direct link.

Under the hood it is a [LangGraph](https://www.langchain.com/langgraph) ReAct agent that calls the
[Instagram Scraper](https://apify.com/apify/instagram-scraper) Actor as a tool, then reasons over
the results. Because it runs on the Apify platform, you get API access, scheduling, integrations,
proxy rotation, and run monitoring out of the box, and you can trigger it from anywhere over HTTP
or from another agent over [MCP](https://docs.apify.com/platform/integrations/mcp).

## Why use Instagram Engagement Analyzer?

- **Competitor and benchmark tracking** - see how an account's recent posts are performing without
  opening the app.
- **Influencer vetting** - check real engagement on a profile before a partnership.
- **Content research** - find the top-performing post and study what worked.
- **Agent-ready** - it is a pay-per-event Actor, so other AI agents can discover, run, and pay for
  it autonomously.

## How to use Instagram Engagement Analyzer

1. Open the Actor and go to the **Input** tab.
2. Write a plain-language **query** naming the profile and what you want, for example
   "total likes and comments for the latest 10 posts on @openai, and the most popular one".
3. Optionally pick the OpenAI **model** and toggle **debug**.
4. Click **Start** and wait for the run to finish.
5. Read the results in the **Output** and **Dataset** tabs, or pull them over the API.

## Input

The Actor takes a small JSON input:

- **query** (required) - a natural-language instruction naming the Instagram handle and the metrics
  you want.
- **modelName** - the OpenAI model to reason with (`gpt-4o-mini` by default).
- **debug** - set to `true` for verbose logs.

```json
{
  "query": "What is the total number of likes and comments for the latest 10 posts on the @openai Instagram account? Show me the most popular one.",
  "modelName": "gpt-4o-mini",
  "debug": false
}
```

## Output

Each run writes one item to the dataset and a human-readable summary to the key-value store
(`response.txt`). You can download the dataset in various formats such as JSON, HTML, CSV, or Excel.

```json
{
  "status": "complete",
  "response": "The latest posts have 65,971 likes and 2,151 comments in total. The most popular post is https://www.instagram.com/p/DalMyY0t0lp/ with 14,252 likes and 263 comments.",
  "structured_response": {
    "total_likes": 65971,
    "total_comments": 2151,
    "most_popular_posts": [
      {
        "url": "https://www.instagram.com/p/DalMyY0t0lp/",
        "likes": 14252,
        "comments": 263,
        "timestamp": "2026-07-09T17:56:34.000Z",
        "caption": "This is the new ChatGPT Work...",
        "alt": "Video by ChatGPT on July 09, 2026."
      }
    ]
  }
}
```

## Data table

| Field | Description |
|---|---|
| status | `complete`, or `partial` when the most popular post could not be identified (a partial run is not charged the completion fee) |
| response | A plain-text summary of the result, the same content saved to `response.txt` |
| structured_response | Object holding the parsed metrics below |
| structured_response.total_likes | Sum of likes across the analyzed posts |
| structured_response.total_comments | Sum of comments across the analyzed posts |
| structured_response.most_popular_posts | The top post(s) by engagement, each with url, likes, comments, timestamp, caption, and alt |

## How much does it cost to analyze an Instagram profile?

This Actor uses Apify's **pay-per-event** pricing: a flat fee when a run starts and a fee when it
completes a task. The agent's OpenAI calls are covered by those fees, so you do not need an OpenAI
account or key of your own. The bundled [Instagram Scraper](https://apify.com/apify/instagram-scraper)
run is billed separately at that Actor's own rate (roughly $0.27 per 100 posts), so a typical
10-post analysis costs the two fees plus a few cents of scraping. A run that cannot verify the
most popular post against the scraped data is marked `partial` and the completion fee is not
charged. The Apify free tier includes monthly usage credits that cover a handful of trial runs.

## Tips and advanced options

- Keep the query specific ("latest 10 posts") to limit scrape volume and cost. One scrape call
  fetches at most 100 posts, and a whole run scrapes at most 200 across all calls.
- Ask for the top post explicitly when you only need the winner.
- Point an MCP client at `https://mcp.apify.com` to let an agent discover and run this Actor as a
  tool with no glue code.

## Project layout and extending

The Actor's code lives in `my_actor/`: `main.py` holds the agent loop, the charging logic, and
the system prompt; `tools.py` holds the tools (add a new one there and register it in the
`tools` list in `main.py`); `models.py` defines the output shape. The two paid events are
declared in `.actor/pay_per_event.json` - after publishing, pick **Pay per event** in Apify
Console (Publication, then the Monetization wizard) and configure exactly those two events,
otherwise the `Actor.charge()` calls are ignored and the Actor earns nothing. In the wizard,
remove the auto-added synthetic `apify-actor-start` event (the code already charges its own
start fee, and keeping both bills every run twice) and do not enable `apify-default-dataset-item`
(it would bill partial runs for the item this Actor pushes without the completion fee).

## FAQ, disclaimers, and support

- **Is scraping Instagram legal?** This Actor reads publicly available profile data. Use it in line
  with Instagram's Terms of Service and applicable law, and do not collect personal or sensitive
  data without a lawful basis.
- **Why did a post get skipped?** Posts missing a url, like count, comment count, or timestamp,
  or whose counts Instagram hides, are excluded, so the totals reflect only evidenced engagement.
- **Something not working?** Report a bug or request a feature on the
  [Issues tab](https://apify.com/premium_stapler/python-langgraph/issues), and if you need a
  tailored version of this Actor, a custom solution can be commissioned the same way.
