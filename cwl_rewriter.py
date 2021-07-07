# Imports
import json
import time
from pathlib import Path
from threading import Thread

import requests
from cwl_utils.parser_v1_0 import CommandInputArraySchema, Dirent, InitialWorkDirRequirement, \
    DockerRequirement
from ruamel import yaml
import sys

# File Input - This is the only thing you will need to adjust or take in as an input to your function:
from ruamel.yaml import StringIO

from wrapper import EMIL_BASE_URL

TEMPLATE = """
#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: CommandLineTool
baseCommand: [cat, config.json] # [python3, /app/wrapper.py]
requirements:
  InlineJavascriptRequirement: {}
  DockerRequirement:
    dockerPull: aeolic/cwl-wrapper:latest
    dockerOutputDirectory: /app/output
  InitialWorkDirRequirement:
    listing:
      - entryname: config.json
        entry: |-
          {}
inputs: 
  []
outputs:
  logfile:
    type: File
    outputBinding:
      glob: '*.log'
"""


def convert_tool_to_yaml(tool):
    tool_dict = tool.save()

    io = StringIO()

    yaml.scalarstring.walk_tree(tool_dict)

    yaml.round_trip_dump(tool_dict, io, default_style=None, default_flow_style=False, indent=2,
                         block_seq_indent=0, line_break=0, explicit_start=False)
    return io.getvalue()


# cwl_file = Path("E:\\Thesis\\TestTool\\test-auto.cwl")
cwl_file = Path("E:\\Thesis\\CwlEnvironmentStarter\\biom_convert.cwl")

# Read in the cwl file from a yaml
with open(cwl_file, "r") as cwl_h:
    yaml_obj = yaml.main.round_trip_load(cwl_h, preserve_quotes=True)

# Check CWLVersion
if 'cwlVersion' not in list(yaml_obj.keys()):
    print("Error - could not get the cwlVersion")
    sys.exit(1)

# Import parser based on CWL Version
if yaml_obj['cwlVersion'] == 'v1.0':
    from cwl_utils import parser_v1_0 as parser
elif yaml_obj['cwlVersion'] == 'v1.1':
    from cwl_utils import parser_v1_1 as parser
elif yaml_obj['cwlVersion'] == 'v1.2':
    from cwl_utils import parser_v1_2 as parser
else:
    print("Version error. Did not recognise {} as a CWL version".format(yaml_obj["CWLVersion"]))
    sys.exit(1)

# Import CWL Object

print(cwl_file.as_uri())

cwl_obj = parser.load_document_by_yaml(yaml_obj, cwl_file.as_uri())
new_cwl = parser.load_document_by_string(TEMPLATE, "template.cwl")

# View CWL Object
# print("List of object attributes:\n{}".format(", ".join(map(str, dir(cwl_obj)))))

print("----- ----- ----- ----- -----")

"""
1. Rewriter starten, mit CWL file als param
2. Dockerpull wird ausgelesen und emuliertes tool wird erzeugt
3. wrapper file wird erstellt
4. wenn fileinputrequirement -> übernehmen für wrapper
"""
# print(cwl_obj)
#
# print(cwl_obj.inputs)


dockerPull = ""
dockerOutputDirectory = ""

original_initial_workdir_req_listing = []

if cwl_obj.hints:

    for hint in cwl_obj.hints:
        if "DockerRequirement" in str(hint):
            for tup in hint:
                if tup == "dockerPull":
                    dockerPull = hint[tup]
                if tup == "dockerOutputDirectory":
                    dockerOutputDirectory = hint[tup]

try:
    for req in cwl_obj.requirements:
        print(req)
        if type(req) == DockerRequirement:
            if req.dockerPull:
                dockerPull = req.dockerPull
            if req.dockerOutputDirectory:
                dockerOutputDirectory = req.dockerOutputDirectory

        if type(req) == InitialWorkDirRequirement:
            original_initial_workdir_req_listing = req.listing

        # TODO other requirements + hints (interesting for prov doc)

