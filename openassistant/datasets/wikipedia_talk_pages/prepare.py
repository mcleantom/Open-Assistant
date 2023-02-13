from __future__ import annotations

import typer

from pydantic import BaseModel
from typing import Literal, List, Dict
from pathlib import Path
import re
import requests
from bs4 import BeautifulSoup


class ConversationTreeNode(BaseModel):
    text: str
    role: Literal['prompter', 'assistant']
    children: List[ConversationTreeNode]
    metadata: Dict[str, Any]


class ConversationTree(BaseModel):
    root: ConversationTreeNode
    metadata: Dict[str, Any]


def main(output_dir: Path = Path("data")):
    """Download and prepare the dataset for use."""
    output_dir.mkdir(exist_ok=True)

    DUMPS_URL = "https://dumps.wikimedia.org/enwiki/latest/"
    pages_meta_current_pattern = re.compile(r"enwiki-latest-pages-meta-current\d+.xml-p\d+p\d+.bz2")

    html = requests.get(DUMPS_URL)
    soup = BeautifulSoup(html.text, "html.parser")
    links = soup.find_all('a', string=pages_meta_current_pattern)
    pass

if __name__ == "__main__":
    typer.run(main)