import json
import os
import shutil
import subprocess
import sys
import tarfile
import time
from distutils.dir_util import copy_tree

import requests

EMIL_BASE_URL = "https://historic-builds.emulation.cloud/emil"
OUTPUT_DIR = "/app/output"

#OUTPUT_DIR = "output"

def upload_file_to_blobstore(path):
    try:
        file = open(path, "rb")
    except Exception as e:
        print("Could not find file: " + path)
        print(e)
        exit(1)

    req = requests.post(EMIL_BASE_URL + "/upload?access_token=undefined", files={"file": file})

    print("Got status:", req.status_code, "for file ", path)
    print("Got response: ", req.json())
    return req.json()["uploads"][0]


def tar_inputs(tool_args):
    paths_to_add = []

    for arg in tool_args:
        if os.path.exists(arg):
            print("Found file or directory:", arg)
            paths_to_add.append(arg)
        else:
            print(arg, "was no file/dir.")

    with tarfile.open("inputs.tgz", "w:gz") as tar:
        for p in paths_to_add:
            print("Adding:", p)
            tar.add(p)


def tar_initial_work_dir_requirements(file_paths):
    if not file_paths:
        return

    with tarfile.open("initial.tgz", "w:gz") as tar:
        for p in file_paths:
            print("Adding:", p)
            tar.add(p)

def cp_parents(target_dir, files):
    dirs = []
    for file in files:
        dirs.append(os.path.dirname(file))
    dirs.sort(reverse=True)
    for i in range(len(dirs)):
        if not dirs[i] in dirs[i-1]:
            need_dir = os.path.normpath(target_dir + dirs[i])
            print("Creating", need_dir )
            os.makedirs(need_dir)
    for file in files:
        dest = os.path.normpath(target_dir + file)
        print("Copying %s to %s" % (file, dest))
        shutil.copy(file, dest)


def removeEmptyFolders(path, removeRoot=True):
    'Function to remove empty folders'
    if not os.path.isdir(path):
        return

    # remove empty subfolders
    files = os.listdir(path)
    if len(files):
        for f in files:
            fullpath = os.path.join(path, f)
            if os.path.isdir(fullpath):
                removeEmptyFolders(fullpath)

    # if folder empty, delete it
    files = os.listdir(path)
    if len(files) == 0 and removeRoot:
        # print("Removing empty folder:", path)
        os.rmdir(path)



def main():
    json_data = {}

    with open("config.json") as config:
        json_data = json.load(config)
    initial_work_dir_reqs = json_data["initialWorkDirRequirements"]

    if len(sys.argv) > 2:
        tool_args = sys.argv[1:]
        print(tool_args)
        tar_inputs(tool_args)

        input_tar_url = upload_file_to_blobstore("inputs.tgz")
        json_data["inputTarURL"] = input_tar_url
        print("Done with tar!")

    if initial_work_dir_reqs:
        tar_initial_work_dir_requirements(initial_work_dir_reqs)
        initial_tar_url = upload_file_to_blobstore("initial.tgz")
        json_data["workdirTarURL"] = initial_tar_url

    args_dict = {}
    for i,arg_to_send in enumerate(sys.argv[1:]):
        args_dict[str(i)] = arg_to_send

    json_data["arguments"] = args_dict
    del json_data["initialWorkDirRequirements"]

    print("Sending Json: ", json_data)

    # TODO überall status checks, falls nicht richtiger status: error + stop
    wf_response = requests.post(EMIL_BASE_URL + "/workflow/api/v1/workflow",
                                json=json_data)
    wait_queue_url = wf_response.json()["waitQueueUrl"]

    print("Entering polling loop now:")
    while True:

        wait_queue_response = requests.get(wait_queue_url)
        q_json = wait_queue_response.json()

        if not q_json["isDone"]:
            print("Tool is still running.")
            time.sleep(5)
        else:
            print("Tool is done!")
            result_url = q_json["resultUrl"]
            break

    result_response = requests.get(result_url)
    blobstore_url = result_response.json()["url"]
    print("Blobstore URL: " + blobstore_url)

    blobstore_response = requests.get(blobstore_url)


    temp_dir = "/tempDir"
    shutil.rmtree(temp_dir, ignore_errors=True)

    os.mkdir(temp_dir)
    # os.chmod(temp_dir, 0o777)

    with open(temp_dir + "/files.tgz", "wb") as f:
        f.write(blobstore_response.content)

    with tarfile.open(temp_dir + "/files.tgz", "r:gz") as zip_ref:
        def is_within_directory(directory, target):
            
            abs_directory = os.path.abspath(directory)
            abs_target = os.path.abspath(target)
        
            prefix = os.path.commonprefix([abs_directory, abs_target])
            
            return prefix == abs_directory
        
        def safe_extract(tar, path=".", members=None, *, numeric_owner=False):
        
            for member in tar.getmembers():
                member_path = os.path.join(path, member.name)
                if not is_within_directory(path, member_path):
                    raise Exception("Attempted Path Traversal in Tar File")
        
            tar.extractall(path, members, numeric_owner=numeric_owner) 
            
        
        safe_extract(zip_ref, path=temp_dir)

    os.remove(temp_dir + "/files.tgz")

    tmp1 = os.path.join(temp_dir, "tmp")
    tmp2 = os.path.join(tmp1, os.listdir(tmp1)[0])
    outputDir = os.path.join(tmp2, "outputDir")

    print("OutputDIR: ", outputDir)
    removeEmptyFolders(outputDir)

    for root, dirs, files in os.walk(outputDir):
        for file in files:
            print("Output file before copy:", os.path.join(root, file))

    # cp_parents(OUTPUT_DIR, output_files)
    # subprocess.run(["cp", "-r",  "/tempDir/*",  "/app/output/"], shell=True)
    # os.system("cp -r /tempDir/* /app/output/")
    shutil.rmtree(OUTPUT_DIR, ignore_errors=True)
    shutil.copytree(outputDir, OUTPUT_DIR, dirs_exist_ok=True)
    shutil.rmtree(temp_dir)

    print("Files in ", OUTPUT_DIR)
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for file in files:
            print(os.path.join(root, file))

    print("Done! Files stored at: " + OUTPUT_DIR)


if __name__ == '__main__':
    main()