except Exception as e:
    print("Something went wrong while reading DockerRequirement:", e)

# TODO - backend hochladen, id zurückkriegen (falls es schon gibt, ansonsten neu anlegen)

should_upload = True


def poll_until_done(task_id):
    while True:
        task_response = requests.get(EMIL_BASE_URL + "/tasks/" + task_id)
        as_json = task_response.json()
        print(as_json)
        task_id = as_json["taskId"]
        is_done = as_json["isDone"]

        if is_done:
            return as_json
        else:
            time.sleep(5)
            print("Task", task_id, "is not finished yet.")


env_id = "90825a58-b795-4002-87e3-8c0b308fbcb2"
if should_upload:
    container, tag = dockerPull.split(":")
    print("Got container:", container, "tag:", tag)
    json_container_request = {"containerType": "dockerhub",
                              "urlString": container,
                              "tag": tag}

    print("Sending request to build image with data:", json_container_request)
    task_response = requests.post(EMIL_BASE_URL + "/EmilContainerData/buildContainerImage",
                                  json=json_container_request)

    image_task_id = task_response.json()["taskId"]

    # TODO error handling everywhere
    image_done = poll_until_done(image_task_id)
    response_obj = image_done["object"]
    print("Got response:", response_obj)

    if response_obj:
        data = eval(response_obj)
        meta = data["metadata"]

        print("Evalualting data was successful:", data)

        import_data = {
            "imageUrl": data["containerUrl"],
            "processArgs": meta.get("entryProcesses", []),
            "processEnvs": meta.get("envVariables", []),
            "workingDir": meta.get("workingDir", "/"),
            "name": "CWL_auto_import_" + container + ":" + tag,
            "inputFolder": "/input",  # irrelevant, gets overwritten by execution anyway
            "outputFolder": "/app/output",
            # irrelevant, gets overwritten by execution anyway (TODO maybe set properly anyway)
            "imageType": "dockerhub",
            "title": "CWL_auto_import_" + container + ":" + tag,
            "description": "<p>Automatic import by CWL Rewriter </p>",
            "author": "CWL Rewriter",  # TODO check CWL for author
            "runtimeId": "882b1ed7-e3ae-4c9b-8733-c183a6f0d6e0",  # TODO variable?
            "serviceContainer": False,
            "enableNetwork": False,
            "archive": "default"}

        print("Sending import Request with data:", import_data)
        import_response = requests.post(EMIL_BASE_URL + "/EmilContainerData/importContainer",
                                        json=import_data)

        import_task_id = import_response.json()["taskId"]

        import_done = poll_until_done(import_task_id)
        env_id = import_done["userData"]["environmentId"]
        print("Got env Id:", env_id)

input_folder = "/input"
output_folder = dockerOutputDirectory if dockerOutputDirectory else "/output"

config_json = {
    "environmentId": env_id,
    "inputFolder": input_folder,
    "outputFolder": output_folder,
    "inputFiles": "",
    "arguments": "",
    "unordered": ""
}

files_to_add = []

base_args = cwl_obj.baseCommand

if type(base_args) is not list:
    base_args = [base_args]

base_args_len = len(base_args)

args_ordered = {}
args_unordered = {}
for i, base_arg in enumerate(base_args):
    args_ordered[i] = base_arg

