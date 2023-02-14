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
from loguru import logger


class ConversationTreeNode(BaseModel):
    text: str
    role: Literal['prompter', 'assistant']
    children: List[ConversationTreeNode]
    metadata: Dict[str, Any]


class ConversationTree(BaseModel):
    root: ConversationTreeNode
    metadata: Dict[str, Any]


def parse_talk_page(element: lxml.etree._Element, child: lxml.etree._Element):
    text = element.getchildren()[-1].getchildren()[7].text
    topics = re.split("(==.*==)", text)[1:]
    for topic, comments in zip(topics[0::2], topics[1::2]):
        assert(topic.startswith("=="))
        assert(topic.endswith("=="))


def parse_page(element: lxml.etree._Element):
    children = element.getchildren()
    for child in children:
        if child.tag == '{http://www.mediawiki.org/xml/export-0.10/}ns':
            if child.text == '1':
                logger.info(f"Parsing topic {children[0].text}")
                parse_talk_page(element, child)


def process_link(link: str, output_dir: Path) -> None:
    logger.info(f"Processing link {link}")
    output_file = output_dir / link[link.rfind("/")+1:]

    if output_file.exists():
        logger.info("File already downloaded")
    else:
        logger.info("Downloading")
        urllib.request.urlretrieve(link, output_file)

    logger.info("Parsing BZ2 file")
    with BZ2File(output_file) as xml_file:
        parser = et.iterparse(xml_file, events=('end',))
        for events, element in parser:
            if element.tag == '{http://www.mediawiki.org/xml/export-0.10/}page':
                parse_page(element)


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
