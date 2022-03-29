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

import math

import spacy


tagger = spacy.load("fr_core_news_md", exclude=["ner", "parser"])


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


def filter_in(pos, pos_filter):
    if not pos_filter:
        return True
    return pos in pos_filter


def preprocess_sentence(sentence, to_qid):
    """Return the text and mentions that are present in the XML element given in
    argument."""

    mentions = []
    texts = [sentence.text or ""]
    offset = len(texts[0])
    for m in list(sentence):
        if m.tag != "{http://www.tei-c.org/ns/1.0}Entity":
            raise ValueError(f"Non entity tag in annotated XML: {m.tag}")
        text = m.text
        annotation = m.attrib["annotation"]
        qid = to_qid.get(annotation, "NIL")
        if qid != "NIL":
            mentions.append((text, annotation, offset, offset+len(text), qid))
        texts.append(text)
        offset += len(texts[-1])
        texts.append(m.tail or "")
        offset += len(texts[-1])
    return normalize("".join(texts)), mentions


def preprocess_mentions(mentions, qid_to_claims, target_property):
    if not target_property:
        return mentions

    remaining = []
    for text, annotation, start, end, qid in mentions:
        claim_values = qid_to_claims.get(qid, {}).get(target_property, [])
        for value in claim_values:
            remaining.append((value, target_property, start, end, qid))
    return remaining


def make_spans(text, mentions, target_property):
    if not mentions:
        return text[:]

    if target_property:
        squashed = [mentions[0]]
        for mention in mentions[1:]:
            if mention[2] == squashed[-1][2] and mention[3] == squashed[-1][3]:  # same spans: merge annotations
                squashed[-1] = (squashed[-1][0] + " | " + mention[0], squashed[-1][1], squashed[-1][2], squashed[-1][3], squashed[-1][4])
            else:
                squashed.append(mention)
    else:
        squashed = mentions[:]

    prev = len(text)
    parts = []
    for mention, annotation, start, end, qid in squashed[::-1]:
        parts.append(text[end:prev])
        if target_property:
            parts.append(f'<span id="Entity" title="{mention}">{text[start:end]}</span>')
        else:
            parts.append(f'<span id="Entity" title="{annotation}">{text[start:end]}</span>')
        prev = start
    parts.append(text[:prev])
    return "".join(parts[::-1])


