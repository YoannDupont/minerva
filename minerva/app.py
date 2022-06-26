from flask import (Flask, render_template, jsonify, request, abort, Response, stream_with_context)

import pathlib
import json
import zipfile

from io import StringIO
import csv

from process_annotated_zip import process_annotated_zip
from process_zip_annotated_cooc import process_zip_cooc as make_cooc_json_annotated


app = Flask(__name__)


with open(pathlib.Path(app.static_folder) / "json" / "mdf-knowledge-base.json") as input_stream:
    knowledge_base = json.load(input_stream)

with open(pathlib.Path(app.static_folder) / "json" / "qid_to_claims.json") as input_stream:
    qid_to_claims = json.load(input_stream)


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/process_zip', methods=["POST"])
def process_zip():
    input_zip = request.files.get("input zip")
    annotation_filter = request.form.get("annotation filter")
    author_xpath = request.form.get("author xpath")  # teiHeader/profileDesc/textClass/keywords/term[@type='author']
    file_like_object = input_zip.stream._file  
    zipfile_object = zipfile.ZipFile(file_like_object)

    return process_annotated_zip(zipfile_object, knowledge_base, annotation_filter=annotation_filter, author_xpath=author_xpath)


@app.route('/process_zip_cooc', methods=["POST"])
def process_zip_cooc():
    input_zip = request.files.get("input zip")
    pos_filter = request.form.get("POS filter")
    pos_filter = set(pos_filter.split(",") if pos_filter else set())
    ne_filter = request.form.get("NE filter")
    target_property = request.form.get("target property")
    max_degree = int(request.form.get("max degree"))
    file_like_object = input_zip.stream._file
    zipfile_object = zipfile.ZipFile(file_like_object)

    return make_cooc_json_annotated(
        zipfile_object,
        knowledge_base,
        qid_to_claims,
        pos_filter=pos_filter,
        target_property=target_property,
        max_degree=max_degree
    )


@app.route('/data_to_csv', methods=["POST"])
@stream_with_context
def data_to_csv():
    input_json_str = request.data
    input_json = json.loads(input_json_str)
    keys = ["source", "target", "strength"]
    output_stream = StringIO()
    writer = csv.DictWriter(output_stream, fieldnames=keys, delimiter="\t")
    writer.writeheader()
    for link in input_json["data"]["links"]:
        row = {
            "source" : link["source"]["id"],
            "target" : link["target"]["id"],
            "strength" : link["value"],
        }
        writer.writerow(row)
    # name not useful, will be handled in javascript
    response = Response(output_stream.getvalue(), mimetype='text/csv', headers={"Content-disposition": "attachment; filename=export.csv"})
    output_stream.seek(0)
    output_stream.truncate(0)
    return response


if __name__ == '__main__':
    app.run(port=5000, debug=True)
