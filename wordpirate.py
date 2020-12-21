#!/usr/bin/env python3.8
import dataclasses
from datetime import datetime
import functools
from html import unescape
import json
import operator
from pathlib import Path
import typing

import pytz
import requests


@dataclasses.dataclass
class Post:
    published: datetime
    modified: datetime
    title: str
    slug: str
    content: str
    summary: str
    aliases: typing.List[str]
    categories: typing.List[str]
    tags: typing.List[str]
    author: str = ""

    @property
    def front_matter(self):
        return json.dumps(
            {
                "title": self.title,
                "categories": self.categories,
                "tags": self.tags,
                "aliases": self.aliases,
                "author": self.author,
                "date": self.published.isoformat(),
                "lastmod": self.modified.isoformat(),
                "slug": self.slug,
                "summary": self.summary,
            }
        )

    @property
    def md(self):
        return f"{self.front_matter}\n\n{self.content}"


@dataclasses.dataclass
class Extractor:
    BASE_HEADERS = {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:83.0) Gecko/20100101 Firefox/83.0"
    }

    base_url: str

    def get(
        self, url: str, params: dict = {}, headers: dict = {}, **kwargs
    ) -> requests.Response:
        (full_headers := self.BASE_HEADERS.copy()).update(headers)
        return requests.get(url=url, params=params, headers=full_headers, **kwargs)

    def pageWhileList(
        self,
        url: str,
        base_params: dict = {"per_page": 100, "order": "asc", "orderby": "id"},
    ) -> typing.Iterator:
        """Returns objects from a paged WordPress list
        until WordPress returns an error."""
        page = 1
        while (
            isinstance(items := self.get(url=url, params=dict(page=page)).json(), list)
            and len(items) > 0
        ):
            yield from items
            page += 1

    @functools.cached_property
    def categories(self) -> typing.Dict:
        return {
            x["id"]: x
            for x in self.pageWhileList(f"{self.base_url}/wp-json/wp/v2/categories")
        }

    @functools.cached_property
    def tags(self) -> typing.Dict:
        return {
            x["id"]: x
            for x in self.pageWhileList(f"{self.base_url}/wp-json/wp/v2/tags")
        }

    @functools.cached_property
    def posts(self) -> typing.List:
        return list(self.get_posts())

    def enhance_post(self, data: typing.Dict) -> Post:
        return Post(
            published=pytz.UTC.localize(datetime.fromisoformat(data["date_gmt"])),
            modified=pytz.UTC.localize(datetime.fromisoformat(data["modified_gmt"])),
            title=unescape(data["title"]["rendered"]),
            slug=data["slug"],
            aliases=[],  # [f"/?p={data['id']}"],
            categories=list(
                map(lambda i: self.categories[i]["name"], data["categories"])
            ),
            tags=list(map(lambda i: self.tags[i]["name"], data["tags"])),
            content=unescape(data["content"]["rendered"]),
            summary=unescape(data["excerpt"]["rendered"]),
        )

    def get_posts(self) -> typing.Iterable:
        return map(
            self.enhance_post,
            self.pageWhileList(f"{self.base_url}/wp-json/wp/v2/posts"),
        )


@dataclasses.dataclass
class Constructor:
    base_path: Path

    @functools.cached_property
    def posts_directory(self):
        path = self.base_path / "content" / "posts"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def add_post(self, post: Post):
        path: Path = self.posts_directory / post.slug
        path.mkdir(parents=True, exist_ok=True)
        (path / "index.md").write_text(post.md)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "base_url", help="base url without final slash (e.g. https://ambiguiti.es)"
    )
    parser.add_argument("target_dir", type=Path)
    args = parser.parse_args()
    e = Extractor(base_url=args.base_url)
    c = Constructor(base_path=args.target_dir)
    for post in e.get_posts():
        c.add_post(post)
