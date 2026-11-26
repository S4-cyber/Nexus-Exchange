# Awesome engineering resource library

Surveyed 2026-11-25 from [GitHub's Awesome topic](https://github.com/topics/awesome), its main index, and related curated lists. This is an initial filtered survey, not an exhaustive crawl of the topic. The machine-readable [catalog.json](catalog.json) records 19 pinned repositories, exact observed file/blob references, license hints (not clearance), applicable existing H01-H08 workstreams, and review next steps. All entries are **REFERENCE_ONLY**. No upstream source, prompts, skills, model weights or executable dependencies are vendored.

## Browse offline

From a source checkout:

```sh
python -m nexus_exchange.resource_catalog
python -m nexus_exchange.resource_catalog --workstream H06
python -m nexus_exchange.resource_catalog --category local-inference
```

This local standard-library CLI validates the closed JSON schema, bounds the input, rejects unpinned or duplicate resources and authority fields, then emits deterministic pinned links and human-written review metadata. It never follows the links or runs tools. It is a source/developer feature, not yet included in the packaged desktop GUI. Its output is untrusted reference data, not model instructions or execution authorization.

## Curated directory

Priority 1 = evaluate first; 2 = useful secondary reference; 3 = exploratory. No rating, adoption approval or assertion that an upstream project is secure.

| Resource | Category | Workstreams | Priority |
|---|---|---|---|
| [anchore/syft](https://github.com/anchore/syft/tree/bbb56b7d5a55fd1cdca9a02e254b24feb92c061d) | security | H06, H07 | 1 |
| [ggml-org/llama.cpp](https://github.com/ggml-org/llama.cpp/tree/2d5b3ddde360cbcefc641cc46cd9e00d700f277a) | local-inference | H01, H04, H07 | 1 |
| [gitleaks/gitleaks](https://github.com/gitleaks/gitleaks/tree/5f6ec56cfa6f8c67648d863582c7ae2f206d5c1c) | security | H06, H07 | 1 |
| [ollama/ollama](https://github.com/ollama/ollama/tree/784dd544291825e8f5f064672dc2bd7f4d9345ed) | local-inference | H01, H03, H04, H07 | 1 |
| [PyCQA/bandit](https://github.com/PyCQA/bandit/tree/2d5467c45c3189f4d7d07e8022276bc73a478abd) | security | H06, H07 | 1 |
| [pydantic/pydantic-ai](https://github.com/pydantic/pydantic-ai/tree/ffbcf3ec5fbf4cf2044ebb7366e3554c82e27a5f) | agents | H01, H04, H06, H07, H08 | 1 |
| [pypa/pip-audit](https://github.com/pypa/pip-audit/tree/864264baeb9a9e30115a0f2838fe4769cf5a0840) | security | H06, H07 | 1 |
| [rafska/awesome-local-llm](https://github.com/rafska/awesome-local-llm/tree/d8b5e8530e906b345e18034986afe1c04d1fd138) | local-inference | H01, H03, H04, H07 | 1 |
| [awesomedata/awesome-public-datasets](https://github.com/awesomedata/awesome-public-datasets/tree/f1c36b86c0e14310c002eefcdc115e44094773d4) | data | H03, H04, H08 | 2 |
| [backblaze-labs/awesome-agent-infrastructure](https://github.com/backblaze-labs/awesome-agent-infrastructure/tree/a36a64e24c3cfa525278d7487f9b560774e7f331) | infrastructure | H01, H02, H03, H04, H06, H07 | 2 |
| [kaushikb11/awesome-llm-agents](https://github.com/kaushikb11/awesome-llm-agents/tree/0db5a88b2b0637be3f053f4fd9ab135f83275cdb) | agents | H01, H02, H03, H04, H07, H08 | 2 |
| [modelcontextprotocol/python-sdk](https://github.com/modelcontextprotocol/python-sdk/tree/77001c96f9507be0f4d009b83210a384a5e08bda) | agents | H01, H02, H06, H07, H08 | 2 |
| [ossf/scorecard](https://github.com/ossf/scorecard/tree/789a810815a4398abf14b10898b111d3ced5d94d) | security | H06, H07 | 2 |
| [public-apis/public-apis](https://github.com/public-apis/public-apis/tree/9fb3bdb62643400aaebee03a2ecce0cd1ec934eb) | data | H02, H04, H08 | 2 |
| [sindresorhus/awesome](https://github.com/sindresorhus/awesome/tree/bc98e517ddca672f55f9857d714fc3ea3c3540b2) | index | H01, H05, H06, H07 | 2 |
| [tysoncung/awesome-devsecops](https://github.com/tysoncung/awesome-devsecops/tree/247ff92d2fe01d1f783a03ae4061d95f3554cd5d) | security | H06, H07 | 2 |
| [vinta/awesome-python](https://github.com/vinta/awesome-python/tree/4c3cb15dc695e95ae64add86b9994add8277f323) | language | H01, H03, H04, H05, H07 | 2 |
| [Awesome-llms-labs/awesome-ai-agents](https://github.com/Awesome-llms-labs/awesome-ai-agents/tree/90685bdc9255a652dff90366b7807360ece0ff9a) | agents | H01, H02, H04, H08 | 3 |
| [awesome-selfhosted/awesome-selfhosted](https://github.com/awesome-selfhosted/awesome-selfhosted/tree/6e7abbc2294fde161ce28811c5e2a7db9d498ba0) | infrastructure | H03, H05, H07 | 3 |

Read [ADOPTION.md](ADOPTION.md) for the required review procedure. The existing [agent engineering adoption plan](../../docs/AGENT_ENGINEERING_ADOPTION.md) remains authoritative for project-local H01-H08 mapping. Existing source restrictions, Governor policies, three-attempt limit, and separate human/commercial approval remain in force.
