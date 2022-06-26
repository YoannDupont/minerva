"""description:
  Link entities using SpaCy opentapioca, pywikibot and a match file.
"""

import spacy

from tqdm import tqdm
import re
import pathlib
import sys
import json
import spacy
from lxml import etree
import collections

import pywikibot
from pywikibot.data import api
from wikidataintegrator import wdi_core


__wikidata_site = pywikibot.Site("wikidata", "wikidata")


def query_wikidata(name, lang, limit=10):
    """Query Wikidata to fetch information about a term."""

    params = {
        'action': 'wbsearchentities' ,
        'format': 'json',
        'language': lang,
        'type' : 'item',
        'search': name,
        "limit": limit
    }
    request = api.Request(site=__wikidata_site, parameters=params)
    return request.submit()


def from_qid(qid):
    """Return the Wikidata entry given the Wikidata identifier (QID) given in argument."""

    entry = wdi_core.WDItemEngine(wd_item_id=qid).get_wd_json_representation()
    entry["id"] = qid
    return entry


def wikidata_properties(item):
    return set(item["mainsnak"]["datavalue"]["value"]["id"] for item in item["claims"].get("P31", []))


def wikidata_occupations(item):
    return set(item["mainsnak"]["datavalue"]["value"]["id"] for item in item["claims"].get("P31", []))


TARGET_OCCUPATIONS = set([
    "Q36180", # writer
    "Q49757", # poet
    "Q6625963", # novelist
    "Q11774202", # essayist
])


def is_human(item):
    # Q5 = human
    properties = wikidata_properties(item)
    return "Q5" in properties


def replace_same_size(m):
    return " " * (m.end() - m.start())


def normalize(text):
    text = text.strip()
    text = text.replace('’', "'")
    text = text.replace('’', "'")
    text = text.replace("' ", "'")
    text = text.replace("D'", "d'")
    text = text.replace("L'", "l'")
    text = text.replace(" De ", " de ")
    text = text.replace(" Di ", " di ")
    text = text[0].upper() + text[1:]
    return text


def simplify_name(name):
    if name.lower().startswith("m."):
        name = name[2:].strip()
    return name


