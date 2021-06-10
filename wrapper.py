import argparse
import time

import requests

EMIL_BASE_URL = "https://historic-builds.emulation.cloud/emil"


def main():
    parser = argparse.ArgumentParser(
        "Wrapper for the EAAS Workflow API, automatically starts a container based tool and retrieves the output!")

    parser.add_argument("environmentId", type=str, help="The Id of the environment.")
    parser.add_argument("files", nargs="*")

    args = parser.parse_args()
    env_id, data = args.environmentId, args.files

    print("Env ID", env_id)
    print("Data", data)

    input_files = []
    for file_path in data:

        try:
            file = open(file_path, "rb")
        except Exception as e:
            print("Could not find file: " + file_path)
            print(e)
            exit(1)

        req = requests.post(EMIL_BASE_URL + "/upload?access_token=undefined", files={"file": file})

        print("Got status:", req.status_code, "for file ", file_path)
        print("Got response: ", req.json())
        input_files.append(req.json()["uploads"][0])

    print("Starting Workflow!")

    # TODO überall status checks, falls nicht richtiger status: error + stop

    wf_response = requests.post(EMIL_BASE_URL + "/workflow/api/v1/workflow",
                                json={"environmentId": env_id, "inputFiles": input_files})
    wait_queue_url = wf_response.json()["waitQueueUrl"]

    while True:

        wait_queue_response = requests.get(wait_queue_url)
        q_json = wait_queue_response.json()

        if not q_json["done"]:
            print("Tool is still running.")
            time.sleep(5)
        else:
            print("Tool is done!")
            result_url = q_json["resultUrl"]
            break

    result_response = requests.get(result_url)
    blobstore_url = result_response.json()["url"]

    blobstore_response = requests.get(blobstore_url)
    with open("files.zip", "wb") as f:
        f.write(blobstore_response.content)

    print("Done! Files stored at: files.zip")


if __name__ == '__main__':
    main()
