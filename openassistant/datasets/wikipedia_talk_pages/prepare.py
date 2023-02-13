from __future__ import annotations

import typer

from pydantic import BaseModel
from typing import Literal, List, Dict
from pathlib import Path
import re
import requests
from bs4 import BeautifulSoup
import tempfile
import urllib.request
from lxml import etree as et
from bz2 import BZ2File


class ConversationTreeNode(BaseModel):
    text: str
    role: Literal['prompter', 'assistant']
    children: List[ConversationTreeNode]
    metadata: Dict[str, Any]


class ConversationTree(BaseModel):
    root: ConversationTreeNode
    metadata: Dict[str, Any]


def process_link(link: str, output_dir: Path) -> None:
    with tempfile.TemporaryDirectory() as tmp_dir:
        output_file = Path(tmp_dir) / "file.bz2"
        urllib.request.urlretrieve(link, output_file)

        with BZ2File(output_file) as xml_file:
            parser = et.iterparse(xml_file, events=('end',))
            for events, element in parser:
                print(et.tostring(element))


def main(output_dir: Path = Path("data")):
    """Download and prepare the dataset for use."""
    output_dir.mkdir(exist_ok=True)

    DUMPS_URL = "https://dumps.wikimedia.org/enwiki/latest/"
    pages_meta_current_pattern = re.compile(r"enwiki-latest-pages-meta-current\d+.xml-p\d+p\d+.bz2$")

    html = requests.get(DUMPS_URL)
    soup = BeautifulSoup(html.text, "html.parser")
    links = soup.find_all('a', href=pages_meta_current_pattern)
    links = [DUMPS_URL + "/" + link['href'] for link in links]

    for link in links:
        process_link(link, output_dir)


if __name__ == "__main__":
    typer.run(main)