def main(inputdir, outputdir, candidatefile, minidumpfile, match_file):
    inputpath = pathlib.Path(inputdir)
    outputpath = pathlib.Path(outputdir)
    xmlns = "http://www.tei-c.org/ns/1.0"

    try:
        outputpath.mkdir()
    except FileExistsError:
        pass

    if inputpath == outputpath:
        raise ValueError("input and output directory are the same.")

    if outputpath.is_file():
        raise ValueError("output directory exists and is a file.")

    pseudo2name = {}
    if match_file:
        with open(match_file) as input_stream:
            pseudo2name = json.load(input_stream)

    nlp = spacy.blank('fr')
    nlp.add_pipe('opentapioca')

    minidump = []
    candidate_entries = {}
    for inputfile in tqdm(sorted(inputpath.glob("*.xml"))):
        root = etree.parse(str(inputfile))
        for sentence in root.iterfind(f".//{{{xmlns}}}s"):
            common = set()
            entities_gold = set(node.text for node in sentence.iterfind(f"{{{xmlns}}}Entity"))

            if not entities_gold:
                continue

            text = normalize(etree.tostring(sentence, method="text", encoding="utf-8").decode("utf-8").strip())
            entities_OT = nlp(text).ents

            for entity in entities_OT:
                if entity.text in entities_gold:
                    print("found:", entity, entity.text, entity.kb_id_, entity.label_, entity._.description)
                    common.add(entity.text)
                    candidate_entries[entity.text] = [entity.kb_id_]

            remaining = entities_gold - common - set(candidate_entries.keys())
            for rem in remaining:
                mention = simplify_name(rem)
                print("remaining:", rem, "==>", mention)
                candidates = []
                for lang in ["fr", "it", "en"]:
                    candidates = query_wikidata(mention, lang)["search"]
                    if candidates:
                        break
                if candidates:
                    candidate_entries[rem] = [item["id"] for item in candidates]
                else:
                    candidate_entries[rem] = ["NIL"]

    # always adding true names so you can safely look for matches later on
    for truename in sorted(set(pseudo2name.values())):
        if truename in candidate_entries:
            continue
        print("searching", truename)
        candidates = []
        for lang in ["fr", "it", "en"]:
            candidates = query_wikidata(mention, lang)["search"]
            if candidates:
                break
        if candidates:
            candidate_entries[truename] = [item["id"] for item in candidates]
        else:
            candidate_entries[truename] = ["NIL"]

    for mention, candidate_ids in list(candidate_entries.items()):
        if len(candidate_ids) == 1:
            continue
        candidates = [from_qid(candidate_id) for candidate_id in candidate_ids]
        candidates = [item for item in candidates if is_human(item) and (wikidata_occupations(item) & TARGET_OCCUPATIONS)]
        if candidates:
            candidate_entries[mention] = [item["id"] for item in candidates]
            minidump.extend(candidates)
        else:
            candidate_entries[mention] = ["NIL"]

    # Short mentions (name or initial+name) have a higher risk of being mislabeled by opentapioca.
    # Since we are in a very restricted case, we try to link together short mentions with longer ones.
    # When we find a match, we simply transfert the candidate ids of the longer mention to the shorter one.
    errorprone_mentions = set(mention for mention in candidate_entries if ' ' not in mention or mention[1] == ".")
    safe_mentions = set(candidate_entries.keys()) - errorprone_mentions
    for errorprone in errorprone_mentions:
        ep_tokens = errorprone.lower().split()
        for safe in safe_mentions:
            s_tokens = safe.lower().split()
            if ep_tokens[-1] == s_tokens[-1]:
                if len(ep_tokens) == 1:
                    print("1", errorprone, "=", safe)
                    candidate_entries[errorprone] = candidate_entries[safe][:]
                    break
                elif errorprone[0] == safe[0]:
                    print("2", errorprone, "=", safe)
                    candidate_entries[errorprone] = candidate_entries[safe][:]
                    break

    for mention in candidate_entries:
        match = pseudo2name.get(mention)
        if match:
            print("found match!", mention, "<->", match)
            candidate_entries[mention] = candidate_entries[match]

    with open(candidatefile, "w") as output_stream:
        json.dump(candidate_entries, output_stream, indent=1)

    valid = set()
    for id_list in candidate_entries.values():
        valid.update(id_list)

    minidump = [item for item in minidump if item["id"] in valid]
    with open(minidumpfile, "w") as output_stream:
        first = True
        output_stream.write("[\n")
        for item in minidump:
            if not first:
                output_stream.write(",\n")
            first = False
            output_stream.write(" ")
            json.dump(item, output_stream)
        output_stream.write("\n]\n")

    for inputfile in tqdm(sorted(inputpath.glob("*.xml"))):
        outfile = pathlib.Path(outputdir) / inputfile.name
        root = etree.parse(str(inputfile))
        for sentence in root.iterfind(f".//{{{xmlns}}}s"):
            for node in sentence.iterfind(f"{{{xmlns}}}Entity"):
                wikidata_id = candidate_entries[node.text][0]
                node.attrib["annotation"] = "PER"
                node.attrib["wikidata_id"] = wikidata_id

        with open(outfile, "w") as output_stream:
            output_stream.write(etree.tostring(root, pretty_print=True, encoding="utf-8").decode("utf-8"))

        etree.parse(str(outfile))


if __name__ == "__main__":
    import sys
    import argparse

    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "inputdir",
        help="The input directory with XML files."
    )
    parser.add_argument(
        "outputdir",
        help="The output directory where annotated XML files will be written."
    )
    parser.add_argument(
        "candidatefile",
        help="The output file with candidate Wikidata IDs (.json)."
    )
    parser.add_argument(
        "minidumpfile",
        help="The file that will act as a minimal subset of Wikidata (.json)."
    )
    parser.add_argument(
        "-m", "--match-file",
        help="The file where some [pseudonym -> name] matches are given (.json)."
    )
    args = parser.parse_args()

    main(**vars(args))
    sys.exit(0)
