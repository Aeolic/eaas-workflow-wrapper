# Imports
import json
import os.path
import time
from pathlib import Path, PurePath
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

SHOULD_UPLOAD = False

def convert_tool_to_yaml(tool):
    tool_dict = tool.save(top=True)

    io = StringIO()

    yaml.scalarstring.walk_tree(tool_dict)

    yaml.round_trip_dump(tool_dict, io, default_style=None, default_flow_style=False, indent=2,
                         block_seq_indent=0, line_break=0, explicit_start=False)

    # print(io.getvalue())

    return io.getvalue()


def rewrite(cwl_file):
    # Read in the cwl file from a yaml
    with open(cwl_file, "r") as cwl_h:
        yaml_obj = yaml.main.round_trip_load(cwl_h, preserve_quotes=True)
        str_obj = cwl_file.read_text()

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

    #cwl_obj = parser.load_document_by_string(str_obj, "") #Path("").as_uri())# cwl_file.as_uri())

    # print("List of object attributes:\n{}".format("\n".join(map(str, dir(cwl_obj)))))

    # TODO add flag to skip command line tool if no dockerPull
    if isinstance(cwl_obj, Workflow):
        if cwl_obj.steps:
            print("WORKFLOW DETECTED ")

            # FIXME check if [8:] works on unix as well
            # TODO only rewrite if dockerPull flag in command line tool
            for step in cwl_obj.steps:
                print("Type step:", type(step))
                print("Step:", step.run, step.run[8:])
                print(step.id)
                is_rewritten = rewrite(Path(step.run[8:]))

                if not is_rewritten:
                    continue

                head, tail = os.path.split(Path(step.run[8:]))  # use this for the actual file?
                rewritten_name = head +"/wrapped_" + tail
                rewritten_name = rewritten_name.replace("\\", "/")

                print("Rewritten name:", rewritten_name)
                print("CWL FILE:", cwl_file)
                print("REL:", os.path.relpath(rewritten_name, os.path.dirname(cwl_file)))
                step.run = os.path.relpath(rewritten_name, os.path.dirname(cwl_file))

            # cwl_obj.id = cwl_obj.id[8:]
            print("ID::", cwl_obj.id)
            head_wf, tail_wf = os.path.split(cwl_file.as_uri()[8:])  # use this for the actual file?
            uri_ = head_wf + "/wrapped_workflow_" + tail_wf
            print("Writing file to:", uri_)
            with open(uri_, "w+") as f:
                final = convert_tool_to_yaml(cwl_obj)
                f.write(final)

            exit(0)

    docker_pull = None
    docker_output_directory = ""
    original_initial_workdir_req_listing = []

    if cwl_obj.hints:

        has_docker_hint = False
        for hint in cwl_obj.hints:
            if hint["class"] == "DockerRequirement":
                has_docker_hint = True
                docker_pull = hint["dockerPull"]
                if "dockerOutputDirectory" in hint:
                    docker_output_directory = hint["dockerOutputDirectory"]
            break
        if has_docker_hint:
            cwl_obj.hints.remove(hint)

    if cwl_obj.requirements:
        docker_req_found = False
        for req in cwl_obj.requirements:
            if type(req) == DockerRequirement:
                docker_req_found = True
                if req.dockerPull:
                    docker_pull = req.dockerPull
                    req.dockerPull = "aeolic/cwl-wrapper:2.7.9"
                if req.dockerOutputDirectory:
                    docker_output_directory = req.dockerOutputDirectory
                req.dockerOutputDirectory = "/app/output"

            if type(req) == InitialWorkDirRequirement:
                original_initial_workdir_req_listing.extend(req.listing)

            # TODO other requirements + hints (interesting for prov doc)

        if not docker_req_found:
            docker_req = DockerRequirement(dockerPull="aeolic/cwl-wrapper:2.7.9", dockerOutputDirectory="/app/output") # TODO remove duplicate
            cwl_obj.requirements.append(docker_req)

    # except Exception as e:
    #     print("Something went wrong while reading DockerRequirement:", e)

    if not docker_pull:
        print("CWL did not have dockerPull, returning")
        return False

    env_id = "50e4bdfa-0762-430e-abae-7b73c4b50da4"

    if SHOULD_UPLOAD:
        env_id = containerImport.import_image(docker_pull)

    output_folder = docker_output_directory if docker_output_directory else "/output"

    config_json = {
        "environmentId": env_id,
        "outputFolder": output_folder,
        "initialWorkDirRequirements": [x.entryname for x in original_initial_workdir_req_listing]
    }

    for inp in cwl_obj.inputs:
        inp.id = inp.id.split("#")[1]  # to remove absolut paths

    for outp in cwl_obj.outputs:
        outp.id = outp.id.split("#")[1]

    # outpBinding = CommandOutputBinding(glob="*.log")
    # log_output = CommandOutputParameter("logfile", type="File", outputBinding=outpBinding)
    # cwl_obj.outputs.append(log_output)

    entry = json.dumps(config_json, indent=4, separators=(',', ': '))

    new_workdir_req = [Dirent(entry, entryname="config.json")]  # TODO to list: []?

    # TODO ADD WRAPPER AS BASE COMMAND

    if not isinstance(cwl_obj.baseCommand, list):
        cwl_obj.baseCommand = [cwl_obj.baseCommand]

    cwl_obj.baseCommand.insert(0, "python3")
    cwl_obj.baseCommand.insert(1, "/app/wrapper.py")

    config_json_set = False
    if not cwl_obj.requirements:
        cwl_obj.requirements = []
    for req in cwl_obj.requirements:
        if type(req) == InitialWorkDirRequirement:
            req.listing.append(new_workdir_req)
            config_json_set = True

    if not config_json_set:
        config_json_req = InitialWorkDirRequirement(new_workdir_req)

        cwl_obj.requirements.append(config_json_req)

    head, tail = os.path.split(cwl_file)  # use this for the actual file?
    rewritten_name = head + "/wrapped_" + tail

    print("----- OUTPUT: Writing file to:", rewritten_name)
    with open(rewritten_name, "w+") as f:
        final = convert_tool_to_yaml(cwl_obj)

        # final = final.replace('"${var', '${var')
        # final = final.replace('r}"', 'r}')

        f.write(final)

    # TODO output in general (change backend!)
    # TODO when using runtime.outdir, wrapper output will be used instead of proper output path

    return True
# cwl_file_path = Path("E:\\Thesis\\TestTool\\test-auto.cwl")
# cwl_file_path = Path("E:\\Thesis\\CwlEnvironmentStarter\\biom_convert.cwl")
cwl_file_path = Path("E:\Thesis\workflowWindows\jurek\\1st-workflow.cwl")
# cwl_file_path = Path("F:/Thesis/pipeline-v5-master-wrapper-tests/workflows/subworkflows/assembly/kegg_analysis.cwl")
# cwl_file_path = Path("F:/Thesis/pipeline-v5-master/tools/RNA_prediction/thesis_example_workflow/example_workflow.cwl")
# cwl_file_path = Path("F:/Thesis/ExampleWorkflow/example_workflow.cwl")


rewrite(cwl_file_path)

# TODOS: runtime.X
# TODO env requirement
