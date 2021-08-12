# Imports
import json
import os.path
import time
from pathlib import Path
from threading import Thread

import requests
from cwl_utils.parser_v1_0 import CommandInputArraySchema, Dirent, InitialWorkDirRequirement, \
    DockerRequirement, CommandLineTool, Workflow, CommandLineBinding, CommandOutputParameter, File, \
    CommandOutputBinding
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

    # TODO this !!!!!!
    # TODO add flag to skip command line tool if no dockerPull
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

    dockerPull = None
    dockerOutputDirectory = ""
    original_initial_workdir_req_listing = []

    if cwl_obj.hints:

        for hint in cwl_obj.hints:
            if "DockerRequirement" in str(hint):
                for tup in hint:
                    if tup == "dockerPull":
                        dockerPull = hint[tup]
                        hint[tup] = "aeolic/cwl-wrapper:latest"
                    if tup == "dockerOutputDirectory":
                        dockerOutputDirectory = hint[tup]
                        hint[tup] = "/app/output"

    try:
        for req in cwl_obj.requirements:
            print(req)
            if type(req) == DockerRequirement:
                if req.dockerPull:
                    dockerPull = req.dockerPull
                    req.dockerPull = "aeolic/cwl-wrapper:latest"
                if req.dockerOutputDirectory:
                    dockerOutputDirectory = req.dockerOutputDirectory
                    req.dockerOutputDirectory = "/app/output"

            if type(req) == InitialWorkDirRequirement:
                original_initial_workdir_req_listing.extend(req.listing)

            # TODO other requirements + hints (interesting for prov doc)

    except Exception as e:
        print("Something went wrong while reading DockerRequirement:", e)

    if not dockerPull:
        print("CWL did not have dockerPull, returning")
        return

    # TODO - backend hochladen, id zurückkriegen (falls es schon gibt, ansonsten neu anlegen)

    env_id = "50e4bdfa-0762-430e-abae-7b73c4b50da4"

    if SHOULD_UPLOAD:
        env_id = containerImport.import_image(dockerPull)

    output_folder = dockerOutputDirectory if dockerOutputDirectory else "/output"

    config_json = {
        "environmentId": env_id,
        "outputFolder": output_folder,
        "initialWorkDirRequirements": [x.entryname for x in original_initial_workdir_req_listing]
    }

    for inp in cwl_obj.inputs:
        inp.id = inp.id.split("#")[1]  # to remove absolut paths

    for outp in cwl_obj.outputs:
        outp.id = outp.id.split("#")[1]

    outpBinding = CommandOutputBinding(glob="*.log")
    log_output = CommandOutputParameter("logfile", type="File", outputBinding=outpBinding)
    cwl_obj.outputs.append(log_output)

    entry = json.dumps(config_json, indent=4, separators=(',', ': '))

    new_workdir_req = Dirent(entry, entryname="config.json")

    for req in cwl_obj.requirements:
        if type(req) == InitialWorkDirRequirement:
            req.listing.append(new_workdir_req)

    cwl_obj.save()

    head, tail = os.path.split(cwl_file)  # use this for the actual file?
    rewritten_name = head + "/wrapped_" + tail

    print("Writing file to:", rewritten_name)
    with open(rewritten_name, "w+") as f:
        final = convert_tool_to_yaml(cwl_obj)

        # final = final.replace('"${var', '${var')
        # final = final.replace('r}"', 'r}')

        f.write(final)

    # TODO output in general (change backend!)
    # TODO when using runtime.outdir, wrapper output will be used instead of proper output path


cwl_file_path = Path("E:\\Thesis\\TestTool\\test-auto.cwl")
# cwl_file_path = Path("E:\\Thesis\\CwlEnvironmentStarter\\biom_convert.cwl")
# cwl_file_path = Path("E:\Thesis\workflowWindows\jurek\\1st-workflow.cwl")

rewrite(cwl_file_path)

# TODOS: runtime.X
# TODO env requirement
