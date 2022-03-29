"""description:
    Create some json data for some visualization of opinion mining in Mercure de
    France corpus. This will compare cooccurrent words for male and female
    (actual gender, not pseudonyms). The output file is a javascript file.

    This requires an XML-TEI corpus with <s> (sentence) tags as they will be the
    ones explored. Sentences need to have an "annotation" field and be annotated
    with <Entity> (named entity) tags with an "annotation" attribute. They do
    not need any other annotation.
"""

import json
import pathlib
import collections
import re

from lxml import etree

import hashlib
from wikidataintegrator import wdi_core


datatype2url = {
    "commonsMedia": "https://upload.wikimedia.org/wikipedia/commons"
}


def url_from_filename(filename, datatype="commonsMedia"):
    name = filename.replace(" ", "_")
    md5 = hashlib.md5(name.encode("utf-8")).hexdigest()
    datatypeurl = datatype2url[datatype]
    p1 = md5[:1]
    p2 = md5[:2]
    url = f"{datatypeurl}/{p1}/{p2}/{name}"

    return url


def url_from_qid(qid, kb=None):
    """
    Raises
    ------
    KeyError
        - If the QID does not exist / is not present.
        - if there are no image claims for QID.
    """

    if kb is None:
        item = wdi_core.WDItemEngine(wd_item_id=qid).get_wd_json_representation()
    else:
        item = kb[qid]

    snak = item["claims"]["P18"][0]["mainsnak"]
    datatype = snak["datatype"]
    filename = snak["datavalue"]["value"]
    return url_from_filename(filename, datatype=datatype)


def url_from_wikidata(qid):
    """
    Raises
    ------
    KeyError
        - If the QID does not exist.
        - if there are no image claims for QID.
    """

    return url_from_qid(qid, kb=None)


def normalize(name):
    name = name.strip()
    name = name[0].upper() + name[1:]
    name = name.replace('’', "'")
    name = name.replace("' ", "'")
    name = name.replace("D'", "d'")
    name = name.replace("L'", "l'")
    name = name.replace(" De ", " de ")
    name = name.replace(" Di ", " di ")
    return name


def process_annotated_zip(
    ziparchive, knowledge_base, annotation_filter="", author_xpath="",
):
    """
    Parameters
    ----------
    ziparchive : zipfile.ZipFile
    knowledge_base : dict
    annotation_filter : str
    """

    data = {"nodes":[], "links":[]}
    links = collections.Counter()
    ne_set = set()
    sentiment_set = set()
    author_set = set()
    backtotext = collections.defaultdict(list)
    xmlns = "http://www.tei-c.org/ns/1.0"
    images = {}
    tried = set()

    xpath_query = author_xpath or ''
    if xpath_query:
        xpath_query = xpath_query.replace("/", f"/{{{xmlns}}}")
        xpath_query = xpath_query.replace(f"/{{{xmlns}}}/{{{xmlns}}}", f"//{{{xmlns}}}")
        if xpath_query[0].isalpha():
            xpath_query = f"{{{xmlns}}}" + xpath_query

    to_qid = knowledge_base["qids"]

    names = [name for name in ziparchive.namelist() if name.endswith(".xml")]
    for filename in sorted(
        names,
        key=lambda x: [int(i) for i in pathlib.Path(x).stem.split("_")[:-3:-1]]
    ):
        basename = pathlib.Path(filename).name
        tree = etree.fromstring(ziparchive.open(filename).read())
        annotated_sentences = tree.findall(f".//{{{xmlns}}}s[@annotation]")

        if xpath_query:
            author = tree.findall(xpath_query)[0].text
        else:
            author = ''
        if author:
            author_set.add(author)

        for sentence in annotated_sentences:
            sentiments_raw = sorted(a.strip() for a in sentence.attrib["annotation"].split("|"))
            sentiments = sentiments_raw[:]

            content = normalize(etree.tostring(sentence, method="text", encoding="utf-8").decode("utf-8").strip())
            mentions = set([
                (normalize(entity.text), entity.attrib["annotation"])
                for entity in sentence.findall(f".//{{{xmlns}}}Entity")
            ])
            mentions = set(
                (mention, entity) for mention, entity in mentions
                if '|' not in entity and annotation_filter in entity
            )

            if not mentions:
                continue

            annotated_content = content[:]
            for mention, annotation in mentions:
                annotated_content = annotated_content.replace(
                    mention, f'<span id="Entity" title="{annotation}">{mention}</span>'
                )

            for text, annotation in mentions:
                if annotation not in tried:
                    tried.add(annotation)
                    try:
                        images[annotation] = url_from_wikidata(to_qid.get(annotation, "NIL"))
                    except KeyError as ke:
                        pass

                ne_set.add((text, annotation))

                data_pointer = {"source": basename, "text": annotated_content}
                if data_pointer not in backtotext[text]:
                    backtotext[text].append(data_pointer)
                if author and data_pointer not in backtotext[author]:
                    backtotext[author].append(data_pointer)
                for sentiment in sentiments:
                    if author:
                        sentiment += f"_{text}_{author}"
                        links[(author, sentiment)] += 1
                    links[(text, sentiment)] += 1
                    sentiment_set.add(sentiment)
                    if data_pointer not in backtotext[sentiment]:
                        backtotext[sentiment].append(data_pointer)

    backtotext = dict(backtotext)
    author_set = set(link[0] for link in links if link[0] in author_set)  # remove authors that did not emit an opinion on target
    mention_set = set(ne[0] for ne in ne_set)

    sentiments = sorted(sentiment_set)
    for sentiment in sentiments:
        group, name = sentiment.rsplit(".", 1)
        if xpath_query:
            name = name.split("_", 1)[0]
        data["nodes"].append({"id": sentiment, "name": sentiment, "label": name, "group": group, "class": sentiment.split(".", 1)[0]})

    authors = sorted(author_set - mention_set)
    for author in authors:
        data["nodes"].append({"id": author, "name": author, "label": author, "group": author, "class": "entity"})

    for mention, entity in sorted(ne_set, key=lambda x: x[::-1]):
        data["nodes"].append({"id": mention, "name": mention, "label": mention, "group": entity, "class": "entity"})

        for sentiment in sentiments:
            weight = links.get((mention, sentiment), 0)
            if weight:
                data["links"].append({"source": mention, "target": sentiment, "value": weight,})

    for author in sorted(author_set):
        for sentiment in sentiments:
            weight = links.get((author, sentiment), 0)
            if weight:
                data["links"].append({"source": author, "target": sentiment, "value": weight,})

    return {
        "data": data,
        "back_to_text": backtotext,
        "name2image" : images
    }


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("corpus_directory", help="Path to the XML-TEI corpus of Mercure de France")
    parser.add_argument("knowledge_base_file", help="The knowledge base with aliases and Wikidata IDs")
    parser.add_argument("output_file", help="The output .js file with graph data")
    parser.add_argument(
        "-f",
        "--annotation-filter",
        default="",
        help="Filter out entities that do not contain this string (default: no filter)."
    )

    args = parser.parse_args()

    main(**vars(args))
    sys.exit(0)
