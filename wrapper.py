import argparse
import json
import os
import pathlib
import re
import shutil
import sys
import time
import zipfile

import requests

EMIL_BASE_URL = "https://historic-builds.emulation.cloud/emil"
OUTPUT_DIR = "/app/output"
# LOG_DIR = "/app/logs"


def main():
    # parser = argparse.ArgumentParser(
    #     "Wrapper for the EAAS Workflow API, automatically starts a container based tool and retrieves the output!")
    #
    # parser.add_argument("environmentId", type=str, help="The Id of the environment.")
    # parser.add_argument("-f", "--files", nargs="*")
    # parser.add_argument("-p", "--params", nargs="*")
    #
    # args = parser.parse_args()
    # env_id, files, params = args.environmentId, args.files, args.params
    #
    # print("Env ID", env_id)
    # print("Data", files)
    # print("Params", params)

    # args = sys.argv
    # print(args)
    # env_id = args[1]
    #
    # files = []
    # params = {}
    #
    # index = 0
    # for i, file in enumerate(args[3:]):
    #     if file in ["-p", "--params"]:
    #         index = i + 4
    #         break
    #     files.append(file)
    #
    # for i2, param in enumerate(args[index:]):
    #     params[i2] = param
    #
    # print("Env ID", env_id)
    # print("Data", files)
    # print("Params", params)

    json_data = {}

    with open("config.json") as config:
        json_data = json.load(config)

    files = json_data["inputFiles"]
    input_files = {}
    for file_path in files:

        try:
            file = open(file_path, "rb")
        except Exception as e:
            print("Could not find file: " + file_path)
            print(e)
            exit(1)

        req = requests.post(EMIL_BASE_URL + "/upload?access_token=undefined", files={"file": file})

        print("Got status:", req.status_code, "for file ", file_path)
        print("Got response: ", req.json())
        input_files[pathlib.Path(file_path).name] = req.json()["uploads"][0]

    print("Starting Workflow!")

    json_data["inputFiles"] = input_files

    # TODO überall status checks, falls nicht richtiger status: error + stop


    print("Sending Json: ", json_data)
    wf_response = requests.post(EMIL_BASE_URL + "/workflow/api/v1/workflow",
                                json=json_data)
    wait_queue_url = wf_response.json()["waitQueueUrl"]

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

    with open(OUTPUT_DIR + "/files.zip", "wb") as f:
        f.write(blobstore_response.content)

    with zipfile.ZipFile(OUTPUT_DIR + "/files.zip", "r") as zip_ref:
        zip_ref.extractall(OUTPUT_DIR)

    os.remove(OUTPUT_DIR + "/files.zip")

    # regex = re.compile("container-log-[a-z0-9\-]*\.log")
    #
    print("Files in output: ")
    for root, dirs, files in os.walk(OUTPUT_DIR):
        for file in files:
            print(file)

    print("Done! Files stored at: " + OUTPUT_DIR)


if __name__ == '__main__':
    main()
