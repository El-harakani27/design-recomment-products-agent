"""The recommendation agent.

    python agent.py <image> <category>
    python agent.py ai-room-2.jpg console_table

The orchestrator holds only `analyze_room`. It never touches the catalog itself -
AGENTS.md tells it to write a design brief and delegate, and the catalog tools
live on the subagents that need them.
"""

from __future__ import annotations

import sys
from pathlib import Path

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend
from deepagents.middleware import FilesystemPermission
from langgraph.checkpoint.memory import MemorySaver

import db
from llm import PROVIDER, chat
from subagents import SUBAGENTS
from tools import analyze_room

ROOT = Path(__file__).resolve().parent


def build_agent():
    return create_deep_agent(
        model=chat("orchestrator"),
        tools=[analyze_room],
        subagents=SUBAGENTS,
        memory=["/AGENTS.md"],
        skills=["/skills/"],
        backend=FilesystemBackend(root_dir=str(ROOT), virtual_mode=True),
        checkpointer=MemorySaver(),  # required whenever memory= is set
        name="room-recommender",
        # Keeps the SQL vocabulary out of the orchestrator's own file access -
        # search_products overrides this with its own `permissions: []` below,
        # since a subagent's permissions replace the parent's rather than add to them.
        permissions=[FilesystemPermission(
            mode="deny", operations=["read", "write"], paths=["/skills/search-products"],
        )],
    )


def recommend(image_path: str, category: str, thread_id: str = "cli-3") -> str:
    if category not in db.CATEGORIES:
        raise SystemExit(f"unknown category {category!r}; expected one of {sorted(db.CATEGORIES)}")
    if not Path(image_path).exists():
        raise SystemExit(f"no image at {image_path}")

    agent = build_agent()
    request = (
        f"A shopper uploaded a room photo at `{image_path}` and is shopping for "
        f"{db.CATEGORIES[category]} (category id `{category}`).\n\n"
        f"Follow the pipeline in AGENTS.md: analyse the room, write a design brief, "
        f"delegate to search_products, then to judge_designer. Finish with a short "
        f"ranked recommendation for the shopper."
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": request}]},
        config={"configurable": {"thread_id": thread_id}, "recursion_limit": 60},
    )
    return result["messages"][-1].content


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(__doc__)
        print("categories:", ", ".join(db.CATEGORIES))
        raise SystemExit(1)
    print(f"[provider: {PROVIDER}]\n")
    print(recommend(sys.argv[1], sys.argv[2]))
