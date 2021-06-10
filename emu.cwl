#!/usr/bin/env cwl-runner

cwlVersion: v1.0
class: CommandLineTool
baseCommand: [python3, wrapper.py]
inputs:
  environment:
    type: string
    inputBinding:
      position: 1

outputs:
  data_from_emu:
    type: File
    outputBinding:
      glob: output.txt
