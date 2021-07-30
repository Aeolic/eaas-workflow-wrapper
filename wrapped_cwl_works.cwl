class: CommandLineTool
id: template.cwl
inputs:
- id: biom
  type: File?
- id: hdf5
  label: Output as HDF5-formatted table.
  type: boolean?
- id: header_key
  doc: |
    The observation metadata to include from the input BIOM table file when
    creating a tsv table file. By default no observation metadata will be
    included.
  type: string?
- id: json
  label: Output as JSON-formatted table.
  type: boolean?
- id: table_type
  type: string?
- id: tsv
  label: Output as TSV-formatted (classic) table.
  type: boolean?
outputs:
- id: logfile
  outputBinding:
    glob: '*.log'
  type: File
- id: result
  outputBinding:
    glob: |
      ${ var ext = "";
      if (inputs.json) { ext = "_json.biom"; }
      if (inputs.hdf5) { ext = "_hdf5.biom"; }
      if (inputs.tsv) { ext = "_tsv.biom"; }
      var pre = inputs.biom.nameroot.split('.');
      pre.pop()
      return pre.join('.') + ext; }
  type: File
requirements:
- class: DockerRequirement
  dockerPull: aeolic/cwl-wrapper:latest
  dockerOutputDirectory: /app/output
- class: InitialWorkDirRequirement
  listing:
  - entryname: config.json
    entry: |-
      {
          "environmentId": "50e4bdfa-0762-430e-abae-7b73c4b50da4",
          "inputFolder": "/input",
          "outputFolder": "/output",
          "inputFiles": [
              "$(inputs.biom.path)"
          ],
          "arguments": {
              "0": "biom",
              "1": "convert"
          },
          "unordered": {
              "--input-fp": "$('/input/' + inputs.biom.basename)",
              "--to-hdf5": "$(inputs.hdf5)",
              "--header-key": "$(inputs.header_key)",
              "--to-json": "$(inputs.json)",
              "--table-type": "$(inputs.table_type)",
              "--to-tsv": "$(inputs.tsv)",
              "--output-fp": "${ var ext = "/output/";    if (inputs.json) { ext += "_json.biom";} if (inputs.hdf5) { ext += "_hdf5.biom"; }    if (inputs.tsv) { ext += "_tsv.biom"; }    var pre = inputs.biom.nameroot.split('.');    pre.pop();    return pre.join('.') + ext; }",
              "--collapsed-observations": "true"
          }
      }
- class: InlineJavascriptRequirement
cwlVersion: v1.0
baseCommand:
- python3
- /app/wrapper.py
