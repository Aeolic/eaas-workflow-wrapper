import json

import demjson as demjson


print(help(demjson))
demjson.json_options.strictness = demjson.STRICTNESS_TOLERANT

a = {
    "abc" : "def",
    "xyz" : "('{1}/' + inputs.{0}.basename)"
}

b = "{\"containerUrl\":\"https://historic-builds.emulation.cloud:443/blobstore/api/v1/blobs/imagebuilder-outputs/78567431-9394-44ff-9cc9-2f8931957792\",\"metadata\":{\"containerSourceUrl\":\"docker://aeolic/cwl-test-tool\",\"entryProcesses\":[\"python3\",\"main.py\"],\"envVariables\":[\"PATH=/usr/local/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin\",\"LANG=C.UTF-8\",\"GPG_KEY=E3FF2839C048B25C084DEBE9B26995E310250568\",\"PYTHON_VERSION=3.8.10\",\"PYTHON_PIP_VERSION=21.1.2\",\"PYTHON_GET_PIP_URL=https://github.com/pypa/get-pip/raw/936e08ce004d0b2fae8952c50f7ccce1bc578ce5/public/get-pip.py\",\"PYTHON_GET_PIP_SHA256=8890955d56a8262348470a76dc432825f61a84a54e2985a86cd520f656a6e220\"],\"workingDir\":\"/app\",\"containerDigest\":\"sha256:69f2611e2d3d3521055b96cfbd85fda32ef4c04ac7b556b45d5f79f679d1fbf5\",\"tag\":\"latest\",\"emulatorType\":\"null\",\"emulatorVersion\":\"null\"}}"

x = eval(b)

print(json.dumps(x,indent=4))

