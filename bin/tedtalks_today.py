#!/usr/bin/env python3

import html
import json
import os
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from html.parser import HTMLParser

import requests

MaxResults = 1
MinDuration = 8 * 60  # seconds
MaxDuration = 15 * 60  # seconds

doDump = False
doTranslate = True

# __________________________________________________


class MyHTMLParser(HTMLParser):
    flag = False
    trscrpt = None
    duration = None
    dodump = False

    def handle_starttag(self, tag, attrs):
        if self.dodump:
            print("Encountered a start tag:", tag)
        if "script" == tag and ("type", "application/ld+json") in attrs:
            self.flag = True

    def handle_endtag(self, tag):
        if self.dodump:
            print("Encountered an end tag :", tag)
        if "script" == tag:
            self.flag = False

    def handle_data(self, data):
        if self.dodump:
            print("Encountered some data  :", data)
        if self.flag:
            info = json.loads(data)
            self.trscrpt = html.unescape(info["transcript"])
            self.duration = html.unescape(info["duration"])

    def do_dump(self, flag):
        self.dodump = flag


# __________________________________________________

def parse_duration(buff):
    result = re.match("(\d+):(\d+):(\d+)", buff)
    h = int(result.group(1))
    m = int(result.group(2))
    s = int(result.group(3))
    return h, m, s

# __________________________________________________


def split_into_sentences(text):
    sentences = list()
    buff = list()
    flflush = False
    flquote = False
    words = text.split()
    nwords = len(words)

    for i, iword in enumerate(words):
        ichar = iword[0]
        fchar = iword[-1]

        if i + 1 == nwords:
            buff.append(iword)
            sentences.append(" ".join(buff))
            flflush = False
            buff = list()
            break

        if '"' == ichar or "“" == ichar:
            flquote = True
        if '"' == fchar or "”" == fchar:
            flquote = False

        if not flquote:
            if words[i + 1][0].isupper() and (
                ("!" == fchar or "?" == fchar)
                or ('."' == iword[-2:] or ".”" == iword[-2:])
                or ("." == fchar and ichar.islower())
            ):
                flflush = True

        buff.append(iword)
        if flflush:
            sentences.append(" ".join(buff))
            flflush = False
            buff = list()

    return sentences


# __________________________________________________


def get_api_info(path):
    url = ""
    param = dict()
    with open(path, "r") as f:
        buff = json.load(f)
        url = buff["scheme"] + "://" + "/".join([buff["FQDN"], buff["path"]])
        param["auth_key"] = buff["auth_key"]
    return url, param


# __________________________________________________


def translate(url, params, text):
    params["text"] = text
    request = requests.post(url, data=params)
    result = request.json()
    return result["translations"][0]["text"]


# __________________________________________________
# TedTalksUrl = "https://www.ted.com/talks/rss"
TedTalksUrl = "http://feeds.feedburner.com/TEDTalks_audio"
DeeplApiConfigPath = os.path.join(os.path.dirname(__file__), "..", "api", "deepl.json")


def main():
    deeplurl, params = get_api_info(DeeplApiConfigPath)
    params["target_lang"] = "JA"

    ns = {"itunes": "http://www.itunes.com/dtds/podcast-1.0.dtd",
          "atom": "http://www.w3.org/2005/Atom",
          "media": "http://search.yahoo.com/mrss/",
          "jwplayer": "http://developer.longtailvideo.com/"}
    for (nskey, nsval) in ns.items():
        ET.register_namespace(nskey, nsval)

    text = requests.get(TedTalksUrl).text
    root = ET.fromstring(text)
    articles = root.findall("channel/item", ns)

    theday = (datetime.utcnow().date() - timedelta(days=1)).isoformat()

    body = f"TED Talks on {theday} UTC.\n\n"

    nc0 = 0
    nc = 0
    nresults = 0
    for i, item in enumerate(articles):
        if nresults == MaxResults:
            break

        if doDump:
            ET.dump(item)
        title = html.unescape(item.find("title", ns).text)
        speaker = item.find("itunes:author", ns).text
        link = item.find("link", ns).text
        date = item.find("pubDate", ns).text
        hours, minutes, seconds = parse_duration(item.find("itunes:duration", ns).text)
        abst = html.unescape(item.find("description", ns).text.strip())

        if None is link or None is hours or None is minutes or None is seconds:
            continue

        duration = 360 * hours + 60 * minutes + seconds

        if duration < MinDuration or MaxDuration < duration:
            continue

        parser = MyHTMLParser()
        parser.do_dump(doDump)
        parser.feed(requests.get(link).text)

        trscrpt = parser.trscrpt
        if 0 == len(parser.trscrpt):
            continue

        sentences = split_into_sentences(trscrpt)

        nc0 += len(trscrpt)
        nresults += 1

        body += 3 * "-" + "\n"
        body += f"## [{title}]({link})\n"
        body += f"- speaker: {speaker}\n"
        body += f"- date: {date}\n"
        body += f"- duration: {hours:02}:{minutes:02}:{seconds:02}\n"
        body += f"- abstact: {abst}\n"
        body += f"- transcript: {trscrpt}\n"
        if doTranslate:
            body += f"- translation:\n"
            for isentence in sentences:
                nc += len(isentence)
                body += "    - " + isentence + "\n"
                body += "        " + translate(deeplurl, params, isentence) + "\n"
        body += "\n\n"

    body += f"transcription character count: {nc0}\n"
    body += f"translated character count: {nc}"

    if 0 == len(articles):
        print(f"No article found on {theday} UTC.")
    else:
        print(body)


# __________________________________________________

main()
