"""Module to crawl and scrape novel contents"""

import pathlib
import os
import logging
import logging.config
import urllib.parse
import re
import time
import datetime
import json
import math
import random

import requests
import bs4
import lxml.html
import lxml.etree
import tomli

import yaml

import pydantic
import copy

from unidecode import unidecode

import _config


def read_data(name: str):
    """Read ./data/{name}.json, this contains the previously recorded series and site data.
    If file doesn't exist return empty dict.

    Returns:
       data (dict): json dictionary
    """
    logger = logging.getLogger(__name__)
    path = f"./data/{name}.json"
    logger.debug("Read JSON [%s]", path)
    try:
        with open(path, mode="rt", encoding="utf-8") as f:
            data: dict = json.load(f)
            return data
    except FileNotFoundError:
        logger.warning("JSON doesn't exist yet [%s] return empty", path)
    except OSError:
        logger.warning("Failed to load JSON [%s] return empty", path, exc_info=True)
    return {}


def write_data(name: str, result: dict):
    """Write dict to ./data/{name}.json, this contains the newly recorded series and site data.
    If file or directory doesn't exist, then create.

    Returns:
       data (dict): json dictionary
    """
    logger = logging.getLogger(__name__)
    os.makedirs("data", exist_ok=True)
    path = f"./data/{name}.json"
    logger.debug("Write JSON [%s]: %s", path, result)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=4)


def write_content(pathstr: str, content: str):
    """Write text to file

    Returns:
       content (str): text content
    """
    logger = logging.getLogger(__name__)

    path = pathlib.Path(pathstr)
    # create parent directories
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        logger.error("Can't write content to an already existsting path: %s", path)
        raise FileExistsError(path)

    logger.debug("Write content: %s", pathstr)

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_content(pathstr: str, content: str):
    """Append text to file

    Returns:
       content (str): text content
    """
    logger = logging.getLogger(__name__)

    path = pathlib.Path(pathstr)
    # create parent directories
    path.parent.mkdir(parents=True, exist_ok=True)

    logger.debug("Append content: %s", pathstr)

    with open(path, "a+", encoding="utf-8") as f:
        f.write(content)


def delay(average_ms: int):
    """Randomly sleep with the specified average time.

    Args:
        average_ms (int): the specified average sleep time
    """
    logger = logging.getLogger(__name__)
    deviation_ms = math.floor(average_ms / 2)
    rand_sec = (
        random.randrange(average_ms - deviation_ms, average_ms + deviation_ms) / 1000
    )
    logger.debug("Delay for: %s ms", rand_sec)
    time.sleep(rand_sec)


def main():
    """Main method"""
    logger = logging.getLogger(__name__)
    # reread config every run
    app_cf = _config.read_app_config()
    basedir = app_cf["basedir"]

    request_cf: dict = app_cf["requests"]
    request_headers: dict = request_cf["headers"]
    request_timeout_s: int = request_cf["timeout_s"]
    request_delay_ms: int = request_cf["delay_ms"]

    sources_cf: dict = app_cf["sources"]

    # serie specific setting
    serie_cf: dict = app_cf["serie"]
    serie_id: str = serie_cf["id"]
    serie_starturl: str = serie_cf["starturl"]
    serie_combine_flag: bool = serie_cf["combine_flag"]

    # common source setting
    src_name: str = serie_cf["source"]
    src_cf: dict = sources_cf[src_name]
    src_baseurl: str = src_cf["baseurl"]
    src_xpath_cf: dict = src_cf["xpath"]
    title_xpath: str = src_xpath_cf["title"]
    contents_xpath: str = src_xpath_cf["contents"]
    nexturl_xpath: str = src_xpath_cf["nexturl"]

    if not "://" in src_baseurl.lower():
        logger.error(
            "source [%s] baseurl [%s] is missing url protocol", src_name, src_baseurl
        )
        raise SystemError("source baseurl configuration missing protocol")

    logger.debug("Finished loading configuration")

    url = serie_starturl

    # while loop
    while url is not None:

        # request website
        logger.info("Fetch URL: %s", url)
        response: requests.Response = requests.get(
            url,
            timeout=request_timeout_s,
            headers=request_headers,
            stream=True,
        )
        response.raw.decode_content = True

        # if exception wasn't raised but still an error

        if response.status_code != STATUS_CODE_OK:
            logger.error(
                "Page status: %s %s",
                response.status_code,
                response.reason,
            )
            raise requests.RequestException(
                f"Bad page status code {response.status_code}"
            )

        # Pass the html response to lxml fromstring method
        logger.debug("Parsing HTML document")
        document = lxml.html.parse(response.raw)

        # find title
        title = document.xpath(title_xpath)[0]
        # normalize title as ascii
        ascii_title = unidecode(title)
        # replace all white space with underscore
        # remove all non alphanumeric character
        filename = re.sub("\\s+|\\W", "_", ascii_title)
        filename = re.sub("_+", "_", filename)
        logger.debug("Title: %s", title)
        logger.debug("Filename: %s", filename)

        # Find content
        contents = document.xpath(contents_xpath)
        content_firstline = contents[0].text_content().lower().strip()
        utf8_content = ""
        for paragraph_element in contents:
            paragraph_text = paragraph_element.text_content()
            utf8_content += paragraph_text + os.linesep
        # fix up any stray excaped newlines
        fixed_nl_content: str = utf8_content.replace("\\n", "\n").replace("\\r", "\r")
        # normalize content as ascii
        ascii_content: str = unidecode(fixed_nl_content)
        ascii_content: str = ascii_content.strip()

        # Add chapter title in the beginning if it doesn't already contain it
        if not (
            content_firstline.startswith("chapter")
            or title.lower() in content_firstline
        ):
            ascii_content = "## " + title + os.linesep + ascii_content
        else:
            ascii_content = "## " + ascii_content

        # Write content to file
        write_content(f"{basedir}/{serie_id}/{filename}.txt", ascii_content)
        if serie_combine_flag:
            # add a new line so the chapter title starts in a new line
            ascii_content = ascii_content + os.linesep
            append_content(f"{basedir}/{serie_id}/{serie_id}.txt", ascii_content)

        # Find next url
        relative_nexturl_matches = document.xpath(nexturl_xpath)
        if not relative_nexturl_matches:
            logger.info("Next URL (xpath) is invalid. End of chapters is reached.")
            raise SystemExit("End of chapters reached")

        relative_nexturl = relative_nexturl_matches[0].strip()
        logger.debug("Next URL (xpath): %s", relative_nexturl)

        # Check if next url is valid
        if relative_nexturl.startswith("/") or relative_nexturl.startswith(src_baseurl):
            next_url = urllib.parse.urljoin(src_baseurl, relative_nexturl)
            logger.debug("Next URL (normalized): %s", next_url)
            url = next_url

            delay(request_delay_ms)
        else:
            logger.info("Next URL (xpath) is invalid. End of chapters is reached.")
            url = None
            raise SystemExit("End of chapters reached")


# constants
STATUS_CODE_OK: int = 200

if __name__ == "__main__":

    # setup logging, later put in a class so it doesnt interfere with other modules
    _config.setup_logging()

    # execute main
    main()

# References
# XPATH https://medium.com/@ghulammustafapy/using-xpath-with-python-requests-module-for-web-scraping-e784c406c55
