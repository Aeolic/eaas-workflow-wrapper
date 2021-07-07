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
          {
            "environmentId": "$(inputs.environment)",
            "inputFolder": "$(inputs.inputFolder)",
            "outputFolder": "$(inputs.outputFolder)",
            "inputFiles": ${
              var r = [];
              for (const val of inputs.inputFiles) {
                r.push(val.path);}
              return r;},
            "arguments": ${
              var a = {};
              for (var i = 0; i < inputs.args.length; i++) {
                a[''+i] = inputs.args[i];}
              return a;}
          }

inputs: 
  []

outputs:
  logfile:
    type: File
    outputBinding:
      glob: '*.log'