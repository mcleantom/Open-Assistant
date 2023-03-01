from __future__ import annotations

import string

import typer

from pydantic import BaseModel
from typing import Literal, List, Dict, Any
from pathlib import Path
import re
import requests
from bs4 import BeautifulSoup
import urllib.request
from lxml import etree as et
from bz2 import BZ2File
from loguru import logger
from typing import Optional, Generator
from datetime import datetime
import wikitextparser as wtp
from enum import Enum


class ConversationTreeNodeMetaData(BaseModel):
    username: str
    timestamp: datetime


class RoleEnum(str, Enum):
    prompter = "prompter"
    assistant = "assistant"


class ConversationTreeNode(BaseModel):
    text: str
    role: RoleEnum
    children: List[ConversationTreeNode]
    metadata: ConversationTreeNodeMetaData


class ConversationTreeMetaData(BaseModel):
    title: str
    topic: str


class ConversationTree(BaseModel):
    root: ConversationTreeNode
    metadata: ConversationTreeMetaData

    def __repr__(self):
        s = ''

        def fn(node: ConversationTreeNode, depth):
            nonlocal s
            s += ':' * depth + " " + node.text
            for child in node.children:
                fn(child, depth + 1)

        fn(self.root, 0)
        return s


def get_comment_username(comment: str) -> str:
    commenter_re = re.compile(r"(\[\[User talk:.*?]])")
    commenters = commenter_re.findall(comment)
    if len(commenters) != 1:
        return ''
    commenter = commenters[0]
    lp = commenter.find("User talk:") + len("User talk:")
    rp = commenter.find("|")
    if rp == -1:
        rp = commenter.rfind("]]")
    commenter = commenter[lp:rp]
    return commenter


def get_comment_timestamp(comment: str) -> datetime | None:
    timestamp = re.search(
        r"\d{2}:\d{2}, (\b\d{1,2}\D{0,3})?\b(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|(Nov|Dec)(?:ember)?)\D?(\d{1,2}\D?)?\D?((19[7-9]\d|20\d{2})|\d{2})",
        comment)
    if timestamp:
        try:
            return datetime.strptime(timestamp.group(), '%H:%M, %d %B %Y')
        except ValueError:
            try:
                return datetime.strptime(timestamp.group(), '%H:%M, %d %b %Y')
            except ValueError:
                pass
    return None


def parse_replies(parent: ConversationTreeNode, reply: wtp.WikiList, depth: int = 1):
    if not reply.string.startswith(":" * depth):
        return

    if parent.role == RoleEnum.prompter:
        role = RoleEnum.assistant
    else:
        role = RoleEnum.prompter

    replies = reply.sublists()

    if len(replies) == 0:
        text = reply.plain_text()
        username = get_comment_username(reply.string)
        timestamp = get_comment_timestamp(reply.string)
    else:
        text = reply.string[:reply.string.find(replies[0].string)]
        username = get_comment_username(text)
        timestamp = get_comment_timestamp(text)
        text = wtp.remove_markup(text)

    text = text.lstrip(": ")

    if username == '' or timestamp == None:
        return

    new_node = ConversationTreeNode(
        text=text.lstrip(": "),
        role=role,
        children=[],
        metadata=ConversationTreeNodeMetaData(
            username=username,
            timestamp=timestamp
        )
    )

    parent.children.append(new_node)

    for sub_reply in replies:
        parse_replies(new_node, sub_reply, depth + 1)


def parse_talk_page(element: lxml.etree._Element, child: lxml.etree._Element, topic: str):
    text = element.getchildren()[-1].getchildren()[7].text
    parsed = wtp.parse(text)
    sections: list[wtp.Section] = parsed.sections
    for section in sections:
        plain_text = section.plain_text()
        plain_text = re.sub(r"==.*==\n", '', plain_text)
        if plain_text == '':
            continue
        if section.title is None or section.title == '':
            continue
        if plain_text[0].lower() not in string.ascii_lowercase:
            continue

        replies = section.get_lists()

        if len(replies) == 0:
            username = get_comment_username(section.string)
            timestamp = get_comment_timestamp(section.string)
        else:
            text = section.string[:section.string.find(replies[0].string)]
            username = get_comment_username(text)
            timestamp = get_comment_timestamp(text)
            plain_text = wtp.remove_markup(text)
        
        if username == '' or timestamp is None:
            logger.debug(f"Could not parse {section.title}")
        
        root_node = ConversationTreeNode(
            text=plain_text,
            role=RoleEnum.prompter,
            children=[],
            metadata=ConversationTreeNodeMetaData(
                username=username,
                timestamp=timestamp,
                topic=topic
            )
        )

        for reply in replies:
            parse_replies(root_node, reply)

        conversation = ConversationTree(
            root=root_node,
            metadata=ConversationTreeMetaData(
                title=section.title.strip("= ")
            )
        )


def parse_page(element: lxml.etree._Element):
    children = element.getchildren()
    for child in children:
        if child.tag == '{http://www.mediawiki.org/xml/export-0.10/}ns':
            if child.text == '1':
                topic = children[0].text
                logger.info(f"Parsing topic {topic}")
                try:
                    parse_talk_page(element, child, topic)
                except Exception as e:
                    logger.warning(f"Could not parse {topic}")
                    # logger.exception(e)


def process_link(link: str, output_dir: Path) -> None:
    logger.info(f"Processing link {link}")
    output_file = output_dir / link[link.rfind("/") + 1:]

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