def process_zip_cooc(
    ziparchive, knowledge_base, qid_to_claims, pos_filter=set(), target_property=None, max_degree=10
):
    """
    Parameters
    ----------
    ziparchive : zipfile.ZipFile
    knowledge_base : dict
    pos_filter : set[str]
    """

    data = {"nodes":[], "links":[]}
    nodes = set()
    links = collections.Counter()
    cooccurrent_set = set()
    mention_set = set()
    global_quark = {}
    backtotext = collections.defaultdict(list)
    xmlns = "http://www.tei-c.org/ns/1.0"
    images = {}
    tried = set()
    single_count = collections.Counter()

    to_qid = knowledge_base["qids"]

    names = [name for name in ziparchive.namelist() if name.endswith(".xml")]
    for filename in sorted(names):
        basename = pathlib.Path(filename).name
        tree = etree.fromstring(ziparchive.open(filename).read())
        sentences = tree.findall(f".//{{{xmlns}}}s")
        for sentence in sentences:
            content, mentions = preprocess_sentence(sentence, to_qid)
            mentions = preprocess_mentions(mentions, qid_to_claims, target_property)

            if not content:
                continue
            if not mentions:
                continue

            document = tagger(content)

            pos_tokens = [
                pos_token for pos_token in document
                if not any(
                    mention[2] <= pos_token.idx and (pos_token.idx+len(pos_token)) <= mention[3]
                    for mention in mentions
                )
            ]
            pos_tokens = [
                pos_token.text for pos_token in document
                if filter_in(pos_token.tag_, pos_filter)
            ]
            pos_tokens = [pos_token for pos_token in pos_tokens if not pos_token.isdigit()]
            pos_tokens = set(pos_tokens)

            single_count.update(pos_tokens)

            if not pos_tokens:
                continue

            annotated_content = make_spans(content, mentions, target_property)

            for mention, annotation, start, end, qid in mentions:
                single_count[mention] += 1
                if annotation not in tried:
                    tried.add(annotation)
                    try:
                        images[annotation] = url_from_wikidata(to_qid.get(annotation, "NIL"))
                    except KeyError as ke:
                        pass

                data_pointer = {"source": basename, "text": annotated_content}
                if data_pointer not in backtotext[mention]:
                    backtotext[mention].append(data_pointer)
                mention_set.add(mention)
                nodes.add((mention, annotation))
                for cooccurrent in pos_tokens:
                    links[(mention, cooccurrent)] += 1
                    cooccurrent_set.add(cooccurrent)
                    if data_pointer not in backtotext[cooccurrent]:
                        backtotext[cooccurrent].append(data_pointer)

    backtotext = dict(backtotext)

    # removing outliers
    counts = list(single_count.items())
    for item, count in counts:
        if count == 1:
            try:
                del single_count[item]
            except KeyError:
                pass
            try:
                del backtotext[item]
            except KeyError:
                pass
            try:
                cooccurrent_set.remove(item)
            except KeyError:
                pass
            try:
                mention_set.remove(item)
            except KeyError:
                pass
            links = {key: val for key, val in links.items() if item not in key}
            nodes = set((mention, annotation) for mention, annotation in nodes if item != mention)

    # ~ correlation = {}
    # ~ k = len(single_count)
    # ~ for key, val in links.items():
        # ~ mention, cooccurrent = key
        # ~ ki = single_count[mention]
        # ~ kj = single_count[cooccurrent]
        # ~ kij = val
        # ~ coeff = 2 * kij / (ki+kj)  # dice coefficient -- nice because results are "per one"
        # ~ correlation[key] = coeff
    correlation = {}
    k = len(single_count)
    smooth = 1
    for key, val in links.items():
        mention, cooccurrent = key
        ki = single_count[mention]
        kj = single_count[cooccurrent]
        kij = val
        coeff = (2 * kij + smooth) / (ki + kj + smooth)  # smoothed dice coefficient
        if not target_property:
            correlation[key] = coeff
        else:
            links_bar = {key: val for key, val in links.items() if key[0] != mention and key[1] == cooccurrent}
            ki_bar = sum(single_count.get(other, 0) for other in mention_set if other != mention)
            kij_bar = sum(links_bar.values())
            coeff_bar = (2 * kij_bar + smooth) / (ki_bar + kj + smooth)  # smoothed dice coefficient
            correlation[key] = coeff / coeff_bar

    threshold = 0.02  # used given some examples
    scale_factor = 1.0 / (threshold * 2)
    links = {key: val for key,val in links.items() if correlation[key] >= threshold}
    per_mentions = collections.defaultdict(list)
    for mention, cooccurrent in links:
        per_mentions[mention].append((mention, cooccurrent))
    remaining = []
    for key in per_mentions:
        remaining.extend(
            sorted(per_mentions[key], key=lambda x: correlation[x], reverse=True)[: max_degree]
        )
    correlation = {key: correlation[key] for key in remaining}
    cooccurrent_set = set(key[1] for key in correlation)
    mention_set = set(key[0] for key in correlation)

    nodes = set((mention, entity) for mention, entity in nodes if mention in mention_set)
    nodes = sorted(nodes, key=lambda x: x[::-1])
    for cooccurrent in sorted(cooccurrent_set):
        global_quark.setdefault(cooccurrent, len(global_quark))
    for mention, entity in nodes:
        global_quark.setdefault(mention, len(global_quark))

    cooccurrents = sorted(cooccurrent_set)
    for cooccurrent in cooccurrents:
        data["nodes"].append({"id": cooccurrent, "name": cooccurrent, "label": cooccurrent.split("_", 1)[0], "group": "cooccurrences"})

    for mention, entity in sorted(nodes, key=lambda x: x[::-1]):
        data["nodes"].append({"id": mention, "name": mention, "group": entity, "class": "entity"})

        for cooccurrent in cooccurrents:
            weight = correlation.get((mention, cooccurrent), 0) * scale_factor
            if weight:
                data["links"].append({"source": mention, "target": cooccurrent, "value": math.ceil(weight),})

    return {
        "data": data,
        "back_to_text": backtotext,
        "name2image": images,
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
