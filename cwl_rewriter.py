# Imports
import json
import os.path
import time
from pathlib import Path
from threading import Thread

import requests
from cwl_utils.parser_v1_0 import CommandInputArraySchema, Dirent, InitialWorkDirRequirement, \
    DockerRequirement, CommandLineTool, Workflow, CommandLineBinding
from ruamel import yaml
import sys

# File Input - This is the only thing you will need to adjust or take in as an input to your function:
from ruamel.yaml import StringIO
from ruamel.yaml.scalarstring import DoubleQuotedScalarString

import containerImport
from wrapper import EMIL_BASE_URL

TEMPLATE = """
#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: CommandLineTool
baseCommand: [python3, /app/wrapper.py]
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
SHOULD_UPLOAD = False


# TODO format somehow doesn't work for wrapped cwl?

def convert_tool_to_yaml(tool):
    tool_dict = tool.save()

    io = StringIO()

    yaml.scalarstring.walk_tree(tool_dict)

    yaml.round_trip_dump(tool_dict, io, default_style=None, default_flow_style=False, indent=2,
                         block_seq_indent=0, line_break=0, explicit_start=False)
    return io.getvalue()


def rewrite(cwl_file):
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
    print("Type:", type(cwl_obj))
    #
    # print(cwl_obj.inputs)

    # TODO this !!!!!!
    if isinstance(cwl_obj, Workflow):
        if cwl_obj.steps:
            print("WORKFLOW DETECTED ")

            # FIXME remove windows only 8: hack
            # TODO only rewrite if dockerPull flag in command line tool
            for step in cwl_obj.steps:
                print(step.run)
                rewrite(Path(step.run[8:]))

                head, tail = os.path.split(Path(step.run[8:]))  # use this for the actual file?
                rewritten_name = "wrapped_" + tail

                step.run = rewritten_name

            head_wf, tail_wf = os.path.split(cwl_file.as_uri()[8:])  # use this for the actual file?
            uri_ = head_wf + "/wrapped_workflow_" + tail_wf
            print("Writing file to:", uri_)
            with open(uri_, "w+") as f:
                final = convert_tool_to_yaml(cwl_obj)
                f.write(final)

            exit(0)

    # TODO add flag to skip command line tool if no dockerPull

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

    env_id = "50e4bdfa-0762-430e-abae-7b73c4b50da4"

    if SHOULD_UPLOAD:
        env_id = containerImport.import_image(dockerPull)

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

        nullable_flag = False
        original_type = inp.type
        # FIXME remove this hack that is a nullable workaround
        # FIXME: ? needs to be added to nullable inputs!
        if isinstance(inp.type, list):
            print("Removing list type to : " + inp.type[
                1])  # FIXME remove hardcoded and check where null is
            inp.type = inp.type[1]
            nullable_flag = True

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
                            args_ordered[
                                str(pos + base_args_len - 1) + "_ARRAY_PREFIX"] = array_prefix
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

                # TODO check for different types and use "" accordingly?
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

        if nullable_flag:
            print("SETTING ORIG TYPE:", original_type)
            inp.type = inp.type + "?"  # TODO arrays? doesn't work because they arent string based

    for inp_after in cwl_obj.inputs:
        print("INP AFTER:", inp_after.id, inp_after.type)

    # TODO ARGUMENTS!!!
    # FIXME: \n in arguments will be stored as \n, which leads to errors - remove!
    if cwl_obj.arguments:
        for arg in cwl_obj.arguments:
            print("ARG:", arg, "TYPE:", type(arg))

            if isinstance(arg, CommandLineBinding):

                if arg.prefix:
                    print("VAL FROM:", arg.valueFrom)
                    print("TYPE:", type(arg.valueFrom))
                    args_unordered[arg.prefix] = str(arg.valueFrom).replace("\n", "")

                else:

                    print("VAL FROM:", arg.valueFrom)
                    args_unordered[
                        arg.valueFrom] = "true"  # TODO rework the whole unordered system, hacky!!
            elif isinstance(arg, str) or isinstance(arg, DoubleQuotedScalarString):
                args_unordered[arg] = "true"

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

    head, tail = os.path.split(cwl_file)  # use this for the actual file?
    rewritten_name = head + "/wrapped_" + tail

    print("Writing file to:", rewritten_name)
    with open(rewritten_name, "w+") as f:
        final = convert_tool_to_yaml(new_cwl)

        final = final.replace('"${var', '${var')
        final = final.replace('r}"', 'r}')

        f.write(final)

    # TODO output in general (change backend!)
    # TODO when using runtime.outdir, wrapper output will be used instead of proper output path


# cwl_file = Path("E:\\Thesis\\TestTool\\test-auto.cwl")
# cwl_file_path = Path("E:\\Thesis\\CwlEnvironmentStarter\\biom_convert.cwl")
cwl_file_path = Path("E:\Thesis\workflowWindows\jurek\\1st-workflow.cwl")

rewrite(cwl_file_path)