for inp in cwl_obj.inputs:
    print("INPUT:")
    print(inp.id, type(inp), inp.type)

    # FIXME remove this hack that is a nullable workaround
    if isinstance(inp.type, list):
        print("Removing list type to : " + inp.type[1])
        inp.type = inp.type[1]

    if inp.inputBinding:
        pos = None
        if inp.inputBinding.position:
            pos = inp.inputBinding.position

        print("Found input with binding ", pos, ":", inp.id)
        # TODO add check for seperate flag for array prefixes (maybe just pass to python)

        prefix = ""
        if inp.inputBinding.prefix:
            print("FOUND PREFIX!!!!!!!", inp.inputBinding.prefix)
            prefix = inp.inputBinding.prefix
            if pos:
                args_ordered[str(pos + base_args_len - 1) + "_PREFIX"] = prefix

        if isinstance(inp.type,
                      CommandInputArraySchema):  # input is array, values need to be concatenated
            print("FOUND ARRAY!")

            array_prefix = ""
            if inp.type.inputBinding:
                if inp.type.inputBinding.prefix:
                    array_prefix = inp.type.inputBinding.prefix
                    if pos:
                        args_ordered[str(pos + base_args_len - 1) + "_ARRAY_PREFIX"] = array_prefix
                    inp.type.inputBinding = None

            FILE_STRING_ARRAY = "${{var r = [];for (const val of inputs.{0}) {{r.push('{1}/' + val.basename);}}return r}}".format(
                inp.id.split("#")[1], input_folder)
            NON_FILE_STRING_ARRAY = "${{var r = [];for (const val of inputs.{0}) {{r.push(val);}}return r}}".format(
                inp.id.split("#")[1])

            if inp.type.items == "File":
                array_code = FILE_STRING_ARRAY
            else:
                array_code = NON_FILE_STRING_ARRAY
            if pos:
                args_ordered[pos + base_args_len - 1] = array_code

        else:  # single input

            FILE_STRING = "$('{1}/' + inputs.{0}.basename)".format(inp.id.split("#")[1],
                                                                   input_folder)
            NON_FILE_STRING = "$(inputs.{0})".format(
                inp.id.split("#")[1])

            str_to_use = FILE_STRING if inp.type == "File" else NON_FILE_STRING

            if pos:
                args_ordered[pos + base_args_len - 1] = str_to_use
            else:
                args_unordered[inp.inputBinding.prefix] = str_to_use

        # Remove inputBinding, because we don't need it in the CWL anymore
        inp.inputBinding = None

    else:
        print("Input", inp.id,
              "had no binding (probably a file that should be mounted but is not called as an argument).")

    if inp.type == "File":  # TODO nullables...
        print("Found single file!")
        files_to_add.append("$(inputs.{0}.path)".format(inp.id.split("#")[1]))

    elif isinstance(inp.type, CommandInputArraySchema):
        print("Found array ---- : " + inp.id.split("#")[1])
        if inp.type.items == "File":
            print("Found file array!", inp.id.split("#")[1])

            array_code = "${{var r = [];for (const val of inputs.{0}) {{r.push(val.path);}}return r}}".format(
                inp.id.split("#")[1])

            files_to_add.append(array_code)

    inp.id = inp.id.split("#")[1]

print("Will use this as args:", args_ordered)
config_json["arguments"] = args_ordered

print("Will use this as unorderer:", args_unordered)
config_json["unordered"] = args_unordered

print("Will use this as files:", files_to_add)
config_json["inputFiles"] = files_to_add
print("IN CONFIG", config_json["inputFiles"])

new_cwl.inputs.extend(cwl_obj.inputs)

for outp in cwl_obj.outputs:
    outp.id = outp.id.split("#")[1]

new_cwl.outputs.extend(cwl_obj.outputs)
entry = json.dumps(config_json, indent=4, separators=(',', ': '))

new_workdir_req = Dirent(entry, entryname="config.json")

for req in new_cwl.requirements:
    if type(req) == InitialWorkDirRequirement:
        req.listing.clear()
        req.listing.append(new_workdir_req)
        req.listing.extend(original_initial_workdir_req_listing)

new_cwl.save()

with open("wrapped_cwl.cwl", "w+") as f:
    final = convert_tool_to_yaml(new_cwl)

    final = final.replace('"${var', '${var')
    final = final.replace('r}"', 'r}')

    f.write(final)
